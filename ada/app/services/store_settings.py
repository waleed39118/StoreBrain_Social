"""Typed store profile persisted as JSON in ``store_settings`` (no migration per new key)."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.models import StoreSetting

PROFILE_KEY = "store.profile"


class StoreProfile(BaseModel):
    store_name: str = Field("متجري", min_length=1, max_length=100)
    store_phone: str = Field("", max_length=24)
    address: str = Field("", max_length=200)
    tax_number: str = Field("", max_length=40)        # VAT registration no. (printed on receipt)
    currency: str = Field("SAR", pattern=r"^[A-Z]{3}$")
    tax_rate: float = Field(15.0, ge=0, le=100)       # percent
    prices_include_tax: bool = True
    timezone: str = "Asia/Riyadh"
    language: str = Field("ar", pattern="^(ar|en)$")
    receipt_footer: str = Field("شكراً لزيارتكم • Thank you!", max_length=200)
    setup_completed: bool = False

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        if v not in available_timezones():
            raise ValueError("Unknown timezone")
        return v

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def get_value(db: Session, key: str, default=None):
    row = db.get(StoreSetting, key)
    return json.loads(row.value) if row else default


def set_value(db: Session, key: str, value) -> None:
    """Caller commits. Upsert by primary key."""
    row = db.get(StoreSetting, key)
    data = json.dumps(value, ensure_ascii=False, default=_json_default)
    if row:
        row.value = data
    else:
        db.add(StoreSetting(key=key, value=data))


def get_profile(db: Session) -> StoreProfile:
    return StoreProfile(**get_value(db, PROFILE_KEY, {}))


def save_profile(db: Session, profile: StoreProfile) -> None:
    set_value(db, PROFILE_KEY, profile.model_dump())


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(type(o))
