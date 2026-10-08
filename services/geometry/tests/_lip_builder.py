"""The projected-rim lip of SKETCH-PROJECT-EDGES, built the way the product
builds it: every pick captured from the selection overlay of the features
before it.

A 120 x 80 x 35 box, R5 vertical corner rounds, a 2 mm shell open at the top,
an ``on_face`` datum on the rim, and a sketch on it that PROJECTS the rim's
outer and inner loops (8 lines, 8 arcs), extruded 3 mm into a lip. The INSET
variant keeps the outer loop as construction and draws a free loop 1 mm inside
it (R4 arcs concentric with the projected R5 corners, each line held 1 mm off
its projected edge by a point-to-line distance), so the lip is 1 mm wide.

Shared by ``test_sketch_projection_revision.py`` and ``test_sketch_projection``
(loaded by file path: the suite runs ``--import-mode=importlib``), and the
generator of the two goldens' ``model.json``:

    uv run python services/geometry/tests/_lip_builder.py full > model.json
    uv run python services/geometry/tests/_lip_builder.py inset > model.json

The stored entity coordinates are computed HERE from the picked signatures (a
line's ends, an arc's circumcentre and counter-clockwise ends), as the web
computes them from the overlay: they are an input, never the code under test.
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

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000f1000")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000f1001")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-0000000f1002")
FILLET_ID = uuid.UUID("00000000-0000-0000-0000-0000000f1003")
SHELL_ID = uuid.UUID("00000000-0000-0000-0000-0000000f1004")
DATUM_ID = uuid.UUID("00000000-0000-0000-0000-0000000f1005")
RIM_SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000f1006")
LIP_ID = uuid.UUID("00000000-0000-0000-0000-0000000f1007")

AUTHORED_W = 120.0
REVISED_W = 130.0
DEPTH = 80.0
HEIGHT = 35.0
CORNER_R = 5.0
WALL = 2.0
LIP_H = 3.0
INSET = 1.0

_SIDES = ("b", "r", "t", "l")
_CORNERS = ("br", "tr", "tl", "bl")


def _p(x: float, y: float) -> dict[str, float]:
    return {"x": x, "y": y}


def _line(eid: str, start: tuple[float, float], end: tuple[float, float]) -> Any:
    return {"id": eid, "kind": "line", "start": _p(*start), "end": _p(*end)}


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


def extrude(feature_id: uuid.UUID, profile: uuid.UUID, mm: float) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile)},
                "distance_mm": mm,
                "operation": "add",
                "direction": "normal",
            },
        },
    }


def _subshape(anchor: uuid.UUID, kind: str, signature: Any) -> dict[str, Any]:
    return {
        "kind": "subshape",
        "feature_id": str(anchor),
        "subshape_type": kind,
        "selector": {
            "selector_version": 1,
            "signature": signature.model_dump(mode="json"),
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


def _up_faces(features: list[dict[str, Any]], z: float) -> list[Any]:
    """The overlay's planar faces facing +Z at height *z*."""
    return [
        face.signature
        for face in _overlay(features).faces
        if face.signature is not None
        and abs(face.signature.normal.z - 1.0) < 1e-9
        and abs(face.signature.centroid.z - z) < 1e-9
    ]


def fillet(features: list[dict[str, Any]]) -> dict[str, Any]:
    """R5 on the four vertical corner edges."""
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
                    "refs": [_subshape(EXTRUDE_ID, "edge", s) for s in corners],
                },
                "radius_mm": CORNER_R,
            },
        },
    }


def shell(features: list[dict[str, Any]]) -> dict[str, Any]:
    """A 2 mm wall, open at the top face."""
    (top,) = _up_faces(features, HEIGHT)
    return {
        "id": str(SHELL_ID),
        "feature": {
            "type": "shell",
            "version": 1,
            "params": {
                "thickness_mm": WALL,
                "faces": {"kind": "faces", "refs": [_subshape(FILLET_ID, "face", top)]},
            },
        },
    }


def datum(features: list[dict[str, Any]]) -> tuple[dict[str, Any], Any]:
    """The ``on_face`` datum on the rim, and the rim's signature."""
    (rim,) = _up_faces(features, HEIGHT)
    feature = {
        "id": str(DATUM_ID),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {
                "kind": "on_face",
                "offset_mm": 0.0,
                "face": _subshape(SHELL_ID, "face", rim),
            },
        },
    }
    return feature, rim


