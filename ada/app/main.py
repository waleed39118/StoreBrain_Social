"""Ada application entrypoint.  Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.core.auto_updater import AutoUpdater
from app.core.voice_engine import VoiceEngine
from app.database import init_db
from app.services.telegram_notifier import TelegramNotifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    app.state.settings = settings
    app.state.notifier = TelegramNotifier(settings)
    app.state.voice = VoiceEngine(settings)
    app.state.updater = AutoUpdater(settings)
    app.state.updater.start()
    yield
    await app.state.updater.stop()


app = FastAPI(title="Ada — Smart Store Assistant", version="1.0.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
