"""The 3D sketch solver (SKETCH-3D, RESEARCH §28).

planegcs is a 2D solver (every primitive is a planar point, line, arc), so a
3D sketch gets its own small one. The relations a skeleton needs are few and
smooth, so the solve is a damped Gauss-Newton over the free points'
coordinates with MINIMUM-NORM steps (``numpy.linalg.lstsq``):

* the unknowns are the x, y, z of every point that is neither snapped nor
  ``fixed`` (those are constants);
* ``coincident`` is three equations ``a - b = 0``; ``along`` is the two
  components of the line's direction across its axis; ``length`` and
  ``distance`` are ``|b - a| - value = 0``;
* the solve starts at the stored positions and each step is the smallest
  move that zeroes the LINEARISED residual. The converged answer is therefore
  near the stored positions but not, in general, the nearest solution (a
  Gauss-Newton path is not a projection). One case is exact: a length
  dimension's gradient is the line's own direction, so a lone length on a
  line from a held point slides the free end ALONG the line and is met in one
  step (the line keeps its direction).

Outcomes: converged (with the remaining degrees of freedom, the Jacobian's
null space, and the constraints that are redundant), or
:class:`Sketch3DConflictError` when the residual cannot be driven to zero
(contradictory relations) or a dimensioned line collapses to a point, or
:class:`Sketch3DTooLargeError` when the sketch would cost more than
:data:`WORK_BUDGET`.

Cost. The Jacobian is assembled vectorised (one numpy pass per relation
kind), each Newton step is one dense least-squares solve, and the redundancy
diagnosis is ONE incremental Gram-Schmidt pass over the rows in constraint
order (a constraint is redundant when its rows add no rank to the rows before
it, the greedy rule). The work is counted in flops from the sketch's size
alone and capped by :data:`WORK_BUDGET`, so a sketch that would take too long
is refused with a typed error, never left running, and the answer never
depends on how busy the machine is.

Determinism (RESEARCH §9): a fixed iteration rule on fixed inputs in entity
and constraint order, float64 throughout, and BLAS pinned to one thread for
the whole solve (:func:`threadpoolctl.threadpool_limits`, the assembly
solver's pin), which fixes LAPACK's reduction order.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from loft_wire.sketch_3d import (
    Sketch3DAlong,
    Sketch3DCoincident,
    Sketch3DConstraint,
    Sketch3DDistance,
    Sketch3DFixed,
    Sketch3DLength,
)
from numpy.typing import NDArray

# threadpoolctl ships no py.typed (single-module BSD dep) → stub-less import.
from threadpoolctl import threadpool_limits  # pyright: ignore[reportMissingTypeStubs]

Point = tuple[float, float, float]
_Array = NDArray[np.float64]
_Index = NDArray[np.intp]

#: Newton iteration ceiling; a well-posed skeleton converges in a handful.
_MAX_ITERATIONS = 100
#: Converged when every residual is below this times the sketch's size (mm):
#: 1e-13 relative is a few ulps of a 1 m skeleton.
_RESIDUAL_RELATIVE = 1e-13
#: A residual above this times the size after the iterations is a conflict.
_CONFLICT_RELATIVE = 1e-9
#: A row adds rank when the part of it outside the rows before it is longer
#: than this times the row (every row is a unit-scale gradient).
_RANK_RELATIVE = 1e-9
_AXIS = {"x": 0, "y": 1, "z": 2}

#: Most flops one solve may spend, counted from the sketch's size alone
#: (``m n min(m, n)`` per least-squares step, ``2 m n r`` for the diagnosis,
#: with ``m`` rows, ``n`` unknowns and ``r`` the rank), never from a clock,
#: so the same sketch is accepted or refused on every machine. Measured
#: 2026-10-22 single-threaded on the dev container: a 200-point skeleton
#: (n 597, m 497) solves in 0.3 s spending 0.9e9; 6e9 caps a solve at a
#: couple of seconds. Raising it is a reviewed decision with a measurement.
WORK_BUDGET = 6_000_000_000


class Sketch3DConflictError(ValueError):
    """The relations cannot all hold (or a dimensioned line has no length)."""

    def __init__(self, message: str, constraints: Sequence[int] = ()) -> None:
        super().__init__(message)
        self.constraints = list(constraints)


class Sketch3DTooLargeError(ValueError):
    """The solve would cost more than :data:`WORK_BUDGET`."""


@dataclass(frozen=True)
class Solved3D:
    """The solve: every point's position, in input order, and the diagnosis."""

    points: dict[str, Point]
    dof: int
    redundant: list[int]


class _Degenerate(Exception):
    """A length or distance whose two points coincide (no direction)."""


class _Budget:
    def __init__(self) -> None:
        self.spent = 0

    def spend(self, flops: int) -> None:
        self.spent += flops
        if self.spent > WORK_BUDGET:
            raise Sketch3DTooLargeError(
                "The 3D sketch is too large to solve here (it would take more "
                f"than {WORK_BUDGET:.0e} operations). Split it into smaller "
                "sketches or fix more of its points."
            )


