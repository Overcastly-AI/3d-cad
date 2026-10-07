"""SKETCH-PROJECT-EDGES step 1: projected entities are fixed solver geometry.

A projected line, arc or circle is a body edge seen from the sketch plane
(Fusion 360's Project, SolidWorks' Convert Entities). Until re-projection lands
the solver honours the stored coordinates: the entity is built from fixed
parameters, adds no degrees of freedom, takes constraints through its ordinary
points, and comes back unchanged with its link. Edits that reshape it in place
are refused until the link is broken.
"""

import math
import uuid
from typing import Any

import pytest
from geometry.sketch import (
    PlanegcsSketchSolver,
    SketchDefinition,
    SketchEditError,
    SolvedSketch,
    chamfer_sketch,
    extend_sketch,
    fillet_sketch,
    mirror_sketch,
    offset_sketch,
    trim_sketch,
)
from geometry.sketch.planegcs_solver import (
    SETTLE_WORK_UNITS,
    _GcsBuild,  # pyright: ignore[reportPrivateUsage]
)
from geometry.sketch.schemas import (
    MirrorAxisEntity,
    Point2D,
    SketchArc,
    SketchCircle,
    SketchEntity,
    SketchLine,
)
from geometry.sketch.solver import SketchDefinitionError

TOL = 1e-9
ANCHOR = uuid.UUID("00000000-0000-4000-8000-000000000001")


def _p(x: float, y: float) -> dict[str, float]:
    return {"x": x, "y": y}


def _link() -> dict[str, Any]:
    """A stored edge reference (its signature is not read until step 2)."""
    point = {"x": 0.0, "y": 0.0, "z": 0.0}
    signature = {
        "curve": "line",
        "end_a": point,
        "end_b": {"x": 1.0, "y": 0.0, "z": 0.0},
        "midpoint": {"x": 0.5, "y": 0.0, "z": 0.0},
        "length_mm": 1.0,
    }
    return {
        "edge": {
            "kind": "subshape",
            "feature_id": str(ANCHOR),
            "subshape_type": "edge",
            "selector": {"signature": signature},
        }
    }


def _line(
    i: str, a: tuple[float, float], b: tuple[float, float], *, linked: bool = False
) -> dict[str, Any]:
    entity: dict[str, Any] = {"id": i, "kind": "line", "start": _p(*a), "end": _p(*b)}
    return {**entity, "projection": _link()} if linked else entity


def _arc(
    i: str,
    c: tuple[float, float],
    s: tuple[float, float],
    e: tuple[float, float],
    *,
    linked: bool = False,
) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "id": i,
        "kind": "arc",
        "center": _p(*c),
        "start": _p(*s),
        "end": _p(*e),
    }
    return {**entity, "projection": _link()} if linked else entity


def _circle(
    i: str, c: tuple[float, float], r: float, *, linked: bool = False
) -> dict[str, Any]:
    entity: dict[str, Any] = {"id": i, "kind": "circle", "center": _p(*c), "radius": r}
    return {**entity, "projection": _link()} if linked else entity


def _ref(entity: str, point: str) -> dict[str, str]:
    return {"entity": entity, "point": point}


def _join(a: str, ap: str, b: str, bp: str) -> dict[str, Any]:
    return {"kind": "coincident", "a": _ref(a, ap), "b": _ref(b, bp)}


def _solve(
    entities: list[dict[str, Any]], constraints: list[dict[str, Any]]
) -> SolvedSketch:
    sketch = SketchDefinition.model_validate(
        {"entities": entities, "constraints": constraints}
    )
    return PlanegcsSketchSolver().solve(sketch)


def _entities(*raw: dict[str, Any]) -> list[SketchEntity]:
    return SketchDefinition.model_validate(
        {"entities": list(raw), "constraints": []}
    ).entities


def _by_id(entities: list[SketchEntity], ident: str) -> SketchEntity:
    return next(e for e in entities if e.id == ident)


def _rim() -> list[dict[str, Any]]:
    """A projected 120 x 80 rim, CCW."""
    corners = [(0.0, 0.0), (120.0, 0.0), (120.0, 80.0), (0.0, 80.0)]
    return [
        _line(f"p{k}", corners[k], corners[(k + 1) % 4], linked=True) for k in range(4)
    ]


