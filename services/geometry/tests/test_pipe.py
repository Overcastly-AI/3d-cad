"""Pipe and Plane Along Path (PIPE-ALONG-PATH): what the goldens cannot say.

The goldens lock the straight bar, the ring section, the mitred chain, the
closed loop, the plane along an arc and the bike frame. This file adds, each
against a number derived by hand:

* the chain rules: pick order and drawn direction never change the tube;
  branched, disjoint and repeated picks are ``sweep_path_not_connected``;
  a branched skeleton is that for a Sweep too, not a kernel ValueError;
* the operations: join, new body, cut; and the refusals (tight bend, missing
  curve, cut with no body);
* model edges as a path, chained around a box corner in 3D;
* face names: every face of a tube is named by its role, and the names
  survive a diameter edit and a skeleton edit;
* the plane along a path: ratio, distance, flip, out of range, a model edge,
  and that it follows a skeleton edit.
"""

import importlib.util
import itertools
import math
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from build123d import Edge, Vector
from geometry.features import evaluate_tree
from geometry.kernel import measure_shape
from geometry.kernel.path_chain import PathNotConnectedError, chain_edges
from geometry.overlay import evaluate_overlay
from loft_wire.features import EvaluateTreeRequest
from loft_wire.overlay import OverlayRequest


def _builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_pipe_builder_unit", Path(__file__).with_name("_pipe_builder.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pb = _builder()
RING = math.pi * (10.0**2 - 8.0**2)  # OD 20, wall 2


def _eval(features: list[dict[str, Any]]) -> Any:
    return evaluate_tree(EvaluateTreeRequest.model_validate(pb.request(features)))


def _ok(features: list[dict[str, Any]]) -> Any:
    evaluation = _eval(features)
    bad = [
        (r.feature_id, r.error) for r in evaluation.result.features if r.status != "ok"
    ]
    assert not bad, bad
    return evaluation


def _error(features: list[dict[str, Any]], n: int) -> str:
    evaluation = _eval(features)
    result = next(
        r for r in evaluation.result.features if str(r.feature_id) == pb.fid(n)
    )
    assert result.status == "error" and result.error is not None
    return result.error.code


def _polyline(
    points: list[tuple[float, float]], *, plane: str = "XY"
) -> dict[str, Any]:
    lines = [
        pb.line(f"e{i + 1}", a, b)
        for i, (a, b) in enumerate(itertools.pairwise(points))
    ]
    return pb.sketch(1, lines, plane)


# --- the chain ----------------------------------------------------------------


def _line(a: tuple[float, float, float], b: tuple[float, float, float]) -> Edge:
    return Edge.make_line(a, b)


def test_a_chain_runs_from_the_first_picks_start_side() -> None:
    picks = [
        _line((100, 80, 0), (100, 0, 0)),  # drawn downwards
        _line((40, 80, 0), (100, 80, 0)),
        _line((0, 0, 0), (100, 0, 0)),  # drawn towards the corner
    ]
    chained = chain_edges(picks)
    assert chained.order == (1, 0, 2)
    starts = [tuple(round(c, 9) for c in e.position_at(0)) for e in chained.edges]
    assert starts == [(40, 80, 0), (100, 80, 0), (100, 0, 0)]
    assert not chained.is_closed


def test_a_loop_starts_where_the_first_pick_does() -> None:
    square = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
    sides = [_line(square[i], square[(i + 1) % 4]) for i in range(4)]
    chained = chain_edges([sides[2], sides[0], sides[3], sides[1]])
    assert chained.is_closed
    assert chained.order == (0, 2, 1, 3)
    assert tuple(chained.edges[0].position_at(0)) == pytest.approx((10, 10, 0))


