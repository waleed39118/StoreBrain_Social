from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from atheer.appointments.service import AppointmentService
from atheer.core.clock import FixedClock
from atheer.core.config import Settings
from atheer.core.events import EventBus
from atheer.db import Doctor, DoctorShift, Patient, create_engine_from_settings, init_db, make_session_factory
from atheer.db.session import session_scope
from atheer.queue.service import QueueService

TZ = ZoneInfo("Asia/Riyadh")
# Monday 2026-11-16 08:00 local
NOW = datetime(2026, 11, 16, 8, 0, tzinfo=TZ)


def local(h: int, m: int = 0, day: int = 16) -> datetime:
    return datetime(2026, 11, day, h, m, tzinfo=TZ)


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite://", clinic_timezone="Asia/Riyadh", _env_file=None)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def sf(settings):
    engine = create_engine_from_settings(settings)
    init_db(engine)
    factory = make_session_factory(engine)
    with session_scope(factory) as s:
        dr = Doctor(full_name="Sara Ali", specialty="Family Medicine", slot_minutes=20)
        dr.shifts.append(DoctorShift(weekday=0, start_time=time(9), end_time=time(12)))
        s.add_all(
            [
                dr,
                Doctor(full_name="Omar Idle", specialty="ENT", is_active=False),
                Patient(mrn="MRN1", first_name="Ahmed", last_name="Hassan"),
                Patient(mrn="MRN2", first_name="Lina", last_name="Saad", is_vip=True),
            ]
        )
    yield factory
    engine.dispose()


@pytest.fixture
def events() -> EventBus:
    return EventBus()


@pytest.fixture
def appts(sf, settings, clock, events) -> AppointmentService:
    return AppointmentService(sf, settings, clock=clock, events=events)


@pytest.fixture
def queue(sf, settings, clock, events) -> QueueService:
    return QueueService(sf, settings, clock=clock, events=events)
