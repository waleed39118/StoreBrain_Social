"""InventoryManager: stock, sales, restocks and in-app low-stock alerting.

Concurrency: stock is decremented with a conditional UPDATE
(``stock_qty = stock_qty - :q WHERE stock_qty >= :q``) so two concurrent sales can never
oversell, without application-level locks.
"""
import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import begin_write
from app.models import Alert, MovementReason, Product, Sale, SaleItem, StockMovement, utcnow

log = logging.getLogger("ada.inventory")


class InventoryError(Exception):
    """Business-rule violation (unknown product, insufficient stock...)."""


@dataclass(frozen=True)
class LineRequest:
    sku: str
    quantity: int


class InventoryManager:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    # ---------- lookup ----------
    def get_by_sku(self, sku: str) -> Product | None:
        return self.db.scalar(select(Product).where(Product.sku == sku))

    def get_by_barcode(self, code: str) -> Product | None:
        return self.db.scalar(select(Product).where(Product.barcode == code))

    def find(self, term: str, limit: int = 5) -> list[Product]:
        """Lookup by exact SKU/barcode or English/Arabic name (case-insensitive substring)."""
        t = f"%{term.strip().lower()}%"
        stmt = (select(Product)
                .where(Product.is_active.is_(True),
                       or_(func.lower(Product.sku) == term.strip().lower(),
                           Product.barcode == term.strip(),
                           func.lower(Product.name_en).like(t),
                           Product.name_ar.like(f"%{term.strip()}%")))
                .order_by(func.length(Product.name_en)).limit(limit))
        return list(self.db.scalars(stmt))

    def low_stock(self) -> list[Product]:
        return list(self.db.scalars(
            select(Product).where(Product.is_active.is_(True),
                                  Product.stock_qty <= Product.reorder_level)
            .order_by(Product.stock_qty)))

    # ---------- mutations ----------
    def record_sale(self, lines: list[LineRequest], channel: str = "api") -> Sale:
        """Atomically record a multi-line sale. Rolls back entirely if any line fails."""
        if not lines:
            raise InventoryError("Sale has no items")
        sale = Sale(channel=channel)
        total = Decimal("0")
        touched: list[Product] = []
        begin_write(self.db)
        try:
            for line in lines:
                if line.quantity <= 0:
                    raise InventoryError(f"Invalid quantity for {line.sku}")
                product = self.get_by_sku(line.sku)
                if product is None or not product.is_active:
                    raise InventoryError(f"Unknown product: {line.sku}")
                res = self.db.execute(
                    update(Product)
                    .where(Product.id == product.id, Product.stock_qty >= line.quantity)
                    .values(stock_qty=Product.stock_qty - line.quantity, updated_at=utcnow()))
                if res.rowcount != 1:
                    self.db.refresh(product)
                    raise InventoryError(
                        f"Insufficient stock for {product.name_en}: {product.stock_qty} left")
                sale.items.append(SaleItem(product_id=product.id, quantity=line.quantity,
                                           unit_price=product.price))
                total += product.price * line.quantity
                self.db.add(StockMovement(product_id=product.id, delta=-line.quantity,
                                          reason=MovementReason.SALE))
                touched.append(product)
            sale.total = total
            self.db.add(sale)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        for p in touched:
            self.db.refresh(p)
        self.check_alerts(touched)
        return sale

    def restock(self, sku: str, quantity: int, ref: str | None = None) -> Product:
        if quantity <= 0:
            raise InventoryError("Restock quantity must be positive")
        begin_write(self.db)
        product = self.get_by_sku(sku)
        if product is None:
            raise InventoryError(f"Unknown product: {sku}")
        self.db.execute(update(Product).where(Product.id == product.id)
                        .values(stock_qty=Product.stock_qty + quantity, updated_at=utcnow()))
        self.db.add(StockMovement(product_id=product.id, delta=quantity,
                                  reason=MovementReason.RESTOCK, ref=ref))
        self.db.commit()
        self.db.refresh(product)
        return product

    # ---------- alerts ----------
    def check_alerts(self, products: list[Product]) -> int:
        """Create in-app low/out-of-stock notifications, deduplicated by a per-SKU cooldown.

        Alerts are shown only inside Ada's app (owner/manager devices); nothing is sent to
        any external service. Returns the number of new alerts."""
        sent = 0
        begin_write(self.db)
        cutoff = utcnow() - timedelta(minutes=self.settings.low_stock_alert_cooldown_min)
        for p in products:
            if p.stock_qty > p.reorder_level:
                continue
            kind = "out_of_stock" if p.stock_qty == 0 else "low_stock"
            recent = self.db.scalar(select(Alert.id).where(
                Alert.kind == kind, Alert.key == p.sku, Alert.created_at >= cutoff).limit(1))
            if recent:
                continue
            msg = (f"⚠️ Ada: {'OUT OF STOCK' if kind == 'out_of_stock' else 'Low stock'} — "
                   f"{p.name_en}{f' / {p.name_ar}' if p.name_ar else ''} (SKU {p.sku}): "
                   f"{p.stock_qty} left, reorder level {p.reorder_level}.")
            self.db.add(Alert(kind=kind, key=p.sku, message=msg))
            sent += 1
        if sent:
            self.db.commit()
        return sent
