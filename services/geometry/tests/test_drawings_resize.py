"""The RESIZE gates — audit N1 + N2 only appear after a model change.

Both P0s the 2026-07-30 product audit measured against the drawing as a DELIVERABLE
are invisible to a test that composes a sheet once:

* **N1** — a dimension on the 84 mm overall-length edge composed ``84.000``; widening
  the plate 100 → 120 (the part rebuilt cleanly) turned it into
  ``code:"subshape_unresolved"``, printed as a 2.6 mm dashed circle holding a ``!``.
  The Ø dimension survived *because its hole did not change* — i.e. the dimensions
  destroyed were exactly the ones that measured what you changed.
* **N2** — the four standard views cleared by 0.70 mm before the widening and
  OVERLAPPED by 6.33 x 60.00 mm after it, with 82.8 mm of sheet empty to the right,
  and the overlapping sheet exported to PDF/DXF silently.

So every test here composes the SAME drawing against TWO trees (before/after the
edit) and asserts on the second sheet. They fail on the pre-fix composer.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import pytest
from ezdxf.document import Drawing
from geometry.drawings import evaluate_drawing_views, place_sheet
from geometry.drawings.compose import (
    MIN_VIEW_CLEARANCE_MM,
    SHEET_MARGIN_MM,
    STANDARD_VIEWS,
    VIEW_GUTTER_MM,
    serialize_dxf,
    serialize_pdf,
    serialize_svg,
)
from py_kit.schemas.drawings import (
    ComposedDimensionError,
    ComposedMeasuredDimension,
    ComposeDrawingRequest,
    ComposedSheet,
    ViewProjection,
)

#: Sheet-mm comparison bound. Placement is exact rational arithmetic over exact prism
#: extents, so residuals are float representation only (the test_drawings_compose
#: posture — documented, not ad-hoc).
_TOL = 1e-9

#: Plate depth / thickness held constant across the widening (only the width changes —
#: the one-number edit the audit performed).
_DEPTH = 60.0
_THICK = 10.0

#: The hole the plate carries, in sketch coordinates.
_HOLE_X = 30.0
_HOLE_Y = 30.0
_HOLE_R = 5.0

_SKETCH_ID = "00000000-0000-0000-0000-0000000000a1"
_EXTRUDE_ID = "00000000-0000-0000-0000-0000000000b1"
_EDGE_DIM_ID = "00000000-0000-0000-0000-000000000001"
_HOLE_DIM_ID = "00000000-0000-0000-0000-000000000002"


def _rect(width: float) -> list[dict[str, Any]]:
    pts = [(0.0, 0.0), (width, 0.0), (width, _DEPTH), (0.0, _DEPTH)]
    return [
        {
            "id": f"e{i + 1}",
            "kind": "line",
            "construction": False,
            "start": {"x": pts[i][0], "y": pts[i][1]},
            "end": {"x": pts[(i + 1) % 4][0], "y": pts[(i + 1) % 4][1]},
        }
        for i in range(4)
    ]


def _features(
    width: float, hole_r: float = _HOLE_R, hole_x: float = _HOLE_X
) -> list[dict[str, Any]]:
    """Plate sketch (outer rect + one hole loop) extruded `_THICK` — the audit's part
    shape in two features, so the edit under test is one number in the base sketch."""
    return [
        {
            "id": _SKETCH_ID,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "entities": [
                        *_rect(width),
                        {
                            "id": "h1",
                            "kind": "circle",
                            "construction": False,
                            "center": {"x": hole_x, "y": _HOLE_Y},
                            "radius": hole_r,
                        },
                    ],
                    "constraints": [],
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                },
            },
        },
        {
            "id": _EXTRUDE_ID,
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": _SKETCH_ID},
                    "distance_mm": _THICK,
                    "operation": "add",
                    "direction": "normal",
                },
            },
        },
    ]


def _line_edge_sig(width: float) -> dict[str, Any]:
    """The plate's y=0, z=0 edge — the overall-length edge a print dimensions."""
    return {
        "subshape_type": "edge",
        "curve": "line",
        "end_a": {"x": 0.0, "y": 0.0, "z": 0.0},
        "end_b": {"x": width, "y": 0.0, "z": 0.0},
        "midpoint": {"x": width / 2, "y": 0.0, "z": 0.0},
        "length_mm": width,
    }


