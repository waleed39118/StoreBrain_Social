"""Pydantic request/response contracts."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models import ProductCondition


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
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
