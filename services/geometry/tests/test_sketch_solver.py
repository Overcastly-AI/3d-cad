"""SketchSolver unit suite — the spike benchmark from RESEARCH §2.

Exercises the planegcs backend through the ``SketchSolver`` protocol only:
the benchmark rectangle (solved positions asserted analytically), the solver
determinism gate (RESEARCH §9), and the diagnosis statuses (underconstrained,
overconstrained, conflicting) as *reported outcomes*, never crashes.

Tolerance: ``RECTANGLE_TOLERANCE_MM = 1e-9`` is the documented benchmark
bound, not an ad-hoc epsilon. Rationale: the benchmark system is small and
well-conditioned; planegcs's DogLeg solve lands on the analytic corner
coordinates with 0.0 observed deviation (spike evidence, RESEARCH §2), and
1e-9 mm still sits five orders of magnitude below the kernel linear
tolerance (1e-7 m = 1e-4 mm), so a pass here can never mask a
kernel-relevant error. Determinism assertions are bitwise (``==``) on
purpose — determinism takes no tolerance.
"""

import math

import pytest
from geometry.sketch import (
    CoincidentConstraint,
    DistanceConstraint,
    EntityPointRef,
    FixedConstraint,
    HorizontalConstraint,
    ParallelConstraint,
    PerpendicularConstraint,
    PlanegcsSketchSolver,
    Point2D,
    RadiusConstraint,
    SketchArc,
    SketchCircle,
    SketchConstraint,
    SketchDefinition,
    SketchDefinitionError,
    SketchEntity,
    SketchLine,
    SketchSolver,
    TangentConstraint,
    VerticalConstraint,
)

#: Documented benchmark tolerance (mm) — see module docstring for rationale.
RECTANGLE_TOLERANCE_MM = 1e-9

#: The winning backend under test, typed as the protocol so the suite is
#: backend-agnostic by construction.
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


def rectangle_sketch(*, guess_shift: float = 0.0) -> SketchDefinition:
    """The RESEARCH §2 benchmark rectangle: 40 x 25 mm, anchored at origin.

    Four lines drawn deliberately sloppily (``guess_shift`` displaces the
    starting guess further), squared up by coincident corners +
    horizontal/vertical constraints, driven by two dimensions, anchored by
    fixing e1.start at its input position (0, 0). 16 parameters, 16
    constraint equations -> fully constrained, DOF 0. Mirrors the worked
    example of docs/design/feature-tree.md §6 plus the anchor.
    """
    s = guess_shift
    entities: list[SketchEntity] = [
        _line("e1", (0.0, 0.0), (38.0 + s, 1.0 + s)),
        _line("e2", (39.0 + s, 0.5 + s), (41.0 + s, 24.0 + s)),
        _line("e3", (40.5 + s, 26.0 + s), (-1.0 + s, 25.5 + s)),
        _line("e4", (0.5 + s, 24.5 + s), (-0.5 + s, 1.0 + s)),
    ]

    def _coincident(a: EntityPointRef, b: EntityPointRef) -> CoincidentConstraint:
        return CoincidentConstraint(kind="coincident", a=a, b=b)

    constraints: list[SketchConstraint] = [
        _coincident(_ref("e1", "end"), _ref("e2", "start")),
        _coincident(_ref("e2", "end"), _ref("e3", "start")),
        _coincident(_ref("e3", "end"), _ref("e4", "start")),
        _coincident(_ref("e4", "end"), _ref("e1", "start")),
        HorizontalConstraint(kind="horizontal", entity="e1"),
        VerticalConstraint(kind="vertical", entity="e2"),
        HorizontalConstraint(kind="horizontal", entity="e3"),
        VerticalConstraint(kind="vertical", entity="e4"),
        DistanceConstraint(kind="distance", entity="e1", value_mm=40.0),
        DistanceConstraint(kind="distance", entity="e2", value_mm=25.0),
        FixedConstraint(kind="fixed", point=_ref("e1", "start")),
    ]
    return SketchDefinition(entities=entities, constraints=constraints)


#: Analytic corner positions: anchored at (0,0), width 40 (e1 horizontal),
#: height 25 (e2 vertical), CCW winding as drawn.
EXPECTED_CORNERS: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "e1": ((0.0, 0.0), (40.0, 0.0)),
    "e2": ((40.0, 0.0), (40.0, 25.0)),
    "e3": ((40.0, 25.0), (0.0, 25.0)),
    "e4": ((0.0, 25.0), (0.0, 0.0)),
}