@dataclass(frozen=True)
class _Group:
    """One relation kind, vectorised: row offsets and point slots."""

    first_row: _Index  # the first row of each constraint
    a: _Index  # point slot of each constraint's first point
    b: _Index  # point slot of each constraint's second point
    axes: _Index  # per constraint, the coordinate axes its rows read (k, rows)
    value: _Array  # dimension value (length / distance), else empty


class _System:
    def __init__(
        self,
        positions: Mapping[str, Point],
        fixed: Mapping[str, Point],
        lines: Mapping[str, tuple[str, str]],
        constraints: Sequence[Sketch3DConstraint],
    ) -> None:
        free = [key for key in positions if key not in fixed]
        held = [key for key in positions if key in fixed]
        self.slot = {key: i for i, key in enumerate(free + held)}
        self.n_free = len(free)
        self.n = 3 * self.n_free
        self.x0: _Array = np.array(
            [v for key in free for v in positions[key]], dtype=float
        )
        self.held: _Array = np.array([fixed[key] for key in held], dtype=float).reshape(
            -1, 3
        )
        self.keys = list(positions)

        diffs: list[tuple[int, int, int, tuple[int, ...]]] = []
        dists: list[tuple[int, int, int, float]] = []
        owner: list[int] = []
        for index, c in enumerate(constraints):
            row = len(owner)
            if isinstance(c, Sketch3DCoincident):
                diffs.append((row, self.slot[c.b], self.slot[c.a], (0, 1, 2)))
                owner.extend([index] * 3)
            elif isinstance(c, Sketch3DAlong):
                a, b = lines[c.line]
                across = tuple(k for k in range(3) if k != _AXIS[c.axis])
                diffs.append((row, self.slot[a], self.slot[b], across))
                owner.extend([index] * 2)
            elif isinstance(c, Sketch3DLength | Sketch3DDistance):
                a, b = lines[c.line] if isinstance(c, Sketch3DLength) else (c.a, c.b)
                dists.append((row, self.slot[a], self.slot[b], c.value_mm))
                owner.append(index)
        self.owner = owner
        self.m = len(owner)
        self.groups: list[tuple[int, _Group]] = []
        for width in (3, 2):
            chosen = [d for d in diffs if len(d[3]) == width]
            if chosen:
                self.groups.append(
                    (
                        width,
                        _Group(
                            np.array([d[0] for d in chosen], dtype=np.intp),
                            np.array([d[1] for d in chosen], dtype=np.intp),
                            np.array([d[2] for d in chosen], dtype=np.intp),
                            np.array([d[3] for d in chosen], dtype=np.intp),
                            np.empty(0),
                        ),
                    )
                )
        if dists:
            self.groups.append(
                (
                    1,
                    _Group(
                        np.array([d[0] for d in dists], dtype=np.intp),
                        np.array([d[1] for d in dists], dtype=np.intp),
                        np.array([d[2] for d in dists], dtype=np.intp),
                        np.empty((0, 0), dtype=np.intp),
                        np.array([d[3] for d in dists], dtype=float),
                    ),
                )
            )

    def points(self, x: _Array) -> _Array:
        return np.vstack([x.reshape(-1, 3), self.held])

    def _scatter(
        self, jac: _Array, rows: _Index, slots: _Index, axes: _Index, sign: float
    ) -> None:
        """``jac[rows, 3 slot + axis] += sign`` (or the per-row gradient) for
        the rows whose point is free."""
        free = slots < self.n_free
        jac[rows[free], 3 * slots[free] + axes[free]] += sign

    def evaluate(self, x: _Array, *, jacobian: bool) -> tuple[_Array, _Array | None]:
        """Residual vector and (optionally) the dense Jacobian, rows in
        constraint order."""
        p = self.points(x)
        residual: _Array = np.zeros(self.m)
        jac: _Array | None = np.zeros((self.m, self.n)) if jacobian else None
        for width, g in self.groups:
            if width == 1:
                d = p[g.b] - p[g.a]
                length = np.linalg.norm(d, axis=1)
                if np.any(length <= 1e-12):
                    raise _Degenerate
                residual[g.first_row] = length - g.value
                if jac is not None:
                    u = d / length[:, None]
                    for k in range(3):
                        for slots, sign in ((g.b, 1.0), (g.a, -1.0)):
                            free = slots < self.n_free
                            jac[g.first_row[free], 3 * slots[free] + k] += (
                                sign * u[free, k]
                            )
                continue
            d = p[g.b] - p[g.a]
            for j in range(width):
                rows = g.first_row + j
                axis = g.axes[:, j]
                residual[rows] = d[np.arange(len(rows)), axis]
                if jac is not None:
                    self._scatter(jac, rows, g.b, axis, 1.0)
                    self._scatter(jac, rows, g.a, axis, -1.0)
        return residual, jac


