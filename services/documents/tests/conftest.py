"""Shared documents test fixtures — SQLite always, real PostgreSQL when possible.

Dialect posture for the feature-tree suite (extends the split stated in
tests/test_parts.py):

- ``sqlite`` — file-per-test DB, schema from the ORM metadata
  (``create_all``), FK enforcement ON via the shared py-kit pragma. Two
  Postgres-only DDL clauses are absent by SQLite limitation (deferrable
  UNIQUE, the composite rollback FK — documented in documents/db.py); the
  deferrable target-side FK on ``feature_dependencies`` IS present and
  enforced, so deferred-at-commit semantics are exercised even here.
- ``postgres`` — a REAL scratch PostgreSQL 16 server (``initdb`` + unix
  socket only, no TCP), schema applied by the ACTUAL alembic migrations
  (0001 + 0002), so model/migration lockstep and the full §1.2 DDL
  (deferrable unique, composite FKs, ``SET NULL (rollback_feature_id)``)
  are exercised for real. Skips with a reason when no PostgreSQL binaries
  are available. When the suite runs as root (sandbox containers), the
  server runs as ``nobody`` via ``runuser`` from a world-writable base dir
  under /tmp — Postgres refuses to run as root.

Per-test databases are cloned from a migrated template database
(``CREATE DATABASE ... TEMPLATE``), so alembic runs once per session.
"""

import asyncio
import itertools
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from documents.db import Base
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "services" / "documents" / "alembic.ini"

#: Template database holding the migrated schema; per-test DBs clone it.
TEMPLATE_DB = "loft_template"

_db_counter = itertools.count()


def find_pg_bin() -> Path | None:
    """Locate PostgreSQL server binaries (env override, PATH, Debian layout)."""
    override = os.environ.get("PG_BIN_DIR")
    if override:
        return Path(override)
    initdb = shutil.which("initdb")
    if initdb:
        return Path(initdb).parent
    debian = Path("/usr/lib/postgresql")
    if debian.exists():
        versions = sorted(debian.glob("*/bin"), reverse=True)
        if versions:
            return versions[0]
    return None


@dataclass
class ScratchPostgres:
    """A throwaway PostgreSQL server reachable via unix socket only."""

    bin_dir: Path
    base_dir: Path
    run_prefix: list[str]

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    def url(self, database: str) -> str:
        # Socket-directory DSN; asyncpg treats a leading-slash host as a
        # socket dir. Default port 5432 only names the socket file — there
        # is no TCP listener.
        return f"postgresql://loft@/{database}?host={self.base_dir}"

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*self.run_prefix, *args], capture_output=True, text=True, check=False
        )

    def start(self) -> str | None:
        """Init + start; returns an error string on failure (→ skip)."""
        initdb = self.run(
            str(self.bin_dir / "initdb"),
            "-D",
            str(self.data_dir),
            "-U",
            "loft",
            "--auth=trust",
            "-N",
        )
        if initdb.returncode != 0:
            return f"initdb failed: {initdb.stderr.strip()[:500]}"
        pg_ctl = self.run(
            str(self.bin_dir / "pg_ctl"),
            "-w",
            "-D",
            str(self.data_dir),
            "-o",
            f"-k {self.base_dir} -c listen_addresses='' -F",
            "-l",
            str(self.base_dir / "server.log"),
            "start",
        )
        if pg_ctl.returncode != 0:
            return f"pg_ctl start failed: {pg_ctl.stderr.strip()[:500]}"
        return None

    def stop(self) -> None:
        self.run(
            str(self.bin_dir / "pg_ctl"),
            "-D",
            str(self.data_dir),
            "stop",
            "-m",
            "immediate",
        )
        shutil.rmtree(self.base_dir, ignore_errors=True)


def _execute_autocommit(url: str, statement: str) -> None:
    async def run() -> None:
        engine = create_async_engine(async_dsn(url), isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                await connection.execute(sa.text(statement))
        finally:
            await engine.dispose()

    asyncio.run(run())


def run_alembic(url: str, revision: str = "head", *, downgrade: bool = False) -> None:
    """Run migrations in-process against *url* (env-driven like production)."""
    config = Config(str(ALEMBIC_INI))
    previous = os.environ.get("POSTGRES_URL")
    os.environ["POSTGRES_URL"] = url
    try:
        if downgrade:
            command.downgrade(config, revision)
        else:
            command.upgrade(config, revision)
    finally:
        if previous is None:
            os.environ.pop("POSTGRES_URL", None)
        else:
            os.environ["POSTGRES_URL"] = previous


@pytest.fixture(scope="session")
def alembic_ini() -> Path:
    """Path to the documents alembic config (fixture: test modules cannot
    import conftest under ``--import-mode=importlib`` without packages)."""
    return ALEMBIC_INI


@pytest.fixture(scope="session")
def alembic_runner() -> Callable[..., None]:
    """The in-process migration runner, injectable into test modules."""
    return run_alembic


@pytest.fixture(scope="session")
def pg_server() -> Iterator[ScratchPostgres]:
    """Session-scoped scratch PostgreSQL (skips when unavailable)."""
    bin_dir = find_pg_bin()
    if bin_dir is None or not (bin_dir / "initdb").exists():
        pytest.skip("no PostgreSQL server binaries found (set PG_BIN_DIR)")
    run_prefix: list[str] = []
    if os.geteuid() == 0:
        # initdb/postgres refuse to run as root; drop to nobody. The base
        # dir must live under a path nobody can traverse (pytest tmp dirs
        # are 0700 root), hence tempfile's default /tmp.
        if shutil.which("runuser") is None:
            pytest.skip("running as root and runuser is unavailable")
        run_prefix = ["runuser", "-u", "nobody", "--"]
    base_dir = Path(tempfile.mkdtemp(prefix="loft-pg-"))
    base_dir.chmod(0o777)
    server = ScratchPostgres(bin_dir=bin_dir, base_dir=base_dir, run_prefix=run_prefix)
    error = server.start()
    if error is not None:
        shutil.rmtree(base_dir, ignore_errors=True)
        pytest.skip(f"scratch PostgreSQL unavailable: {error}")
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture(scope="session")
def pg_template(pg_server: ScratchPostgres) -> str:
    """Create + migrate the template database once per session."""
    _execute_autocommit(pg_server.url("postgres"), f"CREATE DATABASE {TEMPLATE_DB}")
    run_alembic(pg_server.url(TEMPLATE_DB))
    return TEMPLATE_DB


@pytest.fixture
def pg_url(pg_server: ScratchPostgres, pg_template: str) -> str:
    """A fresh per-test database cloned from the migrated template."""
    name = f"loft_test_{next(_db_counter)}"
    _execute_autocommit(
        pg_server.url("postgres"), f"CREATE DATABASE {name} TEMPLATE {pg_template}"
    )
    return pg_server.url(name)


async def _create_sqlite_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture(params=["sqlite", "postgres"])
def any_db_url(request: pytest.FixtureRequest, tmp_path: Path) -> str:
    """The same application code against both dialects (module docstring)."""
    if request.param == "sqlite":
        url = f"sqlite:///{tmp_path}/documents.db"
        asyncio.run(_create_sqlite_schema(url))
        return url
    result: str = request.getfixturevalue("pg_url")
    return result
