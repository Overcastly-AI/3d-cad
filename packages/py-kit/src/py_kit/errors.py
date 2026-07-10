"""Standard error envelope (CLAUDE.md API conventions).

Every error a Loft service returns has the shape::

    {"error": {"code": ..., "message": ..., "details": ..., "request_id": ...}}

Services raise :class:`ApiError` subclasses; :func:`install_error_handlers`
(wired by the app factory) renders them. Unhandled exceptions become an
opaque 500 — no stack traces or internals leak to clients.
"""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from py_kit.logging import get_logger

_logger = get_logger("py_kit.errors")


class ApiError(Exception):
    """Base API error. Subclasses fix the HTTP status and default code.

    ``headers`` (class-level) lets a subclass attach response headers to the
    rendered envelope — e.g. the RFC 6750 ``WWW-Authenticate`` challenge on
    :class:`UnauthorizedError`.
    """

    status_code: int = 500
    code: str = "internal_error"
    headers: ClassVar[dict[str, str] | None] = None

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details


class UnauthorizedError(ApiError):
    """Missing or invalid credentials (HTTP 401).

    Rendered with a ``WWW-Authenticate: Bearer`` challenge (RFC 6750) — the
    Loft auth surface is bearer-token based. Callers refine ``code`` (e.g.
    ``invalid_credentials`` on login, ``invalid_token`` on protected routes)
    but MUST keep messages generic: never echo credentials or say which of
    email/password was wrong.
    """

    status_code = 401
    code = "unauthorized"
    headers: ClassVar[dict[str, str] | None] = {"WWW-Authenticate": "Bearer"}


class NotFoundError(ApiError):
    """Resource does not exist (HTTP 404)."""

    status_code = 404
    code = "not_found"


class ConflictError(ApiError):
    """State conflict, e.g. duplicate or stale write (HTTP 409)."""

    status_code = 409
    code = "conflict"


class ValidationApiError(ApiError):
    """Semantically invalid input past schema validation (HTTP 422)."""

    status_code = 422
    code = "validation_error"


class InternalError(ApiError):
    """Explicit internal failure (HTTP 500)."""

    status_code = 500
    code = "internal_error"


class UpstreamUnavailableError(ApiError):
    """A depended-on Loft service could not be reached (HTTP 502).

    Raised by proxy/aggregation layers (e.g. the gateway) when a connect,
    timeout, or transport error prevents the upstream call entirely — the
    client sees the standard envelope, never a raw stack.
    """

    status_code = 502
    code = "upstream_unavailable"


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Render the standard error envelope."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": jsonable_encoder(details),
                "request_id": request_id,
            }
        },
        headers=headers,
    )


#: Keys of a pydantic validation error that are safe to echo to the client.
#: ``input`` (and ``ctx``/``url``) are deliberately dropped: request payloads
#: may carry secrets (passwords, tokens), and reflecting them back in the 422
#: envelope would leak them to logs/proxies/browsers. ``loc`` + ``msg`` are
#: enough to fix the request.
_SAFE_VALIDATION_ERROR_KEYS = ("type", "loc", "msg")


def _scrub_validation_errors(
    errors: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Strip input echoes from pydantic validation errors (see above)."""
    return [
        {key: error[key] for key in _SAFE_VALIDATION_ERROR_KEYS if key in error}
        for error in errors
    ]


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def install_error_handlers(app: FastAPI) -> None:
    """Register envelope-rendering handlers on *app* (used by the factory)."""

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            request_id=_request_id(request),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            status_code=422,
            code="validation_error",
            message="Request validation failed.",
            details=_scrub_validation_errors(exc.errors()),
            request_id=_request_id(request),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return error_response(
            status_code=exc.status_code,
            code="http_error",
            message=str(exc.detail),
            request_id=_request_id(request),
        )

    @app.exception_handler(Exception)
    async def handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        _logger.exception(
            "unhandled_exception",
            path=request.url.path,
            request_id=_request_id(request),
        )
        return error_response(
            status_code=500,
            code="internal_error",
            message="Internal server error.",
            request_id=_request_id(request),
        )
