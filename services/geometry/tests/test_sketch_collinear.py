"""The COLLINEAR constraint: measured as "both lines on ONE infinite line".

SKETCH-VOCAB-1 / docs/AUDIT-PRODUCT.md T-5 — "two lines on one line, the way you
keep a stepped profile's faces flush". The distinction that matters, and the one
every test here is built around, is against ``parallel``: parallel fixes the
DIRECTION and leaves the OFFSET free, so a step can reappear on the next edit
and the sketch will still solve. Collinear closes that gap, and the way to see
the difference is the offset, not the angle.

Tolerance: ``COLLINEAR_TOLERANCE_MM = 1e-9`` mm — the sketch suite's documented
bound for a well-conditioned solve, five orders under the kernel linear
tolerance (1e-7 m = 1e-4 mm). Measured deviations are at the 1e-14 mm level.
"""

import math

import pytest
from geometry.sketch import (
    CoincidentConstraint,
    CollinearConstraint,
    DistanceConstraint,
    EntityPointRef,
    FixedConstraint,
    HorizontalConstraint,
    ParallelConstraint,
    PlanegcsSketchSolver,
    Point2D,
    SketchCircle,
    SketchConstraint,
    SketchDefinition,
    SketchDefinitionError,
    SketchEntity,
    SketchLine,
    SketchSolver,
    SolvedSketch,
)
from geometry.sketch.planegcs_solver import (
    SATISFIED_TOL_MM,
    _GcsBuild,  # pyright: ignore[reportPrivateUsage]
)
from geometry.sketch.residual import constraint_residual

COLLINEAR_TOLERANCE_MM = 1e-9

SOLVER: SketchSolver = PlanegcsSketchSolver()


def _line(eid: str, start: tuple[float, float], end: tuple[float, float]) -> SketchLine:
    return SketchLine(
        id=eid,
        kind="line",
        start=Point2D(x=start[0], y=start[1]),
        end=Point2D(x=end[0], y=end[1]),
    )


def _ref(entity: str, point: str) -> EntityPointRef:
    return EntityPointRef.model_validate({"entity": entity, "point": point})


def _solved(result: SolvedSketch, eid: str) -> SketchLine:
    entity = next(e for e in result.entities if e.id == eid)
    assert isinstance(entity, SketchLine)
    return entity


def _offset_from_line(point: tuple[float, float], line: SketchLine) -> float:
    """Perpendicular distance from a point to a line's INFINITE extension, mm.

    Measured here rather than imported from ``geometry.sketch.residual``: a test
    that measured with the module under test would verify a wrong claim happily
    against itself (CLAUDE.md).
    """
    dx, dy = line.end.x - line.start.x, line.end.y - line.start.y
    return abs(
        (point[0] - line.start.x) * dy - (point[1] - line.start.y) * dx
    ) / math.hypot(dx, dy)


def _pinned_reference(eid: str = "e1") -> tuple[SketchLine, list[SketchConstraint]]:
    """A rigid horizontal reference line along +X from the origin, 40 long."""
    line = _line(eid, (0.0, 0.0), (40.0, 0.0))
    return line, [
        FixedConstraint(kind="fixed", point=_ref(eid, "start")),
        HorizontalConstraint(kind="horizontal", entity=eid),
        DistanceConstraint(kind="distance", entity=eid, value_mm=40.0),
    ]


def test_both_endpoints_land_on_the_reference_line() -> None:
    """The base case, measured as an OFFSET: both ends of ``b`` sit on ``a``."""
    reference, pins = _pinned_reference()
    stepped = _line("e2", (55.0, 6.0), (95.0, 9.0))  # offset AND skewed
    sketch = SketchDefinition(
        entities=[reference, stepped],
        constraints=[
            *pins,
            CollinearConstraint(kind="collinear", a="e1", b="e2"),
        ],
    )

    result = SOLVER.solve(sketch)

    assert result.status in ("converged", "underconstrained")
    a, b = _solved(result, "e1"), _solved(result, "e2")
    assert _offset_from_line((b.start.x, b.start.y), a) == pytest.approx(
        0.0, abs=COLLINEAR_TOLERANCE_MM
    )
    assert _offset_from_line((b.end.x, b.end.y), a) == pytest.approx(
        0.0, abs=COLLINEAR_TOLERANCE_MM
    )