@pytest.mark.parametrize(
    ("picks", "message"),
    [
        (
            [
                _line((0, 0, 0), (10, 0, 0)),
                _line((0, 0, 0), (0, 10, 0)),
                _line((0, 0, 0), (-10, 0, 0)),
            ],
            "branches at",
        ),
        ([_line((0, 0, 0), (10, 0, 0)), _line((20, 0, 0), (30, 0, 0))], "separate"),
        ([_line((0, 0, 0), (10, 0, 0)), _line((10, 0, 0), (0, 0, 0))], "same curve"),
        (
            [Edge.make_circle(5), _line((5, 0, 0), (15, 0, 0))],
            "closed curve",
        ),
    ],
    ids=["branched", "disjoint", "picked-twice", "circle-with-others"],
)
def test_a_pick_that_is_not_one_chain_is_refused(
    picks: list[Edge], message: str
) -> None:
    with pytest.raises(PathNotConnectedError, match=message):
        chain_edges(picks)


def test_pick_order_and_drawn_direction_do_not_change_the_tube() -> None:
    points = [(0.0, 0.0), (100.0, 0.0), (100.0, 80.0), (40.0, 80.0)]
    forward = _ok(
        [
            _polyline(points),
            pb.pipe(2, [pb.curve(1, f"e{i}") for i in (1, 2, 3)], 20, 2),
        ]
    )
    shuffled = _ok(
        [
            _polyline(points),
            pb.pipe(2, [pb.curve(1, f"e{i}") for i in (2, 3, 1)], 20, 2),
        ]
    )
    a, b = measure_shape(forward.body), measure_shape(shuffled.body)
    assert a.volume == pytest.approx(RING * 240, rel=1e-9)
    assert b.volume == pytest.approx(a.volume, abs=1e-6)
    assert float(forward.body.cut(shuffled.body).volume) <= 1e-6


def test_a_branched_skeleton_pick_is_sweep_path_not_connected() -> None:
    skeleton = pb.skeleton(1)
    # Seat, down and the construction horizontal all start at the BB.
    picks = [pb.curve(1, name) for name in ("seat", "down", "h")]
    assert _error([skeleton, pb.pipe(2, picks, 30)], 2) == "sweep_path_not_connected"
    disjoint = [pb.curve(1, "seat"), pb.curve(1, "head")]
    assert _error([skeleton, pb.pipe(2, disjoint, 30)], 2) == "sweep_path_not_connected"


def test_a_sweep_along_a_branched_skeleton_is_typed_too() -> None:
    """BIKE-SWEEP-PATH-PICK: the whole skeleton as a Sweep path was a kernel
    ValueError ("may self-intersect"); it is now the typed error."""
    circle = {
        "id": "c1",
        "kind": "circle",
        "center": {"x": 0.0, "y": 0.0},
        "radius": 10.0,
    }
    sweep = pb.feature(
        3,
        {
            "type": "sweep",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": pb.fid(2)},
                "path": {"kind": "feature", "feature_id": pb.fid(1)},
                "operation": "add",
            },
        },
    )
    skeleton = pb.skeleton(1)
    # A chainstay from the BB: three tube lines now meet there.
    skeleton["feature"]["params"]["entities"].append(
        pb.line("cs", (0.0, 0.0), (-405.0, 70.0))
    )
    features = [skeleton, pb.sketch(2, [circle]), sweep]
    assert _error(features, 3) == "sweep_path_not_connected"


# --- operations and refusals --------------------------------------------------


def _plate() -> list[dict[str, Any]]:
    rect = [(0.0, 0.0), (80.0, 0.0), (80.0, 40.0), (0.0, 40.0), (0.0, 0.0)]
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


def test_a_pipe_cut_drills_a_round_channel_through_the_plate() -> None:
    """A 6 mm bar along a line through the plate's mid-thickness, across its
    whole 40 mm depth and past both sides: a channel of pi 3^2 40."""
    path = pb.sketch(1, [pb.line("e1", (40.0, -10.0), (40.0, 50.0))], "XY")
    lifted = path["feature"]["params"]
    lifted["plane"] = {"kind": "feature", "feature_id": pb.fid(12)}
    datum = pb.feature(
        12,
        {
            "type": "datum",
            "version": 1,
            "params": {"kind": "offset", "base": "XY", "offset_mm": 5.0},
        },
    )
    evaluation = _ok(
        [*_plate(), datum, path, pb.pipe(2, [pb.curve(1, "e1")], 6.0, operation="cut")]
    )
    assert measure_shape(evaluation.body).volume == pytest.approx(
        80 * 40 * 10 - math.pi * 9 * 40, abs=1e-6
    )


