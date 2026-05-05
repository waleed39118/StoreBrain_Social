"""
services/publishers/linkedin.py — النشر على LinkedIn Organization Page
"""
from __future__ import annotations
import logging
import requests
from core.config     import AppConfig
from core.exceptions import PublishError, AuthError, RateLimitError
from services.ai_content      import PlatformContent
from services.publishers.base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)
_BASE  = "https://api.linkedin.com/v2"


class LinkedInPublisher(BasePublisher):
    PLATFORM_NAME = "LinkedIn"

    def __init__(self, config: AppConfig) -> None:
        self._author  = f"urn:li:organization:{config.linkedin_org_id}"
        self._org_id  = config.linkedin_org_id
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization":               f"Bearer {config.linkedin_token}",
            "Content-Type":                "application/json",
            "X-Restli-Protocol-Version":   "2.0.0",
        })

    def publish(self, content: PlatformContent, image_data: bytes | None = None) -> PublishResult:
        try:
            if image_data:
                asset = self._upload_image(image_data, content.title)
                return self._post_image(content, asset)
            return self._post_text(content)
        except (AuthError, RateLimitError, PublishError):
            raise
        except Exception as e:
            return self._err(str(e))

    def _post_text(self, content: PlatformContent) -> PublishResult:
        payload = {
            "author": self._author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary":   {"text": self._build_text(content)[:3000]},
                    "shareMediaCategory": "ARTICLE",
                    "media": [{"status": "READY", "originalUrl": content.cta_url}],
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        res = self._session.post(f"{_BASE}/ugcPosts", json=payload, timeout=20)
        self._check(res)
        pid = res.headers.get("x-restli-id", "")
        return self._ok(post_id=pid)

    def _upload_image(self, image_data: bytes, title: str) -> str:
        reg = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner":   self._author,
                "serviceRelationships": [{
                    "relationshipType": "OWNER",
                    "identifier":       "urn:li:userGeneratedContent",
                }],
            }
        }
        res = self._session.post(f"{_BASE}/assets?action=registerUpload", json=reg, timeout=20)
        self._check(res)
        val        = res.json().get("value", {})
        upload_url = (val.get("uploadMechanism", {})
                     .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
                     .get("uploadUrl", ""))
        asset      = val.get("asset", "")
        if upload_url:
            self._session.put(upload_url, data=image_data,
                              headers={"Content-Type": "image/jpeg"}, timeout=40)
        return asset

    def _post_image(self, content: PlatformContent, asset: str) -> PublishResult:
        payload = {
            "author": self._author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary":   {"text": self._build_text(content)[:3000]},
                    "shareMediaCategory": "IMAGE",
                    "media": [{"status": "READY", "media": asset,
                               "title": {"text": content.title}}],
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        res = self._session.post(f"{_BASE}/ugcPosts", json=payload, timeout=20)
        self._check(res)
        return self._ok(post_id=res.headers.get("x-restli-id", ""))

    def _check(self, res: requests.Response) -> None:
        if res.status_code == 401:
            raise AuthError(self.PLATFORM_NAME)
        if res.status_code == 429:
            raise RateLimitError(self.PLATFORM_NAME)
        if res.status_code not in (200, 201):
            raise PublishError(self.PLATFORM_NAME, res.text[:150], res.status_code)

    def test_connection(self) -> tuple:
        try:
            res = self._session.get(f"{_BASE}/organizations/{self._org_id}?fields=localizedName", timeout=8)
            if res.ok:
                return True, f"✅ LinkedIn — {res.json().get('localizedName','')}"
            return False, f"❌ LinkedIn — خطأ {res.status_code}"
        except Exception as e:
            return False, str(e)
