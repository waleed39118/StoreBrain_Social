from __future__ import annotations

import io
import json
import time
import wave
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from atheer.admin import run as admin
from atheer.api import create_app
from atheer.core.config import Settings
from atheer.runtime import Atheer
from atheer.voice.engine import VoiceEngine
from atheer.voice.engines import Transcript

KEY = {"X-API-Key": "test-staff-key"}


class RecordingTTS:
    def __init__(self) -> None:
        self.spoken: list[tuple[str, str]] = []

    async def speak(self, text: str, language: str) -> None:
        self.spoken.append((text, language))


class FakeSTT:
    def __init__(self, text: str, confidence: float = 0.9) -> None:
        self.result = Transcript(text=text, language="ar", confidence=confidence)

    async def transcribe(self, pcm16: bytes) -> Transcript:
        return self.result


def wait_for(predicate, timeout: float = 2.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def next_monday(settings: Settings) -> str:
    today = datetime.now(settings.tz).date()
    return str(today + timedelta(days=(7 - today.weekday()) or 7))


@pytest.fixture
def make_client(tmp_path):
    clients = []
    counter = iter(range(100))

    def _make(*, staff_key: str | None = "test-staff-key", stt=None, **overrides):
        formulary = tmp_path / "formulary.json"
        formulary.write_text(json.dumps([
            {"drug_name": "TestDrug", "min_mg_per_kg": "10", "max_mg_per_kg": "15", "max_single_dose_mg": "1000"}
        ]))
        settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{tmp_path / f'api{next(counter)}.db'}",
            clinic_timezone="Asia/Riyadh",
            staff_api_key=staff_key,
            formulary_path=formulary,
            **overrides,
        )
        admin(["seed-demo"], settings)
        tts = RecordingTTS()
        container = Atheer.build(settings, voice=VoiceEngine(tts, stt))
        client = TestClient(create_app(atheer=container, listen=False))
        client.__enter__()
        clients.append(client)
        return client, tts, settings

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


def test_health_and_staff_auth(make_client):
    client, _, _ = make_client()
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["formulary_drugs"] == 1
    assert client.get("/alerts").status_code == 401
    assert client.get("/alerts", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/alerts", headers=KEY).status_code == 200


def test_staff_api_disabled_without_key(make_client):
    client, _, _ = make_client(staff_key=None)
    assert client.get("/alerts", headers=KEY).status_code == 503


def test_booking_conflict_checkin_and_greeting(make_client):
    client, tts, settings = make_client()
    day = next_monday(settings)
    start = f"{day}T09:00:00+03:00"

    r = client.post("/appointments", json={"patient_id": 2, "doctor_id": 1, "starts_at": start}, headers=KEY)
    assert r.status_code == 201, r.text
    appt_id = r.json()["appointment"]["id"]
    assert r.json()["alerts"][0]["kind"] == "vip_booking"

    clash = client.post("/appointments", json={"patient_id": 1, "doctor_id": 1, "starts_at": start}, headers=KEY)
    assert clash.status_code == 409 and clash.json()["conflicting_ids"] == [appt_id]

    slots = client.get(f"/doctors/1/slots?day={day}").json()
    assert all(not s["starts_at"].startswith(f"{day}T06:00") for s in slots)

    assert client.post("/checkin", json={"appointment_id": appt_id, "mrn": "WRONG"}).status_code == 404
    ok = client.post("/checkin", json={"appointment_id": appt_id, "mrn": "DEMO-2"})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["ticket"]["number"] == 1 and "Lina" in body["greeting"] and body["alerts"] == []
    assert wait_for(lambda: any("Lina" in text for text, _ in tts.spoken))
    # Checking in twice is a state error, not a second ticket.
    assert client.post("/checkin", json={"appointment_id": appt_id, "mrn": "DEMO-2"}).status_code == 409
    # The VIP arrival reaches the staff feed even though the kiosk response hides it.
    kinds = [a["kind"] for a in client.get("/alerts", headers=KEY).json()]
    assert kinds[:2] == ["vip_arrival", "vip_booking"]


def test_checkin_guessing_is_rate_limited(make_client):
    client, _, _ = make_client()
    codes = [client.post("/checkin", json={"appointment_id": 99, "mrn": f"G{i}"}).status_code for i in range(7)]
    assert codes == [404] * 5 + [429] * 2


def test_queue_call_next_is_spoken_in_both_languages(make_client):
    client, tts, _ = make_client()
    ticket = client.post("/queue/tickets").json()
    assert client.get(f"/queue/tickets/{ticket['id']}/wait").json()["expected_minutes"] >= 0
    ann = client.post("/queue/call-next", json={"counter": "Room 2"}, headers=KEY).json()
    assert ann["text_en"] == "Number 1, please proceed to Room 2."
    assert wait_for(lambda: {lang for _, lang in tts.spoken} >= {"ar", "en"})
    assert client.post(f"/queue/tickets/{ticket['id']}/serve", headers=KEY).json()["status"] == "serving"
    assert client.post(f"/queue/tickets/{ticket['id']}/explode", headers=KEY).status_code == 422


def test_chat_staff_gating_and_websocket(make_client):
    client, _, _ = make_client()
    assert "staff" in client.post("/chat", json={"text": "call next room 1"}).json()["text"]
    client.post("/queue/tickets")
    assert "Room 1" in client.post("/chat", json={"text": "call next room 1"}, headers=KEY).json()["text"]
    assert client.post("/chat", json={"text": ""}).status_code == 422

    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"text": "مرحبا"})
        assert ws.receive_json()["language"] == "ar"
        ws.send_json({"text": "  "})
        assert "error" in ws.receive_json()


