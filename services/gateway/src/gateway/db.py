"""Gateway persistence — async SQLAlchemy engine, session plumbing, models.

The gateway owns the identity store (users) per RESEARCH §3 — auth is a
gateway concern, so users live HERE, not in the documents service. Schema
changes ship as alembic migrations under ``services/gateway/alembic``
(CLAUDE.md: migrations only, no ad-hoc SQL); the ORM metadata below is the
single source those migrations are written from.

Dialects: production is PostgreSQL via asyncpg. The column types are chosen
to be dialect-portable (``sa.Uuid``, ``DateTime(timezone=True)``) so the unit
tests can run the same code paths against SQLite/aiosqlite in sandboxes
without a Postgres daemon — see ``tests/test_auth.py`` for the honest
statement of that split.
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Budget for the readiness ``SELECT 1`` — a probe, not a real query.
DB_PING_TIMEOUT_S = 2.0

#: RFC 5321 upper bound for a full email address.
EMAIL_MAX_LENGTH = 320

#: Generous bound for the argon2 encoded hash string (current output ~97 ch).
PASSWORD_HASH_MAX_LENGTH = 255


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


class Base(DeclarativeBase):
    """Declarative base for all gateway-owned tables."""


class User(Base):
    """An account — email/password identity, argon2 hash at rest.

    ``email`` is stored lowercase-normalized (done at the route layer) and
    unique; the constraint — not a racy pre-check — is what enforces
    one-account-per-email. The plaintext password never touches this model.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        sa.String(EMAIL_MAX_LENGTH), unique=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        sa.String(PASSWORD_HASH_MAX_LENGTH), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        """Identify the row WITHOUT the hash — keep secrets out of any log."""
        return f"User(id={self.id!r}, email={self.email!r})"


@dataclass
class DatabaseState:
    """Mutable holder bridging lifespan-owned resources to closures.

    ``build_app`` creates readiness-check closures before the app (and its
    lifespan) exists; the lifespan fills this in on startup and clears it on
    shutdown.
    """

    engine: AsyncEngine | None = None
    sessionmaker: async_sessionmaker[AsyncSession] | None = None


def create_database(postgres_url: str) -> DatabaseState:
    """Create the engine + sessionmaker for *postgres_url* (async driver)."""
    engine = create_async_engine(async_dsn(postgres_url), pool_pre_ping=True)
    return DatabaseState(
        engine=engine,
        sessionmaker=async_sessionmaker(engine, expire_on_commit=False),
    )


async def ping(engine: AsyncEngine, timeout_s: float = DB_PING_TIMEOUT_S) -> None:
    """Readiness probe: ``SELECT 1`` within *timeout_s* (raises on failure)."""

    async def select_one() -> None:
        async with engine.connect() as connection:
            await connection.execute(sa.text("SELECT 1"))

    await asyncio.wait_for(select_one(), timeout=timeout_s)
