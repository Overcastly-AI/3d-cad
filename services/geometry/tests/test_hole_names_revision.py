"""A chamfer or fillet on a Hole's edge follows a hole resize, through the
Hole's history names (DESIGN-INTENT-REFS, RESEARCH §14).

THE PROBLEM. EDGE-REF-CONCENTRIC made the geometric tiers keep a circle's
radius, so a picked edge never re-anchors onto a concentric edge of another
size. A resized hole's rim IS another size, so with no names a chamfered rim
failed ``subshape_unresolved`` on the first diameter edit. Fusion 360 keeps it:
the chamfer is on "the edge where Hole1's wall meets the top face", whatever
the diameter.

THE FIX. The Hole names every face it cuts by its ROLE,
``<hole id>:hole:<instance>:<role>`` (``wall``, ``floor``, ``cbore_wall``,
``cbore_floor``, ``csink_cone``); a role is a function of the hole TYPE, never
of a size. An edge is named by its two faces, so the rim keeps its name through
the resize and the named tier finds it at the new radius. A different role's
edge (the counterbore's outer floor edge) keeps a different name, and the
radius guard still refuses it.

Each case: the revised body equals a FRESH pick at the new size (GLB bytes and
mass properties), agrees with a hand-derived closed form, and the same tree
with the names stripped (a selector persisted before this change, or an
imported body) still refuses, typed.

Closed forms used (``V`` the material a blend removes, by Pappus):

* chamfer d on a circular edge of radius R whose material lies OUTSIDE the
  circle (a bore's rim): triangle ``d^2/2`` at centroid radius ``R + d/3``,
  ``V = d^2/2 * 2*pi*(R + d/3)``;
* fillet f on the countersink rim (135 deg of material between the top face
  and the 90 deg cone): the spandrel, a kite minus a sector, computed below.
"""

import copy
import hashlib
import math
import uuid
from typing import Any

import pytest
from geometry.features import evaluate_tree
from geometry.features.evaluate import reset_rebuild_cache
from geometry.harness import evaluate_model
from geometry.kernel.edges import _circle_centre  # pyright: ignore[reportPrivateUsage]
from geometry.kernel.faces import face_signature_dto
from geometry.overlay import evaluate_overlay
from loft_wire.features import EvaluateTreeRequest
from loft_wire.overlay import OverlayRequest
from loft_wire.signatures import EdgeSignature

PART = uuid.UUID(int=0xA0E1)
SK, EX, HOLE, PICK = (uuid.UUID(int=0xA0E100 + i) for i in range(1, 5))
W, DEP, H = 40.0, 25.0, 10.0
CENTRE = (20.0, 12.5)
D = 0.5  # chamfer distance / fillet radius
CBORE_D, CBORE_DEPTH = 18.0, 4.0

#: Prisms, right cylinders and cones integrate exactly in GProp; the measured
#: residuals below are ~1e-12 relative.
REL = 1e-9


def _request(features: list[dict[str, Any]], version: int = 1) -> dict[str, Any]:
    return {
        "part_id": str(PART),
        "tree_version": version,
        "features": features,
        "linear_deflection": 0.1,
    }


def _eval(features: list[dict[str, Any]], version: int = 1) -> Any:
    return evaluate_tree(
        EvaluateTreeRequest.model_validate(_request(features, version))
    )


def _artifact(features: list[dict[str, Any]]) -> tuple[str, Any]:
    blob, meta = evaluate_model(EvaluateTreeRequest.model_validate(_request(features)))
    return hashlib.sha256(blob).hexdigest(), meta


def _plate() -> list[dict[str, Any]]:
    pts = [(0.0, 0.0), (W, 0.0), (W, DEP), (0.0, DEP)]
    sketch = {
        "id": str(SK),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": [
                    {
                        "id": f"e{i + 1}",
                        "kind": "line",
                        "start": {"x": pts[i][0], "y": pts[i][1]},
                        "end": {"x": pts[(i + 1) % 4][0], "y": pts[(i + 1) % 4][1]},
                    }
                    for i in range(4)
                ],
                "constraints": [],
            },
        },
    }
    extrude = {
        "id": str(EX),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(SK)},
                "distance_mm": H,
                "operation": "add",
                "direction": "normal",
            },
        },
    }
    return [sketch, extrude]