def _positions(solved_entities: list[SketchEntity]) -> list[tuple[float, ...]]:
    """Flatten solved geometry for bitwise comparison."""
    out: list[tuple[float, ...]] = []
    for entity in solved_entities:
        assert isinstance(entity, SketchLine)  # this suite's rectangles are lines
        out.append((entity.start.x, entity.start.y, entity.end.x, entity.end.y))
    return out


def test_benchmark_rectangle_solves_to_analytic_corners() -> None:
    result = SOLVER.solve(rectangle_sketch())
    assert result.status == "converged"
    assert result.dof == 0
    assert result.conflicting_constraints == []
    assert result.redundant_constraints == []
    assert [e.id for e in result.entities] == ["e1", "e2", "e3", "e4"]
    for entity in result.entities:
        assert isinstance(entity, SketchLine)
        (ex1, ey1), (ex2, ey2) = EXPECTED_CORNERS[entity.id]
        assert entity.start.x == pytest.approx(ex1, abs=RECTANGLE_TOLERANCE_MM)
        assert entity.start.y == pytest.approx(ey1, abs=RECTANGLE_TOLERANCE_MM)
        assert entity.end.x == pytest.approx(ex2, abs=RECTANGLE_TOLERANCE_MM)
        assert entity.end.y == pytest.approx(ey2, abs=RECTANGLE_TOLERANCE_MM)


def test_construction_geometry_participates_in_the_solve() -> None:
    """A construction line is a first-class solver entity: it is added to the
    planegcs system, can be constrained (anchored + horizontal + dimensioned),
    and the solve moves it — yet it stays flagged ``construction`` on the way
    out (BACKLOG #2: excluded from the *profile* downstream, never from the
    *solve*)."""
    diagonal = SketchLine(
        id="d1",
        kind="line",
        construction=True,
        start=Point2D(x=1.0, y=2.0),
        end=Point2D(x=30.0, y=9.0),  # sloppy guess the solve squares up
    )
    sketch = SketchDefinition(
        entities=[diagonal],
        constraints=[
            FixedConstraint(kind="fixed", point=_ref("d1", "start")),
            HorizontalConstraint(kind="horizontal", entity="d1"),
            DistanceConstraint(kind="distance", entity="d1", value_mm=50.0),
        ],
    )
    result = SOLVER.solve(sketch)

    assert result.status == "converged"
    assert result.dof == 0
    (solved,) = result.entities
    assert isinstance(solved, SketchLine)
    assert solved.construction is True  # the flag survives the solve
    # Anchored at (1, 2), horizontal, length 50 → end at (51, 2).
    assert solved.start.x == pytest.approx(1.0, abs=RECTANGLE_TOLERANCE_MM)
    assert solved.start.y == pytest.approx(2.0, abs=RECTANGLE_TOLERANCE_MM)
    assert solved.end.x == pytest.approx(51.0, abs=RECTANGLE_TOLERANCE_MM)
    assert solved.end.y == pytest.approx(2.0, abs=RECTANGLE_TOLERANCE_MM)


def test_solve_is_deterministic_bitwise() -> None:
    """Two independent solves of the same definition -> identical floats.

    Bitwise equality, no tolerance: RESEARCH §9's solver-determinism gate.
    """
    first = SOLVER.solve(rectangle_sketch())
    second = PlanegcsSketchSolver().solve(rectangle_sketch())  # fresh backend too
    assert _positions(first.entities) == _positions(second.entities)
    assert first.status == second.status
    assert first.dof == second.dof


def test_fully_constrained_solution_is_starting_guess_insensitive() -> None:
    """A fully-constrained sketch converges to the same analytic solution
    from a displaced starting guess (spike evidence recorded in RESEARCH §2:
    0.0 deviation observed; underconstrained sketches DO stay near their
    guess by design — positions double as the seed)."""
    shifted = SOLVER.solve(rectangle_sketch(guess_shift=3.7))
    baseline = SOLVER.solve(rectangle_sketch())
    for solved, reference in zip(shifted.entities, baseline.entities, strict=True):
        assert isinstance(solved, SketchLine)
        assert isinstance(reference, SketchLine)
        assert solved.start.x == pytest.approx(
            reference.start.x, abs=RECTANGLE_TOLERANCE_MM
        )
        assert solved.start.y == pytest.approx(
            reference.start.y, abs=RECTANGLE_TOLERANCE_MM
        )
        assert solved.end.x == pytest.approx(
            reference.end.x, abs=RECTANGLE_TOLERANCE_MM
        )
        assert solved.end.y == pytest.approx(
            reference.end.y, abs=RECTANGLE_TOLERANCE_MM
        )


