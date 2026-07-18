"""Chamfer feature — API-level behavior of the edge-beveling feature.

Covers the BACKLOG #6 acceptance criteria beyond the golden harness (the
golden ``chamfer-plate-d5`` runs every parametrized gate in
``test_goldens.py`` / ``test_step_roundtrip.py``): the golden tree evaluated
over HTTP populates the analytic mass properties and a fetchable
content-addressed mesh; the two edge selectors (``axis_parallel`` and
``all_edges``) are numerically checked; and every chamfer error path —
``no_target_body``, ``no_chamfer_edges`` (bad edge selection),
``chamfer_failed`` — is a per-feature error under the strict-prefix rule
(§4.3), never a transport failure.

Chamfer reuses fillet's SAME ``EdgeSelector`` plumbing (design §2.4) resolved
through the shared ``select_edges`` kernel helper — a deterministic geometric
predicate, NOT topological naming (Phase 2). These tests pin that honest
limitation: the selector is resolved against the body at the feature's point
in the tree.

Numeric assertions use the documented golden tolerance (see
``goldens/chamfer-plate-d5/expected.json`` — measured-then-set), not ad-hoc
epsilons.
"""

import json
import math
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.main import app
from py_kit.schemas.features import EvaluateTreeResult

client = TestClient(app)

GOLDEN_MODEL = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "chamfer-plate-d5"
    / "model.json"
)

#: The documented chamfer-golden tolerance (expected.json tolerance_rationale:
#: all-planar, volume/area exact; residual ulp-scale, 1e-9 reviewed ceiling).
CHAMFER_TOL = 1e-9

#: Analytic chamfered-plate figures (full derivation in the golden expected.json).
CHAMFER_VOLUME = 9500.0  # 10000 - 4*(h*r^2/2), exact
CHAMFER_AREA = 2800.0 + 200.0 * math.sqrt(2)  # 3082.842712474619 mm^2

#: Fixed ids so requests — and therefore responses — are byte-reproducible.
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fc")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-00000000aaaa")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-00000000bbbb")
CHAMFER_ID = uuid.UUID("00000000-0000-0000-0000-00000000cccc")
TAIL_ID = uuid.UUID("00000000-0000-0000-0000-00000000eeee")

XY_PLANE: dict[str, Any] = {"kind": "datum_plane", "plane": "XY"}


def _line(
    eid: str, start: tuple[float, float], end: tuple[float, float]
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def rectangle_sketch(feature_id: uuid.UUID) -> dict[str, Any]:
    """A closed 40x25 rectangle profile (entities already at position)."""
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(XY_PLANE),
                "entities": [
                    _line("e1", (0.0, 0.0), (40.0, 0.0)),
                    _line("e2", (40.0, 0.0), (40.0, 25.0)),
                    _line("e3", (40.0, 25.0), (0.0, 25.0)),
                    _line("e4", (0.0, 25.0), (0.0, 0.0)),
                ],
                "constraints": [],
            },
        },
    }


def circle_sketch(
    feature_id: uuid.UUID, center: tuple[float, float], radius: float
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(XY_PLANE),
                "entities": [
                    {
                        "id": "c1",
                        "kind": "circle",
                        "center": {"x": center[0], "y": center[1]},
                        "radius": radius,
                    }
                ],
                "constraints": [],
            },
        },
    }


def extrude_input(
    feature_id: uuid.UUID, profile_id: uuid.UUID, distance_mm: float
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile_id)},
                "distance_mm": distance_mm,
                "operation": "add",
                "direction": "normal",
            },
        },
    }


def chamfer_input(
    feature_id: uuid.UUID, selector: dict[str, Any], distance_mm: float
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "chamfer",
            "version": 1,
            "params": {"edges": selector, "distance_mm": distance_mm},
        },
    }


def _request(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"part_id": str(PART_ID), "tree_version": 6, "features": features}


