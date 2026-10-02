"""The hard-parts sheet-metal bracket of DESIGN-INTENT-REFS step 3, built the
way the product builds it: every pick captured from the selection overlay of
the features before it.

QA's part (docs/VISION.md "Hard parts", 2026-10-01): a 60x40x2 base flange
(R2 default bend), two 90 deg edge flanges 20 mm long on the +-X edges, a
45 deg edge flange 15 mm long and 50 wide (offset 5, so two bend-end reliefs)
on the -Y edge, a closed 6 mm hem on the +Y edge, and a through Ø5 hole on
the +X flange's outer face near its bend. The rectangle is anchored at its
-X/-Y corner, so the base edit 60 -> 70 moves the +X edge (and Edge flange1
with it) from x = 30 to x = 40. Volumes check against QA's hand calculation:
11 529.75 mm^3 at 60 with the hole, 12 597.41 at 70 without it.

Shared by ``test_design_intent_bracket.py`` and ``test_naming.py`` (loaded by
file path), and the generator of the
``goldens-sheet-metal/revise-base-70-hole-on-flange`` golden's ``model.json``:

    uv run python services/geometry/tests/_bracket_builder.py > model.json
"""

import copy
import json
import sys
import uuid
from typing import Any

from geometry.features import evaluate_tree
from geometry.overlay import evaluate_overlay
from loft_wire.features import EvaluateTreeRequest
from loft_wire.overlay import OverlayRequest

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000b7c00")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000b7c01")
BASE_ID = uuid.UUID("00000000-0000-0000-0000-0000000b7c02")
FLANGE1_ID = uuid.UUID("00000000-0000-0000-0000-0000000b7c03")
FLANGE2_ID = uuid.UUID("00000000-0000-0000-0000-0000000b7c04")
FLANGE3_ID = uuid.UUID("00000000-0000-0000-0000-0000000b7c05")
HEM_ID = uuid.UUID("00000000-0000-0000-0000-0000000b7c06")
HOLE_ID = uuid.UUID("00000000-0000-0000-0000-0000000b7c07")

AUTHORED_W = 60.0
REVISED_W = 70.0
DEPTH = 40.0
GAUGE = 2.0
BEND_R = 2.0
SIDE_LEG = 20.0
FRONT_LEG = 15.0
FRONT_WIDTH = 50.0
FRONT_OFFSET = 5.0
HEM_LEG = 6.0
HOLE_D = 5.0
#: The hole's station on the +X flange (y, z): 5 mm above the bend's end.
HOLE_YZ = (5.0, 9.0)
X0, Y0 = -30.0, -20.0


def _line(eid: str, start: tuple[float, float], end: tuple[float, float]) -> Any:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def sketch(width_mm: float) -> dict[str, Any]:
    """The blank, its -X/-Y corner fixed. ``width_mm`` is the edited value."""
    x1, y1 = X0 + width_mm, Y0 + DEPTH
    corners = [(X0, Y0), (x1, Y0), (x1, y1), (X0, y1)]
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


def base_flange() -> dict[str, Any]:
    return {
        "id": str(BASE_ID),
        "feature": {
            "type": "sheet_metal_base_flange",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(SKETCH_ID)},
                "thickness_mm": GAUGE,
                "bend_radius_mm": BEND_R,
                "k_factor": 0.44,
            },
        },
    }


def _request(features: list[dict[str, Any]], version: int) -> dict[str, Any]:
    return {
        "part_id": str(PART_ID),
        "tree_version": version,
        "features": features,
        "linear_deflection": 0.1,
    }


def _overlay(features: list[dict[str, Any]]) -> Any:
    """The selection overlay of *features*: the pick side, as the product runs it."""
    return evaluate_overlay(
        OverlayRequest.model_validate({"tree": _request(features, 1)})
    )


def _top_edge(features: list[dict[str, Any]], *, x: float | None, y: float | None):
    """The overlay's straight edge on the top skin (z = GAUGE) that runs along
    x = *x* (or y = *y*)."""
    found: list[Any] = []
    for edge in _overlay(features).edges:
        sig = edge.signature
        if sig is None or sig.curve != "line":
            continue
        ends = (sig.end_a, sig.end_b)
        if any(abs(p.z - GAUGE) > 1e-9 for p in ends):
            continue
        if x is not None and all(abs(p.x - x) < 1e-9 for p in ends):
            found.append(sig)
        if y is not None and all(abs(p.y - y) < 1e-9 for p in ends):
            found.append(sig)
    assert len(found) == 1, found
    return found[0]


