"""Authentication.

* Owner: the single phone number in ADA_OWNER_PHONE signs in with a 6-digit SMS code.
  The owner account is created automatically on the first successful verification.
* Staff (manager/cashier): created by the owner; sign in with phone + PIN (no SMS cost
  at the till). PINs are scrypt-hashed and lock after repeated failures.
* Sessions: random bearer tokens; only their keyed hash is stored, so a DB leak can't be
  replayed. Each device has its own revocable session.
* Anti-enumeration: requesting a code for any number returns the same response.
"""
import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.security import (PhoneError, keyed_hash, new_otp, new_token, normalize_phone,
                               verify_pin)
from app.database import begin_write
from app.models import AuthSession, OtpCode, Role, User, utcnow
from app.services.sms import SmsSender

log = logging.getLogger("ada.auth")


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class LoginResult:
    token: str
    user: User
    expires_at: object


class AuthService:
    def __init__(self, db: Session, settings: Settings, sms: SmsSender) -> None:
        self.db, self.s, self.sms = db, settings, sms
        self._secret = settings.auth_secret.get_secret_value()
        if len(self._secret) < 32:
            raise RuntimeError("ADA_AUTH_SECRET must be set (>= 32 chars)")

    def phone(self, raw: str) -> str:
        try:
            return normalize_phone(raw, self.s.default_country_code)
        except PhoneError as exc:
            raise AuthError(str(exc), 422) from exc

    def owner_phone(self) -> str | None:
        return self.phone(self.s.owner_phone) if self.s.owner_phone else None

    # ---------- owner: SMS OTP ----------
    def request_otp(self, raw_phone: str) -> None:
        phone = self.phone(raw_phone)
        if phone != self.owner_phone():
            log.info("OTP requested for non-owner number; ignored")
            return                                   # identical response: no enumeration
        begin_write(self.db)
        now = utcnow()
        last = self.db.scalar(select(func.max(OtpCode.created_at)).where(OtpCode.phone == phone))
        if last and _aware(last) > now - timedelta(seconds=self.s.otp_resend_cooldown_sec):
            raise AuthError("Please wait before requesting another code", 429)
        sent_hour = self.db.scalar(select(func.count(OtpCode.id)).where(
            OtpCode.phone == phone, OtpCode.created_at > now - timedelta(hours=1)))
        if sent_hour >= self.s.otp_max_per_hour:
            raise AuthError("Too many codes requested; try again later", 429)
        # Invalidate older unused codes: only the newest code works.
        self.db.execute(update(OtpCode).where(OtpCode.phone == phone, OtpCode.consumed_at.is_(None))
                        .values(consumed_at=now))
        code = new_otp()
        self.db.add(OtpCode(phone=phone, code_hash=keyed_hash(self._secret, f"{phone}:{code}"),
                            expires_at=now + timedelta(seconds=self.s.otp_ttl_sec)))
        self.sms.send(self.db, phone,
                      f"Ada / أدا: {code} رمز الدخول. لا تشاركه مع أحد. Valid "
                      f"{self.s.otp_ttl_sec // 60} min.", self.s.otp_ttl_sec)
        self.db.commit()

    def verify_otp(self, raw_phone: str, code: str, device: str) -> LoginResult:
        phone = self.phone(raw_phone)
        begin_write(self.db)
        now = utcnow()
        otp = self.db.scalar(select(OtpCode).where(OtpCode.phone == phone, OtpCode.consumed_at.is_(None))
                             .order_by(OtpCode.created_at.desc()).limit(1))
        if otp is None or _aware(otp.expires_at) < now or otp.attempts >= self.s.otp_max_attempts:
            self.db.commit()
            raise AuthError("Code expired or invalid; request a new one")
        otp.attempts += 1
        if keyed_hash(self._secret, f"{phone}:{code.strip()}") != otp.code_hash or phone != self.owner_phone():
            self.db.commit()                          # persist the attempt counter
            raise AuthError("Code expired or invalid; request a new one")
        otp.consumed_at = now
        user = self.db.scalar(select(User).where(User.phone == phone))
        if user is None:
            user = User(phone=phone, name=self.s.owner_name, role=Role.OWNER)
            self.db.add(user)
            self.db.flush()
        elif not user.is_active or user.role != Role.OWNER:
            self.db.commit()
            raise AuthError("Account disabled", 403)
        return self._new_session(user, device)

    # ---------- staff: phone + PIN ----------
    def pin_login(self, raw_phone: str, pin: str, device: str) -> LoginResult:
        phone = self.phone(raw_phone)
        begin_write(self.db)
        now = utcnow()
        user = self.db.scalar(select(User).where(User.phone == phone))
        if user and user.locked_until and _aware(user.locked_until) > now:
            self.db.commit()
            raise AuthError("Too many attempts; account temporarily locked", 429)
        if not verify_pin(pin, user.pin_hash if user else None) or not user.is_active:
            if user:
                user.failed_attempts += 1
                if user.failed_attempts >= self.s.pin_max_attempts:
                    user.locked_until = now + timedelta(minutes=self.s.pin_lockout_min)
                    user.failed_attempts = 0
            self.db.commit()
            raise AuthError("Invalid phone or PIN")
        user.failed_attempts, user.locked_until = 0, None
        return self._new_session(user, device)

    # ---------- sessions ----------
    def _new_session(self, user: User, device: str) -> LoginResult:
        token = new_token()
        exp = utcnow() + timedelta(days=self.s.session_days)
        user.last_login_at = utcnow()
        self.db.add(AuthSession(user_id=user.id, token_hash=keyed_hash(self._secret, token),
                                device_name=(device or "device")[:100], expires_at=exp))
        self.db.commit()
        return LoginResult(token, user, exp)

    def resolve(self, token: str) -> tuple[User, AuthSession]:
        sess = self.db.scalar(select(AuthSession).where(
            AuthSession.token_hash == keyed_hash(self._secret, token)))
        now = utcnow()
        if (sess is None or sess.revoked_at is not None or _aware(sess.expires_at) < now
                or not sess.user.is_active):
            raise AuthError("Not authenticated")
        if now - _aware(sess.last_seen_at) > timedelta(minutes=5):   # throttle writes
            sess.last_seen_at = now
            self.db.commit()
        return sess.user, sess

    def revoke(self, session_id: int, user_id: int | None = None) -> bool:
        begin_write(self.db)
        stmt = update(AuthSession).where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
        if user_id is not None:
            stmt = stmt.where(AuthSession.user_id == user_id)
        n = self.db.execute(stmt.values(revoked_at=utcnow())).rowcount
        self.db.commit()
        return n > 0

    def revoke_all(self, user_id: int) -> int:
        begin_write(self.db)
        n = self.db.execute(update(AuthSession).where(AuthSession.user_id == user_id,
                                                      AuthSession.revoked_at.is_(None))
                            .values(revoked_at=utcnow())).rowcount
        self.db.commit()
        return n


def _aware(dt):
    """SQLite returns naive datetimes; values are always stored as UTC."""
    from datetime import timezone
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
