"""Daily arrival queue: tickets, calling, and bilingual (AR/EN) announcements.

Public announcements use the ticket number and room only. No names or clinical
details go to the speakers.
"""

from __future__ import annotations

from datetime import date, timezone

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from atheer.appointments.exceptions import InvalidTransitionError, NotFoundError
from atheer.calculations.operations import WaitEstimate, estimate_wait
from atheer.core.clock import Clock, SystemClock
from atheer.core.config import Settings
from atheer.core.events import DomainEvent, EventBus
from atheer.db.models import QueueTicket, TicketStatus
from atheer.db.session import session_scope

T = TicketStatus
_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    T.WAITING: frozenset({T.CALLED, T.SKIPPED}),
    T.CALLED: frozenset({T.CALLED, T.SERVING, T.SKIPPED}),  # CALLED→CALLED = recall
    T.SERVING: frozenset({T.DONE}),
    T.DONE: frozenset(),
    T.SKIPPED: frozenset({T.WAITING}),  # late arrival re-queued
}
_ISSUE_RETRIES = 3


class TicketView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    service_date: date
    status: TicketStatus
    doctor_id: int | None
    patient_id: int | None
    appointment_id: int | None
    counter: str | None


class Announcement(BaseModel):
    ticket: TicketView
    text_ar: str
    text_en: str


def announcement_text(number: int, counter: str | None) -> tuple[str, str]:
    """(Arabic, English) call-out. ``counter`` is a room label, e.g. "Room 3" / "3"."""
    return (
        f"الرقم {number}، تفضل إلى {counter or 'مكتب الاستقبال'} من فضلك.",
        f"Number {number}, please proceed to {counter or 'the reception desk'}.",
    )


class QueueService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Clock | None = None,
        events: EventBus | None = None,
    ) -> None:
        self._sf = session_factory
        self._settings = settings
        self._clock = clock or SystemClock()
        self._events = events or EventBus()

    def _today(self) -> date:
        return self._clock.now().astimezone(self._settings.tz).date()

    def issue(
        self, *, patient_id: int | None = None, doctor_id: int | None = None, appointment_id: int | None = None
    ) -> TicketView:
        """Issue the next number for today. The unique constraint plus retry handles concurrent kiosks."""
        today = self._today()
        for attempt in range(_ISSUE_RETRIES):
            try:
                with session_scope(self._sf) as s:
                    last = s.scalar(select(func.max(QueueTicket.number)).where(QueueTicket.service_date == today))
                    ticket = QueueTicket(
                        service_date=today,
                        number=(last or 0) + 1,
                        patient_id=patient_id,
                        doctor_id=doctor_id,
                        appointment_id=appointment_id,
                        issued_at=self._clock.now(),
                    )
                    s.add(ticket)
                    s.flush()
                    view = TicketView.model_validate(ticket)
                break
            except IntegrityError:
                if attempt == _ISSUE_RETRIES - 1:
                    raise
        self._events.publish(DomainEvent("queue.issued", {"ticket": view.model_dump(mode="json")}))
        return view

    def call_next(self, counter: str, *, doctor_id: int | None = None) -> Announcement | None:
        """Call the oldest waiting ticket (for ``doctor_id`` or unassigned tickets), or None if empty."""
        with session_scope(self._sf) as s:
            q = select(QueueTicket).where(
                QueueTicket.service_date == self._today(), QueueTicket.status == T.WAITING
            )
            if doctor_id is not None:
                q = q.where((QueueTicket.doctor_id == doctor_id) | QueueTicket.doctor_id.is_(None))
            ticket = s.scalars(q.order_by(QueueTicket.number).limit(1).with_for_update()).first()
            if ticket is None:
                return None
            self._apply(ticket, T.CALLED)
            ticket.counter = counter
            s.flush()
            view = TicketView.model_validate(ticket)
        return self._announce(view)

    def recall(self, ticket_id: int) -> Announcement:
        view = self._move(ticket_id, T.CALLED)
        return self._announce(view)

    def start_serving(self, ticket_id: int) -> TicketView:
        return self._move(ticket_id, T.SERVING)

    def finish(self, ticket_id: int) -> TicketView:
        return self._move(ticket_id, T.DONE)

    def skip(self, ticket_id: int) -> TicketView:
        return self._move(ticket_id, T.SKIPPED)

    def requeue(self, ticket_id: int) -> TicketView:
        return self._move(ticket_id, T.WAITING)

    def waiting(self) -> list[TicketView]:
        with session_scope(self._sf) as s:
            rows = s.scalars(
                select(QueueTicket)
                .where(QueueTicket.service_date == self._today(), QueueTicket.status == T.WAITING)
                .order_by(QueueTicket.number)
            ).all()
            return [TicketView.model_validate(r) for r in rows]

    def estimate_wait_for(self, ticket_id: int, *, doctors_on_duty: int = 1, history: int = 30) -> WaitEstimate:
        """Wait estimate from today's completed consultation durations."""
        with session_scope(self._sf) as s:
            ticket = s.get(QueueTicket, ticket_id)
            if ticket is None:
                raise NotFoundError(f"Ticket {ticket_id} not found.")
            ahead = s.scalar(
                select(func.count()).where(
                    QueueTicket.service_date == ticket.service_date,
                    QueueTicket.status == T.WAITING,
                    QueueTicket.number < ticket.number,
                )
            ) or 0
            done = s.execute(
                select(QueueTicket.served_at, QueueTicket.finished_at)
                .where(
                    QueueTicket.service_date == ticket.service_date,
                    QueueTicket.status == T.DONE,
                    QueueTicket.served_at.is_not(None),
                    QueueTicket.finished_at.is_not(None),
                )
                .order_by(QueueTicket.finished_at.desc())
                .limit(history)
            ).all()
        durations = [(f - st).total_seconds() / 60 for st, f in done]
        return estimate_wait(
            ahead,
            durations,
            doctors_on_duty=doctors_on_duty,
            fallback_minutes=self._settings.default_slot_minutes,
        )

    # ---------------------------------------------------------------- internals

    def _move(self, ticket_id: int, target: TicketStatus) -> TicketView:
        with session_scope(self._sf) as s:
            ticket = s.get(QueueTicket, ticket_id)
            if ticket is None:
                raise NotFoundError(f"Ticket {ticket_id} not found.")
            self._apply(ticket, target)
            s.flush()
            view = TicketView.model_validate(ticket)
        self._events.publish(DomainEvent(f"queue.{target.value}", {"ticket": view.model_dump(mode="json")}))
        return view

    def _apply(self, ticket: QueueTicket, target: TicketStatus) -> None:
        if target not in _TRANSITIONS[ticket.status]:
            raise InvalidTransitionError(f"Ticket cannot go from {ticket.status.value} to {target.value}.")
        now = self._clock.now().astimezone(timezone.utc)
        ticket.status = target
        if target is T.CALLED:
            ticket.called_at = now
        elif target is T.SERVING:
            ticket.served_at = now
        elif target is T.DONE:
            ticket.finished_at = now

    def _announce(self, view: TicketView) -> Announcement:
        ar, en = announcement_text(view.number, view.counter)
        ann = Announcement(ticket=view, text_ar=ar, text_en=en)
        self._events.publish(DomainEvent("queue.called", ann.model_dump(mode="json")))
        return ann
