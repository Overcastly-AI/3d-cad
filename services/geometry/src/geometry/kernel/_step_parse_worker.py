"""Out-of-process STEP parse — the hard CPU-time + wall-clock KILL boundary (§6).

Run as ``python -m geometry.kernel._step_parse_worker <in> <out> <cpu_seconds>``.
The parent (:func:`geometry.kernel.imports.import_step_solid`) spawns this with a
**CPU-time** ceiling (``resource.setrlimit(RLIMIT_CPU, …)`` applied HERE, in the
child, before any OCCT work) *and* a generous **wall-clock** liveness backstop
(``subprocess.run(..., timeout=…)`` in the parent), so a degenerate/adversarial
part-21 whose OCCT transfer is super-linear is killed and reaped, never pinning a
FastAPI threadpool worker (BACKLOG P1, docs/design/step-import.md §6).

**Why the CPU-time ceiling is the primary bound (2026-07-19).** A pure wall-clock
bound conflates the parse's *work* with the machine's *load*: under CPU
contention (parallel CI/worktrees) a legit ~1 s parse can take many seconds of
WALL time while burning the same ~1 s of CPU, so a tight wall bound false-fires
on a slow-but-legitimate import. ``RLIMIT_CPU`` bounds the CPU seconds the child
actually consumes — invariant to how starved its wall-clock is — so a legit parse
never trips it regardless of load, while an adversarial parse that genuinely
burns CPU is still capped. The wall-clock backstop remains only to kill a child
that is *wedged* (blocked, not CPU-burning); it is sized so it, too, never fires
on a legit parse. On CPU exhaustion the kernel sends ``SIGXCPU`` (soft) then
``SIGKILL`` (hard = soft+1); the parent maps either signal to
``import_parse_timeout``.

This module imports **only OCP** — never build123d — on purpose: build123d's
import graph adds ~2.5 s of cold-start to every spawn, while the raw OCCT
reader/writer is ~0.85 s. The untrusted work done here is exactly the two
unbounded-time OCCT calls (``ReadFile`` → ``TransferRoots``); everything
legible — the null / single-solid taxonomy — stays in the parent where it is
tested and can use build123d.

The result crosses the process boundary as a BREP file (OCCT's native, lossless
serialization): the parent reads it back and runs the topology checks. Units are
pinned to millimetres HERE, in the fresh process, so the read is independent of
any ambient ``Interface_Static`` state — the determinism guarantee is actually
stronger than the in-process path it replaces (RESEARCH §9).

Exit codes are the protocol: ``0`` = a shape (possibly null / a compound) was
written; :data:`EXIT_PARSE_FAILED` = OCCT could not read or transfer the bytes.
A SIGKILL (timeout) or any other nonzero exit is treated by the parent as a
parse failure / timeout — a crash in untrusted parsing is never a 500.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

import math
import sys

#: Exit code when OCCT cannot read/transfer the payload (→ ``ImportParseError``).
#: Distinct from 0 (wrote a shape) and from a SIGKILL/other crash (the parent
#: maps any non-zero, non-timeout exit to a parse failure regardless).
EXIT_PARSE_FAILED = 2


def _apply_cpu_limit(cpu_seconds: float) -> None:
    """Cap this process's CPU time (and disable core dumps) before OCCT work.

    ``RLIMIT_CPU`` is whole-second granular, so the budget is ceil'd to an int
    with a floor of 1 s. Soft = the budget (kernel sends ``SIGXCPU`` when CPU
    time reaches it); hard = soft + 1 (a ``SIGKILL`` backstop if the default
    ``SIGXCPU`` disposition is somehow deferred while the process is deep in
    OCCT C++ — a Python-level handler would not run there, so we rely on the OS
    default termination, not a catchable handler). ``RLIMIT_CORE`` is zeroed so
    a ``SIGXCPU`` termination of untrusted parsing never writes a core file.

    ``resource`` is POSIX-only; on a platform without it (or without
    ``RLIMIT_CPU``) this is a no-op and the parent's wall-clock backstop is the
    sole bound. In our Linux deployment ``RLIMIT_CPU`` is always available, so
    the contention-invariant CPU bound is always in force.
    """
    try:
        import resource
    except ImportError:  # pragma: no cover - non-POSIX only
        return
    soft = max(1, math.ceil(cpu_seconds))
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (soft, soft + 1))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ValueError, OSError):  # pragma: no cover - hostile rlimit env only
        pass


def _parse(in_path: str, out_path: str) -> int:
    """Read the STEP at *in_path*, write the transferred shape to *out_path*."""
    from OCP.BRepTools import BRepTools
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_Reader

    # Pin the target unit in THIS process (fresh every spawn → no ambient state).
    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")

    reader = STEPControl_Reader()
    status = reader.ReadFile(in_path)
    if status != IFSelect_ReturnStatus.IFSelect_RetDone:
        return EXIT_PARSE_FAILED
    try:
        reader.TransferRoots()
        shape = reader.OneShape()
    except Exception:  # OCCT transfer raises are not a stable taxonomy
        return EXIT_PARSE_FAILED

    # A null / compound shape serializes fine; the parent owns the null and
    # single-solid checks so the healing report stays in one tested place.
    BRepTools.Write_s(shape, out_path)
    return 0


def main(argv: list[str]) -> int:
    # argv: <prog> <in_path> <out_path> <cpu_seconds>. The CPU ceiling is applied
    # BEFORE OCCT is imported/run so the ~0.9 s OCP cold-import also counts toward
    # (and is bounded by) the budget — an adversarial file can neither wedge in
    # the import nor in the transfer past the CPU bound.
    if len(argv) != 4:
        return EXIT_PARSE_FAILED
    try:
        cpu_seconds = float(argv[3])
    except ValueError:
        return EXIT_PARSE_FAILED
    _apply_cpu_limit(cpu_seconds)
    return _parse(argv[1], argv[2])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
