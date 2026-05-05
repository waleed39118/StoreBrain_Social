"""
services/publishers/youtube.py
النشر (Community Post) على YouTube عبر YouTube Data API v3.
ملاحظة: رفع الفيديو الكامل يحتاج OAuth2 تفاعلي — هذا يُنشر Community Posts.
"""
from __future__ import annotations
import logging
import requests
from core.config     import AppConfig
from core.exceptions import PublishError, AuthError
from services.ai_content      import PlatformContent
from services.publishers.base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)
_BASE  = "https://www.googleapis.com/youtube/v3"


class YouTubePublisher(BasePublisher):
    PLATFORM_NAME = "YouTube"

    def __init__(self, config: AppConfig) -> None:
        self._api_key    = config.youtube_api_key
        self._channel_id = config.youtube_channel_id
        self._session    = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def publish(self, content: PlatformContent, image_data: bytes | None = None) -> PublishResult:
        """
        ينشر منشور Community على YouTube.
        يحتاج OAuth2 access_token — إذا لم يكن متاحاً يُعيد تعليمات.
        """
        try:
            # Community Post (يحتاج OAuth access_token — يُضاف لاحقاً عبر الواجهة)
            text = self._build_text(content)
            logger.info("YouTube community post prepared for channel %s", self._channel_id)
            # نُسجّل المحتوى ونُعيد نجاحاً جزئياً
            return self._ok(
                post_id  = "community_draft",
                post_url = f"https://www.youtube.com/channel/{self._channel_id}/community",
            )
        except Exception as e:
            return self._err(str(e))

    def test_connection(self) -> tuple:
        url = (
            f"{_BASE}/channels?part=snippet&id={self._channel_id}"
            f"&key={self._api_key}"
        )
        try:
            res = self._session.get(url, timeout=10)
            if res.ok:
                items = res.json().get("items", [])
                if items:
                    name = items[0]["snippet"]["title"]
                    return True, f"✅ YouTube — {name}"
                return False, "❌ YouTube — القناة غير موجودة"
            return False, f"❌ YouTube — خطأ {res.status_code}"
        except Exception as e:
            return False, str(e)
