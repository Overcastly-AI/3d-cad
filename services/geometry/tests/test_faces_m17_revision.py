"""M17 at the FEATURE-TREE level — a bracket revised the way brackets get revised.

The kernel-level gates for the outer-boundary re-match live in ``test_faces.py``;
this file exercises the whole path the product takes, because M17 is a property of
an ORDER of features and not of one resolver call. The audit's finding
(``docs/AUDIT-PRODUCT.md`` M17, ``docs/design/topological-naming.md`` §12a):
thickening a plate that carries four mounting holes left 4 of 11 features red, and
the mechanism is that a planar face's stored signature encodes what has been CUT
INTO it — so hole *n*'s stored ``area_mm2`` is exactly one hole's worth smaller
than hole *n-1*'s and goes stale the moment any earlier hole on that face changes.

Three trees, one part, and the control matters as much as the failure: neither edit
alone breaks anything (tier 2 absorbs the in-plane change, tier 3 the moved plane),
so only the COMBINATION reaches the tier this file gates. The correctness claim is
not "it rebuilds" — a matcher that re-anchored to the wrong face would also rebuild
— but that the rescued body is BYTE-IDENTICAL to the body an exact re-pick produces.
"""

import copy
import hashlib
import itertools
import math
import uuid
from typing import Any

import pytest
from geometry.features import evaluate_tree
from geometry.harness import evaluate_model
from geometry.kernel.faces import planar_faces
from py_kit.schemas.features import EvaluateTreeRequest

#: One hole's worth of face area, Ø6.6: pi * 3.3^2 mm^2. The audit measured the four
#: stored areas exactly this far apart; that spacing IS the defect, so it is asserted.
HOLE_AREA_MM2 = math.pi * 3.3**2

#: Analytic-agreement bound for a boolean cut of right cylinders from a box, which
#: GProp integrates exactly (docs/GEOMETRY-QA.md; the same 1e-9 the revision goldens
#: use). Not an ad-hoc epsilon — measured residuals here are ~1e-11.
AREA_TOLERANCE_MM2 = 1e-9

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000017a0")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000017a1")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-0000000017a2")
BORE_ID = uuid.UUID("00000000-0000-0000-0000-0000000017a3")
HOLE_IDS = [
    uuid.UUID(f"00000000-0000-0000-0000-0000000017b{index}") for index in range(4)
]

PLATE_W, PLATE_H = 100.0, 40.0
BORE_XY = (50.0, 20.0)
HOLE_XY = [(18.0, 8.0), (82.0, 8.0), (82.0, 32.0), (18.0, 32.0)]
HOLE_DIA = 6.6
WIDENED_DIA = 7.0


def _line(eid: str, start: tuple[float, float], end: tuple[float, float]) -> Any:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def _sketch() -> dict[str, Any]:
    corners = [(0.0, 0.0), (PLATE_W, 0.0), (PLATE_W, PLATE_H), (0.0, PLATE_H)]
    return {
        "id": str(SKETCH_ID),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": "XY"},
                "entities": [
                    _line(f"e{i + 1}", corners[i], corners[(i + 1) % 4])
                    for i in range(4)
                ],
                "constraints": [],
            },
        },
    }


def _extrude(thickness_mm: float) -> dict[str, Any]:
    return {
        "id": str(EXTRUDE_ID),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(SKETCH_ID)},
                "distance_mm": thickness_mm,
                "operation": "add",
                "direction": "normal",
            },
        },
    }


def _hole(
    feature_id: uuid.UUID,
    signature: dict[str, Any],
    position: tuple[float, float],
    z_mm: float,
    diameter_mm: float,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "hole",
            "version": 1,
            "params": {
                "face": {
                    "kind": "subshape",
                    "feature_id": str(EXTRUDE_ID),
                    "subshape_type": "face",
                    "selector": {"selector_version": 1, "signature": signature},
                },
                "position": {"x": position[0], "y": position[1], "z": z_mm},
                "diameter_mm": diameter_mm,
                "depth": {"kind": "through_all"},
            },
        },
    }


def _evaluate(features: list[dict[str, Any]], tree_version: int) -> Any:
    return evaluate_tree(
        EvaluateTreeRequest.model_validate(
            {
                "part_id": str(PART_ID),
                "tree_version": tree_version,
                "features": features,
                "linear_deflection": 0.1,
            }
        )
    )


def _top_face_signature(features: list[dict[str, Any]], z_mm: float) -> dict[str, Any]:
    """The +Z top-face signature of the body this feature PREFIX builds.

    Exactly how the product captures a pick: the overlay hands the client the
    signature of the face as it stands after the features that precede the new one.
    So this is an INPUT, produced the way the product produces it — every expectation
    in this file is derived independently of it.
    """
    evaluation = _evaluate(features, 1)
    assert evaluation.body is not None
    tops = [
        record
        for record in planar_faces(evaluation.body)
        if record.signature.normal.z > 0.5
        and abs(record.signature.centroid.z - z_mm) <= 1e-9
    ]
    assert len(tops) == 1
    signature = tops[0].signature
    return {
        "subshape_type": "face",
        "surface": "plane",
        "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
        "centroid": {
            "x": signature.centroid.x,
            "y": signature.centroid.y,
            "z": signature.centroid.z,
        },
        "area_mm2": signature.area_mm2,
    }


