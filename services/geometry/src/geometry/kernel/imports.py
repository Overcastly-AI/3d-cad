"""STEP import — read an external STEP part into a build123d body.

The inverse of :mod:`geometry.kernel.export` (docs/design/step-import.md): given
the STEP AP214 part-21 TEXT of an external part, parse it into the part's base
body (:data:`~geometry.kernel.types.BodyShape`). A file with **exactly one
solid** stays a bare :class:`~build123d.Solid` (byte-identical to the
single-solid pipeline); a file with **two or more solids** becomes ONE
multi-lump body — a lump-sorted :class:`~build123d.Compound` of its disjoint
solids (docs/design/multi-body.md §MB-4), NOT N separate bodies and NOT a
rejection. STEP import is not a boolean: the file's solids are preserved AS
AUTHORED, each a separate lump, even if two solids happen to touch or overlap —
we never silently fuse them. Only a file that yields **zero** solids
(surfaces-only / open shells / wireframe / annotations) is an error. It does not
sew/heal/repair, and IGES is deferred (§7).

**Hard parse bound — CPU-time + wall-clock backstop (design §6, BACKLOG P1).**
A STEP file is untrusted external input and OCCT's transfer is not guaranteed
linear in input size, so a degenerate/adversarial part-21 can be super-linear
and pin its worker — the 16 MiB inline cap bounds MEMORY, not parse TIME. The two
unbounded-time OCCT calls (``ReadFile`` → ``TransferRoots``) therefore run in a
**separate, killable process** (:mod:`geometry.kernel._step_parse_worker`) under
TWO independent ceilings:

* **CPU-time (the primary bound).** The child caps its own CPU seconds via
  ``resource.setrlimit(RLIMIT_CPU, …)`` before any OCCT work. This is invariant
  to machine load: a legit ~1 s parse burns ~1 s of CPU whether its wall-clock is
  starved 2x or 50x under CI/worktree contention, so it NEVER false-fires - while
  an adversarial parse that genuinely burns CPU is still capped. On exhaustion the
  kernel sends ``SIGXCPU`` (soft) / ``SIGKILL`` (hard); the parent maps either to
  a timeout. This decouples the DoS bound from contention — the earlier pure
  wall-clock bound false-fired on slow-but-legit imports under load (the flake
  this design fixes, 2026-07-19).
* **Wall-clock (a liveness backstop only).** ``subprocess.run(..., timeout=…)``
  kills a child that is *wedged* (blocked, not CPU-burning) — a case ``RLIMIT_CPU``
  cannot catch. Sized generously (default 60 s) so it, too, never fires on a legit
  parse; it is a hang guard, not the DoS latency control.

A killed parse is reaped (``subprocess.run`` kills then waits; a signal-killed
child is already reaped) and surfaces as :class:`ImportParseTimeoutError` →
``import_parse_timeout`` — never a hang, a 500, or a leaked/zombie process. A
thread/``signal.alarm`` timeout would NOT work: it cannot interrupt OCCT C++
mid-transfer and signals do not fire in FastAPI threadpool threads.

**Determinism (RESEARCH §9).** OCCT's STEP read is a pure function of the file
bytes plus process-global ``Interface_Static`` settings; the latter is the only
nondeterminism risk (ambient state a prior read may have set). The worker pins
the target unit to millimetres in its FRESH process on every import, so the
result is independent of process history — a strictly stronger guarantee than
the in-process read it replaces. Read precision stays at the OCCT file-default
(deterministic given fixed bytes). Measured: a box exported then re-imported
here matches the analytic box at 0.0 deviation, and re-export is byte-identical
across interpreter restarts.

The transferred shape crosses the process boundary as a BREP file (OCCT's
native, lossless serialization); the null / single-solid topology taxonomy stays
HERE, in the parent, where it is tested and can use build123d. Kernel objects
never leave ``geometry.kernel``.

The OCP wheel ships no type stubs, so the raw OCCT reader/explorer calls below
are opaque to pyright; the directives scope that relaxation to this file only
(same posture as :mod:`geometry.kernel.properties`), and the fully-typed
:class:`~build123d.Solid` return keeps the boundary honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import io
import os
import signal
import subprocess
import sys
import tempfile

from build123d import Compound, Solid
from OCP.BRep import BRep_Builder
from OCP.BRepTools import BRepTools
from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape
from OCP.TopTools import TopTools_FormatVersion

from geometry.kernel.lumps import assemble_lumps
from geometry.kernel.types import BodyShape

#: Default **CPU-time** ceiling (seconds) for the untrusted OCCT parse — the
#: primary DoS bound, enforced by ``RLIMIT_CPU`` inside the killable worker. It
#: is invariant to machine load (a legit parse burns the same CPU whether or not
#: its wall-clock is starved under contention), so it never false-fires on a
#: slow-but-legitimate import - the defect a wall-clock-only bound caused
#: (2026-07-19). Sized for enormous headroom over a legit parse: the STEP
#: round-trip warm median is ~10-23 ms (``test_benchmarks.py``) and the child's
#: ~0.9 s OCP cold-import dominates, so a legit parse consumes ~1 s of CPU - this
#: 20 s ceiling is ~20x that, while still capping an adversarial CPU-burn parse.
#: Overridden per call by the evaluate handler from
#: ``GeometrySettings.step_import_timeout_seconds`` (env
#: ``STEP_IMPORT_TIMEOUT_SECONDS``).
DEFAULT_STEP_IMPORT_CPU_TIMEOUT_S = 20.0

#: Default **wall-clock** liveness backstop (seconds) — kills a child that is
#: *wedged* (blocked, not CPU-burning), which ``RLIMIT_CPU`` cannot catch. It is
#: NOT the DoS latency control (that is the CPU bound above); it is sized so a
#: legit parse - ~1 s of wall-clock in isolation - never trips it even under
#: heavy contention (60x headroom). Overridden per call from
#: ``GeometrySettings.step_import_wall_timeout_seconds`` (env
#: ``STEP_IMPORT_WALL_TIMEOUT_SECONDS``).
DEFAULT_STEP_IMPORT_WALL_TIMEOUT_S = 60.0

#: Absolute path of the OCP-only parse worker (a sibling module), invoked BY
#: PATH (not ``-m``) so the spawn does not drag in ``geometry.kernel.__init__``
#: (build123d + every kernel module, ~3 s of cold-start); by path it is ~0.9 s
#: of OCP alone. Referenced as a file, not imported, so there is no partial-
#: package-init coupling with ``geometry.kernel``.
_WORKER_PATH = os.path.join(os.path.dirname(__file__), "_step_parse_worker.py")


class ImportParseError(Exception):
    """OCCT could not parse the STEP payload (maps to ``import_parse_failed``)."""


class ImportParseTimeoutError(Exception):
    """The OCCT parse exceeded a hard parse bound (``import_parse_timeout``).

    Raised when the killable parse subprocess is killed for exceeding EITHER its
    CPU-time ceiling (``RLIMIT_CPU`` → ``SIGXCPU``/``SIGKILL``) or the wall-clock
    liveness backstop (``subprocess.run`` timeout → ``SIGKILL``) — design §6. The
    subprocess is reaped before this propagates: no hang, no zombie, no 500."""


class ImportNoSolidError(Exception):
    """The STEP parsed but yielded ZERO solids — surfaces-only, open shells,
    wireframe, or annotations (maps to ``import_no_solid``). Carries the shape
    stats so a rejection is legible. A file with one OR MORE solids is a SUCCESS
    (a single-lump or multi-lump body, §MB-4), never this error."""


def _count(shape: object, kind: object) -> int:
    """Number of sub-shapes of *kind* reachable in *shape* (deterministic)."""
    explorer = TopExp_Explorer(shape, kind)
    total = 0
    while explorer.More():
        total += 1
        explorer.Next()
    return total


def _read_brep(path: str) -> TopoDS_Shape:
    """Deserialize the worker's BREP output back into a shape (parent side)."""
    shape = TopoDS_Shape()
    BRepTools.Read_s(shape, path, BRep_Builder())
    return shape