def test_underconstrained_sketch_reports_status_and_dof() -> None:
    """Dropping the dimensions + anchor leaves 4 DOF (2 translations + the
    two lengths); the solve still succeeds and says so — no crash."""
    sketch = rectangle_sketch()
    trimmed = SketchDefinition(
        entities=sketch.entities,
        constraints=[
            c
            for c in sketch.constraints
            if not isinstance(c, DistanceConstraint | FixedConstraint)
        ],
    )
    result = SOLVER.solve(trimmed)
    assert result.status == "underconstrained"
    assert result.dof == 4
    assert result.conflicting_constraints == []
    # Geometry is still returned (solved, near the guess) for the sketcher UI.
    assert len(result.entities) == 4


def test_conflicting_constraints_report_conflict_not_crash() -> None:
    """Both endpoints fixed 10 mm apart, then a 25 mm driving dimension:
    unsatisfiable. Reported as status + the offending constraint indices;
    positions come back unchanged (input echo) rather than half-converged."""
    definition = SketchDefinition(
        entities=[_line("e1", (0.0, 0.0), (10.0, 0.0))],
        constraints=[
            FixedConstraint(kind="fixed", point=_ref("e1", "start")),
            FixedConstraint(kind="fixed", point=_ref("e1", "end")),
            DistanceConstraint(kind="distance", entity="e1", value_mm=25.0),
        ],
    )
    result = SOLVER.solve(definition)
    assert result.status == "conflicting"
    assert result.dof is None  # planegcs reports -1 on conflicting systems
    assert result.conflicting_constraints  # non-empty
    assert 2 in result.conflicting_constraints  # the impossible dimension
    assert set(result.conflicting_constraints) <= {0, 1, 2}
    assert _positions(result.entities) == [(0.0, 0.0, 10.0, 0.0)]  # input echo


def test_redundant_constraint_reports_overconstrained() -> None:
    """A duplicated (consistent) driving dimension is flagged redundant, and
    the sketch still solves."""
    definition = SketchDefinition(
        entities=[_line("e1", (0.0, 0.0), (38.0, 1.0))],
        constraints=[
            FixedConstraint(kind="fixed", point=_ref("e1", "start")),
            HorizontalConstraint(kind="horizontal", entity="e1"),
            DistanceConstraint(kind="distance", entity="e1", value_mm=40.0),
            DistanceConstraint(kind="distance", entity="e1", value_mm=40.0),
        ],
    )
    result = SOLVER.solve(definition)
    assert result.status == "overconstrained"
    assert result.redundant_constraints == [3]
    assert result.conflicting_constraints == []
    # Consistent redundancy still solves; the solved length is honored.
    line = result.entities[0]
    assert isinstance(line, SketchLine)
    assert line.end.x == pytest.approx(40.0, abs=RECTANGLE_TOLERANCE_MM)
    assert line.end.y == pytest.approx(0.0, abs=RECTANGLE_TOLERANCE_MM)


def test_circle_radius_dimension() -> None:
    definition = SketchDefinition(
        entities=[
            SketchCircle(
                id="c1", kind="circle", center=Point2D(x=1.0, y=2.0), radius=10.0
            )
        ],
        constraints=[
            FixedConstraint(kind="fixed", point=_ref("c1", "center")),
            RadiusConstraint(kind="radius", entity="c1", value_mm=12.5),
        ],
    )
    result = SOLVER.solve(definition)
    assert result.status == "converged"
    assert result.dof == 0
    circle = result.entities[0]
    assert isinstance(circle, SketchCircle)
    assert circle.radius == pytest.approx(12.5, abs=RECTANGLE_TOLERANCE_MM)
    assert circle.center.x == pytest.approx(1.0, abs=RECTANGLE_TOLERANCE_MM)
    assert circle.center.y == pytest.approx(2.0, abs=RECTANGLE_TOLERANCE_MM)


