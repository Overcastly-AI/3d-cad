"""Geometry app — boots on the py-kit factory (probes, logging, envelope).

Routes live in :mod:`geometry.api`; kernel code (the only OCP/build123d
imports in the monorepo) lives in :mod:`geometry.kernel`. This module stays
kernel-free — it only assembles the service.
"""

import uvicorn
from fastapi import FastAPI
from py_kit import BaseServiceSettings, create_app

from geometry.api import router
from geometry.mesh_store import assert_single_worker_mesh_store, configure_mesh_store

TITLE = "Loft Geometry"
VERSION = "0.1.0"


class GeometrySettings(BaseServiceSettings):
    """Geometry configuration (env-driven, see ``BaseServiceSettings``)."""

    service_name: str = "geometry"
    port: int = 8002

    #: Worker fan-out (env ``WEB_CONCURRENCY``, the knob uvicorn reads to default
    #: its worker count). MUST stay 1 while the mesh store is the in-process LRU
    #: (``S3_URL`` unset): ``build_app`` refuses to start on >1 so a multi-worker
    #: deploy fails loud instead of 404-ing meshes across worker processes
    #: (engineering audit F1, docs/design/feature-tree.md §7.8). When ``S3_URL``
    #: is set the shared S3/MinIO store is active and this guard is lifted —
    #: multi-worker/replica is then correct (engineering audit F6).
    web_concurrency: int = 1

    #: Object-storage bucket for the content-addressed mesh store (env
    #: ``S3_BUCKET``; ``S3_URL`` is inherited from ``BaseServiceSettings``).
    #: Compose provisions both (docker-compose.yml). Only consumed when
    #: ``s3_url`` is set — otherwise the in-process LRU is used and this is
    #: ignored (docs/design/feature-tree.md §7.8).
    s3_bucket: str = "loft"

    #: S3/MinIO credentials for the mesh store. Optional: when unset, boto3's
    #: default credential chain applies (``AWS_ACCESS_KEY_ID`` /
    #: ``AWS_SECRET_ACCESS_KEY`` env, instance profile, etc.). Env:
    #: ``S3_ACCESS_KEY_ID`` / ``S3_SECRET_ACCESS_KEY`` / ``S3_REGION``.
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "us-east-1"

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

    Installs the mesh-store backend from config (:func:`configure_mesh_store`):
    the shared S3/MinIO store when ``S3_URL`` is set, else the in-process LRU.
    Only for the **unshared** LRU does it enforce the single-worker guard —
    raising :class:`~geometry.mesh_store.MeshStoreMultiWorkerError` when
    ``WEB_CONCURRENCY > 1`` (fail loud beats a silent cross-worker 404). With
    S3 configured the store is shared, so the guard is lifted and
    multi-worker/replica geometry is correct (design §7.8; audit F1/F6).
    """
    settings = settings or GeometrySettings()
    mesh_store = configure_mesh_store(
        settings.s3_url,
        settings.s3_bucket,
        s3_access_key_id=settings.s3_access_key_id,
        s3_secret_access_key=settings.s3_secret_access_key,
        s3_region=settings.s3_region,
    )
    if not mesh_store.is_shared:
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