def _authored_tree(thickness_mm: float) -> tuple[list[dict[str, Any]], list[float]]:
    """The as-authored bracket: plate, Ø30 bore, four Ø6.6 mounting holes.

    Returns the tree plus the stored area each mounting hole captured, which is the
    measurement the audit made and the defect it names.
    """
    features: list[dict[str, Any]] = [_sketch(), _extrude(thickness_mm)]
    features.append(
        _hole(
            BORE_ID,
            _top_face_signature(features, thickness_mm),
            BORE_XY,
            thickness_mm,
            30.0,
        )
    )
    stored_areas: list[float] = []
    for feature_id, position in zip(HOLE_IDS, HOLE_XY, strict=True):
        signature = _top_face_signature(features, thickness_mm)
        stored_areas.append(float(signature["area_mm2"]))
        features.append(_hole(feature_id, signature, position, thickness_mm, HOLE_DIA))
    return features, stored_areas


def _statuses(evaluation: Any) -> list[tuple[str, str]]:
    return [
        (str(result.feature_id), result.status) for result in evaluation.result.features
    ]


def test_each_hole_stores_a_face_area_one_hole_smaller_than_the_last() -> None:
    """THE MECHANISM, measured. A face signature is supposed to be an identity; these
    four differ by exactly the area of one Ø6.6 hole each, because ``area_mm2`` is a
    function of what has already been drilled into the face. That is why hole *n*'s
    stored signature stops describing any real face the moment hole *n-1* changes —
    and it reproduces the audit's table (3293.1417 / 3258.9297 / 3224.7178 /
    3190.5058 mm²) to the digit."""
    _tree, stored_areas = _authored_tree(10.0)
    bare = PLATE_W * PLATE_H - math.pi * 15.0**2
    assert stored_areas[0] == pytest.approx(bare, abs=AREA_TOLERANCE_MM2)
    for previous, current in itertools.pairwise(stored_areas):
        assert previous - current == pytest.approx(
            HOLE_AREA_MM2, abs=AREA_TOLERANCE_MM2
        )


def test_either_edit_ALONE_already_rebuilt_clean() -> None:
    """The control, and the reason the audit's reading ("the thickness change alone")
    was half right. An in-plane change is absorbed by the tier-2 coplanar re-match and
    a moved plane by the tier-3 translated one; each edit on its own has always
    rebuilt clean, so a fix must not be justified by either of them."""
    tree, _areas = _authored_tree(10.0)

    widened = copy.deepcopy(tree)
    widened[3]["feature"]["params"]["diameter_mm"] = WIDENED_DIA
    assert all(status == "ok" for _fid, status in _statuses(_evaluate(widened, 2)))

    thickened = copy.deepcopy(tree)
    thickened[1] = _extrude(14.0)
    assert all(status == "ok" for _fid, status in _statuses(_evaluate(thickened, 3)))


def test_the_bracket_rebuilds_when_the_plate_is_thickened_after_a_hole_edit() -> None:
    """THE M17 GATE. Widen Hole1 Ø6.6 → 7, then retype the plate 10 → 14 mm — two
    edits any engineer makes in a single sitting — and before tier 4 the SECOND
    mounting hole came back ``subshape_unresolved`` with everything after it stranded
    by the strict-prefix rule. Every feature must rebuild."""
    tree, _areas = _authored_tree(10.0)
    revised = copy.deepcopy(tree)
    revised[3]["feature"]["params"]["diameter_mm"] = WIDENED_DIA
    revised[1] = _extrude(14.0)

    statuses = _statuses(_evaluate(revised, 4))
    assert [status for _fid, status in statuses] == ["ok"] * len(tree)


def test_the_rescued_body_is_the_body_an_exact_RE_PICK_would_have_made() -> None:
    """Correctness, not merely liveness. "It rebuilds" is satisfied by a matcher that
    re-anchors to the wrong face; this asserts the revised part is byte-for-byte the
    part the same tree produces when every signature is authored at the CURRENT state
    (a tier-1 strict match that never reaches a resilient tier). Same GLB, same mass
    properties — so the outer-boundary re-anchor put every hole back at its picked
    station, at the face's new place."""
    tree, _areas = _authored_tree(10.0)
    revised = copy.deepcopy(tree)
    revised[3]["feature"]["params"]["diameter_mm"] = WIDENED_DIA
    revised[1] = _extrude(14.0)
    rescued_glb, rescued_meta = evaluate_model(
        EvaluateTreeRequest.model_validate(
            {
                "part_id": str(PART_ID),
                "tree_version": 5,
                "features": revised,
                "linear_deflection": 0.1,
            }
        )
    )

    # The same part, re-picked: authored at 14 mm with Hole1 already at Ø7.
    exact: list[dict[str, Any]] = [_sketch(), _extrude(14.0)]
    exact.append(_hole(BORE_ID, _top_face_signature(exact, 14.0), BORE_XY, 14.0, 30.0))
    for index, (feature_id, position) in enumerate(zip(HOLE_IDS, HOLE_XY, strict=True)):
        exact.append(
            _hole(
                feature_id,
                _top_face_signature(exact, 14.0),
                position,
                14.0,
                WIDENED_DIA if index == 0 else HOLE_DIA,
            )
        )
    exact_glb, exact_meta = evaluate_model(
        EvaluateTreeRequest.model_validate(
            {
                "part_id": str(PART_ID),
                "tree_version": 6,
                "features": exact,
                "linear_deflection": 0.1,
            }
        )
    )

    assert (
        hashlib.sha256(rescued_glb).hexdigest() == hashlib.sha256(exact_glb).hexdigest()
    )
    assert rescued_meta.properties.volume == exact_meta.properties.volume
    assert rescued_meta.properties.centroid == exact_meta.properties.centroid
    assert rescued_meta.properties.topology == exact_meta.properties.topology
    assert rescued_meta.mesh == exact_meta.mesh
