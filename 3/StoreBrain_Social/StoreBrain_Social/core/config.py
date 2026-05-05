"""
core/config.py — محمّل الإعدادات المركزي
نقطة الحقيقة الوحيدة لكل مفاتيح API في النظام.
"""
from __future__ import annotations
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv
from core.exceptions import MissingKeyError, ConfigError

BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent.parent
ENV_PATH = BASE_DIR / ".env"


def _get(key: str, required: bool = True, default: str = "") -> str:
    raw = os.getenv(key, default)
    if raw:
        raw = raw.strip().strip('"').strip("'")
    if required and not raw:
        raise MissingKeyError(key)
    return raw or default


@dataclass(frozen=True)
class AppConfig:
    # Shopify
    shopify_token: str
    shop_url:      str
    # Groq AI
    groq_api_key:  str
    # Facebook / Instagram
    meta_page_id:         str = ""
    meta_page_token:      str = ""
    meta_app_id:          str = ""
    meta_app_secret:      str = ""
    instagram_account_id: str = ""
    # Pinterest
    pinterest_token:    str = ""
    pinterest_board_id: str = ""
    # LinkedIn
    linkedin_token:  str = ""
    linkedin_org_id: str = ""
    # Telegram
    telegram_bot_token:  str = ""
    telegram_channel_id: str = ""
    # Twitter/X
    twitter_api_key:       str = ""
    twitter_api_secret:    str = ""
    twitter_access_token:  str = ""
    twitter_access_secret: str = ""
    # Reddit
    reddit_client_id:     str = ""
    reddit_client_secret: str = ""
    reddit_username:      str = ""
    reddit_password:      str = ""
    reddit_subreddits:    str = ""
    # YouTube
    youtube_api_key:    str = ""
    youtube_channel_id: str = ""
    # Stability AI (اختياري)
    stability_api_key: str = ""
    # ثوابت
    shopify_api_version: str = field(default="2025-01", init=False, compare=False)
    groq_primary_model:  str = field(default="llama-3.3-70b-versatile", init=False, compare=False)
    groq_fallback_model: str = field(default="llama-3.1-8b-instant",    init=False, compare=False)
    base_dir: Path = field(default=BASE_DIR, init=False, compare=False)

    @property
    def clean_shop_url(self) -> str:
        return self.shop_url.replace("https://", "").replace("http://", "").rstrip("/")

    @property
    def shopify_products_endpoint(self) -> str:
        return f"https://{self.clean_shop_url}/admin/api/{self.shopify_api_version}/products.json"

    @property
    def has_facebook(self)  -> bool: return bool(self.meta_page_id and self.meta_page_token)
    @property
    def has_instagram(self) -> bool: return bool(self.instagram_account_id and self.meta_page_token)
    @property
    def has_pinterest(self) -> bool: return bool(self.pinterest_token and self.pinterest_board_id)
    @property
    def has_linkedin(self)  -> bool: return bool(self.linkedin_token and self.linkedin_org_id)
    @property
    def has_telegram(self)  -> bool: return bool(self.telegram_bot_token and self.telegram_channel_id)
    @property
    def has_twitter(self)   -> bool: return bool(self.twitter_api_key and self.twitter_access_token)
    @property
    def has_reddit(self)    -> bool: return bool(self.reddit_client_id and self.reddit_username)
    @property
    def has_youtube(self)   -> bool: return bool(self.youtube_api_key and self.youtube_channel_id)

    def active_platforms(self) -> list[str]:
        mapping = [
            ("Facebook",  self.has_facebook),
            ("Instagram", self.has_instagram),
            ("Pinterest", self.has_pinterest),
            ("LinkedIn",  self.has_linkedin),
            ("Telegram",  self.has_telegram),
            ("Twitter",   self.has_twitter),
            ("Reddit",    self.has_reddit),
            ("YouTube",   self.has_youtube),
        ]
        return [name for name, ok in mapping if ok]

    def __repr__(self) -> str:
        return f"AppConfig(shop={self.clean_shop_url}, platforms={self.active_platforms()})"


def load_config() -> AppConfig:
    load_dotenv(ENV_PATH, override=True)
    shop_url = _get("SHOP_URL").replace("https://", "").replace("http://", "").rstrip("/")
    if not shop_url or "." not in shop_url:
        raise ConfigError(f"SHOP_URL غير صالح: {shop_url}")
    return AppConfig(
        shopify_token        = _get("SHOPIFY_API_TOKEN"),
        shop_url             = shop_url,
        groq_api_key         = _get("GROQ_API_KEY"),
        meta_page_id         = _get("META_PAGE_ID",         required=False),
        meta_page_token      = _get("META_PAGE_TOKEN",      required=False),
        meta_app_id          = _get("META_APP_ID",          required=False),
        meta_app_secret      = _get("META_APP_SECRET",      required=False),
        instagram_account_id = _get("INSTAGRAM_ACCOUNT_ID", required=False),
        pinterest_token      = _get("PINTEREST_TOKEN",      required=False),
        pinterest_board_id   = _get("PINTEREST_BOARD_ID",   required=False),
        linkedin_token       = _get("LINKEDIN_TOKEN",       required=False),
        linkedin_org_id      = _get("LINKEDIN_ORG_ID",      required=False),
        telegram_bot_token   = _get("TELEGRAM_BOT_TOKEN",   required=False),
        telegram_channel_id  = _get("TELEGRAM_CHANNEL_ID",  required=False),
        twitter_api_key      = _get("TWITTER_API_KEY",      required=False),
        twitter_api_secret   = _get("TWITTER_API_SECRET",   required=False),
        twitter_access_token = _get("TWITTER_ACCESS_TOKEN", required=False),
        twitter_access_secret= _get("TWITTER_ACCESS_SECRET",required=False),
        reddit_client_id     = _get("REDDIT_CLIENT_ID",     required=False),
        reddit_client_secret = _get("REDDIT_CLIENT_SECRET", required=False),
        reddit_username      = _get("REDDIT_USERNAME",      required=False),
        reddit_password      = _get("REDDIT_PASSWORD",      required=False),
        reddit_subreddits    = _get("REDDIT_SUBREDDITS",    required=False),
        youtube_api_key      = _get("YOUTUBE_API_KEY",      required=False),
        youtube_channel_id   = _get("YOUTUBE_CHANNEL_ID",   required=False),
        stability_api_key    = _get("STABILITY_API_KEY",    required=False),
    )


def is_configured() -> bool:
    if not ENV_PATH.exists():
        return False
    load_dotenv(ENV_PATH, override=True)
    return all(os.getenv(k, "").strip() for k in ["SHOPIFY_API_TOKEN", "SHOP_URL", "GROQ_API_KEY"])


def save_env_values(values: dict) -> None:
    BAD = {"", "ضع_قيمتك_هنا", "your-store.myshopify.com", "shpca_...", "gsk_..."}
    existing: dict[str, str] = {}
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    existing[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in values.items():
        v = str(v).strip().strip('"').strip("'")
        if v and v not in BAD:
            existing[k] = v
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("# StoreBrain Social — ملف الإعدادات (لا ترفعه على GitHub)\n\n")
        for k, v in existing.items():
            f.write(f"{k}={v}\n")
