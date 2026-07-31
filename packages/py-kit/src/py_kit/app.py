"""FastAPI app factory — every Loft service boots through :func:`create_app`.

Wires (in one place, DRY): structured logging, request-id middleware, response
compression, the standard error envelope, Prometheus metrics, and the infra
probes ``/healthz`` (liveness) and ``/readyz`` (readiness). Probes and
``/metrics`` are infrastructure, deliberately *not* under ``/api/v1`` and
excluded from the OpenAPI schema.
"""

import uuid
from collections.abc import Awaitable, Callable, Sequence

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import Lifespan

from py_kit.config import BaseServiceSettings
from py_kit.errors import install_error_handlers
from py_kit.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
)
from py_kit.metrics import install_metrics

ReadinessCheck = Callable[[], Awaitable[str | None]]
"""Async callable that returns on success and raises on failure. Its
``__name__`` is used as the check's key in the ``/readyz`` report. Return
``None`` for a plain ``"ok"``, or a short status string (e.g. ``"skipped"``
when the dependency isn't configured yet) to report a non-default healthy
state."""

REQUEST_ID_HEADER = "X-Request-ID"

#: gzip level for response compression. Explicit, because Starlette's default
#: (9) is strictly WORSE than 6 on our real payloads — measured on the two
#: docs/PERF.md big parts, level 9 produced *more* bytes than level 6 (221 553
#: vs 220 873 on the tray; 92 180 vs 91 837 on the heat sink — level 9's larger
#: match window is a pessimisation on interleaved float streams) while costing
#: 4-9x the CPU (73 ms vs 17 ms; 90 ms vs 10 ms). Level 6 keeps the full 5.2x /
#: 11.9x ratio for ~10-17 ms on a ~1.1 MiB mesh. See docs/PERF.md PERF-4.
COMPRESSION_LEVEL = 6

#: Smallest response body worth compressing, in bytes. Set to one Ethernet MTU
#: rather than Starlette's 500: below ~1 500 B the body still rides in a single
#: TCP segment, so compression cannot save a round trip and only costs CPU on
#: both ends plus a ``Vary: Accept-Encoding`` that fragments caches. The
#: numbers this route actually sees (docs/PERF.md PERF-4): a small box mesh is
#: ~3 KiB and DOES compress; an error envelope or a probe body is ~100 B and
#: does not.
COMPRESSION_MINIMUM_SIZE = 1500

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

    # Response compression, wired ONCE for every service (DRY): the GLB mesh
    # route is the hottest binary path in the product and shipped raw until
    # PERF-4. Registered BEFORE the request-id middleware so it ends up
    # INNERMOST — Starlette applies user middleware outermost-last, and gzip
    # must sit closest to the routes so it sees a complete, buffered body and
    # can emit a correct ``Content-Length``. Outside the request-id
    # BaseHTTPMiddleware it would only ever see a stream and fall back to
    # chunked, dropping the length the browser uses for download progress.
    #
    # WHEN THE FIRST STREAMING RESPONSE LANDS, READ THIS. Every response in the
    # product is buffered today, which is the only reason the placement above is
    # unambiguously right. A ``StreamingResponse`` or SSE endpoint inverts the
    # trade: gzip would buffer it to compress, destroying the incrementality that
    # was the point of streaming, and a long-lived SSE stream would simply never
    # flush. Starlette's gzip has no per-route opt-out, so the exemption has to be
    # explicit — send ``Content-Encoding: identity`` from that route, or move the
    # streaming endpoints onto a sub-application without this middleware. Do not
    # "fix" it by relaxing ``minimum_size``; the size is not the variable.
    app.add_middleware(
        GZipMiddleware,
        minimum_size=COMPRESSION_MINIMUM_SIZE,
        compresslevel=COMPRESSION_LEVEL,
    )

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

    # Metrics LAST, so the middleware is OUTERMOST: what it times is what the
    # client waits for (compression, request-id binding, the error envelope and
    # the handler), not a handler-only slice that would flatter every number.
    # See :mod:`py_kit.metrics` for what is exported and the ``/metrics``
    # exposure posture — it is not public by default.
    install_metrics(app, settings)

    return app
