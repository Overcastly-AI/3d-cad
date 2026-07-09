"""Loft shared service kit.

One source of truth for cross-service boilerplate (CLAUDE.md DRY rule):
env-driven config, structlog JSON logging, FastAPI app factory with
``/healthz`` + ``/readyz``, the standard error envelope, and the arq queue
client. Every Loft service builds on this package.
"""

from py_kit.app import REQUEST_ID_HEADER, ReadinessCheck, create_app
from py_kit.config import BaseServiceSettings
from py_kit.errors import (
    ApiError,
    ConflictError,
    InternalError,
    NotFoundError,
    ValidationApiError,
    error_response,
    install_error_handlers,
)
from py_kit.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
)
from py_kit.queue import QueueClient, QueueConfigurationError, redis_settings

__all__ = [
    "REQUEST_ID_HEADER",
    "ApiError",
    "BaseServiceSettings",
    "ConflictError",
    "InternalError",
    "NotFoundError",
    "QueueClient",
    "QueueConfigurationError",
    "ReadinessCheck",
    "ValidationApiError",
    "bind_request_context",
    "clear_request_context",
    "configure_logging",
    "create_app",
    "error_response",
    "get_logger",
    "install_error_handlers",
    "redis_settings",
]
