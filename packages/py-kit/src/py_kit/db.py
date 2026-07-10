"""Async persistence plumbing shared by DB-backed services.

Extracted on its second real use (gateway users store → documents parts
store, CLAUDE.md DRY rule): DSN normalization, the lifespan-owned
engine/sessionmaker state, the readiness ping + check factory, and the
request-scoped session dependency. Services keep their OWN declarative
``Base`` and models — only the plumbing is shared, so no table metadata ever
leaks across a service boundary through this module.

Dialects: production is PostgreSQL via asyncpg; unit tests run the same code
against SQLite via aiosqlite (each service's test module states that split
honestly). Driver packages (asyncpg / aiosqlite) are declared by the
services and the dev group, not here.
"""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Annotated

import sqlalchemy as sa
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from py_kit.app import ReadinessCheck
from py_kit.config import BaseServiceSettings
from py_kit.errors import ApiError

#: Budget for the readiness ``SELECT 1`` — a probe, not a real query.
DB_PING_TIMEOUT_S = 2.0


def async_dsn(url: str) -> str:
    """Normalize a DSN to its async SQLAlchemy driver form.

    Compose/ops hand services plain ``postgresql://`` URLs (see
    docker-compose.yml); SQLAlchemy needs the ``+asyncpg`` driver marker.
    URLs that already name a ``+driver`` pass through unchanged.
    """
    for prefix, replacement in (
        ("postgresql://", "postgresql+asyncpg://"),
        ("postgres://", "postgresql+asyncpg://"),
        ("sqlite://", "sqlite+aiosqlite://"),
    ):
        if url.startswith(prefix):
            return replacement + url.removeprefix(prefix)
    return url


@dataclass
class DatabaseState:
    """Mutable holder bridging lifespan-owned DB resources to closures.

    ``build_app`` creates readiness-check closures and route dependencies
    before the app (and its lifespan) exists; the lifespan calls
    :meth:`start` on startup and :meth:`dispose` on shutdown.
    """

    engine: AsyncEngine | None = None
    sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def start(self, postgres_url: str) -> None:
        """Create the engine + sessionmaker for *postgres_url* (async driver)."""
        engine = create_async_engine(async_dsn(postgres_url), pool_pre_ping=True)
        self.engine = engine
        self.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def dispose(self) -> None:
        """Dispose the engine (if started) and clear the holder."""
        if self.engine is not None:
            await self.engine.dispose()
        self.engine = None
        self.sessionmaker = None


async def ping(engine: AsyncEngine, timeout_s: float = DB_PING_TIMEOUT_S) -> None:
    """Readiness probe: ``SELECT 1`` within *timeout_s* (raises on failure)."""

    async def select_one() -> None:
        async with engine.connect() as connection:
            await connection.execute(sa.text("SELECT 1"))

    await asyncio.wait_for(select_one(), timeout=timeout_s)


def postgres_readiness(
    settings: BaseServiceSettings,
    database: DatabaseState,
    *,
    timeout_s: float = DB_PING_TIMEOUT_S,
) -> ReadinessCheck:
    """Build the standard HARD postgres readiness check for ``create_app``.

    A DB-backed service cannot serve without its store, so an unreachable
    database takes ``/readyz`` to 503 (the failure detail is the exception
    *type* only — py-kit's probe handler strips messages, a DSN could leak).
    With ``POSTGRES_URL`` unset (bare-uvicorn dev without a DB) the check
    reports ``"skipped"`` and DB-backed routes answer 503 per-request via
    :func:`get_session` instead.
    """

    async def postgres() -> str:
        if settings.postgres_url is None:
            return "skipped"
        if database.engine is None:
            raise RuntimeError("database engine not started")
        await ping(database.engine, timeout_s=timeout_s)
        return "ok"

    return postgres


class DatabaseUnavailableError(ApiError):
    """The service has no database configured/started (HTTP 503)."""

    status_code = 503
    code = "database_unavailable"


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """Yield a request-scoped DB session from the lifespan-owned sessionmaker.

    Requires the service lifespan to have placed a :class:`DatabaseState` on
    ``app.state.database``; without one (``POSTGRES_URL`` unset) every
    DB-backed route answers a 503 envelope instead of crashing.
    """
    database: DatabaseState | None = getattr(request.app.state, "database", None)
    if database is None or database.sessionmaker is None:
        raise DatabaseUnavailableError("Database is not configured; set POSTGRES_URL.")
    async with database.sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