def solid_to_brep_bytes(body: BodyShape) -> bytes:
    """Serialize *body* to deterministic, geometry-only BREP bytes.

    OCCT's native lossless serialization — the SAME format the parse worker uses
    to cross the process boundary — written to an in-memory stream so the STEP
    re-parse cache (engineering audit F8, :mod:`geometry.step_cache`) can store a
    parsed body and re-read it in-process, skipping the killable subprocess parse
    on an unchanged import. Triangulation and normals are written OFF so the
    cached bytes are a pure function of the geometry (never a mesh at some
    deflection); the format version is pinned so the round-trip is deterministic
    across interpreter restarts (RESEARCH §9). Because a fresh solid is
    round-tripped BEFORE any downstream op meshes it, and BREP write→read is
    idempotent on an already-BREP-read shape (the parse worker already returns
    one), the cached body tessellates byte-identically to the direct parse. A
    multi-lump import body is a :class:`~build123d.Compound`; BREP write
    serializes its lump order verbatim, so a cache round-trip preserves the
    :func:`~geometry.kernel.lumps.assemble_lumps` sort (§MB-4).
    """
    stream = io.BytesIO()
    BRepTools.Write_s(
        body.wrapped,
        stream,
        False,  # theWithTriangles — geometry only, never a cached mesh
        False,  # theWithNormals
        TopTools_FormatVersion.TopTools_FormatVersion_VERSION_1,
    )
    return stream.getvalue()


