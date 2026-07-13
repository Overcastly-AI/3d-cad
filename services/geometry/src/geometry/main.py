"""Geometry app — boots on the py-kit factory (probes, logging, envelope).

Routes live in :mod:`geometry.api`; kernel code (the only OCP/build123d
imports in the monorepo) lives in :mod:`geometry.kernel`. This module stays
kernel-free — it only assembles the service.
"""

import uvicorn
from fastapi import FastAPI
from py_kit import BaseServiceSettings, create_app

from geometry.api import router

TITLE = "Loft Geometry"
VERSION = "0.1.0"


class GeometrySettings(BaseServiceSettings):
    """Geometry configuration (env-driven, see ``BaseServiceSettings``)."""

    service_name: str = "geometry"
    port: int = 8002

    #: Hard wall-clock bound (seconds) on the untrusted OCCT STEP parse, which
    #: runs in a killable subprocess (docs/design/step-import.md §6, BACKLOG P1).
    #: A parse exceeding this is SIGKILLed and surfaces as ``import_parse_timeout``
    #: so a degenerate/adversarial part-21 cannot pin a worker. Env:
    #: ``STEP_IMPORT_TIMEOUT_SECONDS``.
    step_import_timeout_seconds: float = 5.0


def build_app(settings: GeometrySettings | None = None) -> FastAPI:
    """Build the geometry app with its Redis (queue) readiness check."""
    settings = settings or GeometrySettings()

    async def redis() -> str:
        """Redis/queue readiness.

        Skeleton stage: no queue worker yet. With ``REDIS_URL`` unset the
        check reports ``"skipped"`` and ``/readyz`` stays 200. The real
        connection ping replaces this body when the arq worker lands —
        same check name, no probe-API change.
        """
        if settings.redis_url is None:
            return "skipped"
        return "configured (ping lands with the arq worker)"

    app = create_app(settings, title=TITLE, version=VERSION, readiness_checks=(redis,))
    app.include_router(router)
    return app


app = build_app()


def run() -> None:
    """Serve with uvicorn on the configured port (``python -m geometry.main``)."""
    uvicorn.run("geometry.main:app", host="0.0.0.0", port=GeometrySettings().port)


if __name__ == "__main__":
    run()
