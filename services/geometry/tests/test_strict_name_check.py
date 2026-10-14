"""A strict geometric hit must agree with the stored name (BACKLOG
JOINT-STRICT-WRONG-HOLE, RESEARCH §14 and §21).

The defect: the strict tier of the shared picked-reference resolvers matched by
geometry alone. On a bolt-pattern plate (holes h1 / h2 / h3 at x 20 / 50 / 80,
h2 picked), moving h2 to x = 35 and adding a hole h9 at x = 50, or swapping h1
into h2's spot, left ANOTHER hole exactly where the picked one was, and the
reference landed on it with tier ``exact``: a joint seated on the wrong hole, a
chamfer cut on the wrong rim, no error. Fusion 360 follows the picked hole
(its history name) or fails the reference.

The fix: a strict hit the body names differently from a NAMED reference is
dropped; the tiers below then find the picked subshape by its name, or nothing.
A reference without a name (legacy, imported) resolves as before. One fix in the
shared resolvers, so features and assemblies are both covered here.

Hand-checked numbers: the plate is 100 x 30 x 10 with r4 holes at y = 15. A
circle rim's signature midpoint is its parameter-mid point, (x - 4, 15, z) for
a hole centred at x. The pin is r4 x 20; joint 1 puts its bottom-cap centre
(local origin) on the hole's bottom-rim centre (x, 15, 0), identity rotation
(RESEARCH §21: opposed Z after the pin's flip, aligned X), so the pin's
translation IS the hole centre.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
import pytest
from build123d import CenterOf, GeomType
from geometry.assembly import evaluate_assembly
from geometry.assembly.transform import Pose
from geometry.features import evaluate_tree
from geometry.kernel.edges import (
    edge_name_agreement,
    edge_names_agree,
    resolve_edge_durable,
)
from geometry.kernel.faces import (
    SubshapeUnresolvedError,
    match_face_records_tiered,
    planar_faces,
    resolve_face_plane,
    resolve_faces,
)
from geometry.kernel.naming import FaceName, edge_name
from geometry.kernel.overlay import selection_overlay
from loft_wire.assemblies import EvaluateAssemblyRequest, EvaluateAssemblyResult
from loft_wire.features import EdgeSignature, EvaluateTreeRequest
from loft_wire.joints import JointMate, JointOrigin, JointValue
from loft_wire.signatures import PlanarFaceSignature

_SKETCH = "00000000-0000-0000-0000-0000000000a1"
_EXTRUDE = "00000000-0000-0000-0000-0000000000b1"
_CHAMFER = "00000000-0000-0000-0000-0000000000c1"
_PLATE, _PIN, _JOINT = 1, 2, 1001
_TOL = 1e-9

Holes = list[tuple[str, float]]

#: The authored bolt pattern, and the two edits that leave another hole where
#: h2 was (the reviewer's repros), and a third that deletes h2 outright.
AUTHORED: Holes = [("h1", 20.0), ("h2", 50.0), ("h3", 80.0)]
MOVED_AND_ADDED: Holes = [("h1", 20.0), ("h2", 35.0), ("h3", 80.0), ("h9", 50.0)]
SWAPPED: Holes = [("h1", 50.0), ("h2", 20.0), ("h3", 80.0)]
H2_GONE: Holes = [("h1", 50.0), ("h3", 80.0)]


def iid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def _line(eid: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": a[0], "y": a[1]},
        "end": {"x": b[0], "y": b[1]},
    }


def _rect(
    prefix: str, x0: float, y0: float, x1: float, y1: float
) -> list[dict[str, Any]]:
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [
        _line(f"{prefix}{i + 1}", corners[i], corners[(i + 1) % 4]) for i in range(4)
    ]


def _prism(entities: list[dict[str, Any]], depth: float) -> list[dict[str, Any]]:
    return [
        {
            "id": _SKETCH,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "entities": entities,
                    "constraints": [],
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                },
            },
        },
        {
            "id": _EXTRUDE,
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": _SKETCH},
                    "distance_mm": depth,
                    "operation": "add",
                    "direction": "normal",
                    "merge": True,
                },
            },
        },
    ]


def plate(holes: Holes) -> list[dict[str, Any]]:
    """The 100 x 30 x 10 plate with r4 holes at (x, 15)."""
    entities = _rect("e", 0.0, 0.0, 100.0, 30.0)
    entities += [
        {"id": hid, "kind": "circle", "center": {"x": x, "y": 15.0}, "radius": 4.0}
        for hid, x in holes
    ]
    return _prism(entities, 10.0)


def pin() -> list[dict[str, Any]]:
    circle = {"id": "c1", "kind": "circle", "center": {"x": 0.0, "y": 0.0}}
    return _prism([{**circle, "radius": 4.0}], 20.0)


def _evaluate(features: list[dict[str, Any]]) -> Any:
    request = EvaluateTreeRequest.model_validate(
        {
            "part_id": str(iid(77)),
            "tree_version": 1,
            "features": features,
            "linear_deflection": 0.1,
        }
    )
    return evaluate_tree(request)


def _overlay(features: list[dict[str, Any]]) -> Any:
    evaluation = _evaluate(features)
    assert evaluation.body is not None
    return selection_overlay(evaluation.body, 0.1, None, evaluation.face_names())


def _rim(features: list[dict[str, Any]], hole: str, z: float) -> EdgeSignature:
    """The hole's rim at height *z*, picked as the web picks it (named)."""
    (sig,) = (
        e.signature
        for e in _overlay(features).edges
        if e.signature.curve == "circle"
        and e.signature.midpoint.z == z
        and e.signature.topo_name is not None
        and f":side:{hole}" in e.signature.topo_name
    )
    return sig


