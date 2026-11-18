"""Point-of-sale, offline sync, receipts, dashboard, store profile, demo data and backups."""
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import ANY_STAFF, MANAGERS, OWNER, current_user, inventory
from app.core.inventory_manager import InventoryError, InventoryManager, LineRequest
from app.database import begin_write, get_db
from app.models import (Alert, PaymentMethod, Product, Role, Sale, SaleItem, User, utcnow)
from app.schemas import SaleLineIn
from app.services.demo_data import load_demo
from app.services.store_settings import StoreProfile, get_profile, save_profile

router = APIRouter(prefix="/api/v1", dependencies=[Depends(ANY_STAFF)])
CENT = Decimal("0.01")
_UTC = timezone.utc


# ---------- schemas ----------
class PosSaleIn(BaseModel):
    items: list[SaleLineIn] = Field(min_length=1, max_length=200)
    payment_method: PaymentMethod = PaymentMethod.CASH
    client_ref: str | None = Field(None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9\-_]+$")


class OfflineSaleIn(PosSaleIn):
    client_ref: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9\-_]+$")
    sold_at: datetime


class SyncIn(BaseModel):
    sales: list[OfflineSaleIn] = Field(min_length=1, max_length=500)


# ---------- helpers ----------
def _receipt(sale: Sale, profile: StoreProfile) -> dict:
    total = Decimal(sale.total)
    rate = Decimal(str(profile.tax_rate))
    if profile.prices_include_tax:
        tax = (total * rate / (100 + rate)).quantize(CENT, ROUND_HALF_UP)
        subtotal, grand = total - tax, total
    else:
        tax = (total * rate / 100).quantize(CENT, ROUND_HALF_UP)
        subtotal, grand = total, total + tax
    return {
        "id": sale.id, "number": f"{sale.id:06d}", "client_ref": sale.client_ref,
        "created_at": sale.created_at.isoformat(), "channel": sale.channel,
        "payment_method": sale.payment_method, "cashier": sale.cashier.name if sale.cashier else None,
        "items": [{"sku": i.product.sku, "name_en": i.product.name_en, "name_ar": i.product.name_ar,
                   "quantity": i.quantity, "unit_price": str(i.unit_price),
                   "line_total": str((i.unit_price * i.quantity).quantize(CENT))} for i in sale.items],
        "subtotal": str(subtotal), "tax_rate": profile.tax_rate, "tax": str(tax),
        "total": str(grand), "currency": profile.currency,
        "store": {"name": profile.store_name, "phone": profile.store_phone, "address": profile.address,
                  "tax_number": profile.tax_number, "footer": profile.receipt_footer},
    }


def _load_sale(db: Session, sale_id: int) -> Sale | None:
    return db.scalar(select(Sale).where(Sale.id == sale_id).options(
        selectinload(Sale.items).selectinload(SaleItem.product), selectinload(Sale.cashier)))


# ---------- store profile ----------
@router.get("/store/profile", response_model=StoreProfile)
def store_profile(db: Session = Depends(get_db)):
    return get_profile(db)


@router.put("/store/profile", response_model=StoreProfile, dependencies=[Depends(OWNER)])
def update_store_profile(body: StoreProfile, db: Session = Depends(get_db)):
    begin_write(db)
    save_profile(db, body)
    db.commit()
    return body


# ---------- POS ----------
@router.get("/pos/catalog")
def pos_catalog(request: Request, response: Response, db: Session = Depends(get_db)):
    """Compact catalog for the till's offline cache; ETag lets clients skip unchanged data."""
    stamp = db.execute(select(func.count(Product.id), func.max(Product.updated_at))).one()
    etag = f'W/"{stamp[0]}-{stamp[1].timestamp() if stamp[1] else 0}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    rows = db.execute(select(Product.sku, Product.barcode, Product.name_en, Product.name_ar,
                             Product.category, Product.price, Product.stock_qty)
                      .where(Product.is_active.is_(True)).order_by(Product.name_en)).all()
    response.headers["ETag"] = etag
    return [{"sku": r.sku, "barcode": r.barcode, "name_en": r.name_en, "name_ar": r.name_ar,
             "category": r.category, "price": str(r.price), "stock_qty": r.stock_qty} for r in rows]


@router.post("/pos/sales", status_code=201)
def pos_sale(body: PosSaleIn, user: User = Depends(current_user),
             inv: InventoryManager = Depends(inventory)):
    try:
        sale = inv.record_sale([LineRequest(i.sku, i.quantity) for i in body.items], channel="pos",
                               cashier_id=user.id, payment_method=body.payment_method,
                               client_ref=body.client_ref)
    except InventoryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
    return _receipt(_load_sale(inv.db, sale.id), get_profile(inv.db))


