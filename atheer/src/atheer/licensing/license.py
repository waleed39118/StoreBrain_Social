"""Signed, offline-verifiable subscription licenses.

The vendor signs a small JSON payload (customer, plan, doctor limit, expiry)
with an Ed25519 private key that never leaves the vendor's machine. Each
installation verifies it with the vendor's public key, offline, so clinics
without internet keep working.

Expiry never stops a clinic mid-day: a valid license turns into a grace period
(default 14 days) with warnings on every channel, and only after that are
day-to-day operations refused. Renewal needs no restart: replace license.json
and it is picked up on the next check.

This is a deterrent that backs the subscription contract, not DRM: whoever can
edit the Python source can remove it. The contract is the primary protection.
"""

from __future__ import annotations

import base64
import enum
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import AwareDatetime, BaseModel, Field, ValidationError

from atheer.core.clock import Clock, SystemClock

PRODUCT = "atheer"
WARN_DAYS = 14  # start warning this many days before expiry


class LicenseError(Exception):
    """Raised when an operation needs an active license and there isn't one."""

    def __init__(self, message_ar: str, message_en: str) -> None:
        super().__init__(f"{message_en} / {message_ar}")
        self.message_ar = message_ar
        self.message_en = message_en


class License(BaseModel):
    product: str = PRODUCT
    license_id: str = Field(min_length=1, max_length=64)
    customer: str = Field(min_length=1, max_length=200)
    plan: str = Field(min_length=1, max_length=40)
    max_doctors: int | None = Field(default=None, ge=1)
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    grace_days: int = Field(default=14, ge=0, le=90)


class LicenseStatus(str, enum.Enum):
    DEVELOPMENT = "development"  # no vendor key built in: licensing not enforced
    VALID = "valid"
    GRACE = "grace"  # expired, still working, staff warned
    EXPIRED = "expired"
    MISSING = "missing"
    INVALID = "invalid"


ALLOWS_OPERATION = frozenset({LicenseStatus.DEVELOPMENT, LicenseStatus.VALID, LicenseStatus.GRACE})


class LicenseState(BaseModel):
    status: LicenseStatus
    license: License | None = None
    days_remaining: int | None = None  # until expiry (VALID) or until grace ends (GRACE)
    message_ar: str = ""
    message_en: str = ""

    @property
    def allows_operation(self) -> bool:
        return self.status in ALLOWS_OPERATION

    @property
    def needs_attention(self) -> bool:
        return bool(self.message_en)


# --------------------------------------------------------------------- signing (vendor side)


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def generate_vendor_keypair() -> tuple[bytes, str]:
    """Returns (private key PEM — keep secret, base64 public key — build into the product)."""
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return pem, base64.b64encode(pub).decode()


def issue_license(private_key_pem: bytes, lic: License) -> bytes:
    """Sign ``lic`` and return the license.json bytes to give the customer."""
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("License signing key must be an Ed25519 private key")
    payload = lic.model_dump(mode="json")
    signature = base64.b64encode(key.sign(_canonical(payload))).decode()
    return json.dumps({"license": payload, "signature": signature}, ensure_ascii=False, indent=2).encode()


# --------------------------------------------------------------------- verification (clinic side)


def evaluate(raw: bytes | None, public_key_b64: str | None, now: datetime) -> LicenseState:
    """Pure function: license file bytes + vendor key + time -> state."""
    if not public_key_b64:
        return LicenseState(status=LicenseStatus.DEVELOPMENT)
    if raw is None:
        return LicenseState(
            status=LicenseStatus.MISSING,
            message_ar="لا يوجد ترخيص. تواصل مع المورّد لتفعيل أثير.",
            message_en="No license installed. Contact your vendor to activate Atheer.",
        )
    try:
        doc = json.loads(raw)
        payload = doc["license"]
        signature = base64.b64decode(doc["signature"])
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64)).verify(signature, _canonical(payload))
        lic = License.model_validate(payload)
        if lic.product != PRODUCT:
            raise ValueError("license is for another product")
    except (InvalidSignature, ValidationError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return LicenseState(
            status=LicenseStatus.INVALID,
            message_ar="ملف الترخيص غير صالح أو معدَّل. تواصل مع المورّد.",
            message_en="The license file is invalid or has been modified. Contact your vendor.",
        )

    now = now.astimezone(timezone.utc)
    expires = lic.expires_at.astimezone(timezone.utc)
    grace_end = expires + timedelta(days=lic.grace_days)
    if now <= expires:
        days = (expires - now).days
        if days < WARN_DAYS:
            return LicenseState(
                status=LicenseStatus.VALID, license=lic, days_remaining=days,
                message_ar=f"ينتهي اشتراك أثير خلال {days} يومًا. جدّد الاشتراك لتجنّب التوقف.",
                message_en=f"Atheer subscription ends in {days} days. Renew to avoid interruption.",
            )
        return LicenseState(status=LicenseStatus.VALID, license=lic, days_remaining=days)
    if now <= grace_end:
        days = (grace_end - now).days
        return LicenseState(
            status=LicenseStatus.GRACE, license=lic, days_remaining=days,
            message_ar=f"انتهى اشتراك أثير. يستمر العمل {days} يومًا إضافية فقط؛ جدّد الاشتراك الآن.",
            message_en=f"Atheer subscription has ended. Service continues for {days} more days; renew now.",
        )
    return LicenseState(
        status=LicenseStatus.EXPIRED, license=lic, days_remaining=0,
        message_ar="انتهى اشتراك أثير وفترة السماح. جدّد الاشتراك لاستئناف الخدمة.",
        message_en="Atheer subscription and grace period have ended. Renew to resume service.",
    )


class LicenseGuard:
    """Caches the license state and re-reads the file periodically (renewal without restart)."""

    def __init__(self, path: Path, public_key_b64: str | None, *, clock: Clock | None = None,
                 refresh_seconds: float = 300) -> None:
        self.path = Path(path)
        self._key = public_key_b64
        self._clock = clock or SystemClock()
        self._refresh = timedelta(seconds=refresh_seconds)
        self._lock = threading.Lock()
        self._state: LicenseState | None = None
        self._checked_at: datetime | None = None
        self._mtime: float | None = None

    @property
    def enforced(self) -> bool:
        return bool(self._key)

    def state(self) -> LicenseState:
        now = self._clock.now()
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            mtime = None
        with self._lock:
            stale = (self._state is None or mtime != self._mtime
                     or self._checked_at is None or now - self._checked_at >= self._refresh)
            if stale:
                raw = self.path.read_bytes() if mtime is not None else None
                self._state = evaluate(raw, self._key, now)
                self._checked_at, self._mtime = now, mtime
            return self._state  # type: ignore[return-value]

    def require(self) -> LicenseState:
        state = self.state()
        if not state.allows_operation:
            raise LicenseError(state.message_ar, state.message_en)
        return state

    def doctor_limit(self) -> int | None:
        state = self.state()
        return state.license.max_doctors if state.license else None
