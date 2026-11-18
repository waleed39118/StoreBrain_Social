"""Typed boundaries for the appointment service.

These schemas double as LLM tool argument/return types in Increment 4, so all
validation lives here rather than in prompt instructions.
"""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from atheer.db.models import AppointmentStatus


class BookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: int = Field(gt=0)
    doctor_id: int = Field(gt=0)
    starts_at: AwareDatetime
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    reason: str | None = Field(default=None, max_length=255)


class RescheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: int = Field(gt=0)
    new_starts_at: AwareDatetime
    new_doctor_id: int | None = Field(default=None, gt=0)
    expected_version: int | None = Field(
        default=None, description="Optimistic-lock token from the last read; reject if stale."
    )


class AppointmentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    doctor_id: int
    starts_at: datetime
    ends_at: datetime
    status: AppointmentStatus
    reason: str | None
    version_id: int


class Slot(BaseModel):
    starts_at: datetime
    ends_at: datetime


class AlertKind(str, enum.Enum):
    VIP_BOOKING = "vip_booking"
    VIP_ARRIVAL = "vip_arrival"
    RUNNING_LATE = "running_late"
    SCHEDULE_CONFLICT = "schedule_conflict"


class AlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class StaffAlert(BaseModel):
    """Message for staff screens/earpieces — never broadcast on public speakers."""

    kind: AlertKind
    severity: AlertSeverity
    message: str
    appointment_ids: list[int] = Field(default_factory=list)


class BookingResult(BaseModel):
    appointment: AppointmentView
    alerts: list[StaffAlert] = Field(default_factory=list)


class AppointmentContext(BaseModel):
    """Appointment plus the minimum patient/doctor facts the receptionist needs (no clinical data)."""

    appointment: AppointmentView
    patient_mrn: str
    patient_first_name: str
    patient_announce_name: str
    preferred_language: str
    is_vip: bool
    doctor_name: str
