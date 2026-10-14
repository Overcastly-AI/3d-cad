"""QA-DRAWING-DIMS-DURABLE — drawing dimensions follow their edges through an edit.

QA dimensioned a bracket drawing, changed the part's W from 100 to 80 and 2 of 4
dimensions went "unresolved" — including the 40 mm height, whose edge had only
MOVED (it sits at x = W). The PDF then printed the two "REFERENCE LOST" captions
on top of each other. In Fusion a drawing dimension follows its edge through a
model edit and is lost only when that geometry is truly gone.

The part is an L-bracket sketched on XZ and extruded 30 mm (into -Y):

    z
    40 +            +----+          upright: x in [W-8, W], z in [0, 40]
       |            |    |          base:    x in [0, W],   z in [0, 8]
     8 +------------+    |          Ø8 through hole in the base at (20, -15)
       |                 |
     0 +-----------------+ x
       0               W

and the four dimensions are the ones QA placed, PICKED off the drawing the way the
sheet picks them (the projected edges' `source_edge`):

* overall width  — the bottom front edge, length W          (100 -> 80);
* height         — the upright's outer vertical edge at x=W  (40 -> 40, MOVED 20);
* upright wall   — edge-to-edge, x = W-8 to x = W           (8 -> 8, both MOVED);
* hole           — Ø of the top rim of the hole              (Ø8 -> Ø8).

Hand-computed after W = 80: 80.000, 40.000, 8.000, Ø8.000.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from geometry.drawings import evaluate_drawing_views, place_sheet
from geometry.drawings.compose import STANDARD_VIEWS, serialize_pdf, serialize_svg
from geometry.features import evaluate_tree
from geometry.kernel.faces import face_signature_dto
from loft_wire.drawings import (
    ComposedDimensionError,
    ComposedMeasuredDimension,
    ComposeDrawingRequest,
    ComposedSheet,
    EvaluateDrawingViewsResult,
)
from loft_wire.features import EdgeSignature, EvaluateTreeRequest

_PART = "00000000-0000-0000-0000-000000000001"
_SKETCH = "00000000-0000-0000-0000-0000000000a1"
_EXTRUDE = "00000000-0000-0000-0000-0000000000b1"
_HOLE = "00000000-0000-0000-0000-0000000000c1"

_WIDTH_DIM = "00000000-0000-0000-0000-000000000001"
_HEIGHT_DIM = "00000000-0000-0000-0000-000000000002"
_WALL_DIM = "00000000-0000-0000-0000-000000000003"
_HOLE_DIM = "00000000-0000-0000-0000-000000000004"
_HOLE_R_DIM = "00000000-0000-0000-0000-000000000005"

_T = 8.0  # base + upright thickness
_H = 40.0  # overall height
_D = 30.0  # extrude depth (into -Y)
_HOLE_D = 8.0
_HOLE_AT = (20.0, -15.0)

#: Float representation bound for an exact prism (the test_drawings_resize posture).
_TOL = 1e-9


def _profile(w: float) -> list[dict[str, Any]]:
    pts = [(0.0, 0.0), (w, 0.0), (w, _H), (w - _T, _H), (w - _T, _T), (0.0, _T)]
    return [
        {
            "id": f"e{i + 1}",
            "kind": "line",
            "construction": False,
            "start": {"x": pts[i][0], "y": pts[i][1]},
            "end": {"x": pts[(i + 1) % 6][0], "y": pts[(i + 1) % 6][1]},
        }
        for i in range(6)
    ]


def _bracket(w: float) -> list[dict[str, Any]]:
    return [
        {
            "id": _SKETCH,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "entities": _profile(w),
                    "constraints": [],
                    "plane": {"kind": "datum_plane", "plane": "XZ"},
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
                    "distance_mm": _D,
                    "operation": "add",
                    "direction": "normal",
                },
            },
        },
    ]


def _base_top_face_ref() -> dict[str, Any]:
    """The base's top face (z = 8) at W = 100 — what the hole was placed on."""
    evaluation = evaluate_tree(
        EvaluateTreeRequest.model_validate(
            {"part_id": _PART, "tree_version": 1, "features": _bracket(100.0)}
        )
    )
    assert evaluation.body is not None
    for face in evaluation.body.faces():
        sig = face_signature_dto(face)
        if sig and sig.normal.z > 0.99 and abs(sig.centroid.z - _T) < 1e-6:
            return {
                "kind": "subshape",
                "feature_id": _EXTRUDE,
                "subshape_type": "face",
                "selector": {
                    "selector_version": 1,
                    "signature": sig.model_dump(mode="json"),
                },
            }
    raise AssertionError("no base top face")


