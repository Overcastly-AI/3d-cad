"""QA-DRAWING-CENTRE-MARKS — hole centres on a drawing: marks, and dimensions to them.

A drawing that shows a hole only as a circle can give it a diameter, never a
POSITION. Fusion 360, SolidWorks and Onshape mark every circle seen end-on with a
centre mark and let a linear dimension run from an edge to that centre, or from
centre to centre. These tests pin both halves on QA's bracket.

The part is QA's L-bracket (``test_drawings_dims_durable``), sketched on XZ and
extruded 30 mm into -Y, now with TWO Ø8 through holes in the base:

    top view (z up out of the page; y runs 0 .. -30)

     y=0  +--------------------------------+----+   base:    x in [0, W],   z in [0, 8]
          |                                |    |   upright: x in [W-8, W], z in [0, 40]
    y=-10 |                        (A)     |    |   A = (W-20, -10)  — moves with W
          |                                |    |   B = (20,   -20)  — fixed
    y=-20 |    (B)                         |    |
    y=-30 +--------------------------------+----+
          x=0                              W-8  W

Hand values, measured in the top view (its frame is the model's x / y):

    =======================  ==========================  =====================
    dimension                W = 100 (A at x = 80)       W = 80 (A at x = 60)
    =======================  ==========================  =====================
    left edge -> A           80                          60
    back edge (y=0) -> B     20                          20
    A <-> B horizontal       |80 - 20| = 60              |60 - 20| = 40
    A <-> B vertical         |-10 - (-20)| = 10          10
    A <-> B aligned          sqrt(60^2 + 10^2)           sqrt(40^2 + 10^2)
                             = 60.827625303              = 41.231056256
    =======================  ==========================  =====================

The left-edge -> A dimension is the founder's acceptance case: QA moved the hole
with the part (hole at W - 20), and the dimension must follow it to 60.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from ezdxf.document import Drawing
from geometry.drawings import evaluate_drawing_views, place_sheet
from geometry.drawings.compose import (
    STANDARD_VIEWS,
    serialize_dxf,
    serialize_pdf,
    serialize_svg,
)
from geometry.features import evaluate_tree
from geometry.kernel.faces import face_signature_dto
from loft_wire.drawings import (
    ComposedDimensionError,
    ComposedMeasuredDimension,
    ComposeDrawingRequest,
    ComposedSheet,
    ComposedView,
    EvaluateDrawingViewsResult,
)
from loft_wire.features import EdgeSignature, EvaluateTreeRequest

_PART = "00000000-0000-0000-0000-00000000c3a1"
_SKETCH = "00000000-0000-0000-0000-00000000c3a2"
_EXTRUDE = "00000000-0000-0000-0000-00000000c3a3"
_HOLE_A = "00000000-0000-0000-0000-00000000c3a4"
_HOLE_B = "00000000-0000-0000-0000-00000000c3a5"

_EDGE_A = "00000000-0000-0000-0000-00000000d001"
_BACK_B = "00000000-0000-0000-0000-00000000d002"
_HORIZ = "00000000-0000-0000-0000-00000000d003"
_VERT = "00000000-0000-0000-0000-00000000d004"
_ALIGNED = "00000000-0000-0000-0000-00000000d005"

_T = 8.0  # base + upright thickness
_H = 40.0  # overall height
_D = 30.0  # extrude depth (into -Y)
_HOLE_D = 8.0
_B_AT = (20.0, -20.0)
_A_Y = -10.0

#: Float representation bound for an exact prism (the test_drawings_resize posture).
_TOL = 1e-9

_GOLDEN_DIR = Path(__file__).resolve().parent / "compose_centre_marks_goldens"


def _a_at(w: float) -> tuple[float, float]:
    """Hole A sits 20 mm in from the part's right end: x = W - 20."""
    return (w - 20.0, _A_Y)


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
    """The base's top face (z = 8) at W = 100 — what both holes were placed on."""
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


def _hole(feature_id: str, at: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": feature_id,
        "feature": {
            "type": "hole",
            "version": 1,
            "params": {
                "face": _base_top_face_ref(),
                "position": {"x": at[0], "y": at[1], "z": _T},
                "diameter_mm": _HOLE_D,
                "depth": {"kind": "through_all"},
                "type": {"kind": "simple"},
            },
        },
    }


def _features(w: float) -> list[dict[str, Any]]:
    return [*_bracket(w), _hole(_HOLE_A, _a_at(w)), _hole(_HOLE_B, _B_AT)]


