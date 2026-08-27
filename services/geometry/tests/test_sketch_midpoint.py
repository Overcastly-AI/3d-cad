"""The MIDPOINT constraint: the point is measured against the middle it names.

SKETCH-VOCAB-1 / docs/AUDIT-PRODUCT.md T-5 — "place a hole on the centre of an
edge", the constraint the audit called extremely common and this sketcher did
not have. What makes it worth a constraint rather than a coordinate is that it
TRACKS: move either end of the line and the point follows to the new middle,
which is the property the last test here asserts.

Tolerance: ``MIDPOINT_TOLERANCE_MM = 1e-9`` mm, the sketch suite's documented
bound for a well-conditioned solve — five orders under the kernel linear
tolerance (1e-7 m = 1e-4 mm). Measured deviations are at the 1e-14 mm level.
"""

import pytest
from geometry.sketch import (
    DistanceConstraint,
    EntityPointRef,
    FixedConstraint,
    HorizontalConstraint,
    MidpointConstraint,
    PlanegcsSketchSolver,
    Point2D,
    SketchCircle,
    SketchConstraint,
    SketchDefinition,
    SketchDefinitionError,
    SketchEntity,
    SketchLine,
    SketchPoint,
    SketchSolver,
    SolvedSketch,
)
from geometry.sketch.planegcs_solver import (
    SATISFIED_TOL_MM,
    _GcsBuild,  # pyright: ignore[reportPrivateUsage]
)
from geometry.sketch.residual import constraint_residual

MIDPOINT_TOLERANCE_MM = 1e-9

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


def _solved_line(result: SolvedSketch, eid: str) -> SketchLine:
    entity = next(e for e in result.entities if e.id == eid)
    assert isinstance(entity, SketchLine)
    return entity


def _solved_point(result: SolvedSketch, eid: str) -> tuple[float, float]:
    entity = next(e for e in result.entities if e.id == eid)
    if isinstance(entity, SketchPoint):
        return (entity.position.x, entity.position.y)
    assert isinstance(entity, SketchCircle)
    return (entity.center.x, entity.center.y)


def _pinned_edge(
    eid: str = "e1",
    start: tuple[float, float] = (0.0, 0.0),
    end: tuple[float, float] = (40.0, 0.0),
) -> tuple[SketchLine, list[SketchConstraint]]:
    """A line pinned rigid at both ends — the edge a midpoint is taken of."""
    line = _line(eid, start, end)
    return line, [
        FixedConstraint(kind="fixed", point=_ref(eid, "start")),
        FixedConstraint(kind="fixed", point=_ref(eid, "end")),
    ]


def test_a_point_lands_on_the_middle_of_the_line() -> None:
    """The base case, measured: the point IS the mean of the two endpoints."""
    edge, pins = _pinned_edge(end=(40.0, 20.0))  # deliberately not axis-aligned
    free = SketchPoint(id="p1", kind="point", position=Point2D(x=3.0, y=30.0))
    entities: list[SketchEntity] = [edge, free]
    sketch = SketchDefinition(
        entities=entities,
        constraints=[
            *pins,
            MidpointConstraint(
                kind="midpoint", point=_ref("p1", "position"), line="e1"
            ),
        ],
    )

    result = SOLVER.solve(sketch)

    assert result.status in ("converged", "underconstrained")
    solved_edge = _solved_line(result, "e1")
    expected = (
        (solved_edge.start.x + solved_edge.end.x) / 2,
        (solved_edge.start.y + solved_edge.end.y) / 2,
    )
    x, y = _solved_point(result, "p1")
    assert x == pytest.approx(expected[0], abs=MIDPOINT_TOLERANCE_MM)
    assert y == pytest.approx(expected[1], abs=MIDPOINT_TOLERANCE_MM)
    assert (x, y) == pytest.approx((20.0, 10.0), abs=MIDPOINT_TOLERANCE_MM)