def _features(w: float, *, hole: bool = True) -> list[dict[str, Any]]:
    features = _bracket(w)
    if hole:
        features.append(
            {
                "id": _HOLE,
                "feature": {
                    "type": "hole",
                    "version": 1,
                    "params": {
                        "face": _base_top_face_ref(),
                        "position": {"x": _HOLE_AT[0], "y": _HOLE_AT[1], "z": _T},
                        "diameter_mm": _HOLE_D,
                        "depth": {"kind": "through_all"},
                        "type": {"kind": "simple"},
                    },
                },
            }
        )
    return features


def _placements() -> list[dict[str, Any]]:
    return [
        {"projection": p, "position": {"x_mm": 0.0, "y_mm": 0.0}, "auto_place": True}
        for p in STANDARD_VIEWS
    ]


def _request(
    features: list[dict[str, Any]], dimensions: list[dict[str, Any]]
) -> ComposeDrawingRequest:
    return ComposeDrawingRequest.model_validate(
        {
            "part_id": _PART,
            "tree_version": 1,
            "features": features,
            "views": list(STANDARD_VIEWS),
            "scale": {"numerator": 1, "denominator": 2},
            "dimensions": dimensions,
            "layout": {
                "size": "A3",
                "orientation": "landscape",
                "projection": "third_angle",
                "title": "QA bracket",
                "views": _placements(),
            },
            "format": "svg",
        }
    )


_Pick = Callable[[EdgeSignature], bool]


def _picked(
    result: EvaluateDrawingViewsResult, view: str, pick: _Pick
) -> EdgeSignature:
    """The `source_edge` of the ONE projected edge in *view* that *pick* accepts —
    exactly what the sheet stores when the user clicks that edge."""
    found = {
        edge.source_edge.model_dump_json(): edge.source_edge
        for v in result.views
        if v.view == view
        for edge in v.edges
        if edge.source_edge is not None and edge.visible and pick(edge.source_edge)
    }
    assert len(found) == 1, f"expected one picked edge in {view}, got {len(found)}"
    return next(iter(found.values()))


def _vertical_at(x: float, length: float) -> _Pick:
    def pick(sig: EdgeSignature) -> bool:
        return (
            sig.curve == "line"
            and abs(sig.end_a.x - x) < 1e-6
            and abs(sig.end_b.x - x) < 1e-6
            and abs(sig.length_mm - length) < 1e-6
        )

    return pick


def _qa_dimensions() -> list[dict[str, Any]]:
    """The four dimensions QA placed, authored against the W = 100 drawing."""
    authored = evaluate_drawing_views(_request(_features(100.0), []))

    def bottom(s: EdgeSignature) -> bool:
        return (
            s.curve == "line"
            and abs(s.length_mm - 100.0) < 1e-6
            and abs(s.end_a.z) < 1e-6
            and abs(s.end_b.z) < 1e-6
        )

    def top_rim(s: EdgeSignature) -> bool:
        return s.curve == "circle" and abs(s.end_a.z - _T) < 1e-6

    width = _picked(authored, "front", bottom)
    height = _picked(authored, "front", _vertical_at(100.0, _H))
    inner = _picked(authored, "front", _vertical_at(100.0 - _T, _H - _T))
    rim = _picked(authored, "top", top_rim)
    placement = {"offset_mm": 0.0, "text_pos": None}
    return [
        {
            "id": _WIDTH_DIM,
            "view": "front",
            "dimension": {
                "type": "linear",
                "measurement": {
                    "mode": "edge_length",
                    "edge": width.model_dump(mode="json"),
                },
                "placement": placement,
            },
        },
        {
            "id": _HEIGHT_DIM,
            "view": "front",
            "dimension": {
                "type": "linear",
                "measurement": {
                    "mode": "edge_length",
                    "edge": height.model_dump(mode="json"),
                },
                "placement": placement,
            },
        },
        {
            "id": _WALL_DIM,
            "view": "front",
            "dimension": {
                "type": "linear",
                "measurement": {
                    "mode": "edge_to_edge",
                    "edge_a": inner.model_dump(mode="json"),
                    "edge_b": height.model_dump(mode="json"),
                },
                "placement": placement,
            },
        },
        {
            "id": _HOLE_DIM,
            "view": "top",
            "dimension": {
                "type": "diameter",
                "edge": rim.model_dump(mode="json"),
                "placement": placement,
            },
        },
    ]


