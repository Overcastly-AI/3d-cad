"""Geometry app — boots on the py-kit factory (probes, logging, envelope).

Routes live in :mod:`geometry.api`; kernel code (the only OCP/build123d
imports in the monorepo) lives in :mod:`geometry.kernel`. This module stays
kernel-free — it only assembles the service.
"""

from typing import ClassVar

import uvicorn
from fastapi import FastAPI
from py_kit import BaseServiceSettings, create_app

from geometry.api import router
from geometry.drawing_store import configure_drawing_artifact_store
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
    #: The secret is the MinIO ROOT password (compose anchors both to
    #: ``MINIO_ROOT_PASSWORD``) and is the one datastore credential in the
    #: stack that travels outside a URL, so it is declared to py-kit's
    #: dev-credential guard below — geometry refuses to boot on the published
    #: default ``loft-minio-dev-only`` unless ``LOFT_ENV=dev``.
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "us-east-1"

    datastore_credential_fields: ClassVar[tuple[str, ...]] = ("s3_secret_access_key",)

    #: Hard **CPU-time** ceiling (seconds) on the untrusted OCCT STEP parse — the
    #: PRIMARY DoS bound, enforced by ``RLIMIT_CPU`` inside the killable worker
    #: (docs/design/step-import.md §6, BACKLOG P1). A parse exceeding this is
    #: killed and surfaces as ``import_parse_timeout`` so a degenerate/adversarial
    #: part-21 cannot pin a worker. Env: ``STEP_IMPORT_TIMEOUT_SECONDS``. Being a
    #: CPU-time bound (not wall-clock) it is INVARIANT to machine load, so it does
    #: not false-fire on a slow-but-legit import under CI/contention — the flake
    #: the old 5 s wall-clock bound caused (2026-07-19). The bound spans the whole
    #: child, including the ~0.9 s OCP cold-import; a legit parse burns ~1 s of
    #: CPU, so the 20 s default is ~20x headroom.
    step_import_timeout_seconds: float = 20.0

    #: **Wall-clock** liveness backstop (seconds) on the parse subprocess — kills a
    #: child that is *wedged* (blocked, not CPU-burning), which ``RLIMIT_CPU``
    #: cannot catch. NOT the DoS latency control (that is the CPU ceiling above);
    #: sized so a legit ~1 s parse never trips it even under heavy contention. Env:
    #: ``STEP_IMPORT_WALL_TIMEOUT_SECONDS``. Default 60.0s.
    step_import_wall_timeout_seconds: float = 60.0


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

    # DE-4 (drawing-export.md §8.3): install the content-addressed drawing-artifact
    # store on the SAME object-storage seam — shared S3 when configured, else the
    # in-process LRU. No single-worker guard: it is a compose cache, so a
    # cross-worker miss just recomposes (never a 404), unlike the mesh store.
    configure_drawing_artifact_store(
        settings.s3_url,
        settings.s3_bucket,
        s3_access_key_id=settings.s3_access_key_id,
        s3_secret_access_key=settings.s3_secret_access_key,
        s3_region=settings.s3_region,
    )

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
