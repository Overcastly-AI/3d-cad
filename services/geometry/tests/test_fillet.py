"""Fillet feature — API-level behavior of the edge-rounding feature.

Covers the BACKLOG #5 acceptance criteria beyond the golden harness (the
golden ``fillet-plate-r5`` runs every parametrized gate in ``test_goldens.py``
/ ``test_step_roundtrip.py``): the golden tree evaluated over HTTP populates
the analytic mass properties and a fetchable content-addressed mesh; the two
edge selectors (``axis_parallel`` and ``all_edges``) are numerically checked;
and every fillet error path — ``no_target_body``, ``no_fillet_edges``
(bad edge selection), ``fillet_failed`` — is a per-feature error under the
strict-prefix rule (§4.3), never a transport failure.

Edge selection is a **deterministic geometric predicate**, NOT topological
naming (design §2.4 — Phase 2). These tests pin that honest limitation: the
selector is resolved against the body at the feature's point in the tree.

Numeric assertions use the documented golden tolerance (see
``goldens/fillet-plate-r5/expected.json`` — measured-then-set), not ad-hoc
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
    / "fillet-plate-r5"
    / "model.json"
)

#: The documented fillet-golden tolerance (expected.json tolerance_rationale:
#: curved-geometry, measured worst deviation 1.78e-15; 1e-9 reviewed ceiling).
FILLET_TOL = 1e-9

#: Analytic filleted-plate figures (full derivation in the golden expected.json).
FILLET_VOLUME = 9000.0 + 250.0 * math.pi  # 9785.398163397449 mm^3
FILLET_AREA = 2700.0 + 150.0 * math.pi  # 3171.238898038469 mm^2

#: Fixed ids so requests — and therefore responses — are byte-reproducible.
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fb")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-00000000aaaa")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-00000000bbbb")
FILLET_ID = uuid.UUID("00000000-0000-0000-0000-00000000cccc")
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


def fillet_input(
    feature_id: uuid.UUID, selector: dict[str, Any], radius_mm: float
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "fillet",
            "version": 1,
            "params": {"edges": selector, "radius_mm": radius_mm},
        },
    }


def _edge_ref(
    feature_id: uuid.UUID,
    end_a: tuple[float, float, float],
    end_b: tuple[float, float, float],
    midpoint: tuple[float, float, float],
    length_mm: float,
    curve: str = "line",
) -> dict[str, Any]:
    """A stage-1 EdgeSubshapeRef naming ONE edge by its signature (topo-naming)."""
    return {
        "kind": "subshape",
        "feature_id": str(feature_id),
        "subshape_type": "edge",
        "selector": {
            "selector_version": 1,
            "signature": {
                "subshape_type": "edge",
                "curve": curve,
                "end_a": {"x": end_a[0], "y": end_a[1], "z": end_a[2]},
                "end_b": {"x": end_b[0], "y": end_b[1], "z": end_b[2]},
                "midpoint": {"x": midpoint[0], "y": midpoint[1], "z": midpoint[2]},
                "length_mm": length_mm,
            },
        },
    }


def _request(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"part_id": str(PART_ID), "tree_version": 6, "features": features}


def _post(payload: dict[str, Any]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200
    return EvaluateTreeResult.model_validate(response.json())


# --- The golden tree over HTTP -------------------------------------------------------


def test_golden_fillet_tree_evaluates_over_http() -> None:
    """The committed golden model, posted verbatim: all three features ok,
    the analytic filleted-plate volume/area on the wire, a content-addressed
    mesh id, and the new curved topology (10/24/1)."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    result = _post(payload)

    assert [(r.feature_id, r.status) for r in result.features] == [
        (SKETCH_ID, "ok"),
        (EXTRUDE_ID, "ok"),
        (FILLET_ID, "ok"),
    ]
    assert result.last_good_feature_id == FILLET_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(FILLET_VOLUME, abs=FILLET_TOL)
    assert result.properties.surface_area == pytest.approx(FILLET_AREA, abs=FILLET_TOL)
    assert result.properties.topology.faces == 10
    assert result.properties.topology.edges == 24
    assert result.properties.topology.shells == 1
    assert result.mesh_glb_id is not None
    assert result.mesh_glb_id.startswith("sha256:")
    assert result.features[2].data is None  # body-affecting, not a sketch payload


def test_evaluate_response_with_fillet_is_byte_deterministic() -> None:
    """Same tree → identical response bytes incl. mesh_glb_id (a content hash
    of a deterministic GLB) — RESEARCH §9 for the fillet path."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- Edge selectors -----------------------------------------------------------------


def test_axis_parallel_z_rounds_only_the_vertical_edges() -> None:
    """The golden selector: the 4 vertical (Z-parallel) edges round, the 8
    horizontal edges stay sharp — the filleted-plate volume, not a full
    round-over."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                fillet_input(FILLET_ID, {"kind": "axis_parallel", "axis": "Z"}, 5.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(FILLET_VOLUME, abs=FILLET_TOL)


