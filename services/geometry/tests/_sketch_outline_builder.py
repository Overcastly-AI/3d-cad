"""A REALISTIC part outline, at the size a working engineer actually draws.

The solver corpus's sketches top out at twelve entities, which is smaller than
any real profile — and that is exactly how a settle that took **13 seconds** on
one dimension edit shipped unnoticed (SETTLE-PERF-1,
``docs/AUDIT-ENGINEERING.md`` N11). This module is the missing shape: a closed
rectilinear "staircase" outline of *n* lines, every edge horizontal or vertical,
every corner coincident, and one driving width dimension — i.e. a bracket
profile with a few steps in it, partly dimensioned, which is what a partly-
constrained sketch looks like in practice. Its free DOF is ``n - 1``.

One builder, two fixtures, and the difference between them is the whole point:

* ``outline(n, width_mm=None)`` — the sketch as drawn, already an exact
  solution. This is what a tree REBUILD re-solves, because ``PartPage`` adopts
  solved positions back into the store, so it is the commonest solve in the
  product and it takes the settle's one-solve fast path.
* ``outline(n, width_mm=14.0)`` — the same sketch with a driving dimension
  asking for a width the geometry does not have: *typing a new number into an
  existing dimension*, the commonest INTERACTION in the sketcher, and the path
  that was quadratic per solve and linear in solves, i.e. cubic overall.

Shared by ``test_benchmarks.py``'s ``sketch_solve`` budgets so the gate and any
future golden are authored once (CLAUDE.md DRY rule).
"""

from __future__ import annotations

from geometry.sketch.schemas import (
    CoincidentConstraint,
    DistanceConstraint,
    EntityPointRef,
    HorizontalConstraint,
    Point2D,
    SketchConstraint,
    SketchDefinition,
    SketchEntity,
    SketchLine,
    VerticalConstraint,
)

#: Step size of the staircase, mm. Every edge is this long except the return.
STEP_MM = 10.0


def outline_vertices(line_count: int) -> list[tuple[float, float]]:
    """Corners of the closed staircase, in traversal order.

    ``line_count`` must be even and at least 4: the walk climbs
    ``(line_count - 2) / 2`` steps of one horizontal plus one vertical edge, then
    returns along one long horizontal and closes with one vertical, so the
    horizontal/vertical alternation is exact and the outline is closed.
    """
    if line_count % 2 or line_count < 4:
        raise ValueError(f"line_count must be even and >= 4, got {line_count}")
    vertices: list[tuple[float, float]] = [(0.0, 0.0)]
    x = y = 0.0
    for _ in range((line_count - 2) // 2):
        x += STEP_MM
        vertices.append((x, y))
        y += STEP_MM
        vertices.append((x, y))
    vertices.append((0.0, y))
    return vertices


def outline(line_count: int, *, width_mm: float | None) -> SketchDefinition:
    """The outline, optionally carrying a driving width dimension on ``e0``.

    ``width_mm=None`` leaves it undimensioned — the sketch as drawn, which is
    already an exact solution. Passing a value other than :data:`STEP_MM` is the
    dimension EDIT: the constraint asks for a width the drawn geometry does not
    have, so the solve has to move something.
    """
    vertices = outline_vertices(line_count)
    entities: list[SketchEntity] = []
    constraints: list[SketchConstraint] = []
    for index in range(line_count):
        start = vertices[index]
        end = vertices[(index + 1) % len(vertices)]
        entities.append(
            SketchLine(
                id=f"e{index}",
                kind="line",
                start=Point2D(x=start[0], y=start[1]),
                end=Point2D(x=end[0], y=end[1]),
            )
        )
        constraints.append(
            HorizontalConstraint(kind="horizontal", entity=f"e{index}")
            if index % 2 == 0
            else VerticalConstraint(kind="vertical", entity=f"e{index}")
        )
        constraints.append(
            CoincidentConstraint(
                kind="coincident",
                a=EntityPointRef(entity=f"e{index}", point="end"),
                b=EntityPointRef(entity=f"e{(index + 1) % line_count}", point="start"),
            )
        )
    if width_mm is not None:
        constraints.append(
            DistanceConstraint(kind="distance", entity="e0", value_mm=width_mm)
        )
    return SketchDefinition(entities=entities, constraints=constraints)
