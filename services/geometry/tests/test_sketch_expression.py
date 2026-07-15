"""Sketch dimension-expression parser + evaluator, and driving/driven wiring.

Covers the safe recursive-descent evaluator (:mod:`geometry.sketch.expression`)
and its integration with the planegcs solver: a dimension's value can be a
literal, a reference to another dimension by name, or a math expression over
them; a ``driving`` dimension feeds the solver, a ``driven`` one is excluded
and its value is measured back from the solved geometry.

Determinism/tolerance: the parser is exact (bitwise ``==`` on arithmetic); the
solver assertions reuse the documented benchmark bound ``RECTANGLE_TOLERANCE_MM
= 1e-9`` (test_sketch_solver rationale) — never an ad-hoc epsilon.
"""

import math

import pytest
from geometry.sketch import (
    DistanceConstraint,
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
    SketchExpressionError,
    SketchLine,
    SketchSolver,
    VerticalConstraint,
    evaluate_driving_dimensions,
    measure_dimension,
    parse_expression,
)
from geometry.sketch.schemas import CoincidentConstraint, EntityPointRef

RECTANGLE_TOLERANCE_MM = 1e-9
SOLVER: SketchSolver = PlanegcsSketchSolver()


# ---------------------------------------------------------------------------
# Parser / arithmetic
# ---------------------------------------------------------------------------


def _eval(text: str) -> float:
    """Evaluate a name-free expression (any identifier resolves to NaN)."""
    return parse_expression(text).evaluate(lambda _name: math.nan)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("42", 42.0),
        ("3.5", 3.5),
        (".5", 0.5),
        ("2+3", 5.0),
        ("2+3*4", 14.0),  # precedence: * binds tighter than +
        ("(2+3)*4", 20.0),  # parens override precedence
        ("10-2-3", 5.0),  # left-associative subtraction
        ("20/4/5", 1.0),  # left-associative division
        ("-5", -5.0),  # unary minus
        ("-(2+3)*2", -10.0),
        ("--5", 5.0),  # double unary minus
        ("+7", 7.0),  # unary plus
        ("  2  *  ( 3 + 4 ) ", 14.0),  # whitespace insensitivity
        ("2*3+4*5", 26.0),
    ],
)
def test_parser_arithmetic(text: str, expected: float) -> None:
    assert _eval(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "   ", "2+", "2 3", "(2+3", "2+3)", "*2", "2**3", "2 % 3", "$", "2.3.4"],
)
def test_parser_rejects_malformed(text: str) -> None:
    with pytest.raises(SketchExpressionError):
        parse_expression(text).evaluate(lambda _n: 0.0)


def test_division_by_zero_is_a_clean_error() -> None:
    with pytest.raises(SketchExpressionError, match="division by zero"):
        parse_expression("1/0").evaluate(lambda _n: 0.0)

    with pytest.raises(SketchExpressionError, match="division by zero"):
        parse_expression("1/(2-2)").evaluate(lambda _n: 0.0)


def test_references_are_reported_for_the_dependency_graph() -> None:
    node = parse_expression("width/2 + margin*3")
    assert node.references() == {"width", "margin"}


# ---------------------------------------------------------------------------
# Dimension evaluation: references, cycles, unknown/driven refs
# ---------------------------------------------------------------------------


def _dist(entity: str, value: float, **kw: object) -> DistanceConstraint:
    return DistanceConstraint.model_validate(
        {"kind": "distance", "entity": entity, "value_mm": value, **kw}
    )


def test_reference_resolution_width_half() -> None:
    """``width=20``, ``height="width/2"`` → height evaluates to 10."""
    values = evaluate_driving_dimensions(
        [
            _dist("e1", 20.0, name="width"),
            _dist("e2", 1.0, name="height", expression="width/2"),
        ]
    )
    assert values == {0: 20.0, 1: 10.0}


