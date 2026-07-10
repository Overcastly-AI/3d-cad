"""Shared alembic ``env.py`` body (second real use: gateway → documents).

Each DB-backed service keeps its own alembic tree (its schema is its own —
CLAUDE.md service boundaries) but the env glue is identical, so it lives here
once. A service's ``alembic/env.py`` stays a two-liner::

    from <service>.db import Base
    from py_kit.alembic_env import run_migrations

    run_migrations(Base.metadata)

The database URL is read from ``POSTGRES_URL`` through the same py-kit
settings model the services use — no second configuration path. This module
never imports a service's app module: migrations must be runnable with
database credentials alone (e.g. ``gateway.main`` fail-fasts on JWT posture
at import time).
"""

import asyncio

from sqlalchemy import Connection, MetaData
from sqlalchemy.ext.asyncio import create_async_engine

from py_kit.config import BaseServiceSettings
from py_kit.db import async_dsn


def _database_url() -> str:
    url = BaseServiceSettings().postgres_url
    if url is None:
        raise RuntimeError("POSTGRES_URL must be set to run migrations")
    return async_dsn(url)


def run_migrations(target_metadata: MetaData) -> None:
    """Run the calling service's migrations (offline ``--sql`` or online).

    Only callable from an alembic ``env.py`` — the ``alembic.context`` proxy
    is populated exclusively by the alembic runtime, hence the local import.
    """
    from alembic import context

    if context.is_offline_mode():
        # Emit SQL to stdout (``alembic upgrade head --sql``) without a DB.
        context.configure(
            url=_database_url(),
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    def run_sync(connection: Connection) -> None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    async def run_online() -> None:
        engine = create_async_engine(_database_url())
        try:
            async with engine.connect() as connection:
                await connection.run_sync(run_sync)
        finally:
            await engine.dispose()

    asyncio.run(run_online())
