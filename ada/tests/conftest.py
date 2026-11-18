import os
import re
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["ADA_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ADA_TTS_OUTPUT_DIR"] = f"{_tmp}/tts"
os.environ["ADA_UPDATER_HMAC_SECRET"] = "s3cret"
os.environ["ADA_AUTH_SECRET"] = "t" * 48
os.environ["ADA_OWNER_PHONE"] = "0551234567"          # -> +966551234567
os.environ["ADA_SMS_PROVIDER"] = "outbox"
os.environ["ADA_SMS_GATEWAY_TOKEN"] = "g" * 40
os.environ["ADA_OTP_RESEND_COOLDOWN_SEC"] = "10"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

OWNER = "+966551234567"
GATEWAY = {"X-Gateway-Token": "g" * 40}


def reset_db() -> None:
    """Empty database so app startup must build the schema via Alembic migrations."""
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


def gateway_pull(c: TestClient) -> list[dict]:
    """Act as the Android gateway: claim queued SMS and ack them as sent."""
    msgs = c.post("/api/v1/sms-gateway/claim", headers=GATEWAY).json()
    for m in msgs:
        assert c.post(f"/api/v1/sms-gateway/{m['id']}/ack", headers=GATEWAY, json={"ok": True}).status_code == 204
    return msgs


def owner_login(c: TestClient, device: str = "pos-1") -> str:
    assert c.post("/api/v1/auth/otp/request", json={"phone": "0551234567"}).status_code == 202
    code = re.search(r"\b(\d{6})\b", gateway_pull(c)[-1]["body"]).group(1)
    r = c.post("/api/v1/auth/otp/verify", json={"phone": OWNER, "code": code, "device_name": device})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture()
def anon():
    reset_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client(anon):
    anon.headers["Authorization"] = f"Bearer {owner_login(anon)}"
    return anon


@pytest.fixture()
def seeded(client):
    for p in [
        {"sku": "MILK-1L", "name_en": "Milk", "name_ar": "حليب", "category": "dairy",
         "price": "1.50", "cost": "1.00", "stock_qty": 12, "reorder_level": 10},
        {"sku": "EGG-12", "name_en": "Eggs", "name_ar": "بيض", "category": "dairy",
         "price": "3.00", "stock_qty": 30, "reorder_level": 5},
        {"sku": "SOAP", "name_en": "Soap", "category": "care", "price": "2.00",
         "stock_qty": 50, "reorder_level": 5, "condition": "damaged"},
    ]:
        assert client.post("/api/v1/products", json=p).status_code == 201
    return client