def test_transitive_reference_chain() -> None:
    values = evaluate_driving_dimensions(
        [
            _dist("e1", 100.0, name="a"),
            _dist("e2", 1.0, name="b", expression="a/2"),  # 50
            _dist("e3", 1.0, name="c", expression="b + a/10"),  # 60
        ]
    )
    assert values == {0: 100.0, 1: 50.0, 2: 60.0}


def test_unknown_reference_is_clean_error() -> None:
    with pytest.raises(SketchExpressionError, match="unknown dimension name 'nope'"):
        evaluate_driving_dimensions([_dist("e1", 1.0, name="a", expression="nope*2")])


def test_direct_cycle_is_detected() -> None:
    with pytest.raises(SketchExpressionError, match="cycle"):
        evaluate_driving_dimensions(
            [
                _dist("e1", 1.0, name="a", expression="b"),
                _dist("e2", 1.0, name="b", expression="a"),
            ]
        )


def test_self_reference_is_a_cycle() -> None:
    with pytest.raises(SketchExpressionError, match="cycle"):
        evaluate_driving_dimensions([_dist("e1", 1.0, name="a", expression="a+1")])


def test_longer_cycle_is_detected() -> None:
    with pytest.raises(SketchExpressionError, match="cycle"):
        evaluate_driving_dimensions(
            [
                _dist("e1", 1.0, name="a", expression="b"),
                _dist("e2", 1.0, name="b", expression="c"),
                _dist("e3", 1.0, name="c", expression="a"),
            ]
        )


def test_expression_evaluating_non_positive_is_rejected() -> None:
    with pytest.raises(SketchExpressionError, match="must be > 0"):
        evaluate_driving_dimensions(
            [
                _dist("e1", 10.0, name="w"),
                _dist("e2", 1.0, name="h", expression="w - 10"),  # 0
            ]
        )


def test_referencing_a_driven_dimension_is_rejected() -> None:
    """A driven value is only known after the solve, so it cannot drive one."""
    with pytest.raises(SketchExpressionError, match="driven dimension 'meas'"):
        evaluate_driving_dimensions(
            [
                _dist("e1", 10.0, name="meas", driving=False),
                _dist("e2", 1.0, name="w", expression="meas*2"),
            ]
        )


def test_driven_dimensions_are_absent_from_the_driving_map() -> None:
    values = evaluate_driving_dimensions(
        [
            _dist("e1", 20.0, name="width"),  # index 0, driving
            _dist("e2", 5.0, name="depth", driving=False),  # index 1, driven
        ]
    )
    assert values == {0: 20.0}  # driven dim excluded


def test_literal_only_dimensions_pass_value_through() -> None:
    values = evaluate_driving_dimensions([_dist("e1", 40.0), _dist("e2", 25.0)])
    assert values == {0: 40.0, 1: 25.0}


# ---------------------------------------------------------------------------
# Measurement of driven dimensions
# ---------------------------------------------------------------------------


def test_measure_distance_from_geometry() -> None:
    line = SketchLine(
        id="e1", kind="line", start=Point2D(x=0.0, y=0.0), end=Point2D(x=3.0, y=4.0)
    )
    measured = measure_dimension(_dist("e1", 1.0, driving=False), {"e1": line})
    assert measured == pytest.approx(5.0)  # 3-4-5


def test_measure_radius_from_geometry() -> None:
    circle = SketchCircle(
        id="e1", kind="circle", center=Point2D(x=0.0, y=0.0), radius=7.5
    )
    dim = RadiusConstraint.model_validate(
        {"kind": "radius", "entity": "e1", "value_mm": 1.0, "driving": False}
    )
    assert measure_dimension(dim, {"e1": circle}) == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# Solver integration
# ---------------------------------------------------------------------------


def _ref(entity: str, point: str) -> EntityPointRef:
    return EntityPointRef.model_validate({"entity": entity, "point": point})


