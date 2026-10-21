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
* the solve starts at the stored positions and each step is the smallest move
  that zeroes the linearised residual, so a free point moves only as far as
  the relations force it. A length dimension's gradient is the line's own
  direction, so it slides the free end ALONG the line (a lone length is met
  exactly in one step; the line keeps its direction).

Outcomes: converged (with the remaining degrees of freedom, the Jacobian's
null space, and the constraints that are redundant), or
:class:`Sketch3DConflictError` when the residual cannot be driven to zero
(contradictory relations) or a dimensioned line collapses to a point.

Determinism (RESEARCH §9): a fixed iteration rule on fixed inputs in entity
and constraint order; LAPACK's least-squares is deterministic for one input.
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

Point = tuple[float, float, float]
_Array = NDArray[np.float64]

#: Newton iteration ceiling; a well-posed skeleton converges in a handful.
_MAX_ITERATIONS = 100
#: Converged when every residual is below this times the sketch's size (mm):
#: 1e-13 relative is a few ulps of a 1 m skeleton.
_RESIDUAL_RELATIVE = 1e-13
#: A residual above this times the size after the iterations is a conflict.
_CONFLICT_RELATIVE = 1e-9
#: Singular values below this times the largest count as rank-deficient.
_RANK_RELATIVE = 1e-9
_AXIS = {"x": 0, "y": 1, "z": 2}


class Sketch3DConflictError(ValueError):
    """The relations cannot all hold (or a dimensioned line has no length)."""

    def __init__(self, message: str, constraints: Sequence[int] = ()) -> None:
        super().__init__(message)
        self.constraints = list(constraints)


@dataclass(frozen=True)
class Solved3D:
    """The solve: every point's position, in input order, and the diagnosis."""

    points: dict[str, Point]
    dof: int
    redundant: list[int]


class _System:
    def __init__(
        self,
        positions: Mapping[str, Point],
        fixed: Mapping[str, Point],
        lines: Mapping[str, tuple[str, str]],
        constraints: Sequence[Sketch3DConstraint],
    ) -> None:
        self.fixed = {key: np.array(value, dtype=float) for key, value in fixed.items()}
        self.index: dict[str, int] = {}
        start: list[float] = []
        for key, value in positions.items():
            if key in self.fixed:
                continue
            self.index[key] = len(start)
            start.extend(value)
        self.x0: _Array = np.array(start, dtype=float)
        self.lines = lines
        self.constraints = [c for c in constraints if not isinstance(c, Sketch3DFixed)]
        self.owners = [
            i for i, c in enumerate(constraints) if not isinstance(c, Sketch3DFixed)
        ]

    def _at(self, x: _Array, key: str) -> _Array:
        if key in self.fixed:
            return self.fixed[key]
        i = self.index[key]
        return x[i : i + 3]

    def _rows(
        self, x: _Array, constraint: Sketch3DConstraint
    ) -> tuple[list[float], list[_Array]]:
        """Residuals and Jacobian rows (dense, len(x)) of one constraint."""
        n = x.size

        def row(entries: Sequence[tuple[str, _Array]]) -> _Array:
            out: _Array = np.zeros(n)
            for key, grad in entries:
                if key in self.index:
                    i = self.index[key]
                    out[i : i + 3] += grad
            return out

        unit = np.eye(3)
        match constraint:
            case Sketch3DCoincident(a=a, b=b):
                d = self._at(x, a) - self._at(x, b)
                return [float(v) for v in d], [
                    row([(a, unit[k]), (b, -unit[k])]) for k in range(3)
                ]
            case Sketch3DAlong(line=line, axis=axis):
                a, b = self.lines[line]
                d = self._at(x, b) - self._at(x, a)
                across = [k for k in range(3) if k != _AXIS[axis]]
                return [float(d[k]) for k in across], [
                    row([(b, unit[k]), (a, -unit[k])]) for k in across
                ]
            case Sketch3DLength() | Sketch3DDistance():
                if isinstance(constraint, Sketch3DLength):
                    a, b = self.lines[constraint.line]
                else:
                    a, b = constraint.a, constraint.b
                d = self._at(x, b) - self._at(x, a)
                length = float(np.linalg.norm(d))
                if length <= 1e-12:
                    raise _Degenerate
                u = d / length
                return [length - constraint.value_mm], [row([(b, u), (a, -u)])]
            case Sketch3DFixed():  # pragma: no cover - filtered in __init__
                return [], []

    def evaluate(self, x: _Array) -> tuple[_Array, _Array, list[int]]:
        """Residual vector, Jacobian, and the owning constraint of each row."""
        residuals: list[float] = []
        rows: list[_Array] = []
        owner: list[int] = []
        for index, constraint in zip(self.owners, self.constraints, strict=True):
            values, grads = self._rows(x, constraint)
            residuals.extend(values)
            rows.extend(grads)
            owner.extend([index] * len(values))
        jacobian = np.array(rows, dtype=float).reshape(len(rows), x.size)
        return np.array(residuals, dtype=float), jacobian, owner


class _Degenerate(Exception):
    """A length or distance whose two points coincide (no direction)."""


def _rank(matrix: _Array) -> int:
    if matrix.size == 0:
        return 0
    singular = np.linalg.svd(matrix, compute_uv=False)
    if singular.size == 0 or singular[0] == 0.0:
        return 0
    return int(np.count_nonzero(singular > singular[0] * _RANK_RELATIVE))


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
    """
    system = _System(positions, fixed, lines, constraints)
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
        residual, jacobian, owner = system.evaluate(x)
        for _ in range(_MAX_ITERATIONS):
            if residual.size == 0 or np.max(np.abs(residual)) <= (
                _RESIDUAL_RELATIVE * scale
            ):
                break
            step = np.linalg.lstsq(jacobian, -residual, rcond=None)[0]
            norm = float(np.linalg.norm(residual))
            alpha = 1.0
            for _ in range(40):
                trial = x + alpha * step
                trial_residual, trial_jacobian, _ = system.evaluate(trial)
                if float(np.linalg.norm(trial_residual)) < norm:
                    break
                alpha /= 2
            else:
                break  # no descent: a local minimum with a residual left
            x = trial
            residual, jacobian = trial_residual, trial_jacobian
    except _Degenerate:
        raise Sketch3DConflictError(
            "A dimensioned line or distance in the 3D sketch has zero length; "
            "move one of its points first."
        ) from None
    if residual.size and np.max(np.abs(residual)) > _CONFLICT_RELATIVE * scale:
        worst = owner[int(np.argmax(np.abs(residual)))]
        raise Sketch3DConflictError(
            "The 3D sketch's relations cannot all hold (they contradict each "
            f"other; constraint {worst + 1} is furthest off). Delete or change one.",
            [worst],
        )
    # Redundancy: a constraint whose rows add no rank to the ones before it.
    redundant: list[int] = []
    kept: list[_Array] = []
    rank = 0
    for index in dict.fromkeys(owner):
        rows = [jacobian[r] for r in range(len(owner)) if owner[r] == index]
        grown = _rank(np.array(kept + rows)) if kept or rows else 0
        if grown < rank + len(rows):
            redundant.append(index)
        kept.extend(rows)
        rank = _rank(np.array(kept))
    dof = x.size - _rank(jacobian) if residual.size else x.size
    solved: dict[str, Point] = {}
    for key in positions:
        p = system._at(x, key)  # pyright: ignore[reportPrivateUsage]
        solved[key] = (float(p[0]), float(p[1]), float(p[2]))
    return Solved3D(solved, dof, redundant)
