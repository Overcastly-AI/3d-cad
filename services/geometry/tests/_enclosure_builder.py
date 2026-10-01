"""The moulded-enclosure tree of DESIGN-INTENT-REFS, built the way the product
builds it: every pick captured from the selection overlay of the features
before it.

Shared by ``test_design_intent_enclosure.py`` and ``test_naming.py`` (loaded
by file path: the suite runs ``--import-mode=importlib``), and the generator of
the ``revise-width-drafted-fillet-shell-130x80x35`` golden's ``model.json``:

    uv run python services/geometry/tests/_enclosure_builder.py > model.json
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

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000e0c00")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000e0c01")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-0000000e0c02")
DRAFT_ID = uuid.UUID("00000000-0000-0000-0000-0000000e0c03")
FILLET_ID = uuid.UUID("00000000-0000-0000-0000-0000000e0c04")
SHELL_ID = uuid.UUID("00000000-0000-0000-0000-0000000e0c05")

AUTHORED_W = 120.0
REVISED_W = 130.0
DEPTH = 80.0
HEIGHT = 35.0
DRAFT_DEG = 1.5
CORNER_R = 5.0
WALL = 2.0


def _line(eid: str, start: tuple[float, float], end: tuple[float, float]) -> Any:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def sketch(width_mm: float) -> dict[str, Any]:
    """The footprint, centred on the origin. ``width_mm`` is the edited value."""
    hw, hd = width_mm / 2.0, DEPTH / 2.0
    corners = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
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


def extrude() -> dict[str, Any]:
    return {
        "id": str(EXTRUDE_ID),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(SKETCH_ID)},
                "distance_mm": HEIGHT,
                "operation": "add",
                "direction": "normal",
            },
        },
    }


def _face_ref(anchor: uuid.UUID, signature: Any) -> dict[str, Any]:
    return {
        "kind": "subshape",
        "feature_id": str(anchor),
        "subshape_type": "face",
        "selector": {
            "selector_version": 1,
            "signature": signature.model_dump(mode="json"),
        },
    }


def _overlay(features: list[dict[str, Any]]) -> Any:
    """The selection overlay of *features*: the pick side, as the product runs it."""
    return evaluate_overlay(
        OverlayRequest.model_validate({"tree": _request(features, 1)})
    )


def _picked_faces(features: list[dict[str, Any]], normals: list[tuple[float, ...]]):
    """The overlay's planar face signatures whose normal is one of *normals*."""
    picked: list[Any] = []
    for face in _overlay(features).faces:
        sig = face.signature
        if sig is None:
            continue
        n = (sig.normal.x, sig.normal.y, sig.normal.z)
        if any(
            max(abs(a - b) for a, b in zip(n, w, strict=True)) < 1e-9 for w in normals
        ):
            picked.append(sig)
    return picked


def draft(features: list[dict[str, Any]]) -> dict[str, Any]:
    """1.5 deg draft on the two +-X walls, pull +Z from the XY plane."""
    walls = _picked_faces(features, [(1.0, 0.0, 0.0), (-1.0, 0.0, 0.0)])
    assert len(walls) == 2
    return {
        "id": str(DRAFT_ID),
        "feature": {
            "type": "draft",
            "version": 1,
            "params": {
                "angle_deg": DRAFT_DEG,
                "neutral_plane": {"kind": "datum", "base": "XY"},
                "faces": {
                    "kind": "faces",
                    "refs": [_face_ref(EXTRUDE_ID, w) for w in walls],
                },
            },
        },
    }


def fillet(features: list[dict[str, Any]]) -> dict[str, Any]:
    """R5 on the four corner edges: the edges that run from z=0 to z=HEIGHT."""
    corners = [
        edge.signature
        for edge in _overlay(features).edges
        if edge.signature is not None
        and edge.signature.curve == "line"
        and abs(abs(edge.signature.end_a.z - edge.signature.end_b.z) - HEIGHT) < 1e-9
    ]
    assert len(corners) == 4
    return {
        "id": str(FILLET_ID),
        "feature": {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {
                    "kind": "edges",
                    "refs": [
                        {
                            "kind": "subshape",
                            "feature_id": str(DRAFT_ID),
                            "subshape_type": "edge",
                            "selector": {
                                "selector_version": 1,
                                "signature": sig.model_dump(mode="json"),
                            },
                        }
                        for sig in corners
                    ],
                },
                "radius_mm": CORNER_R,
            },
        },
    }


def shell(features: list[dict[str, Any]]) -> dict[str, Any]:
    """A 2 mm wall, open at the top (+Z) face."""
    (top,) = _picked_faces(features, [(0.0, 0.0, 1.0)])
    return {
        "id": str(SHELL_ID),
        "feature": {
            "type": "shell",
            "version": 1,
            "params": {
                "thickness_mm": WALL,
                "faces": {"kind": "faces", "refs": [_face_ref(FILLET_ID, top)]},
            },
        },
    }


def authored_tree(width_mm: float) -> list[dict[str, Any]]:
    """The enclosure built at *width_mm*, every pick captured from the overlay
    of the features before it (exactly how the product captures a pick)."""
    tree: list[dict[str, Any]] = [sketch(width_mm), extrude()]
    tree.append(draft(tree))
    tree.append(fillet(tree))
    tree.append(shell(tree))
    return tree


def revised(tree: list[dict[str, Any]], width_mm: float) -> list[dict[str, Any]]:
    """*tree* with ONLY the sketch width retyped."""
    out = copy.deepcopy(tree)
    out[0] = sketch(width_mm)
    return out


def strip_names(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """*tree* with every ``topo_name`` removed: a selector authored before names."""
    text = json.dumps(tree)
    return json.loads(text, object_hook=_drop_topo_name)


def _drop_topo_name(node: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in node.items() if key != "topo_name"}


def _request(features: list[dict[str, Any]], version: int) -> dict[str, Any]:
    return {
        "part_id": str(PART_ID),
        "tree_version": version,
        "features": features,
        "linear_deflection": 0.1,
    }


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
    """The golden's request: authored at 120, then the width retyped to 130."""
    return _request(revised(authored_tree(AUTHORED_W), REVISED_W), 2)


if __name__ == "__main__":
    json.dump(golden_model(), sys.stdout, indent=2)
    sys.stdout.write("\n")
