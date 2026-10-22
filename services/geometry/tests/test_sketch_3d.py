"""The 3D sketch: solver, snaps, Pipe on its lines, the bike (SKETCH-3D).

* the solver: a length slides the free end along its line, a distance between
  two free points splits the move, Along X/Y/Z, coincident, the remaining
  degrees of freedom, a redundant relation, a contradiction and a collapsed
  line are typed;
* snaps: the origin, a 2D sketch's point (through its plane), an earlier 3D
  sketch's point, and a model vertex that FOLLOWS its body through an edit;
* the bike skeleton (golden ``frame-bike-3d-sketch-skeleton-4-pipes``): every
  point to 1e-9 of the hand numbers, the four main Pipes equal to the 2D
  skeleton's, and the splayed chain stays matched to a plain build123d twin;
* a Plane Along Path on a 3D line, the typed refusals, and determinism.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false

import importlib.util
import itertools
import json
import math
import random
import time
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, cast

import pytest
from build123d import Plane, Solid, Vector
from geometry.features import evaluate_tree
from geometry.kernel import measure_shape
from geometry.overlay import evaluate_overlay
from geometry.sketch.solver3d import (
    Sketch3DConflictError,
    Sketch3DTooLargeError,
    solve_sketch_3d,
)
from loft_wire.features import EvaluateTreeRequest
from loft_wire.overlay import OverlayRequest
from loft_wire.sketch_3d import (
    Sketch3DAlong,
    Sketch3DCoincident,
    Sketch3DDistance,
    Sketch3DLength,
    SolvedSketch3DData,
)


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"{name}_sketch3d", Path(__file__).with_name(f"{name}.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sb = _load("_sketch3d_builder")
pb = _load("_pipe_builder")
GOLDEN = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "frame-bike-3d-sketch-skeleton-4-pipes"
)
P = tuple[float, float, float]


# --- the solver -------------------------------------------------------------------


def test_a_length_slides_the_free_end_along_its_line() -> None:
    solved = solve_sketch_3d(
        {"a": (0.0, 0.0, 0.0), "b": (3.0, 4.0, 12.0)},
        {"a": (0.0, 0.0, 0.0)},
        {"l": ("a", "b")},
        [Sketch3DLength(kind="length", line="l", value_mm=26.0)],
    )
    # |(3, 4, 12)| = 13: doubled along the same direction, exactly.
    assert solved.points["b"] == pytest.approx((6.0, 8.0, 24.0), abs=1e-12)
    assert solved.dof == 2
    assert solved.redundant == []


def test_a_distance_between_two_free_points_moves_both_equally() -> None:
    solved = solve_sketch_3d(
        {"a": (0.0, -64.0, 5.0), "b": (0.0, 64.0, 5.0)},
        {},
        {},
        [Sketch3DDistance(kind="distance", a="a", b="b", value_mm=130.0)],
    )
    assert solved.points == {"a": (0.0, -65.0, 5.0), "b": (0.0, 65.0, 5.0)}
    assert solved.dof == 5


def test_along_each_axis_and_coincident() -> None:
    axes: tuple[tuple[Literal["x", "y", "z"], int], ...] = (
        ("x", 0),
        ("y", 1),
        ("z", 2),
    )
    for axis, index in axes:
        solved = solve_sketch_3d(
            {"a": (1.0, 2.0, 3.0), "b": (5.0, 7.0, 11.0)},
            {"a": (1.0, 2.0, 3.0)},
            {"l": ("a", "b")},
            [Sketch3DAlong(kind="along", line="l", axis=axis)],
        )
        b = solved.points["b"]
        # The free end keeps its coordinate along the axis and takes a's others.
        want = [1.0, 2.0, 3.0]
        want[index] = (5.0, 7.0, 11.0)[index]
        assert b == pytest.approx(tuple(want), abs=1e-12)
        assert solved.dof == 1
    joined = solve_sketch_3d(
        {"a": (0.0, 0.0, 0.0), "b": (2.0, 2.0, 2.0)},
        {"a": (0.0, 0.0, 0.0)},
        {},
        [Sketch3DCoincident(kind="coincident", a="a", b="b")],
    )
    assert joined.points["b"] == (0.0, 0.0, 0.0)
    assert joined.dof == 0


def test_a_redundant_relation_is_named_and_a_contradiction_refused() -> None:
    lines = {"l": ("a", "b")}
    start: dict[str, P] = {"a": (0.0, 0.0, 0.0), "b": (0.0, 0.0, 9.0)}
    fixed: dict[str, P] = {"a": (0.0, 0.0, 0.0)}
    along = Sketch3DAlong(kind="along", line="l", axis="z")
    ten = Sketch3DLength(kind="length", line="l", value_mm=10.0)
    again = Sketch3DDistance(kind="distance", a="a", b="b", value_mm=10.0)
    solved = solve_sketch_3d(start, fixed, lines, [along, ten, again])
    assert solved.points["b"] == pytest.approx((0.0, 0.0, 10.0), abs=1e-12)
    assert solved.redundant == [2]
    assert solved.dof == 0
    other = Sketch3DDistance(kind="distance", a="a", b="b", value_mm=12.0)
    with pytest.raises(Sketch3DConflictError, match="cannot all hold"):
        solve_sketch_3d(start, fixed, lines, [along, ten, other])


def test_a_dimensioned_line_of_zero_length_is_refused() -> None:
    with pytest.raises(Sketch3DConflictError, match="zero length"):
        solve_sketch_3d(
            {"a": (1.0, 1.0, 1.0), "b": (1.0, 1.0, 1.0)},
            {},
            {"l": ("a", "b")},
            [Sketch3DLength(kind="length", line="l", value_mm=5.0)],
        )


# --- trees ------------------------------------------------------------------------


def _request(features: list[dict[str, Any]]) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate(
        {
            "part_id": sb.PART,
            "tree_version": 1,
            "features": features,
            "linear_deflection": 0.1,
        }
    )


def _results(features: list[dict[str, Any]]) -> Any:
    return evaluate_tree(_request(features))


def _ok(features: list[dict[str, Any]]) -> Any:
    evaluation = _results(features)
    bad = [
        (r.feature_id, r.error) for r in evaluation.result.features if r.status != "ok"
    ]
    assert not bad, bad
    return evaluation


def _error(features: list[dict[str, Any]], n: int) -> str:
    result = next(
        r for r in _results(features).result.features if str(r.feature_id) == sb.fid(n)
    )
    assert result.status == "error" and result.error is not None
    return result.error.code


def _sketch_3d(
    n: int,
    points: dict[str, P],
    lines: dict[str, tuple[str, str]] | None = None,
    *,
    snaps: dict[str, dict[str, Any]] | None = None,
    constraints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    entities: list[dict[str, Any]] = []
    for key, p in points.items():
        point: dict[str, Any] = {
            "id": key,
            "kind": "point",
            "position": {"x": p[0], "y": p[1], "z": p[2]},
        }
        if snaps and key in snaps:
            point["snap"] = snaps[key]
        entities.append(point)
    for key, (a, b) in (lines or {}).items():
        entities.append({"id": key, "kind": "line", "start": a, "end": b})
    return {
        "id": sb.fid(n),
        "feature": {
            "type": "sketch_3d",
            "version": 1,
            "params": {"entities": entities, "constraints": constraints or []},
        },
    }


def _points(evaluation: Any, n: int) -> dict[str, P]:
    result = next(
        r for r in evaluation.result.features if str(r.feature_id) == sb.fid(n)
    )
    assert isinstance(result.data, SolvedSketch3DData)
    return {
        p.id: (p.position.x, p.position.y, p.position.z) for p in result.data.points
    }


def _box(width: float) -> list[dict[str, Any]]:
    rect = [(0.0, 0.0), (width, 0.0), (width, 20.0), (0.0, 20.0), (0.0, 0.0)]
    return [
        pb.sketch(
            10,
            [
                pb.line(f"r{i}", a, b)
                for i, (a, b) in enumerate(itertools.pairwise(rect))
            ],
        ),
        pb.feature(
            11,
            {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": pb.fid(10)},
                    "distance_mm": 10.0,
                    "operation": "add",
                },
            },
        ),
    ]


def _vertex_snap(width: float, a: P, b: P, end: str) -> dict[str, Any]:
    """A vertex snap as the viewport makes it: the overlay's edge, one end."""
    overlay = evaluate_overlay(
        OverlayRequest.model_validate({"tree": _request(_box(width)).model_dump()})
    )
    want = sorted([a, b])
    for edge in overlay.edges:
        s = edge.signature
        ends = sorted(
            [(s.end_a.x, s.end_a.y, s.end_a.z), (s.end_b.x, s.end_b.y, s.end_b.z)]
        )
        if all(math.dist(p, q) < 1e-9 for p, q in zip(ends, want, strict=True)):
            return {
                "kind": "vertex",
                "edge": {
                    "kind": "subshape",
                    "feature_id": pb.fid(11),
                    "subshape_type": "edge",
                    "selector": {
                        "selector_version": 1,
                        "signature": s.model_dump(mode="json", exclude_none=True),
                    },
                },
                "end": end,
            }
    raise AssertionError(f"no edge {a} -> {b}")


