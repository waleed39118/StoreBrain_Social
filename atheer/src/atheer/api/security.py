"""Staff authentication: a shared API key in the ``X-API-Key`` header.

Public endpoints (kiosk, lobby chat, ticket issue, wait time) need no key.
Staff endpoints are disabled entirely (503) until ``ATHEER_STAFF_API_KEY`` is set,
so a fresh install never exposes them by accident.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, WebSocket, status

HEADER = "X-API-Key"


def is_staff(connection: Request | WebSocket) -> bool:
    expected = connection.app.state.atheer.settings.staff_api_key
    supplied = connection.headers.get(HEADER)
    if expected is None or not supplied:
        return False
    return hmac.compare_digest(supplied.encode(), expected.get_secret_value().encode())


def require_staff(request: Request) -> None:
    if request.app.state.atheer.settings.staff_api_key is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Staff API disabled: set ATHEER_STAFF_API_KEY.")
    if not is_staff(request):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Missing or invalid {HEADER} header.")