def solid_from_brep_bytes(data: bytes) -> BodyShape:
    """Deserialize BREP *data* into a FRESH :data:`BodyShape` (parent side).

    Every call builds a brand-new :class:`~OCP.TopoDS.TopoDS_Shape` from the
    bytes, so a cache hit never shares a mutable OCCT shape across evaluations:
    downstream tessellation (which stores its triangulation INTO the shape's
    TShape) and the FastAPI threadpool can never race or interfere on a shared
    body — the exact hazard that makes caching a live shape unsafe. Re-reading
    bytes is in-process and cheap versus re-spawning the OCCT parse worker. A
    compound-topology payload (a multi-lump import body, §MB-4) is re-wrapped as
    a :class:`~build123d.Compound` — its lump order is exactly what was written —
    so a cache hit returns the SAME body type the direct parse did.
    """
    shape = TopoDS_Shape()
    BRepTools.Read_s(shape, io.BytesIO(data), BRep_Builder())
    if shape.ShapeType() == TopAbs_COMPOUND:
        return Compound(shape)
    return Solid(shape)


#: Signals that mean the worker was killed for exhausting its CPU-time ceiling
#: (``RLIMIT_CPU``): ``SIGXCPU`` at the soft limit, ``SIGKILL`` at the hard limit
#: if the default ``SIGXCPU`` termination was deferred in OCCT C++. A process
#: killed by a signal reports ``returncode = -signum``, so the parent maps these
#: to a timeout, while any OTHER non-zero exit (e.g. a crash, or the worker's
#: ``EXIT_PARSE_FAILED``) is a parse failure, not a timeout.
_CPU_LIMIT_SIGNALS = frozenset({-signal.SIGXCPU, -signal.SIGKILL})


