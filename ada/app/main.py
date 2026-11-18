"""Ada application entrypoint.  Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth_routes import auth_router, gateway_router, notif_router, users_router
from app.api.routes import machine_router, router
from app.config import get_settings
from app.core.auto_updater import AutoUpdater
from app.core.voice_engine import VoiceEngine
from app.database import init_db
from app.services.sms import build_sender

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


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
    app.state.updater.start()
    yield
    await app.state.updater.stop()


app = FastAPI(title="Ada — Smart Store Assistant", version="1.0.0", lifespan=lifespan)
for r in (auth_router, users_router, notif_router, gateway_router, router, machine_router):
    app.include_router(r)


@app.get("/health")
def health():
    return {"status": "ok"}