def test_unknown_entity_reference_raises_definition_error() -> None:
    definition = SketchDefinition(
        entities=[_line("e1", (0.0, 0.0), (10.0, 0.0))],
        constraints=[DistanceConstraint(kind="distance", entity="nope", value_mm=5.0)],
    )
    with pytest.raises(SketchDefinitionError):
        SOLVER.solve(definition)


def test_wrong_point_name_for_entity_kind_raises_definition_error() -> None:
    definition = SketchDefinition(
        entities=[_line("e1", (0.0, 0.0), (10.0, 0.0))],
        constraints=[
            # A line has no "center" point.
            FixedConstraint(kind="fixed", point=_ref("e1", "center")),
        ],
    )
    with pytest.raises(SketchDefinitionError):
        SOLVER.solve(definition)


def test_duplicate_entity_ids_rejected_at_validation() -> None:
    with pytest.raises(ValueError, match="Duplicate sketch entity id"):
        SketchDefinition(
            entities=[
                _line("e1", (0.0, 0.0), (1.0, 0.0)),
                _line("e1", (0.0, 1.0), (1.0, 1.0)),
            ],
            constraints=[],
        )


# ---------------------------------------------------------------------------
# Curve-relating constraints: parallel / perpendicular / tangent (BACKLOG #3a)
# ---------------------------------------------------------------------------


def _line_dir(line: SketchLine) -> tuple[float, float]:
    return (line.end.x - line.start.x, line.end.y - line.start.y)


def _cross(u: tuple[float, float], v: tuple[float, float]) -> float:
    return u[0] * v[1] - u[1] * v[0]


def _dot(u: tuple[float, float], v: tuple[float, float]) -> float:
    return u[0] * v[0] + u[1] * v[1]


def _dist_point_to_line(cx: float, cy: float, line: SketchLine) -> float:
    """Perpendicular distance from ``(cx, cy)`` to the infinite line."""
    (x1, y1), (x2, y2) = (line.start.x, line.start.y), (line.end.x, line.end.y)
    length = math.hypot(x2 - x1, y2 - y1)
    return abs((x2 - x1) * (y1 - cy) - (x1 - cx) * (y2 - y1)) / length


def _solved_line(result_entities: list[SketchEntity], eid: str) -> SketchLine:
    (line,) = [e for e in result_entities if e.id == eid]
    assert isinstance(line, SketchLine)
    return line


def _fixed_horizontal_reference_line() -> tuple[SketchLine, list[SketchConstraint]]:
    """e1 = the fully-pinned horizontal reference (0,0)->(10,0)."""
    e1 = _line("e1", (0.0, 0.0), (10.0, 0.0))
    fixings: list[SketchConstraint] = [
        FixedConstraint(kind="fixed", point=_ref("e1", "start")),
        FixedConstraint(kind="fixed", point=_ref("e1", "end")),
    ]
    return e1, fixings


def test_parallel_lines_solve_to_equal_direction() -> None:
    """A free line made parallel to a fixed horizontal line becomes horizontal
    (cross product of the two direction vectors -> 0), and the constraint
    removes exactly one degree of freedom."""
    e1, fixings = _fixed_horizontal_reference_line()
    # e2 anchored at (0, 5), drawn sloping; parallel(e1, e2) should flatten it.
    e2 = _line("e2", (0.0, 5.0), (8.0, 7.0))
    base_constraints: list[SketchConstraint] = [
        *fixings,
        FixedConstraint(kind="fixed", point=_ref("e2", "start")),
    ]
    base = SketchDefinition(entities=[e1, e2], constraints=base_constraints)
    with_parallel = SketchDefinition(
        entities=[e1, e2],
        constraints=[
            *base_constraints,
            ParallelConstraint(kind="parallel", a="e1", b="e2"),
        ],
    )

    base_result = SOLVER.solve(base)
    result = SOLVER.solve(with_parallel)

    assert result.status in ("converged", "underconstrained")
    assert base_result.dof is not None
    assert result.dof == base_result.dof - 1  # exactly one DOF removed
    solved_e2 = _solved_line(result.entities, "e2")
    d1, d2 = _line_dir(_solved_line(result.entities, "e1")), _line_dir(solved_e2)
    assert _cross(d1, d2) == pytest.approx(0.0, abs=RECTANGLE_TOLERANCE_MM)
    # Parallel to a horizontal reference => e2 is horizontal (end.y == start.y).
    assert solved_e2.end.y == pytest.approx(5.0, abs=RECTANGLE_TOLERANCE_MM)