def _rectangle(
    *, width_dim: SketchConstraint, height_dim: SketchConstraint
) -> SketchDefinition:
    """A 40x25-ish rectangle anchored at origin, dimensioned by the two dims."""
    entities: list[SketchEntity] = [
        SketchLine(
            id="e1",
            kind="line",
            start=Point2D(x=0.0, y=0.0),
            end=Point2D(x=38.0, y=1.0),
        ),
        SketchLine(
            id="e2",
            kind="line",
            start=Point2D(x=39.0, y=0.5),
            end=Point2D(x=41.0, y=24.0),
        ),
        SketchLine(
            id="e3",
            kind="line",
            start=Point2D(x=40.5, y=26.0),
            end=Point2D(x=-1.0, y=25.5),
        ),
        SketchLine(
            id="e4",
            kind="line",
            start=Point2D(x=0.5, y=24.5),
            end=Point2D(x=-0.5, y=1.0),
        ),
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
            kind="coincident", a=_ref("e4", "end"), b=_ref("e1", "start")
        ),
        HorizontalConstraint(kind="horizontal", entity="e1"),
        VerticalConstraint(kind="vertical", entity="e2"),
        HorizontalConstraint(kind="horizontal", entity="e3"),
        VerticalConstraint(kind="vertical", entity="e4"),
        width_dim,
        height_dim,
        FixedConstraint(kind="fixed", point=_ref("e1", "start")),
    ]
    return SketchDefinition(entities=entities, constraints=constraints)


def _line(entities: list[SketchEntity], eid: str) -> SketchLine:
    entity = next(e for e in entities if e.id == eid)
    assert isinstance(entity, SketchLine)
    return entity


def _length(line: SketchLine) -> float:
    return math.hypot(line.end.x - line.start.x, line.end.y - line.start.y)


def test_expression_dimension_solves_width_half() -> None:
    """The worked acceptance: width=20, height="width/2" → the rectangle solves
    fully constrained with a width-20 base and a height-10 side."""
    sketch = _rectangle(
        width_dim=_dist("e1", 20.0, name="width"),
        height_dim=_dist("e2", 1.0, name="height", expression="width/2"),
    )
    result = SOLVER.solve(sketch)

    assert result.status == "converged"
    assert result.dof == 0
    assert _length(_line(result.entities, "e1")) == pytest.approx(
        20.0, abs=RECTANGLE_TOLERANCE_MM
    )
    assert _length(_line(result.entities, "e2")) == pytest.approx(
        10.0, abs=RECTANGLE_TOLERANCE_MM
    )

    # The solved payload reports the evaluated value for the expression dim.
    height_readout = next(d for d in result.dimensions if d.name == "height")
    assert height_readout.driving is True
    assert height_readout.expression == "width/2"
    assert height_readout.value_mm == pytest.approx(10.0, abs=RECTANGLE_TOLERANCE_MM)


def test_driven_dimension_does_not_over_constrain() -> None:
    """A driven dimension is excluded from the solver, so it neither
    over-constrains nor pins geometry; its readout is measured from the solve."""
    driving = _rectangle(
        width_dim=_dist("e1", 20.0, name="width"),
        height_dim=_dist("e2", 25.0, name="height"),
    )
    driven = _rectangle(
        width_dim=_dist("e1", 20.0, name="width"),
        height_dim=_dist("e2", 999.0, name="height", driving=False),  # stale value
    )

    driving_result = SOLVER.solve(driving)
    driven_result = SOLVER.solve(driven)

    # Driving both dims → fully constrained.
    assert driving_result.status == "converged"
    assert driving_result.dof == 0
    # Marking height driven removes a constraint → a DOF remains (the height is
    # free), NOT an over-constraint / conflict.
    assert driven_result.status == "underconstrained"
    assert driven_result.dof is not None and driven_result.dof > 0
    assert driven_result.conflicting_constraints == []
    assert driven_result.redundant_constraints == []

    # The driven readout is MEASURED from the solved geometry (the input-guess
    # height ≈ 25), never the stale 999 that was stored on the constraint.
    height_readout = next(d for d in driven_result.dimensions if d.name == "height")
    assert height_readout.driving is False
    assert height_readout.value_mm != pytest.approx(999.0)
    assert height_readout.value_mm == pytest.approx(
        _length(_line(driven_result.entities, "e2")), abs=RECTANGLE_TOLERANCE_MM
    )