def _request(w: float, dimensions: list[dict[str, Any]]) -> ComposeDrawingRequest:
    return ComposeDrawingRequest.model_validate(
        {
            "part_id": _PART,
            "tree_version": 1,
            "features": _features(w),
            "views": list(STANDARD_VIEWS),
            "scale": {"numerator": 1, "denominator": 2},
            "dimensions": dimensions,
            "layout": {
                "size": "A3",
                "orientation": "landscape",
                "projection": "third_angle",
                "title": "QA bracket - hole positions",
                "views": [
                    {
                        "projection": p,
                        "position": {"x_mm": 0.0, "y_mm": 0.0},
                        "auto_place": True,
                    }
                    for p in STANDARD_VIEWS
                ],
            },
            "format": "svg",
        }
    )


def _picked(result: EvaluateDrawingViewsResult, pick: Any) -> EdgeSignature:
    """The `source_edge` of the ONE visible projected edge in the TOP view that
    *pick* accepts — what the sheet stores when the user clicks it."""
    found = {
        edge.source_edge.model_dump_json(): edge.source_edge
        for v in result.views
        if v.view == "top"
        for edge in v.edges
        if edge.source_edge is not None and edge.visible and pick(edge.source_edge)
    }
    assert len(found) == 1, f"expected one picked edge, got {len(found)}"
    return next(iter(found.values()))


def _rim_at(x: float, y: float) -> Any:
    def pick(s: EdgeSignature) -> bool:
        # A full circle stores its seam twice and the antipode as the midpoint, so
        # the centre is their midpoint; the TOP rim is the one at z = 8.
        cx = (s.end_a.x + s.midpoint.x) / 2
        cy = (s.end_a.y + s.midpoint.y) / 2
        return (
            s.curve == "circle"
            and abs(s.end_a.z - _T) < 1e-6
            and abs(cx - x) < 1e-6
            and abs(cy - y) < 1e-6
        )

    return pick


def _left_edge(s: EdgeSignature) -> bool:
    return (
        s.curve == "line"
        and abs(s.end_a.x) < 1e-6
        and abs(s.end_b.x) < 1e-6
        and abs(s.end_a.z - _T) < 1e-6
    )


def _back_edge(s: EdgeSignature) -> bool:
    return (
        s.curve == "line"
        and abs(s.end_a.y) < 1e-6
        and abs(s.end_b.y) < 1e-6
        and abs(s.end_a.z - _T) < 1e-6
    )


def _dimensions() -> list[dict[str, Any]]:
    """The five hole-position dimensions, PICKED off the W = 100 top view."""
    authored = evaluate_drawing_views(_request(100.0, []))
    left = _picked(authored, _left_edge).model_dump(mode="json")
    back = _picked(authored, _back_edge).model_dump(mode="json")
    rim_a = _picked(authored, _rim_at(*_a_at(100.0))).model_dump(mode="json")
    rim_b = _picked(authored, _rim_at(*_B_AT)).model_dump(mode="json")

    def linear(
        dim_id: str, measurement: dict[str, Any], offset: float
    ) -> dict[str, Any]:
        return {
            "id": dim_id,
            "view": "top",
            "dimension": {
                "type": "linear",
                "measurement": measurement,
                "placement": {"offset_mm": offset, "text_pos": None},
            },
        }

    def pair(dim_id: str, orientation: str, offset: float) -> dict[str, Any]:
        return linear(
            dim_id,
            {
                "mode": "centre_to_centre",
                "a": rim_a,
                "b": rim_b,
                "orientation": orientation,
            },
            offset,
        )

    # Placed as a drafter would stack them (sheet mm at 1:2): the two horizontal
    # dimensions in rows 8 and 16 mm above the part, the two vertical ones in
    # columns 8 and 16 mm left of it, the aligned one below, clear of the caption.
    return [
        linear(
            _EDGE_A, {"mode": "edge_to_centre", "edge": left, "centre": rim_a}, 13.0
        ),
        linear(
            _BACK_B, {"mode": "edge_to_centre", "edge": back, "centre": rim_b}, 18.0
        ),
        pair(_HORIZ, "horizontal", 23.5),
        pair(_VERT, "vertical", 41.0),
        pair(_ALIGNED, "aligned", 24.0),
    ]


def _measured(w: float, dims: list[dict[str, Any]]) -> dict[str, Any]:
    evaluation = evaluate_drawing_views(_request(w, dims))
    return {str(d.id): d.measured for d in evaluation.dimensions}


