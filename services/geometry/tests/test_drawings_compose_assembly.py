"""Assembly-view COMPOSE gates — the D4 slice-(a) geometry compose branch (§7).

Slice 1 (``8be617e``) shipped ``evaluate_assembly_drawing_views`` (the solved-compound
HLR core); slice 2 (``4f1125d``) threaded the resolved graph to geometry as the
additive ``ComposeDrawingRequest.assembly``. This suite proves the LAST hop: when
``assembly`` is set the compose routes project the SOLVED ASSEMBLY COMPOUND and place
its silhouettes on a real sheet — end-to-end at the API, not VIEW-FAILED placeholders.

Fixture: the slice-1 golden 2-instance assembly (a BIG 20-cube centred at the origin
+ a SMALL 8-cube 40 mm behind it), whose FRONT view is analytically 4 visible + 4
HIDDEN lines (the small cube fully occluded). Gates:

1. **End-to-end compose** — ``/drawing/compose/sheet`` places those 8 edges (visible
   solid, hidden dashed, correct 20 mm / 8 mm concentric extents) and
   ``/drawing/compose`` serializes them into the SVG (4 dashed hidden strokes drawn,
   no VIEW FAILED).
2. **Consistency** — a single-instance assembly composes byte-identical SVG bytes to
   the equivalent PART compose (the slice-1 invariant lifted to the sheet).
3. **Typed degradation** — an all-bodyless assembly composes typed FAILED views
   inside a 200 (never a 500); authored dimensions on an assembly compose are
   ignored, never a strict-zip crash.
4. **Determinism + DE-4 cache** — same assembly request ⇒ identical bytes, second
   hit served from the content-addressed store (``assembly`` is in the hashed key).

The ``assembly=None`` byte-identity regression rides the EXISTING goldens
(``test_drawings_compose`` / section / sheet-metal suites hit the same modified
routes and assert committed bytes verbatim).

Tolerance: composed line coordinates come off the exact placed B-rep through HLR +
an affine sheet transform, so residuals stay ulp-scale — the documented 1e-7 mm
model tolerance (docs/GEOMETRY-QA.md), never an ad-hoc epsilon.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.main import app
from py_kit.schemas.drawings import ComposedLineEdge, ComposedSheet

COORD_TOL_MM = 1e-7

_GOLDEN_DIR = Path(__file__).resolve().parent / "compose_goldens"

client = TestClient(app)


def _uid(n: int) -> str:
    return str(uuid.UUID(int=n))


def _line(
    eid: str, start: tuple[float, float], end: tuple[float, float]
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def _box_features(
    sketch_id: str, extrude_id: str, size_x: float, size_y: float, size_z: float
) -> list[dict[str, Any]]:
    """A centred-in-XY box (the slice-1 golden builder, reproduced verbatim)."""
    hx, hy = size_x / 2.0, size_y / 2.0
    return [
        {
            "id": sketch_id,
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    "entities": [
                        _line("e1", (-hx, -hy), (hx, -hy)),
                        _line("e2", (hx, -hy), (hx, hy)),
                        _line("e3", (hx, hy), (-hx, hy)),
                        _line("e4", (-hx, hy), (-hx, -hy)),
                    ],
                    "constraints": [],
                },
            },
        },
        {
            "id": extrude_id,
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": sketch_id},
                    "distance_mm": size_z,
                    "operation": "add",
                    "direction": "normal",
                },
            },
        },
    ]


def _instance(
    n: int,
    part_key: str,
    features: list[dict[str, Any]],
    *,
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> dict[str, Any]:
    return {
        "instance_id": _uid(n),
        "part_key": part_key,
        "features": features,
        "placement": {
            "position": {"x": pos[0], "y": pos[1], "z": pos[2]},
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        },
        "grounded": True,
    }


def _two_cube_instances() -> list[dict[str, Any]]:
    """The slice-1 golden pair: BIG 20-cube at the origin, SMALL 8-cube 40 mm
    behind it (world X[-4,4], Y[36,44], Z[-4,4]) — front = 4 visible + 4 hidden."""
    return [
        _instance(
            1,
            "big@1",
            _box_features(_uid(11), _uid(12), 20.0, 20.0, 20.0),
            pos=(0.0, 0.0, -10.0),
        ),
        _instance(
            2,
            "small@1",
            _box_features(_uid(21), _uid(22), 8.0, 8.0, 8.0),
            pos=(0.0, 40.0, -4.0),
        ),
    ]


def _sketch_only_instance(n: int) -> dict[str, Any]:
    """An instance whose part has a sketch but NO body-affecting feature."""
    return _instance(
        n, f"empty{n}@1", _box_features(_uid(50 + n), _uid(60 + n), 10, 10, 10)[:1]
    )


def _layout(views: list[str], title: str) -> dict[str, Any]:
    return {
        "size": "A4",
        "orientation": "landscape",
        "projection": "third_angle",
        "title": title,
        "title_block": None,
        "views": [
            {
                "projection": v,
                "position": {"x_mm": 0.0, "y_mm": 0.0},
                "scale": {"numerator": 1, "denominator": 1},
            }
            for v in views
        ],
    }


def _assembly_compose_payload(
    instances: list[dict[str, Any]],
    views: list[str],
    title: str = "Two-Cube Assembly",
) -> dict[str, Any]:
    """A ComposeDrawingRequest JSON payload with ``assembly`` set (slice 2's wire
    shape): the inherited part fields echo the assembly id/version with an EMPTY
    feature prefix — exactly what the gateway aggregation sends."""
    return {
        "part_id": _uid(9000),
        "tree_version": 1,
        "features": [],
        "views": views,
        "scale": {"numerator": 1, "denominator": 1},
        "dimensions": [],
        "assembly": {
            "assembly_id": _uid(9000),
            "version": 1,
            "instances": instances,
            "mates": [],
        },
        "layout": _layout(views, title),
        "format": "svg",
    }


def _line_edges(sheet: ComposedSheet, proj: str) -> list[ComposedLineEdge]:
    (view,) = [v for v in sheet.views if v.projection == proj]
    assert view.failed is False
    return [e for e in view.edges if isinstance(e, ComposedLineEdge)]


def _rect_extent(
    lines: list[ComposedLineEdge],
) -> tuple[float, float, float, float]:
    xs = [c for e in lines for c in (e.x1, e.x2)]
    ys = [c for e in lines for c in (e.y1, e.y2)]
    return min(xs), min(ys), max(xs), max(ys)


# --- 1. End-to-end: the assembly silhouette lands on the composed sheet ---------


def test_assembly_compose_sheet_places_the_silhouette_edges() -> None:
    """``POST /drawing/compose/sheet`` with ``assembly`` set places the slice-1
    front view AS DRAWN geometry: 4 visible (big cube, 20 mm square) + 4 hidden
    (occluded small cube, 8 mm square) line edges, concentric, hidden strictly
    inside visible — a real assembly view, not a VIEW-FAILED placeholder."""
    payload = _assembly_compose_payload(_two_cube_instances(), ["front"])
    response = client.post("/api/v1/drawing/compose/sheet", json=payload)
    assert response.status_code == 200, response.text
    sheet = ComposedSheet.model_validate(response.json())

    lines = _line_edges(sheet, "front")
    visible = [e for e in lines if e.visible]
    hidden = [e for e in lines if not e.visible]
    assert len(visible) == 4, f"big-cube face is 4 visible lines, got {len(visible)}"
    assert len(hidden) == 4, f"occluded small cube is 4 hidden lines, got {len(hidden)}"

    vx0, vy0, vx1, vy1 = _rect_extent(visible)
    hx0, hy0, hx1, hy1 = _rect_extent(hidden)
    # Big cube silhouette: 20 x 20 mm; small cube: 8 x 8 mm (scale 1:1, sheet mm).
    assert vx1 - vx0 == pytest.approx(20.0, abs=COORD_TOL_MM)
    assert vy1 - vy0 == pytest.approx(20.0, abs=COORD_TOL_MM)
    assert hx1 - hx0 == pytest.approx(8.0, abs=COORD_TOL_MM)
    assert hy1 - hy0 == pytest.approx(8.0, abs=COORD_TOL_MM)
    # Concentric (the small cube sits centred behind the big one).
    assert (vx0 + vx1) / 2 == pytest.approx((hx0 + hx1) / 2, abs=COORD_TOL_MM)
    assert (vy0 + vy1) / 2 == pytest.approx((hy0 + hy1) / 2, abs=COORD_TOL_MM)


def test_assembly_compose_svg_draws_hidden_dashed_lines() -> None:
    """``POST /drawing/compose`` serializes the assembly view into the SVG artifact:
    the front view group is NOT failed, the 4 visible edges are solid strokes, the 4
    occluded edges are drawn with the hidden dash pattern — the silhouette appears
    on the shipped sheet bytes."""
    payload = _assembly_compose_payload(_two_cube_instances(), ["front"])
    response = client.post("/api/v1/drawing/compose", json=payload)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/svg+xml")
    svg = response.text
    assert 'data-view="front" data-view-error="false"' in svg
    assert "VIEW FAILED" not in svg
    # 4 hidden edges = the only users of the hidden dash pattern on this sheet.
    assert svg.count('stroke-dasharray="2 1.4"') == 4
    # 4 visible body edges at the visible stroke weight (title-block rules are 0.35).
    assert svg.count('stroke="#1B222B" stroke-width="0.5000"') == 4


# --- 2. Consistency: single-instance assembly compose == part compose -----------


def test_single_instance_assembly_composes_identically_to_the_part() -> None:
    """A one-instance assembly (grounded at identity) composes BYTE-IDENTICAL SVG
    to the same box composed as a plain PART — the slice-1 single-instance == part
    invariant, lifted through place_sheet + serialize_svg to the artifact bytes."""
    features = _box_features(_uid(41), _uid(42), 30.0, 20.0, 10.0)
    views = ["front", "top", "right"]
    title = "Consistency Box"

    part_payload: dict[str, Any] = {
        "part_id": _uid(7),
        "tree_version": 1,
        "features": features,
        "views": views,
        "scale": {"numerator": 1, "denominator": 1},
        "dimensions": [],
        "layout": _layout(views, title),
        "format": "svg",
    }
    assembly_payload = _assembly_compose_payload(
        [_instance(1, "one@1", features)], views, title=title
    )

    part = client.post("/api/v1/drawing/compose", json=part_payload)
    assembly = client.post("/api/v1/drawing/compose", json=assembly_payload)
    assert part.status_code == assembly.status_code == 200
    assert assembly.content == part.content, (
        "single-instance assembly sheet diverged from the part sheet"
    )


# --- 3. Typed degradation: never a 500 ------------------------------------------


def test_all_bodyless_assembly_composes_typed_failed_views() -> None:
    """An assembly where NO instance produces a body (the whole-request typed
    ``no_body``) still composes a 200 SVG sheet — every placed view a typed
    VIEW-FAILED placeholder, never a 500."""
    payload = _assembly_compose_payload(
        [_sketch_only_instance(1), _sketch_only_instance(2)],
        ["front", "top"],
        title="Bodyless Assembly",
    )
    response = client.post("/api/v1/drawing/compose", json=payload)
    assert response.status_code == 200, response.text
    svg = response.text
    assert 'data-view="front" data-view-error="true"' in svg
    assert 'data-view="top" data-view-error="true"' in svg
    assert svg.count("VIEW FAILED") == 2

    sheet_resp = client.post("/api/v1/drawing/compose/sheet", json=payload)
    assert sheet_resp.status_code == 200, sheet_resp.text
    sheet = ComposedSheet.model_validate(sheet_resp.json())
    assert all(v.failed for v in sheet.views)
    assert all(v.edges == [] for v in sheet.views)


def test_assembly_compose_ignores_authored_dimensions_never_500() -> None:
    """Assembly-view dimensioning is out of v1: a request that (incorrectly) carries
    authored ``dimensions`` alongside ``assembly`` must compose the views and IGNORE
    the dimensions (a 200 sheet with no placed dimension) — never trip the strict
    input/measured pairing into a 500."""
    golden = json.loads((_GOLDEN_DIR / "request.json").read_text(encoding="utf-8"))
    payload = _assembly_compose_payload(
        _two_cube_instances(), ["front"], title="Dims Ignored"
    )
    payload["dimensions"] = golden["dimensions"][:1]
    assert payload["dimensions"], "fixture must carry an authored dimension"

    response = client.post("/api/v1/drawing/compose/sheet", json=payload)
    assert response.status_code == 200, response.text
    sheet = ComposedSheet.model_validate(response.json())
    (front,) = [v for v in sheet.views if v.projection == "front"]
    assert front.failed is False
    assert front.dimensions == [], "assembly views place no dimensions in v1"


# --- 4. Determinism + the DE-4 content-addressed cache --------------------------


def test_assembly_compose_is_deterministic_and_cache_keyed() -> None:
    """Same assembly compose request twice ⇒ identical artifact bytes, and the
    second response is served from the content-addressed store (the whole-request
    hash includes ``assembly``): miss then hit."""
    payload = _assembly_compose_payload(
        _two_cube_instances(), ["front"], title="Cache Key Assembly"
    )
    first = client.post("/api/v1/drawing/compose", json=payload)
    second = client.post("/api/v1/drawing/compose", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    assert first.headers["x-loft-artifact-cache"] == "miss"
    assert second.headers["x-loft-artifact-cache"] == "hit"