def test_midpoint_removes_exactly_two_degrees_of_freedom() -> None:
    """A point on a middle is fully determined — both its coordinates, not one.

    A wiring that added only the point-on-line half would leave the point free
    to slide ALONG the edge and still look right in a screenshot; the DOF count
    is what tells the two apart.
    """
    edge, pins = _pinned_edge()
    free = SketchPoint(id="p1", kind="point", position=Point2D(x=3.0, y=30.0))
    entities: list[SketchEntity] = [edge, free]
    base = SketchDefinition(entities=entities, constraints=list(pins))
    constrained = SketchDefinition(
        entities=entities,
        constraints=[
            *pins,
            MidpointConstraint(
                kind="midpoint", point=_ref("p1", "position"), line="e1"
            ),
        ],
    )

    loose = SOLVER.solve(base)
    result = SOLVER.solve(constrained)

    assert loose.dof is not None
    assert result.dof == loose.dof - 2


def test_a_hole_centre_sits_on_the_middle_of_an_edge() -> None:
    """The audit's own example, end to end: a hole centred on an edge.

    ``point`` addresses a circle's ``center`` exactly as it addresses a point
    entity's ``position`` — the constraint is about POINTS, not about which kind
    of entity happens to own them.
    """
    edge, pins = _pinned_edge()
    hole = SketchCircle(
        id="h1", kind="circle", center=Point2D(x=8.0, y=6.0), radius=4.0
    )
    entities: list[SketchEntity] = [edge, hole]
    sketch = SketchDefinition(
        entities=entities,
        constraints=[
            *pins,
            MidpointConstraint(kind="midpoint", point=_ref("h1", "center"), line="e1"),
        ],
    )

    result = SOLVER.solve(sketch)

    assert _solved_point(result, "h1") == pytest.approx(
        (20.0, 0.0), abs=MIDPOINT_TOLERANCE_MM
    )


def test_the_midpoint_tracks_when_the_line_is_re_dimensioned() -> None:
    """The whole reason it is a constraint and not a coordinate.

    Same sketch, one number changed: the edge's driving length goes 40 -> 60 and
    the point must move to 30, not stay at 20. A coordinate would not.
    """

    def solve_at(length: float) -> tuple[float, float]:
        edge = _line("e1", (0.0, 0.0), (40.0, 0.0))
        free = SketchPoint(id="p1", kind="point", position=Point2D(x=20.0, y=0.0))
        entities: list[SketchEntity] = [edge, free]
        return _solved_point(
            SOLVER.solve(
                SketchDefinition(
                    entities=entities,
                    constraints=[
                        FixedConstraint(kind="fixed", point=_ref("e1", "start")),
                        HorizontalConstraint(kind="horizontal", entity="e1"),
                        DistanceConstraint(
                            kind="distance", entity="e1", value_mm=length
                        ),
                        MidpointConstraint(
                            kind="midpoint", point=_ref("p1", "position"), line="e1"
                        ),
                    ],
                )
            ),
            "p1",
        )

    assert solve_at(40.0) == pytest.approx((20.0, 0.0), abs=MIDPOINT_TOLERANCE_MM)
    assert solve_at(60.0) == pytest.approx((30.0, 0.0), abs=MIDPOINT_TOLERANCE_MM)


