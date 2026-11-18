from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from atheer.appointments.exceptions import (
    InactiveDoctorError,
    InvalidBookingTimeError,
    InvalidTransitionError,
    OutsideAvailabilityError,
    SchedulingConflictError,
    StaleVersionError,
)
from atheer.appointments.schemas import AlertKind, BookingRequest, RescheduleRequest
from atheer.db import Appointment, AppointmentStatus
from atheer.db.session import session_scope
from tests.conftest import local


def book(appts, h, m=0, patient=1, doctor=1, day=16):
    return appts.book(BookingRequest(patient_id=patient, doctor_id=doctor, starts_at=local(h, m, day)))


def test_book_uses_doctor_slot_length_and_stores_utc(appts):
    res = book(appts, 9)
    assert res.appointment.ends_at - res.appointment.starts_at == timedelta(minutes=20)
    assert res.appointment.starts_at == datetime(2026, 11, 16, 6, 0, tzinfo=timezone.utc)
    assert res.alerts == []


def test_vip_booking_raises_alert_and_publishes_event(appts, events):
    seen = []
    events.subscribe("appointment.booked", seen.append)
    res = book(appts, 9, patient=2)
    assert [a.kind for a in res.alerts] == [AlertKind.VIP_BOOKING]
    assert "Lina S." in res.alerts[0].message and "Saad" not in res.alerts[0].message
    assert len(seen) == 1


@pytest.mark.parametrize(
    ("start", "error"),
    [
        (local(7), InvalidBookingTimeError),  # in the past
        (local(8, 30), OutsideAvailabilityError),  # before shift
        (local(11, 50), OutsideAvailabilityError),  # runs past shift end
        (local(10, day=17), OutsideAvailabilityError),  # Tuesday: no shift
    ],
)
def test_booking_rejects_invalid_times(appts, start, error):
    with pytest.raises(error):
        appts.book(BookingRequest(patient_id=1, doctor_id=1, starts_at=start))


def test_inactive_doctor_rejected(appts):
    with pytest.raises(InactiveDoctorError):
        book(appts, 9, doctor=2)


def test_doctor_and_patient_conflicts(appts):
    first = book(appts, 9, patient=1)
    with pytest.raises(SchedulingConflictError) as exc:
        book(appts, 9, 10, patient=2)  # same doctor, overlapping
    assert exc.value.conflicting_ids == [first.appointment.id]
    book(appts, 9, 20, patient=2)  # back-to-back is fine


def test_cancelled_slot_can_be_rebooked(appts):
    first = book(appts, 9)
    appts.transition(first.appointment.id, AppointmentStatus.CANCELLED)
    book(appts, 9, patient=2)


def test_reschedule_checks_conflicts_and_version(appts):
    a = book(appts, 9).appointment
    book(appts, 10, patient=2)
    with pytest.raises(SchedulingConflictError):
        appts.reschedule(RescheduleRequest(appointment_id=a.id, new_starts_at=local(10, 10)))
    with pytest.raises(StaleVersionError):
        appts.reschedule(RescheduleRequest(appointment_id=a.id, new_starts_at=local(11), expected_version=99))
    moved = appts.reschedule(RescheduleRequest(appointment_id=a.id, new_starts_at=local(11), expected_version=a.version_id))
    assert moved.starts_at == local(11).astimezone(timezone.utc)
    assert moved.version_id == a.version_id + 1


def test_state_machine(appts):
    a = book(appts, 9, patient=2).appointment
    res = appts.transition(a.id, AppointmentStatus.CHECKED_IN)
    assert [x.kind for x in res.alerts] == [AlertKind.VIP_ARRIVAL]
    with pytest.raises(InvalidTransitionError):
        appts.transition(a.id, AppointmentStatus.COMPLETED)
    appts.transition(a.id, AppointmentStatus.IN_PROGRESS)
    appts.transition(a.id, AppointmentStatus.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        appts.transition(a.id, AppointmentStatus.CANCELLED)


def test_free_slots_excludes_booked_and_past(appts, clock):
    book(appts, 9, 20)
    slots = appts.free_slots(1, date(2026, 11, 16))
    starts = [s.starts_at.astimezone(local(9).tzinfo).strftime("%H:%M") for s in slots]
    assert "09:00" in starts and "09:20" not in starts and len(starts) == 8
    clock.set(local(10, 5))
    assert len(appts.free_slots(1, date(2026, 11, 16))) == 5


def test_reminders_and_running_late(appts, clock):
    a = book(appts, 9).appointment
    b = book(appts, 9, 20, patient=2).appointment
    assert {r.id for r in appts.due_reminders()} == {a.id, b.id}
    appts.mark_reminders_sent([a.id])
    assert [r.id for r in appts.due_reminders()] == [b.id]

    clock.set(local(9, 15))  # a is 15 min overdue (> 10 min grace); b not yet started
    appts.transition(a.id, AppointmentStatus.CHECKED_IN)
    alerts = appts.running_late_alerts()
    assert [x.appointment_ids for x in alerts] == [[a.id]]
    assert "is waiting" in alerts[0].message


def test_conflict_scan_detects_imported_overlaps(appts, sf):
    a = book(appts, 9).appointment
    with session_scope(sf) as s:  # simulate a bad import bypassing the service
        s.add(Appointment(patient_id=2, doctor_id=1, starts_at=local(9, 10), ends_at=local(9, 30)))
    alerts = appts.conflict_alerts(date(2026, 11, 16))
    assert len(alerts) == 1 and a.id in alerts[0].appointment_ids


def test_naive_datetime_rejected_at_schema():
    with pytest.raises(ValueError):
        BookingRequest(patient_id=1, doctor_id=1, starts_at=datetime(2026, 11, 16, 9))