def _ref(owner: uuid.UUID, kind: str, sig: Any) -> dict[str, Any]:
    return {
        "kind": "subshape",
        "feature_id": str(owner),
        "subshape_type": kind,
        "selector": {"selector_version": 1, "signature": sig.model_dump(mode="json")},
    }


def _top_face_ref(plate: list[dict[str, Any]]) -> dict[str, Any]:
    for face in _eval(plate).body.faces():
        sig = face_signature_dto(face)
        if sig and sig.normal.z > 0.99 and abs(sig.centroid.z - H) < 1e-6:
            return _ref(EX, "face", sig)
    raise AssertionError("no top face")


def _hole(dia: float, kind: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(HOLE),
        "feature": {
            "type": "hole",
            "version": 1,
            "params": {
                "face": _top_face_ref(_plate()),
                "position": {"x": CENTRE[0], "y": CENTRE[1], "z": H},
                "diameter_mm": dia,
                "depth": {"kind": "through_all"},
                "type": kind,
            },
        },
    }


def _simple(dia: float) -> dict[str, Any]:
    return _hole(dia, {"kind": "simple"})


def _counterbore(dia: float) -> dict[str, Any]:
    return _hole(
        dia,
        {
            "kind": "counterbore",
            "cbore_diameter_mm": CBORE_D,
            "cbore_depth_mm": CBORE_DEPTH,
        },
    )


def _countersink(csink_dia: float) -> dict[str, Any]:
    return _hole(
        10.0,
        {"kind": "countersink", "csink_diameter_mm": csink_dia, "csink_angle_deg": 90},
    )


def _on_edge(kind: str, sig: EdgeSignature) -> dict[str, Any]:
    size = {"fillet": "radius_mm", "chamfer": "distance_mm"}[kind]
    return {
        "id": str(PICK),
        "feature": {
            "type": kind,
            "version": 1,
            "params": {
                "edges": {"kind": "edges", "refs": [_ref(HOLE, "edge", sig)]},
                size: D,
            },
        },
    }


def _radius(sig: EdgeSignature) -> float:
    centre = _circle_centre(sig)
    assert centre is not None
    m = sig.midpoint
    return math.dist(centre, (m.x, m.y, m.z))


def _circle(features: list[dict[str, Any]], z: float, radius: float) -> EdgeSignature:
    """The overlay's signature of the circle at height *z* and *radius*: the
    pick exactly as the product captures it (with its ``topo_name``)."""
    overlay = evaluate_overlay(
        OverlayRequest.model_validate({"tree": _request(features)})
    )
    (sig,) = [
        e.signature
        for e in overlay.edges
        if e.signature.curve == "circle"
        and abs((_circle_centre(e.signature) or (0, 0, 1e9))[2] - z) < 1e-6
        and _radius(e.signature) == pytest.approx(radius, abs=1e-9)
    ]
    return sig


def _unnamed(sig: EdgeSignature) -> EdgeSignature:
    return sig.model_copy(
        update={"topo_name": None, "end_a_topo_name": None, "end_b_topo_name": None}
    )


def _pick_result(evaluation: Any) -> Any:
    (result,) = [r for r in evaluation.result.features if r.feature_id == PICK]
    return result


def _outcome(evaluation: Any) -> tuple[str, str | None]:
    result = _pick_result(evaluation)
    return result.status, result.error.code if result.error else None


def _tier(evaluation: Any) -> str | None:
    summary = _pick_result(evaluation).subshape_resolution
    return None if summary is None else summary.worst_tier


def _ring_chamfer(radius: float) -> float:
    return D * D / 2 * 2 * math.pi * (radius + D / 3)