def test_midpoint_residual_matches_the_two_witnesses_planegcs_reports() -> None:
    """The bisector formula is the PROBED one, not the natural-language one.

    "Point on the perpendicular bisector" reads as ``| |p-l1| - |p-l2| |``, and
    planegcs reports something else: ``(|p-l1|^2 - |p-l2|^2) / L``, i.e. twice
    the point's offset ALONG the line from the midpoint. On a 40 mm line with
    the point 100 mm past its end those are 240 and 40 — a factor of six, and
    invisible to any comparison made at a solution, because both are zero there.
    This pins the number, off-solution, against the witness itself.
    """
    line = _line("e1", (0.0, 0.0), (40.0, 0.0))
    point = SketchPoint(id="p1", kind="point", position=Point2D(x=140.0, y=0.0))
    entities: list[SketchEntity] = [line, point]
    sketch = SketchDefinition(
        entities=entities,
        constraints=[
            MidpointConstraint(kind="midpoint", point=_ref("p1", "position"), line="e1")
        ],
    )
    build = _GcsBuild(sketch, {})
    tags = [tag for tag, index in build.tag_to_index.items() if index == 0]
    assert len(tags) == 2  # on-the-line AND on-the-perpendicular-bisector

    worst = max(abs(build.gcs.solver.constraint_error(tag)) for tag in tags)
    mine = constraint_residual(
        sketch.constraints[0], {e.id: e for e in build.read_back()}, {}, None
    )

    # (140^2 - 100^2) / 40 = 240, which is 2 x the 120 mm offset from the middle.
    assert worst == pytest.approx(240.0, abs=SATISFIED_TOL_MM)
    assert mine is not None
    assert mine == pytest.approx(worst, abs=SATISFIED_TOL_MM)
    # The natural-language formula, for the record — six times blinder.
    assert abs(140.0 - 100.0) == pytest.approx(40.0, abs=1e-12)


def test_midpoint_on_a_non_line_rejected() -> None:
    """A circle has no middle to sit on; the reference is malformed input."""
    hole = SketchCircle(
        id="h1", kind="circle", center=Point2D(x=0.0, y=0.0), radius=4.0
    )
    free = SketchPoint(id="p1", kind="point", position=Point2D(x=3.0, y=3.0))
    entities: list[SketchEntity] = [hole, free]
    sketch = SketchDefinition(
        entities=entities,
        constraints=[
            MidpointConstraint(kind="midpoint", point=_ref("p1", "position"), line="h1")
        ],
    )

    with pytest.raises(SketchDefinitionError, match="midpoint"):
        SOLVER.solve(sketch)


def test_midpoint_can_name_a_spline_fit_point() -> None:
    """``point`` is an EntityPointRef, so the fit-point form works unchanged.

    Not a special case in the wiring — it falls out of resolving the reference
    the same way ``coincident`` does — but a constraint that quietly dropped its
    point refs would leave the fit point unregistered and surface a misleading
    "no such point" error, which is exactly what the ``assert_never`` tail on
    ``_constraint_point_refs`` exists to prevent.
    """
    from geometry.sketch import SketchSpline

    edge, pins = _pinned_edge()
    spline = SketchSpline(
        id="s1",
        kind="spline",
        points=[
            Point2D(x=0.0, y=10.0),
            Point2D(x=5.0, y=14.0),
            Point2D(x=12.0, y=10.0),
        ],
    )
    entities: list[SketchEntity] = [edge, spline]
    sketch = SketchDefinition(
        entities=entities,
        constraints=[
            *pins,
            MidpointConstraint(kind="midpoint", point=_ref("s1", "fit1"), line="e1"),
        ],
    )

    result = SOLVER.solve(sketch)
    solved = next(e for e in result.entities if e.id == "s1")
    assert isinstance(solved, SketchSpline)

    assert (solved.points[1].x, solved.points[1].y) == pytest.approx(
        (20.0, 0.0), abs=MIDPOINT_TOLERANCE_MM
    )
    # The fit points nobody constrained are preserved exactly.
    assert (solved.points[0].x, solved.points[0].y) == (0.0, 10.0)


def test_midpoint_solve_is_deterministic_bitwise() -> None:
    """Same definition in, bitwise identical geometry out (RESEARCH §9)."""
    edge, pins = _pinned_edge(end=(37.0, 19.0))
    free = SketchPoint(id="p1", kind="point", position=Point2D(x=3.0, y=30.0))
    entities: list[SketchEntity] = [edge, free]
    sketch = SketchDefinition(
        entities=entities,
        constraints=[
            *pins,
            MidpointConstraint(
                kind="midpoint", point=_ref("p1", "position"), line="e1"
            ),
        ],
    )

    runs = [SOLVER.solve(sketch).model_dump() for _ in range(5)]

    for other in runs[1:]:
        assert other == runs[0]
