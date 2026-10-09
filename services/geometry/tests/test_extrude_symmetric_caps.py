# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""A symmetric extrude's caps keep the sides its ``direction`` names.

Review of 3738c00 (blocking): the symmetric prism always ran along the normal,
so its ``end`` cap sat at +d/2 whatever the row said. On a one-sided REVERSE
extrude ``end`` is the -normal cap, so toggling such a row to symmetric moved a
fillet picked on ``end`` to the opposite side, silently, and a face-seated
reverse cut's ``end`` floor became the cap in the air. Each case below derives
the expected cap position by hand: on XY (normal +Z) a one-sided extrude of
depth d runs z in [0, d] (normal) or [-d, 0] (reverse) with ``start`` at z = 0;
symmetric runs z in [-d/2, d/2] with ``start`` on the side opposite ``end``.
"""

import uuid
from typing import Any

import pytest
from build123d import GeomType
from geometry.features import evaluate_tree
from geometry.kernel.naming import face_name
from geometry.overlay import evaluate_overlay
from loft_wire.features import EvaluateTreeRequest
from loft_wire.overlay import OverlayRequest

PART = uuid.UUID(int=0x5C00)
SKETCH = uuid.UUID(int=0x5C01)
EXTRUDE = uuid.UUID(int=0x5C02)
DATUM = uuid.UUID(int=0x5C03)
POCKET_SKETCH = uuid.UUID(int=0x5C04)
CUT = uuid.UUID(int=0x5C05)
FILLET = uuid.UUID(int=0x5C06)


def _rect(fid: uuid.UUID, x0: float, y0: float, w: float, h: float, plane: Any):
    pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    entities = [
        {
            "id": f"e{i + 1}",
            "kind": "line",
            "start": {"x": pts[i][0], "y": pts[i][1]},
            "end": {"x": pts[(i + 1) % 4][0], "y": pts[(i + 1) % 4][1]},
        }
        for i in range(4)
    ]
    return {
        "id": str(fid),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {"plane": plane, "entities": entities, "constraints": []},
        },
    }


def _extrude(fid: uuid.UUID, profile: uuid.UUID, depth: float, **params: Any):
    return {
        "id": str(fid),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile)},
                "distance_mm": depth,
                **params,
            },
        },
    }


def _request(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "part_id": str(PART),
        "tree_version": 1,
        "features": features,
        "linear_deflection": 0.1,
    }


def _evaluate(features: list[dict[str, Any]]) -> Any:
    evaluation = evaluate_tree(EvaluateTreeRequest.model_validate(_request(features)))
    assert all(r.status == "ok" for r in evaluation.result.features), [
        (str(r.feature_id)[-4:], r.error) for r in evaluation.result.features
    ]
    return evaluation


def _cap_z(evaluation: Any, feature: uuid.UUID, cap: str) -> float:
    """The z of the planar face named ``<feature>:<cap>`` on the body."""
    wanted = face_name(feature, cap)
    found = [
        face.center().Z
        for face, name in zip(
            evaluation.body.faces(), evaluation.face_names(), strict=True
        )
        if name == wanted
    ]
    assert len(found) == 1, (cap, found)
    return found[0]


def _block_tree(direction: str, extent: str) -> list[dict[str, Any]]:
    xy = {"kind": "datum_plane", "plane": "XY"}
    params: dict[str, Any] = {"operation": "add", "direction": direction}
    if extent == "symmetric":
        params["extent"] = "symmetric"
    return [_rect(SKETCH, 0, 0, 40, 25, xy), _extrude(EXTRUDE, SKETCH, 10.0, **params)]


@pytest.mark.parametrize(
    ("direction", "extent", "start", "end"),
    [
        ("normal", "one_side", 0.0, 10.0),
        ("reverse", "one_side", 0.0, -10.0),
        ("normal", "symmetric", -5.0, 5.0),
        # The blocker: `end` stays on the -normal side, as one-sided reverse.
        ("reverse", "symmetric", 5.0, -5.0),
    ],
)
def test_add_caps_keep_their_sides(
    direction: str, extent: str, start: float, end: float
) -> None:
    evaluation = _evaluate(_block_tree(direction, extent))
    assert _cap_z(evaluation, EXTRUDE, "start") == pytest.approx(start, abs=1e-9)
    assert _cap_z(evaluation, EXTRUDE, "end") == pytest.approx(end, abs=1e-9)


def _pocket_tree(direction: str, extent: str) -> list[dict[str, Any]]:
    """A 40x25x20 block, then a 10x10 pocket cut from a datum on its top face
    (XY offset 20). One-sided reverse 6 reaches z = 14; symmetric 12 reaches
    z in [14, 26] (the top half in air), the floor at z = 14 either way."""
    xy = {"kind": "datum_plane", "plane": "XY"}
    datum = {
        "id": str(DATUM),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {"base": "XY", "offset_mm": 20.0, "flip": False},
        },
    }
    on_top = {"kind": "feature", "feature_id": str(DATUM)}
    params: dict[str, Any] = {"operation": "cut", "direction": direction}
    depth = 6.0
    if extent == "symmetric":
        params["extent"] = "symmetric"
        depth = 12.0
    return [
        _rect(SKETCH, 0, 0, 40, 25, xy),
        _extrude(EXTRUDE, SKETCH, 20.0, operation="add", direction="normal"),
        datum,
        _rect(POCKET_SKETCH, 15, 7.5, 10, 10, on_top),
        _extrude(CUT, POCKET_SKETCH, depth, **params),
    ]


@pytest.mark.parametrize("extent", ["one_side", "symmetric"])
def test_reverse_cut_floor_stays_the_end_cap(extent: str) -> None:
    """The pocket floor (z = 14) is the cut's ``end`` cap in both extents."""
    evaluation = _evaluate(_pocket_tree("reverse", extent))
    assert _cap_z(evaluation, CUT, "end") == pytest.approx(14.0, abs=1e-9)


