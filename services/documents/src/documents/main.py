"""Documents app — boots on the py-kit factory (probes, logging, envelope).

``/api/v1`` surface: parts CRUD (:mod:`documents.parts`), the ordered feature
tree (:mod:`documents.features`, per docs/design/feature-tree.md), assembly
CRUD (:mod:`documents.assemblies`, per docs/design/assemblies.md — a graph of
instances + mates), and drawing CRUD (:mod:`documents.drawings`, per
docs/design/drawings.md — a layout of sheets/views/dimensions/annotations),
folder filing (:mod:`documents.folders`, per py_kit.schemas.folders — a
per-drawer tree plus the document MOVE routes), plus the static material
library (:mod:`documents.materials`, per
docs/design/materials.md — densities served so nothing hardcodes one),
backed by Postgres via the shared :mod:`py_kit.db` plumbing with the schema
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
from documents.drawings import router as drawings_router
from documents.duplicate import assemblies_router as duplicate_assemblies_router
from documents.duplicate import drawings_router as duplicate_drawings_router
from documents.duplicate import parts_router as duplicate_parts_router
from documents.features import router as features_router
from documents.folders import assemblies_router as folder_assemblies_router
from documents.folders import drawings_router as folder_drawings_router
from documents.folders import parts_router as folder_parts_router
from documents.folders import router as folders_router
from documents.materials import router as materials_router
from documents.parts import router as parts_router
from documents.step_import import router as step_import_router

TITLE = "Loft Documents"
VERSION = "0.1.0"

#: Readiness-probe budget for the ``SELECT 1`` ping.
READINESS_PROBE_TIMEOUT_S = 2.0


class DocumentsSettings(BaseServiceSettings):
    """Documents configuration (env-driven, see ``BaseServiceSettings``).

    ``POSTGRES_URL`` is inherited, and so is py-kit's dev-credential guard:
    constructing these settings with the repo-public compose password
    embedded in the DSN raises unless ``LOFT_ENV=dev``, so this service
    refuses to boot against an unsecured store rather than serving from it.
    """

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
    app.include_router(materials_router)
    app.include_router(assemblies_router)
    app.include_router(drawings_router)
    app.include_router(step_import_router)
    # Workspace management (:mod:`documents.duplicate`) — one module, three
    # routers, so the id-remap and the copy-naming rule are written once.
    app.include_router(duplicate_parts_router)
    app.include_router(duplicate_assemblies_router)
    app.include_router(duplicate_drawings_router)
    # Filing (:mod:`documents.folders`) — the folder tree plus the three
    # document MOVE routes, one implementation behind three registrations for
    # the same reason ``duplicate`` is one module.
    app.include_router(folders_router)
    app.include_router(folder_parts_router)
    app.include_router(folder_assemblies_router)
    app.include_router(folder_drawings_router)
    return app


app = build_app()


def run() -> None:
    """Serve with uvicorn on the configured port (``python -m documents.main``)."""
    uvicorn.run("documents.main:app", host="0.0.0.0", port=DocumentsSettings().port)


if __name__ == "__main__":
    run()
