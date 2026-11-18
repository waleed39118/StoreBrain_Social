"""AutoUpdater: zero-downtime background ingestion of signed catalog patches.

Design decision: Ada updates *data* (catalog/prices/policies), never executable code.
Pulling and executing remote code is a supply-chain attack vector; code ships via normal
deploys. Patches are:
  * authenticated   – HMAC-SHA256 over the raw body (header ``X-Ada-Signature``)
  * idempotent      – each ``version`` is applied once (catalog_patches table)
  * atomic          – one DB transaction; a bad item aborts the whole patch
  * non-blocking    – runs as an asyncio task; DB work happens in a worker thread

Patch format::

    {"version": "2026.11.18-1",
     "products": [{"sku": "MILK-1L", "name_en": "Milk 1L", "name_ar": "حليب",
                   "category": "dairy", "price": 1.25, "reorder_level": 10,
                   "stock_delta": 24, "is_active": true}]}
"""
import asyncio
import hashlib
import hmac
import json
import logging
from decimal import Decimal

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from app.config import Settings
from app.database import session_scope
from app.models import CatalogPatch, MovementReason, Product, ProductCondition, StockMovement

log = logging.getLogger("ada.updater")


class PatchItem(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name_en: str | None = Field(None, max_length=200)
    name_ar: str | None = Field(None, max_length=200)
    category: str | None = Field(None, max_length=100)
    price: Decimal | None = Field(None, ge=0)
    cost: Decimal | None = Field(None, ge=0)
    reorder_level: int | None = Field(None, ge=0)
    lead_time_days: int | None = Field(None, ge=0)
    condition: ProductCondition | None = None
    is_active: bool | None = None
    stock_delta: int = 0


class CatalogPatchDoc(BaseModel):
    version: str = Field(min_length=1, max_length=50)
    products: list[PatchItem] = Field(max_length=10_000)


class PatchError(Exception):
    pass


class AutoUpdater:
    _UPDATABLE = ("name_en", "name_ar", "category", "price", "cost", "reorder_level",
                  "lead_time_days", "condition", "is_active")

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.last_status: dict = {"state": "idle"}

    # ---------- lifecycle ----------
    def start(self) -> None:
        if not (self.s.updater_enabled and self.s.updater_url):
            log.info("AutoUpdater disabled")
            return
        if not self.s.updater_hmac_secret.get_secret_value():
            raise RuntimeError("ADA_UPDATER_HMAC_SECRET is required when the updater is enabled")
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="ada-auto-updater")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await asyncio.wait([self._task], timeout=10)

    async def _loop(self) -> None:
        backoff = self.s.updater_interval_sec
        async with httpx.AsyncClient(timeout=30) as client:
            while not self._stop.is_set():
                try:
                    await self.poll_once(client)
                    backoff = self.s.updater_interval_sec
                except Exception as exc:  # keep the loop alive on any failure
                    log.exception("Patch poll failed")
                    self.last_status = {"state": "error", "error": str(exc)}
                    backoff = min(backoff * 2, 6 * 3600)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass

    # ---------- core ----------
    async def poll_once(self, client: httpx.AsyncClient) -> dict:
        r = await client.get(self.s.updater_url)
        if r.status_code == 304:
            return self.last_status
        r.raise_for_status()
        result = await asyncio.to_thread(self.apply_raw, r.content, r.headers.get("X-Ada-Signature", ""))
        self.last_status = {"state": "ok", **result}
        return result

    def verify(self, body: bytes, signature: str) -> None:
        expected = hmac.new(self.s.updater_hmac_secret.get_secret_value().encode(), body,
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature.removeprefix("sha256=")):
            raise PatchError("Invalid patch signature")

    def apply_raw(self, body: bytes, signature: str) -> dict:
        self.verify(body, signature)
        try:
            doc = CatalogPatchDoc.model_validate(json.loads(body))
        except (ValueError, ValidationError) as exc:
            raise PatchError(f"Malformed patch: {exc}") from exc
        return self.apply(doc, hashlib.sha256(body).hexdigest())

    def apply(self, doc: CatalogPatchDoc, digest: str) -> dict:
        with session_scope() as db:
            if db.scalar(select(CatalogPatch.id).where(CatalogPatch.version == doc.version)):
                return {"version": doc.version, "applied": False, "reason": "already_applied"}
            created = updated = 0
            for item in doc.products:
                p = db.scalar(select(Product).where(Product.sku == item.sku))
                fields = item.model_dump(include=set(self._UPDATABLE), exclude_none=True)
                if p is None:
                    if not item.name_en or item.price is None:
                        raise PatchError(f"New SKU {item.sku} needs name_en and price")
                    p = Product(sku=item.sku, stock_qty=0, **fields)
                    db.add(p); db.flush(); created += 1
                else:
                    for k, v in fields.items():
                        setattr(p, k, v)
                    updated += 1
                if item.stock_delta:
                    if p.stock_qty + item.stock_delta < 0:
                        raise PatchError(f"Patch would make stock negative for {item.sku}")
                    p.stock_qty += item.stock_delta
                    db.add(StockMovement(product_id=p.id, delta=item.stock_delta,
                                         reason=MovementReason.PATCH, ref=doc.version))
            db.add(CatalogPatch(version=doc.version, sha256=digest,
                                items_applied=created + updated))
        log.info("Applied patch %s (%d new, %d updated)", doc.version, created, updated)
        return {"version": doc.version, "applied": True, "created": created, "updated": updated}