def _compose(request: ComposeDrawingRequest) -> ComposedSheet:
    return place_sheet(
        evaluate_drawing_views(request), request.dimensions, request.layout
    )


def _view(sheet: ComposedSheet, projection: str) -> ComposedView:
    return next(v for v in sheet.views if v.projection == projection)


# --- measurement -----------------------------------------------------------------


def test_hole_positions_measure_the_hand_values() -> None:
    measured = _measured(100.0, _dimensions())
    assert all(m.error is None for m in measured.values()), measured
    assert measured[_EDGE_A].value == pytest.approx(80.0, abs=_TOL)
    assert measured[_BACK_B].value == pytest.approx(20.0, abs=_TOL)
    assert measured[_HORIZ].value == pytest.approx(60.0, abs=_TOL)
    assert measured[_VERT].value == pytest.approx(10.0, abs=_TOL)
    assert measured[_ALIGNED].value == pytest.approx(math.hypot(60, 10), abs=_TOL)
    assert all(m.unit == "mm" and not m.foreshortened for m in measured.values())


def test_the_edge_to_centre_dimension_follows_the_hole_through_w_100_to_80() -> None:
    """THE acceptance case: the left edge -> hole A dimension reads 80, then QA
    changes W 100 -> 80 (hole A at W - 20 moves to x = 60) and it reads 60."""
    dims = _dimensions()
    before = _measured(100.0, dims)
    assert before[_EDGE_A].value == pytest.approx(80.0, abs=_TOL)

    after = _measured(80.0, dims)
    assert all(m.error is None for m in after.values()), {
        k: m.error for k, m in after.items()
    }
    assert after[_EDGE_A].value == pytest.approx(60.0, abs=_TOL)
    assert after[_BACK_B].value == pytest.approx(20.0, abs=_TOL)
    assert after[_HORIZ].value == pytest.approx(40.0, abs=_TOL)
    assert after[_VERT].value == pytest.approx(10.0, abs=_TOL)
    assert after[_ALIGNED].value == pytest.approx(math.hypot(40, 10), abs=_TOL)

    # Hole A MOVED, so its reference re-anchored (honestly reported durable) onto
    # the rim now at x = 60, while the left edge it is measured from is still the
    # x = 0 edge.
    anchor = after[_EDGE_A].anchor
    assert anchor is not None and anchor.tier == "durable"
    assert anchor.primary is not None and anchor.secondary is not None
    assert anchor.primary.end_a.x == pytest.approx(0.0, abs=_TOL)
    assert anchor.primary.end_b.x == pytest.approx(0.0, abs=_TOL)
    centre_x = (anchor.secondary.end_a.x + anchor.secondary.midpoint.x) / 2
    assert centre_x == pytest.approx(60.0, abs=_TOL)


def test_the_composed_sheet_stamps_the_followed_values() -> None:
    dims = _dimensions()
    sheet = _compose(_request(80.0, dims))
    placed = {str(d.dimension_id): d for d in _view(sheet, "top").dimensions}
    assert all(isinstance(d, ComposedMeasuredDimension) for d in placed.values())
    values = {
        k: d.text.value
        for k, d in placed.items()
        if isinstance(d, ComposedMeasuredDimension)
    }
    assert values == {
        _EDGE_A: "60.000",
        _BACK_B: "20.000",
        _HORIZ: "40.000",
        _VERT: "10.000",
        _ALIGNED: "41.231",
    }


def test_a_horizontal_dimension_is_drawn_horizontally_between_the_centres() -> None:
    """The horizontal pitch: a horizontal dimension line whose two ends sit square
    above/below the two centres (witness lines of different lengths)."""
    sheet = _compose(_request(100.0, _dimensions()))
    top = _view(sheet, "top")
    horiz = next(d for d in top.dimensions if str(d.dimension_id) == _HORIZ)
    assert isinstance(horiz, ComposedMeasuredDimension)
    line = next(ln for ln in horiz.lines if ln.role == "dimension")
    assert line.y1 == pytest.approx(line.y2, abs=_TOL)
    marks = sorted(top.centre_marks, key=lambda m: m.cx)
    # The dimension spans exactly the two centres' x (60 mm at 1:2 = 30 sheet mm).
    assert sorted((line.x1, line.x2)) == pytest.approx(
        [marks[0].cx, marks[1].cx], abs=_TOL
    )
    assert abs(line.x2 - line.x1) == pytest.approx(30.0, abs=_TOL)
    witnesses = [ln for ln in horiz.lines if ln.role == "extension"]
    assert len(witnesses) == 2
    assert all(ln.x1 == pytest.approx(ln.x2, abs=_TOL) for ln in witnesses)