def _compose(request: ComposeDrawingRequest) -> ComposedSheet:
    evaluation = evaluate_drawing_views(request)
    return place_sheet(
        evaluation, request.dimensions, request.layout, request.annotations
    )


def _by_id(sheet: ComposedSheet) -> dict[str, Any]:
    return {
        str(d.dimension_id): d
        for v in sheet.views
        for d in v.dimensions
        if d.dimension_id is not None
    }


def test_the_picked_reference_carries_the_persistent_names() -> None:
    """The sheet hands out the pick-side signature: a reference picked on the
    drawing carries the part's persistent naming, not only absolute coordinates."""
    height = _qa_dimensions()[1]["dimension"]["measurement"]["edge"]
    assert height["topo_name"] is not None
    assert height["adjacent_faces"] is not None and len(height["adjacent_faces"]) == 2


def test_qa_w_100_to_80_every_dimension_still_resolves() -> None:
    """THE QA reproduction: W 100 -> 80, re-project, all four resolve with the
    hand-computed values (80 / 40 / 8 / Ø8)."""
    dims = _qa_dimensions()
    before = _by_id(_compose(_request(_features(100.0), dims)))
    assert [before[i].text.value for i in (_WIDTH_DIM, _HEIGHT_DIM, _WALL_DIM)] == [
        "100.000",
        "40.000",
        "8.000",
    ]
    assert before[_HOLE_DIM].text.value == "Ø8.000"

    request = _request(_features(80.0), dims)
    evaluation = evaluate_drawing_views(request)
    measured = {str(d.id): d.measured for d in evaluation.dimensions}
    assert all(m.error is None for m in measured.values()), {
        k: m.error for k, m in measured.items()
    }
    assert measured[_WIDTH_DIM].value == pytest.approx(80.0, abs=_TOL)
    assert measured[_HEIGHT_DIM].value == pytest.approx(40.0, abs=_TOL)
    assert measured[_WALL_DIM].value == pytest.approx(8.0, abs=_TOL)
    assert measured[_HOLE_DIM].value == pytest.approx(8.0, abs=_TOL)

    # The height re-anchored onto the MOVED edge, not some other 40 mm edge: the
    # outer vertical edge now at x = 80 (honestly reported as durable).
    height = measured[_HEIGHT_DIM].anchor
    assert height is not None and height.tier == "durable"
    assert height.primary is not None
    assert height.primary.end_a.x == pytest.approx(80.0, abs=_TOL)
    assert height.primary.end_b.x == pytest.approx(80.0, abs=_TOL)
    wall = measured[_WALL_DIM].anchor
    assert wall is not None and wall.primary is not None and wall.secondary is not None
    assert wall.primary.end_a.x == pytest.approx(72.0, abs=_TOL)
    assert wall.secondary.end_a.x == pytest.approx(80.0, abs=_TOL)
    hole = measured[_HOLE_DIM].anchor
    assert hole is not None and hole.tier == "exact"  # the hole did not move

    sheet = place_sheet(
        evaluation, request.dimensions, request.layout, request.annotations
    )
    after = _by_id(sheet)
    assert all(isinstance(d, ComposedMeasuredDimension) for d in after.values())
    assert after[_WIDTH_DIM].text.value == "80.000"
    assert after[_HEIGHT_DIM].text.value == "40.000"
    assert after[_WALL_DIM].text.value == "8.000"
    assert after[_HOLE_DIM].text.value == "Ø8.000"
    assert b"REFERENCE LOST" not in serialize_pdf(sheet)


