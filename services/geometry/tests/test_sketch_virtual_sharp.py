"""SKETCH-FILLET-KEEP-DIMS: a filleted leg's dimension is kept to the virtual sharp.

The fixture is an 80 x 50 rectangle with all four corners rounded by the web's
fillet (``cornerConstraints.ts``): legs trimmed, arcs joined by endpoint
tangents, each radius dimensioned. Before the fix the fillet DROPPED the W and
H dimensions on the legs it trimmed, and R5 -> R15 grew the outline to
100 x 70 (review ``grow.py``): nothing held the legs' lines apart. Now W and H
are measured to the virtual sharps, as SolidWorks and Fusion 360 keep them.
"""

import math
from typing import Any

import pytest
from geometry.sketch import (
    PlanegcsSketchSolver,
    SketchDefinition,
    SolvedSketch,
    planegcs_solver,
    readouts,
)
from geometry.sketch.schemas import DistanceConstraint, SketchArc, SketchLine
from geometry.sketch.solver import SketchDefinitionError
from geometry.sketch.virtual_sharp import line_intersection
from pydantic import ValidationError

TOL = 1e-9
W, H = 80.0, 50.0


def _p(x: float, y: float) -> dict[str, float]:
    return {"x": x, "y": y}


def _line(i: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": i,
        "kind": "line",
        "construction": False,
        "start": _p(*a),
        "end": _p(*b),
    }


_Pt = tuple[float, float]


def _arc(i: str, c: _Pt, s: _Pt, e: _Pt) -> dict[str, Any]:
    return {
        "id": i,
        "kind": "arc",
        "construction": False,
        "center": _p(*c),
        "start": _p(*s),
        "end": _p(*e),
    }


def _tan(a: str, ap: str, b: str, bp: str) -> dict[str, Any]:
    return {"kind": "tangent", "a": a, "b": b, "a_point": ap, "b_point": bp}


def _rounded(r: float, *, width: float = W, driving: bool = True) -> SketchDefinition:
    """The R5-filleted 80 x 50 rectangle (as drawn), radius dimension ``r``."""
    f = 5.0
    entities = [
        _line("b", (f, 0), (W - f, 0)),
        _line("rt", (W, f), (W, H - f)),
        _line("tp", (W - f, H), (f, H)),
        _line("lf", (0, H - f), (0, f)),
        _arc("a1", (W - f, f), (W - f, 0), (W, f)),
        _arc("a2", (W - f, H - f), (W, H - f), (W - f, H)),
        _arc("a3", (f, H - f), (f, H), (0, H - f)),
        _arc("a4", (f, f), (0, f), (f, 0)),
    ]
    constraints: list[dict[str, Any]] = [
        {"kind": "horizontal", "entity": "b"},
        {"kind": "horizontal", "entity": "tp"},
        {"kind": "vertical", "entity": "rt"},
        {"kind": "vertical", "entity": "lf"},
        _tan("b", "end", "a1", "start"),
        _tan("a1", "end", "rt", "start"),
        _tan("rt", "end", "a2", "start"),
        _tan("a2", "end", "tp", "start"),
        _tan("tp", "end", "a3", "start"),
        _tan("a3", "end", "lf", "start"),
        _tan("lf", "end", "a4", "start"),
        _tan("a4", "end", "b", "start"),
        {
            "kind": "distance",
            "entity": "b",
            "value_mm": width,
            "driving": driving,
            "start_sharp": "lf",
            "end_sharp": "rt",
        },
        {
            "kind": "distance",
            "entity": "rt",
            "value_mm": H,
            "start_sharp": "b",
            "end_sharp": "tp",
        },
        *[
            {"kind": "radius", "entity": a, "value_mm": r}
            for a in ("a1", "a2", "a3", "a4")
        ],
    ]
    return SketchDefinition.model_validate(
        {"entities": entities, "constraints": constraints}
    )


def _solve(sketch: SketchDefinition) -> SolvedSketch:
    return PlanegcsSketchSolver().solve(sketch)


def _legs(solved: SolvedSketch) -> dict[str, SketchLine]:
    legs = {e.id: e for e in solved.entities if isinstance(e, SketchLine)}
    assert set(legs) == {"b", "rt", "tp", "lf"}
    return legs


def _outline(solved: SolvedSketch) -> tuple[float, float]:
    legs = _legs(solved)
    return (
        legs["rt"].start.x - legs["lf"].start.x,
        legs["tp"].start.y - legs["b"].start.y,
    )


def _assert_tangent(solved: SolvedSketch, r: float) -> None:
    """Each arc's centre is r inside both legs it joins: tangent, not a cusp."""
    by_id = {e.id: e for e in solved.entities}
    legs = _legs(solved)
    left, right = legs["lf"].start.x, legs["rt"].start.x
    bottom, top = legs["b"].start.y, legs["tp"].start.y
    for name in ("a1", "a2", "a3", "a4"):
        arc = by_id[name]
        assert isinstance(arc, SketchArc)
        c = arc.center
        assert math.hypot(arc.start.x - c.x, arc.start.y - c.y) == pytest.approx(
            r, abs=TOL
        )
        assert min(c.x - left, right - c.x) == pytest.approx(r, abs=TOL)
        assert min(c.y - bottom, top - c.y) == pytest.approx(r, abs=TOL)
        assert left < c.x < right and bottom < c.y < top