def test_auto_placed_hole_dimensions_stand_clear_of_the_part() -> None:
    """A centre is INSIDE the part, so the token offset from it would run the
    dimension line across the part. Auto-placed (no authored offset), every hole
    dimension's line lies outside the view's outline, `_O` = 11 mm beyond it."""
    dims = _dimensions()
    for item in dims:
        item["dimension"]["placement"] = {"offset_mm": 0.0, "text_pos": None}
    sheet = _compose(_request(100.0, dims))
    top = _view(sheet, "top")
    xs = [x for e in top.edges if e.kind == "line" for x in (e.x1, e.x2)]
    ys = [y for e in top.edges if e.kind == "line" for y in (e.y1, e.y2)]
    box = (min(xs), min(ys), max(xs), max(ys))
    for dim in top.dimensions:
        assert isinstance(dim, ComposedMeasuredDimension)
        line = next(ln for ln in dim.lines if ln.role == "dimension")
        mid = ((line.x1 + line.x2) / 2, (line.y1 + line.y2) / 2)
        outside = max(
            box[0] - mid[0], mid[0] - box[2], box[1] - mid[1], mid[1] - box[3]
        )
        if dim.dimension_id is not None and str(dim.dimension_id) == _ALIGNED:
            # A slanted line: its midpoint clears the outline, by less than _O.
            assert outside > 0.0
        else:
            assert outside == pytest.approx(11.0, abs=_TOL)


def test_a_lost_hole_is_an_honest_marker_not_a_number() -> None:
    """Delete hole A: its dimensions are stamped REFERENCE LOST, never a value."""
    dims = _dimensions()
    request = _request(100.0, dims)
    request = request.model_copy(
        update={"features": [f for f in request.features if str(f.id) != _HOLE_A]}
    )
    sheet = _compose(request)
    placed = {str(d.dimension_id): d for d in _view(sheet, "top").dimensions}
    for dim_id in (_EDGE_A, _HORIZ, _VERT, _ALIGNED):
        lost = placed[dim_id]
        assert isinstance(lost, ComposedDimensionError)
        assert lost.code == "subshape_unresolved"
    assert isinstance(placed[_BACK_B], ComposedMeasuredDimension)


def _measure_one(view: str, measurement: dict[str, Any]) -> Any:
    from geometry.drawings.measure import measure_dimension_dto
    from loft_wire.drawings import LinearDimensionParams

    body = evaluate_tree(
        EvaluateTreeRequest.model_validate(
            {"part_id": _PART, "tree_version": 1, "features": _features(100.0)}
        )
    ).body
    assert body is not None
    params = LinearDimensionParams.model_validate(
        {"type": "linear", "measurement": measurement}
    )
    return measure_dimension_dto(body, params, view)  # type: ignore[arg-type]


def test_honest_refusals_never_a_number() -> None:
    """Three ways a hole-centre dimension cannot mean anything, each a typed
    error: a section view (no fixed frame for it yet), an edge the view sees
    end-on (no line to measure square to), and a straight edge named as a
    centre (no centre)."""
    dims = {str(d["id"]): d["dimension"]["measurement"] for d in _dimensions()}
    in_section = _measure_one("section", dims[_HORIZ])
    assert in_section.value is None
    assert in_section.error.code == "dimension_not_placeable"
    # The front view looks along -Y, so the Y-running left edge is a point there.
    end_on = _measure_one("front", dims[_EDGE_A])
    assert end_on.value is None
    assert end_on.error.code == "dimension_not_placeable"
    not_a_hole = _measure_one("top", {**dims[_HORIZ], "a": dims[_EDGE_A]["edge"]})
    assert not_a_hole.value is None
    assert not_a_hole.error.code == "dimension_wrong_type"


def test_iso_view_measures_in_plane_and_flags_foreshortening() -> None:
    """The iso frame is not a model plane: the in-plane value is drawn length,
    so it is flagged (design §3.2), never passed off as a model distance."""
    dims = {str(d["id"]): d["dimension"]["measurement"] for d in _dimensions()}
    iso = _measure_one("iso", dims[_ALIGNED])
    assert iso.error is None and iso.foreshortened is True
    top = _measure_one("top", dims[_ALIGNED])
    assert top.foreshortened is False
    assert top.value == pytest.approx(math.hypot(60, 10), abs=_TOL)


# --- centre marks ----------------------------------------------------------------


