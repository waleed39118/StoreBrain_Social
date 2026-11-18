"""Centralised, typed configuration loaded from environment / .env (prefix ``ADA_``)."""
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADA_", env_file=".env", extra="ignore")

    app_name: str = "Ada"
    database_url: str = "sqlite:///./data/ada.db"
    # Simple shared-secret auth for the owner/staff API. Empty => auth disabled (dev only).
    api_key: SecretStr = SecretStr("")

    # Telegram owner alerts
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""

    # Voice
    whisper_model: str = "small"            # tiny|base|small|medium|large-v3
    tts_rate: int = 170
    tts_voice_hint: str = ""                # substring matched against installed voice names/langs
    tts_output_dir: str = "./data/tts"
    max_audio_bytes: int = 10 * 1024 * 1024

    # Inventory / analytics
    low_stock_alert_cooldown_min: int = 360  # don't re-alert the same SKU more often than this
    analytics_window_days: int = 30
    obsolete_after_days: int = 90
    safety_stock_days: int = 7

    # Auto-updater (signed catalog patches)
    updater_enabled: bool = False
    updater_url: str = ""
    updater_hmac_secret: SecretStr = SecretStr("")
    updater_interval_sec: int = Field(900, ge=30)


@lru_cache
def get_settings() -> Settings:
    return Settings()
