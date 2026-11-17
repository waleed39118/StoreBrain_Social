"""HTTP and WebSocket endpoints.

Handlers that touch the database are plain ``def`` so FastAPI runs them in its
thread pool and the event loop (speakers, microphone) never blocks.
"""

from __future__ import annotations

import asyncio
import io
import wave
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ConfigDict, Field

from atheer import __version__
from atheer.api.security import is_staff, require_staff
from atheer.appointments.schemas import (
    AppointmentView,
    BookingRequest,
    BookingResult,
    RescheduleRequest,
    Slot,
    StaffAlert,
)
from atheer.calculations import CostBreakdown, CoverageTerms, DoseVerification, StockAnalysis, WaitEstimate
from atheer.db.models import AppointmentStatus
from atheer.queue.service import Announcement, TicketView
from atheer.runtime import Atheer
from atheer.secretary import CheckInResult
from atheer.voice.engines import SAMPLE_RATE

MAX_AUDIO_BYTES = 5 * 1024 * 1024  # ~2.5 min of 16 kHz mono PCM16
MAX_TEXT = 500

public = APIRouter()
staff = APIRouter(dependencies=[Depends(require_staff)])


def app_state(request: Request) -> Atheer:
    return request.app.state.atheer


# ----------------------------------------------------------------- schemas


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    speak: bool = False


class ChatOut(BaseModel):
    text: str
    language: str
    speak: bool


class CheckInIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appointment_id: int = Field(gt=0)
    mrn: str = Field(min_length=1, max_length=32)


class StatusIn(BaseModel):
    status: AppointmentStatus


class CallNextIn(BaseModel):
    counter: str = Field(min_length=1, max_length=32)
    doctor_id: int | None = Field(default=None, gt=0)


class DoctorPresenceIn(BaseModel):
    arrived: bool


class DoseIn(BaseModel):
    drug_name: str = Field(min_length=1, max_length=120)
    prescribed_mg: Decimal = Field(gt=0)
    weight_kg: Decimal = Field(gt=0)
    doses_per_day: int = Field(default=1, ge=1, le=24)


class CostIn(BaseModel):
    charges: list[Decimal] = Field(min_length=1, max_length=200)
    terms: CoverageTerms | None = None


class StockIn(BaseModel):
    on_hand: int = Field(ge=0)
    daily_usage: list[int] = Field(min_length=1, max_length=366)
    lead_time_days: int = Field(ge=0, le=365)
    on_order: int = Field(default=0, ge=0)
    service_level: float = Field(default=0.95, ge=0.5, lt=1)
    review_period_days: int = Field(default=7, ge=1, le=90)


class BsaIn(BaseModel):
    height_cm: Decimal
    weight_kg: Decimal


class CrclIn(BaseModel):
    age_years: int
    weight_kg: Decimal
    serum_creatinine_mg_dl: Decimal
    sex: Literal["male", "female"]


# ----------------------------------------------------------------- public


@public.get("/health")
def health(a: Atheer = Depends(app_state)) -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "clinic": a.settings.clinic_name,
        "voice": {"tts": a.voice.tts_name, "listening": a.voice.can_listen},
        "content_version": a.updater.current_version if a.updater else None,
        "formulary_drugs": len(a.calc.drugs),
        "terminology_terms": len(a.terminology),
    }


@public.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, request: Request, a: Atheer = Depends(app_state)) -> ChatOut:
    """Text conversation. With a valid staff key, staff-only requests are allowed."""
    reply = a.secretary.handle_text(body.text, staff=is_staff(request), speak=body.speak)
    return ChatOut(text=reply.text, language=reply.language, speak=reply.speak)


@public.websocket("/ws/chat")
async def chat_ws(ws: WebSocket) -> None:
    """Streaming chat: send ``{"text": "..."}``, receive ``{"text", "language", "speak"}`` per message."""
    a: Atheer = ws.app.state.atheer
    staff_rights = is_staff(ws)
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            text = str(data.get("text", ""))[:MAX_TEXT] if isinstance(data, dict) else ""
            if not text.strip():
                await ws.send_json({"error": "text is required"})
                continue
            reply = await asyncio.to_thread(a.secretary.handle_text, text, staff=staff_rights,
                                            speak=bool(data.get("speak")))
            await ws.send_json({"text": reply.text, "language": reply.language, "speak": reply.speak})
    except WebSocketDisconnect:
        return


@public.post("/voice/transcribe")
async def transcribe(request: Request) -> dict:
    """Send a 16 kHz mono 16-bit WAV body; returns the transcript and Atheer's reply (public rights)."""
    a: Atheer = request.app.state.atheer
    if not a.voice.can_listen:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Speech recognition is not enabled.")
    if int(request.headers.get("content-length") or 0) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio too long.")
    body = await request.body()
    if len(body) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio too long.")
    pcm = _wav_to_pcm16(body)
    transcript = await a.voice.transcribe(pcm)
    if transcript is None:
        return {"transcript": None, "reply": None}
    reply = await asyncio.to_thread(a.secretary.handle_text, transcript.text, staff=False)
    return {
        "transcript": {"text": transcript.text, "language": transcript.language, "confidence": transcript.confidence},
        "reply": {"text": reply.text, "language": reply.language},
    }


@public.post("/checkin", response_model=CheckInResult)
def check_in(body: CheckInIn, a: Atheer = Depends(app_state)) -> CheckInResult:
    """Kiosk check-in: appointment number + medical record number."""
    result = a.secretary.check_in(body.appointment_id, body.mrn)
    result.alerts = []  # VIP/staff alerts are for staff screens, never the kiosk
    return result


@public.post("/queue/tickets", response_model=TicketView, status_code=201)
def walk_in(a: Atheer = Depends(app_state)) -> TicketView:
    return a.secretary.walk_in()


