"""Stateless measure endpoint + kernel — exact nearest distance (BACKLOG #6a).

Two levels, mirroring the export gates: kernel-level analytic checks against
hand-derived distances/angles on a controlled ``make_box`` (point-point,
point-edge nearest, edge-edge nearest + angle, out-of-range index,
determinism), and HTTP-level checks through the real FastAPI app (the box
golden's two corners → the analytic space diagonal, per BACKLOG #6 acceptance;
edge measurement via a recomputed tree; the 422 envelopes; determinism).

Tolerances are the documented kernel bounds (conftest / box golden), never
ad-hoc epsilons: the box is planar-exact in OCCT, so measured deviation from
analytic is 0.0 up to floating round-off.
"""

import math
from collections.abc import Callable
from typing import Any

import pytest
from build123d import Solid
from fastapi.testclient import TestClient
from geometry.kernel import EdgeIndexError, measure_targets
from geometry.main import app
from py_kit.errors import ValidationApiError
from py_kit.schemas.geometry import Vec3
from py_kit.schemas.measure import (
    EdgeTarget,
    MeasureRequest,
    MeasureResult,
    PointTarget,
)

client = TestClient(app)

#: Kernel linear tolerance (CLAUDE.md 1e-7) — a ceiling, not a fit; the box is
#: planar-exact so real deviation is round-off only.
TOL = 1e-7

#: The box golden's dimensions (goldens/box-10x20x30).
BOX = (10.0, 20.0, 30.0)


def _box() -> Solid:
    return Solid.make_box(*BOX)


def _find_edge_index(
    solid: Solid, a: tuple[float, float, float], b: tuple[float, float, float]
) -> int:
    """Index of the straight edge whose endpoints are {a, b} (order-free).

    The transient edge selector IS an index into ``solid.edges()``; this
    resolves a KNOWN geometric edge to its index so the test can assert an
    independently hand-derived distance, exactly as a picking UI would map a
    clicked edge to its overlay index.
    """
    want = {a, b}
    for index, edge in enumerate(solid.edges()):
        start = edge @ 0.0
        end = edge @ 1.0
        got = {
            (round(start.X, 6), round(start.Y, 6), round(start.Z, 6)),
            (round(end.X, 6), round(end.Y, 6), round(end.Z, 6)),
        }
        if got == want:
            return index
    raise AssertionError(f"no edge with endpoints {want} in the box")


# --- kernel-level analytic checks ------------------------------------------------


def test_point_point_is_the_exact_space_diagonal() -> None:
    """Two opposite box corners → sqrt(10^2 + 20^2 + 30^2)."""
    result = measure_targets(
        PointTarget(position=Vec3(x=0.0, y=0.0, z=0.0)),
        PointTarget(position=Vec3(x=10.0, y=20.0, z=30.0)),
        None,
    )
    assert result.kind == "point_point"
    assert result.distance == pytest.approx(math.sqrt(1400.0), abs=TOL)
    assert (result.delta.x, result.delta.y, result.delta.z) == pytest.approx(
        (10.0, 20.0, 30.0), abs=TOL
    )
    assert result.angle_deg is None


def test_point_edge_nearest_is_perpendicular_drop() -> None:
    """Point (5,4,3) to the origin X-edge (0,0,0)->(10,0,0): drop = 5."""
    box = _box()
    index = _find_edge_index(box, (0.0, 0.0, 0.0), (10.0, 0.0, 0.0))
    result = measure_targets(
        PointTarget(position=Vec3(x=5.0, y=4.0, z=3.0)),
        EdgeTarget(index=index),
        box,
    )
    assert result.kind == "point_edge"
    assert result.distance == pytest.approx(5.0, abs=TOL)  # sqrt(4^2 + 3^2)
    # Nearest point on the edge is the foot of the perpendicular (5,0,0).
    assert (result.point_on_b.x, result.point_on_b.y, result.point_on_b.z) == (
        pytest.approx((5.0, 0.0, 0.0), abs=TOL)
    )
    assert result.angle_deg is None  # a point has no direction