def test_driven_readout_tracks_edited_geometry() -> None:
    """Editing the geometry the driven dimension measures updates the readout."""

    def solve_with_end(end_x: float) -> float:
        line = SketchLine(
            id="e1",
            kind="line",
            start=Point2D(x=0.0, y=0.0),
            end=Point2D(x=end_x, y=0.0),
        )
        sketch = SketchDefinition(
            entities=[line],
            constraints=[
                FixedConstraint(kind="fixed", point=_ref("e1", "start")),
                HorizontalConstraint(kind="horizontal", entity="e1"),
                _dist("e1", 5.0, name="len", driving=False),  # stale stored value
            ],
        )
        result = SOLVER.solve(sketch)
        (readout,) = result.dimensions
        return readout.value_mm

    assert solve_with_end(10.0) == pytest.approx(10.0, abs=RECTANGLE_TOLERANCE_MM)
    assert solve_with_end(7.0) == pytest.approx(7.0, abs=RECTANGLE_TOLERANCE_MM)


def test_expression_error_surfaces_through_solve() -> None:
    """A cycle in the sketch's dimensions raises through solve() as a
    SketchDefinitionError (→ sketch_invalid), never a hang or a 500."""
    sketch = _rectangle(
        width_dim=_dist("e1", 1.0, name="width", expression="height"),
        height_dim=_dist("e2", 1.0, name="height", expression="width"),
    )
    with pytest.raises(SketchDefinitionError, match="cycle"):
        SOLVER.solve(sketch)


def test_expression_dimension_is_bitwise_deterministic() -> None:
    sketch = _rectangle(
        width_dim=_dist("e1", 20.0, name="width"),
        height_dim=_dist("e2", 1.0, name="height", expression="width/2"),
    )
    first = SOLVER.solve(sketch)
    second = PlanegcsSketchSolver().solve(sketch)
    assert [(e.id, _length(_line(first.entities, e.id))) for e in first.entities] == [
        (e.id, _length(_line(second.entities, e.id))) for e in second.entities
    ]
    assert [d.value_mm for d in first.dimensions] == [
        d.value_mm for d in second.dimensions
    ]


def test_literal_rectangle_unchanged_backward_compat() -> None:
    """A literal-only sketch solves exactly as before AND now reports readouts."""
    sketch = _rectangle(
        width_dim=_dist("e1", 40.0),
        height_dim=_dist("e2", 25.0),
    )
    result = SOLVER.solve(sketch)
    assert result.status == "converged"
    assert result.dof == 0
    assert _length(_line(result.entities, "e1")) == pytest.approx(
        40.0, abs=RECTANGLE_TOLERANCE_MM
    )
    assert _length(_line(result.entities, "e2")) == pytest.approx(
        25.0, abs=RECTANGLE_TOLERANCE_MM
    )
    # Both literal dims report driving readouts equal to their literals.
    assert sorted(d.value_mm for d in result.dimensions) == pytest.approx([25.0, 40.0])
    assert all(d.driving for d in result.dimensions)
    assert all(d.expression is None for d in result.dimensions)


def test_duplicate_dimension_name_is_rejected_at_schema() -> None:
    with pytest.raises(ValueError, match="Duplicate sketch dimension name"):
        SketchDefinition(
            entities=[
                SketchLine(
                    id="e1",
                    kind="line",
                    start=Point2D(x=0.0, y=0.0),
                    end=Point2D(x=1.0, y=0.0),
                )
            ],
            constraints=[
                _dist("e1", 10.0, name="w"),
                _dist("e1", 20.0, name="w"),
            ],
        )
