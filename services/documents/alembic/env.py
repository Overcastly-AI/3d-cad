"""Alembic environment for the documents schema — shared py-kit env glue.

Imports only :mod:`documents.db` (the metadata), never ``documents.main``:
migrations must be runnable with database credentials alone. Everything else
(offline/online modes, POSTGRES_URL via the py-kit settings model, asyncpg
engine) lives once in :mod:`py_kit.alembic_env`.
"""

from documents.db import Base
from py_kit.alembic_env import run_migrations

run_migrations(Base.metadata)