def test_a_rectangle_joined_to_projected_corners_is_fully_constrained() -> None:
    """Four free lines, each corner coincident to a projected corner: DOF 0."""
    free = [
        _line("a", (1, 1), (119, 1)),
        _line("b", (119, 1), (119, 79)),
        _line("c", (119, 79), (1, 79)),
        _line("d", (1, 79), (1, 1)),
    ]
    constraints = [
        _join("a", "end", "b", "start"),
        _join("b", "end", "c", "start"),
        _join("c", "end", "d", "start"),
        _join("d", "end", "a", "start"),
        *(_join(f, "start", f"p{k}", "start") for k, f in enumerate("abcd")),
    ]
    solved = _solve(_rim() + free, constraints)

    assert solved.status == "converged"
    assert solved.dof == 0
    assert solved.redundant_constraints == []
    assert solved.conflicting_constraints == []
    rim = _entities(*_rim())
    for stored in rim:
        assert _by_id(solved.entities, stored.id) == stored  # bitwise, link kept
    a = _by_id(solved.entities, "a")
    assert isinstance(a, SketchLine)
    assert (a.start.x, a.start.y, a.end.x, a.end.y) == pytest.approx(
        (0, 0, 120, 0), abs=TOL
    )


def test_a_point_line_distance_to_a_projected_line_holds() -> None:
    """The QA inset: a free point held 1 mm inside the projected rim's top."""
    point = {"id": "q", "kind": "point", "position": _p(30, 75)}
    dim = {"kind": "point_line_distance", "point": _ref("q", "position")}
    solved = _solve([*_rim(), point], [{**dim, "line": "p2", "value_mm": 1.0}])

    assert solved.status == "underconstrained"
    assert solved.dof == 1
    q = _by_id(solved.entities, "q")
    assert q.kind == "point"
    assert q.position.y == pytest.approx(79.0, abs=TOL)
    assert q.position.x == pytest.approx(30.0, abs=TOL)  # the settle holds x
    assert _by_id(solved.entities, "p2").projection is not None


def test_projected_points_take_the_existing_constraint_kinds() -> None:
    """Coincident, collinear, tangent, concentric and a point distance."""
    entities = [
        _line("p", (0, 0), (100, 0), linked=True),
        _arc("pa", (50, 50), (60, 50), (50, 60), linked=True),
        _circle("pc", (0, 50), 10, linked=True),
        _line("l", (10, 1), (40, 2)),
        _circle("c", (51, 49), 4),
        _line("t", (12, 30), (12, 70)),
    ]
    constraints = [
        {"kind": "collinear", "a": "l", "b": "p"},
        {"kind": "concentric", "a": "c", "b": "pa"},
        {"kind": "tangent", "a": "t", "b": "pc"},
        {"kind": "vertical", "entity": "t"},
        {
            "kind": "point_distance",
            "a": _ref("l", "start"),
            "b": _ref("p", "start"),
            "value_mm": 15.0,
        },
    ]
    solved = _solve(entities, constraints)

    assert solved.status == "underconstrained"
    assert solved.redundant_constraints == solved.conflicting_constraints == []
    line, ring, tangent = (_by_id(solved.entities, i) for i in ("l", "c", "t"))
    assert isinstance(line, SketchLine)
    assert isinstance(ring, SketchCircle)
    assert isinstance(tangent, SketchLine)
    assert (line.start.y, line.end.y) == pytest.approx((0, 0), abs=TOL)
    assert line.start.x == pytest.approx(15.0, abs=TOL)
    assert (ring.center.x, ring.center.y) == pytest.approx((50, 50), abs=TOL)
    assert tangent.start.x == pytest.approx(10.0, abs=TOL)
    for ident in ("p", "pa", "pc"):
        assert _by_id(solved.entities, ident).projection is not None


def test_a_projected_arc_has_no_arc_rules_and_frees_no_other_arc() -> None:
    """The cleared tag is the projected arc's own: a free arc before it keeps
    its rules (5 DOF), and the projected one adds nothing and no redundancy."""
    entities = [
        _arc("free", (0, 0), (10, 0), (0, 10)),
        _arc("linked", (50, 0), (60, 0), (50, 10), linked=True),
        _arc("free2", (0, 50), (10, 50), (0, 60)),
    ]
    solved = _solve(entities, [])

    assert solved.status == "underconstrained"
    assert solved.dof == 10
    assert solved.redundant_constraints == []
    linked = _by_id(solved.entities, "linked")
    (stored,) = _entities(entities[1])
    assert linked == stored


