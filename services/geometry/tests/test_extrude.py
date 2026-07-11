"""Extrude feature — API-level behavior of the first body-affecting feature.

Covers the BACKLOG #6 acceptance criteria beyond the golden harness (the
golden ``sketch-extrude-40x25x10`` runs every parametrized gate in
``test_goldens.py`` / ``test_step_roundtrip.py``): the golden tree evaluated
over HTTP populates real mass properties and a fetchable content-addressed
mesh; ``add``/``cut`` and ``direction: normal|reverse`` semantics are
numerically checked; the **broken-profile strict-prefix case** (unclosed
profile → ``profile_not_closed`` pinned to the extrude, downstream skipped,
last-good semantics per design §4.3/§6 failure flavour) is demonstrated
end-to-end at the API level; and every extrude error path is a per-feature
error, never a transport failure.

Numeric assertions use the documented tree-golden tolerance (see
``goldens/sketch-extrude-40x25x10/expected.json`` — measured-then-set), not
ad-hoc epsilons.
"""

import hashlib
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
    / "sketch-extrude-40x25x10"
    / "model.json"
)

#: The documented tolerance of the sketch-extrude golden (expected.json
#: tolerance_rationale: measured worst deviation 1.82e-12 mm^3 on the
#: wire→face→prism path; 1e-9 is the reviewed ceiling). Booleans in this
#: suite are the same planar construction path.
EXTRUDE_TOL = 1e-9

#: Fixed ids so requests — and therefore responses — are byte-reproducible.
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fa")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-00000000aaaa")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-00000000bbbb")
SKETCH2_ID = uuid.UUID("00000000-0000-0000-0000-00000000cccc")
EXTRUDE2_ID = uuid.UUID("00000000-0000-0000-0000-00000000dddd")
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


def rectangle_sketch(
    feature_id: uuid.UUID,
    x0: float = 0.0,
    y0: float = 0.0,
    x1: float = 40.0,
    y1: float = 25.0,
    *,
    close: bool = True,
) -> dict[str, Any]:
    """An unconstrained rectangle profile (entities already at position).

    ``close=False`` drops the closing edge — the broken-profile flavour
    (three sides only, an open chain the solver happily solves).
    """
    entities = [
        _line("e1", (x0, y0), (x1, y0)),
        _line("e2", (x1, y0), (x1, y1)),
        _line("e3", (x1, y1), (x0, y1)),
    ]
    if close:
        entities.append(_line("e4", (x0, y1), (x0, y0)))
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(XY_PLANE),
                "entities": entities,
                "constraints": [],
            },
        },
    }


def circle_sketch(
    feature_id: uuid.UUID, center: tuple[float, float], radius: float, count: int = 1
) -> dict[str, Any]:
    entities = [
        {
            "id": f"c{i + 1}",
            "kind": "circle",
            "center": {"x": center[0] + 3 * radius * i, "y": center[1]},
            "radius": radius,
        }
        for i in range(count)
    ]
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(XY_PLANE),
                "entities": entities,
                "constraints": [],
            },
        },
    }


def extrude_input(
    feature_id: uuid.UUID,
    profile_id: uuid.UUID,
    distance_mm: float,
    operation: str = "add",
    direction: str = "normal",
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile_id)},
                "distance_mm": distance_mm,
                "operation": operation,
                "direction": direction,
            },
        },
    }


def _request(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"part_id": str(PART_ID), "tree_version": 4, "features": features}


def _post(payload: dict[str, Any]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200
    return EvaluateTreeResult.model_validate(response.json())


# --- The golden tree over HTTP -------------------------------------------------------


def test_golden_tree_evaluates_with_body_artifact_over_http() -> None:
    """The committed golden model, posted verbatim to /api/v1/evaluate:
    both features ok, §6 numbers on the wire, content-addressed mesh id."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    result = _post(payload)

    assert [(r.feature_id, r.status) for r in result.features] == [
        (SKETCH_ID, "ok"),
        (EXTRUDE_ID, "ok"),
    ]
    assert result.last_good_feature_id == EXTRUDE_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(10000.0, abs=EXTRUDE_TOL)
    assert result.properties.surface_area == pytest.approx(3300.0, abs=EXTRUDE_TOL)
    assert result.mesh_glb_id is not None
    assert result.mesh_glb_id.startswith("sha256:")
    # The extrude produced a body, not a sketch payload (§7.10).
    assert result.features[1].data is None


def test_mesh_glb_id_is_fetchable_and_content_addressed() -> None:
    """GET /api/v1/meshes/{id} returns the GLB whose sha256 IS the id — the
    interim §7.8 delivery path with object-storage-compatible semantics."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    result = _post(payload)
    assert result.mesh_glb_id is not None

    fetched = client.get(f"/api/v1/meshes/{result.mesh_glb_id}")
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "model/gltf-binary"
    assert fetched.content.startswith(b"glTF")
    assert f"sha256:{hashlib.sha256(fetched.content).hexdigest()}" == result.mesh_glb_id


def test_unknown_mesh_id_is_404_envelope() -> None:
    """A miss (evicted/unknown) is an honest 404 — the caller re-evaluates
    (results are pure functions of the request, design §4.4/§7.8)."""
    response = client.get(f"/api/v1/meshes/sha256:{'0' * 64}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "mesh_not_found"


def test_evaluate_response_with_body_is_byte_deterministic() -> None:
    """Same tree → identical response bytes INCLUDING mesh_glb_id (a content
    hash of a deterministic GLB) — RESEARCH §9 for the body-affecting path."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- Broken profile: the strict-prefix rule end-to-end (§4.3, §6 failure flavour) ----


def test_broken_profile_strict_prefix_at_api_level() -> None:
    """Unclosed profile → the sketch itself is ok, the extrude errors with
    ``profile_not_closed`` pinned to the sketch as upstream, everything
    downstream is skipped, and last-good semantics hold: the artifact fields
    honestly reflect that no body exists (§6 failure flavour, verbatim)."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID, close=False),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                rectangle_sketch(TAIL_ID),
            ]
        )
    )

    assert [(r.feature_id, r.status) for r in result.features] == [
        (SKETCH_ID, "ok"),
        (EXTRUDE_ID, "error"),
        (TAIL_ID, "skipped"),
    ]
    error = result.features[1].error
    assert error is not None
    assert error.code == "profile_not_closed"
    assert error.upstream_feature_id == SKETCH_ID
    assert result.features[2].error is None  # skipped carries no error
    assert result.last_good_feature_id == SKETCH_ID
    assert result.mesh_glb_id is None
    assert result.properties is None


