"""
services/publishers/base.py — الواجهة الأساسية لكل publishers
"""
from __future__ import annotations
from abc        import ABC, abstractmethod
from dataclasses import dataclass
from services.ai_content import PlatformContent


@dataclass
class PublishResult:
    platform: str
    success:  bool
    post_id:  str = ""
    post_url: str = ""
    error:    str = ""

    def __str__(self) -> str:
        if self.success:
            return f"✅ {self.platform} — ID: {self.post_id}"
        return f"❌ {self.platform} — {self.error}"


class BasePublisher(ABC):
    PLATFORM_NAME: str = "Unknown"

    @abstractmethod
    def publish(self, content: PlatformContent, image_data: bytes | None = None) -> PublishResult: ...

    @abstractmethod
    def test_connection(self) -> tuple: ...

    def _build_text(self, content: PlatformContent) -> str:
        parts = [content.caption]
        if content.hashtags:
            parts.append(" ".join(f"#{h.strip('#')}" for h in content.hashtags))
        if content.cta_url:
            parts.append(content.cta_url)
        return "\n\n".join(p for p in parts if p)

    def _ok(self, post_id: str = "", post_url: str = "") -> PublishResult:
        return PublishResult(platform=self.PLATFORM_NAME, success=True,
                             post_id=post_id, post_url=post_url)

    def _err(self, error: str) -> PublishResult:
        return PublishResult(platform=self.PLATFORM_NAME, success=False, error=error)
