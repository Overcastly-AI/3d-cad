"""A picked edge whose own edge vanished must FAIL, typed, never re-anchor onto
a CONCENTRIC edge of another radius (BACKLOG EDGE-REF-CONCENTRIC, RESEARCH §14).

The defect: ``_match_edge_records`` tier 2 (``concentric_same_station_match``)
accepted any circle with the same centre and angular station, whatever its
radius, so when the picked R_a edge disappeared and a single R_b edge of the
same centre remained, a fillet / chamfer silently rounded the R_b edge (tier
``durable``, status ok). The fix, as in Fusion 360 (a fillet whose edge is gone
is an error): tiers 2-3 keep the circle's radius, and a geometric re-find of a
NAMED reference whose edge the body names differently is refused, for every
edge-ref consumer. Both rules are checked named and unnamed (an imported body
has no names), at the kernel, the fillet / chamfer and the projection level.

Each refusal test first proves the authored tree builds ok with the picked
edge, so only the refusal assertion can fail. Positive controls show the
legitimate re-finds still work: the same circle after a plate-size edit, a
NAMED rim following its resized bore (the named tier), and a straight edge
growing along its own line (the durable tier). Numbers derived by hand:

* chamfer d on a convex circular edge of radius R, material outside it: Pappus,
  triangle area ``d^2/2`` at centroid radius ``R + d/3``:
  ``V = d^2/2 * 2*pi*(R + d/3)``;
* chamfer d on a convex straight edge of length L: ``d^2/2 * L``;
* counterbored plate W x 25 x 10: ``250 W - pi*9^2*4 - pi*r^2*6`` (r the bore).
"""

import copy
import importlib.util
import math
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from geometry.features import evaluate_tree
from geometry.kernel import export_step_bytes
from geometry.kernel.edges import (
    _circle_centre,  # pyright: ignore[reportPrivateUsage]
    enumerate_edges_with_adjacency,
    resolve_edge_durable,
)
from geometry.kernel.faces import (
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    face_signature_dto,
)
from geometry.overlay import evaluate_overlay
from loft_wire.features import EvaluateTreeRequest, SolvedSketchData
from loft_wire.overlay import OverlayRequest
from loft_wire.signatures import EdgeSignature

SK, EX, FIL, SH, HOLE, PICK, IMP = (uuid.UUID(int=0xF100 + i) for i in range(1, 8))
PART = uuid.UUID(int=0xF1)
D = 0.5  # the chamfer / fillet size on the picked edge


def _request(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "part_id": str(PART),
        "tree_version": 1,
        "features": features,
        "linear_deflection": 0.1,
    }


def _eval(features: list[dict[str, Any]]) -> Any:
    return evaluate_tree(EvaluateTreeRequest.model_validate(_request(features)))


def _radius(sig: EdgeSignature) -> float:
    centre = _circle_centre(sig)
    assert centre is not None
    m = sig.midpoint
    return math.dist(centre, (m.x, m.y, m.z))


def _unnamed(sig: EdgeSignature) -> EdgeSignature:
    return sig.model_copy(
        update={"topo_name": None, "end_a_topo_name": None, "end_b_topo_name": None}
    )


def _rect(width: float, depth: float) -> dict[str, Any]:
    pts = [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)]
    return {
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


def _extrude(height: float) -> dict[str, Any]:
    return {
        "id": str(EX),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(SK)},
                "distance_mm": height,
                "operation": "add",
                "direction": "normal",
            },
        },
    }


def _ref(owner: uuid.UUID, kind: str, sig: Any) -> dict[str, Any]:
    return {
        "kind": "subshape",
        "feature_id": str(owner),
        "subshape_type": kind,
        "selector": {"selector_version": 1, "signature": sig.model_dump(mode="json")},
    }


def _top_face_ref(owner: uuid.UUID, features: list[dict[str, Any]], z: float) -> Any:
    evaluation = _eval(features)
    for face in evaluation.body.faces():
        sig = face_signature_dto(face)
        if sig and sig.normal.z > 0.99 and abs(sig.centroid.z - z) < 1e-6:
            return _ref(owner, "face", sig)
    raise AssertionError("no top face")


def _picked(features: list[dict[str, Any]]) -> list[EdgeSignature]:
    """The overlay's edge signatures: the pick side as the product runs it
    (each carries its ``topo_name`` where the body names the edge)."""
    overlay = evaluate_overlay(
        OverlayRequest.model_validate({"tree": _request(features)})
    )
    return [e.signature for e in overlay.edges]


def _circles_at(features: list[dict[str, Any]], z: float) -> list[EdgeSignature]:
    return [
        s
        for s in _picked(features)
        if s.curve == "circle" and abs((_circle_centre(s) or (0, 0, 1e9))[2] - z) < 1e-6
    ]