def test_a_projected_circle_is_zero_dof_with_its_radius_fixed() -> None:
    solved = _solve([_circle("pc", (5, 5), 7.5, linked=True)], [])

    assert (solved.status, solved.dof) == ("converged", 0)
    circle = _by_id(solved.entities, "pc")
    assert isinstance(circle, SketchCircle)
    assert circle.radius == 7.5
    assert circle.projection is not None


def test_a_degenerate_projected_arc_is_refused_like_any_arc() -> None:
    with pytest.raises(SketchDefinitionError, match="degenerate"):
        _solve([_arc("pa", (0, 0), (0, 0), (1, 1), linked=True)], [])


def test_read_back_keeps_the_link_on_both_paths() -> None:
    """``adoptSolved`` replaces the web's entities with these: a dropped
    ``projection`` would unlink every projected entity on the next save."""
    settled = _solve([*_rim(), _line("x", (5, 5), (20, 9))], [])
    assert settled.status == "underconstrained"
    plain = _solve(_rim(), [])
    assert plain.status == "converged"
    for solved in (settled, plain):
        linked = [e.id for e in solved.entities if e.projection is not None]
        assert linked == ["p0", "p1", "p2", "p3"]
    dumped = settled.model_dump(mode="json")["entities"]
    assert "projection" not in dumped[-1]
    assert dumped[0]["projection"]["edge"]["feature_id"] == str(ANCHOR)


def test_the_settle_budget_counts_only_free_entities() -> None:
    sketch = SketchDefinition.model_validate(
        {"entities": [*_rim(), _line("x", (5, 5), (20, 9))], "constraints": []}
    )
    build = _GcsBuild(sketch, {})
    assert build._ladder_budget() == SETTLE_WORK_UNITS  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# Edit ops
# ---------------------------------------------------------------------------


def _edit(op: str, entities: list[SketchEntity]) -> list[SketchEntity]:
    match op:
        case "trim":
            return trim_sketch(entities, "p", Point2D(x=5, y=0))
        case "extend":
            return extend_sketch(entities, "p", Point2D(x=9, y=0))
        case "fillet":
            return fillet_sketch(entities, "p", "v", 2.0)
        case "fillet-second":
            return fillet_sketch(entities, "v", "p", 2.0)
        case _:
            return chamfer_sketch(entities, "p", "v", 2.0)


@pytest.mark.parametrize("op", ["trim", "extend", "fillet", "fillet-second", "chamfer"])
def test_edits_that_reshape_a_projected_entity_are_refused(op: str) -> None:
    entities = _entities(
        _line("p", (0, 0), (10, 0), linked=True),
        _line("v", (20, -5), (20, 5)),
        _line("w", (2, -5), (2, 5)),
    )
    with pytest.raises(SketchEditError, match="Break link first") as raised:
        _edit(op, entities)
    assert raised.value.code == "sketch_entity_linked"


def test_a_projected_arc_cannot_be_trimmed() -> None:
    entities = _entities(
        _arc("pa", (0, 0), (10, 0), (-10, 0), linked=True),
        _line("w", (0, -1), (0, 20)),
    )
    with pytest.raises(SketchEditError, match="linked to the body"):
        trim_sketch(entities, "pa", Point2D(x=10 * math.cos(0.3), y=10 * math.sin(0.3)))


def test_a_projected_entity_still_cuts_and_bounds_free_geometry() -> None:
    """Only the projected entity itself is protected; it is a fine cutter."""
    entities = _entities(
        _line("p", (5, -5), (5, 5), linked=True), _line("f", (0, 0), (10, 0))
    )
    trimmed = trim_sketch(entities, "f", Point2D(x=8, y=0))
    f = _by_id(trimmed, "f")
    assert isinstance(f, SketchLine)
    assert f.end.x == pytest.approx(5.0, abs=TOL)


def test_offset_and_mirror_copies_are_unlinked() -> None:
    entities = _entities(
        _line("p", (0, 0), (10, 0), linked=True),
        _arc("pa", (0, 0), (3, 0), (0, 3), linked=True),
        _line("axis", (0, -1), (0, 1)),
    )
    copies = offset_sketch(entities, "p", 2.0) + mirror_sketch(
        entities, ["p", "pa"], MirrorAxisEntity(kind="entity", entity="axis")
    )
    assert len(copies) == 3
    assert all(copy.projection is None for copy in copies)
    assert isinstance(copies[2], SketchArc)
