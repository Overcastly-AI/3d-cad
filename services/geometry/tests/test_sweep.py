"""Sweep feature — API-level behavior of the first non-prismatic feature.

Covers the BACKLOG #7 acceptance criteria beyond the golden harness (the golden
``sweep-circle-r8-h30`` runs every parametrized gate in ``test_goldens.py`` /
``test_step_roundtrip.py``): the golden tree evaluated over HTTP populates real
mass properties and a fetchable content-addressed mesh; ``add``/``cut`` and a
bent (multi-segment) path are numerically checked; and every sweep error path —
``profile_not_closed``, ``reference_unresolved`` (bad profile OR bad path),
``sweep_path_closed``, ``sweep_path_not_connected``, ``sweep_path_empty``,
``no_prior_body`` — is a per-feature error pinned under the strict-prefix rule
(design §4.3), never a transport failure.

Numeric assertions use the documented tree-golden tolerance (see
``goldens/sweep-circle-r8-h30/expected.json`` — measured-then-set), not ad-hoc
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
    / "sweep-circle-r8-h30"
    / "model.json"
)

#: The documented tolerance of the sweep golden (expected.json
#: tolerance_rationale: measured worst deviation 1.44e-15; 1e-9 is the reviewed
#: curved-geometry ceiling). Every sweep in this suite is the same curved GProp
#: path.
SWEEP_TOL = 1e-9

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fd")
PROFILE_ID = uuid.UUID("00000000-0000-0000-0000-0000000a0001")
PATH_ID = uuid.UUID("00000000-0000-0000-0000-0000000a0002")
SWEEP_ID = uuid.UUID("00000000-0000-0000-0000-0000000a0003")
EXTRA_ID = uuid.UUID("00000000-0000-0000-0000-0000000a0004")


def _sketch(
    feature_id: uuid.UUID,
    plane: str,
    entities: list[dict[str, Any]],
    constraints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "datum_plane", "plane": plane},
                "entities": entities,
                "constraints": constraints or [],
            },
        },
    }


def _circle(eid: str, cx: float, cy: float, r: float) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "circle",
        "center": {"x": cx, "y": cy},
        "radius": r,
    }


def _line(
    eid: str, start: tuple[float, float], end: tuple[float, float]
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def profile_sketch(
    feature_id: uuid.UUID = PROFILE_ID, r: float = 8.0, *, closed: bool = True
) -> dict[str, Any]:
    """An r-circle profile on XY (``closed=False`` swaps in an OPEN line pair)."""
    if closed:
        return _sketch(feature_id, "XY", [_circle("c1", 0.0, 0.0, r)])
    # Two lines that do not close → profile_not_closed on the profile slot.
    return _sketch(
        feature_id,
        "XY",
        [_line("l1", (0.0, 0.0), (10.0, 0.0)), _line("l2", (10.0, 0.0), (10.0, 5.0))],
    )


def straight_path(
    feature_id: uuid.UUID = PATH_ID, length: float = 30.0
) -> dict[str, Any]:
    """A straight OPEN path up +Z, drawn as a vertical line on XZ."""
    return _sketch(feature_id, "XZ", [_line("p1", (0.0, 0.0), (0.0, length))])


def sweep_input(
    feature_id: uuid.UUID = SWEEP_ID,
    *,
    profile_id: uuid.UUID = PROFILE_ID,
    path_id: uuid.UUID = PATH_ID,
    operation: str = "add",
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sweep",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile_id)},
                "path": {"kind": "feature", "feature_id": str(path_id)},
                "operation": operation,
            },
        },
    }


def _request(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"part_id": str(PART_ID), "tree_version": 3, "features": features}


def _post(payload: dict[str, Any]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200
    return EvaluateTreeResult.model_validate(response.json())


# --- The golden tree over HTTP -------------------------------------------------------


def test_golden_tree_evaluates_with_body_artifact_over_http() -> None:
    """The committed sweep golden, posted verbatim: all three features ok, the
    cylinder volume pi*r^2*L on the wire, content-addressed mesh id."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    result = _post(payload)

    assert [(r.feature_id, r.status) for r in result.features] == [
        (PROFILE_ID, "ok"),
        (PATH_ID, "ok"),
        (SWEEP_ID, "ok"),
    ]
    assert result.last_good_feature_id == SWEEP_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        math.pi * 64.0 * 30.0, abs=SWEEP_TOL
    )
    assert result.properties.surface_area == pytest.approx(
        2.0 * math.pi * 8.0 * 38.0, abs=SWEEP_TOL
    )
    assert result.mesh_glb_id is not None
    assert result.mesh_glb_id.startswith("sha256:")


