"""Geometry app — boots on the py-kit factory (probes, logging, envelope).

Routes live in :mod:`geometry.api`; kernel code (the only OCP/build123d
imports in the monorepo) lives in :mod:`geometry.kernel`. This module stays
kernel-free — it only assembles the service.
"""

import uvicorn
from fastapi import FastAPI
from py_kit import BaseServiceSettings, create_app

from geometry.api import router
from geometry.mesh_store import assert_single_worker_mesh_store

TITLE = "Loft Geometry"
VERSION = "0.1.0"


class GeometrySettings(BaseServiceSettings):
    """Geometry configuration (env-driven, see ``BaseServiceSettings``)."""

    service_name: str = "geometry"
    port: int = 8002

    #: Worker fan-out (env ``WEB_CONCURRENCY``, the knob uvicorn reads to default
    #: its worker count). MUST stay 1 while the mesh store is the in-process LRU:
    #: ``build_app`` refuses to start on >1 so a multi-worker deploy fails loud
    #: instead of 404-ing meshes across worker processes (engineering audit F1,
    #: docs/design/feature-tree.md §7.8). Lifts when the MinIO swap lands.
    web_concurrency: int = 1

    #: Hard wall-clock bound (seconds) on the untrusted OCCT STEP parse, which
    #: runs in a killable subprocess (docs/design/step-import.md §6, BACKLOG P1).
    #: A parse exceeding this is SIGKILLed and surfaces as ``import_parse_timeout``
    #: so a degenerate/adversarial part-21 cannot pin a worker. Env:
    #: ``STEP_IMPORT_TIMEOUT_SECONDS``. NOTE: the bound spans the whole child
    #: lifetime, including the ~0.9s OCP cold-import, so the effective parse
    #: budget is roughly this minus ~1s — do not set it below ~1s or every import
    #: false-times-out. Default 5.0s leaves ~4s of real parse headroom.
    step_import_timeout_seconds: float = 5.0


def build_app(settings: GeometrySettings | None = None) -> FastAPI:
    """Build the geometry app with its Redis (queue) readiness check.

    Raises :class:`~geometry.mesh_store.MeshStoreMultiWorkerError` when
    ``WEB_CONCURRENCY > 1``: the in-process mesh store can't serve across
    workers until the object-storage swap lands (design §7.8). Fail loud at
    import/startup beats a silent cross-worker 404.
    """
    settings = settings or GeometrySettings()
    assert_single_worker_mesh_store(settings.web_concurrency)

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
