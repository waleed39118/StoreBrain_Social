"""Application settings loaded from environment variables (prefix ``ATHEER_``) or ``.env``."""

from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ATHEER_", env_file=".env", extra="ignore")

    clinic_name: str = "Atheer Clinic"
    clinic_timezone: str = "UTC"

    database_url: str = "sqlite:///./atheer.db"
    database_echo: bool = False

    default_slot_minutes: int = Field(default=15, ge=5, le=240)
    late_grace_minutes: int = Field(default=10, ge=0, le=120)
    reminder_lead_hours: int = Field(default=24, ge=1, le=168)

    @field_validator("clinic_timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown IANA timezone: {value!r}") from exc
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.clinic_timezone)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