def test_edge_edge_parallel_gives_gap_and_zero_angle() -> None:
    """Two parallel X-edges 20 mm apart in Y → distance 20, angle 0."""
    box = _box()
    a = _find_edge_index(box, (0.0, 0.0, 0.0), (10.0, 0.0, 0.0))
    b = _find_edge_index(box, (0.0, 20.0, 0.0), (10.0, 20.0, 0.0))
    result = measure_targets(EdgeTarget(index=a), EdgeTarget(index=b), box)
    assert result.kind == "edge_edge"
    assert result.distance == pytest.approx(20.0, abs=TOL)
    assert result.angle_deg == pytest.approx(0.0, abs=TOL)


def test_edge_edge_perpendicular_meets_at_corner() -> None:
    """An X-edge and a Y-edge sharing the origin → distance 0, angle 90."""
    box = _box()
    a = _find_edge_index(box, (0.0, 0.0, 0.0), (10.0, 0.0, 0.0))
    b = _find_edge_index(box, (0.0, 0.0, 0.0), (0.0, 20.0, 0.0))
    result = measure_targets(EdgeTarget(index=a), EdgeTarget(index=b), box)
    assert result.kind == "edge_edge"
    assert result.distance == pytest.approx(0.0, abs=TOL)
    assert result.angle_deg == pytest.approx(90.0, abs=TOL)


def test_out_of_range_edge_index_raises() -> None:
    with pytest.raises(EdgeIndexError):
        measure_targets(
            PointTarget(position=Vec3(x=0.0, y=0.0, z=0.0)),
            EdgeTarget(index=999),
            _box(),
        )


def test_kernel_measure_is_deterministic() -> None:
    """Same body + targets → identical result (RESEARCH §9)."""
    box_one = _box()
    box_two = _box()
    index_one = _find_edge_index(box_one, (0.0, 0.0, 30.0), (10.0, 0.0, 30.0))
    index_two = _find_edge_index(box_two, (0.0, 0.0, 30.0), (10.0, 0.0, 30.0))
    point = PointTarget(position=Vec3(x=2.0, y=7.0, z=1.0))
    first = measure_targets(point, EdgeTarget(index=index_one), box_one)
    second = measure_targets(point, EdgeTarget(index=index_two), box_two)
    assert first.model_dump() == second.model_dump()


# --- HTTP-level checks -----------------------------------------------------------

