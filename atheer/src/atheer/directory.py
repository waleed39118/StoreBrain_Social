"""Doctors and patients: the minimal lookups and creation the reception screens need."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from atheer.appointments.exceptions import AppointmentError, NotFoundError
from atheer.db.models import Doctor, Patient
from atheer.db.session import session_scope


class DoctorView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    specialty: str
    is_active: bool


class PatientView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mrn: str
    first_name: str
    last_name: str
    phone: str | None
    preferred_language: str
    is_vip: bool


class PatientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mrn: str = Field(min_length=1, max_length=32)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    phone: str | None = Field(default=None, max_length=32)
    date_of_birth: date | None = None
    preferred_language: str = Field(default="ar", pattern="^(ar|en)$")
    is_vip: bool = False


class DuplicateRecordError(AppointmentError):
    pass


class DirectoryService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def doctors(self, *, active_only: bool = True) -> list[DoctorView]:
        with session_scope(self._sf) as s:
            q = select(Doctor).order_by(Doctor.full_name)
            if active_only:
                q = q.where(Doctor.is_active.is_(True))
            return [DoctorView.model_validate(d) for d in s.scalars(q)]

    def active_doctor_count(self) -> int:
        with session_scope(self._sf) as s:
            return s.scalar(select(func.count()).select_from(Doctor).where(Doctor.is_active.is_(True))) or 0

    def patient_by_mrn(self, mrn: str) -> PatientView:
        with session_scope(self._sf) as s:
            p = s.scalars(select(Patient).where(Patient.mrn == mrn.strip())).one_or_none()
            if p is None:
                raise NotFoundError("No patient with this medical record number.")
            return PatientView.model_validate(p)

    def create_patient(self, data: PatientCreate) -> PatientView:
        try:
            with session_scope(self._sf) as s:
                p = Patient(**data.model_dump())
                s.add(p)
                s.flush()
                return PatientView.model_validate(p)
        except IntegrityError as exc:
            raise DuplicateRecordError("A patient with this medical record number already exists.") from exc