# --- snaps ------------------------------------------------------------------------


def test_a_vertex_snap_follows_its_body_through_an_edit() -> None:
    """A point on the box's top corner (40, 20, 10): widen the box to 60 and
    the point, and the line from it, move with the corner."""
    snap = _vertex_snap(40.0, (40.0, 20.0, 0.0), (40.0, 20.0, 10.0), "b")
    sketch = _sketch_3d(
        1,
        {"c": (40.0, 20.0, 10.0), "far": (100.0, 100.0, 100.0)},
        {"l": ("c", "far")},
        snaps={"c": snap},
    )
    assert _points(_ok([*_box(40.0), sketch]), 1)["c"] == (40.0, 20.0, 10.0)
    edited = _ok([*_box(60.0), sketch])
    assert _points(edited, 1)["c"] == pytest.approx((60.0, 20.0, 10.0), abs=1e-9)
    # end "a" is the other end of the same edge.
    other = _sketch_3d(
        1,
        {"c": (0.0, 0.0, 0.0)},
        snaps={"c": {**snap, "end": "a"}},
    )
    assert _points(_ok([*_box(40.0), other]), 1)["c"] == (40.0, 20.0, 0.0)


def test_snaps_to_the_origin_a_2d_sketch_point_and_a_3d_sketch_point() -> None:
    # A 2D line on XZ (sketch y is world Z): its end (30, 40) is world (30, 0, 40).
    flat = pb.sketch(2, [pb.line("e1", (0.0, 0.0), (30.0, 40.0))], "XZ")
    first = _sketch_3d(
        3,
        {"o": (5.0, 5.0, 5.0), "q": (0.0, 0.0, 0.0)},
        snaps={
            "o": {"kind": "origin"},
            "q": {
                "kind": "sketch_point",
                "sketch": {"kind": "feature", "feature_id": pb.fid(2)},
                "entity": "e1",
                "point": "end",
            },
        },
    )
    second = _sketch_3d(
        4,
        {"r": (9.0, 9.0, 9.0)},
        snaps={
            "r": {
                "kind": "sketch_point",
                "sketch": {"kind": "feature", "feature_id": sb.fid(3)},
                "entity": "q",
                "point": "position",
            }
        },
    )
    evaluation = _ok([flat, first, second])
    assert _points(evaluation, 3) == {"o": (0.0, 0.0, 0.0), "q": (30.0, 0.0, 40.0)}
    assert _points(evaluation, 4) == {"r": (30.0, 0.0, 40.0)}