def test_join_fuses_the_tube_and_new_body_keeps_it_separate() -> None:
    """A 10 mm bar along the plate's top front edge region, 50 long, its axis
    at z = 10 on y = 20: half of it is inside the plate. Joined, the part
    gains the half above the top face; as a new body, the whole bar."""
    path = pb.sketch(1, [pb.line("e1", (10.0, 20.0), (60.0, 20.0))])
    lifted = path["feature"]["params"]
    lifted["plane"] = {"kind": "feature", "feature_id": pb.fid(12)}
    datum = pb.feature(
        12,
        {
            "type": "datum",
            "version": 1,
            "params": {"kind": "offset", "base": "XY", "offset_mm": 10.0},
        },
    )
    bar = [datum, path]
    joined = _ok([*_plate(), *bar, pb.pipe(2, [pb.curve(1, "e1")], 10.0)])
    separate = _ok(
        [*_plate(), *bar, pb.pipe(2, [pb.curve(1, "e1")], 10.0, merge=False)]
    )
    plate = 80 * 40 * 10
    whole = math.pi * 25 * 50
    assert measure_shape(joined.body).volume == pytest.approx(
        plate + whole / 2, abs=1e-6
    )
    assert len(joined.result.bodies) == 1
    assert len(separate.result.bodies) == 2
    assert measure_shape(separate.body).volume == pytest.approx(plate + whole, abs=1e-6)


def _vertical_bore(x: float, y: float) -> list[dict[str, Any]]:
    """An OD 6 pipe cut along a vertical line through the plate at (x, y)."""
    path = pb.sketch(1, [pb.line("e1", (x, -2.0), (x, 12.0))], "XZ")
    path["feature"]["params"]["plane"] = {"kind": "feature", "feature_id": pb.fid(13)}
    datum = pb.feature(
        13,
        {
            "type": "datum",
            "version": 1,
            "params": {"kind": "offset", "base": "XZ", "offset_mm": -y},
        },
    )
    return [datum, path, pb.pipe(2, [pb.curve(1, "e1")], 6.0, operation="cut")]


@pytest.mark.parametrize("replicate", ["mirror", "pattern"])
def test_a_pipe_cut_is_mirrored_and_patterned_as_a_cut(replicate: str) -> None:
    """The composition matrix's CM-5 shape for the pipe (its CUT_ROW_EXEMPT
    reason): a body-scope mirror or pattern after a pipe CUT replicates the
    REMOVAL (the cut tool is on record), never fills it back in. The XZ datum
    at offset -y puts sketch (x, *) at world y = 12; plate 80 x 40 x 10."""
    bore = math.pi * 9 * 10
    if replicate == "mirror":
        datum = pb.feature(
            14,
            {
                "type": "datum",
                "version": 1,
                "params": {"base": "YZ", "offset_mm": 40.0},
            },
        )
        step = [
            datum,
            pb.feature(
                15,
                {
                    "type": "mirror",
                    "version": 1,
                    "params": {"plane": {"kind": "feature", "feature_id": pb.fid(14)}},
                },
            ),
        ]
    else:
        step = [
            pb.feature(
                15,
                {
                    "type": "pattern",
                    "version": 1,
                    "params": {
                        "pattern": {
                            "kind": "linear",
                            "direction": {"x": 0.0, "y": 1.0, "z": 0.0},
                            "spacing_mm": 16.0,
                            "count": 2,
                        }
                    },
                },
            )
        ]
    evaluation = _ok([*_plate(), *_vertical_bore(20.0, 12.0), *step])
    assert measure_shape(evaluation.body).volume == pytest.approx(
        80 * 40 * 10 - 2 * bore, abs=1e-6
    )


def test_a_cut_with_no_body_and_a_missing_curve_are_typed() -> None:
    path = pb.sketch(1, [pb.line("e1", (0.0, 0.0), (50.0, 0.0))])
    assert (
        _error([path, pb.pipe(2, [pb.curve(1, "e1")], 10.0, operation="cut")], 2)
        == "no_prior_body"
    )
    assert (
        _error([path, pb.pipe(2, [pb.curve(1, "nope")], 10.0)], 2)
        == "reference_unresolved"
    )
    assert _error([pb.pipe(2, [pb.curve(1, "e1")], 10.0)], 2) == "reference_unresolved"