def test_perpendicular_lines_solve_to_ninety_degrees() -> None:
    """A free line made perpendicular to a fixed horizontal line becomes
    vertical (direction dot product -> 0), removing one degree of freedom."""
    e1, fixings = _fixed_horizontal_reference_line()
    e2 = _line("e2", (0.0, 0.0), (8.0, 2.0))
    base_constraints: list[SketchConstraint] = [
        *fixings,
        FixedConstraint(kind="fixed", point=_ref("e2", "start")),
    ]
    base = SketchDefinition(entities=[e1, e2], constraints=base_constraints)
    with_perp = SketchDefinition(
        entities=[e1, e2],
        constraints=[
            *base_constraints,
            PerpendicularConstraint(kind="perpendicular", a="e1", b="e2"),
        ],
    )

    base_result = SOLVER.solve(base)
    result = SOLVER.solve(with_perp)

    assert result.status in ("converged", "underconstrained")
    assert base_result.dof is not None
    assert result.dof == base_result.dof - 1
    solved_e2 = _solved_line(result.entities, "e2")
    d1, d2 = _line_dir(_solved_line(result.entities, "e1")), _line_dir(solved_e2)
    assert _dot(d1, d2) == pytest.approx(0.0, abs=RECTANGLE_TOLERANCE_MM)
    # Perpendicular to horizontal => vertical: end.x == start.x (== 0).
    assert solved_e2.end.x == pytest.approx(0.0, abs=RECTANGLE_TOLERANCE_MM)


def test_line_arc_tangent_touches_circle_at_one_point() -> None:
    """The worked acceptance case: a horizontal line dropped onto a quarter
    arc of radius 10 by a tangent constraint. At the solution the line grazes
    the arc's circle — the perpendicular distance from the arc center to the
    line equals the radius (single contact point). One DOF removed."""
    # Arc a1: center (0,0), start (10,0), end (0,10) -> radius 10, pinned.
    arc = SketchArc(
        id="a1",
        kind="arc",
        center=Point2D(x=0.0, y=0.0),
        start=Point2D(x=10.0, y=0.0),
        end=Point2D(x=0.0, y=10.0),
    )
    # Line e1 above the arc (guess y=12), horizontal; tangent pulls it to y=10.
    e1 = _line("e1", (-5.0, 12.0), (5.0, 12.0))
    # Fixing center + start pins the arc's circle (center + radius=10); the end
    # is left free on the circle, so no arc-rule redundancy is introduced.
    arc_fixings: list[SketchConstraint] = [
        FixedConstraint(kind="fixed", point=_ref("a1", "center")),
        FixedConstraint(kind="fixed", point=_ref("a1", "start")),
    ]
    base_constraints: list[SketchConstraint] = [
        *arc_fixings,
        HorizontalConstraint(kind="horizontal", entity="e1"),
    ]
    base = SketchDefinition(entities=[arc, e1], constraints=base_constraints)
    with_tangent = SketchDefinition(
        entities=[arc, e1],
        constraints=[
            *base_constraints,
            TangentConstraint(kind="tangent", a="e1", b="a1"),
        ],
    )

    base_result = SOLVER.solve(base)
    result = SOLVER.solve(with_tangent)

    assert result.status in ("converged", "underconstrained")
    assert base_result.dof is not None
    assert result.dof == base_result.dof - 1
    solved_line = _solved_line(result.entities, "e1")
    solved_arc = next(e for e in result.entities if e.id == "a1")
    assert isinstance(solved_arc, SketchArc)
    radius = math.hypot(
        solved_arc.start.x - solved_arc.center.x,
        solved_arc.start.y - solved_arc.center.y,
    )
    distance = _dist_point_to_line(
        solved_arc.center.x, solved_arc.center.y, solved_line
    )
    # The tangency: center-to-line distance == radius (grazes at one point).
    assert distance == pytest.approx(radius, abs=RECTANGLE_TOLERANCE_MM)
    assert distance == pytest.approx(10.0, abs=RECTANGLE_TOLERANCE_MM)
    # Line dropped from y=12 to the near tangent line y=10.
    assert solved_line.start.y == pytest.approx(10.0, abs=RECTANGLE_TOLERANCE_MM)