def _circumcentre(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
) -> tuple[float, float]:
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    ux = (
        (ax * ax + ay * ay) * (by - cy)
        + (bx * bx + by * by) * (cy - ay)
        + (cx * cx + cy * cy) * (ay - by)
    ) / d
    uy = (
        (ax * ax + ay * ay) * (cx - bx)
        + (bx * bx + by * by) * (ax - cx)
        + (cx * cx + cy * cy) * (bx - ax)
    ) / d
    return (ux, uy)


def _name(sig: Any, hw: float, hd: float) -> str:
    """``o``/``i`` (outer/inner loop) plus the side or corner the edge is on."""
    loop = "o"
    if sig.curve == "line":
        horizontal = abs(sig.end_a.y - sig.end_b.y) < 1e-9
        offset = abs(sig.end_a.y) if horizontal else abs(sig.end_a.x)
        if abs(offset - (hd if horizontal else hw)) > 1e-6:
            loop = "i"
        if horizontal:
            return loop + ("b" if sig.end_a.y < 0 else "t")
        return loop + ("l" if sig.end_a.x < 0 else "r")
    if abs(sig.length_mm - CORNER_R * math.pi / 2.0) > 1e-6:
        loop = "i"
    vertical = "b" if sig.midpoint.y < 0 else "t"
    horizontal = "l" if sig.midpoint.x < 0 else "r"
    return loop + vertical + horizontal


def _projected(sig: Any, origin: tuple[float, float], name: str) -> dict[str, Any]:
    """The entity the web stores for a picked rim edge: the plane is the rim's
    (normal +Z, so its x axis is world +X), origin at the rim's centroid."""

    def local(p: Any) -> tuple[float, float]:
        return (p.x - origin[0], p.y - origin[1])

    a, b, mid = local(sig.end_a), local(sig.end_b), local(sig.midpoint)
    link = {"edge": _subshape(SHELL_ID, "edge", sig)}
    if sig.curve == "line":
        return {**_line(name, a, b), "projection": link}
    centre = _circumcentre(a, b, mid)
    cross = (a[0] - centre[0]) * (b[1] - centre[1]) - (a[1] - centre[1]) * (
        b[0] - centre[0]
    )
    start, end = (a, b) if cross > 0 else (b, a)
    return {
        "id": name,
        "kind": "arc",
        "center": _p(*centre),
        "start": _p(*start),
        "end": _p(*end),
        "projection": link,
    }


def rim_entities(features: list[dict[str, Any]], width_mm: float) -> list[Any]:
    """The 16 rim edges of *features*' body, projected and named, sorted."""
    _datum, rim = datum(features)
    origin = (rim.centroid.x, rim.centroid.y)
    hw, hd = width_mm / 2.0, DEPTH / 2.0
    edges = [
        edge.signature
        for edge in _overlay(features).edges
        if edge.signature is not None
        and abs(edge.signature.end_a.z - HEIGHT) < 1e-9
        and abs(edge.signature.end_b.z - HEIGHT) < 1e-9
    ]
    assert len(edges) == 16, len(edges)
    out = [_projected(sig, origin, _name(sig, hw, hd)) for sig in edges]
    names = sorted(e["id"] for e in out)
    assert len(set(names)) == 16, names
    return sorted(out, key=lambda e: e["id"])


def _rim_sketch(entities: list[Any], constraints: list[Any]) -> dict[str, Any]:
    return {
        "id": str(RIM_SKETCH_ID),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "feature", "feature_id": str(DATUM_ID)},
                "entities": entities,
                "constraints": constraints,
            },
        },
    }