def _on_edge(kind: str, owner: uuid.UUID, sig: EdgeSignature) -> dict[str, Any]:
    size = {"fillet": "radius_mm", "chamfer": "distance_mm"}[kind]
    return {
        "id": str(PICK),
        "feature": {
            "type": kind,
            "version": 1,
            "params": {
                "edges": {"kind": "edges", "refs": [_ref(owner, "edge", sig)]},
                size: D,
            },
        },
    }


def _outcome(evaluation: Any) -> tuple[str, str | None]:
    (result,) = [r for r in evaluation.result.features if r.feature_id == PICK]
    return result.status, result.error.code if result.error else None


def _tier(evaluation: Any) -> str | None:
    (result,) = [r for r in evaluation.result.features if r.feature_id == PICK]
    summary = result.subshape_resolution
    return None if summary is None else summary.worst_tier


# --- case (a): the shelled R5 box, inner R3 rim arc ------------------------------


def _r5_box() -> list[dict[str, Any]]:
    return [
        _rect(40, 30),
        _extrude(20),
        {
            "id": str(FIL),
            "feature": {
                "type": "fillet",
                "version": 1,
                "params": {
                    "edges": {"kind": "axis_parallel", "axis": "Z"},
                    "radius_mm": 5.0,
                },
            },
        },
    ]


def _shell(base: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": str(SH),
        "feature": {
            "type": "shell",
            "version": 1,
            "params": {
                "thickness_mm": 2.0,
                "faces": {"kind": "faces", "refs": [_top_face_ref(FIL, base, 20)]},
            },
        },
    }


def _inner_rim_arc(features: list[dict[str, Any]]) -> EdgeSignature:
    inner = [s for s in _circles_at(features, 20) if _radius(s) == pytest.approx(3.0)]
    assert len(inner) == 4
    return min(inner, key=lambda s: (s.end_a.x, s.end_a.y))


def test_a_kernel_inner_rim_arc_is_unresolved_once_the_shell_is_deleted() -> None:
    base = _r5_box()
    picked = _unnamed(_inner_rim_arc([*base, _shell(base)]))
    # Only the R5 rim arcs remain at z = 20; the R3 arc is gone.
    with pytest.raises(SubshapeUnresolvedError):
        resolve_edge_durable(_eval(base).body, picked)


@pytest.mark.parametrize("named", [True, False], ids=["named", "unnamed"])
def test_a_fillet_on_the_inner_rim_arc_fails_once_the_shell_is_deleted(
    named: bool,
) -> None:
    base = _r5_box()
    shelled = [*base, _shell(base)]
    picked = _inner_rim_arc(shelled)
    assert picked.topo_name is not None
    picked = picked if named else _unnamed(picked)
    assert _outcome(_eval([*shelled, _on_edge("fillet", SH, picked)])) == ("ok", None)
    assert _outcome(_eval([*base, _on_edge("fillet", SH, picked)])) == (
        "error",
        "subshape_unresolved",
    )


def test_a_fillet_on_an_unnamed_imported_rim_fails_when_the_file_loses_its_shell() -> (
    None
):
    """An imported body carries no history names; re-importing a revision of
    the file without the shell must fail the fillet, not round the R5 rim."""
    base = _r5_box()

    def imported(features: list[dict[str, Any]]) -> dict[str, Any]:
        step = export_step_bytes(_eval(features).body).decode("utf-8")
        return {
            "id": str(IMP),
            "feature": {
                "type": "import",
                "version": 1,
                "params": {"kind": "inline", "format": "step", "data": step},
            },
        }

    shelled = [imported([*base, _shell(base)])]
    picked = _unnamed(_inner_rim_arc(shelled))
    assert _outcome(_eval([*shelled, _on_edge("fillet", IMP, picked)])) == ("ok", None)
    revised = [imported(base)]
    assert _outcome(_eval([*revised, _on_edge("fillet", IMP, picked)])) == (
        "error",
        "subshape_unresolved",
    )


# --- case (b): the counterbore's R5 floor edge -----------------------------------


def _plate(width: float = 40.0) -> list[dict[str, Any]]:
    return [_rect(width, 25), _extrude(10)]


def _hole(
    plate: list[dict[str, Any]],
    kind: dict[str, Any],
    dia: float,
    depth: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": str(HOLE),
        "feature": {
            "type": "hole",
            "version": 1,
            "params": {
                "face": _top_face_ref(EX, plate, 10),
                "position": {"x": 20, "y": 12.5, "z": 10},
                "diameter_mm": dia,
                "depth": depth,
                "type": kind,
            },
        },
    }


def _counterbore(plate: list[dict[str, Any]], bore: float = 10.0) -> dict[str, Any]:
    return _hole(
        plate,
        {"kind": "counterbore", "cbore_diameter_mm": 18.0, "cbore_depth_mm": 4.0},
        bore,
        {"kind": "through_all"},
    )


