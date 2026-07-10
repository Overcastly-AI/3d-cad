"""Gateway app — boots on the py-kit factory (probes, logging, envelope).

First real ``/api/v1`` surface: the geometry tessellation proxy
(:mod:`gateway.geometry`) — apps/web talks only to the gateway (CLAUDE.md
service boundaries), so geometry capability is exposed here, never as a new
public port.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx2 as httpx
import uvicorn
from fastapi import FastAPI
from py_kit import BaseServiceSettings, create_app

from gateway.geometry import create_geometry_client
from gateway.geometry import router as geometry_router

TITLE = "Loft Gateway"
VERSION = "0.1.0"

#: Readiness-probe budget — a quick "is geometry there?" ping, not a real call.
READINESS_PROBE_TIMEOUT_S = 2.0


class GatewaySettings(BaseServiceSettings):
    """Gateway configuration (env-driven, see ``BaseServiceSettings``)."""

    service_name: str = "gateway"
    port: int = 8000
    geometry_url: str = "http://localhost:8002"  # env: GEOMETRY_URL


def build_app(
    settings: GatewaySettings | None = None,
    *,
    geometry_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Build the gateway app.

    ``geometry_transport`` lets tests hand the upstream client an
    ``httpx.MockTransport``; production always passes ``None`` (real network).
    """
    settings = settings or GatewaySettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Own the upstream geometry client: one pool, closed on shutdown."""
        client = create_geometry_client(settings.geometry_url, geometry_transport)
        app.state.geometry_client = client
        try:
            yield
        finally:
            await client.aclose()

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

    app = create_app(
        settings,
        title=TITLE,
        version=VERSION,
        readiness_checks=(geometry,),
        lifespan=lifespan,
    )
    app.include_router(geometry_router)
    return app


app = build_app()


def run() -> None:
    """Serve with uvicorn on the configured port (``python -m gateway.main``)."""
    uvicorn.run("gateway.main:app", host="0.0.0.0", port=GatewaySettings().port)


if __name__ == "__main__":
    run()