def test_a_snap_that_does_not_resolve_is_typed() -> None:
    lost = _sketch_3d(
        3,
        {"q": (0.0, 0.0, 0.0)},
        snaps={
            "q": {
                "kind": "sketch_point",
                "sketch": {"kind": "feature", "feature_id": pb.fid(2)},
                "entity": "missing",
                "point": "end",
            }
        },
    )
    flat = pb.sketch(2, [pb.line("e1", (0.0, 0.0), (30.0, 40.0))], "XZ")
    assert _error([flat, lost], 3) == "reference_unresolved"
    snap = _vertex_snap(40.0, (40.0, 20.0, 0.0), (40.0, 20.0, 10.0), "a")
    orphan = _sketch_3d(1, {"c": (0.0, 0.0, 0.0)}, snaps={"c": snap})
    assert _error([orphan], 1) == "subshape_unresolved"


def test_a_contradiction_is_sketch_conflicting() -> None:
    sketch = _sketch_3d(
        1,
        {"a": (0.0, 0.0, 0.0), "b": (0.0, 0.0, 10.0)},
        {"l": ("a", "b")},
        constraints=[
            {"kind": "fixed", "point": "a"},
            {"kind": "fixed", "point": "b"},
            {"kind": "length", "line": "l", "value_mm": 20.0},
        ],
    )
    assert _error([sketch], 1) == "sketch_conflicting"


# --- Pipe and Plane Along Path on 3D lines -----------------------------------------


