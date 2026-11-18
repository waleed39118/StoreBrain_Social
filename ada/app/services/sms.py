"""SMS delivery behind one interface. Default = outbox: nothing leaves the server unless the
owner's own Android gateway phone (SIM) pulls it. Other providers are opt-in by config."""
import logging
from datetime import timedelta
from typing import Protocol

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import SmsOutbox, SmsStatus, utcnow

log = logging.getLogger("ada.sms")
CLAIM_TIMEOUT = timedelta(minutes=2)   # a claimed-but-unacked SMS is re-offered after this


class SmsSender(Protocol):
    def send(self, db: Session, phone: str, body: str, ttl_sec: int) -> None: ...


class OutboxSender:
    """Queue in DB; the gateway device fetches via /api/v1/sms-gateway/*."""
    def send(self, db: Session, phone: str, body: str, ttl_sec: int) -> None:
        db.add(SmsOutbox(phone=phone, body=body, expires_at=utcnow() + timedelta(seconds=ttl_sec)))


class HttpSender:
    """Generic JSON POST to a provider the owner explicitly configured and authorised."""
    def __init__(self, settings: Settings) -> None:
        if not settings.sms_http_url.startswith("https://"):
            raise RuntimeError("ADA_SMS_HTTP_URL must be an https:// URL")
        self.url, self.token = settings.sms_http_url, settings.sms_http_token.get_secret_value()

    def send(self, db: Session, phone: str, body: str, ttl_sec: int) -> None:
        r = httpx.post(self.url, json={"to": phone, "message": body}, timeout=10,
                       headers={"Authorization": f"Bearer {self.token}"} if self.token else {})
        r.raise_for_status()


class ConsoleSender:
    """Development only."""
    def send(self, db: Session, phone: str, body: str, ttl_sec: int) -> None:
        log.warning("DEV SMS to %s: %s", phone, body)


def build_sender(settings: Settings) -> SmsSender:
    return {"outbox": OutboxSender, "console": ConsoleSender}.get(
        settings.sms_provider, lambda: HttpSender(settings))()


class SmsGatewayQueue:
    """Server side of the Android gateway protocol: claim -> send -> ack."""
    def __init__(self, db: Session) -> None:
        self.db = db

    def claim(self, limit: int = 10) -> list[SmsOutbox]:
        now = utcnow()
        # Expire stale messages and wipe their bodies (may contain OTPs).
        self.db.execute(update(SmsOutbox)
                        .where(SmsOutbox.status.in_([SmsStatus.PENDING, SmsStatus.SENDING]),
                               SmsOutbox.expires_at < now)
                        .values(status=SmsStatus.EXPIRED, body=""))
        rows = list(self.db.scalars(
            select(SmsOutbox).where(
                (SmsOutbox.status == SmsStatus.PENDING) |
                ((SmsOutbox.status == SmsStatus.SENDING) & (SmsOutbox.claimed_at < now - CLAIM_TIMEOUT)))
            .order_by(SmsOutbox.created_at).limit(limit)))
        for m in rows:
            m.status, m.claimed_at, m.attempts = SmsStatus.SENDING, now, m.attempts + 1
        self.db.commit()
        return rows

    def ack(self, msg_id: int, ok: bool, error: str | None = None) -> bool:
        m = self.db.get(SmsOutbox, msg_id)
        if m is None or m.status != SmsStatus.SENDING:
            return False
        m.status = SmsStatus.SENT if ok else SmsStatus.FAILED
        m.sent_at = utcnow() if ok else None
        m.error = (error or "")[:200] or None
        m.body = ""                      # never keep OTP text after delivery
        self.db.commit()
        return True
