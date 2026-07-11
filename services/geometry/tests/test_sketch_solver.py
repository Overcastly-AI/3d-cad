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

import pytest
from geometry.sketch import (
    CoincidentConstraint,
    DistanceConstraint,
    EntityPointRef,
    FixedConstraint,
    HorizontalConstraint,
    PlanegcsSketchSolver,
    Point2D,
    RadiusConstraint,
    SketchCircle,
    SketchConstraint,
    SketchDefinition,
    SketchDefinitionError,
    SketchEntity,
    SketchLine,
    SketchSolver,
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