def test_every_hole_seen_end_on_gets_one_centre_mark() -> None:
    """Top view: one mark per hole (the two rims of a through hole share it), at
    the hole's centre and sized to it. Front / right see the holes side-on: no
    marks (their circles project to lines)."""
    sheet = _compose(_request(100.0, []))
    top = _view(sheet, "top")
    assert len(top.centre_marks) == 2
    a, b = sorted(top.centre_marks, key=lambda m: -m.cx)
    # Centres are 60 mm apart in x and 10 mm in y at 1:2 (sheet y is down: A at
    # y = -10 is ABOVE B at y = -20 in the view, so a smaller sheet y).
    assert a.cx - b.cx == pytest.approx(30.0, abs=_TOL)
    assert b.cy - a.cy == pytest.approx(5.0, abs=_TOL)
    for mark in (a, b):
        assert mark.r == pytest.approx(_HOLE_D / 2 / 2, abs=_TOL)  # Ø8 at 1:2
        # The ISO cross: 3 segments per arm-axis; reach r + 3 mm, cross ±1.5,
        # gap 1 mm (2 + 3 = 5 mm reach: long dashes 2.5 -> 5 mm).
        horizontal = [ln for ln in mark.lines if ln.y1 == ln.y2 == mark.cy]
        vertical = [ln for ln in mark.lines if ln.x1 == ln.x2 == mark.cx]
        assert len(horizontal) == len(vertical) == 3
        spans = sorted(
            (round(ln.x1 - mark.cx, 9), round(ln.x2 - mark.cx, 9)) for ln in horizontal
        )
        assert spans == [(-5.0, -2.5), (-1.5, 1.5), (2.5, 5.0)]
    for side in ("front", "right"):
        assert _view(sheet, side).centre_marks == []


def test_a_mark_names_the_visible_dimensionable_rim() -> None:
    """The mark's `edge_index` points at the circle a pick on it stores: the
    visible top rim, whose `source_edge` is the hole's dimensionable signature."""
    request = _request(100.0, [])
    evaluation = evaluate_drawing_views(request)
    sheet = place_sheet(evaluation, request.dimensions, request.layout)
    top_eval = next(v for v in evaluation.views if v.view == "top")
    for mark in _view(sheet, "top").centre_marks:
        edge = top_eval.edges[mark.edge_index]
        assert edge.primitive == "circle" and edge.dimensionable and edge.visible
        assert edge.source_edge is not None and edge.source_edge.curve == "circle"


# --- the golden (CLAUDE.md: a new capability ships a golden) ---------------------


def _golden_request() -> ComposeDrawingRequest:
    return ComposeDrawingRequest.model_validate_json(
        (_GOLDEN_DIR / "request.json").read_text(encoding="utf-8")
    )


def _golden_sheet() -> ComposedSheet:
    return _compose(_golden_request())


def test_golden_request_is_the_qa_bracket_with_its_hole_dimensions() -> None:
    """The committed request is exactly this module's W = 100 drawing, so the
    golden cannot drift from the hand values above."""
    assert _golden_request() == _request(100.0, _dimensions())


def test_golden_svg_is_byte_identical() -> None:
    expected = (_GOLDEN_DIR / "sheet.svg").read_text(encoding="utf-8")
    assert serialize_svg(_golden_sheet()) == expected


def test_golden_pdf_is_byte_identical() -> None:
    assert serialize_pdf(_golden_sheet()) == (_GOLDEN_DIR / "sheet.pdf").read_bytes()


def test_golden_dxf_is_byte_identical() -> None:
    assert serialize_dxf(_golden_sheet()) == (_GOLDEN_DIR / "sheet.dxf").read_bytes()


def test_golden_svg_stamps_the_hand_values_and_the_marks() -> None:
    svg = (_GOLDEN_DIR / "sheet.svg").read_text(encoding="utf-8")
    for value in ("80.000", "20.000", "60.000", "10.000", "60.828"):
        assert f'data-dimension-value="{value}"' in svg
    assert svg.count('data-testid="drawing-centre-mark"') == 2


def test_golden_dxf_puts_the_marks_on_the_center_layer(
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    doc = read_dxf((_GOLDEN_DIR / "sheet.dxf").read_bytes())
    assert "CENTER" in {layer.dxf.name for layer in doc.layers}
    centre = [e for e in doc.modelspace() if e.dxf.layer == "CENTER"]
    assert len(centre) == 12  # two marks x two axes x three dashes
    assert all(e.dxftype() == "LINE" for e in centre)
