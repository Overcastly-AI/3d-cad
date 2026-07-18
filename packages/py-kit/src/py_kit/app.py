"""FastAPI app factory — every Loft service boots through :func:`create_app`.

Wires (in one place, DRY): structured logging, request-id middleware, the
standard error envelope, and the infra probes ``/healthz`` (liveness) and
``/readyz`` (readiness). Probes are infrastructure, deliberately *not* under
``/api/v1`` and excluded from the OpenAPI schema.
"""

import uuid
from collections.abc import Awaitable, Callable, Sequence

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.types import Lifespan

from py_kit.config import BaseServiceSettings
from py_kit.errors import install_error_handlers
from py_kit.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
)

ReadinessCheck = Callable[[], Awaitable[str | None]]
"""Async callable that returns on success and raises on failure. Its
``__name__`` is used as the check's key in the ``/readyz`` report. Return
``None`` for a plain ``"ok"``, or a short status string (e.g. ``"skipped"``
when the dependency isn't configured yet) to report a non-default healthy
state."""

REQUEST_ID_HEADER = "X-Request-ID"

_logger = get_logger("py_kit.app")


def create_app(
    settings: BaseServiceSettings,
    *,
    title: str,
    version: str,
    readiness_checks: Sequence[ReadinessCheck] = (),
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    """Build a service app with logging, probes, and the error envelope.

    ``lifespan`` is passed straight to FastAPI — services use it to own
    startup/shutdown resources (e.g. the gateway's upstream HTTP client).
    """
    configure_logging(settings)
    app = FastAPI(title=title, version=version, lifespan=lifespan)
    install_error_handlers(app)

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        clear_request_context()
        bind_request_context(request_id=request_id)
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        """Liveness: 200 whenever the process is up."""
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        """Readiness: run the provided checks; 503 with per-check detail."""
        checks: dict[str, str] = {}
        ready = True
        for check in readiness_checks:
            name = getattr(check, "__name__", type(check).__name__)
            try:
                status = await check()
            except Exception as exc:
                ready = False
                # Exception *type* only in the body — /readyz is unauthenticated
                # and str(exc) may embed secrets (e.g. a Postgres DSN). The full
                # message goes to the server-side log.
                checks[name] = f"error: {type(exc).__name__}"
                _logger.warning("readiness_check_failed", check=name, error=str(exc))
            else:
                checks[name] = status if status is not None else "ok"
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ok" if ready else "unavailable",
                "checks": checks,
            },
        )

    return app
