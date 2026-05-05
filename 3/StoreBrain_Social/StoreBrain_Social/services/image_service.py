"""
services/image_service.py
توليد وتحضير الصور الإعلانية بأبعاد كل منصة.
"""
from __future__ import annotations
import logging
import urllib.parse
from pathlib import Path
import requests

logger = logging.getLogger(__name__)

PLATFORM_SIZES: dict[str, tuple] = {
    "Facebook":  (1200, 628),
    "Instagram": (1080, 1080),
    "Pinterest": (1000, 1500),
    "LinkedIn":  (1200, 628),
    "Telegram":  (1280, 720),
    "Twitter":   (1600, 900),
    "Reddit":    (1200, 628),
    "YouTube":   (1280, 720),
    "default":   (1080, 1080),
}

_SAVE_DIR = Path.home() / ".storebrain_social" / "images"


class ImageService:
    def __init__(self) -> None:
        _SAVE_DIR.mkdir(parents=True, exist_ok=True)
        self._session = requests.Session()
        self._session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

    def get_image_bytes(
        self,
        product_title: str,
        platform: str,
        source_url: str = "",
    ) -> bytes | None:
        """يجلب bytes صورة جاهزة للنشر — من Shopify أو Pollinations AI."""
        if source_url:
            data = self._download(source_url)
            if data:
                self._save(product_title, platform, data)
                return data
        w, h = PLATFORM_SIZES.get(platform, PLATFORM_SIZES["default"])
        return self._pollinations(product_title, w, h)

    def get_image_path(self, product_title: str, platform: str, source_url: str = "") -> Path | None:
        data = self.get_image_bytes(product_title, platform, source_url)
        if not data:
            return None
        return self._save(product_title, platform, data)

    def _download(self, url: str) -> bytes | None:
        try:
            res = self._session.get(url, timeout=25)
            res.raise_for_status()
            if "image" not in res.headers.get("Content-Type", ""):
                return None
            return res.content
        except Exception as e:
            logger.warning("Image download failed: %s", e)
            return None

    def _pollinations(self, title: str, w: int, h: int) -> bytes | None:
        prompt  = (
            f"Professional commercial product photography of {title[:60]}, "
            "pure white studio background, perfect lighting, ultra-sharp, 8k, "
            "e-commerce ready, no text, no watermark"
        )
        encoded = urllib.parse.quote(prompt)
        url     = f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&nologo=true"
        try:
            res = self._session.get(url, timeout=50)
            res.raise_for_status()
            return res.content
        except Exception as e:
            logger.error("Pollinations failed: %s", e)
            return None

    def _save(self, title: str, platform: str, data: bytes) -> Path:
        safe  = "".join(c for c in title if c.isalnum() or c == " ").strip()[:35]
        fname = f"{safe}_{platform}.jpg".replace(" ", "_")
        path  = _SAVE_DIR / fname
        path.write_bytes(data)
        return path

    @property
    def save_directory(self) -> Path:
        return _SAVE_DIR