@public.get("/queue/tickets/{ticket_id}/wait", response_model=WaitEstimate)
def ticket_wait(ticket_id: int, a: Atheer = Depends(app_state)) -> WaitEstimate:
    return a.secretary.queue.estimate_wait_for(ticket_id)


@public.get("/doctors/{doctor_id}/slots", response_model=list[Slot])
def slots(doctor_id: int, day: date, a: Atheer = Depends(app_state)) -> list[Slot]:
    return a.secretary.free_slots(doctor_id, day)


@public.get("/terminology/{term}")
def terminology(term: str, a: Atheer = Depends(app_state)) -> dict:
    entry = a.terminology.lookup(term)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Term not found.")
    return {"term": term, "entry": entry}


# ----------------------------------------------------------------- staff: scheduling & queue


@staff.post("/appointments", response_model=BookingResult, status_code=201)
def book(body: BookingRequest, a: Atheer = Depends(app_state)) -> BookingResult:
    return a.secretary.book(body)


@staff.post("/appointments/reschedule", response_model=AppointmentView)
def reschedule(body: RescheduleRequest, a: Atheer = Depends(app_state)) -> AppointmentView:
    return a.secretary.reschedule(body)


@staff.post("/appointments/{appointment_id}/status", response_model=BookingResult)
def set_status(appointment_id: int, body: StatusIn, a: Atheer = Depends(app_state)) -> BookingResult:
    return a.secretary.set_status(appointment_id, body.status)


@staff.get("/alerts", response_model=list[StaffAlert])
def alerts(day: date | None = None, a: Atheer = Depends(app_state)) -> list[StaffAlert]:
    return a.secretary.alerts(day)


@staff.get("/reminders", response_model=list[AppointmentView])
def reminders(a: Atheer = Depends(app_state)) -> list[AppointmentView]:
    return a.secretary.appointments.due_reminders()


@staff.get("/queue", response_model=list[TicketView])
def waiting(a: Atheer = Depends(app_state)) -> list[TicketView]:
    return a.secretary.queue.waiting()


@staff.post("/queue/call-next", response_model=Announcement | None)
def call_next(body: CallNextIn, a: Atheer = Depends(app_state)) -> Announcement | None:
    return a.secretary.call_next(body.counter, doctor_id=body.doctor_id)


@staff.post("/queue/tickets/{ticket_id}/{action}", response_model=TicketView | Announcement)
def ticket_action(
    ticket_id: int,
    action: Literal["recall", "serve", "finish", "skip", "requeue"],
    a: Atheer = Depends(app_state),
) -> TicketView | Announcement:
    q = a.secretary.queue
    handler = {"recall": q.recall, "serve": q.start_serving, "finish": q.finish, "skip": q.skip, "requeue": q.requeue}
    return handler[action](ticket_id)


@staff.post("/doctors/{doctor_id}/presence")
def doctor_presence(doctor_id: int, body: DoctorPresenceIn, a: Atheer = Depends(app_state)) -> dict:
    text_ar, text_en = a.secretary.announce_doctor(doctor_id, arrived=body.arrived)
    return {"text_ar": text_ar, "text_en": text_en}


# ----------------------------------------------------------------- staff: calculations


@staff.get("/calc/formulary")
def formulary(a: Atheer = Depends(app_state)) -> dict:
    return {"drugs": a.calc.drugs}


@staff.post("/calc/dose", response_model=DoseVerification)
def dose(body: DoseIn, a: Atheer = Depends(app_state)) -> DoseVerification:
    return a.calc.verify_dose(body.drug_name, body.prescribed_mg, body.weight_kg, body.doses_per_day)


@staff.post("/calc/cost", response_model=CostBreakdown)
def cost(body: CostIn, a: Atheer = Depends(app_state)) -> CostBreakdown:
    return a.calc.patient_cost(body.charges, body.terms)


@staff.post("/calc/stock", response_model=StockAnalysis)
def stock(body: StockIn, a: Atheer = Depends(app_state)) -> StockAnalysis:
    return a.calc.stock(body.on_hand, body.daily_usage, body.lead_time_days, on_order=body.on_order,
                        service_level=body.service_level, review_period_days=body.review_period_days)


@staff.post("/calc/bsa")
def bsa(body: BsaIn, a: Atheer = Depends(app_state)) -> dict:
    return {"bsa_m2": a.calc.bsa(body.height_cm, body.weight_kg)}


@staff.post("/calc/crcl")
def crcl(body: CrclIn, a: Atheer = Depends(app_state)) -> dict:
    return {"crcl_ml_min": a.calc.creatinine_clearance(body.age_years, body.weight_kg,
                                                        body.serum_creatinine_mg_dl, body.sex)}


# ----------------------------------------------------------------- staff: updates


@staff.get("/updates")
def update_status(a: Atheer = Depends(app_state)) -> dict:
    return a.updater.status() if a.updater else {"enabled": False}


@staff.post("/updates/check")
def update_check(a: Atheer = Depends(app_state)) -> dict:
    if a.updater is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auto-update is not configured.")
    return {"installed": a.updater.check_now(), "current_version": a.updater.current_version}


@staff.post("/updates/rollback")
def update_rollback(a: Atheer = Depends(app_state)) -> dict:
    if a.updater is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auto-update is not configured.")
    return {"current_version": a.updater.rollback()}


# ----------------------------------------------------------------- helpers


def _wav_to_pcm16(data: bytes) -> bytes:
    try:
        with wave.open(io.BytesIO(data)) as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (SAMPLE_RATE, 1, 2):
                raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Send 16 kHz mono 16-bit PCM WAV.")
            return wav.readframes(wav.getnframes())
    except (wave.Error, EOFError) as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Body is not a valid WAV file.") from exc
