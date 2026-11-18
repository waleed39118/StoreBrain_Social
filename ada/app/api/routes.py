"""HTTP API. Sync DB endpoints run in FastAPI's threadpool; voice work is offloaded explicitly."""
import asyncio
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request, UploadFile,
                     status)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import ANY_STAFF, MANAGERS, OWNER, analytics, assistant, current_user, inventory
from app.core.assistant import CASHIER_INTENTS, AdaAssistant
from app.core.auto_updater import PatchError
from app.core.barcode import BarcodeError, normalize_barcode
from app.core.inventory_manager import InventoryError, InventoryManager, LineRequest
from app.core.market_analytics import MarketAnalytics
from app.database import begin_write
from app.models import Product, Role, User
from app.schemas import (ChatIn, ChatOut, ImportReportOut, ProductIn, ProductOut, ProductUpdate,
                         RestockIn, SaleIn, SaleOut)
from app.services.catalog_import import (MAX_FILE_BYTES, CatalogImporter, ImportFileError,
                                         StockMode, build_template)

# Every route requires a signed-in user; stricter roles are declared per route.
router = APIRouter(prefix="/api/v1", dependencies=[Depends(ANY_STAFF)])
# Machine-to-machine routes authenticated by their own mechanism (HMAC signature).
machine_router = APIRouter(prefix="/api/v1")


# ---------- products / inventory ----------
@router.post("/products", response_model=ProductOut, status_code=201, dependencies=[Depends(MANAGERS)])
def create_product(body: ProductIn, inv: InventoryManager = Depends(inventory)):
    begin_write(inv.db)
    p = Product(**body.model_dump())
    inv.db.add(p)
    try:
        inv.db.commit()
    except IntegrityError:
        inv.db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "SKU or barcode already exists")
    return p


@router.patch("/products/{sku}", response_model=ProductOut, dependencies=[Depends(MANAGERS)])
def update_product(sku: str, body: ProductUpdate, inv: InventoryManager = Depends(inventory)):
    begin_write(inv.db)
    p = inv.get_by_sku(sku)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown product: {sku}")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    try:
        inv.db.commit()
    except IntegrityError:
        inv.db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Barcode already assigned to another product")
    return p


@router.get("/products/by-barcode/{code}", response_model=ProductOut)
def product_by_barcode(code: str, inv: InventoryManager = Depends(inventory)):
    """Used by USB/Bluetooth scanners (keyboard wedge) and camera scanning in the UI."""
    try:
        clean = normalize_barcode(code)
    except BarcodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
    p = inv.get_by_barcode(clean) if clean else None
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Barcode not found")
    return p


@router.post("/products/import", response_model=ImportReportOut, dependencies=[Depends(MANAGERS)])
async def import_products(file: UploadFile = File(...), dry_run: bool = Form(False),
                          stock_mode: StockMode = Form(StockMode.SET),
                          skip_invalid: bool = Form(False),
                          inv: InventoryManager = Depends(inventory)):
    """Excel/CSV import. Run with dry_run=true first to preview the report."""
    data = await file.read(MAX_FILE_BYTES + 1)
    try:
        report = await run_in_threadpool(CatalogImporter(inv.db).run, file.filename or "", data,
                                         stock_mode=stock_mode, dry_run=dry_run,
                                         skip_invalid=skip_invalid)
    except ImportFileError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return ImportReportOut(**vars(report))


@router.get("/products/import/template", dependencies=[Depends(MANAGERS)])
def import_template():
    return Response(build_template(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="ada_products_template.xlsx"'})


@router.get("/products", response_model=list[ProductOut])
def list_products(q: str | None = None, inv: InventoryManager = Depends(inventory)):
    if q:
        return inv.find(q, limit=50)
    return list(inv.db.scalars(select(Product).order_by(Product.name_en).limit(500)))


@router.get("/inventory/low-stock", response_model=list[ProductOut])
def low_stock(inv: InventoryManager = Depends(inventory)):
    return inv.low_stock()


@router.post("/products/{sku}/restock", response_model=ProductOut, dependencies=[Depends(MANAGERS)])
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
@router.get("/analytics/best-sellers", dependencies=[Depends(MANAGERS)])
def best_sellers(top: int = 10, days: int | None = None, an: MarketAnalytics = Depends(analytics)):
    return an.best_sellers(min(top, 100), days)


@router.get("/analytics/conditions", dependencies=[Depends(MANAGERS)])
def conditions(an: MarketAnalytics = Depends(analytics)):
    return an.evaluate_conditions()


@router.get("/analytics/obsolete", dependencies=[Depends(MANAGERS)])
def obsolete(an: MarketAnalytics = Depends(analytics)):
    return an.obsolete_items()


@router.get("/analytics/reorder", dependencies=[Depends(MANAGERS)])
def reorder(an: MarketAnalytics = Depends(analytics)):
    return an.reorder_list()


@router.get("/analytics/diversification", dependencies=[Depends(MANAGERS)])
def diversification(an: MarketAnalytics = Depends(analytics)):
    return an.diversification()


# ---------- Ada: text & voice ----------
def _allowed(user: User) -> frozenset[str] | None:
    """Chat must not bypass role checks (e.g. a cashier restocking by voice)."""
    return CASHIER_INTENTS if user.role == Role.CASHIER else None


async def _finish(request: Request, reply, speak: bool, transcript: str | None = None) -> ChatOut:
    audio_url = None
    if speak:
        path: Path = await asyncio.to_thread(request.app.state.voice.synthesize, reply.text, reply.language)
        audio_url = f"/api/v1/audio/{path.name}"
    return ChatOut(reply=reply.text, language=reply.language, intent=reply.intent,
                   data=reply.data, transcript=transcript, audio_url=audio_url)


@router.post("/ada/chat", response_model=ChatOut)
async def chat(body: ChatIn, request: Request, ada: AdaAssistant = Depends(assistant),
               user: User = Depends(current_user)):
    reply = await run_in_threadpool(ada.handle, body.text, body.language, "text", _allowed(user))
    return await _finish(request, reply, body.speak)


@router.post("/ada/voice", response_model=ChatOut)
async def voice(request: Request, audio: UploadFile = File(...), speak: bool = Form(True),
                ada: AdaAssistant = Depends(assistant), user: User = Depends(current_user)):
    data = await audio.read(request.app.state.settings.max_audio_bytes + 1)
    suffix = Path(audio.filename or "a.wav").suffix or ".wav"
    try:
        tr = await asyncio.to_thread(request.app.state.voice.transcribe, data, suffix)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if not tr.text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No speech detected")
    lang = tr.language if tr.language in ("ar", "en") else None
    reply = await run_in_threadpool(ada.handle, tr.text, lang, "voice", _allowed(user))
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
@router.get("/system/updater", dependencies=[Depends(OWNER)])
def updater_status(request: Request):
    return request.app.state.updater.last_status


@machine_router.post("/system/patches")
async def push_patch(request: Request):
    """Push-mode patch delivery (same signature rules as pull mode)."""
    body = await request.body()
    try:
        return await asyncio.to_thread(request.app.state.updater.apply_raw, body,
                                       request.headers.get("X-Ada-Signature", ""))
    except PatchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