def test_a_pipe_on_a_3d_line_and_a_missing_line() -> None:
    sketch = _sketch_3d(
        1, {"a": (0.0, 0.0, 0.0), "b": (20.0, 30.0, 60.0)}, {"seat": ("a", "b")}
    )
    bar = _ok([sketch, sb.pipe(2, 1, "seat")])
    # |(20, 30, 60)| = 70: a 31.8 x 1.0 ring that long.
    ring = math.pi * (15.9**2 - 14.9**2)
    assert measure_shape(bar.body).volume == pytest.approx(ring * 70.0, rel=1e-9)
    missing = sb.pipe(2, 1, "seat")
    missing["feature"]["params"]["path"][0]["entity"] = "nope"
    assert _error([sketch, missing], 2) == "reference_unresolved"


def test_a_plane_along_a_3d_line() -> None:
    sketch = _sketch_3d(
        1, {"a": (10.0, 0.0, 0.0), "b": (10.0, 60.0, 80.0)}, {"l": ("a", "b")}
    )
    path = {
        "kind": "sketch_curve",
        "sketch": {"kind": "feature", "feature_id": sb.fid(1)},
        "entity": "l",
    }
    plane = _ok([sketch, pb.along_path(2, path, ratio=0.5)]).datum_planes[
        uuid.UUID(pb.fid(2))
    ]
    assert tuple(plane.origin) == pytest.approx((10.0, 30.0, 40.0))
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.6, 0.8))


# --- the bike ---------------------------------------------------------------------


def test_the_bike_skeleton_lands_on_the_reference_to_1e_9() -> None:
    evaluation = _ok([sb.skeleton_3d(1)])
    points = _points(evaluation, 1)
    reference = sb.reference_points()
    assert list(points) == list(reference)
    for key, want in reference.items():
        assert math.dist(points[key], want) <= 1e-9, (key, points[key], want)
    # The typed ends really were off: 2 mm short, and 1 mm in across Y.
    typed = sb.typed_points()
    assert math.dist(typed["st"], reference["st"]) == pytest.approx(2.0)
    assert math.dist(typed["dl"], reference["dl"]) == pytest.approx(1.0)
    data = next(r.data for r in evaluation.result.features)
    assert isinstance(data, SolvedSketch3DData)
    # 4 free points x 3 - (2 lengths + Along Y's 2 + 1 distance) = 7.
    assert data.dof == 7
    assert data.redundant_constraints == []


def test_the_4_pipes_on_the_3d_skeleton_are_the_2d_skeletons_frame() -> None:
    three = measure_shape(_ok(sb.bike_frame_3d()["features"]).body)
    flat = evaluate_tree(EvaluateTreeRequest.model_validate(pb.bike_frame()))
    assert flat.body is not None
    two = measure_shape(flat.body)
    assert three.volume == pytest.approx(two.volume, abs=1e-6)
    assert three.surface_area == pytest.approx(two.surface_area, abs=1e-6)
    assert three.topology == two.topology


def _tube(a: Vector, b: Vector, od: float, wall: float) -> Solid:
    axis = b - a
    plane = Plane(origin=a, z_dir=axis.normalized())
    outer = Solid.make_cylinder(od / 2, axis.length, plane)
    bore = Solid.make_cylinder(od / 2 - wall, axis.length, plane)
    return outer.cut(bore).solids()[0]


def test_the_splayed_chain_stays_match_a_plain_build123d_twin() -> None:
    """The BACKLOG acceptance: the chain stays are Pipes on the 3D sketch tied
    to the BB and the dropouts, matching an independent build (cylinders minus
    bores on the hand joints) to 1e-4, here held to 1e-8 with an empty two-way
    difference. Measured 2026-10-21: volume 1.45e-3 mm^3 (4.5e-9 relative)."""
    tubes = ("down", "seat", "top", "head", "cs_l", "cs_r")
    evaluation = _ok(sb.bike_frame_3d(tubes)["features"])
    (mine,) = evaluation.body.solids()
    ref = {key: Vector(*p) for key, p in sb.reference_points().items()}
    parts = [
        _tube(ref[sb.LINES[n][0]], ref[sb.LINES[n][1]], *sb.TUBES[n]) for n in tubes
    ]
    (twin,) = parts[0].fuse(*parts[1:]).clean().solids()
    assert mine.is_valid
    ours, theirs = measure_shape(mine), measure_shape(twin)
    assert ours.topology == theirs.topology
    assert ours.topology.shells == 1
    assert ours.volume == pytest.approx(theirs.volume, rel=1e-8)
    assert float(mine.cut(twin).volume) <= 1e-6
    assert float(twin.cut(mine).volume) <= 1e-6
    # The stays' dropout caps set x_min and y by hand: a cap of radius R normal
    # to unit u spans R sqrt(1 - u_i^2) along axis i.
    dl = ref["dl"]
    u = dl.normalized()
    assert ours.bounding_box.min.x == pytest.approx(
        dl.X - 11.0 * math.sqrt(1 - u.X**2), abs=1e-6
    )
    assert ours.bounding_box.max.y == pytest.approx(
        dl.Y + 11.0 * math.sqrt(1 - u.Y**2), abs=1e-6
    )


