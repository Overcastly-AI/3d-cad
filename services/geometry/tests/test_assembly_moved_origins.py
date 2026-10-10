"""Joint and mate origins follow a hole that a part edit MOVED (RESEARCH §21).

The QA case: a hinge of two brackets and a pin, revolute joints through the hole
circle centres, the hinge at 90 deg. The bracket is W x 30 x 10 with an r5 hole
at its centre (W/2, 15). Changing W from 100 to 80 moves the hole 10 mm along X,
off every coordinate the stored circle signatures hold, so the strict resolver
lost both joints and every part fell back to its seed pose. In Fusion 360 the
joints move with the hole: the origins now resolve through the feature tree's
tiered resolver, whose named tier finds the rim by how it was made (the extrude's
cap and the side face swept from sketch circle ``h1``).

The origins are PICKED exactly as the web picks them: from the selection overlay
of the W = 100 bracket, names included. ``goldens-assembly/
assembly-hinge-pin-moved-holes-w100-to-80`` is this request at W = 80, and the
first test proves the golden's stored signatures are that pick.

Hand derivation (frames per RESEARCH §21; R = RotZ(90 deg) maps x -> y, y -> -x):

- Joint 1 (revolute, value 0): A's hole BOTTOM rim, origin (W/2, 15, 0), Z = -Z,
  X = +X; the pin's bottom cap circle, origin (0, 0, 0), Z = -Z, flipped to +Z
  (X kept). Opposed Z and aligned X give the pin the identity rotation, so the
  pin sits at (W/2, 15, 0) and spans z 0..20 through A's hole.
- Joint 2 (revolute, value 90): the pin's TOP cap circle, world (W/2, 15, 20),
  Z = +Z, X = +X; B's hole TOP rim, B-local (W/2, 15, 10), Z = +Z flipped to -Z.
  B's frame X lands on RotZ(90) X = +Y and its Z on -Z, so B's rotation is R and
  R (W/2, 15, 10) + t = (W/2, 15, 20) gives t = (W/2 + 15, 15 - W/2, 10).
- W = 100: pin (50, 15, 0), B t = (65, -35, 10). W = 80: pin (40, 15, 0),
  B t = (55, -25, 10). B's hole centre R (W/2, 15, z) + t = (W/2, 15, z + 10):
  on A's hole axis in both.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from __future__ import annotations

import math
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from geometry.assembly import evaluate_assembly
from geometry.assembly.transform import Pose
from geometry.features import evaluate_tree
from geometry.kernel.edges import resolve_edge
from geometry.kernel.faces import SubshapeUnresolvedError
from geometry.kernel.overlay import selection_overlay
from loft_wire.assemblies import (
    ConcentricMate,
    EvaluateAssemblyRequest,
    EvaluateAssemblyResult,
    MateAxisRef,
)
from loft_wire.features import EdgeSignature, EvaluateTreeRequest
from loft_wire.joints import JointMate, JointOrigin, JointValue

#: Closed-form snaps on a grounded tree: exact to float64 round-off, as the
#: hinge golden measured (<= 5.4e-15 mm).
EXACT_TOL = 1e-9

_GOLDEN = (
    Path(__file__).resolve().parent.parent
    / "goldens-assembly/assembly-hinge-pin-moved-holes-w100-to-80/model.json"
)

_SKETCH = "00000000-0000-0000-0000-0000000000a1"
_EXTRUDE = "00000000-0000-0000-0000-0000000000b1"
_A, _PIN, _B = 1, 2, 3
_J1, _J2 = 1001, 1002
_ROT_Z_90 = (0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4))


def iid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def _line(eid: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": a[0], "y": a[1]},
        "end": {"x": b[0], "y": b[1]},
    }


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


def bracket(width: float, *, hole: bool = True) -> list[dict[str, Any]]:
    """The W x 30 x 10 bracket, its r5 hole ``h1`` centred at (W/2, 15)."""
    entities = [
        _line("e1", (0.0, 0.0), (width, 0.0)),
        _line("e2", (width, 0.0), (width, 30.0)),
        _line("e3", (width, 30.0), (0.0, 30.0)),
        _line("e4", (0.0, 30.0), (0.0, 0.0)),
    ]
    if hole:
        entities.append(
            {
                "id": "h1",
                "kind": "circle",
                "center": {"x": width / 2, "y": 15.0},
                "radius": 5.0,
            }
        )
    return _prism(entities, 10.0)


def pin() -> list[dict[str, Any]]:
    """The r5 x 20 pin, its axis on local Z."""
    circle = {"id": "c1", "kind": "circle", "center": {"x": 0.0, "y": 0.0}}
    return _prism([{**circle, "radius": 5.0}], 20.0)


def _picked_rims(features: list[dict[str, Any]]) -> dict[float, EdgeSignature]:
    """The circular edges as the web picks them (the selection overlay with the
    evaluation's face names), keyed by height."""
    request = EvaluateTreeRequest.model_validate(
        {"part_id": str(iid(77)), "tree_version": 1, "features": features}
    )
    evaluation = evaluate_tree(request)
    assert evaluation.body is not None
    overlay = selection_overlay(evaluation.body, 0.1, None, evaluation.face_names())
    rims = {
        e.signature.midpoint.z: e.signature
        for e in overlay.edges
        if e.signature.curve == "circle"
    }
    assert len(rims) == 2
    assert all(sig.topo_name is not None for sig in rims.values())
    return rims


def _instance(
    n: int,
    part_key: str,
    features: list[dict[str, Any]],
    position: tuple[float, float, float],
    *,
    grounded: bool = False,
) -> dict[str, Any]:
    return {
        "instance_id": str(iid(n)),
        "part_key": part_key,
        "features": features,
        "placement": {
            "position": dict(zip("xyz", position, strict=True)),
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        },
        "grounded": grounded,
    }


def _origin(n: int, signature: EdgeSignature, *, flip: bool = False) -> JointOrigin:
    return JointOrigin(
        instance_id=iid(n), kind="circle_centre", signature=signature, flip=flip
    )


def hinge(width: float, *, hole: bool = True) -> EvaluateAssemblyRequest:
    """The hinge at bracket width *width*, its origins picked at W = 100.

    Seeds are drop poses far from the answer, so a dropped joint shows."""
    rim = _picked_rims(bracket(100.0))
    cap = _picked_rims(pin())
    j1 = JointMate(
        motion="revolute",
        a=_origin(_A, rim[0.0]),
        b=_origin(_PIN, cap[0.0], flip=True),
        value=JointValue(rot_deg=0.0),
    )
    j2 = JointMate(
        motion="revolute",
        a=_origin(_PIN, cap[20.0]),
        b=_origin(_B, rim[10.0], flip=True),
        value=JointValue(rot_deg=90.0),
    )
    key = f"part-bracket@{int(width)}{'' if hole else '-no-hole'}"
    features = bracket(width, hole=hole)
    return EvaluateAssemblyRequest.model_validate(
        {
            "assembly_id": str(iid(0x41)),
            "version": 1,
            "instances": [
                _instance(_A, key, features, (0.0, 0.0, 0.0), grounded=True),
                _instance(_PIN, "part-pin@1", pin(), (0.0, -60.0, 0.0)),
                _instance(_B, key, features, (0.0, 60.0, 0.0)),
            ],
            "mates": [
                {"mate_id": str(iid(_J1)), "order_index": 0, "mate": j1.model_dump()},
                {"mate_id": str(iid(_J2)), "order_index": 1, "mate": j2.model_dump()},
            ],
            "linear_deflection": 0.1,
        }
    )


def _pose(result: EvaluateAssemblyResult, n: int) -> Pose:
    (inst,) = (i for i in result.instances if i.instance_id == iid(n))
    return Pose.from_placement(inst.placement)


def _assert_pose(
    result: EvaluateAssemblyResult,
    n: int,
    t: tuple[float, float, float],
    q: tuple[float, float, float, float],
) -> None:
    got = _pose(result, n)
    want = Pose(t=np.array(t), q=np.array(q))
    assert np.allclose(got.t, want.t, rtol=0.0, atol=EXACT_TOL)
    assert np.allclose(got.matrix(), want.matrix(), rtol=0.0, atol=EXACT_TOL)


def _assert_hinge(result: EvaluateAssemblyResult, width: float) -> None:
    assert result.mate_errors == []
    _assert_pose(result, _A, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    _assert_pose(result, _PIN, (width / 2, 15.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    _assert_pose(result, _B, (width / 2 + 15.0, 15.0 - width / 2, 10.0), _ROT_Z_90)
    # B's hole centre sits on A's hole axis, one plate up.
    hole_b = _pose(result, _B).apply_point(np.array([width / 2, 15.0, 0.0]))
    assert np.allclose(hole_b, [width / 2, 15.0, 10.0], rtol=0.0, atol=EXACT_TOL)
    states = {s.mate_id: s for s in result.joint_states}
    assert states[iid(_J1)].rot_deg == pytest.approx(0.0, abs=EXACT_TOL)
    assert states[iid(_J2)].rot_deg == pytest.approx(90.0, abs=EXACT_TOL)


def test_the_golden_stores_the_w100_pick_at_w80() -> None:
    stored = EvaluateAssemblyRequest.model_validate_json(
        _GOLDEN.read_text(encoding="utf-8")
    )
    assert stored == hinge(80.0)


def test_the_hinge_solves_at_w100() -> None:
    _assert_hinge(evaluate_assembly(hinge(100.0)), 100.0)


def test_the_strict_signature_no_longer_matches_at_w80() -> None:
    """The precondition the fix answers: W = 80 moved the rim off every stored
    coordinate, so the strict tier alone finds nothing."""
    request = EvaluateTreeRequest.model_validate(
        {"part_id": str(iid(77)), "tree_version": 1, "features": bracket(80.0)}
    )
    body = evaluate_tree(request).body
    assert body is not None
    for signature in _picked_rims(bracket(100.0)).values():
        with pytest.raises(SubshapeUnresolvedError):
            resolve_edge(body, signature)


def test_the_joints_follow_the_moved_holes_at_w80() -> None:
    _assert_hinge(evaluate_assembly(hinge(80.0)), 80.0)


def test_the_moved_hinge_is_deterministic() -> None:
    first = evaluate_assembly(hinge(80.0)).model_dump_json()
    assert evaluate_assembly(hinge(80.0)).model_dump_json() == first


def test_a_deleted_hole_leaves_both_joints_unresolved() -> None:
    """With the hole gone there is no edge to follow: both joints report
    ``subshape_unresolved`` and nothing is placed on another edge."""
    result = evaluate_assembly(hinge(80.0, hole=False))
    errors = {e.mate_id: e.error.code for e in result.mate_errors}
    assert errors == {
        iid(_J1): "subshape_unresolved",
        iid(_J2): "subshape_unresolved",
    }
    assert result.joint_states == []
    # Unconstrained, the pin and B stay at their seeds.
    _assert_pose(result, _PIN, (0.0, -60.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    _assert_pose(result, _B, (0.0, 60.0, 0.0), (0.0, 0.0, 0.0, 1.0))


def _concentric(width: float, *, hole: bool = True) -> EvaluateAssemblyRequest:
    """A legacy concentric mate between A's hole and the pin, picked at W = 100."""
    request = hinge(width, hole=hole)
    mate = ConcentricMate(
        a=MateAxisRef(instance_id=iid(_A), signature=_picked_rims(bracket(100.0))[0.0]),
        b=MateAxisRef(instance_id=iid(_PIN), signature=_picked_rims(pin())[0.0]),
    )
    evaluated = request.mates[0].model_copy(update={"mate": mate})
    return request.model_copy(update={"mates": [evaluated]})


@pytest.mark.parametrize("width", [100.0, 80.0])
def test_a_legacy_concentric_mate_follows_the_moved_hole(width: float) -> None:
    result = evaluate_assembly(_concentric(width))
    assert result.mate_errors == []
    # The pin's axis is A's hole axis: x = W/2, y = 15 at every height.
    pose = _pose(result, _PIN)
    for z in (0.0, 20.0):
        point = pose.apply_point(np.array([0.0, 0.0, z]))
        assert np.allclose(point[:2], [width / 2, 15.0], rtol=0.0, atol=1e-6)


def test_a_legacy_concentric_mate_on_a_deleted_hole_is_unresolved() -> None:
    result = evaluate_assembly(_concentric(80.0, hole=False))
    assert [(e.mate_id, e.error.code) for e in result.mate_errors] == [
        (iid(_J1), "subshape_unresolved")
    ]
