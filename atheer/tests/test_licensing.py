from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from atheer.admin import run as admin
from atheer.api import create_app
from atheer.core.clock import FixedClock
from atheer.core.config import Settings
from atheer.licensing.license import (
    License,
    LicenseError,
    LicenseGuard,
    LicenseStatus,
    evaluate,
    generate_vendor_keypair,
    issue_license,
)
from atheer.runtime import Atheer
from atheer.voice.engine import VoiceEngine
from atheer.voice.engines import LogTTS

NOW = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)
PEM, PUB = generate_vendor_keypair()


def make_license(days: int, *, max_doctors: int | None = None, grace: int = 14, key: bytes = PEM) -> bytes:
    lic = License(license_id="ATH-TEST", customer="عيادة النور", plan="clinic", max_doctors=max_doctors,
                  issued_at=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=days), grace_days=grace)
    return issue_license(key, lic)


@pytest.mark.parametrize(
    ("days", "status", "warns", "allowed"),
    [
        (200, LicenseStatus.VALID, False, True),
        (5, LicenseStatus.VALID, True, True),  # close to expiry: warn, keep working
        (-3, LicenseStatus.GRACE, True, True),  # expired 3 days ago: grace period
        (-20, LicenseStatus.EXPIRED, True, False),  # past the 14-day grace
    ],
)
def test_license_lifecycle(days, status, warns, allowed):
    state = evaluate(make_license(days), PUB, NOW)
    assert state.status is status
    assert state.needs_attention is warns
    assert state.allows_operation is allowed
    if warns:
        assert state.message_ar and state.message_en


def test_development_missing_invalid_and_wrong_key():
    assert evaluate(None, None, NOW).status is LicenseStatus.DEVELOPMENT  # no vendor key built in
    assert evaluate(None, PUB, NOW).status is LicenseStatus.MISSING
    assert evaluate(b"not json", PUB, NOW).status is LicenseStatus.INVALID

    tampered = json.loads(make_license(30))
    tampered["license"]["expires_at"] = "2099-01-01T00:00:00Z"  # customer edits the expiry
    assert evaluate(json.dumps(tampered).encode(), PUB, NOW).status is LicenseStatus.INVALID

    other_pem, _ = generate_vendor_keypair()  # signed by someone else's key
    assert evaluate(make_license(30, key=other_pem), PUB, NOW).status is LicenseStatus.INVALID


def test_guard_picks_up_renewal_without_restart(tmp_path):
    path = tmp_path / "license.json"
    path.write_bytes(make_license(-30))
    clock = FixedClock(NOW)
    guard = LicenseGuard(path, PUB, clock=clock)
    with pytest.raises(LicenseError):
        guard.require()

    path.write_bytes(make_license(365))
    os.utime(path, (NOW.timestamp() + 5, NOW.timestamp() + 5))  # new file → new mtime
    assert guard.require().status is LicenseStatus.VALID


@pytest.fixture
def client_with_license(tmp_path):
    def _make(days: int):
        path = tmp_path / f"lic{days}.json"
        path.write_bytes(make_license(days))
        settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / f'db{days}.db'}",
                            clinic_timezone="Asia/Riyadh", staff_api_key="k", license_path=path)
        admin(["seed-demo"], settings, license_guard=LicenseGuard(path, None))
        guard = LicenseGuard(path, PUB, clock=FixedClock(NOW))
        container = Atheer.build(settings, voice=VoiceEngine(LogTTS()), license_guard=guard)
        client = TestClient(create_app(atheer=container, listen=False))
        client.__enter__()
        return client
    clients = []
    yield lambda days: clients.append(_make(days)) or clients[-1]
    for c in clients:
        c.__exit__(None, None, None)


def test_expired_license_stops_daily_operations_with_clear_message(client_with_license):
    client = client_with_license(-30)
    r = client.post("/queue/tickets")
    assert r.status_code == 402 and "جدّد" in r.json()["message_ar"]
    assert client.post("/queue/call-next", json={"counter": "Room 1"}, headers={"X-API-Key": "k"}).status_code == 402
    chat = client.post("/chat", json={"text": "أريد تذكرة"}).json()
    assert "جدّد" in chat["text"] and chat["speak"] is False
    health = client.get("/health").json()  # health stays available for diagnosis
    assert health["license"]["status"] == "expired"


def test_grace_period_keeps_clinic_running_with_warning(client_with_license):
    client = client_with_license(-3)
    assert client.post("/queue/tickets").status_code == 201
    lic = client.get("/health").json()["license"]
    assert lic["status"] == "grace" and lic["message_ar"]


def test_admin_license_commands_and_doctor_limit(tmp_path, capsys):
    key = tmp_path / "vendor.pem"
    assert admin(["license-keygen", "--out", str(key)]) == 0
    assert "VENDOR_PUBLIC_KEY" in capsys.readouterr().out
    assert admin(["license-keygen", "--out", str(key)]) == 1  # never overwrite the vendor key

    lic_path = tmp_path / "license.json"
    assert admin(["license-issue", "--key", str(key), "--customer", "Al Noor Clinic", "--plan", "clinic",
                  "--days", "365", "--max-doctors", "2", "--out", str(lic_path)]) == 0
    raw_pub = serialization.load_pem_private_key(key.read_bytes(), None).public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    pub = base64.b64encode(raw_pub).decode()

    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'a.db'}", license_path=lic_path)
    guard = LicenseGuard(lic_path, pub)
    assert admin(["license-status"], settings, license_guard=guard) == 0
    assert "Al Noor Clinic" in capsys.readouterr().out

    assert admin(["add-doctor", "--name", "A", "--specialty", "GP"], settings, license_guard=guard) == 0
    assert admin(["add-doctor", "--name", "B", "--specialty", "GP"], settings, license_guard=guard) == 0
    assert admin(["add-doctor", "--name", "C", "--specialty", "GP"], settings, license_guard=guard) == 1
    assert "allows 2 active doctors" in capsys.readouterr().err
