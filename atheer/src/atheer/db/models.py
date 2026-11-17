"""ORM models for scheduling.

Clinical records (diagnoses, notes) are intentionally *not* modelled here; Atheer
is an administrative assistant and should integrate with the clinic's EHR for
clinical data rather than becoming a shadow medical record.
"""

from __future__ import annotations

import enum
from datetime import date, datetime, time, timezone

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from atheer.db.types import UTCDateTime


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class Doctor(TimestampMixin, Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    specialty: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    # Overrides the clinic default consultation length when set.
    slot_minutes: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    shifts: Mapped[list[DoctorShift]] = relationship(
        back_populates="doctor", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("slot_minutes IS NULL OR slot_minutes BETWEEN 5 AND 240", name="ck_doctor_slot"),
    )


class DoctorShift(Base):
    """Recurring weekly availability, expressed in the clinic's local time."""

    __tablename__ = "doctor_shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0 = Monday … 6 = Sunday
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    doctor: Mapped[Doctor] = relationship(back_populates="shifts")

    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_shift_weekday"),
        CheckConstraint("start_time < end_time", name="ck_shift_order"),
        Index("ix_shift_doctor_weekday", "doctor_id", "weekday"),
    )


class Patient(TimestampMixin, Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    mrn: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)  # medical record number
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    is_vip: Mapped[bool] = mapped_column(default=False, nullable=False)

    @property
    def announce_name(self) -> str:
        """Privacy-safe name for public announcements: first name + last initial."""
        return f"{self.first_name} {self.last_name[:1]}." if self.last_name else self.first_name


class AppointmentStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    CHECKED_IN = "checked_in"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


# Statuses that occupy a doctor's time slot.
ACTIVE_STATUSES: frozenset[AppointmentStatus] = frozenset(
    {AppointmentStatus.SCHEDULED, AppointmentStatus.CHECKED_IN, AppointmentStatus.IN_PROGRESS}
)


class Appointment(TimestampMixin, Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        default=AppointmentStatus.SCHEDULED,
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    version_id: Mapped[int] = mapped_column(nullable=False)

    patient: Mapped[Patient] = relationship(lazy="joined")
    doctor: Mapped[Doctor] = relationship(lazy="joined")

    __mapper_args__ = {"version_id_col": version_id}
    __table_args__ = (
        CheckConstraint("starts_at < ends_at", name="ck_appointment_order"),
        Index("ix_appointment_doctor_start", "doctor_id", "starts_at"),
        Index("ix_appointment_patient_start", "patient_id", "starts_at"),
        Index("ix_appointment_status_start", "status", "starts_at"),
    )


class TicketStatus(str, enum.Enum):
    WAITING = "waiting"
    CALLED = "called"
    SERVING = "serving"
    DONE = "done"
    SKIPPED = "skipped"


class QueueTicket(Base):
    """Walk-in / arrival queue. Numbers restart daily (clinic local date)."""

    __tablename__ = "queue_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_date: Mapped[date] = mapped_column(nullable=False)
    number: Mapped[int] = mapped_column(nullable=False)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id", ondelete="SET NULL"))
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("doctors.id", ondelete="SET NULL"))
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id", ondelete="SET NULL"))
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        default=TicketStatus.WAITING,
        nullable=False,
    )
    counter: Mapped[str | None] = mapped_column(String(32))  # room / desk the patient is called to
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    called_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    served_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    __table_args__ = (
        UniqueConstraint("service_date", "number", name="uq_ticket_day_number"),
        Index("ix_ticket_day_status", "service_date", "status"),
    )
