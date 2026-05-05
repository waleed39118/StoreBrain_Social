"""
services/publishers/twitter.py — النشر على Twitter/X عبر API v2
"""
from __future__ import annotations
import base64
import logging
import requests
from core.config     import AppConfig
from core.exceptions import PublishError, AuthError, RateLimitError
from services.ai_content      import PlatformContent
from services.publishers.base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class TwitterPublisher(BasePublisher):
    PLATFORM_NAME = "Twitter"

    def __init__(self, config: AppConfig) -> None:
        from requests_oauthlib import OAuth1
        self._auth = OAuth1(
            config.twitter_api_key,    config.twitter_api_secret,
            config.twitter_access_token, config.twitter_access_secret,
        )

    def publish(self, content: PlatformContent, image_data: bytes | None = None) -> PublishResult:
        try:
            payload: dict = {"text": self._build_text(content)[:280]}
            if image_data:
                mid = self._upload_media(image_data)
                if mid:
                    payload["media"] = {"media_ids": [mid]}
            res = requests.post("https://api.twitter.com/2/tweets",
                                json=payload, auth=self._auth, timeout=20)
            if res.status_code == 401:
                raise AuthError(self.PLATFORM_NAME)
            if res.status_code == 429:
                raise RateLimitError(self.PLATFORM_NAME)
            if res.status_code not in (200, 201):
                raise PublishError(self.PLATFORM_NAME, res.text[:150], res.status_code)
            tid = res.json().get("data", {}).get("id", "")
            return self._ok(post_id=tid, post_url=f"https://twitter.com/i/web/status/{tid}")
        except (AuthError, RateLimitError, PublishError):
            raise
        except Exception as e:
            return self._err(str(e))

    def _upload_media(self, image_data: bytes) -> str | None:
        try:
            b64 = base64.b64encode(image_data).decode()
            res = requests.post(
                "https://upload.twitter.com/1.1/media/upload.json",
                data={"media_data": b64}, auth=self._auth, timeout=30,
            )
            return str(res.json().get("media_id", "")) if res.ok else None
        except Exception:
            return None

    def test_connection(self) -> tuple:
        try:
            res = requests.get("https://api.twitter.com/2/users/me",
                               auth=self._auth, timeout=8)
            if res.ok:
                return True, f"✅ Twitter — @{res.json().get('data',{}).get('username','')}"
            return False, f"❌ Twitter — خطأ {res.status_code}"
        except Exception as e:
            return False, str(e)
