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
  are exercised for real. When no PostgreSQL binaries are available this
  either SKIPS (a contributor's laptop) or FAILS (CI) — see PGTEST-GATE
  below. When the suite runs as root (sandbox containers), the
  server runs as ``nobody`` via ``runuser`` from a world-writable base dir
  under /tmp — Postgres refuses to run as root.

Per-test databases are cloned from a migrated template database
(``CREATE DATABASE ... TEMPLATE``), so alembic runs once per session.

PGTEST-GATE (2026-08-28) — why this file shouts about ``initdb``
---------------------------------------------------------------
172 of this suite's 468 tests (37%), including the ONLY check that the
alembic chain upgrades, downgrades and matches the models against a real
server, hang off ``pg_server``. Measured: 468 passed with server binaries
present, 296 passed + 172 skipped with ``PG_BIN_DIR=/nonexistent`` — and
**the same exit code (0) both times**, with the dot-line still looking
busy. A gate that cannot fail for the reason it exists is not a gate, so:

- when a real PostgreSQL is REQUIRED (``LOFT_REQUIRE_PG``, defaulting to
  on under ``CI``) and cannot be started, the fixture ``pytest.fail``s
  instead of skipping — the absence is red, not invisible;
- either way the run prints a short ``== postgres (documents suite) ==``
  verdict naming where it searched, what it found, and how many tests were
  actually handed a database. The count is a side effect only real
  execution produces, which is the evidence "did these run in CI?" needs;
  guessing from an image's undocumented contents is what got us here.
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
from typing import Any, NoReturn

import pytest
import sqlalchemy as sa
from _pytest.terminal import TerminalReporter
from alembic import command
from alembic.config import Config
from documents.db import Base
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "services" / "documents" / "alembic.ini"

#: Template database holding the migrated schema; per-test DBs clone it.
TEMPLATE_DB = "loft_template"

#: Embedded in every message this module emits about PostgreSQL availability
#: so the end-of-run verdict can COUNT the affected reports instead of
#: pattern-matching prose that somebody will reword.
PG_MARKER = "[loft-pg]"

#: Env var that makes a real PostgreSQL MANDATORY. Unset, it defaults to
#: ``CI``: automatic, so nobody has to remember it on a new workflow, while
#: the explicit form stays available for the two cases the default gets
#: wrong — a CI-ish environment that genuinely has no server (``=0``), and a
#: local run that wants the CI posture (``=1``).
REQUIRE_PG_ENV = "LOFT_REQUIRE_PG"

_db_counter = itertools.count()

#: Tests handed a REAL PostgreSQL database this session. Incremented by the
#: ``pg_url`` fixture, i.e. a side effect only real execution produces.
_pg_stats: dict[str, int] = {"served": 0}


@dataclass(frozen=True)
class PgBinSearch:
    """Where we looked for server binaries, and what we found."""

    bin_dir: Path | None
    trail: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return self.bin_dir is not None and (self.bin_dir / "initdb").exists()

    def describe(self) -> str:
        where = "<none>" if self.bin_dir is None else str(self.bin_dir)
        found = "FOUND" if self.usable else "MISSING"
        return f"initdb: {found} at {where} (searched: {' -> '.join(self.trail)})"


def search_pg_bin() -> PgBinSearch:
    """Locate PostgreSQL server binaries, recording the search for the log.

    Same order as always (env override, PATH, Debian layout); the trail is
    the addition. It is what turns "the tests skipped" into "the tests
    skipped because /usr/lib/postgresql does not exist on this image".
    """
    trail: list[str] = []
    override = os.environ.get("PG_BIN_DIR")
    if override:
        trail.append(f"PG_BIN_DIR={override}")
        return PgBinSearch(Path(override), tuple(trail))
    trail.append("PG_BIN_DIR unset")
    initdb = shutil.which("initdb")
    if initdb:
        trail.append(f"PATH: {initdb}")
        return PgBinSearch(Path(initdb).parent, tuple(trail))
    trail.append("PATH: no initdb")
    debian = Path("/usr/lib/postgresql")
    versions = sorted(debian.glob("*/bin"), reverse=True) if debian.exists() else []
    if versions:
        trail.append(f"{debian}: {versions[0]}")
        return PgBinSearch(versions[0], tuple(trail))
    trail.append(f"{debian}: nothing")
    return PgBinSearch(None, tuple(trail))


def find_pg_bin() -> Path | None:
    """Locate PostgreSQL server binaries (env override, PATH, Debian layout)."""
    return search_pg_bin().bin_dir


def pg_required(env: dict[str, str] | None = None) -> tuple[bool, str]:
    """Is a real PostgreSQL mandatory for this run, and who said so?

    ``env`` is injectable because this is exactly the kind of subject that
    must not INHERIT ambient state: pytest imports every conftest before it
    runs any test, so a whole-repo run already carries other services'
    ``os.environ`` edits by the time this file is read.
    """
    source = os.environ if env is None else env
    explicit = source.get(REQUIRE_PG_ENV, "").strip()
    if explicit:
        required = explicit.lower() not in {"0", "false", "no", "off"}
        return required, f"{REQUIRE_PG_ENV}={explicit!r}"
    ci = source.get("CI", "").strip()
    if ci and ci.lower() not in {"0", "false", "no", "off"}:
        return True, f"CI={ci!r} ({REQUIRE_PG_ENV} unset)"
    return False, f"not CI, {REQUIRE_PG_ENV} unset"


def _refuse_or_skip(reason: str, search: PgBinSearch) -> NoReturn:
    """Fail when PostgreSQL is required, skip helpfully when it is not.

    ONE LINE, deliberately. pytest repeats a fixture's reason once per
    dependent test in both the errors section and the short summary, so a
    four-line message here becomes ~1400 lines of identical prose for 172
    tests and buries the end-of-run verdict under it. The explanation of
    what to do about it belongs in the verdict, which prints once.
    """
    required, _ = pg_required()
    detail = f"{PG_MARKER} {reason} -- {search.describe()}"
    if required:
        pytest.fail(detail, pytrace=False)
    pytest.skip(f"{detail} [{REQUIRE_PG_ENV}=1 would make this an error]")


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
def pg_required_fn() -> Callable[[dict[str, str] | None], tuple[bool, str]]:
    """``pg_required``, injectable so test_pg_gate.py can exercise it.

    Same reason ``alembic_runner`` exists: under ``--import-mode=importlib``
    a test module cannot import this conftest. A gate needs its own guard,
    and a guard that cannot reach the code it guards is decoration.
    """
    return pg_required


@pytest.fixture(scope="session")
def pg_server() -> Iterator[ScratchPostgres]:
    """Session-scoped scratch PostgreSQL.

    Skips when unavailable and not required; FAILS when required — see the
    PGTEST-GATE note in the module docstring. Every exit routes through
    ``_refuse_or_skip`` so a future third way to be unusable inherits the
    refusal automatically rather than reintroducing a silent skip.
    """
    search = search_pg_bin()
    if not search.usable:
        _refuse_or_skip("no PostgreSQL server binaries found", search)
    bin_dir = search.bin_dir
    assert bin_dir is not None  # `search.usable` implies it; narrows the type
    run_prefix: list[str] = []
    if os.geteuid() == 0:
        # initdb/postgres refuse to run as root; drop to nobody. The base
        # dir must live under a path nobody can traverse (pytest tmp dirs
        # are 0700 root), hence tempfile's default /tmp.
        if shutil.which("runuser") is None:
            _refuse_or_skip("running as root and runuser is unavailable", search)
        run_prefix = ["runuser", "-u", "nobody", "--"]
    base_dir = Path(tempfile.mkdtemp(prefix="loft-pg-"))
    base_dir.chmod(0o777)
    server = ScratchPostgres(bin_dir=bin_dir, base_dir=base_dir, run_prefix=run_prefix)
    error = server.start()
    if error is not None:
        shutil.rmtree(base_dir, ignore_errors=True)
        _refuse_or_skip(f"scratch PostgreSQL would not start: {error}", search)
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
    _pg_stats["served"] += 1
    return pg_server.url(name)


def _marked(reports: list[Any]) -> int:
    """How many of *reports* carry this module's PostgreSQL marker."""
    return sum(
        1 for report in reports if PG_MARKER in str(getattr(report, "longrepr", ""))
    )


def _verdict_lines(reporter: TerminalReporter | None) -> list[str]:
    """The whole PostgreSQL story for this run, in five lines or fewer.

    Two counts, derived independently: ``served`` from a fixture side effect
    that only real execution produces, ``skipped``/``refused`` from the
    reports pytest collected. When they contradict each other the block says
    so instead of picking a winner — a summary that quietly guesses is how a
    wrong number gets believed.
    """
    search = search_pg_bin()
    required, why = pg_required()
    stats: dict[str, list[Any]] = {} if reporter is None else reporter.stats
    skipped = _marked(stats.get("skipped", []))
    refused = _marked(stats.get("error", [])) + _marked(stats.get("failed", []))
    served = _pg_stats["served"]

    lines = [
        "== postgres (documents suite) ==",
        search.describe(),
        f"required: {'YES' if required else 'no'} ({why})",
        f"served a real database: {served}; skipped for want of one: "
        f"{skipped}; refused: {refused}",
    ]
    if refused:
        lines.append(
            f"REFUSED: a real PostgreSQL is required here and none could be "
            f"started, so {refused} tests (the alembic up/down chain among "
            f"them) did NOT run. Install postgresql, point PG_BIN_DIR at its "
            f"bin dir, or set {REQUIRE_PG_ENV}=0 to accept the loss knowingly."
        )
    elif skipped:
        lines.append(
            f"WARNING: {skipped} test(s) did not run for want of a real "
            f"PostgreSQL server. A full documents run skips 172 that way -- "
            f"37% of the suite, including every real-server migration check. "
            f"The exit code cannot tell you that; this line can."
        )
    # Cross-checks. Binaries found and pg tests not running are mutually
    # exclusive, and so are binaries missing and tests served.
    if search.usable and (skipped or refused):
        lines.append(
            "INCONSISTENT: binaries were found yet pg tests did not run -- "
            "trust neither count until checked (server start? permissions?)"
        )
    elif not search.usable and served:
        lines.append(
            "INCONSISTENT: no binaries were found yet tests were served a "
            "database -- trust neither count until checked"
        )
    elif search.usable and served == 0:
        lines.append(
            "NOTE: no test asked for a database this run -- expected only for "
            "a narrow selection; a full documents run serves 172"
        )
    return lines


def pytest_unconfigure(config: pytest.Config) -> None:
    """Emit the verdict AFTER everything else pytest prints.

    Not ``pytest_terminal_summary``: that hook runs before the short test
    summary, and with 172 refusals the summary is ~700 lines, so the verdict
    landed at line 870 of 1563 and a fixed ``tail_lines`` read could never
    reach it (measured — the exact trap CLAUDE.md records for e2e shards).
    ``pytest_unconfigure`` runs after the reporter's final stats line, so a
    small tail always finds this block.
    """
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    lines = _verdict_lines(reporter if isinstance(reporter, TerminalReporter) else None)
    print("\n" + "\n".join(lines))


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