def _pocket(plate: list[dict[str, Any]]) -> dict[str, Any]:
    return _hole(plate, {"kind": "simple"}, 18.0, {"kind": "blind", "depth_mm": 4.0})


def _floor_edge(features: list[dict[str, Any]], radius: float) -> EdgeSignature:
    (edge,) = [
        s for s in _circles_at(features, 6) if _radius(s) == pytest.approx(radius)
    ]
    return edge


def _cbore_plate_volume(width: float, bore_r: float) -> float:
    return width * 25 * 10 - math.pi * 81 * 4 - math.pi * bore_r**2 * 6


def _ring_chamfer(radius: float) -> float:
    return D * D / 2 * 2 * math.pi * (radius + D / 3)


def test_b_kernel_bore_floor_edge_is_unresolved_once_the_counterbore_goes() -> None:
    plate = _plate()
    picked = _unnamed(_floor_edge([*plate, _counterbore(plate)], 5.0))
    with pytest.raises(SubshapeUnresolvedError):
        resolve_edge_durable(_eval([*plate, _pocket(plate)]).body, picked)


def test_b_chamfer_on_the_bore_floor_edge_fails_when_the_hole_becomes_a_pocket() -> (
    None
):
    """A Hole's faces carry no history names yet, so this is the radius check
    alone (the old tier landed on the R9 floor edge, +6.94 mm^3)."""
    plate = _plate()
    authored = [*plate, _counterbore(plate)]
    picked = _floor_edge(authored, 5.0)
    assert picked.topo_name is None
    assert _outcome(_eval([*authored, _on_edge("chamfer", HOLE, picked)])) == (
        "ok",
        None,
    )
    retyped = [*plate, _pocket(plate), _on_edge("chamfer", HOLE, picked)]
    assert _outcome(_eval(retyped)) == ("error", "subshape_unresolved")


# --- the sketch projection, names stripped --------------------------------------


