"""STEP import — read an external STEP part into a single build123d solid.

The inverse of :mod:`geometry.kernel.export` (docs/design/step-import.md): given
the STEP AP214 part-21 TEXT of an external part, parse it into the part's base
body. v1 accepts EXACTLY ONE solid and otherwise fails with a legible,
stats-bearing error (§4) — it does not sew/heal/repair, and IGES / multi-solid
assemblies are deferred (§7).

**Hard wall-clock bound (design §6, BACKLOG P1).** A STEP file is untrusted
external input and OCCT's transfer is not guaranteed linear in input size, so a
degenerate/adversarial part-21 can be super-linear and pin its worker — the
16 MiB inline cap bounds MEMORY, not parse TIME. The two unbounded-time OCCT
calls (``ReadFile`` → ``TransferRoots``) therefore run in a **separate,
killable process** (:mod:`geometry.kernel._step_parse_worker`) spawned with a
configurable ``subprocess.run(..., timeout=...)``. A parse that exceeds the
bound is SIGKILLed and reaped (``subprocess.run`` kills then waits before
re-raising), surfacing as :class:`ImportParseTimeoutError` →
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

import os
import subprocess
import sys
import tempfile

from build123d import Solid
from OCP.BRep import BRep_Builder
from OCP.BRepTools import BRepTools
from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape

#: Default hard wall-clock bound (seconds) for the untrusted OCCT parse. A few
#: seconds comfortably clears a real mechanical part's transfer while capping an
#: adversarial one. Overridden per call by the evaluate handler from
#: ``GeometrySettings.step_import_timeout_seconds`` (the py-kit config knob), so
#: this is a floor, not a magic number wired into the hot path.
DEFAULT_STEP_IMPORT_TIMEOUT_S = 5.0

#: Absolute path of the OCP-only parse worker (a sibling module), invoked BY
#: PATH (not ``-m``) so the spawn does not drag in ``geometry.kernel.__init__``
#: (build123d + every kernel module, ~3 s of cold-start); by path it is ~0.9 s
#: of OCP alone. Referenced as a file, not imported, so there is no partial-
#: package-init coupling with ``geometry.kernel``.
_WORKER_PATH = os.path.join(os.path.dirname(__file__), "_step_parse_worker.py")


class ImportParseError(Exception):
    """OCCT could not parse the STEP payload (maps to ``import_parse_failed``)."""


class ImportParseTimeoutError(Exception):
    """The OCCT parse exceeded its hard wall-clock bound (``import_parse_timeout``).

    Raised when the killable parse subprocess is SIGKILLed for running past
    ``timeout_s`` (design §6). The subprocess is reaped before this propagates —
    no hang, no zombie, no 500."""


class ImportNotSingleSolidError(Exception):
    """The STEP parsed but did not yield exactly one solid — the v1 healing
    report (maps to ``import_not_single_solid``). Carries the shape stats so a
    rejection is legible."""


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


def _run_parse_worker(step_text: str, timeout_s: float) -> TopoDS_Shape:
    """Parse *step_text* in a killable subprocess and return the transferred shape.

    The subprocess does exactly the two unbounded-time OCCT calls; on timeout it
    is SIGKILLed and reaped (``subprocess.run`` kills then waits before
    re-raising ``TimeoutExpired``), so no process or file descriptor leaks across
    repeated calls. The temp dir — holding the STEP in and the BREP out — is
    removed on every exit path by the context manager.
    """
    with tempfile.TemporaryDirectory(prefix="loft-step-import-") as tmp:
        in_path = os.path.join(tmp, "part.step")
        out_path = os.path.join(tmp, "part.brep")
        with open(in_path, "wb") as handle:
            handle.write(step_text.encode("utf-8"))
        try:
            completed = subprocess.run(
                [sys.executable, _WORKER_PATH, in_path, out_path],
                capture_output=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise ImportParseTimeoutError(
                "STEP import exceeded its "
                f"{timeout_s:g}s parse-time limit and was aborted; the file may "
                "be pathologically large or geometrically degenerate. Simplify "
                "or repair the part and try again."
            ) from exc
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
    step_text: str, *, timeout_s: float = DEFAULT_STEP_IMPORT_TIMEOUT_S
) -> Solid:
    """Parse STEP AP214 part-21 *step_text* into a single :class:`Solid`.

    Deterministic (units pinned to mm in the worker; see module docstring). The
    untrusted OCCT parse runs in a subprocess bounded by *timeout_s* (design §6).
    Raises rather than returning a sentinel so the evaluate handler maps each
    failure to its per-feature error code — a geometry outcome is never a 500
    (design §4.3).

    Args:
        step_text: the STEP AP214 part-21 text (already size-bounded upstream).
        timeout_s: hard wall-clock bound on the OCCT parse; the evaluate handler
            passes the configured ``step_import_timeout_seconds``.

    Raises:
        ImportParseTimeoutError: the parse exceeded *timeout_s* and the worker
            was killed (maps to ``import_parse_timeout``).
        ImportParseError: OCCT could not read the payload (bad/empty/truncated
            STEP), or the worker exited non-zero for any other reason (maps to
            ``import_parse_failed``).
        ImportNotSingleSolidError: the file parsed but yielded zero or more than
            one solid (open shells, surfaces-only, or a multi-solid assembly).
            The message carries the shape stats (v1 healing report).
    """
    shape = _run_parse_worker(step_text, timeout_s)

    if shape is None or shape.IsNull():
        raise ImportNotSingleSolidError(
            "The STEP file transferred no geometry (found 0 solids); it may "
            "contain only surfaces, wireframe, or annotations."
        )

    solids = _count(shape, TopAbs_SOLID)
    if solids != 1:
        shells = _count(shape, TopAbs_SHELL)
        faces = _count(shape, TopAbs_FACE)
        raise ImportNotSingleSolidError(
            f"STEP import expects exactly one solid, but found {solids} "
            f"(shells={shells}, faces={faces}). Multi-solid assemblies, open "
            "shells, and surface/wireframe geometry are not supported yet; "
            "provide a single closed solid."
        )

    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    return Solid(TopoDS.Solid_s(explorer.Current()))