@router.post("/pos/sync")
def pos_sync(body: SyncIn, user: User = Depends(current_user),
             inv: InventoryManager = Depends(inventory)):
    """Upload sales recorded while offline. Safe to retry: each client_ref is applied once."""
    results = []
    for s in body.sales:
        try:
            sale = inv.record_sale([LineRequest(i.sku, i.quantity) for i in s.items], channel="offline",
                                   cashier_id=user.id, payment_method=s.payment_method,
                                   client_ref=s.client_ref, offline=True, sold_at=s.sold_at)
            results.append({"client_ref": s.client_ref, "status": "ok", "sale_id": sale.id})
        except InventoryError as exc:
            results.append({"client_ref": s.client_ref, "status": "error", "error": str(exc)})
    return {"results": results}


@router.get("/sales")
def list_sales(before_id: int | None = None, limit: int = Query(50, ge=1, le=200),
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Sale).options(selectinload(Sale.cashier)).order_by(Sale.id.desc()).limit(limit)
    if before_id:
        stmt = stmt.where(Sale.id < before_id)
    if user.role == Role.CASHIER:               # cashiers see only their own sales
        stmt = stmt.where(Sale.cashier_id == user.id)
    return [{"id": s.id, "number": f"{s.id:06d}", "total": str(s.total), "channel": s.channel,
             "payment_method": s.payment_method, "created_at": s.created_at.isoformat(),
             "cashier": s.cashier.name if s.cashier else None} for s in db.scalars(stmt)]


@router.get("/sales/{sale_id}")
def get_receipt(sale_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sale = _load_sale(db, sale_id)
    if sale is None or (user.role == Role.CASHIER and sale.cashier_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return _receipt(sale, get_profile(db))


# ---------- dashboard ----------
@router.get("/dashboard/summary", dependencies=[Depends(MANAGERS)])
def dashboard(db: Session = Depends(get_db)):
    profile = get_profile(db)
    tz = profile.tz
    local_now = utcnow().astimezone(tz)
    today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start7 = today - timedelta(days=6)
    rows = db.execute(select(Sale.id, Sale.total, Sale.created_at, Sale.payment_method)
                      .where(Sale.created_at >= start7.astimezone(_UTC))).all()
    by_day = {(start7 + timedelta(days=i)).date().isoformat(): Decimal("0") for i in range(7)}
    today_ids, revenue, pay_mix = [], Decimal("0"), {}
    for r in rows:
        created = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=_UTC)
        day = created.astimezone(tz).date().isoformat()
        if day in by_day:
            by_day[day] += Decimal(r.total)
        if created.astimezone(tz) >= today:
            today_ids.append(r.id)
            revenue += Decimal(r.total)
            pay_mix[r.payment_method] = pay_mix.get(r.payment_method, 0) + 1
    top = []
    items_sold = 0
    if today_ids:
        q = (select(Product.sku, Product.name_en, Product.name_ar, func.sum(SaleItem.quantity).label("qty"))
             .join(Product, Product.id == SaleItem.product_id)
             .where(SaleItem.sale_id.in_(today_ids)).group_by(Product.id)
             .order_by(func.sum(SaleItem.quantity).desc()))
        all_rows = db.execute(q).all()
        items_sold = sum(int(r.qty) for r in all_rows)
        top = [{"sku": r.sku, "name_en": r.name_en, "name_ar": r.name_ar, "quantity": int(r.qty)}
               for r in all_rows[:5]]
    low = db.scalar(select(func.count(Product.id)).where(
        Product.is_active.is_(True), Product.stock_qty <= Product.reorder_level))
    unread = db.scalar(select(func.count(Alert.id)).where(Alert.read_at.is_(None)))
    n = len(today_ids)
    return {"currency": profile.currency, "today": {
                "revenue": str(revenue.quantize(CENT)), "sales": n, "items": items_sold,
                "avg_ticket": str((revenue / n).quantize(CENT)) if n else "0.00",
                "payment_mix": pay_mix},
            "last_7_days": [{"date": d, "revenue": str(v.quantize(CENT))} for d, v in by_day.items()],
            "top_today": top, "low_stock": low, "unread_alerts": unread}


# ---------- onboarding / maintenance (owner) ----------
@router.post("/setup/demo-data", dependencies=[Depends(OWNER)])
def demo_data(db: Session = Depends(get_db)):
    begin_write(db)
    if db.scalar(select(func.count(Product.id))):
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Catalog is not empty")
    n = load_demo(db)
    db.commit()
    return {"created": n}


@router.get("/system/backups", dependencies=[Depends(OWNER)])
def list_backups(request: Request):
    return request.app.state.backups.list()


@router.post("/system/backups", status_code=201, dependencies=[Depends(OWNER)])
async def create_backup(request: Request):
    try:
        path = await run_in_threadpool(request.app.state.backups.backup_now)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"name": path.name}


@router.get("/system/backups/{name}", dependencies=[Depends(OWNER)])
def download_backup(name: str, request: Request):
    path = request.app.state.backups.path_for(name)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return FileResponse(path, media_type="application/vnd.sqlite3", filename=name)

