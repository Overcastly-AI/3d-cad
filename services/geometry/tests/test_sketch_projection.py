"""SKETCH-PROJECT-EDGES: projected entities, in the solver and on a rebuild.

A projected line, arc or circle is a body edge seen from the sketch plane
(Fusion 360's Project, SolidWorks' Convert Entities). In the solver (step 1)
the entity is built from fixed parameters, adds no degrees of freedom, takes
constraints through its ordinary points, and comes back unchanged with its
link. Edits that reshape it in place are refused until the link is broken.

On a rebuild (step 2) the evaluator re-finds the edge on the body at the
sketch's tree position and re-projects it before the solve
(:func:`geometry.kernel.project.project_edge`); one that cannot follow its edge
is sick: it keeps its stored coordinates and the sketch stays ok. The width
edit itself, against a fresh pick, is ``test_sketch_projection_revision.py``.
"""

import copy
import importlib.util
import math
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from build123d import Edge, Plane
from geometry.features.evaluate import rebuild_cache_stats, reset_rebuild_cache
from geometry.kernel.project import (
    ProjectedArc,
    ProjectedCircle,
    ProjectedLine,
    project_edge,
)
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
from geometry.sketch.projected import entity_point_names
from geometry.sketch.schemas import (
    MirrorAxisEntity,
    Point2D,
    SketchArc,
    SketchCircle,
    SketchEntity,
    SketchLine,
)
from geometry.sketch.solver import SketchDefinitionError
from loft_wire.features import SolvedSketchData

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


# --- step 2: re-projection on a rebuild ---------------------------------------------

_V3 = tuple[float, float, float]

#: Sketch planes as explicit (origin, x axis, y axis, normal): the expected
#: local coordinates below are dot products with these axes, worked by hand,
#: never the kernel's own transform. Offset: XY lifted 10. Tilted: rotated 30
#: deg about X. Antiparallel: XY seen from below (normal -Z, so local y = -y).
_S, _C = math.sin(math.radians(30.0)), math.cos(math.radians(30.0))
_PLANES: dict[str, tuple[_V3, _V3, _V3, _V3]] = {
    "offset": ((0.0, 0.0, 10.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "tilted": ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, _C, _S), (0.0, -_S, _C)),
    "antiparallel": (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0),
        (0.0, 0.0, -1.0),
    ),
}


def _plane(name: str) -> Plane:
    origin, x, _y, z = _PLANES[name]
    return Plane(origin=origin, x_dir=x, z_dir=z)


def _dot(a: _V3, b: _V3) -> float:
    return sum(p * q for p, q in zip(a, b, strict=True))


def _add(a: _V3, b: _V3, k: float = 1.0) -> _V3:
    return (a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2])


def _local(name: str, p: _V3) -> tuple[float, float]:
    origin, x, y, _z = _PLANES[name]
    d = _add(p, origin, -1.0)
    return (_dot(d, x), _dot(d, y))


def _near(got: tuple[float, float], want: tuple[float, float]) -> bool:
    return math.dist(got, want) <= 1e-9


@pytest.mark.parametrize("name", sorted(_PLANES))
def test_a_line_projects_to_its_ends_seen_along_the_normal(name: str) -> None:
    a, b = (1.0, 2.0, 3.0), (4.0, 6.0, 3.0)
    got = project_edge(Edge.make_line(b, a), _plane(name), "line")
    assert isinstance(got, ProjectedLine)
    # The canonical ends: end_a is the lexicographically smaller, whichever
    # way the edge runs.
    assert _near(got.a, _local(name, a))
    assert _near(got.b, _local(name, b))
    assert got.a_3d == pytest.approx(a) and got.b_3d == pytest.approx(b)


@pytest.mark.parametrize("name", sorted(_PLANES))
@pytest.mark.parametrize("sense", [1.0, -1.0])
def test_an_arc_projects_counter_clockwise_whichever_way_its_axis_points(
    name: str, sense: float
) -> None:
    """A quarter arc 7 mm off the plane, its axis along (+) or against (-)
    the normal. Seen from the sketch, the -axis arc runs clockwise, so its
    ends swap to keep the sketch's counter-clockwise convention."""
    origin, x, y, z = _PLANES[name]
    centre = _add(_add(origin, z, 7.0), x, 2.0)
    axis = (sense * z[0], sense * z[1], sense * z[2])
    arc = Edge.make_circle(
        4.0, Plane(origin=centre, x_dir=x, z_dir=axis), start_angle=0, end_angle=90
    )
    got = project_edge(arc, _plane(name), "arc")
    assert isinstance(got, ProjectedArc)
    on_x, on_y = _add(centre, x, 4.0), _add(centre, y, 4.0 * sense)
    first, last = (on_x, on_y) if sense > 0 else (on_y, on_x)
    assert _near(got.center, _local(name, centre))
    assert _near(got.start, _local(name, first))
    assert _near(got.end, _local(name, last))


