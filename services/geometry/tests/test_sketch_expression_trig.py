"""Sketch dimensions speak the shared expression language (PART-PARAMETERS
step 1, closes SKETCH-EXPR-TRIG): trig in degrees, unit suffixes, and the
same typed errors as ``loft_wire.expr``, mapped to ``sketch_invalid``.

``20*tan(15)`` is ``20*(2 - sqrt(3))`` = 5.35898384862245413 mm by hand; the
solver bound is the documented benchmark ``RECTANGLE_TOLERANCE_MM = 1e-9``
(test_sketch_solver rationale).
"""

import math

import pytest
from geometry.sketch import (
    AngleConstraint,
    DistanceConstraint,
    FixedConstraint,
    HorizontalConstraint,
    PlanegcsSketchSolver,
    Point2D,
    SketchConstraint,
    SketchDefinition,
    SketchDefinitionError,
    SketchEntity,
    SketchExpressionError,
    SketchLine,
    VerticalConstraint,
    evaluate_driving_dimensions,
    parse_expression,
)
from geometry.sketch.schemas import CoincidentConstraint, EntityPointRef

RECTANGLE_TOLERANCE_MM = 1e-9
#: 20*tan(15 deg) = 20*(2 - sqrt(3)) = 5.35898384862245413 by hand; this is the
#: nearest double (computing 20*(2.0 - math.sqrt(3.0)) in floats is 2 ulp off).
HAND_HEIGHT_MM = 5.358983848622454
SOLVER = PlanegcsSketchSolver()


def _ref(entity: str, point: str) -> EntityPointRef:
    return EntityPointRef.model_validate({"entity": entity, "point": point})


def _line(eid: str, a: tuple[float, float], b: tuple[float, float]) -> SketchLine:
    return SketchLine(
        id=eid,
        kind="line",
        start=Point2D(x=a[0], y=a[1]),
        end=Point2D(x=b[0], y=b[1]),
    )


def _dist(entity: str, value: float, **kw: object) -> DistanceConstraint:
    return DistanceConstraint.model_validate(
        {"kind": "distance", "entity": entity, "value_mm": value, **kw}
    )


def _rectangle(width: str, height: str) -> SketchDefinition:
    entities: list[SketchEntity] = [
        _line("e1", (0.0, 0.0), (38.0, 1.0)),
        _line("e2", (39.0, 0.5), (41.0, 7.0)),
        _line("e3", (40.5, 6.0), (-1.0, 5.5)),
        _line("e4", (0.5, 4.5), (-0.5, 1.0)),
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
        _dist("e1", 1.0, name="width", expression=width),
        _dist("e2", 1.0, name="height", expression=height),
        FixedConstraint(kind="fixed", point=_ref("e1", "start")),
    ]
    return SketchDefinition(entities=entities, constraints=constraints)


def _length(entities: list[SketchEntity], eid: str) -> float:
    line = next(e for e in entities if e.id == eid)
    assert isinstance(line, SketchLine)
    return math.hypot(line.end.x - line.start.x, line.end.y - line.start.y)


def test_twenty_tan_fifteen_solves_and_round_trips() -> None:
    sketch = _rectangle("1in + 14.6", "20*tan(15)")
    # Save and reload: the stored JSON is the sketch's whole persistent form.
    reloaded = SketchDefinition.model_validate_json(sketch.model_dump_json())
    assert reloaded == sketch

    for definition in (sketch, reloaded):
        result = SOLVER.solve(definition)
        assert result.status == "converged"
        assert result.dof == 0
        assert _length(result.entities, "e1") == pytest.approx(
            40.0, abs=RECTANGLE_TOLERANCE_MM
        )
        assert _length(result.entities, "e2") == pytest.approx(
            HAND_HEIGHT_MM, abs=RECTANGLE_TOLERANCE_MM
        )
        height = next(d for d in result.dimensions if d.name == "height")
        assert height.expression == "20*tan(15)"
        assert height.value_mm == pytest.approx(HAND_HEIGHT_MM, abs=1e-15)

    first, second = SOLVER.solve(sketch), SOLVER.solve(reloaded)
    assert first.model_dump_json() == second.model_dump_json()


def test_height_from_width_by_trig_reference() -> None:
    values = evaluate_driving_dimensions(
        _rectangle("40", "width/2*tan(15 deg)").constraints
    )
    assert values[9] == pytest.approx(HAND_HEIGHT_MM, abs=1e-15)


def test_angle_dimension_from_atan() -> None:
    angle = AngleConstraint(
        kind="angle", a="e1", b="e2", value_deg=1.0, expression="atan2(1 in, 25.4)"
    )
    assert evaluate_driving_dimensions([angle]) == {0: 45.0}


@pytest.mark.parametrize(
    ("height", "match"),
    [
        ("30 deg", "evaluates to an angle"),
        ("tan(90)", "undefined"),
        ("2 mm * 3 mm", "cannot multiply"),
        ("sinh(1)", "unknown function 'sinh'"),
        ("__import__(1)", "unknown function"),
    ],
)
def test_typed_errors_surface_as_sketch_invalid(height: str, match: str) -> None:
    with pytest.raises(SketchExpressionError, match=match):
        SOLVER.solve(_rectangle("10 mm", height))


def test_parse_expression_is_the_shared_grammar() -> None:
    assert parse_expression("20*tan(15)").evaluate(lambda _n: 0.0) == 5.358983848622454
    with pytest.raises(SketchDefinitionError):
        parse_expression("2 mm mm")
