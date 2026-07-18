"""Alembic environment for the gateway schema — shared py-kit env glue.

Imports only :mod:`gateway.db` (the metadata), never ``gateway.main``: that
module builds the app at import time (fail-fast on JWT posture), and
migrations must be runnable with database credentials alone. Everything else
(offline/online modes, POSTGRES_URL via the py-kit settings model, asyncpg
engine) lives once in :mod:`py_kit.alembic_env`.
"""

from gateway.db import Base
from py_kit.alembic_env import run_migrations

run_migrations(Base.metadata)
