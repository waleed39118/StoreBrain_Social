"""
services/publishers/telegram.py — النشر على Telegram Channel
"""
from __future__ import annotations
import logging
import requests
from core.config     import AppConfig
from core.exceptions import PublishError, AuthError
from services.ai_content      import PlatformContent
from services.publishers.base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class TelegramPublisher(BasePublisher):
    PLATFORM_NAME = "Telegram"

    def __init__(self, config: AppConfig) -> None:
        self._token      = config.telegram_bot_token
        self._channel_id = config.telegram_channel_id
        self._base       = f"https://api.telegram.org/bot{self._token}"
        self._session    = requests.Session()

    def publish(self, content: PlatformContent, image_data: bytes | None = None) -> PublishResult:
        try:
            text = self._build_text(content)
            if image_data:
                res = self._session.post(
                    f"{self._base}/sendPhoto",
                    data={"chat_id": self._channel_id, "caption": text[:1024], "parse_mode": "HTML"},
                    files={"photo": ("product.jpg", image_data, "image/jpeg")},
                    timeout=30,
                )
            else:
                res = self._session.post(
                    f"{self._base}/sendMessage",
                    json={"chat_id": self._channel_id, "text": text[:4096], "parse_mode": "HTML"},
                    timeout=15,
                )
            if res.status_code == 401:
                raise AuthError(self.PLATFORM_NAME)
            if not res.ok:
                raise PublishError(self.PLATFORM_NAME, res.json().get("description", "")[:150])
            msg_id = str(res.json().get("result", {}).get("message_id", ""))
            return self._ok(post_id=msg_id)
        except (AuthError, PublishError):
            raise
        except Exception as e:
            return self._err(str(e))

    def test_connection(self) -> tuple:
        try:
            res = self._session.get(f"{self._base}/getMe", timeout=8)
            if res.ok:
                name = res.json().get("result", {}).get("username", "")
                return True, f"✅ Telegram — @{name}"
            return False, f"❌ Telegram — خطأ {res.status_code}"
        except Exception as e:
            return False, str(e)