def _unnamed(sig: EdgeSignature) -> EdgeSignature:
    return sig.model_copy(
        update={"topo_name": None, "end_a_topo_name": None, "end_b_topo_name": None}
    )


def _resolve_rim(holes: Holes, signature: EdgeSignature) -> Any:
    evaluation = _evaluate(plate(holes))
    return resolve_edge_durable(
        evaluation.body, signature, face_names=evaluation.face_names()
    )


# --- the shared edge resolver ---------------------------------------------------


def test_the_authored_pick_is_strict_and_on_h2() -> None:
    picked = _rim(plate(AUTHORED), "h2", 10.0)
    resolved = _resolve_rim(AUTHORED, picked)
    assert resolved.tier == "exact"
    assert (resolved.signature.midpoint.x, resolved.signature.midpoint.y) == (
        46.0,
        15.0,
    )


@pytest.mark.parametrize(
    ("holes", "x"), [(MOVED_AND_ADDED, 35.0), (SWAPPED, 20.0)], ids=["h9", "swap"]
)
def test_a_named_rim_follows_h2_not_the_hole_in_its_old_place(
    holes: Holes, x: float
) -> None:
    picked = _rim(plate(AUTHORED), "h2", 10.0)
    resolved = _resolve_rim(holes, picked)
    assert resolved.tier == "named"
    mid = resolved.signature.midpoint
    assert (mid.x, mid.y, mid.z) == pytest.approx((x - 4.0, 15.0, 10.0), abs=_TOL)


def test_a_named_rim_is_unresolved_when_h2_is_gone_and_h1_took_its_place() -> None:
    picked = _rim(plate(AUTHORED), "h2", 10.0)
    with pytest.raises(SubshapeUnresolvedError):
        _resolve_rim(H2_GONE, picked)


def test_an_unnamed_rim_keeps_the_strict_geometric_answer() -> None:
    """Legacy: without a name there is no identity to check, so the strict
    tier answers by geometry alone, exactly as before the fix."""
    picked = _unnamed(_rim(plate(AUTHORED), "h2", 10.0))
    resolved = _resolve_rim(MOVED_AND_ADDED, picked)
    assert resolved.tier == "exact"
    assert resolved.signature.midpoint.x == pytest.approx(46.0, abs=_TOL)


# --- a feature: the chamfer on the picked rim -----------------------------------


def _chamfered(holes: Holes, picked: EdgeSignature) -> Any:
    chamfer = {
        "id": _CHAMFER,
        "feature": {
            "type": "chamfer",
            "version": 1,
            "params": {
                "edges": {
                    "kind": "edges",
                    "refs": [
                        {
                            "kind": "subshape",
                            "feature_id": _EXTRUDE,
                            "subshape_type": "edge",
                            "selector": {
                                "selector_version": 1,
                                "signature": picked.model_dump(mode="json"),
                            },
                        }
                    ],
                },
                "distance_mm": 0.5,
            },
        },
    }
    return _evaluate([*plate(holes), chamfer])


def _chamfer_result(evaluation: Any) -> Any:
    (result,) = (r for r in evaluation.result.features if str(r.feature_id) == _CHAMFER)
    return result