def _csink_rim_fillet(rim_radius: float) -> float:
    """Pappus on the fillet's spandrel at the countersink rim.

    In the (rho, z) half-plane the corner is (R, 0); the top face runs +rho
    from it and the 90 deg cone runs down and in, (-1, -1)/sqrt2, so the
    material angle is alpha = 135 deg. The fillet circle is tangent to both at
    t = f*cot(alpha/2) from the corner; the spandrel is the kite (corner,
    tangent points, centre) less the sector of angle pi - alpha."""
    f, alpha = D, math.radians(135.0)
    corner = (rim_radius, 0.0)
    u1, u2 = (1.0, 0.0), (-1 / math.sqrt(2), -1 / math.sqrt(2))
    bis = (u1[0] + u2[0], u1[1] + u2[1])
    norm = math.hypot(*bis)
    bis = (bis[0] / norm, bis[1] / norm)
    t = f / math.tan(alpha / 2)
    centre = (
        corner[0] + bis[0] * f / math.sin(alpha / 2),
        corner[1] + bis[1] * f / math.sin(alpha / 2),
    )
    t1 = (corner[0] + u1[0] * t, corner[1] + u1[1] * t)
    t2 = (corner[0] + u2[0] * t, corner[1] + u2[1] * t)
    kite_area = f * t
    kite_rho = ((corner[0] + t1[0] + centre[0]) + (corner[0] + t2[0] + centre[0])) / 6
    half = (math.pi - alpha) / 2
    sector_area = f * f * half
    sector_rho = centre[0] - bis[0] * 2 * f * math.sin(half) / (3 * half)
    area = kite_area - sector_area
    rho = (kite_area * kite_rho - sector_area * sector_rho) / area
    return 2 * math.pi * rho * area


def _plate_volume() -> float:
    return W * DEP * H


def _assert_same_as_fresh_pick(
    revised: list[dict[str, Any]], fresh: list[dict[str, Any]]
) -> Any:
    revised_hash, revised_meta = _artifact(revised)
    fresh_hash, fresh_meta = _artifact(fresh)
    assert revised_hash == fresh_hash
    assert revised_meta.properties == fresh_meta.properties
    assert revised_meta.mesh == fresh_meta.mesh
    return revised_meta


# --- the simple hole: a rim chamfer through dia 10 -> 12 ----------------------------


def test_a_rim_chamfer_follows_a_simple_hole_resize_and_equals_a_fresh_pick() -> None:
    plate = _plate()
    authored = [*plate, _simple(10.0)]
    picked = _circle(authored, H, 5.0)
    assert picked.topo_name is not None
    assert f"{HOLE}:hole:0:wall" in picked.topo_name
    assert f"{EX}:end" in picked.topo_name
    assert _outcome(_eval([*authored, _on_edge("chamfer", picked)])) == ("ok", None)

    revised = [*plate, _simple(12.0), _on_edge("chamfer", picked)]
    evaluation = _eval(revised)
    assert _outcome(evaluation) == ("ok", None)
    assert _tier(evaluation) == "named"
    fresh_pick = _circle([*plate, _simple(12.0)], H, 6.0)
    assert fresh_pick.topo_name == picked.topo_name
    meta = _assert_same_as_fresh_pick(
        revised, [*plate, _simple(12.0), _on_edge("chamfer", fresh_pick)]
    )
    want = _plate_volume() - math.pi * 36 * H - _ring_chamfer(6.0)
    assert meta.properties.volume == pytest.approx(want, rel=REL)


def test_a_rim_chamfer_without_names_refuses_the_resize() -> None:
    plate = _plate()
    picked = _unnamed(_circle([*plate, _simple(10.0)], H, 5.0))
    assert _outcome(_eval([*plate, _simple(10.0), _on_edge("chamfer", picked)])) == (
        "ok",
        None,
    )
    assert _outcome(_eval([*plate, _simple(12.0), _on_edge("chamfer", picked)])) == (
        "error",
        "subshape_unresolved",
    )