def test_evaluate_response_with_body_is_byte_deterministic() -> None:
    """Same sweep tree → identical response bytes INCLUDING mesh_glb_id
    (a content hash of a deterministic GLB) — RESEARCH §9."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- Valid sweep variants ------------------------------------------------------------


def test_bent_path_sweeps_a_valid_single_solid() -> None:
    """A two-segment (L-shaped) path sweeps a circle around a bend into ONE
    connected solid — the non-prismatic capability the feature exists for."""
    # Path: up +Z 20, then over +X 15 (on XZ, sketch (x,y)->world (x,0,y)).
    path = _sketch(
        PATH_ID,
        "XZ",
        [_line("p1", (0.0, 0.0), (0.0, 20.0)), _line("p2", (0.0, 20.0), (15.0, 20.0))],
    )
    result = _post(_request([profile_sketch(r=3.0), path, sweep_input()]))

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume > 0.0


def test_sweep_cut_removes_a_swept_channel() -> None:
    """Sweep-add a fat cylinder, then sweep-cut a thinner coaxial one: the cut
    is a per-feature ok that reduces the body volume."""
    result = _post(
        _request(
            [
                profile_sketch(PROFILE_ID, r=8.0),
                straight_path(PATH_ID),
                sweep_input(SWEEP_ID),
                profile_sketch(EXTRA_ID, r=4.0),
                sweep_input(
                    uuid.UUID("00000000-0000-0000-0000-0000000a0005"),
                    profile_id=EXTRA_ID,
                    operation="cut",
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok", "ok"]
    assert result.properties is not None
    # annulus (r_o=8, r_i=4) x L=30: pi*(64-16)*30
    assert result.properties.volume == pytest.approx(
        math.pi * (64.0 - 16.0) * 30.0, abs=SWEEP_TOL
    )


# --- Error paths are per-feature values, never transport failures ---------------------


def test_open_profile_is_profile_not_closed() -> None:
    """An open profile chain → profile_not_closed pinned to the profile sketch
    (shared with extrude/revolve via the same build_profile_face check)."""
    result = _post(
        _request([profile_sketch(closed=False), straight_path(), sweep_input()])
    )

    assert result.features[2].status == "error"
    error = result.features[2].error
    assert error is not None
    assert error.code == "profile_not_closed"
    assert error.upstream_feature_id == PROFILE_ID


def test_closed_path_is_sweep_path_closed() -> None:
    """A CLOSED path (a circle) → sweep_path_closed pinned to the path sketch."""
    closed_path = _sketch(PATH_ID, "XZ", [_circle("p1", 0.0, 20.0, 10.0)])
    result = _post(_request([profile_sketch(), closed_path, sweep_input()]))

    assert result.features[2].status == "error"
    error = result.features[2].error
    assert error is not None
    assert error.code == "sweep_path_closed"
    assert error.upstream_feature_id == PATH_ID
    assert result.mesh_glb_id is None


def test_disjoint_path_is_sweep_path_not_connected() -> None:
    """Two disjoint path segments → sweep_path_not_connected."""
    split_path = _sketch(
        PATH_ID,
        "XZ",
        [_line("p1", (0.0, 0.0), (0.0, 10.0)), _line("p2", (5.0, 20.0), (5.0, 30.0))],
    )
    result = _post(_request([profile_sketch(), split_path, sweep_input()]))

    assert result.features[2].status == "error"
    error = result.features[2].error
    assert error is not None
    assert error.code == "sweep_path_not_connected"
    assert error.upstream_feature_id == PATH_ID


def test_path_with_only_construction_is_sweep_path_empty() -> None:
    """A path sketch whose only entity is construction geometry → the path has
    no trajectory curve: sweep_path_empty."""
    empty_path = _sketch(
        PATH_ID,
        "XZ",
        [{**_line("p1", (0.0, 0.0), (0.0, 30.0)), "construction": True}],
    )
    result = _post(_request([profile_sketch(), empty_path, sweep_input()]))

    assert result.features[2].status == "error"
    error = result.features[2].error
    assert error is not None
    assert error.code == "sweep_path_empty"
    assert error.upstream_feature_id == PATH_ID


def test_unknown_path_reference_is_reference_unresolved() -> None:
    """A path FeatureRef to a feature that is not an ok sketch of this prefix →
    reference_unresolved pinned to the missing path id."""
    result = _post(
        _request([profile_sketch(), straight_path(), sweep_input(path_id=EXTRA_ID)])
    )

    assert result.features[2].status == "error"
    error = result.features[2].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == EXTRA_ID


def test_path_referencing_non_sketch_is_reference_unresolved() -> None:
    """A path that points at the sweep's own profile-consuming feature (not a
    sketch) → reference_unresolved (geometry re-checks §2.2)."""
    result = _post(
        _request(
            [
                profile_sketch(PROFILE_ID, r=8.0),
                straight_path(PATH_ID),
                sweep_input(SWEEP_ID),
                # A second sweep whose PATH points at the first sweep feature.
                sweep_input(EXTRA_ID, profile_id=PROFILE_ID, path_id=SWEEP_ID),
            ]
        )
    )

    assert result.features[3].status == "error"
    error = result.features[3].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == SWEEP_ID


def test_cut_with_no_prior_body_is_feature_error() -> None:
    """A sweep-cut with nothing to cut → no_prior_body (no body-affecting
    feature precedes it)."""
    result = _post(
        _request([profile_sketch(), straight_path(), sweep_input(operation="cut")])
    )

    assert result.features[2].status == "error"
    error = result.features[2].error
    assert error is not None
    assert error.code == "no_prior_body"
    assert result.mesh_glb_id is None