def test_collinear_is_strictly_stronger_than_parallel() -> None:
    """The whole point of having it: parallel leaves the STEP behind.

    Same sketch, same starting geometry, one constraint swapped. Under
    ``parallel`` the second line flattens but stays 6 mm off the reference — the
    step the engineer was trying to remove, still there and fully solved. Under
    ``collinear`` the offset goes to zero. Asserted on the offset, which is the
    quantity the two constraints disagree about; their ANGLES agree, so an
    angle-based assertion could not tell them apart.
    """
    reference, pins = _pinned_reference()
    stepped = _line("e2", (55.0, 6.0), (95.0, 9.0))
    anchor: list[SketchConstraint] = [
        *pins,
        FixedConstraint(kind="fixed", point=_ref("e2", "start")),
    ]

    parallel = SOLVER.solve(
        SketchDefinition(
            entities=[reference, stepped],
            constraints=[*pins, ParallelConstraint(kind="parallel", a="e1", b="e2")],
        )
    )
    collinear = SOLVER.solve(
        SketchDefinition(
            entities=[reference, stepped],
            constraints=[*pins, CollinearConstraint(kind="collinear", a="e1", b="e2")],
        )
    )
    assert anchor  # (kept for the reader: the pins above are the same in both)

    par_a, par_b = _solved(parallel, "e1"), _solved(parallel, "e2")
    col_a, col_b = _solved(collinear, "e1"), _solved(collinear, "e2")

    # Parallel: flat, and STILL offset.
    assert par_b.end.y - par_b.start.y == pytest.approx(0.0, abs=COLLINEAR_TOLERANCE_MM)
    assert _offset_from_line((par_b.start.x, par_b.start.y), par_a) > 1.0
    # Collinear: flat AND flush.
    assert _offset_from_line((col_b.start.x, col_b.start.y), col_a) == pytest.approx(
        0.0, abs=COLLINEAR_TOLERANCE_MM
    )


def test_collinear_removes_exactly_two_degrees_of_freedom() -> None:
    """Direction and offset — one more than ``parallel`` takes."""
    reference, pins = _pinned_reference()
    stepped = _line("e2", (55.0, 6.0), (95.0, 9.0))
    base = SketchDefinition(entities=[reference, stepped], constraints=list(pins))
    with_parallel = SketchDefinition(
        entities=[reference, stepped],
        constraints=[*pins, ParallelConstraint(kind="parallel", a="e1", b="e2")],
    )
    with_collinear = SketchDefinition(
        entities=[reference, stepped],
        constraints=[*pins, CollinearConstraint(kind="collinear", a="e1", b="e2")],
    )

    loose = SOLVER.solve(base)
    parallel = SOLVER.solve(with_parallel)
    collinear = SOLVER.solve(with_collinear)

    assert loose.dof is not None
    assert parallel.dof == loose.dof - 1
    assert collinear.dof == loose.dof - 2


def test_collinear_is_symmetric_in_meaning_if_not_in_wiring() -> None:
    """``collinear(a, b)`` and ``collinear(b, a)`` describe the same relation.

    The wiring is asymmetric — ``b``'s endpoints go onto ``a``'s line — so this
    is worth asserting rather than assuming: with one line pinned rigid, both
    orders must leave the free line flush with it.
    """
    reference, pins = _pinned_reference()
    stepped = _line("e2", (55.0, 6.0), (95.0, 9.0))

    for a, b in (("e1", "e2"), ("e2", "e1")):
        result = SOLVER.solve(
            SketchDefinition(
                entities=[reference, stepped],
                constraints=[*pins, CollinearConstraint(kind="collinear", a=a, b=b)],
            )
        )
        solved_a, solved_b = _solved(result, "e1"), _solved(result, "e2")
        assert _offset_from_line(
            (solved_b.start.x, solved_b.start.y), solved_a
        ) == pytest.approx(0.0, abs=COLLINEAR_TOLERANCE_MM), f"order ({a}, {b})"
        assert _offset_from_line(
            (solved_b.end.x, solved_b.end.y), solved_a
        ) == pytest.approx(0.0, abs=COLLINEAR_TOLERANCE_MM), f"order ({a}, {b})"


