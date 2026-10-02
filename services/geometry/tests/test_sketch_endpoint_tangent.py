"""SKETCH-ENDPOINT-TANGENT: a filleted corner stays tangent through every edit.

The fixture is the sketch the web's fillet leaves on a 40 x 25 rectangle's
top-right corner (``cornerConstraints.ts``): the legs ``e2``/``e3`` trimmed to
the tangent points, the arc ``e2.1`` bridging them, joined by ENDPOINT
tangents, and the radius dimensioned. Before the fix the joins were plain
coincidents, and R5 -> R10 left the centre 9.114 mm from both legs (a kink in
the extrude, with no warning); R5 -> R3 left it 2.076 / 2.834 mm away.
"""

import math
from typing import Any

import pytest
from geometry.sketch import PlanegcsSketchSolver, SketchDefinition, SolvedSketch
from geometry.sketch.schemas import SketchArc, SketchLine, TangentConstraint
from geometry.sketch.solver import SketchDefinitionError
from geometry.sketch.tangency import endpoint_target_rad
from pydantic import ValidationError

TOL = 1e-9


def _p(x: float, y: float) -> dict[str, float]:
    return {"x": x, "y": y}


def _line(
    entity_id: str, a: tuple[float, float], b: tuple[float, float]
) -> dict[str, Any]:
    return {"id": entity_id, "kind": "line", "construction": False,
            "start": _p(*a), "end": _p(*b)}  # fmt: skip


def _co(a: str, ap: str, b: str, bp: str) -> dict[str, Any]:
    return {"kind": "coincident", "a": {"entity": a, "point": ap},
            "b": {"entity": b, "point": bp}}  # fmt: skip


def _tan(a: str, ap: str, b: str, bp: str) -> dict[str, Any]:
    return {"kind": "tangent", "a": a, "b": b, "a_point": ap, "b_point": bp}


def _filleted(
    r: float,
    *,
    extra: tuple[dict[str, Any], ...] = (),
    moved: dict[str, dict[str, Any]] | None = None,
) -> SketchDefinition:
    """The 40 x 25 rectangle after an R5 fillet at (40, 25), radius dimension ``r``."""
    entities = [
        _line("e1", (0, 0), (40, 0)),
        _line("e2", (40, 0), (40, 20)),
        _line("e3", (35, 25), (0, 25)),
        _line("e4", (0, 25), (0, 0)),
        {
            "id": "e2.1",
            "kind": "arc",
            "construction": False,
            "center": _p(35, 20),
            "start": _p(40, 20),
            "end": _p(35, 25),
        },
    ]
    entities = [(moved or {}).get(str(e["id"]), e) for e in entities]
    constraints = [
        _co("e1", "end", "e2", "start"),
        _co("e3", "end", "e4", "start"),
        _co("e4", "end", "e1", "start"),
        {"kind": "horizontal", "entity": "e1"},
        {"kind": "horizontal", "entity": "e3"},
        {"kind": "vertical", "entity": "e2"},
        {"kind": "vertical", "entity": "e4"},
        {"kind": "distance", "entity": "e1", "value_mm": 40},
        _tan("e2", "end", "e2.1", "start"),
        _tan("e3", "start", "e2.1", "end"),
        {"kind": "radius", "entity": "e2.1", "value_mm": r},
        *extra,
    ]
    return SketchDefinition.model_validate(
        {"entities": entities, "constraints": constraints}
    )


def _solve(sketch: SketchDefinition) -> SolvedSketch:
    return PlanegcsSketchSolver().solve(sketch)


