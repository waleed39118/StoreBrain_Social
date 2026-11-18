"""Pydantic request/response contracts."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.barcode import normalize_barcode
from app.models import ProductCondition


def _clean_barcode(v):
    return normalize_barcode(v)


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    barcode: str | None = None
    name_en: str = Field(min_length=1, max_length=200)
    name_ar: str | None = Field(None, max_length=200)
    category: str = "general"
    price: Decimal = Field(ge=0)
    cost: Decimal | None = Field(None, ge=0)
    stock_qty: int = Field(0, ge=0)
    reorder_level: int = Field(5, ge=0)
    lead_time_days: int = Field(3, ge=0)
    condition: ProductCondition = ProductCondition.NEW
    expiry_date: date | None = None

    _barcode = field_validator("barcode", mode="before")(_clean_barcode)


class ProductUpdate(BaseModel):
    """Partial manual edit; only provided fields change. Stock changes go via restock/sales."""
    barcode: str | None = None
    name_en: str | None = Field(None, min_length=1, max_length=200)
    name_ar: str | None = Field(None, max_length=200)
    category: str | None = Field(None, max_length=100)
    price: Decimal | None = Field(None, ge=0)
    cost: Decimal | None = Field(None, ge=0)
    reorder_level: int | None = Field(None, ge=0)
    lead_time_days: int | None = Field(None, ge=0)
    condition: ProductCondition | None = None
    expiry_date: date | None = None
    is_active: bool | None = None

    _barcode = field_validator("barcode", mode="before")(_clean_barcode)


class ImportReportOut(BaseModel):
    total_rows: int
    created: int
    updated: int
    skipped: int
    applied: bool
    dry_run: bool
    unknown_columns: list[str]
    errors: list[dict]


class ProductOut(ProductIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool


class SaleLineIn(BaseModel):
    sku: str
    quantity: int = Field(gt=0, le=10_000)


class SaleIn(BaseModel):
    items: list[SaleLineIn] = Field(min_length=1, max_length=200)


class SaleOut(BaseModel):
    sale_id: int
    total: Decimal


class RestockIn(BaseModel):
    quantity: int = Field(gt=0, le=1_000_000)
    ref: str | None = Field(None, max_length=100)


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    language: str | None = Field(None, pattern="^(ar|en)$")
    speak: bool = False


class ChatOut(BaseModel):
    reply: str
    language: str
    intent: str
    data: dict | list | None = None
    transcript: str | None = None
    audio_url: str | None = None


# ---------- auth ----------
class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=6, max_length=24)


class OtpVerifyIn(OtpRequestIn):
    code: str = Field(pattern=r"^\d{6}$")
    device_name: str = Field("device", max_length=100)


class PinLoginIn(OtpRequestIn):
    pin: str = Field(pattern=r"^\d{4,8}$")
    device_name: str = Field("device", max_length=100)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    phone: str
    name: str
    role: str
    is_active: bool


class LoginOut(BaseModel):
    token: str
    expires_at: datetime
    user: UserOut


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_name: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool = False


class StaffIn(BaseModel):
    phone: str = Field(min_length=6, max_length=24)
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(pattern="^(manager|cashier)$")
    pin: str = Field(pattern=r"^\d{4,8}$")


class StaffUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    role: str | None = Field(None, pattern="^(manager|cashier)$")
    pin: str | None = Field(None, pattern=r"^\d{4,8}$")
    is_active: bool | None = None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    key: str
    message: str
    created_at: datetime
    read_at: datetime | None


class GatewayMessageOut(BaseModel):
    id: int
    phone: str
    body: str


class GatewayAckIn(BaseModel):
    ok: bool
    error: str | None = Field(None, max_length=200)
