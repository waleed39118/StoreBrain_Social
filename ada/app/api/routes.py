"""HTTP API. Sync DB endpoints run in FastAPI's threadpool; voice work is offloaded explicitly."""
import asyncio
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request, UploadFile,
                     status)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import analytics, assistant, inventory, require_api_key
from app.core.assistant import AdaAssistant
from app.core.auto_updater import PatchError
from app.core.inventory_manager import InventoryError, InventoryManager, LineRequest
from app.core.market_analytics import MarketAnalytics
from app.models import Product
from app.schemas import ChatIn, ChatOut, ProductIn, ProductOut, RestockIn, SaleIn, SaleOut

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])


# ---------- products / inventory ----------
@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(body: ProductIn, inv: InventoryManager = Depends(inventory)):
    p = Product(**body.model_dump())
    inv.db.add(p)
    try:
        inv.db.commit()
    except IntegrityError:
        inv.db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"SKU {body.sku} already exists")
    return p


@router.get("/products", response_model=list[ProductOut])
def list_products(q: str | None = None, inv: InventoryManager = Depends(inventory)):
    if q:
        return inv.find(q, limit=50)
    return list(inv.db.scalars(select(Product).order_by(Product.name_en).limit(500)))


@router.get("/inventory/low-stock", response_model=list[ProductOut])
def low_stock(inv: InventoryManager = Depends(inventory)):
    return inv.low_stock()


@router.post("/products/{sku}/restock", response_model=ProductOut)
def restock(sku: str, body: RestockIn, inv: InventoryManager = Depends(inventory)):
    try:
        return inv.restock(sku, body.quantity, body.ref)
    except InventoryError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/sales", response_model=SaleOut, status_code=201)
def create_sale(body: SaleIn, inv: InventoryManager = Depends(inventory)):
    try:
        sale = inv.record_sale([LineRequest(i.sku, i.quantity) for i in body.items])
    except InventoryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
    return SaleOut(sale_id=sale.id, total=sale.total)


# ---------- analytics ----------
@router.get("/analytics/best-sellers")
def best_sellers(top: int = 10, days: int | None = None, an: MarketAnalytics = Depends(analytics)):
    return an.best_sellers(min(top, 100), days)


@router.get("/analytics/conditions")
def conditions(an: MarketAnalytics = Depends(analytics)):
    return an.evaluate_conditions()


@router.get("/analytics/obsolete")
def obsolete(an: MarketAnalytics = Depends(analytics)):
    return an.obsolete_items()


@router.get("/analytics/reorder")
def reorder(an: MarketAnalytics = Depends(analytics)):
    return an.reorder_list()


@router.get("/analytics/diversification")
def diversification(an: MarketAnalytics = Depends(analytics)):
    return an.diversification()


# ---------- Ada: text & voice ----------
async def _finish(request: Request, reply, speak: bool, transcript: str | None = None) -> ChatOut:
    audio_url = None
    if speak:
        path: Path = await asyncio.to_thread(request.app.state.voice.synthesize, reply.text, reply.language)
        audio_url = f"/api/v1/audio/{path.name}"
    return ChatOut(reply=reply.text, language=reply.language, intent=reply.intent,
                   data=reply.data, transcript=transcript, audio_url=audio_url)


@router.post("/ada/chat", response_model=ChatOut)
async def chat(body: ChatIn, request: Request, ada: AdaAssistant = Depends(assistant)):
    reply = await run_in_threadpool(ada.handle, body.text, body.language, "text")
    return await _finish(request, reply, body.speak)


@router.post("/ada/voice", response_model=ChatOut)
async def voice(request: Request, audio: UploadFile = File(...), speak: bool = Form(True),
                ada: AdaAssistant = Depends(assistant)):
    data = await audio.read(request.app.state.settings.max_audio_bytes + 1)
    suffix = Path(audio.filename or "a.wav").suffix or ".wav"
    try:
        tr = await asyncio.to_thread(request.app.state.voice.transcribe, data, suffix)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if not tr.text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No speech detected")
    reply = await run_in_threadpool(ada.handle, tr.text, tr.language if tr.language in ("ar", "en") else None, "voice")
    return await _finish(request, reply, speak, transcript=tr.text)


@router.get("/audio/{name}")
def audio_file(name: str, request: Request):
    # Strict name check prevents path traversal.
    if not (name.endswith(".wav") and len(name) == 36 and name[:32].isalnum()):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    path = Path(request.app.state.settings.tts_output_dir) / name
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return FileResponse(path, media_type="audio/wav")


# ---------- updater ----------
@router.get("/system/updater")
def updater_status(request: Request):
    return request.app.state.updater.last_status


@router.post("/system/patches")
async def push_patch(request: Request):
    """Push-mode patch delivery (same signature rules as pull mode)."""
    body = await request.body()
    try:
        return await asyncio.to_thread(request.app.state.updater.apply_raw, body,
                                       request.headers.get("X-Ada-Signature", ""))
    except PatchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
