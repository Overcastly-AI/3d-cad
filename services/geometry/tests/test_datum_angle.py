# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""DATUM-PLANE-ANGLE: a plane through a line, turned from a reference by an angle.

The golden ``datum-angle-head-tube-od50-id32-l160-25deg`` runs the parametrized
gates (mass properties, topology, determinism, STEP round trip). This file adds
what a golden cannot say, each against a number derived outside the code under
test:

* the moto frame's steering-head tube, sketched on a 25 deg plane about a
  sketch line and extruded symmetric, gives the frame golden's volume, with an
  empty two-way difference against the golden's independent build123d twin
  (the golden tree revolves the head about a tilted axis);
* the plane-at-angle math by hand (angle 0, 90, flip, sign), and the refusal
  of a line that is not parallel to its reference;
* the plane follows BOTH inputs on rebuild (a moved sketch line, a resized
  body's edge, a turned reference), and every lost reference leaves a typed,
  sick datum rather than a crash;
* the wire: references materialise into the dependency map, and a stored
  datum of every older kind dumps byte-identically.
"""

import importlib.util
import json
import math
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from build123d import Plane, Solid, Vector
from geometry.features import evaluate_tree
from geometry.harness import load_model_request
from geometry.kernel import measure_shape
from geometry.kernel.datum_angle import DatumLineNotParallelError, plane_at_angle
from geometry.overlay import evaluate_overlay
from loft_wire.features import (
    DatumFeature,
    EvaluateTreeRequest,
    feature_references,
)
from loft_wire.overlay import OverlayRequest
from pydantic import ValidationError

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
FRAME = GOLDENS / "frame-moto-cradle-tube-od25.4-t1.6"
HEAD_GOLDEN = GOLDENS / "datum-angle-head-tube-od50-id32-l160-25deg"

#: The frame golden's head: a sketch on XZ revolved about a tilted axis line,
#: then unioned into the frame.
HEAD_SKETCH = "00000000-0000-0000-0000-00000000001e"
HEAD_REVOLVE = "00000000-0000-0000-0000-00000000001f"
HEAD_UNION = "00000000-0000-0000-0000-000000000032"

#: The front apex the head's axis passes through (test_moto_frame.py derives it
#: from the rail corners independently; the cross-tube sketch at 0x1a uses it).
APEX_X, APEX_Z = -32.38409359864937, 495.46749033400226


def _load_moto_frame_tests() -> Any:
    """``tests/test_moto_frame.py``, loaded by file path (importlib import-mode),
    for its independent build123d frame (the frame golden's derivation)."""
    spec = importlib.util.spec_from_file_location(
        "_moto_frame_twin", Path(__file__).with_name("test_moto_frame.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_independent_frame: Callable[[], tuple[Any, float]] = (
    _load_moto_frame_tests()._independent_frame
)


def _fid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012x}"


def _request(golden: Path) -> EvaluateTreeRequest:
    request = load_model_request((golden / "model.json").read_text(encoding="utf-8"))
    assert isinstance(request, EvaluateTreeRequest)
    return request


def _expected(golden: Path) -> dict[str, Any]:
    return json.loads((golden / "expected.json").read_text(encoding="utf-8"))


def _circle(eid: str, x: float, y: float, r: float) -> dict[str, Any]:
    return {"id": eid, "kind": "circle", "center": {"x": x, "y": y}, "radius": r}


def _line(eid: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "construction": True,
        "start": {"x": a[0], "y": a[1]},
        "end": {"x": b[0], "y": b[1]},
    }


def _feature(fid: str, type_: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"id": fid, "feature": {"type": type_, "version": 1, "params": params}}


def _sketch(fid: str, plane: dict[str, Any], entities: list[Any]) -> dict[str, Any]:
    return _feature(
        fid, "sketch", {"plane": plane, "entities": entities, "constraints": []}
    )


def _on(fid: str) -> dict[str, Any]:
    return {"kind": "feature", "feature_id": fid}


def _angle(
    fid: str,
    line: dict[str, Any],
    reference: dict[str, Any],
    angle: float,
    flip: bool = False,
) -> dict[str, Any]:
    return _feature(
        fid,
        "datum",
        {
            "kind": "angle",
            "line": line,
            "reference": reference,
            "angle_deg": angle,
            "flip": flip,
        },
    )


def _sketch_line(sketch: str, entity: str) -> dict[str, Any]:
    return {"kind": "sketch_line", "sketch": _on(sketch), "entity": entity}


XY = {"kind": "datum_plane", "plane": "XY"}


def _angled_head(rake_deg: float = 25.0) -> list[dict[str, Any]]:
    """The steering head on a plane at an angle: a construction line along -Y
    through the apex, on an XY datum at the apex height; the plane turned
    ``rake_deg`` from XY about it (the XY normal +Z turns right-handed about
    -Y, towards -X: raked back); the 50/32 annulus on that plane at its origin
    (the line's point nearest the world origin, the apex), extruded symmetric
    160."""
    return [
        _feature(
            _fid(0x40), "datum", {"base": "XY", "offset_mm": APEX_Z, "flip": False}
        ),
        _sketch(
            _fid(0x41),
            _on(_fid(0x40)),
            [_line("head", (APEX_X, 10.0), (APEX_X, -10.0))],
        ),
        _angle(_fid(0x42), _sketch_line(_fid(0x41), "head"), XY, rake_deg),
        _sketch(
            _fid(0x43),
            _on(_fid(0x42)),
            [_circle("o", 0, 0, 25.0), _circle("i", 0, 0, 16.0)],
        ),
        _feature(
            _fid(0x44),
            "extrude",
            {
                "profile": _on(_fid(0x43)),
                "distance_mm": 160.0,
                "operation": "add",
                "extent": "symmetric",
                "merge": False,
            },
        ),
    ]


def _frame_with_angled_head() -> EvaluateTreeRequest:
    data = _request(FRAME).model_dump(mode="json")
    features: list[dict[str, Any]] = []
    for item in data["features"]:
        if item["id"] == HEAD_SKETCH:
            features.extend(_angled_head())
            continue
        if item["id"] == HEAD_REVOLVE:
            continue
        if item["id"] == HEAD_UNION:
            item["feature"]["params"]["tool"] = _on(_fid(0x44))
        features.append(item)
    data["features"] = features
    return EvaluateTreeRequest.model_validate(data)


def test_moto_frame_head_on_a_25deg_plane_extruded_symmetric_matches_the_golden() -> (
    None
):
    expected = _expected(FRAME)
    tolerance = expected["tolerance"]
    evaluation = evaluate_tree(_frame_with_angled_head())
    assert all(r.status == "ok" for r in evaluation.result.features), [
        (r.feature_id, r.error) for r in evaluation.result.features if r.status != "ok"
    ]
    assert evaluation.body is not None
    props = measure_shape(evaluation.body)
    assert props.volume == pytest.approx(
        expected["properties"]["volume"], abs=tolerance
    )
    for axis in ("x", "z"):
        assert getattr(props.centroid, axis) == pytest.approx(
            expected["properties"]["centroid"][axis], abs=tolerance
        )
    # The two-way difference is taken against the golden's own derivation, the
    # independent build123d frame (test_moto_frame.py), whose head is a hollow
    # Solid.make_cylinder. Not against the golden TREE: its head is a revolve,
    # and OCCT's cut between a revolved and an extruded copy of the same tube
    # (coincident faces on different surface types) returns 2.07e6 mm^3 in 9
    # solids one way and runs out of memory the other.
    twin, _ = _independent_frame()
    assert float(evaluation.body.cut(twin).volume) <= tolerance
    assert float(twin.cut(evaluation.body).volume) <= tolerance


# --- the kernel math, by hand --------------------------------------------------


def _close(a: Vector, b: tuple[float, float, float]) -> None:
    assert (a - Vector(*b)).length == pytest.approx(0.0, abs=1e-12)


def test_angle_zero_is_parallel_through_the_line() -> None:
    plane = plane_at_angle(Vector(5, 3, 7), Vector(0, 2, 0), Plane.XY, 0.0, False)
    _close(plane.z_dir, (0, 0, 1))
    _close(plane.x_dir, (0, 1, 0))
    # The point of the line nearest the world origin.
    _close(plane.origin, (5, 0, 7))


def test_positive_angle_turns_right_handed_about_the_line() -> None:
    # About +X, +Z turns towards -Y (right hand: Y -> Z -> -Y).
    s, c = math.sin(math.radians(30)), math.cos(math.radians(30))
    plane = plane_at_angle(Vector(0, 0, 0), Vector(1, 0, 0), Plane.XY, 30.0, False)
    _close(plane.z_dir, (0, -s, c))
    plane = plane_at_angle(Vector(0, 0, 0), Vector(1, 0, 0), Plane.XY, 90.0, False)
    _close(plane.z_dir, (0, -1, 0))
    flipped = plane_at_angle(Vector(0, 0, 0), Vector(1, 0, 0), Plane.XY, 30.0, True)
    _close(flipped.z_dir, (0, s, -c))
    _close(flipped.x_dir, (1, 0, 0))


def test_a_line_off_the_reference_but_parallel_to_it_is_accepted() -> None:
    plane = plane_at_angle(Vector(0, 0, 40), Vector(0, 1, 0), Plane.XY, 90.0, False)
    _close(plane.z_dir, (1, 0, 0))
    _close(plane.origin, (0, 0, 40))


def test_a_line_crossing_the_reference_is_refused() -> None:
    with pytest.raises(DatumLineNotParallelError, match="crosses the reference"):
        plane_at_angle(Vector(0, 0, 0), Vector(1, 0, 1), Plane.XY, 10.0, False)


# --- follows its inputs; sick, never a crash -------------------------------------


def _box(width: float, *extra: dict[str, Any]) -> EvaluateTreeRequest:
    """A width x 20 x 10 box on XY, then *extra* features."""
    corners = [(0, 0), (width, 0), (width, 20), (0, 20)]
    rect = [
        {
            "id": f"r{i}",
            "kind": "line",
            "start": {"x": a[0], "y": a[1]},
            "end": {"x": b[0], "y": b[1]},
        }
        for i, (a, b) in enumerate(zip(corners, corners[1:] + corners[:1], strict=True))
    ]
    return EvaluateTreeRequest.model_validate(
        {
            "part_id": str(uuid.UUID(int=7)),
            "tree_version": 1,
            "features": [
                _sketch(_fid(1), XY, rect),
                _feature(
                    _fid(2),
                    "extrude",
                    {"profile": _on(_fid(1)), "distance_mm": 10.0, "operation": "add"},
                ),
                *extra,
            ],
        }
    )


def _picks(width: float) -> tuple[dict[str, Any], dict[str, Any]]:
    """The box's +X top edge (along Y at x = width, z = 10) and its top face,
    as the selection overlay hands them to a click: the pick side, with the
    history names a real pick stores (the input, never the code under test)."""
    overlay = evaluate_overlay(
        OverlayRequest.model_validate({"tree": _box(width).model_dump(mode="json")})
    )
    edges = [
        e.signature
        for e in overlay.edges
        if e.signature.curve == "line"
        and abs(e.signature.end_a.x - width) < 1e-9
        and abs(e.signature.end_b.x - width) < 1e-9
        and abs(e.signature.end_a.z - 10) < 1e-9
        and abs(e.signature.end_b.z - 10) < 1e-9
    ]
    faces = [
        f.signature
        for f in overlay.faces
        if f.signature is not None
        and abs(f.signature.normal.z - 1) < 1e-9
        and abs(f.signature.centroid.z - 10) < 1e-9
    ]
    assert len(edges) == 1 and len(faces) == 1
    assert edges[0].topo_name is not None and faces[0].topo_name is not None

    def ref(subshape: str, signature: Any) -> dict[str, Any]:
        return {
            "kind": "subshape",
            "feature_id": _fid(2),
            "subshape_type": subshape,
            "selector": {
                "selector_version": 1,
                "signature": signature.model_dump(mode="json", exclude_none=True),
            },
        }

    return ref("edge", edges[0]), ref("face", faces[0])


def _box_and_edge_tree(width: float, picked_at: float) -> EvaluateTreeRequest:
    """The box at *width*, and a plane at 30 deg from its top face about its +X
    top edge, both picked on the box at *picked_at* (an un-re-picked resize when
    the two differ)."""
    edge, top = _picks(picked_at)
    return _box(width, _angle(_fid(3), edge, top, 30.0))


def _plane(request: EvaluateTreeRequest, fid: int) -> Plane:
    evaluation = evaluate_tree(request)
    plane = evaluation.datum_planes.get(uuid.UUID(_fid(fid)))
    assert plane is not None, [
        (r.feature_id, r.error) for r in evaluation.result.features
    ]
    return plane


def _error(request: EvaluateTreeRequest, fid: int) -> str:
    evaluation = evaluate_tree(request)
    result = next(
        r for r in evaluation.result.features if r.feature_id == uuid.UUID(_fid(fid))
    )
    assert result.status == "error" and result.error is not None
    return result.error.code


def test_the_plane_follows_a_resized_body_edge() -> None:
    # The edge runs +Y (end_a -> end_b); +Z turned 30 deg about +Y leans to +X.
    s, c = math.sin(math.radians(30)), math.cos(math.radians(30))
    plane = _plane(_box_and_edge_tree(40.0, 40.0), 3)
    _close(plane.z_dir, (s, 0, c))
    _close(plane.origin, (40, 0, 10))
    # Resize to 55 with nothing re-picked: the stored picks still say x = 40;
    # their history names re-find the edge and the face, and the plane follows.
    plane = _plane(_box_and_edge_tree(55.0, 40.0), 3)
    _close(plane.origin, (55, 0, 10))
    _close(plane.z_dir, (s, 0, c))


def test_the_plane_follows_an_edited_sketch_line_and_a_turned_reference() -> None:
    def tree(line_x: float) -> EvaluateTreeRequest:
        return EvaluateTreeRequest.model_validate(
            {
                "part_id": str(uuid.UUID(int=8)),
                "tree_version": 1,
                "features": [
                    _sketch(_fid(1), XY, [_line("l", (line_x, 0.0), (line_x, 5.0))]),
                    _angle(_fid(3), _sketch_line(_fid(1), "l"), XY, 20.0),
                ],
            }
        )

    a = _plane(tree(12.0), 3)
    b = _plane(tree(30.0), 3)
    _close(a.origin, (12, 0, 0))
    _close(b.origin, (30, 0, 0))
    _close(b.z_dir, (math.sin(math.radians(20)), 0, math.cos(math.radians(20))))
    # A reference datum that turns: the plane at 0 deg from an angled reference
    # turns with it.
    req = EvaluateTreeRequest.model_validate(
        {
            "part_id": str(uuid.UUID(int=9)),
            "tree_version": 1,
            "features": [
                _sketch(_fid(1), XY, [_line("l", (0.0, 0.0), (5.0, 0.0))]),
                _angle(_fid(2), {"kind": "origin_axis", "axis": "X"}, XY, 40.0),
                _angle(_fid(3), _sketch_line(_fid(1), "l"), _on(_fid(2)), 0.0),
            ],
        }
    )
    ref = _plane(req, 2)
    plane = _plane(req, 3)
    _close(plane.z_dir, (ref.z_dir.X, ref.z_dir.Y, ref.z_dir.Z))


def test_lost_references_leave_a_typed_sick_datum() -> None:
    base = _box_and_edge_tree(40.0, 40.0)
    # The edge is gone: an edge with no name, nowhere on the box.
    data = base.model_dump(mode="json")
    signature = data["features"][2]["feature"]["params"]["line"]["selector"][
        "signature"
    ]
    signature.pop("topo_name", None)
    signature.pop("adjacent_faces", None)
    signature.pop("end_a_topo_name", None)
    signature["end_a"] = {"x": 999.0, "y": 0.0, "z": 10.0}
    signature["end_b"] = {"x": 999.0, "y": 20.0, "z": 10.0}
    signature["midpoint"] = {"x": 999.0, "y": 10.0, "z": 10.0}
    assert _error(EvaluateTreeRequest.model_validate(data), 3) == "subshape_unresolved"

    # The sketch is missing (deleted/suppressed upstream) and the entity is gone.
    lone = EvaluateTreeRequest.model_validate(
        {
            "part_id": str(uuid.UUID(int=10)),
            "tree_version": 1,
            "features": [
                _angle(_fid(3), _sketch_line(_fid(1), "l"), XY, 10.0),
                _sketch(_fid(4), _on(_fid(3)), [_circle("c", 0, 0, 5)]),
            ],
        }
    )
    results = {r.feature_id: r for r in evaluate_tree(lone).result.features}
    sick = results[uuid.UUID(_fid(3))]
    assert sick.status == "error" and sick.error is not None
    assert sick.error.code == "reference_unresolved"
    assert sick.error.upstream_feature_id == uuid.UUID(_fid(1))
    # The sketch on it does not build on a plane that is not there.
    assert results[uuid.UUID(_fid(4))].status != "ok"

    def one(
        entities: list[Any], line_entity: str, reference: dict[str, Any] = XY
    ) -> str:
        return _error(
            EvaluateTreeRequest.model_validate(
                {
                    "part_id": str(uuid.UUID(int=11)),
                    "tree_version": 1,
                    "features": [
                        _sketch(_fid(1), XY, entities),
                        _angle(
                            _fid(3), _sketch_line(_fid(1), line_entity), reference, 10.0
                        ),
                    ],
                }
            ),
            3,
        )

    assert one([_line("l", (0, 0), (5, 0))], "gone") == "reference_unresolved"
    assert one([_circle("c", 0, 0, 5)], "c") == "datum_line_invalid"
    # A line along Y pierces XZ (whose normal is -Y): no angle from it.
    assert (
        one([_line("l", (0, 0), (0, 5))], "l", {"kind": "datum_plane", "plane": "XZ"})
        == "datum_line_not_parallel"
    )


# --- the wire ----------------------------------------------------------------------


def test_references_materialise_and_bad_angles_are_422() -> None:
    feature = DatumFeature.model_validate(
        {
            "type": "datum",
            "version": 1,
            "params": {
                "kind": "angle",
                "line": _sketch_line(_fid(1), "l"),
                "reference": _on(_fid(2)),
                "angle_deg": 25.0,
            },
        }
    )
    slots = {
        (r.slot, str(r.ref.feature_id), tuple(sorted(r.allowed_types)))
        for r in feature_references(feature)
    }
    assert slots == {("line", _fid(1), ("sketch",)), ("reference", _fid(2), ("datum",))}
    assert feature.params.model_dump()["flip"] is False
    for bad in (float("nan"), 360.5, -400.0):
        with pytest.raises(ValidationError):
            DatumFeature.model_validate(
                {
                    "type": "datum",
                    "version": 1,
                    "params": {
                        "kind": "angle",
                        "line": {"kind": "origin_axis", "axis": "X"},
                        "reference": XY,
                        "angle_deg": bad,
                    },
                }
            )


@pytest.mark.parametrize(
    "params",
    [
        {"base": "XZ", "offset_mm": -110.0, "flip": False},
        {"kind": "offset_from", "base": _on(_fid(1)), "offset_mm": 3.0, "flip": True},
        {"kind": "midplane", "a": XY, "b": _on(_fid(1)), "flip": False},
    ],
)
def test_stored_datums_of_older_kinds_dump_byte_identically(
    params: dict[str, Any],
) -> None:
    feature = DatumFeature.model_validate(
        {"type": "datum", "version": 1, "params": params}
    )
    dumped = feature.model_dump(mode="json")["params"]
    expected = {"kind": "offset", **params} if "kind" not in params else params
    assert json.dumps(dumped, sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_head_golden_matches_an_independent_build123d_tube() -> None:
    """The golden's annulus vs a hollow ``Solid.make_cylinder`` on a plane whose
    normal is the raked axis (no datum, no sketch, no extrude)."""
    expected = _expected(HEAD_GOLDEN)
    tolerance = expected["tolerance"]
    evaluation = evaluate_tree(_request(HEAD_GOLDEN))
    assert evaluation.body is not None
    rake = math.radians(25.0)
    axis = Vector(-math.sin(rake), 0, math.cos(rake))
    base = Vector(APEX_X, 0, APEX_Z) - axis * 80.0
    plane = Plane(origin=base, z_dir=axis)
    tube = Solid.make_cylinder(25.0, 160.0, plane).cut(
        Solid.make_cylinder(16.0, 160.0, plane)
    )
    mine = measure_shape(evaluation.body).volume
    theirs = measure_shape(tube).volume
    assert mine == pytest.approx(theirs, abs=tolerance)
    assert expected["properties"]["volume"] == pytest.approx(theirs, abs=tolerance)
    assert float(evaluation.body.cut(tube).volume) <= tolerance
    assert float(tube.cut(evaluation.body).volume) <= tolerance