@pytest.mark.parametrize(
    ("holes", "x"), [(MOVED_AND_ADDED, 35.0), (SWAPPED, 20.0)], ids=["h9", "swap"]
)
def test_a_chamfer_on_h2s_rim_follows_h2(holes: Holes, x: float) -> None:
    picked = _rim(plate(AUTHORED), "h2", 10.0)
    evaluation = _chamfered(holes, picked)
    result = _chamfer_result(evaluation)
    assert result.status == "ok", result.error
    assert result.subshape_resolution.worst_tier == "named"
    (cone,) = (f for f in evaluation.body.faces() if f.geom_type == GeomType.CONE)
    centre = cone.center(CenterOf.BOUNDING_BOX)
    got = (centre.X, centre.Y)
    assert got == pytest.approx((x, 15.0), abs=1e-6)


def test_a_chamfer_on_h2s_rim_fails_when_h2_is_gone() -> None:
    picked = _rim(plate(AUTHORED), "h2", 10.0)
    result = _chamfer_result(_chamfered(H2_GONE, picked))
    assert result.status == "error"
    assert result.error.code == "subshape_unresolved"


# --- split faces: a changed qualifier is the same face --------------------------
#
# A 5 mm-deep underside cut through both ends at y 12..18 splits the plate's
# bottom face in two. Each piece is named "<base>/<digest of its neighbours>",
# so widening the cut or adding a hole changes the digest of the front piece,
# though the bottom-front edge, (0..100, 0, 0), never moves. The strict hit
# must stay exact (4fe3162 resolved it so; the first name check refused it).
# r2 fillet on a straight convex edge of length L removes (4 - pi) * L mm^3.

_CUT_SKETCH = "00000000-0000-0000-0000-0000000000d1"
_CUT = "00000000-0000-0000-0000-0000000000d2"
_FILLET = "00000000-0000-0000-0000-0000000000e1"
_FILLET_REMOVES = (4.0 - np.pi) * 100.0


def _undercut(y0: float, y1: float, prefix: str = "s") -> list[dict[str, Any]]:
    return [
        {
            "id": _CUT_SKETCH,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "entities": _rect(prefix, -10.0, y0, 110.0, y1),
                    "constraints": [],
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                },
            },
        },
        {
            "id": _CUT,
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": _CUT_SKETCH},
                    "distance_mm": 5.0,
                    "operation": "cut",
                    "direction": "normal",
                },
            },
        },
    ]


def _bottom_front(features: list[dict[str, Any]]) -> EdgeSignature:
    (sig,) = (
        e.signature
        for e in _overlay(features).edges
        if e.signature.curve == "line"
        and (e.signature.midpoint.x, e.signature.midpoint.y, e.signature.midpoint.z)
        == (50.0, 0.0, 0.0)
    )
    assert sig.topo_name is not None and "/" in sig.topo_name  # a split piece
    return sig


SPLIT_EDITS = {
    "slot-widened": plate(AUTHORED) + _undercut(11.0, 19.0),
    "hole-added": plate([*AUTHORED, ("h4", 65.0)]) + _undercut(12.0, 18.0),
}


@pytest.mark.parametrize("edit", sorted(SPLIT_EDITS))
def test_an_edge_on_a_split_face_stays_exact_when_its_neighbours_change(
    edit: str,
) -> None:
    picked = _bottom_front(plate(AUTHORED) + _undercut(12.0, 18.0))
    edited = SPLIT_EDITS[edit]
    evaluation = _evaluate(edited)
    resolved = resolve_edge_durable(
        evaluation.body, picked, face_names=evaluation.face_names()
    )
    assert resolved.tier == "exact"
    mid = resolved.signature.midpoint
    assert (mid.x, mid.y, mid.z) == (50.0, 0.0, 0.0)
    assert _bottom_front(edited).topo_name != picked.topo_name  # the drift
    fillet = {
        "id": _FILLET,
        "feature": {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {
                    "kind": "edges",
                    "refs": [
                        {
                            "kind": "subshape",
                            "feature_id": _EXTRUDE,
                            "subshape_type": "edge",
                            "selector": {
                                "selector_version": 1,
                                "signature": picked.model_dump(mode="json"),
                            },
                        }
                    ],
                },
                "radius_mm": 2.0,
            },
        },
    }
    filleted = _evaluate([*edited, fillet])
    (result,) = (r for r in filleted.result.features if str(r.feature_id) == _FILLET)
    assert result.status == "ok", result.error
    assert result.subshape_resolution.worst_tier == "exact"
    removed = evaluation.body.volume - filleted.body.volume
    assert removed == pytest.approx(_FILLET_REMOVES, rel=1e-7)