# --- the counterbore: the inner floor edge through a bore resize --------------------


def _cbore_volume(bore_r: float) -> float:
    r_cb = CBORE_D / 2
    return (
        _plate_volume()
        - math.pi * r_cb**2 * CBORE_DEPTH
        - math.pi * bore_r**2 * (H - CBORE_DEPTH)
    )


def test_a_counterbore_floor_edge_chamfer_follows_a_bore_resize() -> None:
    """The bore's top edge (cbore floor against the bore wall, R5 at z=6)
    follows the bore to R6. The counterbore's OUTER floor edge (cbore floor
    against cbore wall, R9 at the same height and centre) is a different role,
    so it is never the landing edge: the named tier picks R6."""
    plate = _plate()
    floor_z = H - CBORE_DEPTH
    picked = _circle([*plate, _counterbore(10.0)], floor_z, 5.0)
    assert picked.topo_name is not None
    assert f"{HOLE}:hole:0:cbore_floor" in picked.topo_name
    assert f"{HOLE}:hole:0:wall" in picked.topo_name
    outer = _circle([*plate, _counterbore(12.0)], floor_z, CBORE_D / 2)
    assert outer.topo_name is not None and outer.topo_name != picked.topo_name

    revised = [*plate, _counterbore(12.0), _on_edge("chamfer", picked)]
    evaluation = _eval(revised)
    assert _outcome(evaluation) == ("ok", None)
    assert _tier(evaluation) == "named"
    fresh_pick = _circle([*plate, _counterbore(12.0)], floor_z, 6.0)
    meta = _assert_same_as_fresh_pick(
        revised, [*plate, _counterbore(12.0), _on_edge("chamfer", fresh_pick)]
    )
    want = _cbore_volume(6.0) - _ring_chamfer(6.0)
    assert meta.properties.volume == pytest.approx(want, rel=REL)


def test_a_counterbore_floor_edge_chamfer_without_names_refuses_the_resize() -> None:
    plate = _plate()
    floor_z = H - CBORE_DEPTH
    picked = _unnamed(_circle([*plate, _counterbore(10.0)], floor_z, 5.0))
    assert _outcome(
        _eval([*plate, _counterbore(10.0), _on_edge("chamfer", picked)])
    ) == ("ok", None)
    assert _outcome(
        _eval([*plate, _counterbore(12.0), _on_edge("chamfer", picked)])
    ) == ("error", "subshape_unresolved")


def test_a_counterbore_retyped_to_a_pocket_removes_the_role_and_refuses() -> None:
    """Converting the hole to an Ø18 x 4 blind simple hole removes the
    ``cbore_floor`` role, so the named bore-top edge is gone, typed."""
    plate = _plate()
    picked = _circle([*plate, _counterbore(10.0)], H - CBORE_DEPTH, 5.0)
    pocket = _hole(CBORE_D, {"kind": "simple"})
    pocket["feature"]["params"]["depth"] = {"kind": "blind", "depth_mm": CBORE_DEPTH}
    assert _outcome(_eval([*plate, pocket, _on_edge("chamfer", picked)])) == (
        "error",
        "subshape_unresolved",
    )


# --- the countersink: a rim fillet through a mouth resize ---------------------------


def _csink_volume(mouth_r: float) -> float:
    bore_r = 5.0
    h = mouth_r - bore_r  # 90 deg included angle
    frustum_annulus = math.pi * h / 3 * (mouth_r**2 + mouth_r * bore_r - 2 * bore_r**2)
    return _plate_volume() - math.pi * bore_r**2 * H - frustum_annulus


