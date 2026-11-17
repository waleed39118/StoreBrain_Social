"""Speech-to-text and text-to-speech engines.

Defaults are local/offline (faster-whisper + Piper) so patient audio never
leaves the clinic. Heavy dependencies are imported lazily, so the text-only
deployment and the test suite don't need them.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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