def test_a_split_face_piece_stays_exact_when_its_neighbours_are_renamed() -> None:
    """The face twin. Widening the cut or adding a hole also reshapes the
    bottom face's front piece (y 0..12), so its strict signature misses for a
    geometric reason. Redrawing the cut's rectangle (new sketch entity ids)
    renames only the piece's neighbour, the cut wall: same geometry, new
    qualifier."""

    def front_piece(features: list[dict[str, Any]]) -> PlanarFaceSignature:
        (sig,) = (
            f.signature
            for f in _overlay(features).faces
            if f.signature is not None
            and f.signature.normal.z < -0.99
            and f.signature.centroid.z == 0.0
            and f.signature.centroid.y < 10.0
        )
        return sig

    picked = front_piece(plate(AUTHORED) + _undercut(12.0, 18.0))
    assert picked.topo_name is not None and "/" in picked.topo_name
    redrawn = plate(AUTHORED) + _undercut(12.0, 18.0, prefix="t")
    assert front_piece(redrawn).topo_name != picked.topo_name  # the drift
    evaluation = _evaluate(redrawn)
    records = planar_faces(evaluation.body, evaluation.face_names())
    matches, tier = match_face_records_tiered(records, picked)
    assert tier == "exact"
    (match,) = matches
    assert match.signature.centroid == picked.centroid


# --- the shared face resolver ---------------------------------------------------


def slotted(slots: list[tuple[str, float]]) -> list[dict[str, Any]]:
    """A 100 x 30 x 10 plate with 10 x 10 square slots at x0..x0+10, y 10..20."""
    entities = _rect("e", 0.0, 0.0, 100.0, 30.0)
    for prefix, x0 in slots:
        entities += _rect(prefix, x0, 10.0, x0 + 10.0, 20.0)
    return _prism(entities, 10.0)


def _slot_wall(features: list[dict[str, Any]], name: str) -> PlanarFaceSignature:
    """The slot wall named *name* (line 4 is a slot's wall at x = x0), picked
    as the web picks it."""
    (sig,) = (
        f.signature
        for f in _overlay(features).faces
        if f.signature is not None and f.signature.topo_name == name
    )
    return sig


_A4 = f"{_EXTRUDE}:side:a4"


def test_a_named_slot_wall_follows_its_slot_through_a_swap() -> None:
    """Slots a (x 20..30) and b (x 60..70) swap places: b's wall now holds the
    picked wall's exact signature, and the name finds a's wall at x = 60."""
    picked = _slot_wall(slotted([("a", 20.0), ("b", 60.0)]), _A4)
    assert picked.centroid.x == pytest.approx(20.0, abs=_TOL)
    evaluation = _evaluate(slotted([("a", 60.0), ("b", 20.0)]))
    names = evaluation.face_names()
    (face,) = resolve_faces(evaluation.body, [picked], face_names=names)
    face_x = face.center().X
    assert face_x == pytest.approx(60.0, abs=_TOL)
    plane = resolve_face_plane(evaluation.body, picked, 0.0, face_names=names)
    origin_x = plane.origin.X
    assert origin_x == pytest.approx(60.0, abs=_TOL)
    # Legacy, unnamed: the strict tier still answers by geometry (b's wall).
    unnamed = picked.model_copy(update={"topo_name": None})
    (legacy,) = resolve_faces(evaluation.body, [unnamed], face_names=names)
    legacy_x = legacy.center().X
    assert legacy_x == pytest.approx(20.0, abs=_TOL)


def test_a_named_slot_wall_is_unresolved_when_its_slot_is_gone() -> None:
    picked = _slot_wall(slotted([("a", 20.0), ("b", 60.0)]), _A4)
    evaluation = _evaluate(slotted([("b", 20.0)]))
    with pytest.raises(SubshapeUnresolvedError):
        resolve_faces(evaluation.body, [picked], face_names=evaluation.face_names())


# --- an assembly joint seated on h2 ---------------------------------------------


def _joint_assembly(holes: Holes) -> EvaluateAssemblyRequest:
    rim = _rim(plate(AUTHORED), "h2", 0.0)
    (cap,) = (
        e.signature
        for e in _overlay(pin()).edges
        if e.signature.curve == "circle" and e.signature.midpoint.z == 0.0
    )
    joint = JointMate(
        motion="revolute",
        a=JointOrigin(instance_id=iid(_PLATE), kind="circle_centre", signature=rim),
        b=JointOrigin(
            instance_id=iid(_PIN), kind="circle_centre", signature=cap, flip=True
        ),
        value=JointValue(rot_deg=0.0),
    )

    def instance(n: int, key: str, features: Any, at: tuple[float, ...]) -> Any:
        return {
            "instance_id": str(iid(n)),
            "part_key": key,
            "features": features,
            "placement": {
                "position": dict(zip("xyz", at, strict=True)),
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            },
            "grounded": n == _PLATE,
        }

    key = "plate@" + ",".join(f"{h}:{x}" for h, x in holes)
    return EvaluateAssemblyRequest.model_validate(
        {
            "assembly_id": str(iid(0x42)),
            "version": 1,
            "instances": [
                instance(_PLATE, key, plate(holes), (0.0, 0.0, 0.0)),
                instance(_PIN, "pin@1", pin(), (0.0, -60.0, 0.0)),
            ],
            "mates": [
                {
                    "mate_id": str(iid(_JOINT)),
                    "order_index": 0,
                    "mate": joint.model_dump(),
                }
            ],
            "linear_deflection": 0.1,
        }
    )


