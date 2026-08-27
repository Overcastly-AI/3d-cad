"""A dimension that is not drawn leaves WORDS on the print — asserted on the BYTES.

QA-4 (docs/QA-REVIEW.md 2026-07-30, P1): "a lost dimension leaves no trace on the
print". The commit that introduced the sheet caption
(:func:`geometry.drawings.compose.dimension_error_caption`) asserted the words reach
SVG/PDF/DXF, but its gates called ``place_sheet`` + a serializer directly — a function
can be perfectly correct while nothing calls it. So every gate in this module goes
through the SHIPPED ROUTE (``POST /api/v1/drawing/compose``) and asserts on the
returned ARTIFACT BYTES, which is what a shop actually receives.

Two failure modes are covered, because they reach the paper by different doors:

1. **Unmeasurable** — the reference genuinely cannot be re-anchored (a hole that
   MOVED). Measurement reports a typed error; the composer stamps it.
2. **Unplaceable** — the dimension MEASURES fine but there is nothing on its view to
   draw it on (its edge is not drawn in that view, is drawn as a primitive the
   dimension type cannot annotate, or the placement itself is degenerate). Before
   QA-4 the composer returned ``None`` here and the caller SKIPPED the dimension: the
   authored dimension vanished from the sheet and from every exported artifact with
   no marker, no caption and no error — a print that has silently lost a dimension
   looks exactly like a complete one, which is the one failure a shop cannot catch.

Byte assertions, not model assertions: the words must survive composition AND
serialization in all three formats, so a serializer that forgets the caption is a
failing gate rather than a silent regression.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import pytest
from ezdxf.document import Drawing
from fastapi.testclient import TestClient
from geometry.drawings.compose import STANDARD_VIEWS
from geometry.main import app
from py_kit.schemas.drawings import ComposeDrawingRequest

client = TestClient(app)

_COMPOSE_URL = "/api/v1/drawing/compose"

#: The plate the shipped drawing fixtures use: 40 x 25 x 10 with a Ø10 through hole.
_W, _D, _THICK = 40.0, 25.0, 10.0
_HOLE_X, _HOLE_Y, _HOLE_R = 20.0, 12.5, 5.0

_SKETCH_ID = "00000000-0000-0000-0000-0000000000a1"
_EXTRUDE_ID = "00000000-0000-0000-0000-0000000000b1"
_DIM_ID = "00000000-0000-0000-0000-000000000004"


def _rect(width: float, depth: float) -> list[dict[str, Any]]:
    pts = [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)]
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


def _features(hole_x: float) -> list[dict[str, Any]]:
    return [
        {
            "id": _SKETCH_ID,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    "entities": [
                        *_rect(_W, _D),
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
                    "distance_mm": _THICK,
                    "operation": "add",
                    "direction": "normal",
                },
            },
        },
    ]


def _rim_signature(hole_x: float) -> dict[str, Any]:
    """The hole's TOP rim circle — the edge a Ø dimension names (seam at +r)."""
    return {
        "subshape_type": "edge",
        "curve": "circle",
        "end_a": {"x": hole_x + _HOLE_R, "y": _HOLE_Y, "z": _THICK},
        "end_b": {"x": hole_x + _HOLE_R, "y": _HOLE_Y, "z": _THICK},
        "midpoint": {"x": hole_x - _HOLE_R, "y": _HOLE_Y, "z": _THICK},
        "length_mm": 2.0 * math.pi * _HOLE_R,
    }