def test_rebuilds_are_deterministic() -> None:
    tree = sb.bike_frame_3d()["features"]
    first, second = _ok(tree), _ok(tree)
    assert _points(first, 1) == _points(second, 1)
    assert measure_shape(first.body) == measure_shape(second.body)


def test_the_bike_sketch_rebuilds_byte_identical() -> None:
    """Two rebuilds of the 3D skeleton give the same payload, byte for byte
    (BLAS is pinned to one thread for the solve)."""
    tree = [sb.skeleton_3d(1)]
    payloads = [
        next(r.data for r in _ok(tree).result.features).model_dump_json()
        for _ in range(2)
    ]
    assert payloads[0] == payloads[1]
    assert "-142.00767235196136" in payloads[0]


# --- redundancy, size and the work budget ------------------------------------------


def _reference_redundancy(
    positions: dict[str, P],
    fixed: dict[str, P],
    lines: dict[str, tuple[str, str]],
    constraints: list[Any],
) -> tuple[int, list[int]]:
    """The first solver's diagnosis, kept as the oracle: one SVD rank per
    constraint prefix, in constraint order, at the solved positions."""
    import numpy as np

    solved = solve_sketch_3d(positions, fixed, lines, constraints).points
    free = [k for k in positions if k not in fixed]
    col = {k: 3 * i for i, k in enumerate(free)}
    n = 3 * len(free)
    rows: list[tuple[int, Any]] = []
    for index, c in enumerate(constraints):

        def row(entries: list[tuple[str, Any]]) -> Any:
            out = np.zeros(n)
            for key, grad in entries:
                if key in col:
                    out[col[key] : col[key] + 3] += grad
            return out

        eye = np.eye(3)
        if c.kind == "coincident":
            rows += [(index, row([(c.a, eye[k]), (c.b, -eye[k])])) for k in range(3)]
        elif c.kind == "along":
            a, b = lines[c.line]
            axis = "xyz".index(c.axis)
            rows += [
                (index, row([(b, eye[k]), (a, -eye[k])])) for k in range(3) if k != axis
            ]
        elif c.kind in ("length", "distance"):
            a, b = lines[c.line] if c.kind == "length" else (c.a, c.b)
            d = np.subtract(solved[b], solved[a])
            u = d / np.linalg.norm(d)
            rows.append((index, row([(b, u), (a, -u)])))

    def rank(matrix: Any) -> int:
        if len(matrix) == 0:
            return 0
        sv = np.linalg.svd(np.array(matrix), compute_uv=False)
        return int(np.count_nonzero(sv > sv[0] * 1e-9)) if sv[0] > 0 else 0

    redundant: list[int] = []
    kept: list[Any] = []
    for index in dict.fromkeys(i for i, _ in rows):
        mine = [r for i, r in rows if i == index]
        if rank(kept + mine) < rank(kept) + len(mine):
            redundant.append(index)
        kept += mine
    return n - rank(kept), redundant


