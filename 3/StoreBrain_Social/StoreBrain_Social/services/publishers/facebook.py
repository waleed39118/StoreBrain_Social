"""
services/publishers/facebook.py — النشر على Facebook عبر Graph API v19
"""
from __future__ import annotations
import logging
import requests
from core.config     import AppConfig
from core.exceptions import PublishError, AuthError, RateLimitError
from services.ai_content      import PlatformContent
from services.publishers.base import BasePublisher, PublishResult

logger  = logging.getLogger(__name__)
_GRAPH  = "https://graph.facebook.com/v19.0"


class FacebookPublisher(BasePublisher):
    PLATFORM_NAME = "Facebook"

    def __init__(self, config: AppConfig) -> None:
        self._page_id = config.meta_page_id
        self._token   = config.meta_page_token
        self._session = requests.Session()

    def publish(self, content: PlatformContent, image_data: bytes | None = None) -> PublishResult:
        try:
            if image_data:
                return self._post_with_photo(content, image_data)
            return self._post_text(content)
        except (AuthError, RateLimitError, PublishError):
            raise
        except Exception as e:
            return self._err(str(e))

    def _post_text(self, content: PlatformContent) -> PublishResult:
        res = self._request(
            f"{_GRAPH}/{self._page_id}/feed",
            {"message": self._build_text(content), "link": content.cta_url,
             "access_token": self._token}
        )
        pid = res.get("id", "")
        return self._ok(post_id=pid, post_url=f"https://www.facebook.com/{pid}")

    def _post_with_photo(self, content: PlatformContent, image_data: bytes) -> PublishResult:
        # رفع الصورة أولاً
        res1 = self._request(
            f"{_GRAPH}/{self._page_id}/photos",
            {"published": False, "access_token": self._token},
            files={"source": ("product.jpg", image_data, "image/jpeg")},
        )
        photo_id = res1.get("id", "")
        if not photo_id:
            return self._post_text(content)
        res2 = self._request(
            f"{_GRAPH}/{self._page_id}/feed",
            {"message": self._build_text(content),
             "attached_media[0]": f'{{"media_fbid":"{photo_id}"}}',
             "access_token": self._token},
        )
        pid = res2.get("id", "")
        return self._ok(post_id=pid, post_url=f"https://www.facebook.com/{pid}")

    def test_connection(self) -> tuple:
        url = f"{_GRAPH}/{self._page_id}?fields=name&access_token={self._token}"
        try:
            res = self._session.get(url, timeout=10)
            if res.ok:
                return True, f"✅ Facebook — صفحة: {res.json().get('name','')}"
            return False, f"❌ Facebook — خطأ {res.status_code}"
        except Exception as e:
            return False, str(e)

    def _request(self, url: str, data: dict, files: dict | None = None) -> dict:
        try:
            res = self._session.post(url, data=data, files=files, timeout=30) if files \
                  else self._session.post(url, data=data, timeout=20)
        except requests.exceptions.Timeout:
            raise PublishError(self.PLATFORM_NAME, "انتهت مهلة الاتصال.")
        except requests.exceptions.ConnectionError:
            raise PublishError(self.PLATFORM_NAME, "لا يوجد اتصال.")
        if res.status_code in (190, 401):
            raise AuthError(self.PLATFORM_NAME)
        if res.status_code == 429:
            raise RateLimitError(self.PLATFORM_NAME)
        if res.status_code not in (200, 201):
            err = res.json().get("error", {}).get("message", res.text[:150])
            raise PublishError(self.PLATFORM_NAME, err, res.status_code)
        return res.json()