def _load_lip_builder() -> ModuleType:
    path = Path(__file__).resolve().parent / "_lip_builder.py"
    spec = importlib.util.spec_from_file_location("_lip_builder_concentric", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unnamed_lip_projection_inner_arcs_are_sick_once_the_shell_is_deleted() -> None:
    """The coordinator's case: SKETCH-PROJECT-EDGES' name guard is skipped
    without names, so the radius check alone must keep the inner R3 arcs off
    the outer R5 ones."""
    lip = _load_lip_builder()
    tree = copy.deepcopy(lip.authored_tree(lip.AUTHORED_W))
    rim = next(i for i in tree if i["id"] == str(lip.RIM_SKETCH_ID))
    for entity in rim["feature"]["params"]["entities"]:
        signature = entity["projection"]["edge"]["selector"]["signature"]
        for key in ("topo_name", "end_a_topo_name", "end_b_topo_name"):
            signature[key] = None
    gone = [i for i in tree if i["id"] != str(lip.SHELL_ID)]
    evaluation = lip.evaluate(gone)
    (result,) = [
        r for r in evaluation.result.features if r.feature_id == lip.RIM_SKETCH_ID
    ]
    assert result.status == "ok", result.error
    assert isinstance(result.data, SolvedSketchData)
    states = {p.entity: (p.state, p.tier, p.reason) for p in result.data.projections}
    inner = {e for e in states if e.startswith("i")}
    assert len(inner) == 8
    assert {e for e, s in states.items() if s == ("sick", None, "unresolved")} == inner
    assert {e for e, s in states.items() if s == ("ok", "exact", None)} == (
        set(states) - inner
    )


# --- positive controls: legitimate re-finds still resolve ------------------------


def test_the_same_floor_circle_still_resolves_after_the_plate_is_widened() -> None:
    """A size edit that leaves the picked circle where it was (radius 5, same
    centre): the chamfer re-finds it and removes the hand-derived ring."""
    authored = [*_plate(40), _counterbore(_plate(40))]
    picked = _floor_edge(authored, 5.0)
    widened_plate = _plate(50)
    evaluation = _eval(
        [*widened_plate, _counterbore(widened_plate), _on_edge("chamfer", HOLE, picked)]
    )
    assert _outcome(evaluation) == ("ok", None)
    want = _cbore_plate_volume(50, 5.0) - _ring_chamfer(5.0)
    assert evaluation.result.properties.volume == pytest.approx(want, rel=1e-7)
    landed = resolve_edge_durable(
        _eval([*widened_plate, _counterbore(widened_plate)]).body, picked
    )
    assert _radius(landed.signature) == pytest.approx(5.0, abs=1e-9)


def test_a_same_radius_circle_off_strict_tolerance_is_a_durable_re_find() -> None:
    """Tier 2's circular half still fires when the circle is the SAME one
    (centre, radius, station) but a strict field drifted past its tolerance:
    here the stored length, off by 1e-3 mm."""
    plate = _plate()
    authored = [*plate, _counterbore(plate)]
    picked = _floor_edge(authored, 5.0)
    drifted = picked.model_copy(update={"length_mm": picked.length_mm + 1e-3})
    landed = resolve_edge_durable(_eval(authored).body, drifted)
    assert landed.tier == "durable"
    assert _radius(landed.signature) == pytest.approx(5.0, abs=1e-9)


def test_a_named_rim_arc_follows_a_thinner_shell_and_an_unnamed_one_refuses() -> None:
    """Fusion keeps a fillet on an edge an edit resizes: that is the named
    tier's job (the same two faces still meet there), not a concentric guess.
    Shell 2 -> 1 mm turns the inner R3 rim arc into an R4 one. Named, the
    fillet follows; unnamed, R4 is another circle, so it fails, typed."""
    base = _r5_box()
    picked = _inner_rim_arc([*base, _shell(base)])
    thinner = _shell(base)
    thinner["feature"]["params"]["thickness_mm"] = 1.0
    named = _eval([*base, thinner, _on_edge("fillet", SH, picked)])
    assert _outcome(named) == ("ok", None)
    assert _tier(named) == "named"
    # Hand: the 1 mm shell is outer (1100 + 25 pi) * 20 - inner (1000 + 16 pi) *
    # 19; the R0.5 fillet runs the whole tangent rim loop (lines 2 * (30 + 20),
    # arcs R4) and removes the spandrel r^2 (1 - pi/4), its centroid
    # r (10 - 3 pi) / (3 (4 - pi)) into the wall (Pappus on the arcs).
    shell = (1100 + 25 * math.pi) * 20 - (1000 + 16 * math.pi) * 19
    spandrel = D * D * (1 - math.pi / 4)
    offset = D * (10 - 3 * math.pi) / (3 * (4 - math.pi))
    path = 2 * (30 + 20) + 2 * math.pi * (4 + offset)
    want = shell - spandrel * path
    assert named.result.properties.volume == pytest.approx(want, rel=1e-7)
    unnamed = _eval([*base, thinner, _on_edge("fillet", SH, _unnamed(picked))])
    assert _outcome(unnamed) == ("error", "subshape_unresolved")


def test_a_straight_edge_growing_along_its_line_is_still_a_durable_re_find() -> None:
    """The durable tier's straight half is untouched: the plate's front top edge
    (y = 0, z = 10) grows 40 -> 50 along its own line and the chamfer follows."""
    (front,) = [
        s
        for s in _picked(_plate(40))
        if s.curve == "line"
        and s.end_a.y == pytest.approx(0)
        and s.end_b.y == pytest.approx(0)
        and s.end_a.z == pytest.approx(10)
        and s.end_b.z == pytest.approx(10)
    ]
    evaluation = _eval([*_plate(50), _on_edge("chamfer", EX, _unnamed(front))])
    assert _outcome(evaluation) == ("ok", None)
    assert _tier(evaluation) == "durable"
    want = 50 * 25 * 10 - D * D / 2 * 50
    assert evaluation.result.properties.volume == pytest.approx(want, rel=1e-9)


def test_two_remaining_concentric_circles_are_still_a_typed_refusal() -> None:
    """Shell thickness 1 mm instead of 2: the R3 arc is gone, an R4 arc stands
    where it would be. Typed failure, never a resolution."""
    base = _r5_box()
    picked = _unnamed(_inner_rim_arc([*base, _shell(base)]))
    thinner = copy.deepcopy(_shell(base))
    thinner["feature"]["params"]["thickness_mm"] = 1.0
    with pytest.raises((SubshapeUnresolvedError, SubshapeAmbiguousError)):
        resolve_edge_durable(_eval([*base, thinner]).body, picked)


def test_the_picked_arcs_are_concentric_with_the_edges_left_standing() -> None:
    """The probe is meaningful: each vanished edge DOES have a concentric
    same-station edge of another radius left, the one the old tier jumped to."""
    base = _r5_box()
    arc = _inner_rim_arc([*base, _shell(base)])
    outer = [
        r.signature
        for r in enumerate_edges_with_adjacency(_eval(base).body)
        if r.signature.curve == "circle"
        and _circle_centre(r.signature) == pytest.approx(_circle_centre(arc), abs=1e-6)
    ]
    assert [round(_radius(s), 6) for s in outer] == [5.0]
    plate = _plate()
    floor = _floor_edge([*plate, _counterbore(plate)], 5.0)
    assert _floor_edge([*plate, _pocket(plate)], 9.0) is not None
    assert _circle_centre(floor) == pytest.approx((20.0, 12.5, 6.0), abs=1e-6)
