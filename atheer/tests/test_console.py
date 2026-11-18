from __future__ import annotations

import io
import sys

from atheer.core.console import configure_console


def test_arabic_and_emoji_never_crash_on_legacy_code_page(monkeypatch):
    raw = io.BytesIO()
    legacy = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")  # e.g. an old Windows console
    monkeypatch.setattr(sys, "stdout", legacy)
    configure_console()
    print("🔊 أثير جاهزة للخدمة")
    sys.stdout.flush()
    assert "أثير".encode() in raw.getvalue()
