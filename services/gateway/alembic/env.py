"""Alembic environment for the gateway schema (Postgres via asyncpg).

Reads ``POSTGRES_URL`` from the environment through the same py-kit settings
model the service uses — no second configuration path. Deliberately does NOT
import :mod:`gateway.main`: that module builds the app at import time
(fail-fast on JWT posture), and migrations must be runnable with database
credentials alone.
"""

import asyncio

from alembic import context
from gateway.db import Base, async_dsn
from py_kit import BaseServiceSettings
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

target_metadata = Base.metadata


def _database_url() -> str:
    url = BaseServiceSettings().postgres_url
    if url is None:
        raise RuntimeError("POSTGRES_URL must be set to run gateway migrations")
    return async_dsn(url)


def run_migrations_offline() -> None:
    """Emit SQL to stdout (``alembic upgrade head --sql``) without a DB."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations over the async engine (asyncpg)."""
    engine = create_async_engine(_database_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
