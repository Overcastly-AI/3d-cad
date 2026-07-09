"""Gateway app — boots on the py-kit factory (probes, logging, envelope).

Skeleton stage: no ``/api/v1`` routes yet; the first real routes land with
the contract-pipeline and auth items (docs/ROADMAP.md Phase 0/1).
"""

import uvicorn
from fastapi import FastAPI
from py_kit import BaseServiceSettings, create_app

TITLE = "Loft Gateway"
VERSION = "0.1.0"


class GatewaySettings(BaseServiceSettings):
    """Gateway configuration (env-driven, see ``BaseServiceSettings``)."""

    service_name: str = "gateway"
    port: int = 8000


def build_app(settings: GatewaySettings | None = None) -> FastAPI:
    """Build the gateway app.

    The gateway has no infrastructure dependencies yet, so readiness is
    trivially green; real checks (e.g. the geometry queue) slot into
    ``readiness_checks`` later without changing the probe API.
    """
    settings = settings or GatewaySettings()
    return create_app(settings, title=TITLE, version=VERSION, readiness_checks=())


app = build_app()


def run() -> None:
    """Serve with uvicorn on the configured port (``python -m gateway.main``)."""
    uvicorn.run("gateway.main:app", host="0.0.0.0", port=GatewaySettings().port)


if __name__ == "__main__":
    run()
