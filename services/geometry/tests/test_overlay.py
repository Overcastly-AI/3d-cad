"""Stateless overlay endpoint + kernel — pickable selection geometry (#6b).

Two levels, mirroring the measure gates. The HEADLINE gate is order-equality:
``overlay.edges[i]`` MUST be the SAME B-rep edge ``measure`` resolves for
``EdgeTarget(index=i)`` — enumerated once via ``body.edges()`` in both paths —
or an edge measurement silently targets the wrong edge (the review's headline
6b risk). Proven at the kernel level (shared ``body.edges()``) AND over the real
HTTP path (overlay's start coords measured against the edge at the same index →
distance 0). The rest: exact vertex coords, curved-edge polyline sampling at the
mesh tolerance, and the 422 envelopes (never a 500).

Tolerances are the documented kernel bound (box golden), never ad-hoc epsilons:
the box is planar-exact in OCCT, so deviation from analytic is round-off only.
"""

from collections.abc import Callable
from typing import Any

import pytest
from build123d import GeomType, Solid
from fastapi.testclient import TestClient
from geometry.kernel import measure_targets, selection_overlay
from geometry.main import app
from py_kit.errors import ValidationApiError
from py_kit.schemas.geometry import Vec3
from py_kit.schemas.measure import EdgeTarget, PointTarget
from py_kit.schemas.overlay import OverlayRequest, OverlayResult

client = TestClient(app)

#: Kernel linear tolerance (CLAUDE.md 1e-7) — a ceiling, not a fit.
TOL = 1e-7

#: The box golden's dimensions (goldens/box-10x20x30): 8 vertices, 12 edges.
BOX = (10.0, 20.0, 30.0)


def _box() -> Solid:
    return Solid.make_box(*BOX)


def _key(vec: Vec3) -> tuple[float, float, float]:
    return (round(vec.x, 6), round(vec.y, 6), round(vec.z, 6))


# --- kernel-level checks ---------------------------------------------------------


def test_overlay_vertices_are_the_exact_box_corners() -> None:
    """Eight vertices, exact world-mm coordinates (never a mesh snap)."""
    overlay = selection_overlay(_box(), 0.1)
    assert len(overlay.vertices) == 8
    corners = {(x, y, z) for x in (0.0, 10.0) for y in (0.0, 20.0) for z in (0.0, 30.0)}
    assert {_key(v) for v in overlay.vertices} == corners


def test_overlay_edges_all_lines_on_a_box() -> None:
    overlay = selection_overlay(_box(), 0.1)
    assert len(overlay.edges) == 12
    assert all(edge.kind == "line" for edge in overlay.edges)
    # A straight edge's polyline is exactly its two endpoints.
    for edge in overlay.edges:
        assert edge.polyline == [edge.start, edge.end]


def test_overlay_edge_index_matches_measure_edge_index() -> None:
    """HEADLINE GATE: overlay.edges[i] IS the edge measure resolves for
    EdgeTarget(index=i). Enumerate body.edges() ONCE as ground truth; assert
    the overlay is index-aligned with it AND that measuring a point ON the
    overlay edge's start against EdgeTarget(index=i) gives distance 0."""
    box = _box()
    overlay = selection_overlay(box, 0.1)
    edges = box.edges()  # the exact call measure's _resolve_target makes
    assert len(overlay.edges) == len(edges)

    for index, edge in enumerate(edges):
        start, end = edge @ 0.0, edge @ 1.0
        truth = {
            (round(start.X, 6), round(start.Y, 6), round(start.Z, 6)),
            (round(end.X, 6), round(end.Y, 6), round(end.Z, 6)),
        }
        overlay_edge = overlay.edges[index]
        assert {_key(overlay_edge.start), _key(overlay_edge.end)} == truth, (
            f"overlay edge {index} endpoints diverge from body.edges()[{index}]"
        )
        # The overlay edge's start lies ON the edge measure resolves at the
        # SAME index → nearest distance is exactly 0. If the two enumerations
        # disagreed, this would be a nonzero gap.
        result = measure_targets(
            PointTarget(position=overlay_edge.start), EdgeTarget(index=index), box
        )
        assert result.distance == pytest.approx(0.0, abs=TOL), (
            f"overlay edge {index} start is not on measure's edge {index}"
        )


def test_overlay_curved_edge_is_sampled_to_a_circle_polyline() -> None:
    """A cylinder's circular edges are tagged 'circle' and sampled to a
    polyline finer than two points, at the given deflection."""
    cylinder = Solid.make_cylinder(5.0, 10.0)
    overlay = selection_overlay(cylinder, 0.1)
    circles = [edge for edge in overlay.edges if edge.kind == "circle"]
    assert circles, "cylinder should expose circular edges"
    for circle in circles:
        assert len(circle.polyline) > 2  # curved → many chords, not just endpoints
    # Sanity: the kernel really sees these as circles.
    assert any(e.geom_type == GeomType.CIRCLE for e in cylinder.edges())


def test_overlay_is_deterministic() -> None:
    """Same body → identical overlay (RESEARCH §9)."""
    first = selection_overlay(_box(), 0.1)
    second = selection_overlay(_box(), 0.1)
    assert first.model_dump() == second.model_dump()


# --- HTTP-level checks -----------------------------------------------------------

