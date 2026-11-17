"""Process entry point: wires services and runs text, voice, speaker and update loops concurrently.

    python -m atheer.runtime
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass

from atheer.appointments.service import AppointmentService
from atheer.assistant.brain import Brain, Reply
from atheer.core.config import Settings, get_settings
from atheer.core.events import DomainEvent, EventBus
from atheer.db.session import create_engine_from_settings, init_db, make_session_factory
from atheer.queue.service import QueueService
from atheer.voice.engines import LogTTS, SpeechToText, TextToSpeech

logger = logging.getLogger("atheer")


@dataclass
class Atheer:
    settings: Settings
    events: EventBus
    appointments: AppointmentService
    queue: QueueService
    brain: Brain
    tts: TextToSpeech
    stt: SpeechToText | None

    @classmethod
    def build(cls, settings: Settings | None = None) -> Atheer:
        settings = settings or get_settings()
        engine = create_engine_from_settings(settings)
        init_db(engine)
        sf = make_session_factory(engine)
        events = EventBus()
        appointments = AppointmentService(sf, settings, events=events)
        queue = QueueService(sf, settings, events=events)
        tts, stt = _build_voice(settings)
        return cls(settings, events, appointments, queue, Brain(settings, appointments, queue), tts, stt)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        speech: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        # Event handlers may fire on worker threads; hand speech to the loop safely.
        def _on_called(event: DomainEvent) -> None:
            for text, lang in ((event.payload["text_ar"], "ar"), (event.payload["text_en"], "en")):
                loop.call_soon_threadsafe(speech.put_nowait, (text, lang))

        self.events.subscribe("queue.called", _on_called)

        tasks = [
            asyncio.create_task(self._speaker(speech), name="speaker"),
            asyncio.create_task(self._text_loop(speech), name="text"),
        ]
        if self.stt is not None:
            tasks.append(asyncio.create_task(self._voice_loop(speech), name="voice"))
        if self.settings.update_manifest_url and self.settings.update_public_key:
            from atheer.updater.service import run_update_loop

            tasks.append(asyncio.create_task(run_update_loop(self.settings, self._is_quiet), name="updater"))

        await speech.put((f"أثير جاهزة للخدمة في {self.settings.clinic_name}.", "ar"))
        try:
            # The text loop ending (EOF / "exit") shuts everything down.
            await tasks[1]
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    # ---------------------------------------------------------------- loops

    async def _respond(self, text: str, speech: asyncio.Queue[tuple[str, str]], *, spoken_input: bool) -> Reply:
        # The console is the staff desk; the lobby microphone is a public channel.
        reply = await asyncio.to_thread(self.brain.handle, text, staff=not spoken_input)
        if reply.text:
            print(f"Atheer> {reply.text}", flush=True)
            if reply.speak and (spoken_input or self.stt is None):
                await speech.put((reply.text, reply.language))
        return reply

    async def _text_loop(self, speech: asyncio.Queue[tuple[str, str]]) -> None:
        while True:
            try:
                line = await asyncio.to_thread(input, "You> ")
            except EOFError:
                return
            if line.strip().lower() in {"exit", "quit", "خروج"}:
                return
            try:
                await self._respond(line, speech, spoken_input=False)
            except Exception as exc:  # noqa: BLE001 - keep the desk running; log and report
                logger.exception("Failed to handle text input")
                print(f"Atheer> ⚠ {exc}", flush=True)

    async def _voice_loop(self, speech: asyncio.Queue[tuple[str, str]]) -> None:
        from atheer.voice.microphone import microphone_utterances

        assert self.stt is not None
        async for pcm in microphone_utterances():
            try:
                transcript = await self.stt.transcribe(pcm)
                if not transcript.text or transcript.confidence < self.settings.min_stt_confidence:
                    continue  # ignore noise / low-confidence fragments rather than act on a guess
                print(f"🎙 [{transcript.language}] {transcript.text}", flush=True)
                await self._respond(transcript.text, speech, spoken_input=True)
            except Exception:  # noqa: BLE001
                logger.exception("Voice pipeline error")

    async def _speaker(self, speech: asyncio.Queue[tuple[str, str]]) -> None:
        while True:
            text, lang = await speech.get()
            try:
                await self.tts.speak(text, lang)
            except Exception:  # noqa: BLE001 - a TTS fault must not stop the queue
                logger.exception("TTS failed; falling back to console")
                await LogTTS().speak(text, lang)

    def _is_quiet(self) -> bool:
        """Apply content updates only while nobody is waiting (swap is atomic either way)."""
        return not self.queue.waiting()


def _build_voice(settings: Settings) -> tuple[TextToSpeech, SpeechToText | None]:
    if not settings.voice_enabled:
        return LogTTS(), None
    try:
        from atheer.voice.engines import PiperTTS, WhisperSTT

        voices = {k: v for k, v in (("ar", settings.voice_model_ar), ("en", settings.voice_model_en)) if v}
        tts: TextToSpeech = PiperTTS(voices) if voices else LogTTS()
        return tts, WhisperSTT(settings.stt_model)
    except (ImportError, OSError) as exc:
        logger.warning("Voice disabled (%s). Install with: pip install '.[voice]'", exc)
        return LogTTS(), None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(Atheer.build().run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
