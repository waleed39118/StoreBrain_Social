"""Composition root and console entry point.

``Atheer.build()`` wires every component once; the console (``atheer``) and the
HTTP server (``atheer-server``) both use it, so they behave identically.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from atheer.appointments.service import AppointmentService
from atheer.assistant.brain import Brain
from atheer.calculations.engine import CalcEngine
from atheer.core.config import Settings, get_settings
from atheer.core.console import configure_console
from atheer.core.events import DomainEvent, EventBus
from atheer.db.session import create_engine_from_settings, init_db, make_session_factory
from atheer.queue.service import QueueService
from atheer.secretary import SecretaryCore
from atheer.updater.service import AutoUpdater
from atheer.updater.terminology import TerminologyStore
from atheer.voice.engine import VoiceEngine

logger = logging.getLogger("atheer")


@dataclass
class Atheer:
    settings: Settings
    events: EventBus
    voice: VoiceEngine
    secretary: SecretaryCore
    calc: CalcEngine
    terminology: TerminologyStore
    updater: AutoUpdater | None
    _tasks: list[asyncio.Task[None]] = field(default_factory=list)

    @classmethod
    def build(cls, settings: Settings | None = None, *, voice: VoiceEngine | None = None) -> Atheer:
        settings = settings or get_settings()
        engine = create_engine_from_settings(settings)
        init_db(engine)
        sf = make_session_factory(engine)
        events = EventBus()
        appointments = AppointmentService(sf, settings, events=events)
        queue = QueueService(sf, settings, events=events)
        voice = voice or VoiceEngine.from_settings(settings)
        secretary = SecretaryCore(settings, appointments, queue, Brain(settings, appointments, queue), voice)

        # Queue call-outs go to the speakers in both languages, whoever triggered them.
        def _on_called(event: DomainEvent) -> None:
            voice.say(event.payload["text_ar"], "ar")
            voice.say(event.payload["text_en"], "en")

        events.subscribe("queue.called", _on_called)
        events.subscribe("*", secretary.record_alerts)

        calc = CalcEngine()
        if settings.formulary_path:
            calc.load_formulary(settings.formulary_path)
        terminology = TerminologyStore()

        updater = None
        if settings.update_public_key:
            updater = AutoUpdater(settings)
            updater.subscribe(terminology.load)
            updater.subscribe(lambda release: _load_release_formulary(calc, release))
            try:
                updater.activate_current()
            except Exception:  # noqa: BLE001 - keep serving patients; staff see the error in logs/status
                logger.exception("Installed content release could not be loaded; continuing without it")

        return cls(settings, events, voice, secretary, calc, terminology, updater)

    # ------------------------------------------------------------- lifecycle

    async def start(self, *, listen: bool = True) -> None:
        """Start background loops: speakers, microphone (if enabled) and auto-updates (if configured)."""
        self._tasks.append(asyncio.create_task(self.voice.speaker_loop(), name="speaker"))
        await asyncio.sleep(0)  # let the speaker loop bind to this event loop before anyone speaks
        if listen and self.voice.can_listen:
            self._tasks.append(asyncio.create_task(self._listen_loop(), name="microphone"))
        if self.updater is not None and self.settings.update_manifest_url:
            self._tasks.append(asyncio.create_task(self.updater.run(self._is_quiet), name="updater"))
        self.voice.say(f"أثير جاهزة للخدمة في {self.settings.clinic_name}.", "ar")

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _listen_loop(self) -> None:
        """Lobby microphone: a public channel, so staff-only commands are refused."""
        async for transcript in self.voice.listen():
            print(f"🎙 [{transcript.language}] {transcript.text}", flush=True)
            try:
                reply = await asyncio.to_thread(self.secretary.handle_text, transcript.text, staff=False, speak=True)
                print(f"Atheer> {reply.text}", flush=True)
            except Exception:  # noqa: BLE001 - keep listening
                logger.exception("Failed to handle spoken request")

    def _is_quiet(self) -> bool:
        """Apply content updates only while nobody is waiting (the swap is atomic either way)."""
        return not self.secretary.queue.waiting()

    # ------------------------------------------------------------- console

    async def run_console(self) -> None:
        """Staff console: typed requests run with staff rights; replies are also spoken when voice is off."""
        await self.start()
        try:
            while True:
                try:
                    line = await asyncio.to_thread(input, "You> ")
                except EOFError:
                    return
                if line.strip().lower() in {"exit", "quit", "خروج"}:
                    return
                try:
                    reply = await asyncio.to_thread(
                        self.secretary.handle_text, line, staff=True, speak=not self.voice.can_listen
                    )
                    if reply.text:
                        print(f"Atheer> {reply.text}", flush=True)
                except Exception as exc:  # noqa: BLE001 - keep the desk running; log and report
                    logger.exception("Failed to handle text input")
                    print(f"Atheer> ⚠ {exc}", flush=True)
        finally:
            await asyncio.sleep(0.05)  # let queued speech reach the speakers
            await self.stop()


def _load_release_formulary(calc: CalcEngine, release: Path) -> None:
    path = release / "formulary.json"
    if path.is_file():
        calc.load_formulary(path)


def main() -> None:
    configure_console()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(Atheer.build().run_console())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
