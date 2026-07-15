"""Documents app — boots on the py-kit factory (probes, logging, envelope).

``/api/v1`` surface: parts CRUD (:mod:`documents.parts`), the ordered feature
tree (:mod:`documents.features`, per docs/design/feature-tree.md), and assembly
CRUD (:mod:`documents.assemblies`, per docs/design/assemblies.md — a graph of
instances + mates), backed by Postgres via the shared :mod:`py_kit.db` plumbing
with the schema
owned by ``services/documents/alembic``. This service never imports kernel
code (CLAUDE.md service boundaries) — geometry artifacts are referenced by
object-storage id only.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from py_kit import BaseServiceSettings, create_app
from py_kit.db import DatabaseState, postgres_readiness

from documents.assemblies import router as assemblies_router
from documents.features import router as features_router
from documents.parts import router as parts_router

TITLE = "Loft Documents"
VERSION = "0.1.0"

#: Readiness-probe budget for the ``SELECT 1`` ping.
READINESS_PROBE_TIMEOUT_S = 2.0


class DocumentsSettings(BaseServiceSettings):
    """Documents configuration (env-driven, see ``BaseServiceSettings``)."""

    service_name: str = "documents"
    port: int = 8001


def build_app(settings: DocumentsSettings | None = None) -> FastAPI:
    """Build the documents app.

    The postgres readiness check is HARD (shared py-kit posture): parts
    cannot serve without their store, so an unreachable DB takes ``/readyz``
    to 503. With ``POSTGRES_URL`` unset (bare-uvicorn dev without a DB) the
    check reports ``"skipped"`` and parts routes answer 503 per-request.
    """
    settings = settings or DocumentsSettings()
    database = DatabaseState()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Own the DB engine for the app's lifetime."""
        if settings.postgres_url is not None:
            database.start(settings.postgres_url)
        app.state.database = database
        try:
            yield
        finally:
            await database.dispose()

    app = create_app(
        settings,
        title=TITLE,
        version=VERSION,
        readiness_checks=(
            postgres_readiness(settings, database, timeout_s=READINESS_PROBE_TIMEOUT_S),
        ),
        lifespan=lifespan,
    )
    app.include_router(parts_router)
    app.include_router(features_router)
    app.include_router(assemblies_router)
    return app


app = build_app()


def run() -> None:
    """Serve with uvicorn on the configured port (``python -m documents.main``)."""
    uvicorn.run("documents.main:app", host="0.0.0.0", port=DocumentsSettings().port)


if __name__ == "__main__":
    run()
