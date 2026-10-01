"""The impeller tree of DESIGN-INTENT-REFS step 2, built the way the product
builds it: every pick captured from the selection overlay of the features
before it.

The hard-parts QA impeller (docs/VISION.md): a 20 mm hub, a twisted ruled-loft
blade patterned 7x about the hub axis, a bore with a keyway, and an R1 fillet
on the 14 blade-root edges (hub cylinder meeting a B-spline blade side, curve
kind "other"). The edit is the hub diameter, 40 -> 44.

Shared by ``test_design_intent_impeller.py`` and ``test_naming.py`` (loaded by
file path: the suite runs ``--import-mode=importlib``), and the generator of the
``revise-hub-d44-blade-root-fillet`` golden's ``model.json``:

    uv run python services/geometry/tests/_impeller_builder.py > model.json
"""

import copy
import json
import math
import sys
import uuid
from typing import Any

from geometry.features import evaluate_tree
from geometry.overlay import evaluate_overlay
from loft_wire.features import EvaluateTreeRequest
from loft_wire.overlay import OverlayRequest


def _id(tail: int) -> uuid.UUID:
    return uuid.UUID(f"00000000-0000-0000-0000-0000000e1{tail:03x}")


PART_ID = _id(0)
HUB_SKETCH_ID = _id(1)
HUB_ID = _id(2)
ROOT_PLANE_ID = _id(3)
ROOT_SKETCH_ID = _id(4)
TIP_PLANE_ID = _id(5)
TIP_SKETCH_ID = _id(6)
LOFT_ID = _id(7)
PATTERN_ID = _id(8)
BORE_SKETCH_ID = _id(9)
BORE_ID = _id(10)
KEY_SKETCH_ID = _id(11)
KEY_ID = _id(12)
FILLET_ID = _id(13)

AUTHORED_D = 40.0
REVISED_D = 44.0
HUB_H = 20.0
BLADES = 7
#: Each blade section is a 3 mm x 35 mm radial rectangle from r=15 (inside the
#: hub at either diameter) to r=50, turned ROOT_DEG about the hub axis (so no
#: blade root crosses the hub cylinder's seam at +X); the tip section is turned
#: TWIST_DEG further, so the ruled sides are twisted B-spline faces.
BLADE_R0, BLADE_R1, BLADE_T = 15.0, 50.0, 3.0
ROOT_DEG, TWIST_DEG = 10.0, 20.0
BORE_D = 12.0
#: The keyway: 4 mm wide, reaching 2.5 mm past the bore at +X.
KEY_W, KEY_DEPTH = 4.0, 2.5
ROOT_R = 1.0


def _line(eid: str, start: tuple[float, float], end: tuple[float, float]) -> Any:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def _sketch(
    sketch_id: uuid.UUID, plane: dict[str, Any], entities: list[Any]
) -> dict[str, Any]:
    return {
        "id": str(sketch_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {"plane": plane, "entities": entities, "constraints": []},
        },
    }


_XY = {"kind": "datum_plane", "plane": "XY"}


def _rectangle(prefix: str, corners: list[tuple[float, float]]) -> list[Any]:
    return [
        _line(f"{prefix}{i + 1}", corners[i], corners[(i + 1) % 4]) for i in range(4)
    ]


def _extrude(
    feature_id: uuid.UUID, sketch_id: uuid.UUID, operation: str
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(sketch_id)},
                "distance_mm": HUB_H,
                "operation": operation,
                "direction": "normal",
            },
        },
    }


def _datum(feature_id: uuid.UUID, offset: float) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {"base": "XY", "offset_mm": offset, "flip": False},
        },
    }


def hub_sketch(diameter_mm: float) -> dict[str, Any]:
    """The hub circle. ``diameter_mm`` is the edited value."""
    circle = {
        "id": "c1",
        "kind": "circle",
        "center": {"x": 0.0, "y": 0.0},
        "radius": diameter_mm / 2.0,
    }
    return _sketch(HUB_SKETCH_ID, _XY, [circle])


def _blade_corners(turn_deg: float) -> list[tuple[float, float]]:
    c, s = math.cos(math.radians(turn_deg)), math.sin(math.radians(turn_deg))
    half = BLADE_T / 2.0
    raw = [(BLADE_R0, -half), (BLADE_R1, -half), (BLADE_R1, half), (BLADE_R0, half)]
    return [(x * c - y * s, x * s + y * c) for x, y in raw]