def _edge_ref(anchor: uuid.UUID, signature: Any) -> dict[str, Any]:
    return {
        "kind": "subshape",
        "feature_id": str(anchor),
        "subshape_type": "edge",
        "selector": {
            "selector_version": 1,
            "signature": signature.model_dump(mode="json"),
        },
    }


def _flange(
    fid: uuid.UUID, anchor: uuid.UUID, sig: Any, leg: float, angle: float, **extra: Any
) -> dict[str, Any]:
    return {
        "id": str(fid),
        "feature": {
            "type": "sheet_metal_edge_flange",
            "version": 1,
            "params": {
                "edge": _edge_ref(anchor, sig),
                "flange_length_mm": leg,
                "bend_angle_deg": angle,
                **extra,
            },
        },
    }


def hole(features: list[dict[str, Any]]) -> dict[str, Any]:
    """Ø5 through all, on the +X flange's OUTER leg face (normal +X, the
    outermost such face: the -X flange's inner face shares its normal)."""
    found: list[Any] = []
    for face in _overlay(features).faces:
        sig = face.signature
        if sig is None or abs(sig.normal.x - 1.0) > 1e-9:
            continue
        if sig.area_mm2 > 100.0:
            found.append(sig)
    outer = max(found, key=lambda sig: sig.centroid.x)
    x = outer.centroid.x
    return {
        "id": str(HOLE_ID),
        "feature": {
            "type": "hole",
            "version": 1,
            "params": {
                "face": {
                    "kind": "subshape",
                    "feature_id": str(FLANGE1_ID),
                    "subshape_type": "face",
                    "selector": {
                        "selector_version": 1,
                        "signature": outer.model_dump(mode="json"),
                    },
                },
                "position": {"x": x, "y": HOLE_YZ[0], "z": HOLE_YZ[1]},
                "diameter_mm": HOLE_D,
                "depth": {"kind": "through_all"},
            },
        },
    }


def authored_tree(width_mm: float) -> list[dict[str, Any]]:
    """The bracket built at *width_mm*, every pick captured from the overlay of
    the features before it (exactly how the product captures a pick)."""
    x1 = X0 + width_mm
    tree: list[dict[str, Any]] = [sketch(width_mm), base_flange()]
    tree.append(
        _flange(FLANGE1_ID, BASE_ID, _top_edge(tree, x=x1, y=None), SIDE_LEG, 90.0)
    )
    tree.append(
        _flange(FLANGE2_ID, BASE_ID, _top_edge(tree, x=X0, y=None), SIDE_LEG, 90.0)
    )
    tree.append(
        _flange(
            FLANGE3_ID,
            BASE_ID,
            _top_edge(tree, x=None, y=Y0),
            FRONT_LEG,
            45.0,
            width_mm=FRONT_WIDTH,
            offset_mm=FRONT_OFFSET,
        )
    )
    hem_sig = _top_edge(tree, x=None, y=Y0 + DEPTH)
    tree.append(
        {
            "id": str(HEM_ID),
            "feature": {
                "type": "sheet_metal_hem",
                "version": 1,
                "params": {
                    "edge": _edge_ref(BASE_ID, hem_sig),
                    "hem_type": "closed",
                    "length_mm": HEM_LEG,
                },
            },
        }
    )
    tree.append(hole(tree))
    return tree


def revised(tree: list[dict[str, Any]], width_mm: float) -> list[dict[str, Any]]:
    """*tree* with ONLY the sketch width retyped."""
    out = copy.deepcopy(tree)
    out[0] = sketch(width_mm)
    return out


def strip_names(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """*tree* with every ``topo_name`` removed: a selector authored before names."""
    return json.loads(json.dumps(tree), object_hook=_drop_topo_name)


def _drop_topo_name(node: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in node.items() if key != "topo_name"}


def evaluate(features: list[dict[str, Any]], version: int = 1) -> Any:
    return evaluate_tree(
        EvaluateTreeRequest.model_validate(_request(features, version))
    )


def statuses(evaluation: Any) -> list[tuple[str, str, str | None]]:
    return [
        (str(r.feature_id)[-4:], r.status, r.error.code if r.error else None)
        for r in evaluation.result.features
    ]


def golden_model() -> dict[str, Any]:
    """The golden's request: authored at 60, then the base retyped to 70."""
    return _request(revised(authored_tree(AUTHORED_W), REVISED_W), 2)


if __name__ == "__main__":
    json.dump(golden_model(), sys.stdout, indent=2)
    sys.stdout.write("\n")
