"""Gateway app — boots on the py-kit factory (probes, logging, envelope).

``/api/v1`` surface: the geometry proxy (:mod:`gateway.geometry` — apps/web
talks only to the gateway, CLAUDE.md service boundaries), auth
(:mod:`gateway.auth` — email/password + JWT; the gateway owns identity per
RESEARCH §3, backed by its own Postgres schema under ``alembic/``), and the
parts + feature-tree + assembly-graph aggregation (:mod:`gateway.parts`,
:mod:`gateway.features`, :mod:`gateway.assemblies` — auth-protected forwarding
to the documents service with the verified principal attached), plus the
material-library read (:mod:`gateway.materials`) that aggregation writes
against.

Startup is fail-fast on secrets: ``build_app`` resolves the JWT secret
posture BEFORE assembling the app, so a non-dev deployment without
``JWT_SECRET`` refuses to boot (see :mod:`gateway.auth.security`).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx2 as httpx
import uvicorn
from fastapi import FastAPI
from py_kit import BaseServiceSettings, create_app
from py_kit.db import DatabaseState, postgres_readiness
from py_kit.ratelimit import RateLimiter

from gateway.affinity import parse_worker_urls
from gateway.assemblies import router as assemblies_router
from gateway.auth import auth_router, resolve_auth_config
from gateway.drawings import router as drawings_router
from gateway.features import router as features_router
from gateway.folders import assemblies_router as folder_assemblies_router
from gateway.folders import drawings_router as folder_drawings_router
from gateway.folders import parts_router as folder_parts_router
from gateway.folders import router as folders_router
from gateway.geometry import DEFAULT_GEOMETRY_TIMEOUT_S, create_geometry_pool
from gateway.geometry import router as geometry_router
from gateway.materials import router as materials_router
from gateway.parts import create_documents_client
from gateway.parts import router as parts_router
from gateway.step_import import assembly_router as assembly_import_router
from gateway.step_import import router as step_import_router

TITLE = "Loft Gateway"
VERSION = "0.1.0"

#: Readiness-probe budget — a quick "is geometry there?" ping, not a real call.
READINESS_PROBE_TIMEOUT_S = 2.0

#: Default access-token lifetime (1 h) — overridable via ``JWT_TTL_S``.
DEFAULT_TOKEN_TTL_S = 3600


class GatewaySettings(BaseServiceSettings):
    """Gateway configuration (env-driven, see ``BaseServiceSettings``)."""

    service_name: str = "gateway"
    port: int = 8000
    #: Geometry upstream(s) — env ``GEOMETRY_URL``, **comma-separated for a
    #: fan-out**: ``http://geometry-1:8002,http://geometry-2:8002``. The gateway
    #: pins each modeler to one of them by rendezvous hash (CONC-1,
    #: :mod:`gateway.affinity`), which is worth 3.75x against 1.21x for the
    #: random dispatch a shared listening socket or compose DNS gives. A single
    #: URL is the one-worker case and behaves exactly as before.
    geometry_url: str = "http://localhost:8002"  # env: GEOMETRY_URL
    #: Per-request budget for a geometry call, seconds (env:
    #: ``GEOMETRY_TIMEOUT_S``). See :data:`~gateway.geometry.
    #: DEFAULT_GEOMETRY_TIMEOUT_S` for how 90 s was derived from the measured
    #: distribution — and for why the old 30 s produced a false outage report on
    #: a part size this project ships goldens for.
    geometry_timeout_s: float = DEFAULT_GEOMETRY_TIMEOUT_S  # env: GEOMETRY_TIMEOUT_S
    documents_url: str = "http://localhost:8001"  # env: DOCUMENTS_URL
    # `loft_env` is INHERITED from BaseServiceSettings (env: LOFT_ENV) — one
    # deployment-posture variable for the whole stack, gating both the JWT
    # fallback below and py-kit's datastore-credential guard. It has no
    # default: only the explicit LOFT_ENV=dev permits running without
    # JWT_SECRET (a fixed, publicly-known fallback, with a warning); unset or
    # anything else refuses startup without a real secret, so an
    # unconfigured deployment dies loudly instead of signing tokens with the
    # repo-public dev constant.
    jwt_secret: str | None = None  # env: JWT_SECRET (>= 32 chars when set)
    jwt_ttl_s: int = DEFAULT_TOKEN_TTL_S  # env: JWT_TTL_S


def build_app(
    settings: GatewaySettings | None = None,
    *,
    geometry_transport: httpx.AsyncBaseTransport | None = None,
    documents_transport: httpx.AsyncBaseTransport | None = None,
    rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    """Build the gateway app.

    Raises :class:`RuntimeError` (i.e. the process does not boot) when the
    JWT secret posture is invalid for ``settings.loft_env`` — including the
    fully-unset case (no ``LOFT_ENV``, no ``JWT_SECRET``): booting demands
    either an explicit ``LOFT_ENV=dev`` or a real secret. This is THE
    fail-fast choke point; routes only ever read the resolved config from
    ``app.state.auth_config``, which is populated nowhere else.

    The ``*_transport`` parameters let tests hand each upstream client an
    ``httpx.MockTransport``; production always passes ``None`` (real network).
    ``rate_limiter`` is likewise a test seam: an injected limiter (e.g.
    fake-Redis-backed) is used as-is and its lifecycle left to the caller;
    production passes ``None`` and the lifespan builds one from settings
    (Redis-backed, or a no-op when rate limiting is disabled/unconfigured).
    """
    settings = settings or GatewaySettings()
    auth_config = resolve_auth_config(
        loft_env=settings.loft_env,
        jwt_secret=settings.jwt_secret,
        token_ttl_s=settings.jwt_ttl_s,
    )
    database = DatabaseState()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Own startup/shutdown resources: upstream clients + DB + limiter."""
        pool = create_geometry_pool(
            settings.geometry_url,
            geometry_transport,
            timeout_s=settings.geometry_timeout_s,
        )
        app.state.geometry_pool = pool
        documents_client = create_documents_client(
            settings.documents_url, documents_transport
        )
        app.state.documents_client = documents_client
        if settings.postgres_url is not None:
            database.start(settings.postgres_url)
        app.state.database = database
        # Injected limiter (tests) is used as-is and NOT closed here — the
        # caller owns it; otherwise build one from settings and own its pool.
        owns_limiter = rate_limiter is None
        limiter = rate_limiter or RateLimiter.from_settings(settings)
        app.state.rate_limiter = limiter
        try:
            yield
        finally:
            await pool.aclose()
            await documents_client.aclose()
            await database.dispose()
            if owns_limiter and limiter is not None:
                await limiter.aclose()

    async def geometry() -> str:
        """Best-effort, REPORT-ONLY geometry reachability.

        Deliberately never fails ``/readyz``: in dev the gateway must come up
        and serve (health, docs, future documents routes) even while the
        geometry service is still building or down — a hard gate here would
        take the whole gateway unready over one degraded dependency, and
        per-request proxy failures already surface cleanly as the 502
        ``upstream_unavailable`` envelope. The check only annotates the
        readiness report so operators see the dependency state at a glance.

        With a fan-out (CONC-1) it reports the COUNT — ``"ok (3/4 workers)"``.
        That distinction is the whole operational value of the probe now: a
        gateway with three of four geometry workers alive is degraded but
        serving (the pool re-routes; those modelers are slower, not stranded),
        and a report that collapsed to "ok" would hide a dead process until
        somebody noticed the latency.
        """
        workers = parse_worker_urls(settings.geometry_url)
        reachable = 0
        async with httpx.AsyncClient(timeout=READINESS_PROBE_TIMEOUT_S) as probe:
            for url in workers:
                try:
                    response = await probe.get(f"{url}/healthz")
                except httpx.HTTPError:
                    continue
                if response.status_code == 200:
                    reachable += 1
        if reachable == 0:
            return "unreachable"
        if len(workers) == 1:
            return "ok"
        return f"ok ({reachable}/{len(workers)} workers)"

    # Postgres readiness is the shared py-kit posture: HARD check (unlike
    # geometry) — auth cannot serve without its store; "skipped" while
    # POSTGRES_URL is unset (auth routes then answer 503 per-request).
    postgres = postgres_readiness(
        settings, database, timeout_s=READINESS_PROBE_TIMEOUT_S
    )

    app = create_app(
        settings,
        title=TITLE,
        version=VERSION,
        readiness_checks=(geometry, postgres),
        lifespan=lifespan,
    )
    app.state.auth_config = auth_config
    app.include_router(geometry_router)
    app.include_router(auth_router)
    app.include_router(parts_router)
    app.include_router(materials_router)
    app.include_router(features_router)
    app.include_router(assemblies_router)
    app.include_router(drawings_router)
    app.include_router(step_import_router)
    app.include_router(assembly_import_router)
    # Filing (:mod:`gateway.folders`): the folder tree + the three document
    # MOVE routes, registered after their document routers so the static
    # `/move` suffix never shadows a document's own `/{id}` route.
    app.include_router(folders_router)
    app.include_router(folder_parts_router)
    app.include_router(folder_assemblies_router)
    app.include_router(folder_drawings_router)
    return app


app = build_app()


def run() -> None:
    """Serve with uvicorn on the configured port (``python -m gateway.main``)."""
    uvicorn.run("gateway.main:app", host="0.0.0.0", port=GatewaySettings().port)


if __name__ == "__main__":
    run()