def test_a_countersink_rim_fillet_follows_a_mouth_resize() -> None:
    plate = _plate()
    picked = _circle([*plate, _countersink(16.0)], H, 8.0)
    assert picked.topo_name is not None
    assert f"{HOLE}:hole:0:csink_cone" in picked.topo_name

    revised = [*plate, _countersink(18.0), _on_edge("fillet", picked)]
    evaluation = _eval(revised)
    assert _outcome(evaluation) == ("ok", None)
    assert _tier(evaluation) == "named"
    fresh_pick = _circle([*plate, _countersink(18.0)], H, 9.0)
    meta = _assert_same_as_fresh_pick(
        revised, [*plate, _countersink(18.0), _on_edge("fillet", fresh_pick)]
    )
    want = _csink_volume(9.0) - _csink_rim_fillet(9.0)
    assert meta.properties.volume == pytest.approx(want, rel=REL)


def test_a_countersink_rim_fillet_without_names_refuses_the_resize() -> None:
    plate = _plate()
    picked = _unnamed(_circle([*plate, _countersink(16.0)], H, 8.0))
    assert _outcome(
        _eval([*plate, _countersink(16.0), _on_edge("fillet", picked)])
    ) == (
        "ok",
        None,
    )
    assert _outcome(
        _eval([*plate, _countersink(18.0), _on_edge("fillet", picked)])
    ) == (
        "error",
        "subshape_unresolved",
    )


# --- every role, every type; determinism -------------------------------------------


def _hole_names(evaluation: Any) -> list[str]:
    prefix = f"{HOLE}:hole:0:"
    return sorted(
        str(n)[len(prefix) :]
        for n in evaluation.face_names()
        if n is not None and str(n).startswith(prefix)
    )


@pytest.mark.parametrize(
    ("hole", "roles"),
    [
        (lambda: _simple(10.0), ["wall"]),
        (lambda: _blind(_simple(10.0)), ["floor", "wall"]),
        (lambda: _counterbore(10.0), ["cbore_floor", "cbore_wall", "wall"]),
        (
            lambda: _blind(_counterbore(10.0)),
            ["cbore_floor", "cbore_wall", "floor", "wall"],
        ),
        (lambda: _countersink(16.0), ["csink_cone", "wall"]),
        (lambda: _tapped(), ["wall"]),
    ],
    ids=[
        "simple",
        "blind",
        "counterbore",
        "blind-counterbore",
        "countersink",
        "tapped",
    ],
)
def test_every_face_a_hole_cuts_is_named_by_its_role(
    hole: Any, roles: list[str]
) -> None:
    evaluation = _eval([*_plate(), hole()])
    assert _hole_names(evaluation) == roles
    names = [n for n in evaluation.face_names() if n is not None]
    assert len(names) == len(set(names)), "no name is held twice"
    # Every face of the drilled plate is named: the six plate faces keep theirs.
    assert all(n is not None for n in evaluation.face_names())


def _blind(hole: dict[str, Any]) -> dict[str, Any]:
    blind = copy.deepcopy(hole)
    blind["feature"]["params"]["depth"] = {"kind": "blind", "depth_mm": 6.0}
    return blind


def _tapped() -> dict[str, Any]:
    tapped = _simple(8.5)
    tapped["feature"]["params"]["thread"] = {
        "standard": "iso_metric",
        "nominal_diameter_mm": 10.0,
        "pitch_mm": 1.5,
    }
    return tapped


def _tree() -> list[dict[str, Any]]:
    plate = _plate()
    picked = _circle([*plate, _counterbore(10.0)], H - CBORE_DEPTH, 5.0)
    return [*plate, _counterbore(12.0), _on_edge("chamfer", picked)]


def test_hole_names_are_identical_across_two_cold_rebuilds_and_a_resumed_one() -> None:
    tree = _tree()
    reset_rebuild_cache()
    cold = _eval(tree, 11).face_names()
    reset_rebuild_cache()
    again = _eval(tree, 12).face_names()
    assert cold == again
    assert sum(n is not None for n in cold) == len(cold)
    reset_rebuild_cache()
    prefix = _eval(tree[:3], 13)
    del prefix  # releases the checkpoint for the next rebuild to resume
    resumed = _eval(tree, 14)
    assert resumed.face_names() == cold
    assert _eval(tree, 15).face_names() == cold  # a frontier hit
