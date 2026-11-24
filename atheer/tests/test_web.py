"""Web screens and the endpoints they use."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from atheer.admin import run as admin
from atheer.api import create_app
from atheer.core.config import Settings
from atheer.licensing.license import LicenseGuard
from atheer.runtime import Atheer
from atheer.voice.engine import VoiceEngine
from atheer.voice.engines import LogTTS

KEY = {"X-API-Key": "k"}


@pytest.fixture
def client(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'w.db'}",
                        clinic_timezone="Asia/Riyadh", staff_api_key="k")
    admin(["seed-demo"], settings, license_guard=LicenseGuard(tmp_path / "none.json", None))
    container = Atheer.build(settings, voice=VoiceEngine(LogTTS()))
    with TestClient(create_app(atheer=container, listen=False)) as c:
        c.settings = settings
        yield c


@pytest.mark.parametrize(("path", "marker"), [
    ("/", "لوحة الاستقبال"), ("/display", "شاشة الانتظار"), ("/reception", "لوحة الاستقبال"), ("/kiosk", "تسجيل الحضور"),
])
def test_pages_are_served(client, path, marker):
    r = client.get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert marker in r.text
    assert "https://" not in r.text.split("<body>")[0]  # no external resources: works without internet


def test_assets_are_allow_listed(client):
    assert client.get("/ui/atheer.js").status_code == 200
    assert client.get("/ui/atheer.css").headers["content-type"].startswith("text/css")
    assert client.get("/ui/secret.env").status_code == 404
    assert client.get("/ui/..%2Fapi%2Fapp.py").status_code == 404


def test_board_shows_calls_without_patient_data(client):
    client.post("/queue/tickets")
    client.post("/queue/tickets")
    client.post("/queue/call-next", json={"counter": "Room 3"}, headers=KEY)
    board = client.get("/queue/board").json()
    assert board["waiting"] == 1
    assert board["calls"][0]["number"] == 1 and board["calls"][0]["counter"] == "Room 3"
    assert set(board["calls"][0]) == {"number", "counter", "status", "called_at"}


def test_reception_flow_patient_booking_checkin(client):
    assert [d["full_name"] for d in client.get("/doctors").json()] == ["Sara Ali"]

    created = client.post("/patients", json={"mrn": "P-77", "first_name": "Omar", "last_name": "Zaid"}, headers=KEY)
    assert created.status_code == 201
    assert client.post("/patients", json={"mrn": "P-77", "first_name": "X", "last_name": "Y"}, headers=KEY).status_code == 409
    assert client.get("/patients/by-mrn/P-77", headers=KEY).json()["first_name"] == "Omar"
    assert client.get("/patients/by-mrn/NOPE", headers=KEY).status_code == 404
    assert client.get("/patients/by-mrn/P-77").status_code == 401  # staff only

    day = (datetime.now(client.settings.tz) + timedelta(days=1)).date()
    slot = client.get(f"/doctors/1/slots?day={day}").json()[0]
    booked = client.post("/appointments", json={"patient_id": created.json()["id"], "doctor_id": 1,
                                                "starts_at": slot["starts_at"]}, headers=KEY).json()
    rows = client.get(f"/appointments?day={day}", headers=KEY).json()
    assert [(r["id"], r["patient_name"], r["doctor_name"]) for r in rows] == [(booked["appointment"]["id"], "Omar Z.", "Sara Ali")]

    checked = client.post(f"/appointments/{booked['appointment']['id']}/checkin", headers=KEY).json()
    assert checked["ticket"]["number"] == 1 and "Omar" in checked["greeting"]
    client.post("/queue/call-next", json={"counter": "Room 1"}, headers=KEY)
    assert [t["number"] for t in client.get("/queue/active", headers=KEY).json()] == [1]


def test_seed_demo_with_appointments(tmp_path, capsys):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 's.db'}", clinic_timezone="Asia/Riyadh")
    assert admin(["seed-demo", "--with-appointments"], settings,
                 license_guard=LicenseGuard(tmp_path / "none.json", None)) == 0
    assert capsys.readouterr().out.count("Demo appointment #") == 2
