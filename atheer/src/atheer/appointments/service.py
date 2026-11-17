"""Appointment management: booking, rescheduling, lifecycle, and proactive checks.

Every public method is its own unit of work. Domain events are published only
after a successful commit.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, aliased, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from atheer.appointments.exceptions import (
    InactiveDoctorError,
    InvalidBookingTimeError,
    InvalidTransitionError,
    NotFoundError,
    OutsideAvailabilityError,
    SchedulingConflictError,
    StaleVersionError,
)
from atheer.appointments.schemas import (
    AlertKind,
    AlertSeverity,
    AppointmentView,
    BookingRequest,
    BookingResult,
    RescheduleRequest,
    Slot,
    StaffAlert,
)
from atheer.core.clock import Clock, SystemClock
from atheer.core.config import Settings
from atheer.core.events import DomainEvent, EventBus
from atheer.db.models import ACTIVE_STATUSES, Appointment, AppointmentStatus, Doctor, Patient
from atheer.db.session import session_scope

logger = logging.getLogger(__name__)

S = AppointmentStatus
ALLOWED_TRANSITIONS: dict[AppointmentStatus, frozenset[AppointmentStatus]] = {
    S.SCHEDULED: frozenset({S.CHECKED_IN, S.CANCELLED, S.NO_SHOW}),
    S.CHECKED_IN: frozenset({S.IN_PROGRESS, S.CANCELLED, S.NO_SHOW}),
    S.IN_PROGRESS: frozenset({S.COMPLETED}),
    S.COMPLETED: frozenset(),
    S.CANCELLED: frozenset(),
    S.NO_SHOW: frozenset(),
}


class AppointmentService:
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

    # ------------------------------------------------------------------ commands

    def book(self, request: BookingRequest) -> BookingResult:
        starts_at = request.starts_at.astimezone(timezone.utc)
        if starts_at < self._clock.now():
            raise InvalidBookingTimeError("Cannot book an appointment in the past.")

        with session_scope(self._sf) as session:
            doctor = self._lock_doctor(session, request.doctor_id)
            patient = self._lock_patient(session, request.patient_id)
            duration = request.duration_minutes or doctor.slot_minutes or self._settings.default_slot_minutes
            ends_at = starts_at + timedelta(minutes=duration)

            self._ensure_within_shift(doctor, starts_at, ends_at)
            self._ensure_no_conflict(session, doctor.id, patient.id, starts_at, ends_at)

            appointment = Appointment(
                patient_id=patient.id,
                doctor_id=doctor.id,
                starts_at=starts_at,
                ends_at=ends_at,
                reason=request.reason,
                status=AppointmentStatus.SCHEDULED,
            )
            session.add(appointment)
            session.flush()

            view = AppointmentView.model_validate(appointment)
            alerts: list[StaffAlert] = []
            if patient.is_vip:
                alerts.append(
                    StaffAlert(
                        kind=AlertKind.VIP_BOOKING,
                        severity=AlertSeverity.INFO,
                        message=(
                            f"VIP patient {patient.announce_name} booked with Dr. {doctor.full_name} "
                            f"at {self._local_hhmm(starts_at)}."
                        ),
                        appointment_ids=[view.id],
                    )
                )

        self._publish("appointment.booked", view, alerts)
        return BookingResult(appointment=view, alerts=alerts)

    def reschedule(self, request: RescheduleRequest) -> AppointmentView:
        new_start = request.new_starts_at.astimezone(timezone.utc)
        if new_start < self._clock.now():
            raise InvalidBookingTimeError("Cannot move an appointment into the past.")

        try:
            with session_scope(self._sf) as session:
                appointment = self._get_appointment(session, request.appointment_id)
                if request.expected_version is not None and appointment.version_id != request.expected_version:
                    raise StaleVersionError("Appointment was changed by another user; reload and retry.")
                if appointment.status is not AppointmentStatus.SCHEDULED:
                    raise InvalidTransitionError(
                        f"Only scheduled appointments can be rescheduled (current: {appointment.status.value})."
                    )

                doctor = self._lock_doctor(session, request.new_doctor_id or appointment.doctor_id)
                self._lock_patient(session, appointment.patient_id)
                duration = appointment.ends_at - appointment.starts_at
                new_end = new_start + duration

                self._ensure_within_shift(doctor, new_start, new_end)
                self._ensure_no_conflict(
                    session, doctor.id, appointment.patient_id, new_start, new_end, exclude_id=appointment.id
                )

                appointment.doctor_id = doctor.id
                appointment.starts_at = new_start
                appointment.ends_at = new_end
                appointment.reminder_sent_at = None  # the patient must be reminded of the new time
                session.flush()
                view = AppointmentView.model_validate(appointment)
        except StaleDataError as exc:
            raise StaleVersionError("Appointment was changed by another user; reload and retry.") from exc

        self._publish("appointment.rescheduled", view)
        return view

    def transition(self, appointment_id: int, target: AppointmentStatus) -> BookingResult:
        """Move an appointment through its lifecycle (check-in, start, complete, cancel, no-show)."""
        try:
            with session_scope(self._sf) as session:
                appointment = self._get_appointment(session, appointment_id)
                current = appointment.status
                if target not in ALLOWED_TRANSITIONS[current]:
                    raise InvalidTransitionError(f"Cannot move appointment from {current.value} to {target.value}.")

                appointment.status = target
                alerts: list[StaffAlert] = []
                if target is AppointmentStatus.CHECKED_IN:
                    appointment.checked_in_at = self._clock.now()
                    if appointment.patient.is_vip:
                        alerts.append(
                            StaffAlert(
                                kind=AlertKind.VIP_ARRIVAL,
                                severity=AlertSeverity.WARNING,
                                message=(
                                    f"VIP patient {appointment.patient.announce_name} has arrived for "
                                    f"Dr. {appointment.doctor.full_name}."
                                ),
                                appointment_ids=[appointment.id],
                            )
                        )
                session.flush()
                view = AppointmentView.model_validate(appointment)
        except StaleDataError as exc:
            raise StaleVersionError("Appointment was changed by another user; reload and retry.") from exc

        self._publish(f"appointment.{target.value}", view, alerts)
        return BookingResult(appointment=view, alerts=alerts)

    def mark_reminders_sent(self, appointment_ids: Iterable[int]) -> int:
        ids = list(appointment_ids)
        if not ids:
            return 0
        now = self._clock.now()
        with session_scope(self._sf) as session:
            rows = session.scalars(select(Appointment).where(Appointment.id.in_(ids))).all()
            for row in rows:
                row.reminder_sent_at = now
            return len(rows)

    # ------------------------------------------------------------------ queries

    def free_slots(self, doctor_id: int, day: date) -> list[Slot]:
        """Bookable slots for ``day`` (clinic local date), excluding past and occupied times."""
        tz = self._settings.tz
        with session_scope(self._sf) as session:
            doctor = session.get(Doctor, doctor_id)
            if doctor is None:
                raise NotFoundError(f"Doctor {doctor_id} not found.")
            if not doctor.is_active:
                return []

            step = timedelta(minutes=doctor.slot_minutes or self._settings.default_slot_minutes)
            day_start = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
            day_end = day_start + timedelta(days=1)
            busy = session.execute(
                select(Appointment.starts_at, Appointment.ends_at).where(
                    Appointment.doctor_id == doctor_id,
                    Appointment.status.in_(ACTIVE_STATUSES),
                    Appointment.starts_at < day_end,
                    Appointment.ends_at > day_start,
                )
            ).all()

            now = self._clock.now()
            slots: list[Slot] = []
            for shift in sorted(doctor.shifts, key=lambda s: s.start_time):
                if shift.weekday != day.weekday():
                    continue
                cursor = datetime.combine(day, shift.start_time, tzinfo=tz).astimezone(timezone.utc)
                shift_end = datetime.combine(day, shift.end_time, tzinfo=tz).astimezone(timezone.utc)
                while cursor + step <= shift_end:
                    slot_end = cursor + step
                    overlaps = any(b_start < slot_end and b_end > cursor for b_start, b_end in busy)
                    if cursor >= now and not overlaps:
                        slots.append(Slot(starts_at=cursor, ends_at=slot_end))
                    cursor = slot_end
            return slots

    def due_reminders(self) -> list[AppointmentView]:
        """Scheduled appointments within the reminder window that have not been reminded yet."""
        now = self._clock.now()
        horizon = now + timedelta(hours=self._settings.reminder_lead_hours)
        with session_scope(self._sf) as session:
            rows = session.scalars(
                select(Appointment)
                .where(
                    Appointment.status == AppointmentStatus.SCHEDULED,
                    Appointment.reminder_sent_at.is_(None),
                    Appointment.starts_at > now,
                    Appointment.starts_at <= horizon,
                )
                .order_by(Appointment.starts_at)
            ).all()
            return [AppointmentView.model_validate(r) for r in rows]

    def running_late_alerts(self) -> list[StaffAlert]:
        """Today's appointments whose start time passed the grace period but consultation hasn't begun."""
        now = self._clock.now()
        threshold = now - timedelta(minutes=self._settings.late_grace_minutes)
        local_midnight = datetime.combine(now.astimezone(self._settings.tz).date(), time.min, tzinfo=self._settings.tz)
        with session_scope(self._sf) as session:
            rows = session.scalars(
                select(Appointment)
                .where(
                    Appointment.status.in_([AppointmentStatus.SCHEDULED, AppointmentStatus.CHECKED_IN]),
                    Appointment.starts_at >= local_midnight.astimezone(timezone.utc),
                    Appointment.starts_at <= threshold,
                )
                .order_by(Appointment.starts_at)
            ).all()

            alerts = []
            for appt in rows:
                overdue = int((now - appt.starts_at).total_seconds() // 60)
                waiting = "is waiting" if appt.status is AppointmentStatus.CHECKED_IN else "has not arrived"
                alerts.append(
                    StaffAlert(
                        kind=AlertKind.RUNNING_LATE,
                        # A checked-in patient left waiting is the clinic's delay: escalate.
                        severity=(
                            AlertSeverity.WARNING
                            if appt.status is AppointmentStatus.CHECKED_IN
                            else AlertSeverity.INFO
                        ),
                        message=(
                            f"Dr. {appt.doctor.full_name}'s {self._local_hhmm(appt.starts_at)} appointment is "
                            f"{overdue} min overdue; patient {appt.patient.announce_name} {waiting}."
                        ),
                        appointment_ids=[appt.id],
                    )
                )
            return alerts

    def conflict_alerts(self, day: date) -> list[StaffAlert]:
        """Detect overlapping active appointments (e.g. from imports or manual DB edits) for ``day``."""
        tz = self._settings.tz
        day_start = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
        day_end = day_start + timedelta(days=1)
        a, b = aliased(Appointment), aliased(Appointment)
        with session_scope(self._sf) as session:
            pairs = session.execute(
                select(a.id, b.id, a.doctor_id, a.patient_id, b.patient_id)
                .join(b, and_(a.id < b.id, a.starts_at < b.ends_at, b.starts_at < a.ends_at))
                .where(
                    or_(a.doctor_id == b.doctor_id, a.patient_id == b.patient_id),
                    a.status.in_(ACTIVE_STATUSES),
                    b.status.in_(ACTIVE_STATUSES),
                    a.starts_at < day_end,
                    a.ends_at > day_start,
                )
            ).all()
            return [
                StaffAlert(
                    kind=AlertKind.SCHEDULE_CONFLICT,
                    severity=AlertSeverity.CRITICAL,
                    message=(
                        f"Appointments #{a_id} and #{b_id} overlap "
                        f"({'same patient' if a_pat == b_pat else 'same doctor'})."
                    ),
                    appointment_ids=[a_id, b_id],
                )
                for a_id, b_id, _doc, a_pat, b_pat in pairs
            ]

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _lock_doctor(session: Session, doctor_id: int) -> Doctor:
        # Row lock serialises concurrent bookings for the same doctor on PostgreSQL.
        doctor = session.scalars(select(Doctor).where(Doctor.id == doctor_id).with_for_update()).one_or_none()
        if doctor is None:
            raise NotFoundError(f"Doctor {doctor_id} not found.")
        if not doctor.is_active:
            raise InactiveDoctorError(f"Dr. {doctor.full_name} is not currently accepting appointments.")
        return doctor

    @staticmethod
    def _lock_patient(session: Session, patient_id: int) -> Patient:
        patient = session.scalars(select(Patient).where(Patient.id == patient_id).with_for_update()).one_or_none()
        if patient is None:
            raise NotFoundError(f"Patient {patient_id} not found.")
        return patient

    @staticmethod
    def _get_appointment(session: Session, appointment_id: int) -> Appointment:
        appointment = session.get(Appointment, appointment_id)
        if appointment is None:
            raise NotFoundError(f"Appointment {appointment_id} not found.")
        return appointment

    def _ensure_within_shift(self, doctor: Doctor, starts_at: datetime, ends_at: datetime) -> None:
        tz = self._settings.tz
        local_start, local_end = starts_at.astimezone(tz), ends_at.astimezone(tz)
        if local_start.date() != local_end.date():
            raise OutsideAvailabilityError("Appointments cannot span midnight.")
        for shift in doctor.shifts:
            if (
                shift.weekday == local_start.weekday()
                and shift.start_time <= local_start.time()
                and local_end.time() <= shift.end_time
            ):
                return
        raise OutsideAvailabilityError(
            f"Dr. {doctor.full_name} is not available {local_start:%A %H:%M}–{local_end:%H:%M}."
        )

    @staticmethod
    def _ensure_no_conflict(
        session: Session,
        doctor_id: int,
        patient_id: int,
        starts_at: datetime,
        ends_at: datetime,
        *,
        exclude_id: int | None = None,
    ) -> None:
        query = select(Appointment.id, Appointment.doctor_id).where(
            Appointment.status.in_(ACTIVE_STATUSES),
            Appointment.starts_at < ends_at,
            Appointment.ends_at > starts_at,
            or_(Appointment.doctor_id == doctor_id, Appointment.patient_id == patient_id),
        )
        if exclude_id is not None:
            query = query.where(Appointment.id != exclude_id)
        clashes = session.execute(query).all()
        if clashes:
            who = "doctor" if any(d == doctor_id for _, d in clashes) else "patient"
            raise SchedulingConflictError(
                f"Requested time overlaps an existing appointment for the {who}.",
                conflicting_ids=[c_id for c_id, _ in clashes],
            )

    def _local_hhmm(self, moment: datetime) -> str:
        return moment.astimezone(self._settings.tz).strftime("%H:%M")

    def _publish(self, name: str, view: AppointmentView, alerts: list[StaffAlert] | None = None) -> None:
        self._events.publish(
            DomainEvent(
                name=name,
                payload={
                    "appointment": view.model_dump(mode="json"),
                    "alerts": [a.model_dump(mode="json") for a in alerts or []],
                },
            )
        )
