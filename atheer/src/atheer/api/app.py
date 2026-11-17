"""FastAPI application factory and server entry point.

    atheer-server                      # uses ATHEER_API_HOST / ATHEER_API_PORT
    open http://127.0.0.1:8000/docs    # interactive API documentation
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from atheer import __version__
from atheer.api.routes import public, staff
from atheer.appointments.exceptions import (
    AppointmentError,
    InvalidTransitionError,
    NotFoundError,
    SchedulingConflictError,
    StaleVersionError,
)
from atheer.calculations.engine import UnknownDrugError
from atheer.core.config import Settings, get_settings
from atheer.runtime import Atheer
from atheer.updater.service import UpdateError

logger = logging.getLogger("atheer.api")


def create_app(settings: Settings | None = None, *, atheer: Atheer | None = None, listen: bool = True) -> FastAPI:
    """Build the app. Pass ``atheer`` to inject a pre-built container (tests)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = atheer or Atheer.build(settings or get_settings())
        app.state.atheer = container
        await container.start(listen=listen)
        if container.settings.staff_api_key is None:
            logger.warning("ATHEER_STAFF_API_KEY is not set: staff endpoints are disabled.")
        try:
            yield
        finally:
            await container.stop()

    app = FastAPI(title="Atheer API", version=__version__, lifespan=lifespan,
                  description="Atheer (أثير) smart clinic assistant. Staff endpoints need the X-API-Key header.")
    app.include_router(public, tags=["public"])
    app.include_router(staff, tags=["staff"])
    _register_errors(app)
    return app


def _register_errors(app: FastAPI) -> None:
    """Map domain errors to HTTP status codes. Messages are written to be safe to show (no PHI)."""

    def handler(code: int, extra=None):
        async def _handle(_: Request, exc: Exception) -> JSONResponse:
            body = {"detail": str(exc)}
            if extra:
                body.update(extra(exc))
            return JSONResponse(status_code=code, content=body)

        return _handle

    app.add_exception_handler(NotFoundError, handler(status.HTTP_404_NOT_FOUND))
    app.add_exception_handler(UnknownDrugError, handler(status.HTTP_404_NOT_FOUND))
    app.add_exception_handler(
        SchedulingConflictError,
        handler(status.HTTP_409_CONFLICT, lambda e: {"conflicting_ids": e.conflicting_ids}),
    )
    app.add_exception_handler(StaleVersionError, handler(status.HTTP_409_CONFLICT))
    app.add_exception_handler(InvalidTransitionError, handler(status.HTTP_409_CONFLICT))
    app.add_exception_handler(AppointmentError, handler(status.HTTP_422_UNPROCESSABLE_CONTENT))  # other rule violations
    app.add_exception_handler(ValueError, handler(status.HTTP_422_UNPROCESSABLE_CONTENT))  # calculation input limits
    app.add_exception_handler(UpdateError, handler(status.HTTP_502_BAD_GATEWAY))


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