def test_a_bend_tighter_than_the_tube_is_refused() -> None:
    """An R8 arc can carry an OD 15 tube (radius 7.5) but not an OD 16 one."""
    arc = pb.sketch(1, [pb.arc("a1", (0.0, 0.0), (8.0, 0.0), (0.0, 8.0))])
    fits = _ok([arc, pb.pipe(2, [pb.curve(1, "a1")], 15.0)])
    torus_quarter = math.pi * 7.5**2 * (math.pi * 8 / 2)
    assert measure_shape(fits.body).volume == pytest.approx(torus_quarter, rel=1e-9)
    assert _error([arc, pb.pipe(2, [pb.curve(1, "a1")], 16.0)], 2) == "sweep_failed"


# --- model edges as the path --------------------------------------------------


def _box_edges() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The 80 x 40 x 10 plate and three of its edges that chain round the
    corner at the origin in 3D: along X, along Y, up Z, as the overlay hands
    them to a click."""
    features = _plate()
    overlay = evaluate_overlay(
        OverlayRequest.model_validate({"tree": pb.request(features)})
    )

    def pick(
        a: tuple[float, float, float], b: tuple[float, float, float]
    ) -> dict[str, Any]:
        want = sorted([a, b])
        for edge in overlay.edges:
            s = edge.signature
            ends = sorted(
                [(s.end_a.x, s.end_a.y, s.end_a.z), (s.end_b.x, s.end_b.y, s.end_b.z)]
            )
            if all(math.dist(p, q) < 1e-9 for p, q in zip(ends, want, strict=True)):
                return {
                    "kind": "subshape",
                    "feature_id": pb.fid(11),
                    "subshape_type": "edge",
                    "selector": {
                        "selector_version": 1,
                        "signature": s.model_dump(mode="json", exclude_none=True),
                    },
                }
        raise AssertionError(f"no edge {a} -> {b}")

    picks = [
        pick((0, 40, 0), (0, 0, 0)),
        pick((0, 0, 0), (80, 0, 0)),
        pick((80, 0, 0), (80, 0, 10)),
    ]
    return features, picks


def test_a_pipe_follows_a_chain_of_model_edges_round_a_3d_corner() -> None:
    features, picks = _box_edges()
    evaluation = _ok([*features, pb.pipe(2, picks, 4.0, merge=False)])
    # As a new body the tube is whole (it overlaps the plate along the edges):
    # the bodies are the plate and the mitred tube, pi 2^2 (40 + 80 + 10).
    assert len(evaluation.result.bodies) == 2
    total = measure_shape(evaluation.body).volume
    assert total == pytest.approx(80 * 40 * 10 + math.pi * 4 * 130, rel=1e-9)


# --- face names ---------------------------------------------------------------


def _pipe_names(evaluation: Any) -> list[str]:
    prefix = f"{pb.fid(2)}:"
    return sorted(
        str(n)[len(prefix) :]
        for n in evaluation.face_names()
        if n is not None and str(n).startswith(prefix)
    )


def test_every_tube_face_is_named_by_its_role_and_survives_edits() -> None:
    sketch_id = pb.fid(1)
    points = [(0.0, 0.0), (100.0, 0.0), (100.0, 80.0)]
    tree = [
        _polyline(points),
        pb.pipe(2, [pb.curve(1, "e1"), pb.curve(1, "e2")], 20, 2),
    ]
    names = _pipe_names(_ok(tree))
    assert names == sorted(
        [
            "start",
            "end",
            f"wall:{sketch_id}:e1",
            f"bore:{sketch_id}:e1",
            f"wall:{sketch_id}:e2",
            f"bore:{sketch_id}:e2",
        ]
    )
    thicker = [
        _polyline(points),
        pb.pipe(2, [pb.curve(1, "e1"), pb.curve(1, "e2")], 24, 3),
    ]
    assert _pipe_names(_ok(thicker)) == names
    moved = [_polyline([(0.0, 0.0), (120.0, 0.0), (150.0, 60.0)]), tree[1]]
    assert _pipe_names(_ok(moved)) == names


def test_the_bike_frame_names_every_tube_wall() -> None:
    evaluation = _ok(pb.bike_frame()["features"])
    walls = {
        str(n).split(":wall:")[1].split("/")[0]  # a split face is qualified
        for n in evaluation.face_names()
        if n is not None and ":wall:" in str(n)
    }
    assert walls == {f"{pb.fid(1)}:{name}" for name in ("down", "seat", "top", "head")}


# --- plane along path ---------------------------------------------------------


def _plane_of(features: list[dict[str, Any]], n: int) -> Any:
    return _ok(features).datum_planes[uuid.UUID(pb.fid(n))]


def test_plane_along_a_line_by_ratio_distance_and_flip() -> None:
    line = pb.sketch(1, [pb.line("e1", (10.0, 0.0), (70.0, 80.0))], "XZ")
    # (10,0)->(70,80) on XZ: length 100, direction (0.6, 0, 0.8).
    by_ratio = _plane_of([line, pb.along_path(2, pb.curve(1, "e1"), ratio=0.25)], 2)
    assert tuple(by_ratio.origin) == pytest.approx((25.0, 0.0, 20.0))
    assert tuple(by_ratio.z_dir) == pytest.approx((0.6, 0.0, 0.8))
    # x_dir is the skeleton's normal (XZ's is -Y): continuous under edits.
    assert tuple(by_ratio.x_dir) == pytest.approx((0.0, -1.0, 0.0))
    by_distance = _plane_of(
        [line, pb.along_path(2, pb.curve(1, "e1"), distance=25.0)], 2
    )
    assert tuple(by_distance.origin) == pytest.approx(tuple(by_ratio.origin))
    flipped = _plane_of(
        [line, pb.along_path(2, pb.curve(1, "e1"), ratio=0.25, flip=True)], 2
    )
    assert tuple(flipped.z_dir) == pytest.approx((-0.6, 0.0, -0.8))
    assert tuple(flipped.x_dir) == pytest.approx(tuple(by_ratio.x_dir))
    end = _plane_of([line, pb.along_path(2, pb.curve(1, "e1"), distance=100.0)], 2)
    assert tuple(end.origin) == pytest.approx((70.0, 0.0, 80.0))
    assert _error([line, pb.along_path(2, pb.curve(1, "e1"), distance=100.01)], 2) == (
        "datum_path_out_of_range"
    )


def test_plane_along_path_follows_the_skeleton() -> None:
    """The head tube's mid plane moves with the head angle, by hand."""
    for angle in (73.0, 72.0):
        plane = _plane_of(
            [pb.skeleton(1, angle), pb.along_path(2, pb.curve(1, "head"), ratio=0.5)], 2
        )
        p = pb.skeleton_points(angle)
        mid = (
            (p["ht_top"][0] + p["ht_bottom"][0]) / 2,
            (p["ht_top"][1] + p["ht_bottom"][1]) / 2,
        )
        assert tuple(plane.origin) == pytest.approx((mid[0], 0.0, mid[1]), abs=1e-7)
        a = math.radians(angle)
        assert tuple(plane.z_dir) == pytest.approx(
            (math.cos(a), 0.0, -math.sin(a)), abs=1e-9
        )


def test_plane_along_a_model_edge_runs_from_its_picked_end() -> None:
    features, picks = _box_edges()
    edge = picks[2]  # (80,0,0) - (80,0,10)
    signature = edge["selector"]["signature"]
    plane = _plane_of([*features, pb.along_path(2, edge, distance=2.5)], 2)
    a = signature["end_a"]
    b = signature["end_b"]
    start, finish = Vector(a["x"], a["y"], a["z"]), Vector(b["x"], b["y"], b["z"])
    direction = (finish - start).normalized()
    assert tuple(plane.origin) == pytest.approx(tuple(start + direction * 2.5))
    assert tuple(plane.z_dir) == pytest.approx(tuple(direction))
