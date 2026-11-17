"""Staff authentication: a shared API key in the ``X-API-Key`` header.

Public endpoints (kiosk, lobby chat, ticket issue, wait time) need no key.
Staff endpoints are disabled entirely (503) until ``ATHEER_STAFF_API_KEY`` is set,
so a fresh install never exposes them by accident.
"""

from __future__ import annotations

import hmac
import threading
import time
from collections import deque

from fastapi import HTTPException, Request, Security, WebSocket, status
from fastapi.security import APIKeyHeader

HEADER = "X-API-Key"
# Declared as a security scheme so /docs shows an "Authorize" button for staff endpoints.
api_key_header = APIKeyHeader(name=HEADER, auto_error=False, description="Staff API key (ATHEER_STAFF_API_KEY)")


def is_staff(connection: Request | WebSocket) -> bool:
    expected = connection.app.state.atheer.settings.staff_api_key
    supplied = connection.headers.get(HEADER)
    if expected is None or not supplied:
        return False
    return hmac.compare_digest(supplied.encode(), expected.get_secret_value().encode())


def require_staff(request: Request, _key: str | None = Security(api_key_header)) -> None:
    if request.app.state.atheer.settings.staff_api_key is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Staff API disabled: set ATHEER_STAFF_API_KEY.")
    if not is_staff(request):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Missing or invalid {HEADER} header.")


class FailureLimiter:
    """Blocks a client after too many failed attempts in a sliding window (e.g. kiosk check-in guessing).

    In-memory and per process: enough for a single clinic server. Behind several
    workers or a load balancer, enforce the limit at the reverse proxy instead.
    """

    def __init__(self, max_failures: int = 5, window_seconds: float = 300.0) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, client: str, now: float) -> deque[float]:
        hits = self._failures.setdefault(client, deque())
        while hits and now - hits[0] > self.window:
            hits.popleft()
        return hits

    def blocked(self, client: str) -> bool:
        with self._lock:
            return len(self._recent(client, time.monotonic())) >= self.max_failures

    def fail(self, client: str) -> None:
        with self._lock:
            self._recent(client, time.monotonic()).append(time.monotonic())
            if len(self._failures) > 10_000:  # bound memory under a scan from many addresses
                self._failures = {k: v for k, v in self._failures.items() if v}
