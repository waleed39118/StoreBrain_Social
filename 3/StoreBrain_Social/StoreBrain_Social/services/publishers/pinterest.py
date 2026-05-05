"""
services/publishers/pinterest.py — النشر على Pinterest عبر API v5
"""
from __future__ import annotations
import base64
import logging
import urllib.parse
import requests
from core.config     import AppConfig
from core.exceptions import PublishError, AuthError, RateLimitError
from services.ai_content      import PlatformContent
from services.publishers.base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)
_BASE  = "https://api.pinterest.com/v5"


class PinterestPublisher(BasePublisher):
    PLATFORM_NAME = "Pinterest"

    def __init__(self, config: AppConfig) -> None:
        self._board_id = config.pinterest_board_id
        self._session  = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {config.pinterest_token}",
            "Content-Type":  "application/json",
        })

    def publish(self, content: PlatformContent, image_data: bytes | None = None) -> PublishResult:
        try:
            if image_data:
                media_src = {
                    "source_type":  "image_base64",
                    "content_type": "image/jpeg",
                    "data":         base64.b64encode(image_data).decode(),
                }
            else:
                prompt    = urllib.parse.quote(f"product photography {content.title[:40]}")
                media_src = {
                    "source_type": "image_url",
                    "url": f"https://image.pollinations.ai/prompt/{prompt}?width=1000&height=1500&nologo=true",
                }
            payload = {
                "board_id":    self._board_id,
                "title":       content.title[:100],
                "description": content.caption[:500],
                "link":        content.cta_url,
                "media_source": media_src,
            }
            res = self._session.post(f"{_BASE}/pins", json=payload, timeout=35)
            if res.status_code == 401:
                raise AuthError(self.PLATFORM_NAME)
            if res.status_code == 429:
                raise RateLimitError(self.PLATFORM_NAME)
            if res.status_code not in (200, 201):
                raise PublishError(self.PLATFORM_NAME, res.text[:150], res.status_code)
            pin_id = res.json().get("id", "")
            return self._ok(post_id=pin_id, post_url=f"https://www.pinterest.com/pin/{pin_id}/")
        except (AuthError, RateLimitError, PublishError):
            raise
        except Exception as e:
            return self._err(str(e))

    def test_connection(self) -> tuple:
        try:
            res = self._session.get(f"{_BASE}/user_account", timeout=8)
            if res.ok:
                return True, f"✅ Pinterest — @{res.json().get('username','')}"
            return False, f"❌ Pinterest — خطأ {res.status_code}"
        except Exception as e:
            return False, str(e)