def _assert_tangent_round(solved: SolvedSketch, r: float) -> None:
    """The arc meets both legs at their ends, centre r from each, on the inside."""
    by_id = {e.id: e for e in solved.entities}
    arc, e2, e3 = by_id["e2.1"], by_id["e2"], by_id["e3"]
    assert isinstance(arc, SketchArc)
    assert isinstance(e2, SketchLine) and isinstance(e3, SketchLine)
    assert solved.status in ("converged", "underconstrained")
    assert solved.redundant_constraints == []
    assert solved.conflicting_constraints == []
    c = arc.center
    assert math.hypot(arc.start.x - c.x, arc.start.y - c.y) == pytest.approx(r, abs=TOL)
    # Centre-to-leg distance = r: the tangency itself (legs are axis-aligned).
    assert abs(c.x - e2.start.x) == pytest.approx(r, abs=TOL)
    assert abs(c.y - e3.start.y) == pytest.approx(r, abs=TOL)
    # ...on the INSIDE of the corner, so the round is not a cusp.
    assert c.x < e2.start.x and c.y < e3.start.y
    # The joins: each trimmed leg ends exactly on the arc's matching end.
    assert (e2.end.x, e2.end.y) == pytest.approx((arc.start.x, arc.start.y), abs=TOL)
    assert (e3.start.x, e3.start.y) == pytest.approx((arc.end.x, arc.end.y), abs=TOL)


def test_the_fillet_as_drawn_is_clean_with_no_redundancy() -> None:
    solved = _solve(_filleted(5))
    _assert_tangent_round(solved, 5)
    # Each endpoint tangent removes 3 DOF (join 2 + direction 1), where the
    # coincident it replaces removed 2: 5 free before, 3 now.
    assert solved.dof == 3


@pytest.mark.parametrize("r", [10.0, 3.0])
def test_editing_r_keeps_the_arc_tangent(r: float) -> None:
    _assert_tangent_round(_solve(_filleted(r)), r)


def test_dragging_a_leg_end_keeps_the_arc_tangent() -> None:
    """The trimmed leg's end dragged down the leg: the arc follows, still tangent."""
    dragged = _line("e2", (40, 0), (40, 14))
    _assert_tangent_round(_solve(_filleted(5, moved={"e2": dragged})), 5)


def test_dragging_the_side_out_keeps_the_arc_tangent() -> None:
    """The far corner of the right side dragged outwards, off the legs' lines."""
    dragged = _line("e2", (52, -3), (40, 20))
    _assert_tangent_round(_solve(_filleted(5, moved={"e2": dragged})), 5)


def test_r_edit_with_the_height_dimensioned_shortens_the_legs() -> None:
    """Fully pinned outline: R10 must come out of the legs, not the outline."""
    extra = (
        {"kind": "distance", "entity": "e4", "value_mm": 25},
        {"kind": "fixed", "point": {"entity": "e1", "point": "start"}},
    )
    solved = _solve(_filleted(10, extra=extra))
    _assert_tangent_round(solved, 10)
    by_id = {e.id: e for e in solved.entities}
    arc = by_id["e2.1"]
    assert isinstance(arc, SketchArc)
    assert (arc.center.x, arc.center.y) == pytest.approx((30, 15), abs=TOL)
    assert solved.dof == 0 and solved.status == "converged"


def test_a_leg_drawn_away_from_the_arc_keeps_its_branch() -> None:
    """A leg authored END -> START into the arc is held on the pi branch.

    The tangent directions follow each curve's own parameterisation, so the
    target angle is 0 or pi depending on which ends meet: two ``start`` ends
    here, so pi, read from the names (``endpoint_target_rad``).
    """
    reversed_e2 = _line("e2", (40, 20), (40, 0))
    sketch = _filleted(10, moved={"e2": reversed_e2})
    data = sketch.model_dump()
    data["constraints"][0] = _co("e1", "end", "e2", "end")
    data["constraints"][8] = _tan("e2", "start", "e2.1", "start")
    solved = _solve(SketchDefinition.model_validate(data))
    by_id = {e.id: e for e in solved.entities}
    arc = by_id["e2.1"]
    assert isinstance(arc, SketchArc)
    assert solved.redundant_constraints == []
    assert 40 - arc.center.x == pytest.approx(10, abs=TOL)


def test_a_coincident_on_the_same_join_is_reported_redundant() -> None:
    """The endpoint tangent IS the coincidence; authoring both says it twice."""
    solved = _solve(_filleted(5, extra=(_co("e2", "end", "e2.1", "start"),)))
    assert solved.redundant_constraints != [] or solved.conflicting_constraints != []