def _inset_loop(width_mm: float) -> tuple[list[Any], list[Any]]:
    """The free loop 1 mm inside the outer rim, and the constraints that hold
    it there: endpoint tangency at each join, each arc's centre on its
    projected corner's centre, each line 1 mm off its projected side."""
    hw, hd = width_mm / 2.0 - INSET, DEPTH / 2.0 - INSET
    r = CORNER_R - INSET
    cx, cy = hw - r, hd - r
    lines = {
        "b": ((-cx, -hd), (cx, -hd)),
        "r": ((hw, -cy), (hw, cy)),
        "t": ((cx, hd), (-cx, hd)),
        "l": ((-hw, cy), (-hw, -cy)),
    }
    arcs = {
        "br": ((cx, -cy), (cx, -hd), (hw, -cy)),
        "tr": ((cx, cy), (hw, cy), (cx, hd)),
        "tl": ((-cx, cy), (-cx, hd), (-hw, cy)),
        "bl": ((-cx, -cy), (-hw, -cy), (-cx, -hd)),
    }
    entities: list[Any] = [_line(f"n{s}", *lines[s]) for s in _SIDES]
    entities += [
        {
            "id": f"n{c}",
            "kind": "arc",
            "center": _p(*arcs[c][0]),
            "start": _p(*arcs[c][1]),
            "end": _p(*arcs[c][2]),
        }
        for c in _CORNERS
    ]
    constraints: list[Any] = []
    for side, corner in zip(_SIDES, _CORNERS, strict=True):
        nxt = _SIDES[(_SIDES.index(side) + 1) % 4]
        constraints.append(
            {
                "kind": "tangent",
                "a": f"n{side}",
                "b": f"n{corner}",
                "a_point": "end",
                "b_point": "start",
            }
        )
        constraints.append(
            {
                "kind": "tangent",
                "a": f"n{corner}",
                "b": f"n{nxt}",
                "a_point": "end",
                "b_point": "start",
            }
        )
        constraints.append(
            {
                "kind": "coincident",
                "a": {"entity": f"n{corner}", "point": "center"},
                "b": {"entity": f"o{corner}", "point": "center"},
            }
        )
        constraints.append(
            {
                "kind": "point_line_distance",
                "point": {"entity": f"n{side}", "point": "start"},
                "line": f"o{side}",
                "value_mm": INSET,
            }
        )
    return entities, constraints


def authored_tree(width_mm: float, *, inset: bool = False) -> list[dict[str, Any]]:
    """The lip built at *width_mm*, every pick captured from the overlay of
    the features before it (exactly how the product captures a pick)."""
    tree: list[dict[str, Any]] = [
        sketch(width_mm),
        extrude(EXTRUDE_ID, SKETCH_ID, HEIGHT),
    ]
    tree.append(fillet(tree))
    tree.append(shell(tree))
    feature, _rim = datum(tree)
    tree.append(feature)
    projected = rim_entities(tree, width_mm)
    constraints: list[Any] = []
    if inset:
        for entity in projected:
            if entity["id"].startswith("o"):
                entity["construction"] = True
        free, constraints = _inset_loop(width_mm)
        projected += free
    tree.append(_rim_sketch(projected, constraints))
    tree.append(extrude(LIP_ID, RIM_SKETCH_ID, LIP_H))
    return tree


def revised(tree: list[dict[str, Any]], width_mm: float) -> list[dict[str, Any]]:
    """*tree* with ONLY the base sketch width retyped."""
    out = copy.deepcopy(tree)
    out[0] = sketch(width_mm)
    return out


def strip_projection(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """*tree* with every ``projection`` removed: the same coordinates, unlinked."""
    out = copy.deepcopy(tree)
    for item in out:
        if item["feature"]["type"] == "sketch":
            for entity in item["feature"]["params"]["entities"]:
                entity.pop("projection", None)
    return out


def evaluate(features: list[dict[str, Any]], version: int = 1) -> Any:
    return evaluate_tree(
        EvaluateTreeRequest.model_validate(_request(features, version))
    )


def statuses(evaluation: Any) -> list[tuple[str, str, str | None]]:
    return [
        (str(r.feature_id)[-4:], r.status, r.error.code if r.error else None)
        for r in evaluation.result.features
    ]


def golden_model(*, inset: bool) -> dict[str, Any]:
    """A golden's request: authored at 120, then the width retyped to 130."""
    return _request(revised(authored_tree(AUTHORED_W, inset=inset), REVISED_W), 2)


if __name__ == "__main__":
    json.dump(golden_model(inset=sys.argv[1:] == ["inset"]), sys.stdout, indent=2)
    sys.stdout.write("\n")
