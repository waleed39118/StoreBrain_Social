import hashlib
import hmac
import json
import re
from datetime import timedelta

from sqlalchemy import update

from app.database import SessionLocal
from app.models import OtpCode, SmsOutbox, utcnow
from tests.conftest import GATEWAY, OWNER, gateway_pull, owner_login


def _age_otps(seconds: int) -> None:
    with SessionLocal() as db:
        db.execute(update(OtpCode).values(created_at=utcnow() - timedelta(seconds=seconds)))
        db.commit()


def _request_code(c) -> str:
    _age_otps(3600)  # bypass resend cooldown / hourly cap between steps
    assert c.post("/api/v1/auth/otp/request", json={"phone": OWNER}).status_code == 202
    return re.search(r"\b(\d{6})\b", gateway_pull(c)[-1]["body"]).group(1)


def _verify(c, code):
    return c.post("/api/v1/auth/otp/verify", json={"phone": OWNER, "code": code})


# ---------- owner OTP ----------
def test_owner_otp_login_and_me(anon):
    token = owner_login(anon)
    me = anon.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["phone"] == OWNER and me["role"] == "owner"


def test_non_owner_number_gets_same_response_and_no_sms(anon):
    r = anon.post("/api/v1/auth/otp/request", json={"phone": "+201001234567"})
    assert r.status_code == 202 and "If this number" in r.json()["detail"]
    assert gateway_pull(anon) == []


def test_otp_wrong_attempts_lock_code(anon):
    code = _request_code(anon)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert _verify(anon, wrong).status_code == 401
    assert _verify(anon, code).status_code == 401       # locked after max attempts


def test_otp_single_use_newest_only_and_expiry(anon):
    old = _request_code(anon)
    new = _request_code(anon)
    if old != new:
        assert _verify(anon, old).status_code == 401    # superseded
    assert _verify(anon, new).status_code == 200
    assert _verify(anon, new).status_code == 401        # single use
    code = _request_code(anon)
    with SessionLocal() as db:
        db.execute(update(OtpCode).values(expires_at=utcnow() - timedelta(seconds=1))); db.commit()
    assert _verify(anon, code).status_code == 401


def test_otp_resend_cooldown(anon):
    _request_code(anon)
    assert anon.post("/api/v1/auth/otp/request", json={"phone": OWNER}).status_code == 429


# ---------- staff, PIN, roles ----------
def _staff(client, phone, role, pin="4821"):
    r = client.post("/api/v1/users", json={"phone": phone, "name": role, "role": role, "pin": pin})
    assert r.status_code == 201, r.text
    return r.json()


def _pin_login(c, phone, pin="4821"):
    return c.post("/api/v1/auth/pin/login", json={"phone": phone, "pin": pin, "device_name": "till"})


def test_roles_enforced_including_chat(seeded):
    _staff(seeded, "0500000001", "cashier")
    _staff(seeded, "0500000002", "manager")
    cashier = {"Authorization": f"Bearer {_pin_login(seeded, '0500000001').json()['token']}"}
    manager = {"Authorization": f"Bearer {_pin_login(seeded, '0500000002').json()['token']}"}

    assert seeded.post("/api/v1/sales", headers=cashier,
                       json={"items": [{"sku": "EGG-12", "quantity": 1}]}).status_code == 201
    assert seeded.post("/api/v1/products/EGG-12/restock", headers=cashier, json={"quantity": 5}).status_code == 403
    assert seeded.get("/api/v1/analytics/reorder", headers=cashier).status_code == 403
    assert seeded.get("/api/v1/products/import/template", headers=cashier).status_code == 403
    r = seeded.post("/api/v1/ada/chat", headers=cashier, json={"text": "أضف 5 حليب"}).json()
    assert r["reply"].startswith("عذراً") and \
        seeded.get("/api/v1/products", params={"q": "MILK-1L"}).json()[0]["stock_qty"] == 12
    assert "29" in seeded.post("/api/v1/ada/chat", headers=cashier, json={"text": "how many eggs"}).json()["reply"]

    assert seeded.get("/api/v1/analytics/reorder", headers=manager).status_code == 200
    assert seeded.get("/api/v1/users", headers=manager).status_code == 403


