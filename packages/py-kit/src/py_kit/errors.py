"""Standard error envelope (CLAUDE.md API conventions).

Every error a Loft service returns has the shape::

    {"error": {"code": ..., "message": ..., "details": ..., "request_id": ...}}

Services raise :class:`ApiError` subclasses; :func:`install_error_handlers`
(wired by the app factory) renders them. Unhandled exceptions become an
opaque 500 — no stack traces or internals leak to clients.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from py_kit.logging import get_logger

_logger = get_logger("py_kit.errors")


class ApiError(Exception):
    """Base API error. Subclasses fix the HTTP status and default code."""

    status_code: int = 500
    code: str = "internal_error"

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


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    request_id: str | None = None,
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
    )


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
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            status_code=422,
            code="validation_error",
            message="Request validation failed.",
            details=exc.errors(),
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