def test_all_edges_rounds_every_edge() -> None:
    """``all_edges`` on the plate rounds all 12 box edges — strictly less
    volume than the vertical-only fillet, and the result is a valid single
    body (the point is the selector plumbing, not a second analytic figure)."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                fillet_input(FILLET_ID, {"kind": "all_edges"}, 2.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    # Rounding every edge removes more than rounding only the 4 vertical ones,
    # and never adds material.
    assert result.properties.volume < 10000.0
    assert result.properties.topology.shells == 1


# --- Picked-edge selection (topological naming §2.4/§10) -----------------------------


#: The selective-fillet golden's analytic figures (full derivation in
#: goldens/fillet-top-edge-40x25x10-r5/expected.json): the 40x25x10 plate with
#: ONE top edge rounded — front-top edge, length 40, r=5.
ONE_EDGE_VOLUME = 9000.0 + 250.0 * math.pi  # 9785.398163397449 mm^3


def test_picked_edge_rounds_only_the_named_edge() -> None:
    """The capability predicates cannot express: round exactly ONE top edge
    (front-top, midpoint (20,0,10)) and leave its three neighbour top edges
    sharp. The analytic one-edge volume, and the new curved topology 7/15/1 —
    contrast `all_edges`/`axis_parallel` which round a whole set."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                fillet_input(
                    FILLET_ID,
                    {
                        "kind": "edges",
                        "refs": [
                            _edge_ref(
                                EXTRUDE_ID,
                                (0.0, 0.0, 10.0),
                                (40.0, 0.0, 10.0),
                                (20.0, 0.0, 10.0),
                                40.0,
                            )
                        ],
                    },
                    5.0,
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(ONE_EDGE_VOLUME, abs=FILLET_TOL)
    assert result.properties.topology.faces == 7
    assert result.properties.topology.edges == 15
    assert result.properties.topology.shells == 1


def test_picked_edge_that_no_longer_exists_is_subshape_unresolved() -> None:
    """A picked signature that matches no current edge is an honest per-feature
    `subshape_unresolved` (topo-naming §5), never a 500 and never a silent
    wrong-edge retarget: the midpoint is at z=99, where no edge lives."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                fillet_input(
                    FILLET_ID,
                    {
                        "kind": "edges",
                        "refs": [
                            _edge_ref(
                                EXTRUDE_ID,
                                (0.0, 0.0, 99.0),
                                (40.0, 0.0, 99.0),
                                (20.0, 0.0, 99.0),
                                40.0,
                            )
                        ],
                    },
                    5.0,
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "subshape_unresolved"
    # last-good body is the un-filleted extrude (§4.3 honest fallback).
    assert result.last_good_feature_id == EXTRUDE_ID


def test_empty_picked_refs_rejected_at_request_validation(
    assert_validation_envelope: Any,
) -> None:
    """A picked-edge selector needs >= 1 ref (min_length): an empty refs list is
    a transport/validation 422, never a silent no-op fillet."""
    payload = _request(
        [
            rectangle_sketch(SKETCH_ID),
            extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
            fillet_input(FILLET_ID, {"kind": "edges", "refs": []}, 5.0),
        ]
    )
    response = client.post("/api/v1/evaluate", json=payload)

    assert response.status_code == 422
    assert_validation_envelope(response.json())


# --- Error paths are per-feature values, never transport failures --------------------


def test_fillet_with_no_prior_body_is_no_target_body() -> None:
    """Fillet needs a body-affecting feature before it (single body chain,
    §7.6): a sketch-only prefix → ``no_target_body``, downstream skipped."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                fillet_input(FILLET_ID, {"kind": "all_edges"}, 2.0),
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


def test_selector_matching_no_edge_is_no_fillet_edges() -> None:
    """Bad edge selection pinned at the API level: a cylinder (from a circle
    profile) has no straight edge parallel to X, so ``axis_parallel X`` matches
    nothing → ``no_fillet_edges`` (honest 'your selector picked no edges',
    distinct from a kernel failure)."""
    result = _post(
        _request(
            [
                circle_sketch(SKETCH_ID, (20.0, 12.5), 6.0),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                fillet_input(FILLET_ID, {"kind": "axis_parallel", "axis": "X"}, 1.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "no_fillet_edges"


def test_radius_too_large_is_fillet_failed() -> None:
    """A radius larger than the adjacent faces admit (r=20 on the 25 mm-deep
    plate: opposing fillets overlap) is a diagnosed kernel outcome, not a
    crash — ``fillet_failed`` pinned to the feature, HTTP 200."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                fillet_input(FILLET_ID, {"kind": "axis_parallel", "axis": "Z"}, 20.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "fillet_failed"
    # last-good body is the un-filleted extrude (§4.3: honest fallback).
    assert result.last_good_feature_id == EXTRUDE_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(10000.0, abs=FILLET_TOL)


def test_non_positive_radius_rejected_at_request_validation(
    assert_validation_envelope: Any,
) -> None:
    """radius_mm has ``gt=0``: a zero/negative radius is a transport/validation
    failure of the call itself (§4.3) — 422 envelope, the same rejection
    documents applies on the write path (shared model)."""
    payload = _request(
        [
            rectangle_sketch(SKETCH_ID),
            extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
            fillet_input(FILLET_ID, {"kind": "all_edges"}, 0.0),
        ]
    )
    response = client.post("/api/v1/evaluate", json=payload)

    assert response.status_code == 422
    assert_validation_envelope(response.json())