def _run_parse_worker(
    step_text: str, *, cpu_timeout_s: float, wall_timeout_s: float
) -> TopoDS_Shape:
    """Parse *step_text* in a killable subprocess and return the transferred shape.

    The subprocess does exactly the two unbounded-time OCCT calls under two
    ceilings: a **CPU-time** limit it applies to itself (``RLIMIT_CPU``, the
    contention-invariant primary bound) and the parent's **wall-clock** backstop
    (``subprocess.run(..., timeout=wall_timeout_s)``, a hang guard). On either
    kill the child is reaped — ``subprocess.run`` kills then waits before
    re-raising ``TimeoutExpired`` for the wall-clock case, and a signal-killed
    child is already reaped when ``run`` returns — so no process or file
    descriptor leaks across repeated calls. The temp dir — holding the STEP in
    and the BREP out — is removed on every exit path by the context manager.

    The child's stdout/stderr are sent to ``DEVNULL``, not captured: OCCT's STEP
    reader is chatty on malformed input (per-entity warnings ∝ input size), and
    capturing that would buffer untrusted-input-proportional diagnostics in the
    *parent* — which the kill does not reclaim. We never read the output, so
    discarding it both closes that amplification vector and is strictly simpler.
    """
    with tempfile.TemporaryDirectory(prefix="loft-step-import-") as tmp:
        in_path = os.path.join(tmp, "part.step")
        out_path = os.path.join(tmp, "part.brep")
        with open(in_path, "wb") as handle:
            handle.write(step_text.encode("utf-8"))
        try:
            completed = subprocess.run(
                [sys.executable, _WORKER_PATH, in_path, out_path, repr(cpu_timeout_s)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=wall_timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise ImportParseTimeoutError(
                "STEP import exceeded its "
                f"{wall_timeout_s:g}s wall-clock liveness limit and was aborted; "
                "the parse appears wedged. Simplify or repair the part and try "
                "again."
            ) from exc
        if completed.returncode in _CPU_LIMIT_SIGNALS:
            raise ImportParseTimeoutError(
                "STEP import exceeded its "
                f"{cpu_timeout_s:g}s CPU-time limit and was aborted; the file may "
                "be pathologically large or geometrically degenerate. Simplify "
                "or repair the part and try again."
            )
        if completed.returncode != 0:
            # EXIT_PARSE_FAILED, a crash, or any non-timeout non-zero exit: the
            # untrusted bytes could not be read/transferred. Never a 500.
            raise ImportParseError(
                "The STEP payload could not be parsed or transferred (worker "
                f"exit {completed.returncode}); it may be malformed, truncated, "
                "or not a STEP file."
            )
        return _read_brep(out_path)


def import_step_solid(
    step_text: str,
    *,
    cpu_timeout_s: float = DEFAULT_STEP_IMPORT_CPU_TIMEOUT_S,
    wall_timeout_s: float = DEFAULT_STEP_IMPORT_WALL_TIMEOUT_S,
) -> BodyShape:
    """Parse STEP AP214 part-21 *step_text* into a :data:`BodyShape`.

    One solid → a bare :class:`Solid` (byte-identical to the single-solid
    pipeline); two or more solids → ONE lump-sorted :class:`~build123d.Compound`
    (a multi-lump body, §MB-4). The file's solids are preserved AS AUTHORED —
    each becomes a lump, and touching/overlapping solids are NOT fused (STEP
    import is not a boolean). Determinism (units pinned to mm in the worker; see
    module docstring): OCCT's solid-traversal order is not a contract, so the
    lumps are put through :func:`~geometry.kernel.lumps.assemble_lumps`'s
    explicit sort (centroid x/y/z, then volume), yielding a byte-identical body
    regardless of the reader's order. The untrusted OCCT parse runs in a
    subprocess bounded by a CPU-time ceiling (*cpu_timeout_s*, the primary DoS
    bound, invariant to machine load) and a wall-clock liveness backstop
    (*wall_timeout_s*) — design §6. Raises rather than returning a sentinel so the
    evaluate handler maps each failure to its per-feature error code — a geometry
    outcome is never a 500 (design §4.3).

    Args:
        step_text: the STEP AP214 part-21 text (already size-bounded upstream).
        cpu_timeout_s: hard CPU-time ceiling on the OCCT parse (``RLIMIT_CPU`` in
            the worker); the evaluate handler passes the configured
            ``step_import_timeout_seconds``. Contention-invariant, so it does not
            false-fire on a slow-but-legit parse under load.
        wall_timeout_s: wall-clock liveness backstop that kills a *wedged* child;
            the evaluate handler passes ``step_import_wall_timeout_seconds``.

    Raises:
        ImportParseTimeoutError: the parse exceeded its CPU-time ceiling or the
            wall-clock backstop and the worker was killed (maps to
            ``import_parse_timeout``).
        ImportParseError: OCCT could not read the payload (bad/empty/truncated
            STEP), or the worker exited non-zero for any other reason (maps to
            ``import_parse_failed``).
        ImportNoSolidError: the file parsed but yielded ZERO solids (surfaces
            only, open shells, or wireframe). The message carries the shape stats.
    """
    shape = _run_parse_worker(
        step_text, cpu_timeout_s=cpu_timeout_s, wall_timeout_s=wall_timeout_s
    )

    if shape is None or shape.IsNull():
        raise ImportNoSolidError(
            "The STEP file transferred no geometry (found 0 solids); it may "
            "contain only surfaces, wireframe, or annotations."
        )

    solid_count = _count(shape, TopAbs_SOLID)
    if solid_count == 0:
        shells = _count(shape, TopAbs_SHELL)
        faces = _count(shape, TopAbs_FACE)
        raise ImportNoSolidError(
            f"STEP import found no solids (shells={shells}, faces={faces}). "
            "Open shells and surface/wireframe geometry are not supported; "
            "provide a closed solid (or a file of several closed solids)."
        )

    # One or more solids: preserve each as a lump AS AUTHORED (no fusing) and let
    # assemble_lumps impose the deterministic order. A lone solid returns bare
    # (byte-identical to today); >=2 return a lump-sorted Compound (§MB-4).
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    solids: list[Solid] = []
    while explorer.More():
        solids.append(Solid(TopoDS.Solid_s(explorer.Current())))
        explorer.Next()
    return assemble_lumps(solids)