def _rim_sig(radius: float, hole_x: float = _HOLE_X) -> dict[str, Any]:
    """The hole's top-face rim circle: seam at (+r, 0), curve midpoint diametrically
    opposite (the shape `edge_signature_dto` emits for a full circle)."""
    return {
        "subshape_type": "edge",
        "curve": "circle",
        "end_a": {"x": hole_x + radius, "y": _HOLE_Y, "z": _THICK},
        "end_b": {"x": hole_x + radius, "y": _HOLE_Y, "z": _THICK},
        "midpoint": {"x": hole_x - radius, "y": _HOLE_Y, "z": _THICK},
        "length_mm": 2.0 * math.pi * radius,
    }


def _placements(manual: dict[str, tuple[float, float]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for projection in STANDARD_VIEWS:
        position = (manual or {}).get(projection)
        out.append(
            {
                "projection": projection,
                "position": {
                    "x_mm": position[0] if position else 0.0,
                    "y_mm": position[1] if position else 0.0,
                },
                "auto_place": position is None,
            }
        )
    return out


def _request(
    *,
    width: float,
    dim_width: float,
    hole_r: float = _HOLE_R,
    dim_hole_r: float = _HOLE_R,
    hole_x: float = _HOLE_X,
    dim_hole_x: float = _HOLE_X,
    manual: dict[str, tuple[float, float]] | None = None,
    size: str = "A3",
) -> ComposeDrawingRequest:
    """A four-view sheet of the plate at *width*, dimensioned as AUTHORED against a
    plate of *dim_width* (and a hole of *dim_hole_r* at *dim_hole_x*) — i.e. the stored
    drawing, replayed against an edited model."""
    payload: dict[str, Any] = {
        "part_id": "00000000-0000-0000-0000-000000000001",
        "tree_version": 1,
        "features": _features(width, hole_r=hole_r, hole_x=hole_x),
        "views": list(STANDARD_VIEWS),
        "scale": {"numerator": 1, "denominator": 1},
        "dimensions": [
            {
                "id": _EDGE_DIM_ID,
                "view": "front",
                "dimension": {
                    "type": "linear",
                    "measurement": {
                        "mode": "edge_length",
                        "edge": _line_edge_sig(dim_width),
                    },
                    "placement": {"offset_mm": 0.0, "text_pos": None},
                },
            },
            {
                "id": _HOLE_DIM_ID,
                "view": "top",
                "dimension": {
                    "type": "diameter",
                    "edge": _rim_sig(dim_hole_r, hole_x=dim_hole_x),
                    "placement": {"offset_mm": 0.0, "text_pos": None},
                },
            },
        ],
        "layout": {
            "size": size,
            "orientation": "landscape",
            "projection": "third_angle",
            "title": "Resize regression",
            "views": _placements(manual),
        },
        "format": "svg",
    }
    return ComposeDrawingRequest.model_validate(payload)


def _compose(request: ComposeDrawingRequest) -> ComposedSheet:
    evaluation = evaluate_drawing_views(request)
    return place_sheet(
        evaluation, request.dimensions, request.layout, request.annotations
    )


def _measured(sheet: ComposedSheet, dim_type: str) -> ComposedMeasuredDimension:
    found = [
        d
        for v in sheet.views
        for d in v.dimensions
        if isinstance(d, ComposedMeasuredDimension) and d.dimension_type == dim_type
    ]
    assert len(found) == 1, f"expected one measured {dim_type} dim, got {len(found)}"
    return found[0]


def _errors(sheet: ComposedSheet) -> list[ComposedDimensionError]:
    return [
        d
        for v in sheet.views
        for d in v.dimensions
        if isinstance(d, ComposedDimensionError)
    ]


def _geometry_rects(
    sheet: ComposedSheet,
) -> dict[ViewProjection, tuple[float, float, float, float]]:
    """Each placed view's DRAWN extent, measured off the composed sheet itself (SVG mm),
    so the assertions read the artifact rather than the layout's own arithmetic."""
    rects: dict[ViewProjection, tuple[float, float, float, float]] = {}
    for view in sheet.views:
        xs: list[float] = []
        ys: list[float] = []
        for edge in view.edges:
            if edge.kind == "line":
                xs += [edge.x1, edge.x2]
                ys += [edge.y1, edge.y2]
            elif edge.kind == "circle":
                xs += [edge.cx - edge.r, edge.cx + edge.r]
                ys += [edge.cy - edge.r, edge.cy + edge.r]
            else:
                xs += [p.x_mm for p in edge.points]
                ys += [p.y_mm for p in edge.points]
        if xs:
            rects[view.projection] = (min(xs), min(ys), max(xs), max(ys))
    return rects


def _gap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    """White gap (mm) between two boxes; 0.0 when they overlap."""
    overlap_x = min(a[2], b[2]) - max(a[0], b[0])
    overlap_y = min(a[3], b[3]) - max(a[1], b[1])
    if overlap_x > 0 and overlap_y > 0:
        return 0.0
    return max(-overlap_x, -overlap_y)


# --- N1: the dimension survives the edit it measures ----------------------------
def test_widening_the_plate_re_measures_its_overall_length_dimension() -> None:
    """THE N1 gate. The stored drawing dimensions the 100 mm edge; the plate is widened
    to 120 and the SAME drawing is recomposed. The dimension must re-measure to the new
    length and STAMP it — before the fix it came back `subshape_unresolved` and printed
    a bare `!`."""
    before = _compose(_request(width=100.0, dim_width=100.0))
    assert _measured(before, "linear").text.value == "100.000"
    assert _errors(before) == []

    after = _compose(_request(width=120.0, dim_width=100.0))
    assert _errors(after) == [], "the widened sheet must carry no broken dimension"
    linear = _measured(after, "linear")
    # RE-MEASURED off the current B-rep, not re-stamped from the authored number.
    assert linear.text.value == "120.000"


def test_the_re_measured_value_comes_from_the_edge_the_user_picked() -> None:
    """A dimension that resolves to the WRONG edge silently is worse than one that
    errors, so the wire is checked too: the measured value is the widened edge's exact
    length and the re-anchored signature is the SAME supporting line (y = 0, z = 0)."""
    request = _request(width=120.0, dim_width=100.0)
    evaluation = evaluate_drawing_views(request)
    linear = next(d for d in evaluation.dimensions if str(d.id) == _EDGE_DIM_ID)
    assert linear.measured.error is None
    assert linear.measured.value == pytest.approx(120.0, abs=_TOL)
    anchor = linear.measured.anchor
    assert anchor is not None
    assert anchor.tier == "durable"  # honestly reported as re-anchored
    primary = anchor.primary
    assert primary is not None
    assert (primary.end_a.y, primary.end_a.z) == (0.0, 0.0)
    assert (primary.end_b.y, primary.end_b.z) == (0.0, 0.0)
    assert primary.end_b.x == pytest.approx(120.0, abs=_TOL)


def test_the_unchanged_hole_dimension_stays_on_the_exact_tier() -> None:
    """The audit's asymmetry, now the right way round: the Ø dimension whose hole did
    NOT change still resolves strictly (byte-identical behaviour), while the edge
    dimension re-anchors. The durable tier is a fallback, not a new default."""
    request = _request(width=120.0, dim_width=100.0)
    evaluation = evaluate_drawing_views(request)
    hole = next(d for d in evaluation.dimensions if str(d.id) == _HOLE_DIM_ID)
    assert hole.measured.anchor is not None
    assert hole.measured.anchor.tier == "exact"
    assert hole.measured.value == pytest.approx(2.0 * _HOLE_R, abs=_TOL)
    assert _measured(_compose(request), "diameter").text.value == "Ø10.000"


def test_resizing_the_hole_re_measures_its_diameter_dimension() -> None:
    """The other everyday revision: Ø10 → Ø14. The rim's endpoints, midpoint and length
    all change; its centre and angular station do not, so the dimension re-measures."""
    after = _compose(_request(width=100.0, dim_width=100.0, hole_r=7.0, dim_hole_r=5.0))
    assert _errors(after) == []
    assert _measured(after, "diameter").text.value == "Ø14.000"


def test_a_moved_hole_is_an_honest_error_with_WORDS_on_the_sheet(
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """The refusal side of the contract: a hole that MOVED breaks the centre invariant,
    so its dimension must NOT re-anchor onto the hole at its new place. It fails
    honestly — and the sheet now says so in words beside the marker, in all three
    formats (the bare `!` was the whole diagnostic before)."""
    sheet = _compose(
        _request(width=100.0, dim_width=100.0, hole_x=60.0, dim_hole_x=_HOLE_X)
    )
    errors = _errors(sheet)
    assert len(errors) == 1
    error = errors[0]
    assert error.dimension_type == "diameter"
    assert error.code == "subshape_unresolved"
    assert error.message == "DIAMETER DIM: REFERENCE LOST - RE-PICK THE EDGE"
    assert error.text is not None

    svg = serialize_svg(sheet)
    assert 'data-testid="drawing-dimension-error"' in svg
    assert "DIAMETER DIM: REFERENCE LOST - RE-PICK THE EDGE" in svg
    assert b"DIAMETER DIM: REFERENCE LOST" in serialize_pdf(sheet)
    doc = read_dxf(serialize_dxf(sheet))
    texts = {e.dxf.text for e in doc.modelspace() if e.dxftype() == "TEXT"}
    assert "DIAMETER DIM: REFERENCE LOST - RE-PICK THE EDGE" in texts
    assert not doc.audit().errors


# --- N2: the layout re-flows on the edit, and a bad sheet is never silent --------
@pytest.mark.parametrize("width", [100.0, 120.0])
def test_auto_layout_keeps_the_full_gutter_at_any_part_size(width: float) -> None:
    """THE N2 gate. Every pair of the four standard views clears by the full drafting
    gutter both BEFORE and AFTER the widening — the iso anchor is derived from the
    extents it must clear, so growth re-flows the sheet instead of colliding. Before the
    fix this same 120 mm sheet put the isometric ON TOP of the top view."""
    sheet = _compose(_request(width=width, dim_width=width))
    assert sheet.layout_issues == []
    rects = _geometry_rects(sheet)
    assert set(rects) == set(STANDARD_VIEWS)
    for index, a in enumerate(STANDARD_VIEWS):
        for b in STANDARD_VIEWS[index + 1 :]:
            gap = _gap(rects[a], rects[b])
            assert gap == pytest.approx(VIEW_GUTTER_MM, abs=1e-6), (
                f"{a}/{b} gap {gap:.2f} mm at width {width}"
            )


def test_the_widened_sheet_still_fits_inside_the_border() -> None:
    """Re-flowing into the empty right-hand third must not push a view off the paper:
    every view's drawn extent stays inside the border margins after the widening."""
    sheet = _compose(_request(width=120.0, dim_width=120.0))
    for projection, (x0, y0, x1, y1) in _geometry_rects(sheet).items():
        assert x0 >= SHEET_MARGIN_MM, projection
        assert y0 >= SHEET_MARGIN_MM, projection
        assert x1 <= sheet.width_mm - SHEET_MARGIN_MM, projection
        assert y1 <= sheet.height_mm - SHEET_MARGIN_MM, projection


def test_hand_placed_views_are_honored_and_their_overlap_is_reported(
    read_dxf: Callable[[bytes], Drawing],
) -> None:
    """The user-intent rule (documented in drawing-export.md): an `auto_place=False`
    position is INTENT and is never re-flowed — so when two hand-placed views collide,
    composition reports it in millimetres and every export stamps a banner, rather than
    moving the user's views or shipping the collision silently."""
    manual = {"front": (150.0, 150.0), "top": (160.0, 150.0)}
    sheet = _compose(_request(width=120.0, dim_width=120.0, manual=manual))

    # Honored verbatim (y-up authored → y-down SVG anchor).
    for projection, (x_mm, y_mm) in manual.items():
        view = next(v for v in sheet.views if v.projection == projection)
        assert view.anchor.x_mm == pytest.approx(x_mm, abs=_TOL)
        assert view.anchor.y_mm == pytest.approx(sheet.height_mm - y_mm, abs=_TOL)

    overlaps = [i for i in sheet.layout_issues if i.code == "views_overlap"]
    assert overlaps, sheet.layout_issues
    issue = next(i for i in overlaps if set(i.views) == {"front", "top"})
    assert issue.severity == "error"
    assert issue.overlap_x_mm > 0.0 and issue.overlap_y_mm > 0.0
    assert issue.clearance_mm == 0.0
    assert "OVERLAP" in issue.message

    svg = serialize_svg(sheet)
    assert 'data-testid="drawing-layout-issue"' in svg
    assert "LAYOUT ERROR:" in svg
    assert b"LAYOUT ERROR:" in serialize_pdf(sheet)
    dxf = serialize_dxf(sheet)
    assert b"LAYOUT ERROR:" in dxf
    doc = read_dxf(dxf)
    assert any(
        e.dxftype() == "TEXT" and e.dxf.text.startswith("LAYOUT ERROR:")
        for e in doc.modelspace()
    )
    assert not doc.audit().errors


def test_sub_millimetre_clearance_is_a_warning_not_a_pass() -> None:
    """The 0.70 mm near-tangency the audit measured was the DIAGNOSIS, not the accident:
    a gap that small is one design change from a collision. A hand-placed pair that
    clears by less than the documented minimum is a `views_crowded` warning, stamped on
    the sheet — while a genuinely clear pair says nothing."""
    # All four views hand-placed on an A2 so only ONE pair is tight: the front view
    # (120 x 10) at y = 100 and the top view (120 x 60) just 1 mm above its caption
    # band; the other two are parked far right, well clear.
    manual = {
        "front": (150.0, 100.0),
        "top": (150.0, 145.7),
        "right": (400.0, 100.0),
        "iso": (400.0, 300.0),
    }
    sheet = _compose(_request(width=120.0, dim_width=120.0, manual=manual, size="A2"))
    assert not [i for i in sheet.layout_issues if i.code == "views_overlap"], (
        sheet.layout_issues
    )
    crowded = [i for i in sheet.layout_issues if i.code == "views_crowded"]
    assert crowded, sheet.layout_issues
    issue = crowded[0]
    assert set(issue.views) == {"front", "top"}
    assert issue.severity == "warning"
    assert 0.0 < issue.clearance_mm < MIN_VIEW_CLEARANCE_MM
    assert "CLEAR BY ONLY" in issue.message
    svg = serialize_svg(sheet)
    assert "LAYOUT WARNING:" in svg


def test_a_clean_sheet_carries_no_banner_at_all() -> None:
    """The additive posture: no issues ⇒ no banner ink ⇒ a clean sheet's bytes are
    unchanged by this whole mechanism (which is why the committed goldens only moved by
    the layout fix)."""
    svg = serialize_svg(_compose(_request(width=120.0, dim_width=120.0)))
    assert 'data-testid="drawing-layout-issue"' not in svg
    assert "LAYOUT ERROR" not in svg and "LAYOUT WARNING" not in svg