@pytest.mark.parametrize("r", [5.0, 15.0, 24.0])
def test_an_r_edit_keeps_the_outline(r: float) -> None:
    """R5 -> R15 is the backlog's case (it grew to 100 x 70); R24 nearly closes."""
    solved = _solve(_rounded(r))
    assert solved.status == "underconstrained"
    assert solved.redundant_constraints == [] and solved.conflicting_constraints == []
    # The rectangle's own two: it may still slide. Untrimmed, W + H left 2 too.
    assert solved.dof == 2
    assert _outline(solved) == pytest.approx((W, H), abs=TOL)
    _assert_tangent(solved, r)
    assert [d.value_mm for d in solved.dimensions][:2] == pytest.approx([W, H], abs=TOL)


def test_editing_w_still_drives_the_size() -> None:
    solved = _solve(_rounded(15, width=120))
    assert solved.redundant_constraints == [] and solved.conflicting_constraints == []
    assert _outline(solved) == pytest.approx((120, H), abs=TOL)
    _assert_tangent(solved, 15)


def test_a_driven_w_reads_to_the_virtual_sharps() -> None:
    """A reference dimension reads the sharp-to-sharp span, not the trimmed leg."""
    solved = _solve(_rounded(5, width=1, driving=False))
    assert solved.dimensions[0].driving is False
    width = _outline(solved)[0]
    assert solved.dimensions[0].value_mm == pytest.approx(width, abs=TOL)
    assert width == pytest.approx(W, abs=1e-6)  # the drawn sharps


def test_a_skewed_corner_is_measured_along_its_leg() -> None:
    """A 60-degree corner chamfered back: the dimension is to where the legs
    MEET, |sharp - start| along the leg, not to the trimmed end."""
    s3 = math.sqrt(3.0)
    sketch = SketchDefinition.model_validate(
        {
            "entities": [
                _line("l1", (0, 0), (27, 0)),
                _line("l2", (31.5, 1.5 * s3), (40, 10 * s3)),
                _line("ch", (27, 0), (31.5, 1.5 * s3)),
            ],
            "constraints": [
                {"kind": "fixed", "point": {"entity": "l1", "point": "start"}},
                {"kind": "horizontal", "entity": "l1"},
                {"kind": "angle", "a": "l1", "b": "l2", "value_deg": 60},
                {
                    "kind": "coincident",
                    "a": {"entity": "l1", "point": "end"},
                    "b": {"entity": "ch", "point": "start"},
                },
                {
                    "kind": "coincident",
                    "a": {"entity": "ch", "point": "end"},
                    "b": {"entity": "l2", "point": "start"},
                },
                {"kind": "distance", "entity": "l1", "value_mm": 45, "end_sharp": "l2"},
            ],
        }
    )
    solved = _solve(sketch)
    assert solved.conflicting_constraints == [] and solved.redundant_constraints == []
    by_id = {e.id: e for e in solved.entities}
    l1, l2 = by_id["l1"], by_id["l2"]
    assert isinstance(l1, SketchLine) and isinstance(l2, SketchLine)
    sharp = line_intersection(l1, l2)
    assert sharp == pytest.approx((45.0, 0.0), abs=TOL)


def test_parallel_lines_have_no_sharp_and_say_so() -> None:
    sketch = SketchDefinition.model_validate(
        {
            "entities": [_line("a", (0, 0), (10, 0)), _line("b", (0, 5), (10, 5))],
            "constraints": [
                {"kind": "horizontal", "entity": "a"},
                {"kind": "horizontal", "entity": "b"},
                {"kind": "distance", "entity": "a", "value_mm": 10, "end_sharp": "b"},
            ],
        }
    )
    assert _solve(sketch).status == "conflicting"


@pytest.mark.parametrize("driving", [True, False])
def test_a_sharp_with_a_non_line_is_malformed(driving: bool) -> None:
    sketch = SketchDefinition.model_validate(
        {
            "entities": [
                _line("a", (0, 0), (10, 0)),
                _arc("c", (5, 5), (10, 5), (5, 10)),
            ],
            "constraints": [
                {
                    "kind": "distance",
                    "entity": "a",
                    "value_mm": 10,
                    "end_sharp": "c",
                    "driving": driving,
                },
            ],
        }
    )
    with pytest.raises(SketchDefinitionError, match="virtual sharp"):
        _solve(sketch)


def test_the_readouts_share_the_solvers_tolerance() -> None:
    """``readouts.py`` restates the constant to keep its import one-way."""
    assert readouts.SATISFIED_TOL_MM == planegcs_solver.SATISFIED_TOL_MM


def test_a_line_is_not_its_own_sharp() -> None:
    with pytest.raises(ValidationError, match="TWO different lines"):
        DistanceConstraint.model_validate(
            {"kind": "distance", "entity": "a", "value_mm": 5, "start_sharp": "a"}
        )


def test_a_stored_distance_parses_to_its_endpoints() -> None:
    """Additive: a distance persisted before sharps reads as endpoint-to-endpoint."""
    stored = DistanceConstraint.model_validate(
        {"kind": "distance", "entity": "a", "value_mm": 5}
    )
    assert stored.start_sharp is None and stored.end_sharp is None


def test_the_solve_is_deterministic() -> None:
    first = _solve(_rounded(15)).model_dump_json()
    assert all(_solve(_rounded(15)).model_dump_json() == first for _ in range(3))