#: A minimal sketch+extrude tree — a 40x25x10 body to measure edges of.
EXTRUDE_TREE: dict[str, Any] = {
    "part_id": "00000000-0000-0000-0000-0000000000fa",
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


def test_measure_two_box_corners_matches_analytic_diagonal() -> None:
    """BACKLOG #6 acceptance: measure two corners of box-10x20x30 → the
    analytic space diagonal, over the real HTTP path."""
    payload = {
        "a": {"kind": "point", "position": {"x": 0.0, "y": 0.0, "z": 0.0}},
        "b": {"kind": "point", "position": {"x": 10.0, "y": 20.0, "z": 30.0}},
    }
    response = client.post("/api/v1/measure", json=payload)
    assert response.status_code == 200, response.text
    result = MeasureResult.model_validate(response.json())
    assert result.kind == "point_point"
    assert result.distance == pytest.approx(math.sqrt(1400.0), abs=TOL)


def test_measure_edge_via_recomputed_tree() -> None:
    """An edge target resolves against the recomputed body and is exact."""
    request = MeasureRequest.model_validate(
        {
            "a": {"kind": "point", "position": {"x": 0.0, "y": 0.0, "z": 0.0}},
            "b": {"kind": "edge", "index": 0},
            "tree": EXTRUDE_TREE,
        }
    )
    response = client.post("/api/v1/measure", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    result = MeasureResult.model_validate(response.json())
    assert result.kind == "point_edge"
    assert result.distance >= 0.0
    # |delta| == distance (witness points are consistent with the scalar).
    magnitude = math.sqrt(result.delta.x**2 + result.delta.y**2 + result.delta.z**2)
    assert magnitude == pytest.approx(result.distance, abs=TOL)


def test_measure_edge_is_deterministic_over_http() -> None:
    """Two identical edge measurements → byte-identical JSON (RESEARCH §9)."""
    payload = MeasureRequest.model_validate(
        {
            "a": {"kind": "edge", "index": 0},
            "b": {"kind": "edge", "index": 1},
            "tree": EXTRUDE_TREE,
        }
    ).model_dump(mode="json")
    first = client.post("/api/v1/measure", json=payload)
    second = client.post("/api/v1/measure", json=payload)
    assert first.status_code == 200
    assert first.content == second.content


def test_edge_target_without_tree_is_422(
    assert_validation_envelope: Callable[[dict[str, Any]], None],
) -> None:
    """An edge target with no tree fails DTO validation at the boundary."""
    response = client.post(
        "/api/v1/measure",
        json={
            "a": {"kind": "point", "position": {"x": 0.0, "y": 0.0, "z": 0.0}},
            "b": {"kind": "edge", "index": 0},
        },
    )
    assert response.status_code == 422
    assert_validation_envelope(response.json())


def test_out_of_range_edge_index_is_clean_422() -> None:
    """A recomputable tree but an impossible edge index → a 422 envelope,
    never a 500."""
    response = client.post(
        "/api/v1/measure",
        json={
            "a": {"kind": "point", "position": {"x": 0.0, "y": 0.0, "z": 0.0}},
            "b": {"kind": "edge", "index": 9999},
            "tree": EXTRUDE_TREE,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "edge_index_out_of_range"


def test_measure_rejects_malformed_payload(
    assert_validation_envelope: Callable[[dict[str, Any]], None],
) -> None:
    response = client.post("/api/v1/measure", json={"a": {"kind": "point"}})
    assert response.status_code == 422
    assert_validation_envelope(response.json())


def test_unexpected_kernel_raise_is_sanitized_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A RAW kernel raise (not EdgeIndexError/MeasureError) is a clean 422
    ``measure_failed`` with the OCCT detail sanitized to the class name — the
    "surfaces as a 422, never a 500" promise, tested at the service function."""
    import geometry.measure as measure_mod

    def boom(*_args: Any, **_kwargs: Any) -> MeasureResult:
        raise RuntimeError("OCCT StdFail_NotDone: gp_Pnt internals leaked here")

    monkeypatch.setattr(measure_mod, "measure_targets", boom)
    with pytest.raises(ValidationApiError) as excinfo:
        measure_mod.evaluate_measure(
            MeasureRequest.model_validate(
                {
                    "a": {"kind": "point", "position": {"x": 0.0, "y": 0.0, "z": 0.0}},
                    "b": {"kind": "point", "position": {"x": 1.0, "y": 0.0, "z": 0.0}},
                }
            )
        )
    error = excinfo.value
    assert error.code == "measure_failed"
    assert error.status_code == 422
    assert "RuntimeError" in error.message  # class name kept
    assert "gp_Pnt internals" not in error.message  # OCCT detail sanitized out


def test_pathological_kernel_raise_is_422_over_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same degenerate raise over the real HTTP path is a 422 envelope,
    never a 500 (the belt-and-braces the module docstring promises)."""
    import geometry.measure as measure_mod

    def boom(*_args: Any, **_kwargs: Any) -> MeasureResult:
        raise RuntimeError("BRepExtrema_DistShapeShape constructor failed")

    monkeypatch.setattr(measure_mod, "measure_targets", boom)
    response = client.post(
        "/api/v1/measure",
        json={
            "a": {"kind": "point", "position": {"x": 0.0, "y": 0.0, "z": 0.0}},
            "b": {"kind": "point", "position": {"x": 1.0, "y": 2.0, "z": 3.0}},
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "measure_failed"