def test_the_re_projection_is_deterministic() -> None:
    dims = _qa_dimensions()
    first = serialize_svg(_compose(_request(_features(80.0), dims)))
    second = serialize_svg(_compose(_request(_features(80.0), dims)))
    assert first == second


def _boxes_overlap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _error_box(err: ComposedDimensionError) -> tuple[float, float, float, float]:
    """Marker + caption box (Courier 0.6 em + 0.2 mm letter-spacing at 2.4 mm)."""
    assert err.text is not None
    return (
        err.at.x_mm - 2.6,
        min(err.at.y_mm - 2.6, err.text.y_mm - 2.4),
        err.text.x_mm + len(err.message) * (0.6 * 2.4 + 0.2),
        max(err.at.y_mm + 2.6, err.text.y_mm),
    )


def test_a_deleted_hole_loses_only_its_dimensions_and_their_labels_stack() -> None:
    """The geometry is truly gone: delete the hole. Its Ø and R dimensions (both in
    the top view, both falling back to the view centre) are lost; the other three
    still measure; and the two REFERENCE LOST captions no longer print over each
    other or over a placed dimension."""
    dims = _qa_dimensions()
    rim = dims[3]["dimension"]["edge"]
    dims.append(
        {
            "id": _HOLE_R_DIM,
            "view": "top",
            "dimension": {
                "type": "radius",
                "edge": rim,
                "placement": {"offset_mm": 0.0, "text_pos": None},
            },
        }
    )
    sheet = _compose(_request(_features(80.0, hole=False), dims))
    placed = _by_id(sheet)
    assert placed[_WIDTH_DIM].text.value == "80.000"
    assert placed[_HEIGHT_DIM].text.value == "40.000"
    assert placed[_WALL_DIM].text.value == "8.000"
    lost = [placed[_HOLE_DIM], placed[_HOLE_R_DIM]]
    assert all(isinstance(d, ComposedDimensionError) for d in lost)
    assert [d.code for d in lost] == ["subshape_unresolved"] * 2
    assert lost[0].message == "DIAMETER DIM: REFERENCE LOST - RE-PICK THE EDGE"
    assert lost[1].message == "RADIUS DIM: REFERENCE LOST - RE-PICK THE EDGE"

    boxes = [_error_box(d) for d in lost]
    assert not _boxes_overlap(boxes[0], boxes[1])
    # Stacked as a list: same column, the second one row below the first.
    assert lost[1].at.x_mm == lost[0].at.x_mm
    assert lost[1].at.y_mm > lost[0].at.y_mm
    top = next(v for v in sheet.views if v.projection == "top")
    for d in top.dimensions:
        if isinstance(d, ComposedMeasuredDimension):
            lines = [(ln.x1, ln.y1, ln.x2, ln.y2) for ln in d.lines]
            for box in boxes:
                for x1, y1, x2, y2 in lines:
                    seg = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
                    assert not _boxes_overlap(box, seg)
    assert serialize_pdf(sheet).count(b"REFERENCE LOST") == 2


def test_a_legacy_reference_without_names_keeps_its_geometric_tiers() -> None:
    """A reference stored before the sheet handed out names (bare stage-1
    coordinates) behaves exactly as before: the width (grown in place) re-anchors,
    the hole (unchanged) is exact."""
    dims = _qa_dimensions()
    for item in dims:
        dim = item["dimension"]
        refs = [dim.get("edge"), dim.get("measurement", {}).get("edge")]
        for ref in refs:
            if ref is not None:
                ref["adjacent_faces"] = None
                ref["topo_name"] = None
    evaluation = evaluate_drawing_views(_request(_features(80.0), [dims[0], dims[3]]))
    measured = {str(d.id): d.measured for d in evaluation.dimensions}
    assert measured[_WIDTH_DIM].value == pytest.approx(80.0, abs=_TOL)
    assert measured[_HOLE_DIM].value == pytest.approx(8.0, abs=_TOL)


def test_part_id_is_a_uuid() -> None:
    assert uuid.UUID(_PART)
