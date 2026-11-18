"""Speech-to-text and text-to-speech engines.

All engines are local/offline (Whisper, Piper, pyttsx3) so patient audio never
leaves the clinic. Heavy dependencies are imported lazily, so the text-only
deployment and the test suite don't need them.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000  # Whisper and webrtcvad both operate on 16 kHz mono int16


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    language: str  # ISO 639-1, e.g. "ar" / "en"
    confidence: float  # 0..1


class SpeechToText(Protocol):
    async def transcribe(self, pcm16: bytes) -> Transcript: ...


class TextToSpeech(Protocol):
    async def speak(self, text: str, language: str) -> None: ...


class WhisperSTT:
    """faster-whisper wrapper. Runs inference in a worker thread to keep the event loop responsive."""

    def __init__(self, model_size: str = "medium", device: str = "auto", compute_type: str = "int8") -> None:
        from faster_whisper import WhisperModel  # lazy: optional dependency

        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def _run(self, pcm16: bytes) -> Transcript:
        import numpy as np

        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        segments, info = self._model.transcribe(audio, beam_size=5, vad_filter=False)
        segments = list(segments)
        text = " ".join(s.text.strip() for s in segments).strip()
        # avg_logprob is ~[-1, 0]; map to a rough 0..1 confidence.
        conf = sum(min(1.0, max(0.0, 1.0 + s.avg_logprob)) for s in segments) / len(segments) if segments else 0.0
        return Transcript(text=text, language=info.language, confidence=conf)

    async def transcribe(self, pcm16: bytes) -> Transcript:
        return await asyncio.to_thread(self._run, pcm16)


class PiperTTS:
    """Piper neural TTS with one voice model per language; plays to the default speaker."""

    def __init__(self, voices: dict[str, Path]) -> None:
        from piper import PiperVoice  # lazy: optional dependency

        missing = [str(p) for p in voices.values() if not Path(p).is_file()]
        if missing:
            raise FileNotFoundError(f"Piper voice models not found: {missing}")
        self._voices = {lang: PiperVoice.load(str(path)) for lang, path in voices.items()}
        self._lock = asyncio.Lock()  # one speaker: never overlap utterances

    def _run(self, text: str, language: str) -> None:
        import numpy as np
        import sounddevice as sd

        voice = self._voices.get(language) or next(iter(self._voices.values()))
        audio = b"".join(chunk.audio_int16_bytes for chunk in voice.synthesize(text))
        sd.play(np.frombuffer(audio, dtype=np.int16), samplerate=voice.config.sample_rate, blocking=True)

    async def speak(self, text: str, language: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._run, text, language)


class LogTTS:
    """Fallback when no audio stack is installed: speech goes to the log/console."""

    async def speak(self, text: str, language: str) -> None:
        logger.info("[TTS:%s] %s", language, text)
        print(f"🔊 [{language}] {text}", flush=True)


class OpenAIWhisperSTT:
    """Reference ``openai-whisper`` package. Heavier (PyTorch) than faster-whisper; same model weights."""

    def __init__(self, model_size: str = "medium") -> None:
        import whisper  # lazy: optional dependency (pip install ".[whisper]")

        self._model = whisper.load_model(model_size)

    def _run(self, pcm16: bytes) -> Transcript:
        import numpy as np

        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        result = self._model.transcribe(audio, fp16=False)
        segments = result.get("segments") or []
        conf = (
            sum(min(1.0, max(0.0, 1.0 + s["avg_logprob"])) for s in segments) / len(segments) if segments else 0.0
        )
        return Transcript(text=result.get("text", "").strip(), language=result.get("language", "en"), confidence=conf)

    async def transcribe(self, pcm16: bytes) -> Transcript:
        return await asyncio.to_thread(self._run, pcm16)


_AR_NAME_HINTS = ("arabic", "naayf", "hoda", "ar-sa", "ar_sa", "ar-eg", "ar_eg")
_EN_NAME_HINTS = ("english", "en-us", "en_us", "en-gb", "en_gb")


def _voice_language(voice: object) -> str | None:
    """Best-effort language ("ar"/"en") of a pyttsx3 voice; drivers report it inconsistently.

    eSpeak gives language tags as bytes with a leading priority byte (b"\\x05en-us");
    Windows SAPI often gives none, so the voice name/id is checked as well.
    """
    for raw in getattr(voice, "languages", None) or []:
        tag = (raw.decode(errors="ignore") if isinstance(raw, bytes) else str(raw)).lstrip("".join(map(chr, range(32)))).lower()
        if tag.startswith("ar"):
            return "ar"
        if tag.startswith("en"):
            return "en"
    label = f"{getattr(voice, 'name', '')} {getattr(voice, 'id', '')}".lower()
    if any(hint in label for hint in _AR_NAME_HINTS):
        return "ar"
    if any(hint in label for hint in _EN_NAME_HINTS):
        return "en"
    return None


class Pyttsx3TTS:
    """System voices via pyttsx3 (SAPI5 on Windows, NSSpeech on macOS, eSpeak on Linux).

    No model downloads and fully offline. Quality and Arabic support depend on the
    installed OS voices: on Windows, add the Arabic language pack for "Naayf"/"Hoda".
    pyttsx3 engines are not thread-safe, so one dedicated worker thread owns the engine.
    """

    def __init__(self, rate: int = 165, *, engine_factory: Callable[[], Any] | None = None) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pyttsx3")
        self._factory = engine_factory or _pyttsx3_factory
        self._rate = rate
        self._engine: Any = None
        self.voices: dict[str, str] = {}  # language → voice id
        self._executor.submit(self._init).result()  # fail fast if no TTS driver is available

    def _init(self) -> None:
        self._engine = self._factory()
        self._engine.setProperty("rate", self._rate)
        for voice in self._engine.getProperty("voices") or []:
            lang = _voice_language(voice)
            if lang and lang not in self.voices:
                self.voices[lang] = voice.id
        if "ar" not in self.voices:
            logger.warning("No Arabic system voice found; Arabic text will use the default voice.")

    def _speak(self, text: str, language: str) -> None:
        voice_id = self.voices.get(language) or self.voices.get("en")
        if voice_id:
            self._engine.setProperty("voice", voice_id)
        self._engine.say(text)
        self._engine.runAndWait()

    async def speak(self, text: str, language: str) -> None:
        await asyncio.get_running_loop().run_in_executor(self._executor, self._speak, text, language)


def _pyttsx3_factory() -> Any:
    import pyttsx3  # lazy: optional dependency

    return pyttsx3.init()
