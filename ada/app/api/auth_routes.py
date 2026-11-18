"""Auth, staff management, in-app notifications and the SMS gateway protocol."""
import asyncio
import json
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import MANAGERS, OWNER, auth_service, current_session, require_gateway
from app.core.security import hash_pin, validate_pin_format
from app.database import begin_write, get_db
from app.config import Settings, get_settings
from app.models import Alert, AuthSession, Role, SmsOutbox, SmsStatus, User, utcnow
from app.schemas import (GatewayAckIn, GatewayMessageOut, LoginOut, NotificationOut, OtpRequestIn,
                         OtpVerifyIn, PinLoginIn, SessionOut, StaffIn, StaffUpdate, UserOut)
from app.services.auth_service import AuthError, AuthService, LoginResult
from app.services.sms import CLAIM_TIMEOUT, SmsGatewayQueue
from app.services.store_settings import get_value, set_value

GATEWAY_SEEN_KEY = "sms_gateway.last_seen"

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/v1/users", tags=["users"], dependencies=[Depends(OWNER)])
notif_router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"],
                         dependencies=[Depends(MANAGERS)])
gateway_router = APIRouter(prefix="/api/v1/sms-gateway", tags=["sms-gateway"],
                           dependencies=[Depends(require_gateway)])
gateway_admin = APIRouter(prefix="/api/v1/system/sms-gateway", tags=["sms-gateway"],
                          dependencies=[Depends(OWNER)])


def _http(exc: AuthError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


def _login_out(r: LoginResult) -> LoginOut:
    return LoginOut(token=r.token, expires_at=r.expires_at, user=UserOut.model_validate(r.user))


# ---------- auth ----------
@auth_router.post("/otp/request", status_code=202)
def otp_request(body: OtpRequestIn, auth: AuthService = Depends(auth_service)):
    try:
        auth.request_otp(body.phone)
    except AuthError as exc:
        raise _http(exc)
    return {"detail": "If this number is registered, a code has been sent."}


@auth_router.post("/otp/verify", response_model=LoginOut)
def otp_verify(body: OtpVerifyIn, auth: AuthService = Depends(auth_service)):
    try:
        return _login_out(auth.verify_otp(body.phone, body.code, body.device_name))
    except AuthError as exc:
        raise _http(exc)


@auth_router.post("/pin/login", response_model=LoginOut)
def pin_login(body: PinLoginIn, auth: AuthService = Depends(auth_service)):
    try:
        return _login_out(auth.pin_login(body.phone, body.pin, body.device_name))
    except AuthError as exc:
        raise _http(exc)


@auth_router.get("/me", response_model=UserOut)
def me(sess=Depends(current_session)):
    return sess[0]


@auth_router.post("/logout", status_code=204)
def logout(sess=Depends(current_session), auth: AuthService = Depends(auth_service)):
    auth.revoke(sess[1].id)


@auth_router.post("/logout-all", status_code=204)
def logout_all(sess=Depends(current_session), auth: AuthService = Depends(auth_service)):
    auth.revoke_all(sess[0].id)


@auth_router.get("/sessions", response_model=list[SessionOut])
def my_sessions(sess=Depends(current_session), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuthSession).where(AuthSession.user_id == sess[0].id,
                                                AuthSession.revoked_at.is_(None),
                                                AuthSession.expires_at > utcnow())
                      .order_by(AuthSession.last_seen_at.desc()))
    return [SessionOut.model_validate(r).model_copy(update={"current": r.id == sess[1].id}) for r in rows]


@auth_router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: int, sess=Depends(current_session),
                   auth: AuthService = Depends(auth_service)):
    if not auth.revoke(session_id, user_id=sess[0].id):
        raise HTTPException(status.HTTP_404_NOT_FOUND)


# ---------- staff management (owner only) ----------
def _pin(pin: str) -> str:
    try:
        validate_pin_format(pin)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
    return hash_pin(pin)


@users_router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return list(db.scalars(select(User).order_by(User.role, User.name)))


@users_router.post("", response_model=UserOut, status_code=201)
def create_staff(body: StaffIn, db: Session = Depends(get_db), auth: AuthService = Depends(auth_service)):
    try:
        phone = auth.phone(body.phone)
    except AuthError as exc:
        raise _http(exc)
    if phone == auth.owner_phone():
        raise HTTPException(status.HTTP_409_CONFLICT, "This is the owner's number")
    begin_write(db)
    user = User(phone=phone, name=body.name, role=Role(body.role), pin_hash=_pin(body.pin))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Phone already registered")
    return user


@users_router.patch("/{user_id}", response_model=UserOut)
def update_staff(user_id: int, body: StaffUpdate, db: Session = Depends(get_db),
                 auth: AuthService = Depends(auth_service)):
    begin_write(db)
    user = db.get(User, user_id)
    if user is None or user.role == Role.OWNER:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")
    data = body.model_dump(exclude_unset=True)
    if "pin" in data:
        user.pin_hash, user.failed_attempts, user.locked_until = _pin(data.pop("pin")), 0, None
    if "role" in data:
        user.role = Role(data.pop("role"))
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    if body.is_active is False or body.pin or body.role:
        auth.revoke_all(user.id)          # force re-login with new credentials/permissions
    return user


