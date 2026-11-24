"""Serves the built-in web screens: waiting-room display, reception panel and check-in kiosk.

Plain HTML/CSS/JS with no external resources, so the screens work inside a
clinic network without internet.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
PAGES = {"": "index.html", "display": "display.html", "reception": "reception.html", "kiosk": "kiosk.html"}
ASSETS = {"atheer.css": "text/css", "atheer.js": "text/javascript", "logo.svg": "image/svg+xml"}

web = APIRouter(include_in_schema=False)


@web.get("/")
def home() -> FileResponse:
    return FileResponse(WEB_DIR / PAGES[""], media_type="text/html")


@web.get("/display")
def display() -> FileResponse:
    return FileResponse(WEB_DIR / PAGES["display"], media_type="text/html")


@web.get("/reception")
def reception() -> FileResponse:
    return FileResponse(WEB_DIR / PAGES["reception"], media_type="text/html")


@web.get("/kiosk")
def kiosk() -> FileResponse:
    return FileResponse(WEB_DIR / PAGES["kiosk"], media_type="text/html")


@web.get("/ui/{name}")
def asset(name: str) -> FileResponse:
    # Fixed allow-list: no path traversal, no directory listing.
    if name not in ASSETS:
        raise HTTPException(404)
    return FileResponse(WEB_DIR / name, media_type=ASSETS[name])