#: A minimal sketch+extrude tree — a 40x25x10 body to overlay.
EXTRUDE_TREE: dict[str, Any] = {
    "part_id": "00000000-0000-0000-0000-0000000000fb",
    "tree_version": 4,
    "features": [
        {
            "id": "00000000-0000-0000-0000-00000000aaaa",
            "feature": {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": {"kind": "datum_plane", "plane": "XY"},
                    "entities": [
                        {
                            "id": "e1",
                            "kind": "line",
                            "start": {"x": 0.0, "y": 0.0},
                            "end": {"x": 40.0, "y": 0.0},
                        },
                        {
                            "id": "e2",
                            "kind": "line",
                            "start": {"x": 40.0, "y": 0.0},
                            "end": {"x": 40.0, "y": 25.0},
                        },
                        {
                            "id": "e3",
                            "kind": "line",
                            "start": {"x": 40.0, "y": 25.0},
                            "end": {"x": 0.0, "y": 25.0},
                        },
                        {
                            "id": "e4",
                            "kind": "line",
                            "start": {"x": 0.0, "y": 25.0},
                            "end": {"x": 0.0, "y": 0.0},
                        },
                    ],
                    "constraints": [
                        {"kind": "horizontal", "entity": "e1"},
                        {"kind": "vertical", "entity": "e2"},
                    ],
                },
            },
        },
        {
            "id": "00000000-0000-0000-0000-00000000bbbb",
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {
                        "kind": "feature",
                        "feature_id": "00000000-0000-0000-0000-00000000aaaa",
                    },
                    "distance_mm": 10.0,
                    "operation": "add",
                    "direction": "normal",
                },
            },
        },
    ],
    "linear_deflection": 0.1,
}


def _overlay_payload(tree: dict[str, Any]) -> dict[str, Any]:
    return OverlayRequest.model_validate({"tree": tree}).model_dump(mode="json")


def test_overlay_over_http_returns_pickable_geometry() -> None:
    response = client.post("/api/v1/overlay", json=_overlay_payload(EXTRUDE_TREE))
    assert response.status_code == 200, response.text
    overlay = OverlayResult.model_validate(response.json())
    assert len(overlay.vertices) == 8  # a box prism: 8 corners
    assert len(overlay.edges) == 12


def test_overlay_and_measure_agree_on_edge_index_over_http() -> None:
    """The two ENDPOINTS agree on edge index: for every overlay edge, measuring
    its start against EdgeTarget(index=i) via /measure gives distance 0."""
    overlay_response = client.post(
        "/api/v1/overlay", json=_overlay_payload(EXTRUDE_TREE)
    )
    assert overlay_response.status_code == 200, overlay_response.text
    overlay = OverlayResult.model_validate(overlay_response.json())

    for index, edge in enumerate(overlay.edges):
        measure_payload = {
            "a": {"kind": "point", "position": edge.start.model_dump()},
            "b": {"kind": "edge", "index": index},
            "tree": EXTRUDE_TREE,
        }
        measure_response = client.post("/api/v1/measure", json=measure_payload)
        assert measure_response.status_code == 200, measure_response.text
        distance = measure_response.json()["distance"]
        assert distance == pytest.approx(0.0, abs=TOL), (
            f"overlay edge {index} start not on measure's edge {index}"
        )


def test_overlay_is_deterministic_over_http() -> None:
    payload = _overlay_payload(EXTRUDE_TREE)
    first = client.post("/api/v1/overlay", json=payload)
    second = client.post("/api/v1/overlay", json=payload)
    assert first.status_code == 200
    assert first.content == second.content


def test_overlay_of_bodyless_tree_is_clean_422() -> None:
    """A sketch-only tree recomputes to no body → 422 tree_overlay_failed,
    never a 500."""
    sketch_only = {
        "part_id": EXTRUDE_TREE["part_id"],
        "tree_version": 1,
        "features": [EXTRUDE_TREE["features"][0]],  # sketch, no extrude
        "linear_deflection": 0.1,
    }
    response = client.post("/api/v1/overlay", json=_overlay_payload(sketch_only))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "tree_overlay_failed"


def test_overlay_rejects_malformed_payload(
    assert_validation_envelope: Callable[[dict[str, Any]], None],
) -> None:
    response = client.post("/api/v1/overlay", json={"tree": {"features": "nope"}})
    assert response.status_code == 422
    assert_validation_envelope(response.json())


def test_unexpected_kernel_raise_is_sanitized_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raw kernel raise while enumerating the overlay is a clean 422
    ``overlay_failed`` with OCCT detail sanitized to the class name."""
    import geometry.overlay as overlay_mod

    def boom(*_args: Any, **_kwargs: Any) -> OverlayResult:
        raise RuntimeError("OCCT GCPnts internals leaked here")

    monkeypatch.setattr(overlay_mod, "selection_overlay", boom)
    with pytest.raises(ValidationApiError) as excinfo:
        overlay_mod.evaluate_overlay(
            OverlayRequest.model_validate({"tree": EXTRUDE_TREE})
        )
    error = excinfo.value
    assert error.code == "overlay_failed"
    assert error.status_code == 422
    assert "RuntimeError" in error.message
    assert "GCPnts internals" not in error.message
