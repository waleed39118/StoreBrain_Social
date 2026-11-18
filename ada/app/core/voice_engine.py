"""VoiceEngine: offline STT (OpenAI Whisper, local model) and TTS (pyttsx3).

* Models load lazily on first use so the API boots instantly and tests need no torch.
* Both backends are CPU-bound and not thread-safe -> serialised with locks and meant to be
  called via ``asyncio.to_thread`` from async endpoints.
* Whisper needs ``ffmpeg`` on PATH; pyttsx3 on Linux needs ``espeak-ng``.
"""
import logging
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings

log = logging.getLogger("ada.voice")


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str  # ISO code detected by Whisper, e.g. "ar" / "en"


class VoiceEngine:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._stt_model = None
        self._stt_lock = threading.Lock()
        self._tts_lock = threading.Lock()
        self._out_dir = Path(settings.tts_output_dir)
        self._out_dir.mkdir(parents=True, exist_ok=True)

    # ---------- STT ----------
    def _model(self):
        if self._stt_model is None:
            import whisper  # heavy import deferred
            log.info("Loading Whisper model '%s'", self.s.whisper_model)
            self._stt_model = whisper.load_model(self.s.whisper_model)
        return self._stt_model

    def transcribe(self, audio: bytes, suffix: str = ".wav") -> Transcript:
        """Transcribe raw audio bytes (any ffmpeg-readable format). Language auto-detected."""
        if not audio:
            raise ValueError("Empty audio")
        if len(audio) > self.s.max_audio_bytes:
            raise ValueError("Audio too large")
        with tempfile.NamedTemporaryFile(suffix=suffix) as f:
            f.write(audio); f.flush()
            with self._stt_lock:
                result = self._model().transcribe(f.name, fp16=False, task="transcribe")
        return Transcript(text=result.get("text", "").strip(), language=result.get("language", "en"))

    # ---------- TTS ----------
    def synthesize(self, text: str, language: str = "en") -> Path:
        """Render speech to a WAV file and return its path.

        pyttsx3 keeps global driver state, so a fresh engine is created per call under a lock
        (avoids the known 'run loop already started' deadlock in long-running servers).
        """
        import pyttsx3
        path = self._out_dir / f"{uuid.uuid4().hex}.wav"
        with self._tts_lock:
            engine = pyttsx3.init()
            try:
                engine.setProperty("rate", self.s.tts_rate)
                voice = self._pick_voice(engine, language)
                if voice:
                    engine.setProperty("voice", voice)
                engine.save_to_file(text, str(path))
                engine.runAndWait()
            finally:
                engine.stop()
        return path

    def _pick_voice(self, engine, language: str) -> str | None:
        hint = (self.s.tts_voice_hint or language).lower()
        for v in engine.getProperty("voices"):
            langs = " ".join(l.decode() if isinstance(l, bytes) else str(l)
                             for l in (getattr(v, "languages", []) or []))
            if hint in f"{v.id} {v.name} {langs}".lower():
                return v.id
        return None