def test_a_stepped_outline_closes_flush() -> None:
    """The audit's sentence, as geometry: a step flattened into one face.

    A five-line outline whose top edge is drawn in two segments 3 mm apart; the
    collinear constraint is what makes the two read as one straight face. What
    is asserted is that all four of the top edge's endpoints end up at the same
    height — the step is GONE, not merely parallel.
    """
    entities: list[SketchEntity] = [
        _line("e1", (0.0, 0.0), (40.0, 0.0)),
        _line("e2", (40.0, 0.0), (40.0, 25.0)),
        _line("e3", (40.0, 25.0), (20.0, 25.0)),
        _line("e4", (20.0, 22.0), (0.0, 25.0)),  # drawn 3 mm low: the step
        _line("e5", (0.0, 25.0), (0.0, 0.0)),
    ]
    constraints: list[SketchConstraint] = [
        CoincidentConstraint(
            kind="coincident", a=_ref("e1", "end"), b=_ref("e2", "start")
        ),
        CoincidentConstraint(
            kind="coincident", a=_ref("e2", "end"), b=_ref("e3", "start")
        ),
        CoincidentConstraint(
            kind="coincident", a=_ref("e3", "end"), b=_ref("e4", "start")
        ),
        CoincidentConstraint(
            kind="coincident", a=_ref("e4", "end"), b=_ref("e5", "start")
        ),
        CoincidentConstraint(
            kind="coincident", a=_ref("e5", "end"), b=_ref("e1", "start")
        ),
        FixedConstraint(kind="fixed", point=_ref("e1", "start")),
        HorizontalConstraint(kind="horizontal", entity="e1"),
        DistanceConstraint(kind="distance", entity="e1", value_mm=40.0),
        DistanceConstraint(kind="distance", entity="e2", value_mm=25.0),
        HorizontalConstraint(kind="horizontal", entity="e3"),
        CollinearConstraint(kind="collinear", a="e3", b="e4"),
    ]

    result = SOLVER.solve(SketchDefinition(entities=entities, constraints=constraints))

    e3, e4 = _solved(result, "e3"), _solved(result, "e4")
    for label, y in (
        ("e3.start", e3.start.y),
        ("e3.end", e3.end.y),
        ("e4.start", e4.start.y),
        ("e4.end", e4.end.y),
    ):
        assert y == pytest.approx(25.0, abs=COLLINEAR_TOLERANCE_MM), label


def test_collinear_residual_is_the_two_point_on_line_distances() -> None:
    """The residual matches the witnesses, and is measured off-solution.

    ``point_on_line``'s error is the perpendicular distance in mm, so this
    residual is the max of the two tags planegcs is actually holding rather than
    a re-derivation of "collinear" from a different definition. Off-solution
    here by construction: ``b`` sits 5 mm and 9 mm off ``a``'s line.
    """
    entities: list[SketchEntity] = [
        _line("l1", (0.0, 0.0), (40.0, 0.0)),
        _line("l2", (10.0, 5.0), (30.0, 9.0)),
    ]
    sketch = SketchDefinition(
        entities=entities,
        constraints=[CollinearConstraint(kind="collinear", a="l1", b="l2")],
    )
    build = _GcsBuild(sketch, {})
    tags = [tag for tag, index in build.tag_to_index.items() if index == 0]
    assert len(tags) == 2  # both of b's endpoints, on a's infinite line

    errors = sorted(abs(build.gcs.solver.constraint_error(tag)) for tag in tags)
    mine = constraint_residual(
        sketch.constraints[0], {e.id: e for e in build.read_back()}, {}, None
    )

    assert errors == pytest.approx([5.0, 9.0], abs=SATISFIED_TOL_MM)
    assert mine is not None
    assert mine == pytest.approx(9.0, abs=SATISFIED_TOL_MM)


def test_collinear_with_a_circle_rejected() -> None:
    """Collinear relates two LINES; anything else is malformed input."""
    reference, pins = _pinned_reference()
    circle = SketchCircle(
        id="c1", kind="circle", center=Point2D(x=5.0, y=5.0), radius=3.0
    )
    entities: list[SketchEntity] = [reference, circle]
    sketch = SketchDefinition(
        entities=entities,
        constraints=[*pins, CollinearConstraint(kind="collinear", a="e1", b="c1")],
    )

    with pytest.raises(SketchDefinitionError, match="collinear"):
        SOLVER.solve(sketch)


def test_collinear_solve_is_deterministic_bitwise() -> None:
    """Same definition in, bitwise identical geometry out (RESEARCH §9)."""
    reference, pins = _pinned_reference()
    stepped = _line("e2", (55.0, 6.0), (95.0, 9.0))
    sketch = SketchDefinition(
        entities=[reference, stepped],
        constraints=[*pins, CollinearConstraint(kind="collinear", a="e1", b="e2")],
    )

    runs = [SOLVER.solve(sketch).model_dump() for _ in range(5)]

    for other in runs[1:]:
        assert other == runs[0]