@pytest.mark.parametrize("name", sorted(_PLANES))
@pytest.mark.parametrize("sense", [1.0, -1.0])
def test_a_circle_projects_to_its_centre_and_radius(name: str, sense: float) -> None:
    origin, x, _y, z = _PLANES[name]
    centre = _add(_add(origin, z, -3.0), x, 5.0)
    axis = (sense * z[0], sense * z[1], sense * z[2])
    circle = Edge.make_circle(2.5, Plane(origin=centre, x_dir=x, z_dir=axis))
    got = project_edge(circle, _plane(name), "circle")
    assert isinstance(got, ProjectedCircle)
    assert _near(got.center, _local(name, centre))
    assert got.radius == pytest.approx(2.5, abs=1e-12)


def test_a_line_along_the_normal_is_degenerate() -> None:
    edge = Edge.make_line((1.0, 1.0, 0.0), (1.0, 1.0, 5.0))
    assert project_edge(edge, Plane.XY, "line") == "degenerate"


@pytest.mark.parametrize(
    "edge",
    [
        Edge.make_circle(3.0, Plane.XZ),
        Edge.make_circle(3.0, Plane(origin=(0, 0, 0), z_dir=(0, 0.1, 1))),
        Edge.make_ellipse(5.0, 3.0),
        Edge.make_spline([(0, 0, 0), (5, 3, 0), (10, 0, 0)]),
    ],
    ids=["circle-end-on", "circle-tilted", "ellipse", "bspline"],
)
def test_a_curve_without_an_exact_sketch_entity_is_unsupported(edge: Edge) -> None:
    for kind in ("line", "arc", "circle"):
        assert project_edge(edge, Plane.XY, kind) == "unsupported_curve"


def test_an_edge_that_projects_to_another_kind_is_kind_changed() -> None:
    line = Edge.make_line((0, 0, 0), (5, 0, 0))
    arc = Edge.make_circle(3.0, start_angle=0, end_angle=90)
    circle = Edge.make_circle(3.0)
    assert project_edge(line, Plane.XY, "arc") == "kind_changed"
    assert project_edge(arc, Plane.XY, "line") == "kind_changed"
    assert project_edge(arc, Plane.XY, "circle") == "kind_changed"
    assert project_edge(circle, Plane.XY, "arc") == "kind_changed"


