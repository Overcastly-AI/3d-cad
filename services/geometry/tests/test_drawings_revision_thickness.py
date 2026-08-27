"""THE REVISION GATE for a print: retype the thickness, the drawing must still be one.

QA-3 (docs/QA-REVIEW.md 2026-07-30, P1). Every drawing gate that shipped before this
module composes a sheet ONCE. The defect class they cannot see is the second one: an
edit lands on the part and the print — which is by definition attached to the geometry
the designer is about to change — has to survive it. Here the SAME authored drawing
(a Ø10 hole dimension in the top view, a 10 mm thickness dimension in the front view)
is composed against the part BEFORE and AFTER a one-number revision, thickness
10 -> 16, exactly as a document is left after the user retypes Extrude1's distance.

What must hold afterwards, and why each half is a separate gate:

* the LINEAR dimension on the edge the edit CHANGED re-measures 10.000 -> 16.000
  (the `7fde5d2` line tier — asserted here as a control, so a regression in it is
  distinguishable from a regression in the circle tier);
* the DIAMETER dimension on a hole the edit NEVER TOUCHED still reads Ø10.000. Its
  rim slid 6 mm along its own axis because the face it sits on moved, which broke
  both earlier tiers and destroyed the dimension (QA-3);
* both are STAMPED — on the composed sheet and in the exported SVG/PDF/DXF bytes,
  because a dimension whose value re-measures but whose annotation is dropped is
  still a dimension the shop does not get;
* and the refusals survive: a hole that MOVED is still an honest error with words on
  the print, never a silently re-anchored number.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import pytest
from ezdxf.document import Drawing
from fastapi.testclient import TestClient
from geometry.drawings import evaluate_drawing_views, place_sheet
from geometry.drawings.compose import STANDARD_VIEWS
from geometry.main import app
from py_kit.schemas.drawings import (
    ComposedDimensionError,
    ComposedMeasuredDimension,
    ComposeDrawingRequest,
    ComposedSheet,
)

client = TestClient(app)

#: The shipped drawing fixture part: a 40 x 25 plate with a Ø10 through hole.
_W, _D = 40.0, 25.0
_HOLE_X, _HOLE_Y, _HOLE_R = 20.0, 12.5, 5.0

#: The revision under test: the plate is 10 mm thick when the drawing is authored.
_AUTHORED_THICK = 10.0
_REVISED_THICK = 16.0

_SKETCH_ID = "00000000-0000-0000-0000-0000000000a1"
_EXTRUDE_ID = "00000000-0000-0000-0000-0000000000b1"
_EDGE_DIM_ID = "00000000-0000-0000-0000-000000000001"
_HOLE_DIM_ID = "00000000-0000-0000-0000-000000000002"

#: Sheet-mm / measured-value comparison bound. The plate is an exact prism and the
#: bore an exact cylinder, so residuals are float representation only (the
#: test_drawings_resize posture — documented, not ad-hoc).
_TOL = 1e-9


def _rect() -> list[dict[str, Any]]:
    pts = [(0.0, 0.0), (_W, 0.0), (_W, _D), (0.0, _D)]
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


def _features(thickness: float, hole_x: float) -> list[dict[str, Any]]:
    return [
        {
            "id": _SKETCH_ID,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    "entities": [
                        *_rect(),
                        {
                            "id": "h1",
                            "kind": "circle",
                            "construction": False,
                            "center": {"x": hole_x, "y": _HOLE_Y},
                            "radius": _HOLE_R,
                        },
                    ],
                    "constraints": [],
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
                    "distance_mm": thickness,
                    "operation": "add",
                    "direction": "normal",
                },
            },
        },
    ]


def _rim_signature(z: float, hole_x: float = _HOLE_X) -> dict[str, Any]:
    """The bore's TOP rim circle — what a pick in the TOP view stores (the projector
    emits the rim the viewer sees; the coincident bottom rim is not drawn)."""
    return {
        "subshape_type": "edge",
        "curve": "circle",
        "end_a": {"x": hole_x + _HOLE_R, "y": _HOLE_Y, "z": z},
        "end_b": {"x": hole_x + _HOLE_R, "y": _HOLE_Y, "z": z},
        "midpoint": {"x": hole_x - _HOLE_R, "y": _HOLE_Y, "z": z},
        "length_mm": 2.0 * math.pi * _HOLE_R,
    }


def _thickness_edge_signature(thickness: float) -> dict[str, Any]:
    """The vertical corner edge at (0, 0) — the plate's THICKNESS, dimensioned in the
    front view. This is the edge the revision changes out from under its dimension."""
    return {
        "subshape_type": "edge",
        "curve": "line",
        "end_a": {"x": 0.0, "y": 0.0, "z": 0.0},
        "end_b": {"x": 0.0, "y": 0.0, "z": thickness},
        "midpoint": {"x": 0.0, "y": 0.0, "z": thickness / 2},
        "length_mm": thickness,
    }


def _request(
    *,
    thickness: float,
    hole_x: float = _HOLE_X,
    dim_thickness: float = _AUTHORED_THICK,
    dim_rim_z: float = _AUTHORED_THICK,
    dim_hole_x: float = _HOLE_X,
    fmt: str = "svg",
) -> ComposeDrawingRequest:
    """The AUTHORED drawing (dimensions written against the plate as it was), replayed
    against the part as it IS."""
    payload: dict[str, Any] = {
        "part_id": "00000000-0000-0000-0000-000000000001",
        "tree_version": 1,
        "features": _features(thickness, hole_x),
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
                        "edge": _thickness_edge_signature(dim_thickness),
                    },
                    "placement": {"offset_mm": 0.0, "text_pos": None},
                },
            },
            {
                "id": _HOLE_DIM_ID,
                "view": "top",
                "dimension": {
                    "type": "diameter",
                    "edge": _rim_signature(dim_rim_z, hole_x=dim_hole_x),
                    "placement": {"offset_mm": 0.0, "text_pos": None},
                },
            },
        ],
        "layout": {
            "size": "A3",
            "orientation": "landscape",
            "projection": "third_angle",
            "title": "Thickness revision",
            "views": [
                {
                    "projection": projection,
                    "position": {"x_mm": 0.0, "y_mm": 0.0},
                    "auto_place": True,
                }
                for projection in STANDARD_VIEWS
            ],
        },
        "format": fmt,
    }
    return ComposeDrawingRequest.model_validate(payload)


def _compose(request: ComposeDrawingRequest) -> ComposedSheet:
    evaluation = evaluate_drawing_views(request)
    return place_sheet(
        evaluation, request.dimensions, request.layout, request.annotations
    )


def _stamped(sheet: ComposedSheet, dim_type: str) -> ComposedMeasuredDimension:
    found = [
        d
        for v in sheet.views
        for d in v.dimensions
        if isinstance(d, ComposedMeasuredDimension) and d.dimension_type == dim_type
    ]
    assert len(found) == 1, f"expected one placed {dim_type} dim, got {len(found)}"
    return found[0]


def _errors(sheet: ComposedSheet) -> list[ComposedDimensionError]:
    return [
        d
        for v in sheet.views
        for d in v.dimensions
        if isinstance(d, ComposedDimensionError)
    ]


def _artifact(request: ComposeDrawingRequest) -> bytes:
    """The composed artifact BYTES from the shipped route — what a shop receives."""
    response = client.post(
        "/api/v1/drawing/compose", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    return response.content


# --- the revision itself ---------------------------------------------------------
def test_the_authored_print_is_correct_before_the_revision() -> None:
    """The baseline both halves are measured against: Ø10.000 and 10.000, no errors,
    both on the EXACT tier (the durable tiers are fallbacks, never the default)."""
    request = _request(thickness=_AUTHORED_THICK)
    evaluation = evaluate_drawing_views(request)
    for measured in evaluation.dimensions:
        assert measured.measured.error is None
        assert measured.measured.anchor is not None
        assert measured.measured.anchor.tier == "exact"
    sheet = _compose(request)
    assert _errors(sheet) == []
    assert _stamped(sheet, "diameter").text.value == "Ø10.000"
    assert _stamped(sheet, "linear").text.value == "10.000"


def test_a_diameter_dimension_the_revision_never_touched_survives_it() -> None:
    """THE QA-3 gate. Thickness 10 -> 16 moves the top face, so the bore's rim — the
    edge the Ø dimension names — slides 6 mm along its own axis. The hole's DIAMETER
    did not change, and the print must still say so: Ø10.000, re-measured off the
    current B-rep (never re-stamped from the authored number), re-anchored honestly
    (the wire reports the tier), and PLACED on the sheet."""
    request = _request(thickness=_REVISED_THICK)
    evaluation = evaluate_drawing_views(request)
    diameter = next(d for d in evaluation.dimensions if str(d.id) == _HOLE_DIM_ID)
    assert diameter.measured.error is None
    assert diameter.measured.value == pytest.approx(2.0 * _HOLE_R, abs=_TOL)
    anchor = diameter.measured.anchor
    assert anchor is not None
    assert anchor.tier == "durable"
    # Re-anchored onto the rim at the plate's NEW height, same axis, same radius.
    primary = anchor.primary
    assert primary is not None
    assert primary.end_a.z == pytest.approx(_REVISED_THICK, abs=_TOL)
    assert (primary.end_a.x, primary.end_a.y) == pytest.approx(
        (_HOLE_X + _HOLE_R, _HOLE_Y), abs=_TOL
    )

    sheet = _compose(request)
    assert _errors(sheet) == [], "the revised sheet must carry no broken dimension"
    assert _stamped(sheet, "diameter").text.value == "Ø10.000"


def test_the_thickness_dimension_the_revision_DID_change_follows_it() -> None:
    """The control half (the `7fde5d2` line tier), so a failure of either tier is
    attributable: the linear dimension measuring the edge the edit changed re-measures
    10.000 -> 16.000 rather than being destroyed by the very edit it measures."""
    sheet = _compose(_request(thickness=_REVISED_THICK))
    assert _stamped(sheet, "linear").text.value == "16.000"


@pytest.mark.parametrize("fmt", ["svg", "pdf", "dxf"])
def test_the_revised_print_carries_BOTH_numbers_in_the_exported_bytes(
    fmt: str, read_dxf: Callable[[bytes], Drawing]
) -> None:
    """A value that re-measures into a sheet nobody exports is not a fixed print, so
    the gate reads the ARTIFACT: both dimensions are stamped in the exported file, and
    no failure caption is."""
    payload = _artifact(_request(thickness=_REVISED_THICK, fmt=fmt))
    if fmt == "dxf":
        doc = read_dxf(payload)
        texts = {e.dxf.text for e in doc.modelspace() if e.dxftype() == "TEXT"}
        assert "Ø10.000" in texts
        assert "16.000" in texts
        assert not [t for t in texts if "REFERENCE LOST" in t or "CANNOT BE" in t]
    elif fmt == "svg":
        assert "Ø10.000".encode() in payload
        assert b"16.000" in payload
        assert b"REFERENCE LOST" not in payload
        assert b"CANNOT BE PLACED" not in payload
    else:
        # reportlab writes the Ø as an octal escape in a Tj string ("\33010.000"),
        # so the byte assertion reads the escaped form rather than UTF-8.
        assert rb"(\33010.000) Tj" in payload
        assert b"16.000" in payload
        assert b"REFERENCE LOST" not in payload
        assert b"CANNOT BE PLACED" not in payload


def test_a_hole_that_MOVED_is_still_a_refusal_with_words_on_the_print() -> None:
    """The refusal QA-3 must not trade away — a fix that turned a visible failure into
    a silently wrong number would be worse than the defect. The hole is relocated
    (x 20 -> 28) AND the plate thickened, so its rim leaves the axis line the
    dimension named: honest error, and the exported print SAYS so."""
    request = _request(thickness=_REVISED_THICK, hole_x=28.0, fmt="svg")
    evaluation = evaluate_drawing_views(request)
    diameter = next(d for d in evaluation.dimensions if str(d.id) == _HOLE_DIM_ID)
    assert diameter.measured.error is not None
    assert diameter.measured.error.code == "subshape_unresolved"

    errors = _errors(_compose(request))
    assert [e.dimension_type for e in errors] == ["diameter"]
    assert errors[0].message == "DIAMETER DIM: REFERENCE LOST - RE-PICK THE EDGE"
    assert b"DIAMETER DIM: REFERENCE LOST" in _artifact(request)


def test_the_revised_sheet_is_byte_deterministic() -> None:
    """RESEARCH §9 applied to the re-anchored path: the re-match is a pure function of
    (body, signature, drawn set), so composing the revised drawing twice yields
    byte-identical artifacts — a tier that picked its candidate by enumeration luck
    would show up here."""
    request = _request(thickness=_REVISED_THICK)
    assert _artifact(request) == _artifact(request)
