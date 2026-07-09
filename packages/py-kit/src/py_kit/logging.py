"""Structured logging — structlog, JSON to stdout.

``configure_logging(settings)`` sets up structlog once per process. Output is
JSON lines on stdout (12-factor); set ``LOG_FORMAT=console`` for a
human-friendly dev renderer. Request-scoped context (request id, user, ...)
is bound via :func:`bind_request_context` and merged into every log line.
"""

import logging
from typing import Any, cast

import structlog
from structlog.typing import EventDict, FilteringBoundLogger, Processor, WrappedLogger

from py_kit.config import BaseServiceSettings


def _add_service_name(service_name: str) -> Processor:
    """Processor stamping every log line with the emitting service's name."""

    def add_service(
        logger: WrappedLogger, method_name: str, event_dict: EventDict
    ) -> EventDict:
        event_dict.setdefault("service", service_name)
        return event_dict

    return add_service


def configure_logging(settings: BaseServiceSettings) -> None:
    """Configure structlog for the whole process (idempotent)."""
    level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)

    renderer: Processor
    if settings.log_format == "console":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_service_name(settings.service_name),
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(*names: str) -> FilteringBoundLogger:
    """Typed accessor for a structlog logger."""
    return cast(FilteringBoundLogger, structlog.get_logger(*names))


def bind_request_context(**values: Any) -> None:
    """Bind request-scoped values (e.g. ``request_id``) to all log lines."""
    structlog.contextvars.bind_contextvars(**values)


def clear_request_context() -> None:
    """Drop all request-scoped log context (start of each request)."""
    structlog.contextvars.clear_contextvars()