def _request(
    *, hole_x: float, dim_hole_x: float, view: str, fmt: str
) -> ComposeDrawingRequest:
    """A four-view sheet of the plate carrying ONE diameter dimension on *view*,
    authored against a hole at *dim_hole_x* and composed against one at *hole_x*."""
    payload: dict[str, Any] = {
        "part_id": "00000000-0000-0000-0000-000000000001",
        "tree_version": 1,
        "features": _features(hole_x),
        "views": list(STANDARD_VIEWS),
        "scale": {"numerator": 1, "denominator": 1},
        "dimensions": [
            {
                "id": _DIM_ID,
                "view": view,
                "dimension": {
                    "type": "diameter",
                    "edge": _rim_signature(dim_hole_x),
                    "placement": {"offset_mm": 0.0, "text_pos": None},
                },
            }
        ],
        "layout": {
            "size": "A3",
            "orientation": "landscape",
            "projection": "third_angle",
            "title": "Lost dimension",
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


def _artifact(request: ComposeDrawingRequest) -> bytes:
    """The composed artifact BYTES from the shipped route (never a model)."""
    response = client.post(_COMPOSE_URL, json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    return response.content


def _dxf_text_set(read_dxf: Callable[[bytes], Drawing], payload: bytes) -> set[str]:
    """Every TEXT string in the DXF, read back through the conftest `read_dxf`
    fixture — which derives the encoding from the file's own `$DWGCODEPAGE` instead
    of assuming UTF-8 (AUDIT-PRODUCT F-3)."""
    doc = read_dxf(payload)
    return {e.dxf.text for e in doc.modelspace() if e.dxftype() == "TEXT"}


# --- 1. an unmeasurable reference ------------------------------------------------
@pytest.mark.parametrize("fmt", ["svg", "pdf", "dxf"])
def test_a_lost_reference_prints_words_in_the_exported_bytes(
    fmt: str, read_dxf: Callable[[bytes], Drawing]
) -> None:
    """THE QA-4 gate. The hole MOVED (x 20 → 30), so its Ø dimension cannot be
    re-anchored — an honest refusal (a dimension that silently retargets onto a
    different hole would be worse). The exported file must SAY so."""
    payload = _artifact(_request(hole_x=30.0, dim_hole_x=20.0, view="top", fmt=fmt))
    expected = "DIAMETER DIM: REFERENCE LOST - RE-PICK THE EDGE"
    if fmt == "dxf":
        assert expected in _dxf_text_set(read_dxf, payload)
    else:
        assert expected.encode("utf-8") in payload


def test_a_resolvable_reference_prints_its_value_and_no_caption() -> None:
    """The control: with the hole where the dimension says it is, the SAME request
    stamps Ø10.000 and no failure words — so the gate above measures the failure
    path, not an always-on caption."""
    payload = _artifact(_request(hole_x=20.0, dim_hole_x=20.0, view="top", fmt="svg"))
    assert b"10.000" in payload
    assert b"REFERENCE LOST" not in payload
    assert b"CANNOT BE PLACED" not in payload


# --- 2. an unplaceable (but perfectly measurable) dimension ----------------------
@pytest.mark.parametrize("fmt", ["svg", "pdf", "dxf"])
def test_a_dimension_with_nothing_to_draw_on_prints_words_too(
    fmt: str, read_dxf: Callable[[bytes], Drawing]
) -> None:
    """The silent half of QA-4. A Ø dimension authored on the FRONT view measures
    fine off the 3-D bore, but the front view draws that rim edge-on — there is no
    circle to span, so the annotation cannot be placed. It used to be dropped with no
    trace anywhere in the artifact; the exported bytes must now carry the marker and
    the words."""
    payload = _artifact(_request(hole_x=20.0, dim_hole_x=20.0, view="front", fmt=fmt))
    expected = "DIAMETER DIM: CANNOT BE PLACED IN THIS VIEW - RE-PICK IT"
    if fmt == "dxf":
        assert expected in _dxf_text_set(read_dxf, payload)
    else:
        assert expected.encode("utf-8") in payload


def test_every_authored_dimension_lands_on_the_composed_sheet() -> None:
    """The structural invariant behind both gates, asserted on the sheet MODEL the
    same route serializes: the number of placed dimensions equals the number
    authored, whether they measured, failed or could not be placed. A composer that
    can drop one can lose a dimension silently again."""
    for view in ("top", "front", "right", "iso"):
        for hole_x in (20.0, 30.0):
            request = _request(
                hole_x=hole_x, dim_hole_x=20.0, view=view, fmt="svg"
            ).model_dump(mode="json")
            response = client.post("/api/v1/drawing/compose/sheet", json=request)
            assert response.status_code == 200, response.text
            placed = [
                dimension
                for composed_view in response.json()["views"]
                for dimension in composed_view["dimensions"]
            ]
            assert len(placed) == 1, (
                f"{view} view, hole at x={hole_x}: expected the one authored "
                f"dimension on the sheet, got {len(placed)}"
            )
