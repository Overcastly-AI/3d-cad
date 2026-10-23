"""Leak-proofing for throwaway test PostgreSQL clusters (``/tmp/loft-pg-*``).

The documents suite boots a scratch server per pytest session. Its fixture
teardown never runs when the test process is SIGKILLed (a ``timeout``
wrapper, a container restart), so the data directory stays behind and the
server, daemonised by ``pg_ctl``, keeps running and keeps it pinned. On
2026-10-23 twenty of them (0.8-4.1 GB each) filled the sandbox disk twice.

Three layers, all here so they can be tested without a real server:

- :func:`write_owner` records which process owns a cluster, at creation.
- :func:`sweep` runs at the start of the next session and removes clusters
  whose owner is gone, stopping an orphaned server first. It never touches a
  cluster whose owner is alive, nor (conservatively) a running server whose
  owner it cannot identify.
- :data:`THROWAWAY_SETTINGS` keeps a cluster small while it lives.

Stdlib only: this is imported by conftests, not by services.
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PREFIX = "loft-pg-"

#: Written into the cluster's base dir by the process that created it.
OWNER_FILE = "owner.json"

#: A cluster with no owner record and no server is left alone this long: it
#: may belong to an older harness that is still between ``mkdtemp`` and
#: ``initdb`` finishing.
UNOWNED_GRACE_S = 300.0

#: Server settings for a cluster nobody will ever recover. Durability is
#: worthless here, and the defaults let WAL alone grow to ``max_wal_size``
#: (1 GB): ``CREATE DATABASE ... TEMPLATE`` WAL-logs the whole template.
THROWAWAY_SETTINGS: dict[str, str] = {
    "fsync": "off",
    "full_page_writes": "off",
    "synchronous_commit": "off",
    "wal_level": "minimal",
    "max_wal_senders": "0",
    "max_wal_size": "64MB",
    "min_wal_size": "32MB",
}


def server_options(socket_dir: Path) -> str:
    """The ``pg_ctl -o`` string: unix socket only, throwaway settings."""
    settings = " ".join(
        f"-c {key}={value}" for key, value in THROWAWAY_SETTINGS.items()
    )
    return f"-k {socket_dir} -c listen_addresses='' {settings}"


# --------------------------------------------------------------------------
# Process identity
# --------------------------------------------------------------------------


def process_start_time(pid: int) -> str | None:
    """An opaque token that changes when *pid* is reused, or None if dead.

    Linux: field 22 of ``/proc/<pid>/stat`` (start time in clock ticks).
    Elsewhere: ``ps -o lstart``. A PID alone is not an identity — the
    sandbox recycles them quickly, and a recycled owner PID would make an
    orphan look owned forever.
    """
    if pid <= 0:
        return None
    stat = Path(f"/proc/{pid}/stat")
    if Path("/proc/self/stat").exists():
        try:
            raw = stat.read_text()
        except OSError:
            return None
        # comm (field 2) may contain spaces/parens; split after the last ')'.
        fields = raw[raw.rfind(")") + 2 :].split()
        return fields[19] if len(fields) > 19 else None
    result = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
    )
    token = result.stdout.strip()
    return token or None


def process_argv(pid: int) -> list[str] | None:
    """argv of *pid*, or None when it does not exist."""
    cmdline = Path(f"/proc/{pid}/cmdline")
    if Path("/proc/self/cmdline").exists():
        try:
            raw = cmdline.read_bytes()
        except OSError:
            return None
        return [part.decode(errors="replace") for part in raw.split(b"\0") if part]
    result = subprocess.run(
        ["ps", "-o", "command=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.split() or None


def is_postmaster_for(argv: list[str] | None, data_dir: Path) -> bool:
    """Is *argv* ``postgres ... -D <data_dir>``?"""
    if not argv or Path(argv[0]).name != "postgres":
        return False
    target = os.path.realpath(data_dir)
    for flag, value in itertools.pairwise(argv):
        if flag == "-D" and os.path.realpath(value) == target:
            return True
    return any(
        arg.startswith("-D") and os.path.realpath(arg[2:]) == target for arg in argv
    )


# --------------------------------------------------------------------------
# Owner record
# --------------------------------------------------------------------------


def write_owner(base_dir: Path, pid: int | None = None) -> None:
    """Record the owning process (pid + start time) in *base_dir*."""
    owner = os.getpid() if pid is None else pid
    record = {"pid": owner, "start": process_start_time(owner)}
    path = base_dir / OWNER_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record))
    tmp.replace(path)


def owner_alive(base_dir: Path) -> bool | None:
    """True/False for a recorded owner; None when there is no usable record."""
    try:
        record = json.loads((base_dir / OWNER_FILE).read_text())
        pid = int(record["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    start = process_start_time(pid)
    if start is None:
        return False
    recorded = record.get("start")
    return recorded is None or recorded == start


# --------------------------------------------------------------------------
# Server state
# --------------------------------------------------------------------------


def live_postmaster(data_dir: Path) -> int | None:
    """PID of the server running on *data_dir*, or None.

    ``postmaster.pid`` alone proves nothing after a crash: it outlives the
    server, and its PID may since have been handed to something else. Only
    a process that IS ``postgres -D <data_dir>`` counts.
    """
    try:
        first = (data_dir / "postmaster.pid").read_text().splitlines()[0]
        pid = int(first.strip())
    except (OSError, ValueError, IndexError):
        return None
    return pid if is_postmaster_for(process_argv(pid), data_dir) else None


def stop_postmaster(pid: int, data_dir: Path, timeout_s: float = 10.0) -> None:
    """Immediate shutdown (SIGQUIT), escalating to SIGKILL.

    Signals rather than ``pg_ctl``: as root the sweep cannot run ``pg_ctl``
    (Postgres refuses root) and the server's user may differ from ours.
    Re-checks identity before each signal so a recycled PID is never hit.
    """
    for sig in (signal.SIGQUIT, signal.SIGKILL):
        if not is_postmaster_for(process_argv(pid), data_dir):
            return
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not is_postmaster_for(process_argv(pid), data_dir):
                return
            time.sleep(0.05)


# --------------------------------------------------------------------------
# Sweep
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SweepResult:
    removed: list[Path]
    stopped: list[Path]
    kept: list[Path]


def sweep(
    root: Path | None = None,
    *,
    data_subdir: str = "data",
    grace_s: float = UNOWNED_GRACE_S,
    stop: Callable[[int, Path], None] = stop_postmaster,
    now: float | None = None,
) -> SweepResult:
    """Remove stale ``loft-pg-*`` clusters under *root* (default: tempdir).

    Per directory:

    - owner recorded and alive -> keep (a live run, whatever its state);
    - owner recorded and dead -> stop its server if one is running, remove;
    - no owner record, server running -> keep: it may be a live run of an
      older harness, and killing a live run is worse than a leak;
    - no owner record, no server -> remove once older than *grace_s*.
    """
    base = Path(tempfile.gettempdir()) if root is None else root
    clock = time.time() if now is None else now
    removed: list[Path] = []
    stopped: list[Path] = []
    kept: list[Path] = []
    try:
        candidates = sorted(base.glob(f"{PREFIX}*"))
    except OSError:
        candidates = []
    for directory in candidates:
        if directory.is_symlink() or not directory.is_dir():
            continue
        data_dir = directory / data_subdir
        alive = owner_alive(directory)
        if alive:
            kept.append(directory)
            continue
        server = live_postmaster(data_dir)
        if alive is None:
            if server is not None:
                kept.append(directory)
                continue
            try:
                age = clock - directory.stat().st_mtime
            except OSError:
                continue
            if age < grace_s:
                kept.append(directory)
                continue
        elif server is not None:
            stop(server, data_dir)
            stopped.append(directory)
        shutil.rmtree(directory, ignore_errors=True)
        removed.append(directory)
    return SweepResult(removed=removed, stopped=stopped, kept=kept)
