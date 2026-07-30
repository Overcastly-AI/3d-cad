"""Loft shared service kit.

One source of truth for cross-service boilerplate (CLAUDE.md DRY rule):
env-driven config, structlog JSON logging, FastAPI app factory with
``/healthz`` + ``/readyz``, the standard error envelope, and the arq queue
client. Every Loft service builds on this package.
"""

from py_kit.app import REQUEST_ID_HEADER, ReadinessCheck, create_app
from py_kit.config import DEV_ENV, BaseServiceSettings, is_dev_env
from py_kit.errors import (
    ApiError,
    ConflictError,
    InternalError,
    NotFoundError,
    RateLimitExceededError,
    UnauthorizedError,
    UpstreamUnavailableError,
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
from py_kit.ratelimit import RateLimiter

__all__ = [
    "DEV_ENV",
    "REQUEST_ID_HEADER",
    "ApiError",
    "BaseServiceSettings",
    "ConflictError",
    "InternalError",
    "NotFoundError",
    "QueueClient",
    "QueueConfigurationError",
    "RateLimitExceededError",
    "RateLimiter",
    "ReadinessCheck",
    "UnauthorizedError",
    "UpstreamUnavailableError",
    "ValidationApiError",
    "bind_request_context",
    "clear_request_context",
    "configure_logging",
    "create_app",
    "error_response",
    "get_logger",
    "install_error_handlers",
    "is_dev_env",
    "redis_settings",
]