# ---------- in-app notifications (owner/manager) ----------
@notif_router.get("", response_model=list[NotificationOut])
def notifications(unread_only: bool = False, after_id: int = 0,
                  limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    """Poll with after_id=<last seen id> for new alerts."""
    stmt = select(Alert).where(Alert.id > after_id)
    if unread_only:
        stmt = stmt.where(Alert.read_at.is_(None))
    return list(db.scalars(stmt.order_by(Alert.id.desc()).limit(limit)))


@notif_router.get("/unread-count")
def unread_count(db: Session = Depends(get_db)):
    from sqlalchemy import func
    return {"count": db.scalar(select(func.count(Alert.id)).where(Alert.read_at.is_(None)))}


@notif_router.post("/{alert_id}/read", status_code=204)
def mark_read(alert_id: int, db: Session = Depends(get_db)):
    begin_write(db)
    db.execute(update(Alert).where(Alert.id == alert_id, Alert.read_at.is_(None)).values(read_at=utcnow()))
    db.commit()


@notif_router.post("/read-all", status_code=204)
def mark_all_read(db: Session = Depends(get_db)):
    begin_write(db)
    db.execute(update(Alert).where(Alert.read_at.is_(None)).values(read_at=utcnow()))
    db.commit()


# ---------- SMS gateway (owner's Android phone with SIM) ----------
def _work_available(db: Session) -> bool:
    """Cheap read-only check so idle long-polls never take the write lock."""
    now = utcnow()
    return bool(db.scalar(select(SmsOutbox.id).where(
        (SmsOutbox.status == SmsStatus.PENDING) |
        ((SmsOutbox.status == SmsStatus.SENDING) & (SmsOutbox.claimed_at < now - CLAIM_TIMEOUT))
    ).limit(1)))


def _claim(db: Session, limit: int) -> list[GatewayMessageOut]:
    begin_write(db)
    out = [GatewayMessageOut(id=m.id, phone=m.phone, body=m.body)
           for m in SmsGatewayQueue(db).claim(limit)]
    return out


def _touch_gateway(db: Session, device: str) -> None:
    begin_write(db)
    set_value(db, GATEWAY_SEEN_KEY, {"at": utcnow().isoformat(), "device": device[:120]})
    db.commit()


@gateway_router.post("/claim", response_model=list[GatewayMessageOut])
async def gateway_claim(limit: int = Query(10, ge=1, le=50), wait: int = Query(0, ge=0, le=30),
                        x_gateway_device: str = Header(default="android"),
                        db: Session = Depends(get_db)):
    """Long-poll: holds up to ``wait`` seconds until an SMS is queued (instant OTP delivery
    with ~2 requests/minute when idle, so the phone's battery is barely affected)."""
    deadline = time.monotonic() + wait
    try:
        while True:
            if await run_in_threadpool(_work_available, db):
                msgs = await run_in_threadpool(_claim, db, limit)
                if msgs:
                    return msgs
            if time.monotonic() >= deadline:
                return []
            db.rollback()                     # release the read snapshot between checks
            await asyncio.sleep(1)
    finally:
        await run_in_threadpool(_touch_gateway, db, x_gateway_device)


@gateway_router.post("/{msg_id}/ack", status_code=204)
def gateway_ack(msg_id: int, body: GatewayAckIn, db: Session = Depends(get_db)):
    begin_write(db)
    if not SmsGatewayQueue(db).ack(msg_id, body.ok, body.error):
        raise HTTPException(status.HTTP_409_CONFLICT, "Message not in sending state")


# ---------- SMS gateway administration (owner) ----------
@gateway_admin.get("/status")
def gateway_status(db: Session = Depends(get_db)):
    seen = get_value(db, GATEWAY_SEEN_KEY)
    since = utcnow() - timedelta(hours=24)
    counts = dict(db.execute(select(SmsOutbox.status, func.count(SmsOutbox.id))
                             .where(SmsOutbox.created_at >= since).group_by(SmsOutbox.status)).all())
    online = False
    if seen:
        from datetime import datetime
        online = utcnow() - datetime.fromisoformat(seen["at"]) < timedelta(seconds=90)
    return {"online": online, "last_seen": seen["at"] if seen else None,
            "device": seen["device"] if seen else None,
            "last_24h": {k.value if hasattr(k, "value") else k: v for k, v in counts.items()}}


@gateway_admin.get("/pairing")
def gateway_pairing(request: Request, settings: Settings = Depends(get_settings),
                    auth: AuthService = Depends(auth_service)):
    """Data for the pairing QR shown to the owner; scanned by the Ada SMS Gateway app.

    ``allow`` is the recipient allow-list enforced *on the phone*: even a compromised
    server could not make the SIM text any other number.
    """
    token = settings.sms_gateway_token.get_secret_value()
    if len(token) < 32:
        raise HTTPException(status.HTTP_409_CONFLICT, "ADA_SMS_GATEWAY_TOKEN is not configured")
    url = (settings.public_url or str(request.base_url)).rstrip("/")
    allow = [auth.owner_phone()] if auth.owner_phone() else []
    return {"url": url, "allow": allow,
            "qr": json.dumps({"ada": "sms-gateway", "v": 1, "url": url, "token": token,
                              "allow": allow}, separators=(",", ":"))}


@gateway_admin.post("/test", status_code=202)
def gateway_test(request: Request, db: Session = Depends(get_db),
                 auth: AuthService = Depends(auth_service)):
    begin_write(db)
    request.app.state.sms.send(db, auth.owner_phone(), "Ada / أدا: رسالة اختبار ✓ Test message", 600)
    db.commit()
    return {"detail": "Test SMS queued"}