def test_pin_lockout_and_weak_pin(client):
    assert client.post("/api/v1/users", json={"phone": "0500000003", "name": "x", "role": "cashier",
                                              "pin": "1234"}).status_code == 422
    _staff(client, "0500000003", "cashier")
    for _ in range(5):
        assert _pin_login(client, "0500000003", "9999").status_code == 401
    assert _pin_login(client, "0500000003").status_code == 429      # locked even with right PIN
    assert _pin_login(client, "0599999999").status_code == 401      # unknown number: same error


def test_owner_cannot_pin_login_or_be_duplicated(client):
    assert _pin_login(client, OWNER).status_code == 401
    assert client.post("/api/v1/users", json={"phone": OWNER, "name": "x", "role": "manager",
                                              "pin": "4821"}).status_code == 409


def test_sessions_logout_and_deactivation(client):
    sessions = client.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 1 and sessions[0]["current"] and sessions[0]["device_name"] == "pos-1"

    staff = _staff(client, "0500000004", "cashier")
    tok = _pin_login(client, "0500000004").json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200
    client.patch(f"/api/v1/users/{staff['id']}", json={"is_active": False})
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401       # revoked immediately

    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


# ---------- in-app notifications ----------
def test_low_stock_creates_in_app_notification(seeded):
    seeded.post("/api/v1/sales", json={"items": [{"sku": "MILK-1L", "quantity": 3}]})
    seeded.post("/api/v1/sales", json={"items": [{"sku": "MILK-1L", "quantity": 1}]})  # cooldown: no dup
    notes = seeded.get("/api/v1/notifications", params={"unread_only": True}).json()
    assert len(notes) == 1 and notes[0]["key"] == "MILK-1L" and "Low stock" in notes[0]["message"]
    assert seeded.get("/api/v1/notifications/unread-count").json() == {"count": 1}
    assert seeded.post(f"/api/v1/notifications/{notes[0]['id']}/read").status_code == 204
    assert seeded.get("/api/v1/notifications/unread-count").json() == {"count": 0}


# ---------- SMS gateway ----------
def test_gateway_auth_and_body_wiped(anon):
    assert anon.post("/api/v1/sms-gateway/claim", headers={"X-Gateway-Token": "bad"}).status_code == 401
    owner_login(anon)
    with SessionLocal() as db:
        assert all(m.body == "" and m.status == "sent" for m in db.query(SmsOutbox))


def test_gateway_expiry_and_reclaim(anon):
    anon.post("/api/v1/auth/otp/request", json={"phone": OWNER})
    first = anon.post("/api/v1/sms-gateway/claim", headers=GATEWAY).json()
    assert len(first) == 1
    assert anon.post("/api/v1/sms-gateway/claim", headers=GATEWAY).json() == []       # in flight
    with SessionLocal() as db:
        db.execute(update(SmsOutbox).values(claimed_at=utcnow() - timedelta(minutes=5))); db.commit()
    assert [m["id"] for m in anon.post("/api/v1/sms-gateway/claim", headers=GATEWAY).json()] == [first[0]["id"]]
    with SessionLocal() as db:
        db.execute(update(SmsOutbox).values(expires_at=utcnow() - timedelta(seconds=1))); db.commit()
    assert anon.post("/api/v1/sms-gateway/claim", headers=GATEWAY).json() == []       # stale OTP never sent


def test_signed_patch_needs_no_user_session(anon):
    body = json.dumps({"version": "p1", "products": []}).encode()
    sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert anon.post("/api/v1/system/patches", content=body, headers={"X-Ada-Signature": sig}).json()["applied"]
    assert anon.get("/api/v1/products").status_code == 401
