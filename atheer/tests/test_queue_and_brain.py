from __future__ import annotations

from datetime import timedelta

import pytest

from atheer.appointments.exceptions import InvalidTransitionError
from atheer.assistant.brain import Brain
from tests.conftest import local


def test_ticket_numbers_reset_daily(queue, clock):
    assert [queue.issue().number for _ in range(3)] == [1, 2, 3]
    clock.set(local(8, day=17))
    assert queue.issue().number == 1


def test_call_next_announces_without_names(queue, events):
    heard = []
    events.subscribe("queue.called", heard.append)
    t1, t2 = queue.issue(patient_id=1), queue.issue()
    ann = queue.call_next("Room 3")
    assert ann.ticket.id == t1.id
    assert ann.text_en == "Number 1, please proceed to Room 3."
    assert ann.text_ar == "الرقم 1، تفضل إلى الغرفة 3 من فضلك."
    assert "Ahmed" not in ann.text_en and len(heard) == 1
    assert [t.id for t in queue.waiting()] == [t2.id]


def test_queue_transitions(queue):
    t = queue.issue()
    with pytest.raises(InvalidTransitionError):
        queue.finish(t.id)
    queue.call_next("Room 1")
    queue.recall(t.id)
    queue.start_serving(t.id)
    assert queue.finish(t.id).status.value == "done"
    assert queue.call_next("Room 1") is None


def test_wait_estimate_uses_completed_durations(queue, clock):
    for _ in range(5):  # five 10-minute consultations
        t = queue.issue()
        queue.call_next("R1")
        queue.start_serving(t.id)
        clock.set(clock.now() + timedelta(minutes=10))
        queue.finish(t.id)
    queue.issue()
    queue.issue()
    last = queue.issue()
    est = queue.estimate_wait_for(last.id)
    assert est.sample_size == 5 and est.expected_minutes == 30  # current 10 + 2 ahead × 10


def test_brain_bilingual_and_staff_gating(settings, appts, queue, clock):
    brain = Brain(settings, appts, queue, clock=clock)
    assert "Atheer" in brain.handle("Hello").text
    r = brain.handle("أريد تذكرة من فضلك")
    assert r.language == "ar" and "رقمك هو 1" in r.text

    refused = brain.handle("نادِ التالي غرفة ٣")
    assert "لطاقم" in refused.text and len(queue.waiting()) == 1
    staff = brain.handle("نادِ التالي غرفة ٣", staff=True)
    assert "الغرفة 3" in staff.text and staff.speak is False

    assert "09:00" in brain.handle("available slots doctor 1").text
    assert "Which doctor" in brain.handle("any slots?").text
    assert "Sorry" in brain.handle("what is the meaning of life").text
