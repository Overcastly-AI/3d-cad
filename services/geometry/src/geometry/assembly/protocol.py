"""The ``AssemblySolver`` contract + its resolved-geometry input types.

Mirrors the ``SketchSolver`` protocol (RESEARCH §2, ``geometry.sketch.solver``):
the 3D mate solver hides behind this interface so its backend is swappable and
so callers speak only pydantic DTOs — never the numeric core, never a kernel
type (CLAUDE.md service boundaries).

Contract requirements for any implementation (design ``assemblies.md`` §2):

- **Deterministic** (RESEARCH §9): the same :class:`AssemblySolveInput` yields a
  bitwise-identical :class:`AssemblySolveResult`, across calls and processes.
  Instances are laid out in input-list order, mates are processed in
  ``order_index`` order; no dict/set iteration participates in ordering, there
  is no random restart, and quaternions are renormalised each step.
- **Diagnosing, not raising:** solve *outcomes* — under/over/conflicting/
  not-converged — are reported in :attr:`AssemblySolveResult.status` with an
  :class:`AssemblySolveDiagnosis`, never as exceptions. Under-constrained is a
  first-class NON-fatal status that returns a valid seed-consistent placement.
  Exceptions (:class:`AssemblyDefinitionError`) are reserved for malformed
  *input*: a mate naming an unknown instance, a self-mate, resolved geometry of
  the wrong kind for the mate.
- **No foreign types:** input and output are the DTOs below (reusing the #1
  boundary schema :mod:`py_kit.schemas.assemblies`); numpy arrays and the numeric
  solver never escape.

The **resolved mate geometry** carried by :class:`SolverMate.geometry` is the
seam item #3 (mate-geometry-ref resolution) fills: #3 resolves each
``MateFaceRef`` / ``MateAxisRef`` against the instance's evaluated OCCT part body
and hands the solver a :class:`ResolvedFace` / :class:`ResolvedAxis` in that
instance's LOCAL frame. Item #2 (this module) proves the numerics against
SYNTHETIC resolved geometry, so #3 plugs in without touching the solver.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal, Protocol

from py_kit.schemas.assemblies import (
    AssemblyOverconstraintClass,
    AssemblySolveDiagnosis,
    AssemblySolveStatus,
    Mate,
    Placement,
)
from py_kit.schemas.geometry import Vec3
from pydantic import BaseModel, Field

# ``AssemblySolveStatus`` / ``AssemblyOverconstraintClass`` /
# ``AssemblySolveDiagnosis`` now live in the boundary schema
# (:mod:`py_kit.schemas.assemblies`) so the evaluation RESULT can carry them
# without a parallel copy (CLAUDE.md DRY rule). They are re-exported here so
# every existing ``geometry.assembly`` import site is unchanged.
__all__ = [
    "AssemblyDefinitionError",
    "AssemblyOverconstraintClass",
    "AssemblySolveDiagnosis",
    "AssemblySolveInput",
    "AssemblySolveMethod",
    "AssemblySolveResult",
    "AssemblySolveStatus",
    "AssemblySolver",
    "ResolvedAxis",
    "ResolvedFace",
    "ResolvedMateGeometry",
    "SolvedInstancePlacement",
    "SolverInstance",
    "SolverMate",
]


class AssemblyDefinitionError(ValueError):
    """An :class:`AssemblySolveInput` is malformed — a caller bug, not a solve
    outcome (see the module docstring for the exception-vs-status contract)."""


# --- resolved mate geometry (the #3 seam) ---------------------------------------


class ResolvedFace(BaseModel):
    """A planar face resolved to ``(point, unit normal)`` in an instance's LOCAL
    part frame (design §2.3). The solver transforms it to world by the instance's
    current pose for residual evaluation."""

    kind: Literal["face"] = "face"
    point: Vec3 = Field(description="A point on the plane, instance-local mm")
    normal: Vec3 = Field(description="Unit face normal, instance-local")


class ResolvedAxis(BaseModel):
    """An axis resolved to ``(point, unit direction)`` in an instance's LOCAL part
    frame (design §2.3) — e.g. a hole/shaft axis from a circular edge."""

    kind: Literal["axis"] = "axis"
    point: Vec3 = Field(description="A point on the axis line, instance-local mm")
    direction: Vec3 = Field(description="Unit axis direction, instance-local")


#: Discriminated resolved-geometry input: a planar face OR an axis.
ResolvedMateGeometry = Annotated[
    ResolvedFace | ResolvedAxis, Field(discriminator="kind")
]


# --- solver input ---------------------------------------------------------------


class SolverInstance(BaseModel):
    """One instance as the solver sees it: identity, grounded flag, seed pose.

    ``grounded`` instances are held FIXED at ``placement`` (0 DOF, the solver
    anchor); free instances carry 6 DOF seeded from ``placement`` (design §2.2).
    """

    instance_id: uuid.UUID
    grounded: bool = False
    placement: Placement = Field(description="Authored seed pose (world)")


class SolverMate(BaseModel):
    """One mate plus its resolved geometry (design §2.3).

    ``mate`` is the #1 discriminated :class:`~py_kit.schemas.assemblies.Mate`
    (carrying ``flush`` / offsets / the two instance ids). ``geometry`` is the
    resolved ``(a, b)`` pair in the SAME order as the mate's ``a``/``b`` slots —
    two :class:`ResolvedFace` for ``coincident``/``distance``/``angle``, two
    :class:`ResolvedAxis` for ``concentric``, and ``None`` for ``lock`` (which
    names instances directly and derives its target relative pose from the
    seeds). ``mate_id`` and ``order_index`` come from the persisted mate row:
    ``order_index`` fixes the deterministic processing order, ``mate_id`` names
    the mate in diagnosis (offending / redundant sets).
    """

    mate_id: uuid.UUID
    order_index: int = Field(ge=0, description="Deterministic processing order")
    mate: Mate
    geometry: tuple[ResolvedMateGeometry, ResolvedMateGeometry] | None = None


class AssemblySolveInput(BaseModel):
    """The full problem: instances + resolved mates (design §2.2)."""

    instances: list[SolverInstance]
    mates: list[SolverMate] = Field(default_factory=list["SolverMate"])


# --- diagnosis + result ---------------------------------------------------------

#: Which solve path produced the placements — the closed-form tree fast path
#: (design §2.2) or the numerical Levenberg-Marquardt fallback.
AssemblySolveMethod = Literal["closed_form", "numeric"]


class SolvedInstancePlacement(BaseModel):
    """One instance's solved world pose (design §4)."""

    instance_id: uuid.UUID
    placement: Placement


class AssemblySolveResult(BaseModel):
    """Solver output: a solved placement per instance plus diagnosis (design §4).

    ``placements`` is in the SAME order as the input instances (determinism).
    ``diagnosis`` is ``None`` only for a clean ``well_constrained`` solve.
    """

    status: AssemblySolveStatus
    method: AssemblySolveMethod
    placements: list[SolvedInstancePlacement]
    diagnosis: AssemblySolveDiagnosis | None = None


class AssemblySolver(Protocol):
    """A deterministic rigid-body 3D mate solver (design §2.2)."""

    def solve(self, problem: AssemblySolveInput) -> AssemblySolveResult:
        """Solve the mate system and return solved placements plus diagnosis.

        Raises:
            AssemblyDefinitionError: if the input is malformed (see the module
                docstring for the exception-vs-status contract).
        """
        ...