def test_parallel_and_perpendicular_on_same_pair_conflict() -> None:
    """Asserting a pair of lines is both parallel and perpendicular is
    unsatisfiable: reported as ``conflicting`` with the offending constraint
    indices (same diagnosis path as the distance-vs-fixed conflict)."""
    e1, fixings = _fixed_horizontal_reference_line()
    e2 = _line("e2", (0.0, 5.0), (8.0, 7.0))
    definition = SketchDefinition(
        entities=[e1, e2],
        constraints=[
            *fixings,  # indices 0, 1
            FixedConstraint(kind="fixed", point=_ref("e2", "start")),  # index 2
            # A driving length keeps e2 from collapsing to a point (which would
            # satisfy both direction constraints vacuously); now the pair is
            # genuinely unsatisfiable.
            DistanceConstraint(kind="distance", entity="e2", value_mm=5.0),  # index 3
            ParallelConstraint(kind="parallel", a="e1", b="e2"),  # index 4
            PerpendicularConstraint(kind="perpendicular", a="e1", b="e2"),  # index 5
        ],
    )
    result = SOLVER.solve(definition)
    assert result.status == "conflicting"
    assert result.conflicting_constraints  # non-empty, mapped to caller indices
    # The parallel/perpendicular pair is the impossible combination.
    assert set(result.conflicting_constraints) & {4, 5}
    assert set(result.conflicting_constraints) <= {0, 1, 2, 3, 4, 5}


def test_curve_constraints_solve_deterministically_bitwise() -> None:
    """The new constraint kinds preserve the RESEARCH §9 determinism gate:
    two independent solves of a tangent+perpendicular sketch are bitwise
    identical (== , no tolerance)."""
    arc = SketchArc(
        id="a1",
        kind="arc",
        center=Point2D(x=0.0, y=0.0),
        start=Point2D(x=10.0, y=0.0),
        end=Point2D(x=0.0, y=10.0),
    )
    e1 = _line("e1", (-5.0, 12.0), (5.0, 12.0))
    e2 = _line("e2", (0.0, 0.0), (8.0, 2.0))
    definition = SketchDefinition(
        entities=[arc, e1, e2],
        constraints=[
            FixedConstraint(kind="fixed", point=_ref("a1", "center")),
            FixedConstraint(kind="fixed", point=_ref("a1", "start")),
            FixedConstraint(kind="fixed", point=_ref("a1", "end")),
            HorizontalConstraint(kind="horizontal", entity="e1"),
            TangentConstraint(kind="tangent", a="e1", b="a1"),
            FixedConstraint(kind="fixed", point=_ref("e2", "start")),
            PerpendicularConstraint(kind="perpendicular", a="e1", b="e2"),
        ],
    )
    first = SOLVER.solve(definition)
    second = PlanegcsSketchSolver().solve(definition)

    def flatten(entities: list[SketchEntity]) -> list[tuple[float, ...]]:
        out: list[tuple[float, ...]] = []
        for e in entities:
            if isinstance(e, SketchLine):
                out.append((e.start.x, e.start.y, e.end.x, e.end.y))
            elif isinstance(e, SketchArc):
                out.append(
                    (e.center.x, e.center.y, e.start.x, e.start.y, e.end.x, e.end.y)
                )
        return out

    assert flatten(first.entities) == flatten(second.entities)
    assert first.status == second.status
    assert first.dof == second.dof


def test_tangent_between_two_lines_rejected() -> None:
    """Two lines have no common-tangent relation; the solver rejects the
    definition rather than silently mis-mapping it."""
    definition = SketchDefinition(
        entities=[
            _line("e1", (0.0, 0.0), (10.0, 0.0)),
            _line("e2", (0.0, 1.0), (10.0, 1.0)),
        ],
        constraints=[TangentConstraint(kind="tangent", a="e1", b="e2")],
    )
    with pytest.raises(SketchDefinitionError, match="tangency-capable"):
        SOLVER.solve(definition)


def test_parallel_requires_line_entities() -> None:
    """Parallel between a line and a circle is a definition error (parallel
    relates two lines)."""
    definition = SketchDefinition(
        entities=[
            _line("e1", (0.0, 0.0), (10.0, 0.0)),
            SketchCircle(
                id="c1", kind="circle", center=Point2D(x=0.0, y=5.0), radius=2.0
            ),
        ],
        constraints=[ParallelConstraint(kind="parallel", a="e1", b="c1")],
    )
    with pytest.raises(SketchDefinitionError, match="requires a line"):
        SOLVER.solve(definition)
