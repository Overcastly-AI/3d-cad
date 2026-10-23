"""The ``/tmp/loft-pg-*`` sweep, on fake clusters and fake servers.

Every directory lives under ``tmp_path`` and every "server" is a Python
process whose argv reads ``postgres -c ... -D <dir>``: nothing here touches a
real cluster or the real tempdir.
"""

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from py_kit import pg_scratch

OLD = 10 * pg_scratch.UNOWNED_GRACE_S


def _cluster(root: Path, name: str, *, age_s: float = OLD) -> Path:
    base = root / f"{pg_scratch.PREFIX}{name}"
    (base / "data").mkdir(parents=True)
    (base / "data" / "PG_VERSION").write_text("16\n")
    stamp = time.time() - age_s
    os.utime(base, (stamp, stamp))
    return base


def _pidfile(base: Path, pid: int) -> None:
    (base / "data" / "postmaster.pid").write_text(f"{pid}\n{base / 'data'}\n")


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


@pytest.fixture
def fake_server() -> Iterator[list[subprocess.Popen[bytes]]]:
    """Fake servers started by a test; always reaped afterwards."""
    procs: list[subprocess.Popen[bytes]] = []
    yield procs
    for proc in procs:
        proc.kill()
        proc.wait()


def _spawn_postgres(data_dir: Path, procs: list[subprocess.Popen[bytes]]) -> int:
    proc = subprocess.Popen(
        ["postgres", "-c", "import time; time.sleep(120)", "-D", str(data_dir)],
        executable=sys.executable,
    )
    procs.append(proc)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if pg_scratch.is_postmaster_for(pg_scratch.process_argv(proc.pid), data_dir):
            return proc.pid
        time.sleep(0.02)
    raise AssertionError("fake postgres never showed its argv")


def _refuse_stop(pid: int, data_dir: Path) -> None:
    pytest.fail(f"stopped a live run: pid {pid} on {data_dir}")


def test_unowned_cluster_without_server_is_removed(tmp_path: Path) -> None:
    base = _cluster(tmp_path, "nopid")
    result = pg_scratch.sweep(tmp_path)
    assert result.removed == [base]
    assert not base.exists()


def test_pidfile_naming_dead_or_foreign_process_is_stale(tmp_path: Path) -> None:
    dead = _cluster(tmp_path, "dead")
    _pidfile(dead, _dead_pid())
    foreign = _cluster(tmp_path, "foreign")
    _pidfile(foreign, os.getpid())  # alive, but this is pytest, not postgres
    result = pg_scratch.sweep(tmp_path)
    assert sorted(result.removed) == sorted([dead, foreign])
    assert not dead.exists() and not foreign.exists()


def test_live_owner_is_kept_even_before_its_server_starts(tmp_path: Path) -> None:
    base = _cluster(tmp_path, "live")
    pg_scratch.write_owner(base)
    result = pg_scratch.sweep(tmp_path)
    assert result.kept == [base] and result.removed == []
    assert base.exists()


def test_young_unowned_cluster_is_kept(tmp_path: Path) -> None:
    """An older harness between mkdtemp and initdb looks exactly like this."""
    base = _cluster(tmp_path, "young", age_s=1)
    assert pg_scratch.sweep(tmp_path).kept == [base]


def test_recycled_owner_pid_counts_as_dead(tmp_path: Path) -> None:
    base = _cluster(tmp_path, "recycled")
    (base / pg_scratch.OWNER_FILE).write_text(
        json.dumps({"pid": os.getpid(), "start": "not-our-start-time"})
    )
    assert pg_scratch.owner_alive(base) is False
    assert pg_scratch.sweep(tmp_path).removed == [base]


def test_orphaned_server_with_dead_owner_is_stopped(
    tmp_path: Path, fake_server: list[subprocess.Popen[bytes]]
) -> None:
    base = _cluster(tmp_path, "orphan", age_s=0)
    pg_scratch.write_owner(base, pid=_dead_pid())
    pid = _spawn_postgres(base / "data", fake_server)
    _pidfile(base, pid)

    result = pg_scratch.sweep(tmp_path)

    assert result.stopped == [base] and result.removed == [base]
    assert fake_server[0].wait(timeout=5) != 0  # it was signalled, not left running
    assert not base.exists()


def test_running_server_with_live_owner_is_untouched(
    tmp_path: Path, fake_server: list[subprocess.Popen[bytes]]
) -> None:
    base = _cluster(tmp_path, "running")
    pg_scratch.write_owner(base)
    _pidfile(base, _spawn_postgres(base / "data", fake_server))
    result = pg_scratch.sweep(tmp_path, stop=_refuse_stop)
    assert result.kept == [base]
    assert fake_server[0].poll() is None


def test_running_server_with_unknown_owner_is_untouched(
    tmp_path: Path, fake_server: list[subprocess.Popen[bytes]]
) -> None:
    """No owner record: could be a live run of the old harness. Keep it."""
    base = _cluster(tmp_path, "legacy")
    _pidfile(base, _spawn_postgres(base / "data", fake_server))
    result = pg_scratch.sweep(tmp_path, stop=_refuse_stop)
    assert result.kept == [base]
    assert fake_server[0].poll() is None


def test_only_prefixed_directories_are_considered(tmp_path: Path) -> None:
    other = tmp_path / "not-loft-pg-x"
    other.mkdir()
    (tmp_path / f"{pg_scratch.PREFIX}file").write_text("not a dir")
    assert pg_scratch.sweep(tmp_path).removed == []
    assert other.exists()


def test_postmaster_identity_requires_postgres_and_matching_dir(tmp_path: Path) -> None:
    data = tmp_path / "data"
    assert pg_scratch.is_postmaster_for(["/usr/bin/postgres", "-D", str(data)], data)
    assert pg_scratch.is_postmaster_for(["postgres", f"-D{data}"], data)
    assert not pg_scratch.is_postmaster_for(["postgres", "-D", str(tmp_path)], data)
    assert not pg_scratch.is_postmaster_for(["python", "-D", str(data)], data)
    assert not pg_scratch.is_postmaster_for([], data)


def test_server_options_cap_wal_and_keep_socket_only(tmp_path: Path) -> None:
    options = pg_scratch.server_options(tmp_path)
    assert f"-k {tmp_path}" in options and "listen_addresses=''" in options
    for setting in ("fsync=off", "wal_level=minimal", "max_wal_size=64MB"):
        assert f"-c {setting}" in options
