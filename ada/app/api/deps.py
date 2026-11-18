"""Shared FastAPI dependencies: auth and per-request service wiring."""
import hmac

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.assistant import AdaAssistant
from app.core.inventory_manager import InventoryManager
from app.core.market_analytics import MarketAnalytics
from app.database import get_db


def require_api_key(x_api_key: str = Header(default=""),
                    settings: Settings = Depends(get_settings)) -> None:
    expected = settings.api_key.get_secret_value()
    if expected and not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")


def inventory(request: Request, db: Session = Depends(get_db),
              settings: Settings = Depends(get_settings)) -> InventoryManager:
    return InventoryManager(db, settings, request.app.state.notifier)


def analytics(db: Session = Depends(get_db),
              settings: Settings = Depends(get_settings)) -> MarketAnalytics:
    return MarketAnalytics(db, settings)


def assistant(inv: InventoryManager = Depends(inventory),
              an: MarketAnalytics = Depends(analytics)) -> AdaAssistant:
    return AdaAssistant(inv, an)