def test_the_solve_is_deterministic() -> None:
    first = _solve(_filleted(10)).model_dump_json()
    assert all(_solve(_filleted(10)).model_dump_json() == first for _ in range(3))


def test_one_end_named_without_the_other_is_refused_at_the_boundary() -> None:
    with pytest.raises(ValidationError, match="BOTH curves"):
        TangentConstraint.model_validate(
            {"kind": "tangent", "a": "e1", "b": "e2", "a_point": "end"}
        )


def test_an_endpoint_tangent_on_a_circle_or_two_lines_is_malformed() -> None:
    circle = {"id": "c1", "kind": "circle", "construction": False,
              "center": _p(0, 0), "radius": 5}  # fmt: skip
    for b, entity in (("c1", circle), ("l2", _line("l2", (5, 0), (5, 9)))):
        sketch = SketchDefinition.model_validate(
            {
                "entities": [_line("l1", (5, -9), (5, 0)), entity],
                "constraints": [_tan("l1", "end", b, "start")],
            }
        )
        with pytest.raises(SketchDefinitionError):
            _solve(sketch)


def test_the_whole_curve_tangent_is_unchanged_on_the_wire() -> None:
    """A stored ``tangent`` with no ends parses with both unset — the old form."""
    stored = TangentConstraint.model_validate({"kind": "tangent", "a": "l", "b": "a"})
    assert stored.a_point is None and stored.b_point is None


# -- the branch is read from the end NAMES, never the coordinates (review) ----


@pytest.mark.parametrize(
    ("a_point", "b_point", "target"),
    [
        ("end", "start", 0.0),
        ("start", "end", 0.0),
        ("start", "start", math.pi),
        ("end", "end", math.pi),
    ],
)
def test_the_target_is_symbolic(a_point: str, b_point: str, target: float) -> None:
    constraint = TangentConstraint.model_validate(_tan("l", a_point, "a", b_point))
    assert endpoint_target_rad(constraint) == target


def test_a_leg_dragged_through_straight_does_not_hold_a_cusp() -> None:
    """Review case 1: ``e2`` submitted pointing DOWN into the arc (its start
    above its end) read as the pi branch from coordinates and solved with the
    centre at (45, 20), 5 mm OUTSIDE the rectangle. ``end``/``start`` is 0."""
    dragged = _line("e2", (40, 40), (40, 20))
    _assert_tangent_round(_solve(_filleted(5, moved={"e2": dragged})), 5)


def test_an_arc_dragged_outside_its_corner_comes_back_inside() -> None:
    """Review case 2: the arc dragged to the outside, centre (45, 20)."""
    outside = {
        "id": "e2.1",
        "kind": "arc",
        "construction": False,
        "center": _p(45, 20),
        "start": _p(40, 20),
        "end": _p(45, 25),
    }
    _assert_tangent_round(_solve(_filleted(5, moved={"e2.1": outside})), 5)


def test_a_corner_that_can_only_be_a_cusp_is_reported_not_shipped() -> None:
    """The arc's centre pinned on the far side of the leg: the only way to meet
    it is folded back. The solve says conflicting and names the tangent."""
    sketch = SketchDefinition.model_validate(
        {
            "entities": [
                _line("l", (0, 0), (10, 0)),
                {
                    "id": "a",
                    "kind": "arc",
                    "construction": False,
                    "center": _p(10, -5),
                    "start": _p(10, 0),
                    "end": _p(15, -5),
                },
            ],
            "constraints": [
                {"kind": "fixed", "point": {"entity": "l", "point": "start"}},
                {"kind": "distance", "entity": "l", "value_mm": 10},
                {"kind": "fixed", "point": {"entity": "a", "point": "center"}},
                {"kind": "radius", "entity": "a", "value_mm": 5},
                _tan("l", "end", "a", "start"),
            ],
        }
    )
    solved = _solve(sketch)
    assert solved.status == "conflicting"
    assert 4 in solved.conflicting_constraints
