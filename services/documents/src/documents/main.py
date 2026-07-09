"""Documents app — boots on the py-kit factory (probes, logging, envelope).

Skeleton stage: no ``/api/v1`` routes and no DB driver yet; the Postgres
schema (alembic) and the first document routes land with the feature-tree
persistence work (docs/ROADMAP.md Phase 1).
"""

import uvicorn
from fastapi import FastAPI
from py_kit import BaseServiceSettings, create_app

TITLE = "Loft Documents"
VERSION = "0.1.0"


class DocumentsSettings(BaseServiceSettings):
    """Documents configuration (env-driven, see ``BaseServiceSettings``)."""

    service_name: str = "documents"
    port: int = 8001


def build_app(settings: DocumentsSettings | None = None) -> FastAPI:
    """Build the documents app with its Postgres readiness check."""
    settings = settings or DocumentsSettings()

    async def postgres() -> str:
        """Postgres readiness.

        Skeleton stage: no DB driver yet (drivers arrive with the alembic
        schema). With ``POSTGRES_URL`` unset the check reports ``"skipped"``
        and ``/readyz`` stays 200. The real connection ping replaces this
        body later — same check name, no probe-API change.
        """
        if settings.postgres_url is None:
            return "skipped"
        return "configured (ping lands with the documents schema)"

    return create_app(
        settings, title=TITLE, version=VERSION, readiness_checks=(postgres,)
    )


app = build_app()


def run() -> None:
    """Serve with uvicorn on the configured port (``python -m documents.main``)."""
    uvicorn.run("documents.main:app", host="0.0.0.0", port=DocumentsSettings().port)


if __name__ == "__main__":
    run()
