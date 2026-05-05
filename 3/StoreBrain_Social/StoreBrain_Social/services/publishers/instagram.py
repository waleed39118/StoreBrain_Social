"""
services/publishers/instagram.py — النشر على Instagram Business عبر Meta Graph API
"""
from __future__ import annotations
import logging
import urllib.parse
import requests
from core.config     import AppConfig
from core.exceptions import PublishError, AuthError, RateLimitError
from services.ai_content      import PlatformContent
from services.publishers.base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)
_GRAPH = "https://graph.facebook.com/v19.0"


class InstagramPublisher(BasePublisher):
    PLATFORM_NAME = "Instagram"

    def __init__(self, config: AppConfig) -> None:
        self._account_id = config.instagram_account_id
        self._token      = config.meta_page_token
        self._session    = requests.Session()

    def publish(self, content: PlatformContent, image_data: bytes | None = None) -> PublishResult:
        try:
            image_url = self._get_image_url(content.title)
            container_url  = f"{_GRAPH}/{self._account_id}/media"
            container_data = {
                "image_url":    image_url,
                "caption":      self._build_text(content)[:2200],
                "access_token": self._token,
            }
            r1 = self._session.post(container_url, data=container_data, timeout=35)
            self._check(r1)
            container_id = r1.json().get("id", "")
            if not container_id:
                raise PublishError(self.PLATFORM_NAME, "فشل إنشاء container.")

            r2 = self._session.post(
                f"{_GRAPH}/{self._account_id}/media_publish",
                data={"creation_id": container_id, "access_token": self._token},
                timeout=20,
            )
            self._check(r2)
            pid = r2.json().get("id", "")
            return self._ok(post_id=pid, post_url=f"https://www.instagram.com/p/{pid}/")
        except (AuthError, RateLimitError, PublishError):
            raise
        except Exception as e:
            return self._err(str(e))

    def _get_image_url(self, title: str) -> str:
        prompt  = f"Professional product photography of {title[:50]}, white background, 8k"
        encoded = urllib.parse.quote(prompt)
        return f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&nologo=true"

    def test_connection(self) -> tuple:
        url = f"{_GRAPH}/{self._account_id}?fields=username&access_token={self._token}"
        try:
            res = self._session.get(url, timeout=10)
            if res.ok:
                return True, f"✅ Instagram — @{res.json().get('username','')}"
            return False, f"❌ Instagram — خطأ {res.status_code}"
        except Exception as e:
            return False, str(e)

    def _check(self, res: requests.Response) -> None:
        if res.status_code in (190, 401):
            raise AuthError(self.PLATFORM_NAME)
        if res.status_code == 429:
            raise RateLimitError(self.PLATFORM_NAME)
        if res.status_code not in (200, 201):
            err = res.json().get("error", {}).get("message", res.text[:150])
            raise PublishError(self.PLATFORM_NAME, err, res.status_code)
