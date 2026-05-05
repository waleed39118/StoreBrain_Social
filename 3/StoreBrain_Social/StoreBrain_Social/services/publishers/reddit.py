"""
services/publishers/reddit.py — النشر على Reddit عبر OAuth2
"""
from __future__ import annotations
import logging
import requests
from core.config     import AppConfig
from core.exceptions import PublishError, AuthError, RateLimitError
from services.ai_content      import PlatformContent
from services.publishers.base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)
_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_API_URL   = "https://oauth.reddit.com"


class RedditPublisher(BasePublisher):
    PLATFORM_NAME = "Reddit"

    def __init__(self, config: AppConfig) -> None:
        self._client_id     = config.reddit_client_id
        self._client_secret = config.reddit_client_secret
        self._username      = config.reddit_username
        self._password      = config.reddit_password
        self._subreddits    = [s.strip() for s in (config.reddit_subreddits or "ecommerce").split(",") if s.strip()]
        self._token: str    = ""
        self._session       = requests.Session()
        self._session.headers["User-Agent"] = f"StoreBrainSocial/1.0 by {self._username}"

    def publish(self, content: PlatformContent, image_data: bytes | None = None) -> PublishResult:
        try:
            if not self._token:
                self._authenticate()
            sr  = self._subreddits[0] if self._subreddits else "ecommerce"
            res = self._session.post(
                f"{_API_URL}/api/submit",
                headers={"Authorization": f"Bearer {self._token}"},
                data={
                    "sr": sr, "kind": "self",
                    "title": content.title[:300],
                    "text":  self._build_text(content)[:40000],
                    "nsfw":  False,
                },
                timeout=20,
            )
            if res.status_code == 401:
                raise AuthError(self.PLATFORM_NAME)
            if res.status_code == 429:
                raise RateLimitError(self.PLATFORM_NAME)
            if not res.ok:
                raise PublishError(self.PLATFORM_NAME, res.text[:150], res.status_code)
            return self._ok()
        except (AuthError, RateLimitError, PublishError):
            raise
        except Exception as e:
            return self._err(str(e))

    def _authenticate(self) -> None:
        res = requests.post(
            _TOKEN_URL,
            auth=(self._client_id, self._client_secret),
            data={"grant_type": "password", "username": self._username, "password": self._password},
            headers={"User-Agent": self._session.headers["User-Agent"]},
            timeout=10,
        )
        if not res.ok:
            raise AuthError(self.PLATFORM_NAME)
        self._token = res.json().get("access_token", "")

    def test_connection(self) -> tuple:
        try:
            if not self._token:
                self._authenticate()
            res = self._session.get(f"{_API_URL}/api/v1/me",
                                    headers={"Authorization": f"Bearer {self._token}"}, timeout=8)
            if res.ok:
                return True, f"✅ Reddit — u/{res.json().get('name','')}"
            return False, f"❌ Reddit — خطأ {res.status_code}"
        except Exception as e:
            return False, str(e)