def _pin_pose(result: EvaluateAssemblyResult) -> Pose:
    (inst,) = (i for i in result.instances if i.instance_id == iid(_PIN))
    return Pose.from_placement(inst.placement)


@pytest.mark.parametrize(
    ("holes", "x"),
    [(AUTHORED, 50.0), (MOVED_AND_ADDED, 35.0), (SWAPPED, 20.0)],
    ids=["authored", "h9", "swap"],
)
def test_the_joint_follows_h2(holes: Holes, x: float) -> None:
    result = evaluate_assembly(_joint_assembly(holes))
    assert result.mate_errors == []
    pose = _pin_pose(result)
    assert np.allclose(pose.t, [x, 15.0, 0.0], rtol=0.0, atol=_TOL)
    assert np.allclose(pose.matrix()[:3, :3], np.eye(3), rtol=0.0, atol=_TOL)


def test_the_joint_is_unresolved_when_h2_is_gone_and_h1_took_its_place() -> None:
    result = evaluate_assembly(_joint_assembly(H2_GONE))
    assert [(e.mate_id, e.error.code) for e in result.mate_errors] == [
        (iid(_JOINT), "subshape_unresolved")
    ]
    assert np.allclose(_pin_pose(result).t, [0.0, -60.0, 0.0], rtol=0.0, atol=_TOL)


def test_the_followed_joint_is_deterministic() -> None:
    first = evaluate_assembly(_joint_assembly(MOVED_AND_ADDED)).model_dump_json()
    again = evaluate_assembly(_joint_assembly(MOVED_AND_ADDED)).model_dump_json()
    assert again == first


# --- the shared edge-name comparison --------------------------------------------

_Q1, _Q2 = "/" + "a" * 32, "/" + "b" * 32


def test_edge_name_agreement_reads_faces_qualifiers_and_aliases() -> None:
    stored = edge_name("F:side:h2", "F:end")
    # Exact, either face order, string or face pair.
    assert edge_name_agreement(stored, stored) == "same"
    assert edge_name_agreement(("F:end", "F:side:h2"), stored) == "same"
    # Another hole's rim is another edge.
    h9 = edge_name("F:side:h9", "F:end")
    assert edge_name_agreement(h9, stored) == "different"
    # A split piece whose neighbours changed: only the qualifier differs.
    piece = edge_name("F:side:e1", "F:start" + _Q1)
    redigested = edge_name("F:side:e1", "F:start" + _Q2)
    assert edge_name_agreement(redigested, piece) == "split_drift"
    unsplit = edge_name("F:side:e1", "F:start")
    assert edge_name_agreement(unsplit, piece) == "split_drift"
    other = edge_name("F:side:e2", "F:start" + _Q1)
    assert edge_name_agreement(other, piece) == "different"
    # A face a clean merged the stored face into answers to it by alias.
    merged = FaceName("F:side:k", frozenset({"F:side:h2"}))
    assert edge_name_agreement((merged, "F:end"), stored) == "same"
    # A name that is not a face pair compares by equality.
    assert edge_name_agreement("legacy", "legacy") == "same"
    assert edge_name_agreement(("a", "b"), "legacy") == "different"


def test_edge_names_agree_is_the_boolean_guard() -> None:
    stored = edge_name("F:side:h2", "F:end")
    assert edge_names_agree(stored, stored)
    assert edge_names_agree(stored, ("F:end", "F:side:h2"))
    assert not edge_names_agree(stored, edge_name("F:side:h1", "F:end"))
    piece = edge_name("F:side:e1", "F:start" + _Q1)
    assert edge_names_agree(piece, edge_name("F:side:e1", "F:start" + _Q2))
    assert not edge_names_agree(piece, edge_name("F:side:e3", "F:start" + _Q1))
    merged = FaceName("F:side:k", frozenset({"F:side:h2"}))
    assert edge_names_agree(stored, (merged, "F:end"))
    assert not edge_names_agree(stored, ("F:side:k", "F:end"))  # no alias