def _load_lip_builder() -> ModuleType:
    path = Path(__file__).resolve().parent / "_lip_builder.py"
    spec = importlib.util.spec_from_file_location("_lip_builder", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LIP = _load_lip_builder()


def _solved(evaluation: Any, feature_id: uuid.UUID) -> SolvedSketchData:
    (result,) = [r for r in evaluation.result.features if r.feature_id == feature_id]
    assert result.status == "ok", result.error
    assert isinstance(result.data, SolvedSketchData)
    return result.data


def _stored(tree: list[dict[str, Any]], feature_id: uuid.UUID) -> list[SketchEntity]:
    (item,) = [i for i in tree if i["id"] == str(feature_id)]
    return SketchDefinition.model_validate(item["feature"]["params"]).entities


def _states(data: SolvedSketchData) -> dict[str, tuple[str, str | None, str | None]]:
    return {p.entity: (p.state, p.tier, p.reason) for p in data.projections}


def _same_place(got: SketchEntity, want: SketchEntity) -> bool:
    pairs = zip(entity_point_names(got), entity_point_names(want), strict=True)
    return all(math.dist((p.x, p.y), (q.x, q.y)) <= 1e-9 for (_n, p), (_m, q) in pairs)


def test_an_unedited_rebuild_re_projects_every_edge_onto_its_stored_place() -> None:
    tree = LIP.authored_tree(LIP.AUTHORED_W)
    data = _solved(LIP.evaluate(tree), LIP.RIM_SKETCH_ID)
    assert len(data.projections) == 16
    assert set(_states(data).values()) == {("ok", "exact", None)}
    assert data.dof == 0
    stored = _stored(tree, LIP.RIM_SKETCH_ID)
    assert all(
        _same_place(got, want) for got, want in zip(data.entities, stored, strict=True)
    )


def test_with_no_body_every_projection_is_sick_and_keeps_its_coordinates() -> None:
    """A projected sketch ahead of every body: sick with ``no_body``, and the
    sketch still ok on its stored coordinates."""
    tree = LIP.authored_tree(LIP.AUTHORED_W)
    rim = copy.deepcopy(next(i for i in tree if i["id"] == str(LIP.RIM_SKETCH_ID)))
    rim["feature"]["params"]["plane"] = {"kind": "datum_plane", "plane": "XY"}
    data = _solved(LIP.evaluate([rim]), LIP.RIM_SKETCH_ID)
    assert set(_states(data).values()) == {("sick", None, "no_body")}
    assert data.entities == _stored([rim], LIP.RIM_SKETCH_ID)


def test_deleting_the_shell_leaves_the_sketch_ok_with_its_inner_loop_sick() -> None:
    """Without the shell there is no inner rim. Its 8 edges are sick and keep
    their stored place; the outer 8 still resolve, exactly, onto theirs. The
    inner arcs are NOT re-found on the concentric outer arcs, as the durable
    circle tier alone would: a geometric re-find the body names differently
    is another edge (the name guard of ``_match_edge_records``)."""
    tree = LIP.authored_tree(LIP.AUTHORED_W)
    gone = [i for i in tree if i["id"] != str(LIP.SHELL_ID)]
    evaluation = LIP.evaluate(gone)
    assert all(status == "ok" for _i, status, _c in LIP.statuses(evaluation))
    data = _solved(evaluation, LIP.RIM_SKETCH_ID)
    states = _states(data)
    inner = {e for e in states if e.startswith("i")}
    assert len(inner) == 8
    assert {e for e, s in states.items() if s == ("sick", None, "unresolved")} == inner
    assert {e for e, s in states.items() if s == ("ok", "exact", None)} == (
        set(states) - inner
    )
    stored = _stored(tree, LIP.RIM_SKETCH_ID)
    for got, want in zip(data.entities, stored, strict=True):
        assert got == want if got.id in inner else _same_place(got, want)


def test_an_edge_that_now_projects_to_another_kind_is_sick() -> None:
    """The outer +X/-Y corner arc stored as a line between its ends."""
    tree = LIP.authored_tree(LIP.AUTHORED_W)
    rim = next(i for i in tree if i["id"] == str(LIP.RIM_SKETCH_ID))
    entities = rim["feature"]["params"]["entities"]
    index = next(k for k, e in enumerate(entities) if e["id"] == "obr")
    arc = entities[index]
    entities[index] = {
        "id": "obr",
        "kind": "line",
        "start": arc["start"],
        "end": arc["end"],
        "construction": True,
        "projection": arc["projection"],
    }
    data = _solved(LIP.evaluate(tree[:6]), LIP.RIM_SKETCH_ID)
    assert _states(data)["obr"] == ("sick", None, "kind_changed")
    want = _by_id(_stored(tree, LIP.RIM_SKETCH_ID), "obr")
    assert _by_id(data.entities, "obr") == want


def test_seen_end_on_a_line_is_degenerate_and_an_arc_unsupported() -> None:
    """A sketch on the XZ plane projecting the rim's -X line (it runs along Y,
    the plane's normal) and a corner arc (its axis lies IN the plane)."""
    tree = LIP.authored_tree(LIP.AUTHORED_W)
    rim = next(i for i in tree if i["id"] == str(LIP.RIM_SKETCH_ID))
    picked = [
        e for e in rim["feature"]["params"]["entities"] if e["id"] in ("ol", "obr")
    ]
    side_id = uuid.UUID(int=0xF1F1)
    side = {
        "id": str(side_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XZ"},
                "entities": picked,
                "constraints": [],
            },
        },
    }
    data = _solved(LIP.evaluate([*tree[:5], side]), side_id)
    assert _states(data) == {
        "obr": ("sick", None, "unsupported_curve"),
        "ol": ("sick", None, "degenerate"),
    }


def test_a_cold_and_a_cache_resumed_rebuild_are_byte_identical() -> None:
    """Resumed before the sketch (it projects off a cached body) and after it
    (its payload comes back from the checkpoint): the same bytes and the same
    projection statuses as a rebuild with the cache emptied."""
    tree = LIP.revised(LIP.authored_tree(LIP.AUTHORED_W, inset=True), LIP.REVISED_W)

    def answer() -> tuple[bytes | None, str | None, Any, list[Any]]:
        evaluation = LIP.evaluate(tree, 7)
        result = evaluation.result
        return (
            evaluation.glb,
            result.mesh_glb_id,
            result.properties,
            [r.data for r in result.features],
        )

    reset_rebuild_cache()
    cold = answer()
    try:
        for prefix in (5, 6):
            reset_rebuild_cache()
            LIP.evaluate(tree[:prefix], 6)
            hits = rebuild_cache_stats().hits
            warm = answer()
            assert rebuild_cache_stats().hits > hits
            assert warm == cold
    finally:
        reset_rebuild_cache()
