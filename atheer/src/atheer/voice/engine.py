"""VoiceEngine: one owner for speech output (a single ordered speaker queue) and speech input."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from atheer.core.config import Settings
from atheer.voice.engines import LogTTS, SpeechToText, TextToSpeech, Transcript

logger = logging.getLogger(__name__)


class VoiceEngine:
    """Thread-safe ``say()`` for any caller; one speaker loop plays utterances in order.

    Domain services run in worker threads (API thread pool, ``asyncio.to_thread``),
    so ``say()`` hands speech to the event loop with ``call_soon_threadsafe``.
    """

    def __init__(self, tts: TextToSpeech, stt: SpeechToText | None = None, *, min_confidence: float = 0.45) -> None:
        self.tts = tts
        self.stt = stt
        self.min_confidence = min_confidence
        self._queue: asyncio.Queue[tuple[str, str]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> VoiceEngine:
        return cls(*_build_engines(settings), min_confidence=settings.min_stt_confidence)

    @property
    def can_listen(self) -> bool:
        return self.stt is not None

    @property
    def tts_name(self) -> str:
        return type(self.tts).__name__

    # ------------------------------------------------------------- output

    def say(self, text: str, language: str) -> None:
        """Queue ``text`` for the speakers. Safe from any thread; before ``speaker_loop`` starts, logs only."""
        if not text:
            return
        if self._loop is None or self._queue is None:
            logger.info("[speech before speaker start:%s] %s", language, text)
            return
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (text, language))

    async def speaker_loop(self) -> None:
        """Run forever, playing queued utterances one at a time. Cancel to stop."""
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        try:
            while True:
                text, lang = await self._queue.get()
                try:
                    await self.tts.speak(text, lang)
                except Exception:  # noqa: BLE001 - a TTS fault must not silence the clinic
                    logger.exception("TTS failed; falling back to console")
                    await LogTTS().speak(text, lang)
        finally:
            self._loop = self._queue = None

    # ------------------------------------------------------------- input

    async def transcribe(self, pcm16: bytes) -> Transcript | None:
        """Transcribe 16 kHz mono PCM16. Returns None for silence or low-confidence audio rather than a guess."""
        if self.stt is None:
            raise RuntimeError("Speech recognition is not enabled (set ATHEER_VOICE_ENABLED=true).")
        transcript = await self.stt.transcribe(pcm16)
        if not transcript.text or transcript.confidence < self.min_confidence:
            return None
        return transcript

    async def listen(self) -> AsyncIterator[Transcript]:
        """Yield transcripts from the default microphone until cancelled."""
        from atheer.voice.microphone import microphone_utterances

        async for pcm in microphone_utterances():
            try:
                transcript = await self.transcribe(pcm)
            except Exception:  # noqa: BLE001 - one bad utterance must not stop listening
                logger.exception("Speech recognition failed")
                continue
            if transcript is not None:
                yield transcript


def _build_engines(settings: Settings) -> tuple[TextToSpeech, SpeechToText | None]:
    if not settings.voice_enabled:
        return LogTTS(), None
    return _build_tts(settings), _build_stt(settings)


def _build_tts(settings: Settings) -> TextToSpeech:
    choice = settings.tts_engine
    voices = {k: v for k, v in (("ar", settings.voice_model_ar), ("en", settings.voice_model_en)) if v}
    if choice == "console":
        return LogTTS()
    if choice == "piper" or (choice == "auto" and voices):
        try:
            from atheer.voice.engines import PiperTTS

            return PiperTTS(voices)
        except (ImportError, OSError) as exc:
            if choice == "piper":
                raise
            logger.warning("Piper unavailable (%s); trying pyttsx3", exc)
    try:
        from atheer.voice.engines import Pyttsx3TTS

        return Pyttsx3TTS(settings.tts_rate)
    except Exception as exc:  # noqa: BLE001 - pyttsx3 raises driver-specific errors
        if choice == "pyttsx3":
            raise
        logger.warning("pyttsx3 unavailable (%s); speech goes to the console", exc)
        return LogTTS()


def _build_stt(settings: Settings) -> SpeechToText | None:
    try:
        if settings.stt_engine == "openai-whisper":
            from atheer.voice.engines import OpenAIWhisperSTT

            return OpenAIWhisperSTT(settings.stt_model)
        from atheer.voice.engines import WhisperSTT

        return WhisperSTT(settings.stt_model)
    except (ImportError, OSError) as exc:
        logger.warning("Speech recognition disabled (%s). Install with: pip install '.[voice]'", exc)
        return None
