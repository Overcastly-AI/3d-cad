"""Drawing-view evaluate endpoint — part → projected standard views (design §1.2).

Drawings v1 slice #3: the evaluate function + ``POST /api/v1/drawing/evaluate``
turn a real part feature tree into its requested standard drawing views over the
wire. The projection engine itself is golden-gated in
:mod:`tests.test_drawings_project` (exact HLR, canonical order, byte-determinism);
this module gates the EVALUATE layer — that it reuses ``evaluate_tree`` VERBATIM
(no new part-eval path), maps the internal dataclasses to the neutral py-kit DTOs
with no kernel type crossing, and honours the never-500 error posture (a body-less
part → whole-request ``part_error``; a per-view HLR throw → that view's typed
error, the rest still project).

The part under test is the committed plate-with-holes golden (a 40x25x10 plate
with two Ø10 through-holes) — the SAME model the assembly pipeline tests reuse, so
the projected geometry is analytically known: front view = the 40x10 rectangle,
top view = the 40x25 outline + two radius-5 circles at the hole centres.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from geometry.drawings import evaluate as drawings_evaluate
from geometry.drawings import evaluate_drawing_views
from geometry.drawings.project import ViewProjectionError, project_view
from geometry.main import app
from py_kit.schemas.drawings import (
    EvaluateDrawingViewsRequest,
    EvaluateDrawingViewsResult,
    ViewProjection,
    ViewScale,
)
from py_kit.schemas.features import (
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    SketchFeature,
)

#: Documented per-model tolerance (mm) — the projected coordinates come straight
#: off the exact B-rep through OCCT HLR with no tessellation, so residuals are
#: ulp-scale on this axis-aligned analytic part. Same 1e-7 mm linear tolerance the
#: projection goldens use (tests/test_drawings_project.py; docs/GEOMETRY-QA.md).
COORD_TOL_MM = 1e-7
RADIUS_TOL_MM = 1e-7

_PLATE_MODEL = (
    Path(__file__).resolve().parent.parent
    / "goldens/sketch-extrude-plate-2holes-40x25x10/model.json"
)

client = TestClient(app)


def _plate_features() -> list[EvaluatedFeatureInput]:
    """The committed plate-with-2-holes part's ordered feature list."""
    return EvaluateTreeRequest.model_validate_json(
        _PLATE_MODEL.read_text(encoding="utf-8")
    ).features


def _plate_request(
    *views: ViewProjection, scale: ViewScale | None = None
) -> EvaluateDrawingViewsRequest:
    return EvaluateDrawingViewsRequest(
        part_id=UUID(int=1),
        tree_version=1,
        features=_plate_features(),
        views=list(views),
        scale=scale or ViewScale(numerator=1, denominator=1),
    )


def _view(result: EvaluateDrawingViewsResult, view: str) -> Any:
    got = next((v for v in result.views if v.view == view), None)
    assert got is not None, f"no result for view {view!r}"
    return got


# --- the analytic part → its known views ---------------------------------------


def test_front_view_is_the_analytic_rectangle() -> None:
    """The plate's FRONT view is EXACTLY the 40x10 rectangle: four visible lines at
    the analytic extents, no visible circle (the holes are edge-on)."""
    result = evaluate_drawing_views(_plate_request("front"))
    assert result.part_error is None
    front = _view(result, "front")
    assert front.error is None

    lines = [e for e in front.edges if e.primitive == "line" and e.visible]
    assert len(lines) == 4, f"front outline is 4 visible lines, got {len(lines)}"
    assert not [e for e in front.edges if e.primitive == "circle" and e.visible], (
        "the holes are edge-on in the front view — no visible circle"
    )
    xs = [c for e in lines for c in (e.start.x_mm, e.end.x_mm)]
    ys = [c for e in lines for c in (e.start.y_mm, e.end.y_mm)]
    assert max(xs) - min(xs) == pytest.approx(40.0, abs=COORD_TOL_MM)
    assert max(ys) - min(ys) == pytest.approx(10.0, abs=COORD_TOL_MM)


def test_top_view_carries_the_diameter_10_circles() -> None:
    """The plate's TOP view carries the two Ø10 holes as REAL circles of radius
    5.000 (§1.1 exact-HLR guarantee: not a facet polygon), at the hole centres."""
    result = evaluate_drawing_views(_plate_request("top"))
    top = _view(result, "top")
    assert top.error is None

    circles = [e for e in top.edges if e.primitive == "circle" and e.visible]
    assert len(circles) == 2, f"two holes → two visible circles, got {len(circles)}"
    for circle in circles:
        assert circle.radius == pytest.approx(5.0, abs=RADIUS_TOL_MM), (
            f"Ø10 hole must project to radius 5.000, got {circle.radius!r}"
        )
        assert circle.center is not None
    centers = {
        (round(c.center.x_mm, 3), round(c.center.y_mm, 3))
        for c in circles
        if c.center is not None
    }
    assert centers == {(12.0, 12.5), (28.0, 12.5)}


