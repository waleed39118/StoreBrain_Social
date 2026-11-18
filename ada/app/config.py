"""Centralised, typed configuration loaded from environment / .env (prefix ``ADA_``)."""
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADA_", env_file=".env", extra="ignore")

    app_name: str = "Ada"
    api_docs: bool = False                  # expose /docs (OpenAPI) — keep off in production
    max_request_bytes: int = 12 * 1024 * 1024
    database_url: str = "sqlite:///./data/ada.db"
    # ---- Authentication (owner phone + SMS OTP; staff phone + PIN) ----
    # The ONLY number allowed to become/sign in as owner. E.164 or local format.
    owner_phone: str = ""
    owner_name: str = "Owner"
    default_country_code: str = "966"       # used for local numbers starting with 0
    # Server secret for hashing OTPs/tokens. REQUIRED: generate with `python -c
    # "import secrets;print(secrets.token_urlsafe(48))"`. Rotating it logs everyone out.
    auth_secret: SecretStr = SecretStr("")
    session_days: int = Field(30, ge=1, le=365)
    otp_ttl_sec: int = Field(300, ge=60, le=900)
    otp_max_attempts: int = Field(5, ge=1, le=10)
    otp_resend_cooldown_sec: int = Field(60, ge=10)
    otp_max_per_hour: int = Field(5, ge=1)
    pin_max_attempts: int = Field(5, ge=1)
    pin_lockout_min: int = Field(15, ge=1)

    # ---- SMS delivery (no third party unless the owner configures one) ----
    # outbox : an Android phone (SIM) pulls queued SMS from this server and sends them.
    # http   : an SMS provider the owner explicitly authorises (generic JSON POST).
    # console: development only — logs the message.
    sms_provider: str = Field("outbox", pattern="^(outbox|http|console)$")
    sms_gateway_token: SecretStr = SecretStr("")   # auth for the Android gateway device
    sms_http_url: str = ""
    sms_http_token: SecretStr = SecretStr("")

    # Public HTTPS URL of this server (shown in the SMS-phone pairing QR). Optional.
    public_url: str = ""

    # Automatic local backups (SQLite VACUUM INTO)
    backup_dir: str = "./data/backups"
    backup_keep: int = Field(14, ge=1, le=365)
    backup_interval_hours: int = Field(24, ge=1)

    # ---- Local AI (runs on this server via Ollama; never a cloud API) ----
    llm_enabled: bool = False
    llm_url: str = "http://ollama:11434"     # must be loopback/private/compose-internal host
    llm_model: str = "qwen2.5:3b"            # good Arabic+English on CPU; 7b on larger servers
    llm_timeout_sec: float = Field(12.0, ge=1, le=60)

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
