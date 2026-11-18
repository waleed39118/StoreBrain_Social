"""Shared FastAPI dependencies: authentication, role checks and service wiring."""
import hmac
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.assistant import AdaAssistant
from app.core.inventory_manager import InventoryManager
from app.core.market_analytics import MarketAnalytics
from app.database import get_db
from app.models import AuthSession, Role, User
from app.services.auth_service import AuthError, AuthService


def auth_service(request: Request, db: Session = Depends(get_db),
                 settings: Settings = Depends(get_settings)) -> AuthService:
    return AuthService(db, settings, request.app.state.sms)


def current_session(authorization: str = Header(default=""),
                    auth: AuthService = Depends(auth_service)) -> tuple[User, AuthSession]:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        return auth.resolve(token)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc),
                            headers={"WWW-Authenticate": "Bearer"}) from exc


def current_user(sess: tuple[User, AuthSession] = Depends(current_session)) -> User:
    return sess[0]


def require_roles(*roles: Role) -> Callable[..., User]:
    def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user
    return checker


ANY_STAFF = require_roles(Role.OWNER, Role.MANAGER, Role.CASHIER)
MANAGERS = require_roles(Role.OWNER, Role.MANAGER)
OWNER = require_roles(Role.OWNER)


def require_gateway(x_gateway_token: str = Header(default=""),
                    settings: Settings = Depends(get_settings)) -> None:
    expected = settings.sms_gateway_token.get_secret_value()
    if len(expected) < 32 or not hmac.compare_digest(x_gateway_token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid gateway token")


def inventory(db: Session = Depends(get_db),
              settings: Settings = Depends(get_settings)) -> InventoryManager:
    return InventoryManager(db, settings)


def analytics(db: Session = Depends(get_db),
              settings: Settings = Depends(get_settings)) -> MarketAnalytics:
    return MarketAnalytics(db, settings)


def assistant(request: Request, inv: InventoryManager = Depends(inventory),
              an: MarketAnalytics = Depends(analytics)) -> AdaAssistant:
    return AdaAssistant(inv, an, request.app.state.llm)