def blade_features() -> list[dict[str, Any]]:
    """Plane1/Sketch2 (root), Plane2/Sketch3 (tip), Loft1, Pattern1 (7x)."""
    root_plane = {"kind": "feature", "feature_id": str(ROOT_PLANE_ID)}
    tip_plane = {"kind": "feature", "feature_id": str(TIP_PLANE_ID)}
    return [
        _datum(ROOT_PLANE_ID, 0.0),
        _sketch(ROOT_SKETCH_ID, root_plane, _rectangle("r", _blade_corners(ROOT_DEG))),
        _datum(TIP_PLANE_ID, HUB_H),
        _sketch(
            TIP_SKETCH_ID,
            tip_plane,
            _rectangle("t", _blade_corners(ROOT_DEG + TWIST_DEG)),
        ),
        {
            "id": str(LOFT_ID),
            "feature": {
                "type": "loft",
                "version": 1,
                "params": {
                    "profiles": [
                        {"kind": "feature", "feature_id": str(ROOT_SKETCH_ID)},
                        {"kind": "feature", "feature_id": str(TIP_SKETCH_ID)},
                    ],
                    "operation": "add",
                },
            },
        },
        {
            "id": str(PATTERN_ID),
            "feature": {
                "type": "pattern",
                "version": 1,
                "params": {
                    "pattern": {
                        "kind": "circular",
                        "axis_point": {"x": 0.0, "y": 0.0, "z": 0.0},
                        "axis_direction": {"x": 0.0, "y": 0.0, "z": 1.0},
                        "angle_deg": 360.0,
                        "count": BLADES,
                    },
                    "scope": {
                        "kind": "features",
                        "features": [{"kind": "feature", "feature_id": str(LOFT_ID)}],
                    },
                },
            },
        },
    ]


def bore_features() -> list[dict[str, Any]]:
    """Sketch4/Extrude2 (the Ø12 bore) and Sketch5/Extrude3 (the keyway)."""
    bore = {
        "id": "b1",
        "kind": "circle",
        "center": {"x": 0.0, "y": 0.0},
        "radius": BORE_D / 2.0,
    }
    inner, outer, half = BORE_D / 4.0, BORE_D / 2.0 + KEY_DEPTH, KEY_W / 2.0
    key = _rectangle(
        "k", [(inner, -half), (outer, -half), (outer, half), (inner, half)]
    )
    return [
        _sketch(BORE_SKETCH_ID, _XY, [bore]),
        _extrude(BORE_ID, BORE_SKETCH_ID, "cut"),
        _sketch(KEY_SKETCH_ID, _XY, key),
        _extrude(KEY_ID, KEY_SKETCH_ID, "cut"),
    ]


def _overlay(features: list[dict[str, Any]]) -> Any:
    """The selection overlay of *features*: the pick side, as the product runs it."""
    return evaluate_overlay(
        OverlayRequest.model_validate({"tree": _request(features, 1)})
    )


def root_edges(features: list[dict[str, Any]], hub_d: float) -> list[Any]:
    """The overlay's blade-root edges: curve kind "other", lying on the hub
    cylinder (every sample of the edge at radius hub_d / 2)."""
    out: list[Any] = []
    for edge in _overlay(features).edges:
        sig = edge.signature
        if sig is None or sig.curve != "other":
            continue
        points = (sig.end_a, sig.end_b, sig.midpoint)
        if all(abs(math.hypot(p.x, p.y) - hub_d / 2.0) < 1e-6 for p in points):
            out.append(sig)
    return out


def fillet(features: list[dict[str, Any]], hub_d: float) -> dict[str, Any]:
    """R1 on the 14 blade-root edges, picked at hub diameter *hub_d*."""
    roots = root_edges(features, hub_d)
    assert len(roots) == 2 * BLADES, len(roots)
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
                            "feature_id": str(KEY_ID),
                            "subshape_type": "edge",
                            "selector": {
                                "selector_version": 1,
                                "signature": sig.model_dump(mode="json"),
                            },
                        }
                        for sig in roots
                    ],
                },
                "radius_mm": ROOT_R,
            },
        },
    }


def body_features(hub_d: float) -> list[dict[str, Any]]:
    """Every feature before the fillet, at hub diameter *hub_d*."""
    return [
        hub_sketch(hub_d),
        _extrude(HUB_ID, HUB_SKETCH_ID, "add"),
        *blade_features(),
        *bore_features(),
    ]


def authored_tree(hub_d: float) -> list[dict[str, Any]]:
    """The impeller built at hub diameter *hub_d*, the fillet's picks captured
    from the overlay of the features before it."""
    tree = body_features(hub_d)
    tree.append(fillet(tree, hub_d))
    return tree


def revised(tree: list[dict[str, Any]], hub_d: float) -> list[dict[str, Any]]:
    """*tree* with ONLY the hub diameter retyped."""
    out = copy.deepcopy(tree)
    out[0] = hub_sketch(hub_d)
    return out


def strip_names(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """*tree* with every ``topo_name`` removed: a selector authored before names."""
    return json.loads(json.dumps(tree), object_hook=_drop_topo_name)


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
    """The golden's request: authored at Ø40, then the hub retyped to Ø44."""
    return _request(revised(authored_tree(AUTHORED_D), REVISED_D), 2)


if __name__ == "__main__":
    json.dump(golden_model(), sys.stdout, indent=2)
    sys.stdout.write("\n")