def _random_sketch(seed: int) -> tuple[Any, ...]:
    """A small consistent sketch: random relations measured off random points,
    some repeated or implied, so redundancy actually occurs."""
    rng = random.Random(seed)
    count = rng.randint(3, 7)
    truth = {
        f"p{i}": (rng.uniform(-50, 50), rng.uniform(-50, 50), rng.uniform(-50, 50))
        for i in range(count)
    }
    keys = list(truth)
    lines = {f"l{i}": (keys[i], keys[i + 1]) for i in range(count - 1)}
    constraints: list[Any] = []
    aligned: set[str] = set()
    for _ in range(rng.randint(2, 9)):
        kind = rng.choice(["length", "distance", "along", "length"])
        line = rng.choice(list(lines))
        a, b = lines[line]
        if kind == "along" and line not in aligned:
            aligned.add(line)
            axis: Literal["x", "y", "z"] = rng.choice(("x", "y", "z"))
            k = "xyz".index(axis)
            # Make it hold: give b a's other two coordinates.
            pa, pb = truth[a], list(truth[b])
            for j in range(3):
                if j != k:
                    pb[j] = pa[j]
            truth[b] = (pb[0], pb[1], pb[2])
            constraints.append(Sketch3DAlong(kind="along", line=line, axis=axis))
        elif kind != "along":
            constraints.append(("measure", kind, line, a, b))
    measured: list[Any] = []
    for c in constraints:
        if isinstance(c, tuple):
            _, kind, line, a, b = cast(tuple[str, str, str, str, str], c)
            value = math.dist(truth[a], truth[b])
            measured.append(
                Sketch3DLength(kind="length", line=line, value_mm=value)
                if kind == "length"
                else Sketch3DDistance(kind="distance", a=a, b=b, value_mm=value)
            )
        else:
            measured.append(c)
    fixed = {keys[0]: truth[keys[0]]}
    return dict(truth), fixed, lines, measured


@pytest.mark.parametrize("seed", range(40))
def test_redundancy_and_dof_match_the_per_prefix_svd_oracle(seed: int) -> None:
    sketch = _random_sketch(seed)
    solved = solve_sketch_3d(*sketch)
    assert (solved.dof, solved.redundant) == _reference_redundancy(*sketch)


def test_the_existing_redundant_case_still_names_the_same_constraint() -> None:
    lines = {"l": ("a", "b")}
    start: dict[str, P] = {"a": (0.0, 0.0, 0.0), "b": (0.0, 0.0, 9.0)}
    fixed: dict[str, P] = {"a": (0.0, 0.0, 0.0)}
    constraints: list[Any] = [
        Sketch3DAlong(kind="along", line="l", axis="z"),
        Sketch3DLength(kind="length", line="l", value_mm=10.0),
        Sketch3DDistance(kind="distance", a="a", b="b", value_mm=10.0),
        Sketch3DCoincident(kind="coincident", a="b", b="b2"),
    ]
    start["b2"] = (0.0, 0.0, 10.0)
    solved = solve_sketch_3d(start, fixed, lines, constraints)
    assert solved.redundant == [2]
    assert (solved.dof, solved.redundant) == _reference_redundancy(
        start, fixed, lines, constraints
    )


def _chain(count: int) -> tuple[Any, ...]:
    """The review's case: a chain with a length on every line and Along X on
    every other one."""
    positions = {
        f"p{i}": (10.0 * i + 0.3 * (i % 3), 2.0 * (i % 5), 1.0 * (i % 7))
        for i in range(count)
    }
    lines = {f"l{i}": (f"p{i}", f"p{i + 1}") for i in range(count - 1)}
    constraints: list[Any] = []
    for i in range(count - 1):
        constraints.append(Sketch3DLength(kind="length", line=f"l{i}", value_mm=11.0))
        if i % 2 == 0:
            constraints.append(Sketch3DAlong(kind="along", line=f"l{i}", axis="x"))
    return positions, {"p0": positions["p0"]}, lines, constraints


def test_a_200_point_skeleton_solves_in_under_two_seconds() -> None:
    """Measured 0.22 s (the first solver took 118 s: one SVD per constraint)."""
    start = time.perf_counter()
    solved = solve_sketch_3d(*_chain(200))
    assert time.perf_counter() - start < 2.0
    # 199 free points x 3 - (199 lengths + 100 Along X's 2 rows) = 198.
    assert solved.dof == 198
    assert solved.redundant == []


def test_a_1000_entity_sketch_is_refused_by_the_budget_not_left_running() -> None:
    """500 points + 499 lines: past the work budget, refused at once with a
    typed error (the budget counts flops from the sketch's size, never a
    clock, so the same sketch is refused on every machine)."""
    start = time.perf_counter()
    with pytest.raises(Sketch3DTooLargeError, match="too large"):
        solve_sketch_3d(*_chain(500))
    assert time.perf_counter() - start < 5.0
    positions, _, lines, constraints = _chain(500)
    feature = _sketch_3d(1, positions, lines)
    feature["feature"]["params"]["constraints"] = [
        c.model_dump() for c in constraints
    ] + [{"kind": "fixed", "point": "p0"}]
    assert _error([feature], 1) == "sketch_too_large"


def test_the_golden_is_this_tree() -> None:
    assert json.loads((GOLDEN / "model.json").read_text()) == sb.bike_frame_3d()