def _greedy_rank(
    jac: _Array, owner: Sequence[int], budget: _Budget
) -> tuple[int, list[int]]:
    """Rank of the rows, and the constraints whose rows add no rank to the
    rows before them, in ONE incremental (twice-orthogonalised) Gram-Schmidt
    pass in row order."""
    m, n = jac.shape
    basis: _Array = np.zeros((min(m, n), n))
    rank = 0
    redundant: list[int] = []
    budget.spend(4 * m * n * min(m, n))
    for row_index in range(m):
        row: _Array = jac[row_index]
        scale = float(np.linalg.norm(row))
        added = False
        if scale > 0.0 and rank < n:
            v: _Array = row.copy()
            q = basis[:rank]
            for _ in range(2):
                v -= q.T @ (q @ v)
            norm = float(np.linalg.norm(v))
            if norm > _RANK_RELATIVE * scale:
                basis[rank] = v / norm
                rank += 1
                added = True
        if not added and (not redundant or redundant[-1] != owner[row_index]):
            redundant.append(owner[row_index])
    return rank, redundant


def solve_sketch_3d(
    positions: Mapping[str, Point],
    fixed: Mapping[str, Point],
    lines: Mapping[str, tuple[str, str]],
    constraints: Sequence[Sketch3DConstraint],
) -> Solved3D:
    """Solve a 3D sketch. *positions* is every point's stored position in
    entity order; *fixed* the points that are constants (snapped or
    ``fixed``), at their resolved positions; *lines* line id -> (start, end).

    Raises:
        Sketch3DConflictError: the relations cannot all hold, or a dimensioned
            line or distance has collapsed to zero length.
        Sketch3DTooLargeError: the solve would exceed :data:`WORK_BUDGET`.
    """
    with threadpool_limits(limits=1, user_api="blas"):
        return _solve(positions, fixed, lines, constraints)


def _solve(
    positions: Mapping[str, Point],
    fixed: Mapping[str, Point],
    lines: Mapping[str, tuple[str, str]],
    constraints: Sequence[Sketch3DConstraint],
) -> Solved3D:
    effective = [c for c in constraints if not isinstance(c, Sketch3DFixed)]
    order = [i for i, c in enumerate(constraints) if not isinstance(c, Sketch3DFixed)]
    system = _System(positions, fixed, lines, effective)
    owner = [order[i] for i in system.owner]
    m, n = system.m, system.n
    step_cost = m * n * min(m, n)
    budget = _Budget()
    # Refuse up front what cannot afford one step and the diagnosis.
    if step_cost + 4 * m * n * min(m, n) > WORK_BUDGET:
        budget.spend(step_cost + 4 * m * n * min(m, n))
    scale = max(
        [1.0]
        + [abs(v) for p in positions.values() for v in p]
        + [abs(v) for p in fixed.values() for v in p]
        + [
            c.value_mm
            for c in constraints
            if isinstance(c, Sketch3DLength | Sketch3DDistance)
        ]
    )
    x = system.x0.copy()
    try:
        residual, jacobian = system.evaluate(x, jacobian=True)
        assert jacobian is not None
        for _ in range(_MAX_ITERATIONS):
            if m == 0 or np.max(np.abs(residual)) <= _RESIDUAL_RELATIVE * scale:
                break
            budget.spend(step_cost)
            step = np.linalg.lstsq(jacobian, -residual, rcond=None)[0]
            norm = float(np.linalg.norm(residual))
            alpha = 1.0
            trial = x
            for _ in range(40):
                trial = x + alpha * step
                trial_residual, _ = system.evaluate(trial, jacobian=False)
                if float(np.linalg.norm(trial_residual)) < norm:
                    break
                alpha /= 2
            else:
                break  # no descent: a local minimum with a residual left
            x = trial
            residual, jacobian = system.evaluate(x, jacobian=True)
            assert jacobian is not None
    except _Degenerate:
        raise Sketch3DConflictError(
            "A dimensioned line or distance in the 3D sketch has zero length; "
            "move one of its points first."
        ) from None
    if m and np.max(np.abs(residual)) > _CONFLICT_RELATIVE * scale:
        worst = owner[int(np.argmax(np.abs(residual)))]
        raise Sketch3DConflictError(
            "The 3D sketch's relations cannot all hold (they contradict each "
            f"other; constraint {worst + 1} is furthest off). Delete or change one.",
            [worst],
        )
    rank, redundant = _greedy_rank(jacobian, owner, budget)
    p = system.points(x)
    solved: dict[str, Point] = {}
    for key in positions:
        at = p[system.slot[key]]
        solved[key] = (float(at[0]), float(at[1]), float(at[2]))
    return Solved3D(solved, n - rank, redundant)
