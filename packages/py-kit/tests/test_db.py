"""py_kit.db — DSN normalization, lifecycle state, session dep, readiness.

Exercised against SQLite/aiosqlite (no Postgres daemon in the sandbox); the
service suites state the dialect split. The plumbing under test here is
dialect-independent.
"""

import asyncio
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from py_kit import BaseServiceSettings, create_app
from py_kit.db import (
    DatabaseState,
    SessionDep,
    async_dsn,
    ping,
    postgres_readiness,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql://u:p@db:5432/loft", "postgresql+asyncpg://u:p@db:5432/loft"),
        ("postgres://u:p@db/loft", "postgresql+asyncpg://u:p@db/loft"),
        ("sqlite:///tmp/x.db", "sqlite+aiosqlite:///tmp/x.db"),
        # Explicit drivers pass through unchanged.
        ("postgresql+asyncpg://u:p@db/loft", "postgresql+asyncpg://u:p@db/loft"),
        ("sqlite+aiosqlite:///x.db", "sqlite+aiosqlite:///x.db"),
    ],
)
def test_async_dsn(url: str, expected: str) -> None:
    assert async_dsn(url) == expected


def test_database_state_start_ping_dispose(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = DatabaseState()
        # Plain equality on purpose: an `is None` assert would let pyright
        # narrow the attributes to None ACROSS the mutating start() call.
        assert (database.engine, database.sessionmaker) == (None, None)

        database.start(f"sqlite:///{tmp_path}/kit.db")
        engine, sessionmaker = database.engine, database.sessionmaker
        assert engine is not None and sessionmaker is not None
        await ping(engine)
        async with sessionmaker() as session:
            result = await session.execute(sa.text("SELECT 1"))
            assert result.scalar_one() == 1

        await database.dispose()
        assert database.engine is None and database.sessionmaker is None
        # Idempotent: disposing an unstarted holder is a no-op.
        await database.dispose()

    asyncio.run(scenario())


def _app_with_db_route(
    settings: BaseServiceSettings, database: DatabaseState
) -> FastAPI:
    app = create_app(
        settings,
        title="t",
        version="0",
        readiness_checks=(postgres_readiness(settings, database),),
    )
    app.state.database = database

    @app.get("/api/v1/probe")
    async def probe(session: SessionDep) -> dict[str, int]:
        result = await session.execute(sa.text("SELECT 1"))
        return {"one": result.scalar_one()}

    return app


def test_get_session_yields_working_session(tmp_path: Path) -> None:
    settings = BaseServiceSettings(postgres_url=f"sqlite:///{tmp_path}/kit.db")
    database = DatabaseState()
    database.start(settings.postgres_url or "")
    app = _app_with_db_route(settings, database)

    response = TestClient(app).get("/api/v1/probe")
    assert response.status_code == 200
    assert response.json() == {"one": 1}

    readyz = TestClient(app).get("/readyz")
    assert readyz.status_code == 200
    assert readyz.json()["checks"]["postgres"] == "ok"


def test_get_session_503_envelope_without_database() -> None:
    settings = BaseServiceSettings(postgres_url=None)
    app = _app_with_db_route(settings, DatabaseState())

    response = TestClient(app).get("/api/v1/probe")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


def test_postgres_readiness_skipped_when_unconfigured() -> None:
    settings = BaseServiceSettings(postgres_url=None)
    app = _app_with_db_route(settings, DatabaseState())
    response = TestClient(app).get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"]["postgres"] == "skipped"


def test_postgres_readiness_fails_when_engine_not_started() -> None:
    """URL configured but lifespan never started the engine → hard 503."""
    settings = BaseServiceSettings(postgres_url="postgresql://u:secret@db/loft")
    app = _app_with_db_route(settings, DatabaseState())
    response = TestClient(app).get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["postgres"] == "error: RuntimeError"
    assert "secret" not in response.text
