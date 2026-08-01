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

#: Exit code when the ASSEMBLY parse worker aborts because the file's leaf
#: occurrence count exceeds the import ceiling (→ ``ImportTooManyProductsError``).
#: This module is the shared exit-code protocol both parse workers reference (the
#: assembly worker loads it by path for ``_apply_cpu_limit``/``EXIT_PARSE_FAILED``),
#: so the response-amplification count cap lives here as one source of truth. The
#: single-body worker never emits it; the parent maps it to a distinct typed 422
#: so an over-large assembly is rejected INSIDE the CPU-bounded child before it
#: writes a per-occurrence BREP for every occurrence (slice-2b DoS hardening).
EXIT_TOO_MANY_PRODUCTS = 3


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


#: Shape-processing parameters handed to the STEP reader before its transfer —
#: the ONE source both parse workers apply (:func:`apply_shape_fix_parameters`).
#:
#: **Why this exists (docs/PERF.md 2026-07-31b, PERF-3).** OCCT's STEP transfer is
#: not just a read: after ``StepToTopoDS`` builds the topology,
#: ``STEPControl_ActorRead`` runs a full ``ShapeFix_Shape`` over the result
#: (``XSAlgo_ShapeProcessor::ProcessShape``). One operation in that sequence,
#: ``ShapeFix_Wire::FixSelfIntersection`` → ``ShapeFix_IntersectionTool::
#: FixSelfIntersectWire``, tests a wire's edges PAIRWISE and reaches each edge
#: through ``ShapeExtend_WireData::Edge(i)`` — a positional index into an
#: ``NCollection_Sequence``. Its cost is therefore super-quadratic in EDGES PER
#: WIRE, and it dominated every large import: 8 of 8 sampled native stacks during
#: an 18 s import sat inside it.
#:
#: Measured on Loft's own export of a 500-fin heat sink (2 006 faces, whose two
#: comb faces each carry ONE 2 004-edge wire), OCCT 7.9.3 / OCP:
#:
#: * ``TransferRoots`` **17.47 s → 0.98 s** (17.9x) — and the whole import curve
#:   goes from ``faces^2.4`` to LINEAR;
#: * the transferred shape is **byte-identical** (same BREP sha256, same volume,
#:   same 2 006 faces / 12 024 edges) at every corpus size.
#:
#: Disabling it is a fidelity no-op on well-formed input, which is the case it was
#: costing us; on MALFORMED input it means a self-intersecting wire is imported as
#: authored rather than silently repaired. That is the contract this module
#: already documents ("It does not sew/heal/repair" — :mod:`geometry.kernel.
#: imports`), and the downstream guard is unchanged and real: every imported body
#: is admitted through ``body_is_valid`` (``BRepCheck_Analyzer``), so a broken
#: import surfaces as a clean per-feature error, never a silently wrong body. It
#: also TIGHTENS the DoS posture: a hostile file needed only one long wire to burn
#: the entire CPU budget inside OCCT's repair pass.
#:
#: Keys are ``<operation>.<parameter>`` in OCCT's shape-processing vocabulary
#: (``libTKXSBase``); ``0`` is ``ShapeFix``'s "do not perform".
SHAPE_FIX_PARAMETERS: dict[str, str] = {"FixShape.FixSelfIntersectionMode": "0"}


def apply_shape_fix_parameters(reader: object) -> None:
    """Bind :data:`SHAPE_FIX_PARAMETERS` on a STEP *reader*, AFTER ``ReadFile``.

    Order matters and is not obvious: ``XSControl_Reader::SetShapeFixParameters``
    forwards the map to the transfer ACTOR, and the actor does not exist until
    ``ReadFile`` has initialised the work session — calling it before ``ReadFile``
    is silently a no-op (measured: 2.07 s before vs 0.53 s after, on the same
    file). Both workers therefore call this immediately after a successful
    ``ReadFile`` and before the transfer.

    Accepts anything with ``SetShapeFixParameters`` — ``STEPControl_Reader`` for
    the single-body path and ``STEPCAFControl_Reader`` for the XDE assembly path,
    so both get the same bound (they are the same OCCT reader underneath). No
    ``try``/``except``: if a future OCP drops the API this must fail loudly at the
    first import rather than quietly restore the super-quadratic pass.
    """
    from OCP.Resource import Resource_DataMapOfAsciiStringAsciiString
    from OCP.TCollection import TCollection_AsciiString

    parameters = Resource_DataMapOfAsciiStringAsciiString()
    for key, value in SHAPE_FIX_PARAMETERS.items():
        parameters.Bind(TCollection_AsciiString(key), TCollection_AsciiString(value))
    reader.SetShapeFixParameters(parameters)  # pyright: ignore[reportAttributeAccessIssue]


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
    apply_shape_fix_parameters(reader)
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
