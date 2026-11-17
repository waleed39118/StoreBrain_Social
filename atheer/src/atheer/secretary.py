"""SecretaryCore: the receptionist's single entry point.

Combines appointments, the arrival queue, the conversational brain and the
speakers. It holds no business rules of its own: those live in the tested
services it delegates to, so the API, the console and the voice loop all
behave identically.
"""

from __future__ import annotations

import hmac
from datetime import date

from pydantic import BaseModel

from atheer.appointments.exceptions import NotFoundError
from atheer.appointments.schemas import (
    AppointmentView,
    BookingRequest,
    BookingResult,
    RescheduleRequest,
    Slot,
    StaffAlert,
)
from atheer.appointments.service import AppointmentService
from atheer.assistant.brain import Brain, Reply
from atheer.core.clock import Clock, SystemClock
from atheer.core.config import Settings
from atheer.db.models import AppointmentStatus
from atheer.queue.service import Announcement, QueueService, TicketView
from atheer.voice.engine import VoiceEngine


class CheckInResult(BaseModel):
    appointment: AppointmentView
    ticket: TicketView
    greeting: str
    language: str
    alerts: list[StaffAlert]


class SecretaryCore:
    def __init__(
        self,
        settings: Settings,
        appointments: AppointmentService,
        queue: QueueService,
        brain: Brain,
        voice: VoiceEngine,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.settings = settings
        self.appointments = appointments
        self.queue = queue
        self.brain = brain
        self.voice = voice
        self._clock = clock or SystemClock()

    # ------------------------------------------------------------- conversation

    def handle_text(self, text: str, *, staff: bool = False, speak: bool = False) -> Reply:
        """Answer a typed or transcribed request. ``speak`` sends public-safe replies to the speakers."""
        reply = self.brain.handle(text, staff=staff)
        if speak and reply.speak:
            self.voice.say(reply.text, reply.language)
        return reply

    def greet_visitor(self, first_name: str | None = None, language: str = "ar") -> str:
        """Spoken welcome for someone at the desk. Uses the first name only, and only when enabled."""
        name = first_name.strip() if first_name and self.settings.greet_by_name else ""
        if language == "ar":
            text = f"أهلًا وسهلًا{(' ' + name) if name else ''}، مرحبًا بك في {self.settings.clinic_name}."
        else:
            text = f"Welcome{(' ' + name) if name else ''} to {self.settings.clinic_name}."
        self.voice.say(text, language)
        return text

    # ------------------------------------------------------------- arrival

    def check_in(self, appointment_id: int, mrn: str) -> CheckInResult:
        """Kiosk/desk check-in: verify identity, mark arrived, issue a queue ticket, greet by first name.

        The MRN must match the appointment's patient. A mismatch is reported exactly
        like a missing appointment, so the kiosk can't be used to probe records.
        """
        ctx = self.appointments.context(appointment_id)
        if not hmac.compare_digest(ctx.patient_mrn.encode(), mrn.strip().encode()):
            raise NotFoundError(f"Appointment {appointment_id} not found.")

        # Transition first: it validates the state, so a rejected check-in never leaves an orphan ticket.
        result = self.appointments.transition(appointment_id, AppointmentStatus.CHECKED_IN)
        ticket = self.queue.issue(
            patient_id=ctx.appointment.patient_id,
            doctor_id=ctx.appointment.doctor_id,
            appointment_id=appointment_id,
        )

        lang = "ar" if ctx.preferred_language == "ar" else "en"
        name = ctx.patient_first_name if self.settings.greet_by_name else ""
        if lang == "ar":
            greeting = (
                f"أهلًا{(' ' + name) if name else ''}، تم تسجيل حضورك لموعدك مع الدكتور {ctx.doctor_name}. "
                f"رقمك {ticket.number}، تفضل بالجلوس وسننادي رقمك قريبًا."
            )
        else:
            greeting = (
                f"Welcome{(' ' + name) if name else ''}, you're checked in to see Dr. {ctx.doctor_name}. "
                f"Your number is {ticket.number}; please have a seat and we'll call you shortly."
            )
        self.voice.say(greeting, lang)
        return CheckInResult(
            appointment=result.appointment, ticket=ticket, greeting=greeting, language=lang, alerts=result.alerts
        )

    def walk_in(self, *, doctor_id: int | None = None) -> TicketView:
        return self.queue.issue(doctor_id=doctor_id)

    # ------------------------------------------------------------- calling & announcements

    def call_next(self, counter: str, *, doctor_id: int | None = None) -> Announcement | None:
        """Call the next ticket. The AR/EN call-out reaches the speakers via the ``queue.called`` event."""
        return self.queue.call_next(counter, doctor_id=doctor_id)

    def announce_doctor(self, doctor_id: int, *, arrived: bool) -> tuple[str, str]:
        """Announce a doctor's arrival or departure on the speakers (Arabic, then English)."""
        doctor_name = self.appointments.doctor_name(doctor_id)
        if arrived:
            text = (f"وصل الدكتور {doctor_name} إلى العيادة.", f"Dr. {doctor_name} has arrived.")
        else:
            text = (f"غادر الدكتور {doctor_name} العيادة.", f"Dr. {doctor_name} has left the clinic.")
        self.voice.say(text[0], "ar")
        self.voice.say(text[1], "en")
        return text

    # ------------------------------------------------------------- scheduling

    def book(self, request: BookingRequest) -> BookingResult:
        return self.appointments.book(request)

    def reschedule(self, request: RescheduleRequest) -> AppointmentView:
        return self.appointments.reschedule(request)

    def set_status(self, appointment_id: int, status: AppointmentStatus) -> BookingResult:
        return self.appointments.transition(appointment_id, status)

    def free_slots(self, doctor_id: int, day: date) -> list[Slot]:
        return self.appointments.free_slots(doctor_id, day)

    def alerts(self, day: date | None = None) -> list[StaffAlert]:
        """Everything staff should look at now: late-running and conflicting appointments."""
        day = day or self._today()
        return self.appointments.running_late_alerts() + self.appointments.conflict_alerts(day)

    def _today(self) -> date:
        return self._clock.now().astimezone(self.settings.tz).date()
