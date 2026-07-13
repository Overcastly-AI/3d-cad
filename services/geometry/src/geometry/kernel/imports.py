"""STEP import — read an external STEP part into a single build123d solid.

The inverse of :mod:`geometry.kernel.export` (docs/design/step-import.md): given
the STEP AP214 part-21 TEXT of an external part, parse it into the part's base
body. v1 accepts EXACTLY ONE solid and otherwise fails with a legible,
stats-bearing error (§4) — it does not sew/heal/repair, and IGES / multi-solid
assemblies are deferred (§7).

**Determinism (RESEARCH §9).** OCCT's STEP read is a pure function of the file
bytes plus process-global ``Interface_Static`` settings; the latter is the only
nondeterminism risk (ambient state a prior read may have set). We pin the target
unit to millimetres on every import so the result is independent of process
history. Read precision stays at the OCCT file-default (deterministic given fixed
bytes). Measured: a box exported then re-imported here matches the analytic box
at 0.0 deviation, and re-export is byte-identical across interpreter restarts.

We use a low-level ``STEPControl_Reader`` rather than build123d's ``import_step``
for two reasons: ``import_step`` reads from a file PATH only (it
``os.path.exists``-checks its argument, so inline bytes need a tempfile anyway),
and it runs the heavier XCAF color/name/assembly path we do not want in the
determinism-critical import. Kernel objects never leave ``geometry.kernel``.

The OCP wheel ships no type stubs, so the raw OCCT reader/explorer calls below
are opaque to pyright; the directives scope that relaxation to this file only
(same posture as :mod:`geometry.kernel.properties`), and the fully-typed
:class:`~build123d.Solid` return keeps the boundary honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

import os
import tempfile

from build123d import Solid
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS


class ImportParseError(Exception):
    """OCCT could not parse the STEP payload (maps to ``import_parse_failed``)."""


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


def import_step_solid(step_text: str) -> Solid:
    """Parse STEP AP214 part-21 *step_text* into a single :class:`Solid`.

    Deterministic (units pinned to mm; see module docstring). Raises rather than
    returning a sentinel so the evaluate handler maps each failure to its
    per-feature error code — a geometry outcome is never a 500 (design §4.3).

    Raises:
        ImportParseError: OCCT could not read the payload (bad/empty/truncated
            STEP), or the transfer raised. The 16 MiB inline cap (a
            request-validation 422 *before* OCCT parses) bounds MEMORY, not
            parse TIME: OCCT's STEP transfer is not guaranteed linear, so an
            adversarial/degenerate part-21 can be super-linear. Parse time is
            best-effort in v1, not hard-bounded; a hard wall-clock bound (arq
            job timeout / subprocess) is a tracked P1 fast-follow.
        ImportNotSingleSolidError: the file parsed but yielded zero or more than
            one solid (open shells, surfaces-only, or a multi-solid assembly).
            The message carries the shape stats (v1 healing report).
    """
    # Pin the target unit on every read so the scale is independent of any
    # Interface_Static state a prior read left in this process (determinism).
    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")

    reader = STEPControl_Reader()
    with tempfile.TemporaryDirectory(prefix="loft-step-import-") as tmp:
        target = os.path.join(tmp, "part.step")
        with open(target, "wb") as handle:
            handle.write(step_text.encode("utf-8"))
        try:
            status = reader.ReadFile(target)
            if status != IFSelect_ReturnStatus.IFSelect_RetDone:
                raise ImportParseError(
                    "The STEP payload could not be parsed "
                    f"(OCCT read status {status!r}); it may be malformed, "
                    "truncated, or not a STEP file."
                )
            reader.TransferRoots()
            shape = reader.OneShape()
        except ImportParseError:
            raise
        except Exception as exc:  # OCCT transfer raises are not a stable taxonomy
            raise ImportParseError(
                f"The STEP payload could not be transferred ({type(exc).__name__})."
            ) from exc

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