def _post(payload: dict[str, Any]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200
    return EvaluateTreeResult.model_validate(response.json())


# --- The golden tree over HTTP -------------------------------------------------------


def test_golden_chamfer_tree_evaluates_over_http() -> None:
    """The committed golden model, posted verbatim: all three features ok,
    the analytic chamfered-plate volume/area on the wire, a content-addressed
    mesh id, and the new all-planar bevel topology (10/24/1)."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    result = _post(payload)

    assert [(r.feature_id, r.status) for r in result.features] == [
        (SKETCH_ID, "ok"),
        (EXTRUDE_ID, "ok"),
        (CHAMFER_ID, "ok"),
    ]
    assert result.last_good_feature_id == CHAMFER_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(CHAMFER_VOLUME, abs=CHAMFER_TOL)
    assert result.properties.surface_area == pytest.approx(
        CHAMFER_AREA, abs=CHAMFER_TOL
    )
    assert result.properties.topology.faces == 10
    assert result.properties.topology.edges == 24
    assert result.properties.topology.shells == 1
    assert result.mesh_glb_id is not None
    assert result.mesh_glb_id.startswith("sha256:")
    assert result.features[2].data is None  # body-affecting, not a sketch payload


def test_evaluate_response_with_chamfer_is_byte_deterministic() -> None:
    """Same tree → identical response bytes incl. mesh_glb_id (a content hash
    of a deterministic GLB) — RESEARCH §9 for the chamfer path."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- Edge selectors -----------------------------------------------------------------


def test_axis_parallel_z_bevels_only_the_vertical_edges() -> None:
    """The golden selector: the 4 vertical (Z-parallel) edges bevel, the 8
    horizontal edges stay sharp — the chamfered-plate volume, not a full
    bevel."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                chamfer_input(CHAMFER_ID, {"kind": "axis_parallel", "axis": "Z"}, 5.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(CHAMFER_VOLUME, abs=CHAMFER_TOL)


def test_all_edges_bevels_every_edge() -> None:
    """``all_edges`` on the plate bevels all 12 box edges — strictly less
    volume than the vertical-only chamfer, and the result is a valid single
    body (the point is the shared selector plumbing, not a second analytic
    figure)."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                chamfer_input(CHAMFER_ID, {"kind": "all_edges"}, 2.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    # Beveling every edge removes more than beveling only the 4 vertical ones,
    # and never adds material.
    assert result.properties.volume < 10000.0
    assert result.properties.topology.shells == 1


# --- Error paths are per-feature values, never transport failures --------------------


def test_chamfer_with_no_prior_body_is_no_target_body() -> None:
    """Chamfer needs a body-affecting feature before it (single body chain,
    §7.6): a sketch-only prefix → ``no_target_body``, downstream skipped."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                chamfer_input(CHAMFER_ID, {"kind": "all_edges"}, 2.0),
                rectangle_sketch(TAIL_ID),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "error", "skipped"]
    error = result.features[1].error
    assert error is not None
    assert error.code == "no_target_body"
    assert result.mesh_glb_id is None
    assert result.properties is None


def test_selector_matching_no_edge_is_no_chamfer_edges() -> None:
    """Bad edge selection pinned at the API level: a cylinder (from a circle
    profile) has no straight edge parallel to X, so ``axis_parallel X`` matches
    nothing → ``no_chamfer_edges`` (honest 'your selector picked no edges',
    distinct from a kernel failure)."""
    result = _post(
        _request(
            [
                circle_sketch(SKETCH_ID, (20.0, 12.5), 6.0),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                chamfer_input(CHAMFER_ID, {"kind": "axis_parallel", "axis": "X"}, 1.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "no_chamfer_edges"


def test_distance_too_large_is_chamfer_failed() -> None:
    """A distance larger than the adjacent faces admit (d=20 on the 25 mm-deep
    plate: opposing chamfers overlap) is a diagnosed kernel outcome, not a
    crash — ``chamfer_failed`` pinned to the feature, HTTP 200."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                chamfer_input(CHAMFER_ID, {"kind": "axis_parallel", "axis": "Z"}, 20.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "chamfer_failed"
    # last-good body is the un-chamfered extrude (§4.3: honest fallback).
    assert result.last_good_feature_id == EXTRUDE_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(10000.0, abs=CHAMFER_TOL)


def test_non_positive_distance_rejected_at_request_validation(
    assert_validation_envelope: Any,
) -> None:
    """distance_mm has ``gt=0``: a zero/negative distance is a transport/
    validation failure of the call itself (§4.3) — 422 envelope, the same
    rejection documents applies on the write path (shared model)."""
    payload = _request(
        [
            rectangle_sketch(SKETCH_ID),
            extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
            chamfer_input(CHAMFER_ID, {"kind": "all_edges"}, 0.0),
        ]
    )
    response = client.post("/api/v1/evaluate", json=payload)

    assert response.status_code == 422
    assert_validation_envelope(response.json())