def test_normal_symmetric_cut_floor_is_the_start_cap() -> None:
    """Forward symmetric: the sweep starts at z = 14, so the floor is ``start``."""
    evaluation = _evaluate(_pocket_tree("normal", "symmetric"))
    assert _cap_z(evaluation, CUT, "start") == pytest.approx(14.0, abs=1e-9)


def _end_cap_edge(features: list[dict[str, Any]]) -> Any:
    """The overlay's picked edge on the reverse block's ``end`` cap (z = -10)
    along y = 0: what a user clicks to round that edge."""
    overlay = evaluate_overlay(
        OverlayRequest.model_validate({"tree": _request(features)})
    )
    found = [
        edge.signature
        for edge in overlay.edges
        if edge.signature.curve == "line"
        and all(
            abs(p.z + 10.0) < 1e-9 and abs(p.y) < 1e-9
            for p in (edge.signature.end_a, edge.signature.end_b)
        )
    ]
    assert len(found) == 1, found
    return found[0]


def test_a_fillet_on_the_end_cap_survives_the_toggle_to_symmetric() -> None:
    """Round the reverse block's bottom (``end``) edge, then make it symmetric.

    The fillet must follow its edge to z = -5 (the -normal cap, still ``end``),
    not jump to z = +5. Its round face spans z in [-5, -3] (R2).
    """
    authored = _block_tree("reverse", "one_side")
    signature = _end_cap_edge(authored)
    assert signature.topo_name is not None
    fillet = {
        "id": str(FILLET),
        "feature": {
            "type": "fillet",
            "version": 1,
            "params": {
                "edges": {
                    "kind": "edges",
                    "refs": [
                        {
                            "kind": "subshape",
                            "feature_id": str(EXTRUDE),
                            "subshape_type": "edge",
                            "selector": {
                                "selector_version": 1,
                                "signature": signature.model_dump(mode="json"),
                            },
                        }
                    ],
                },
                "radius_mm": 2.0,
            },
        },
    }
    toggled = [*_block_tree("reverse", "symmetric"), fillet]
    evaluation = _evaluate(toggled)
    rounds = [
        face for face in evaluation.body.faces() if face.geom_type != GeomType.PLANE
    ]
    assert len(rounds) == 1
    box = rounds[0].bounding_box()
    assert pytest.approx((-5.0, -3.0), abs=1e-6) == (box.min.Z, box.max.Z)
    assert pytest.approx((0.0, 2.0), abs=1e-6) == (box.min.Y, box.max.Y)