def test_calculations_endpoints(make_client):
    client, _, _ = make_client()
    r = client.post("/calc/dose", json={"drug_name": "testdrug", "prescribed_mg": 250, "weight_kg": 20}, headers=KEY)
    assert r.status_code == 200 and r.json()["status"] == "within_range" and r.json()["requires_clinician_review"]
    assert client.post("/calc/dose", json={"drug_name": "Nope", "prescribed_mg": 1, "weight_kg": 20},
                       headers=KEY).status_code == 404
    cost = client.post("/calc/cost", json={"charges": [300, 200], "terms": {
        "copay": 20, "deductible_remaining": 100, "coinsurance_rate": "0.2"}}, headers=KEY).json()
    assert cost["patient_pays"] == "196.00"
    assert client.post("/calc/bsa", json={"height_cm": 180, "weight_kg": 80}, headers=KEY).json()["bsa_m2"] == "2.00"
    assert client.post("/calc/bsa", json={"height_cm": 5, "weight_kg": 80}, headers=KEY).status_code == 422
    stock = client.post("/calc/stock", json={"on_hand": 40, "daily_usage": [10, 12, 8], "lead_time_days": 5},
                        headers=KEY).json()
    assert stock["should_reorder"] is True


def _wav(rate: int = 16_000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * 1600)
    return buf.getvalue()


def test_voice_transcribe(make_client):
    client, _, _ = make_client()
    assert client.post("/voice/transcribe", content=_wav()).status_code == 503

    client, _, _ = make_client(stt=FakeSTT("أريد تذكرة"))
    r = client.post("/voice/transcribe", content=_wav()).json()
    assert r["transcript"]["text"] == "أريد تذكرة" and "رقمك" in r["reply"]["text"]
    assert client.post("/voice/transcribe", content=_wav(8000)).status_code == 415
    assert client.post("/voice/transcribe", content=b"not audio").status_code == 415


def test_oversized_audio_is_rejected(make_client):
    from atheer.api.routes import MAX_AUDIO_BYTES

    client, _, _ = make_client(stt=FakeSTT("hello"))
    assert client.post("/voice/transcribe", content=b"\0" * (MAX_AUDIO_BYTES + 1)).status_code == 413


def test_rule_violations_map_to_422(make_client):
    client, _, settings = make_client()
    past = "2020-01-06T09:00:00+03:00"
    r = client.post("/appointments", json={"patient_id": 1, "doctor_id": 1, "starts_at": past}, headers=KEY)
    assert r.status_code == 422 and "past" in r.json()["detail"]


def test_low_confidence_audio_is_ignored(make_client):
    client, _, _ = make_client(stt=FakeSTT("call next", confidence=0.1))
    assert client.post("/voice/transcribe", content=_wav()).json() == {"transcript": None, "reply": None}


def test_greet_by_name_can_be_disabled(make_client):
    client, _, settings = make_client(greet_by_name=False)
    r = client.post("/appointments", json={"patient_id": 1, "doctor_id": 1,
                                           "starts_at": f"{next_monday(settings)}T10:00:00+03:00"}, headers=KEY)
    body = client.post("/checkin", json={"appointment_id": r.json()["appointment"]["id"], "mrn": "DEMO-1"}).json()
    assert "Ahmed" not in body["greeting"] and "رقمك 1" in body["greeting"]
