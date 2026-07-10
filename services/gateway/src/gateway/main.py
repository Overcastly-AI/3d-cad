"""Gateway app — boots on the py-kit factory (probes, logging, envelope).

``/api/v1`` surface: the geometry proxy (:mod:`gateway.geometry` — apps/web
talks only to the gateway, CLAUDE.md service boundaries), auth
(:mod:`gateway.auth` — email/password + JWT; the gateway owns identity per
RESEARCH §3, backed by its own Postgres schema under ``alembic/``), and the
parts aggregation (:mod:`gateway.parts` — auth-protected forwarding to the
documents service with the verified principal attached).

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

from gateway.auth import auth_router, resolve_auth_config
from gateway.geometry import create_geometry_client
from gateway.geometry import router as geometry_router
from gateway.parts import create_documents_client
from gateway.parts import router as parts_router

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
    geometry_url: str = "http://localhost:8002"  # env: GEOMETRY_URL
    documents_url: str = "http://localhost:8001"  # env: DOCUMENTS_URL
    # Deployment environment posture. ONLY the exact value "dev" permits
    # running without JWT_SECRET (a fixed, publicly-known fallback is used and
    # a warning logged); everything else fails startup without a real secret.
    loft_env: str = "dev"  # env: LOFT_ENV
    jwt_secret: str | None = None  # env: JWT_SECRET (>= 32 chars when set)
    jwt_ttl_s: int = DEFAULT_TOKEN_TTL_S  # env: JWT_TTL_S


def build_app(
    settings: GatewaySettings | None = None,
    *,
    geometry_transport: httpx.AsyncBaseTransport | None = None,
    documents_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Build the gateway app.

    Raises :class:`RuntimeError` (i.e. the process does not boot) when the
    JWT secret posture is invalid for ``settings.loft_env`` — this is THE
    fail-fast choke point; routes only ever read the resolved config from
    ``app.state.auth_config``, which is populated nowhere else.

    The ``*_transport`` parameters let tests hand each upstream client an
    ``httpx.MockTransport``; production always passes ``None`` (real network).
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
        """Own startup/shutdown resources: upstream clients + DB engine."""
        client = create_geometry_client(settings.geometry_url, geometry_transport)
        app.state.geometry_client = client
        documents_client = create_documents_client(
            settings.documents_url, documents_transport
        )
        app.state.documents_client = documents_client
        if settings.postgres_url is not None:
            database.start(settings.postgres_url)
        app.state.database = database
        try:
            yield
        finally:
            await client.aclose()
            await documents_client.aclose()
            await database.dispose()

    async def geometry() -> str:
        """Best-effort, REPORT-ONLY geometry reachability ("ok"/"unreachable").

        Deliberately never fails ``/readyz``: in dev the gateway must come up
        and serve (health, docs, future documents routes) even while the
        geometry service is still building or down — a hard gate here would
        take the whole gateway unready over one degraded dependency, and
        per-request proxy failures already surface cleanly as the 502
        ``upstream_unavailable`` envelope. The check only annotates the
        readiness report so operators see the dependency state at a glance.
        """
        try:
            async with httpx.AsyncClient(timeout=READINESS_PROBE_TIMEOUT_S) as probe:
                response = await probe.get(f"{settings.geometry_url}/healthz")
        except httpx.HTTPError:
            return "unreachable"
        return "ok" if response.status_code == 200 else "unreachable"

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
    return app


app = build_app()


def run() -> None:
    """Serve with uvicorn on the configured port (``python -m gateway.main``)."""
    uvicorn.run("gateway.main:app", host="0.0.0.0", port=GatewaySettings().port)


if __name__ == "__main__":
    run()
