"""A picked edge whose own edge vanished must not re-anchor onto a CONCENTRIC
edge of another radius (BACKLOG EDGE-REF-CONCENTRIC, wrong geometry).

Found by the SKETCH-PROJECT-EDGES step-2 follow-up probe: ``_match_edge_records``
tier 2 (``concentric_same_station_match``) accepts any circle with the same centre
and angular station, so when the picked R_a edge disappears and a single R_b edge
of the same centre remains, fillet / chamfer silently round the R_b edge: no
error, tier ``durable``, status ok. Projections guard this with ``keep_name``.

Numbers derived outside the code under test (volume of the removed/added wedge):
case (b) chamfer d=0.5 on the R9 floor edge of a dia-18 blind pocket ADDS
``0.5 * 0.5 / 2 * 2*pi*9 = 7.07 mm^3`` (concave edge); on the picked R5 edge
that edge no longer exists. Each test asserts the resolved edge keeps the picked
radius; today it does not, so both are strict xfails. When the fix lands (typed
``subshape_unresolved`` or a name/radius guard) they XPASS and strict flips red:
delete the markers then.
"""

import math
import uuid
from typing import Any

import pytest
from geometry.features import evaluate_tree
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
from loft_wire.features import EvaluateTreeRequest
from loft_wire.signatures import EdgeSignature

SK, EX, FIL, SH, HOLE = (uuid.UUID(int=0xF100 + i) for i in range(1, 6))


def _eval(features: list[dict[str, Any]]) -> Any:
    return evaluate_tree(
        EvaluateTreeRequest.model_validate(
            {
                "part_id": str(uuid.UUID(int=0xF1)),
                "tree_version": 1,
                "features": features,
                "linear_deflection": 0.1,
            }
        )
    )


def _radius(sig: EdgeSignature) -> float:
    centre = _circle_centre(sig)
    assert centre is not None
    m = sig.midpoint
    return math.dist(centre, (m.x, m.y, m.z))


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


def _top_face_ref(owner: uuid.UUID, features: list[dict[str, Any]], z: float) -> Any:
    evaluation = _eval(features)
    for face in evaluation.body.faces():
        sig = face_signature_dto(face)
        if sig and sig.normal.z > 0.99 and abs(sig.centroid.z - z) < 1e-6:
            return {
                "kind": "subshape",
                "feature_id": str(owner),
                "subshape_type": "face",
                "selector": {"selector_version": 1, "signature": sig.model_dump()},
            }
    raise AssertionError("no top face")


def _circles_at(features: list[dict[str, Any]], z: float) -> list[EdgeSignature]:
    evaluation = _eval(features)
    return [
        r.signature
        for r in enumerate_edges_with_adjacency(evaluation.body)
        if r.signature.curve == "circle"
        and abs((_circle_centre(r.signature) or (0, 0, 1e9))[2] - z) < 1e-6
    ]


def _resolved_radius(
    features: list[dict[str, Any]], picked: EdgeSignature
) -> float | None:
    """Radius of the edge the reference lands on, None when it refuses (typed)."""
    evaluation = _eval(features)
    try:
        resolved = resolve_edge_durable(evaluation.body, picked)
    except (SubshapeUnresolvedError, SubshapeAmbiguousError):
        return None
    return _radius(resolved.signature)


@pytest.mark.xfail(
    strict=True,
    reason="BACKLOG EDGE-REF-CONCENTRIC: case (a), shell deleted, inner R3 rim arc "
    "re-anchors (durable) onto the concentric outer R5 rim arc",
)
def test_a_inner_rim_arc_does_not_jump_to_outer_r5_when_the_shell_is_deleted() -> None:
    base = [
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
    shell = {
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
    inner = [
        s for s in _circles_at([*base, shell], 20) if _radius(s) == pytest.approx(3.0)
    ]
    assert len(inner) == 4
    picked = min(inner, key=lambda s: (s.end_a.x, s.end_a.y))
    # Shell deleted: only the R5 rim arcs remain at z=20.
    landed = _resolved_radius(base, picked)
    assert landed is None or landed == pytest.approx(3.0), (
        f"picked an R3 arc, resolved onto an R{landed} arc with no error"
    )


@pytest.mark.xfail(
    strict=True,
    reason="BACKLOG EDGE-REF-CONCENTRIC: case (b), counterbore replaced by a dia-18 "
    "blind pocket, R5 bore-floor edge re-anchors (durable) onto the R9 floor edge",
)
def test_b_bore_floor_edge_does_not_jump_to_r9_when_the_counterbore_goes() -> None:
    plate = [_rect(40, 25), _extrude(10)]

    def hole(kind: dict[str, Any], dia: float, depth: dict[str, Any]) -> dict[str, Any]:
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

    counterbore = hole(
        {"kind": "counterbore", "cbore_diameter_mm": 18.0, "cbore_depth_mm": 4.0},
        10.0,
        {"kind": "through_all"},
    )
    floor = _circles_at([*plate, counterbore], 6)
    picked = next(s for s in floor if _radius(s) == pytest.approx(5.0))
    pocket = hole({"kind": "simple"}, 18.0, {"kind": "blind", "depth_mm": 4.0})
    landed = _resolved_radius([*plate, pocket], picked)
    assert landed is None or landed == pytest.approx(5.0), (
        f"picked an R5 edge, resolved onto an R{landed} edge with no error"
    )