def test_multiple_views_returned_in_request_order() -> None:
    """Every requested view is projected and returned in request order (the sheet
    auto-layout of the standard 4 is a later slice; this slice just projects each)."""
    result = evaluate_drawing_views(_plate_request("top", "front", "right", "iso"))
    assert [v.view for v in result.views] == ["top", "front", "right", "iso"]
    assert all(v.error is None and v.edges for v in result.views)


def test_scale_multiplies_every_coordinate() -> None:
    """A 2:1 scale doubles every projected coordinate (model-mm → sheet-mm) and
    echoes the exact rational scale back on each view result."""
    unit = _view(evaluate_drawing_views(_plate_request("front")), "front")
    scaled = evaluate_drawing_views(
        _plate_request("front", scale=ViewScale(numerator=2, denominator=1))
    )
    scaled_front = _view(scaled, "front")
    assert scaled_front.scale.numerator == 2 and scaled_front.scale.denominator == 1

    unit_lines = sorted(
        (e for e in unit.edges if e.primitive == "line"),
        key=lambda e: (e.start.x_mm, e.start.y_mm),
    )
    scaled_lines = sorted(
        (e for e in scaled_front.edges if e.primitive == "line"),
        key=lambda e: (e.start.x_mm, e.start.y_mm),
    )
    assert len(unit_lines) == len(scaled_lines)
    for u, s in zip(unit_lines, scaled_lines, strict=True):
        assert s.start.x_mm == pytest.approx(2.0 * u.start.x_mm, abs=COORD_TOL_MM)
        assert s.end.y_mm == pytest.approx(2.0 * u.end.y_mm, abs=COORD_TOL_MM)


def test_edges_cross_as_pure_pydantic_no_kernel_type() -> None:
    """Every projected edge is a neutral py-kit DTO — plain floats/strings/bools,
    no kernel handle. The boundary guarantee (CLAUDE.md): no OCCT type crosses."""
    result = evaluate_drawing_views(_plate_request("top"))
    # round-trips through JSON with no custom encoder → pure primitives only.
    dumped = result.model_dump_json()
    assert EvaluateDrawingViewsResult.model_validate_json(dumped) == result
    edge = next(e for v in result.views for e in v.edges)
    assert isinstance(edge.start.x_mm, float) and isinstance(edge.visible, bool)


# --- honest error posture (design §1.5 / §4) -----------------------------------


def test_bodyless_part_is_a_whole_request_error_not_a_raise() -> None:
    """A part with a sketch but NO body-affecting feature evaluates to no body — a
    whole-request ``part_error`` with empty ``views``, never a raise / 500 / empty
    success masquerading as a valid drawing."""
    sketch = next(f for f in _plate_features() if isinstance(f.feature, SketchFeature))
    request = EvaluateDrawingViewsRequest(
        part_id=UUID(int=2),
        tree_version=1,
        features=[sketch],
        views=["front", "top"],
    )
    result = evaluate_drawing_views(request)
    assert result.views == []
    assert result.part_error is not None
    assert result.part_error.code == "no_body"


def test_per_view_hlr_failure_is_a_typed_per_view_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``ViewProjectionError`` on ONE view becomes THAT view's typed
    ``view_projection_failed`` entry (empty edges) while the other requested views
    still project — never a raise, never failing the whole request (§1.5)."""

    def flaky_project_view(body: object, view: str, scale: float = 1.0) -> object:
        if view == "top":
            raise ViewProjectionError("top", "synthetic HLR failure")
        return project_view(body, view, scale=scale)  # type: ignore[arg-type]

    monkeypatch.setattr(drawings_evaluate, "project_view", flaky_project_view)

    result = evaluate_drawing_views(_plate_request("front", "top"))
    front = _view(result, "front")
    top = _view(result, "top")
    assert front.error is None and front.edges, "the healthy view still projects"
    assert top.error is not None, "the failing view carries a typed error"
    assert top.error.code == "view_projection_failed"
    assert top.edges == [], "a failed view carries no edges"


# --- the endpoint (mirrors /assembly/evaluate wiring) --------------------------


def test_endpoint_projects_the_plate() -> None:
    """``POST /api/v1/drawing/evaluate`` returns 200 with the per-view projected
    geometry (identity-free — the gateway owns auth, same posture as assembly)."""
    response = client.post(
        "/api/v1/drawing/evaluate",
        json=_plate_request("front", "top").model_dump(mode="json"),
    )
    assert response.status_code == 200, response.text
    result = EvaluateDrawingViewsResult.model_validate(response.json())
    assert result.part_error is None
    assert [v.view for v in result.views] == ["front", "top"]
    top = _view(result, "top")
    circles = [e for e in top.edges if e.primitive == "circle" and e.visible]
    assert len(circles) == 2
    assert all(c.radius == pytest.approx(5.0, abs=RADIUS_TOL_MM) for c in circles)


def test_endpoint_is_deterministic() -> None:
    """Identical request → byte-identical response JSON (RESEARCH §9): the canonical
    edge order + fixed serialisation carry through the DTO boundary unchanged."""
    payload = _plate_request("front", "top", "right", "iso").model_dump(mode="json")
    first = client.post("/api/v1/drawing/evaluate", json=payload)
    second = client.post("/api/v1/drawing/evaluate", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
