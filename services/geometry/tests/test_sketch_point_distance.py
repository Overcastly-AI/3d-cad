"""SKETCH-POINT-DISTANCE: point-to-point and point-to-line distance dimensions.

The QA case is a lip inset 1 mm from a rim. Fusion 360's Sketch Dimension on a
point and a line gives the perpendicular distance; on two points it gives the
aligned distance, or the horizontal or vertical one. These tests hold the
solver to that, and to the property the native constraint does not have on its
own: a value edit never carries the point across the line.
"""

import math
from collections.abc import Callable
from typing import Any

import pytest
from geometry.sketch import PlanegcsSketchSolver, SketchDefinition, SolvedSketch
from geometry.sketch.schemas import SketchEntity, SketchLine, SketchPoint
from geometry.sketch.solver import SketchDefinitionError
from planegcs import Sketch as GcsSystem
from planegcs import SolveStatus

TOL = 1e-9
W, H = 120.0, 80.0


def _p(x: float, y: float) -> dict[str, float]:
    return {"x": x, "y": y}


def _line(i: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    return {"id": i, "kind": "line", "start": _p(*a), "end": _p(*b)}


def _point(i: str, x: float, y: float) -> dict[str, Any]:
    return {"id": i, "kind": "point", "position": _p(x, y)}


def _ref(entity: str, point: str, sharp: str | None = None) -> dict[str, str]:
    return {"entity": entity, "point": point, **({"sharp": sharp} if sharp else {})}


def _join(a: str, ap: str, b: str, bp: str) -> dict[str, Any]:
    return {"kind": "coincident", "a": _ref(a, ap), "b": _ref(b, bp)}


def _rect(
    prefix: str, x0: float, y0: float, x1: float, y1: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A closed rectangle b, r, t, l (CCW), with its corners joined and H/V."""
    b, r, t, left = (f"{prefix}{side}" for side in "brtl")
    entities = [
        _line(b, (x0, y0), (x1, y0)),
        _line(r, (x1, y0), (x1, y1)),
        _line(t, (x1, y1), (x0, y1)),
        _line(left, (x0, y1), (x0, y0)),
    ]
    constraints = [
        _join(b, "end", r, "start"),
        _join(r, "end", t, "start"),
        _join(t, "end", left, "start"),
        _join(left, "end", b, "start"),
        {"kind": "horizontal", "entity": b},
        {"kind": "horizontal", "entity": t},
        {"kind": "vertical", "entity": r},
        {"kind": "vertical", "entity": left},
    ]
    return entities, constraints


def _inset(
    width: float = W, inset: float = 1.0, *, extra: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """The QA lip: a 20 x 10 pocket held ``inset`` from the rim's right and top.

    Geometry is ALWAYS the one drawn at 120 x 80 with a 1 mm inset; ``width``
    and ``inset`` are only the typed values, exactly what the web submits
    after a dimension edit.
    """
    outer, outer_c = _rect("o", 0, 0, W, H)
    inner, inner_c = _rect("i", W - 21, H - 11, W - 1, H - 1)
    constraints = [
        *outer_c,
        {"kind": "fixed", "point": _ref("ob", "start")},
        {"kind": "distance", "entity": "ob", "value_mm": width},
        {"kind": "distance", "entity": "or", "value_mm": H},
        *inner_c,
        {"kind": "distance", "entity": "ib", "value_mm": 20},
        {"kind": "distance", "entity": "ir", "value_mm": 10},
        {
            "kind": "point_line_distance",
            "point": _ref("ir", "end"),
            "line": "or",
            "value_mm": inset,
        },
        {
            "kind": "point_line_distance",
            "point": _ref("ir", "end"),
            "line": "ot",
            "value_mm": inset,
        },
        *(extra or []),
    ]
    return {"entities": [*outer, *inner], "constraints": constraints}


def _solve(raw: dict[str, Any]) -> SolvedSketch:
    return PlanegcsSketchSolver().solve(SketchDefinition.model_validate(raw))


def _by_id(solved: SolvedSketch) -> dict[str, SketchEntity]:
    return {entity.id: entity for entity in solved.entities}


def _line_of(solved: SolvedSketch, entity: str) -> SketchLine:
    line = _by_id(solved)[entity]
    assert isinstance(line, SketchLine)
    return line


def _adopt(raw: dict[str, Any], solved: SolvedSketch) -> dict[str, Any]:
    """What the web stores after a solve: the solved geometry, same constraints."""
    return {
        "entities": [e.model_dump(mode="json") for e in solved.entities],
        "constraints": raw["constraints"],
    }


# -- point to line ---------------------------------------------------------------


def test_the_inset_is_fully_defined_and_holds_its_value() -> None:
    solved = _solve(_inset())
    assert solved.status == "converged"
    assert solved.dof == 0
    corner = _line_of(solved, "ir").end
    assert (corner.x, corner.y) == pytest.approx((W - 1, H - 1), abs=TOL)
    readout = {d.constraint_index: d.value_mm for d in solved.dimensions}
    assert readout[21] == pytest.approx(1.0, abs=TOL)
    assert readout[22] == pytest.approx(1.0, abs=TOL)


@pytest.mark.parametrize("width", [130.0, 100.0, 60.0])
def test_editing_the_rim_carries_the_lip_and_never_flips_it(width: float) -> None:
    """The backlog's case. 100 and 60 move the rim's right edge PAST the lip's
    corner (drawn at x = 119), which is where an unsigned distance lets the
    corner settle 1 mm OUTSIDE the rim (see the native-constraint test below)."""
    solved = _solve(_inset(width))
    assert solved.status == "converged"
    corner = _line_of(solved, "ir").end
    rim = _line_of(solved, "or")
    assert rim.start.x == pytest.approx(width, abs=TOL)
    assert (corner.x, corner.y) == pytest.approx((width - 1, H - 1), abs=TOL)


def test_planegcs_alone_would_put_the_lip_outside_the_rim() -> None:
    """Why the side is held: the native P2LDistance is unsigned.

    The rim's edge is moved to x = 100 and the lip's corner, drawn at x = 119,
    is asked to be 1 mm from it. planegcs's own constraint is satisfied at 101,
    and DogLeg walks there. The signed encoding is what makes 99 the answer.
    """
    gcs = GcsSystem()
    edge = gcs.add_line(gcs.add_fixed_point(100, 0), gcs.add_fixed_point(100, 80))
    corner = gcs.add_point(119, 79)
    gcs.set_p2l_distance(corner, edge, 1.0)
    assert gcs.solve() in (SolveStatus.Success, SolveStatus.Converged)
    assert gcs.get_point(corner)[0] == pytest.approx(101.0, abs=1e-6)


def test_value_edits_up_and_down_keep_the_side() -> None:
    """Each edit is solved from the previous solve's own geometry, as stored."""
    previous = _solve(_inset())
    for inset in (3.0, 0.5, 12.0, 0.25, 1.0, 40.0, 1.0):
        solved = _solve(_adopt(_inset(inset=inset), previous))
        assert solved.status == "converged", inset
        corner = _line_of(solved, "ir").end
        assert (corner.x, corner.y) == pytest.approx((W - inset, H - inset), abs=TOL)
        previous = solved


def test_a_free_point_keeps_its_side_of_a_free_line() -> None:
    """Below a slanted line, with the line free: the point stays below it."""
    raw = {
        "entities": [_line("l", (0, 0), (40, 10)), _point("p", 20, -3)],
        "constraints": [
            {
                "kind": "point_line_distance",
                "point": _ref("p", "position"),
                "line": "l",
                "value_mm": 6.0,
            }
        ],
    }
    for value in (6.0, 0.5, 25.0, 2.0):
        raw["constraints"][0]["value_mm"] = value
        solved = _solve(raw)
        line, point = _line_of(solved, "l"), _by_id(solved)["p"]
        assert isinstance(point, SketchPoint)
        dx, dy = line.end.x - line.start.x, line.end.y - line.start.y
        signed = (
            dx * (point.position.y - line.start.y)
            - dy * (point.position.x - line.start.x)
        ) / math.hypot(dx, dy)
        assert signed == pytest.approx(-value, abs=TOL)
        assert solved.dof == 4 + 2 - 1
        raw = _adopt(raw, solved)


def test_a_point_drawn_on_the_line_still_solves() -> None:
    """No side to read: +1 (left), and the auxiliary foot is not degenerate."""
    raw = {
        "entities": [_line("l", (0, 0), (40, 0)), _point("p", 15, 0)],
        "constraints": [
            {"kind": "fixed", "point": _ref("l", "start")},
            {"kind": "fixed", "point": _ref("l", "end")},
            {
                "kind": "point_line_distance",
                "point": _ref("p", "position"),
                "line": "l",
                "value_mm": 2.0,
            },
        ],
    }
    solved = _solve(raw)
    point = _by_id(solved)["p"]
    assert isinstance(point, SketchPoint)
    assert (point.position.x, point.position.y) == pytest.approx((15, 2), abs=TOL)
    assert solved.dof == 1


def test_two_parallel_lines_are_dimensioned_from_an_end() -> None:
    """Fusion's parallel-line distance, as one end of b to the line a."""
    raw = {
        "entities": [_line("a", (0, 0), (40, 0)), _line("b", (5, 9), (30, 9))],
        "constraints": [
            {"kind": "fixed", "point": _ref("a", "start")},
            {"kind": "horizontal", "entity": "a"},
            {"kind": "parallel", "a": "a", "b": "b"},
            {
                "kind": "point_line_distance",
                "point": _ref("b", "start"),
                "line": "a",
                "value_mm": 4.0,
            },
        ],
    }
    solved = _solve(raw)
    b = _line_of(solved, "b")
    assert (b.start.y, b.end.y) == pytest.approx((4.0, 4.0), abs=TOL)
    # a: 1 (its length); b: 4 - parallel - distance = 2.
    assert solved.dof == 3


# -- redundancy -------------------------------------------------------------------


def test_a_second_inset_on_the_same_edge_is_redundant() -> None:
    """The lip's lower corner is already 1 mm from the rim (``ir`` is vertical)."""
    extra = {
        "kind": "point_line_distance",
        "point": _ref("ir", "start"),
        "line": "or",
        "value_mm": 1.0,
    }
    solved = _solve(_inset(extra=[extra]))
    assert solved.status == "overconstrained"
    assert solved.redundant_constraints != []
    assert solved.conflicting_constraints == []
    assert _line_of(solved, "ir").end.x == pytest.approx(W - 1, abs=TOL)


def test_a_contradicting_inset_is_a_conflict() -> None:
    extra = {
        "kind": "point_line_distance",
        "point": _ref("ir", "start"),
        "line": "or",
        "value_mm": 2.0,
    }
    solved = _solve(_inset(extra=[extra]))
    assert solved.status == "conflicting"
    assert 23 in solved.conflicting_constraints


# -- point to point -----------------------------------------------------------------


def _pair(direction: str, value: float, at: tuple[float, float]) -> dict[str, Any]:
    return {
        "entities": [_point("o", 0, 0), _point("p", *at)],
        "constraints": [
            {"kind": "fixed", "point": _ref("o", "position")},
            {
                "kind": "point_distance",
                "a": _ref("o", "position"),
                "b": _ref("p", "position"),
                "direction": direction,
                "value_mm": value,
            },
        ],
    }


@pytest.mark.parametrize("direction", ["aligned", "horizontal", "vertical"])
def test_each_direction_removes_one_dof(direction: str) -> None:
    solved = _solve(_pair(direction, 5.0, (-8.0, -6.0)))
    assert solved.status == "underconstrained"
    assert solved.dof == 1


def _aligned(x: float, y: float) -> float:
    return math.hypot(x, y)


def _leftward(x: float, y: float) -> float:
    return -x


def _downward(x: float, y: float) -> float:
    return -y


@pytest.mark.parametrize(
    ("direction", "measure"),
    [("aligned", _aligned), ("horizontal", _leftward), ("vertical", _downward)],
)
def test_point_distance_edits_up_and_down_keep_the_side(
    direction: str, measure: Callable[[float, float], float]
) -> None:
    """``p`` is drawn left of and below the origin, and stays there."""
    at = (-8.0, -6.0)
    for value in (5.0, 0.5, 30.0, 2.0, 10.0):
        solved = _solve(_pair(direction, value, at))
        point = _by_id(solved)["p"]
        assert isinstance(point, SketchPoint)
        x, y = point.position.x, point.position.y
        assert measure(x, y) == pytest.approx(value, abs=TOL), (direction, value)
        assert solved.dimensions[0].value_mm == pytest.approx(value, abs=TOL)
        at = (x, y)


def test_horizontal_and_vertical_fully_place_a_point() -> None:
    raw = _pair("horizontal", 12.0, (9.0, 4.0))
    raw["constraints"].append(
        {
            "kind": "point_distance",
            "a": _ref("o", "position"),
            "b": _ref("p", "position"),
            "direction": "vertical",
            "value_mm": 7.0,
        }
    )
    solved = _solve(raw)
    assert solved.status == "converged"
    point = _by_id(solved)["p"]
    assert isinstance(point, SketchPoint)
    assert (point.position.x, point.position.y) == pytest.approx((12, 7), abs=TOL)


def test_an_aligned_distance_with_both_components_is_redundant_or_conflicting() -> None:
    raw = _pair("horizontal", 3.0, (3.0, 4.0))
    raw["constraints"] += [
        {
            "kind": "point_distance",
            "a": _ref("o", "position"),
            "b": _ref("p", "position"),
            "direction": "vertical",
            "value_mm": 4.0,
        },
        {
            "kind": "point_distance",
            "a": _ref("o", "position"),
            "b": _ref("p", "position"),
            "value_mm": 5.0,
        },
    ]
    assert _solve(raw).status == "overconstrained"
    raw["constraints"][-1]["value_mm"] = 6.0
    assert _solve(raw).status == "conflicting"


def test_a_driven_point_dimension_reads_the_geometry() -> None:
    raw = _pair("vertical", 1.0, (9.0, -4.5))
    raw["constraints"][1]["driving"] = False
    solved = _solve(raw)
    assert solved.dof == 2
    assert solved.dimensions[0].driving is False
    assert solved.dimensions[0].value_mm == pytest.approx(4.5, abs=TOL)


# -- virtual sharps -------------------------------------------------------------------


def _chamfered(value: float, *, driving: bool = True) -> dict[str, Any]:
    """A corner chamfered back: the dimension is to where the legs MEET."""
    return {
        "entities": [
            _line("l1", (0, 0), (27, 0)),
            _line("ch", (27, 0), (30, 3)),
            _line("l2", (30, 3), (30, 40)),
        ],
        "constraints": [
            {"kind": "fixed", "point": _ref("l1", "start")},
            {"kind": "horizontal", "entity": "l1"},
            {"kind": "vertical", "entity": "l2"},
            _join("l1", "end", "ch", "start"),
            _join("ch", "end", "l2", "start"),
            {
                "kind": "point_distance",
                "a": _ref("l1", "start"),
                "b": _ref("l1", "end", sharp="l2"),
                "direction": "horizontal",
                "value_mm": value,
                "driving": driving,
            },
        ],
    }


def test_a_point_distance_to_a_virtual_sharp() -> None:
    solved = _solve(_chamfered(45.0))
    assert solved.conflicting_constraints == [] and solved.redundant_constraints == []
    assert _line_of(solved, "l2").start.x == pytest.approx(45.0, abs=TOL)
    driven = _solve(_chamfered(1.0, driving=False))
    assert driven.dimensions[0].value_mm == pytest.approx(30.0, abs=TOL)


def test_a_sharp_on_a_non_line_is_malformed() -> None:
    raw = _chamfered(45.0)
    raw["entities"].append(
        {"id": "c", "kind": "circle", "center": _p(50, 50), "radius": 5}
    )
    raw["constraints"][-1]["b"] = _ref("l1", "end", sharp="c")
    with pytest.raises(SketchDefinitionError, match="virtual sharp"):
        _solve(raw)
    raw["constraints"][-1]["driving"] = False  # a reference reads it too
    with pytest.raises(SketchDefinitionError, match="virtual sharp"):
        _solve(raw)


def test_a_driven_sharp_on_parallel_legs_reads_its_own_end() -> None:
    """No sharp exists, so the readout falls back as a driven `distance` does
    (review of 564aa68: it used to raise `sketch_invalid`)."""
    raw = _chamfered(1.0, driving=False)
    raw["entities"][2] = _line("l2", (30, 3), (60, 3))  # parallel to l1
    raw["constraints"][2] = {"kind": "horizontal", "entity": "l2"}
    solved = _solve(raw)
    assert solved.dimensions[0].value_mm == pytest.approx(27.0, abs=TOL)


# -- determinism ---------------------------------------------------------------


def test_the_same_sketch_solves_bit_identically() -> None:
    raw = _inset(100.0)
    first = _solve(raw).model_dump_json()
    for _ in range(5):
        assert _solve(raw).model_dump_json() == first