def test_failure_after_body_keeps_last_good_body() -> None:
    """A failure AFTER a successful extrude still ships the last-good body
    (§4.3: 'the viewport always has something honest to show')."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                rectangle_sketch(SKETCH2_ID, close=False),
                extrude_input(EXTRUDE2_ID, SKETCH2_ID, 5.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "error"]
    assert result.last_good_feature_id == SKETCH2_ID  # last ok feature
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(10000.0, abs=EXTRUDE_TOL)
    assert result.mesh_glb_id is not None  # the pre-failure body, honest


# --- add/cut and direction semantics --------------------------------------------------


def test_cut_pocket_removes_material() -> None:
    """add 40x25x10 then cut a 10x10 pocket 4 deep from the sketch plane:
    volume = 10000 - 400 = 9600 (both profiles planar-exact)."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                rectangle_sketch(SKETCH2_ID, 5.0, 5.0, 15.0, 15.0),
                extrude_input(EXTRUDE2_ID, SKETCH2_ID, 4.0, operation="cut"),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 4
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(9600.0, abs=EXTRUDE_TOL)
    # The pocket floor + 4 walls add faces; the bottom face gains a hole:
    # 6 box faces + 5 pocket faces = 11 (cut booleans are clean()ed).
    assert result.properties.topology.faces == 11


def test_direction_reverse_extrudes_along_negative_normal() -> None:
    """direction: reverse on XY → the prism spans z in [-10, 0]."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0, direction="reverse"),
            ]
        )
    )

    assert result.properties is not None
    assert result.properties.bounding_box.min.z == pytest.approx(-10.0, abs=EXTRUDE_TOL)
    assert result.properties.bounding_box.max.z == pytest.approx(0.0, abs=EXTRUDE_TOL)
    assert result.properties.centroid.z == pytest.approx(-5.0, abs=EXTRUDE_TOL)


def test_circle_profile_extrudes_to_cylinder_volume() -> None:
    """A circle entity is a closed profile on its own: V = pi r^2 h."""
    result = _post(
        _request(
            [
                circle_sketch(SKETCH_ID, (20.0, 12.5), 6.0),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        math.pi * 36.0 * 10.0, abs=EXTRUDE_TOL
    )


# --- Error paths are per-feature values, never transport failures ---------------------


def test_cut_with_no_prior_body_is_feature_error() -> None:
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0, operation="cut"),
            ]
        )
    )

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "no_prior_body"
    assert result.mesh_glb_id is None


def test_profile_referencing_non_sketch_is_reference_unresolved() -> None:
    """An extrude profiled on another extrude — documents rejects this at
    write time (§2.2 rule 3); geometry re-checks and pins the upstream id."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                extrude_input(EXTRUDE2_ID, EXTRUDE_ID, 5.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == EXTRUDE_ID


def test_disjoint_add_is_boolean_failed() -> None:
    """Two solids that never touch: a single body chain per part in v1
    (design §7.6) — surfaced as boolean_failed, not a silent compound."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                rectangle_sketch(SKETCH2_ID, 100.0, 0.0, 110.0, 10.0),
                extrude_input(EXTRUDE2_ID, SKETCH2_ID, 5.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "error"]
    error = result.features[3].error
    assert error is not None
    assert error.code == "boolean_failed"


def test_multiple_disjoint_loops_are_profile_unsupported() -> None:
    result = _post(
        _request(
            [
                circle_sketch(SKETCH_ID, (0.0, 0.0), 5.0, count=2),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
            ]
        )
    )

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "profile_unsupported"


def test_points_only_sketch_has_nothing_to_extrude() -> None:
    """Point entities are construction geometry — a points-only profile is
    profile_not_closed, with a message saying nothing is extrudable."""
    sketch = {
        "id": str(SKETCH_ID),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(XY_PLANE),
                "entities": [
                    {"id": "p1", "kind": "point", "position": {"x": 1.0, "y": 2.0}}
                ],
                "constraints": [],
            },
        },
    }
    result = _post(_request([sketch, extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0)]))

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "profile_not_closed"
