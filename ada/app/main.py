"""Ada application entrypoint.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text

from app import __version__
from app.api.auth_routes import (auth_router, gateway_admin, gateway_router, notif_router,
                                 users_router)
from app.api.pos_routes import router as pos_router
from app.api.routes import machine_router, router
from app.config import get_settings
from app.core.auto_updater import AutoUpdater
from app.core.voice_engine import VoiceEngine
from app.database import engine, init_db
from app.security_middleware import AppShellFiles, SecurityMiddleware
from app.services.backup import BackupService
from app.services.sms import build_sender

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if len(settings.auth_secret.get_secret_value()) < 32:
        raise RuntimeError("ADA_AUTH_SECRET is required (>= 32 chars)")
    if not settings.owner_phone:
        logging.getLogger("ada").warning("ADA_OWNER_PHONE is not set: nobody can sign in as owner")
    init_db()
    app.state.settings = settings
    app.state.sms = build_sender(settings)
    app.state.voice = VoiceEngine(settings)
    app.state.updater = AutoUpdater(settings)
    app.state.backups = BackupService(settings)
    app.state.updater.start()
    app.state.backups.start()
    yield
    await app.state.updater.stop()
    await app.state.backups.stop()


_s = get_settings()
app = FastAPI(title="Ada — Smart Store Assistant", version=__version__, lifespan=lifespan,
              docs_url="/docs" if _s.api_docs else None, redoc_url=None,
              openapi_url="/openapi.json" if _s.api_docs else None)
app.add_middleware(SecurityMiddleware, max_bytes=_s.max_request_bytes)
for r in (auth_router, users_router, notif_router, gateway_router, gateway_admin, pos_router,
          router, machine_router):
    app.include_router(r)


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "version": __version__}


@app.get("/api/v1/version")
def version():
    return {"version": __version__}


if WEB_DIR.is_dir():   # PWA last, so API routes always take precedence
    app.mount("/", AppShellFiles(directory=WEB_DIR, html=True), name="web")
