"""Loft feature — API-level behavior of the second non-prismatic feature.

Covers the BACKLOG #8 acceptance criteria beyond the golden harness (the golden
``loft-pyramid-sq20-h30`` runs every parametrized gate in ``test_goldens.py`` /
``test_step_roundtrip.py``): the golden tree evaluated over HTTP populates real
mass properties and a fetchable content-addressed mesh; ``add``/``cut``, a
three-section loft, and the loft-to-apex capability are numerically checked; and
every loft error path — ``profile_not_closed``, ``reference_unresolved`` (bad
section ref OR non-sketch ref), ``loft_failed`` (an apex wedged between two wire
sections), ``no_prior_body`` — is a per-feature error pinned under the
strict-prefix rule (design §4.3), never a transport failure. A <2-section loft
is a request-validation 422 (``LoftParamsV1.min_length=2``), also never a 500.

Numeric assertions use the documented tree-golden tolerance (see
``goldens/loft-pyramid-sq20-h30/expected.json`` — measured-then-set), not ad-hoc
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
    / "loft-pyramid-sq20-h30"
    / "model.json"
)

#: The documented tolerance of the loft golden (expected.json: AABB-padding
#: limited, measured worst 1.0e-7; 2e-7 is the reviewed ceiling = 2x the kernel
#: linear tolerance). Every loft in this suite is the same ThruSections path.
LOFT_TOL = 2e-7

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fc")
BASE_ID = uuid.UUID("00000000-0000-0000-0000-0000000b0001")
APEX_ID = uuid.UUID("00000000-0000-0000-0000-0000000b0002")
LOFT_ID = uuid.UUID("00000000-0000-0000-0000-0000000b0003")
EXTRA_ID = uuid.UUID("00000000-0000-0000-0000-0000000b0004")
LOFT2_ID = uuid.UUID("00000000-0000-0000-0000-0000000b0005")


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


def _line(
    eid: str, start: tuple[float, float], end: tuple[float, float]
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
    }


def square_sketch(
    feature_id: uuid.UUID = BASE_ID, plane: str = "XY", half: float = 10.0
) -> dict[str, Any]:
    """A closed axis-aligned square, side 2*half, centred at the sketch origin."""
    corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
    entities = [_line(f"l{i + 1}", corners[i], corners[(i + 1) % 4]) for i in range(4)]
    constraints = [
        {
            "kind": "coincident",
            "a": {"entity": f"l{i + 1}", "point": "end"},
            "b": {"entity": f"l{(i + 1) % 4 + 1}", "point": "start"},
        }
        for i in range(4)
    ]
    return _sketch(feature_id, plane, entities, constraints)


def apex_sketch(
    feature_id: uuid.UUID = APEX_ID, plane: str = "XZ", height: float = 30.0
) -> dict[str, Any]:
    """A single fixed sketch point — the loft apex (on XZ -> world (0,0,height))."""
    return _sketch(
        feature_id,
        plane,
        [{"id": "a1", "kind": "point", "position": {"x": 0.0, "y": height}}],
        [{"kind": "fixed", "point": {"entity": "a1", "point": "position"}}],
    )


def loft_input(
    feature_id: uuid.UUID = LOFT_ID,
    *,
    profiles: list[uuid.UUID] | None = None,
    operation: str = "add",
) -> dict[str, Any]:
    ids = profiles if profiles is not None else [BASE_ID, APEX_ID]
    return {
        "id": str(feature_id),
        "feature": {
            "type": "loft",
            "version": 1,
            "params": {
                "profiles": [
                    {"kind": "feature", "feature_id": str(pid)} for pid in ids
                ],
                "operation": operation,
            },
        },
    }


def _request(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"part_id": str(PART_ID), "tree_version": 2, "features": features}


def _post(payload: dict[str, Any]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200
    return EvaluateTreeResult.model_validate(response.json())


# --- The golden tree over HTTP -------------------------------------------------------


def test_golden_tree_evaluates_with_body_artifact_over_http() -> None:
    """The committed loft golden, posted verbatim: all three features ok, the
    pyramid volume a^2*h/3 on the wire, content-addressed mesh id."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    result = _post(payload)

    assert [(r.feature_id, r.status) for r in result.features] == [
        (BASE_ID, "ok"),
        (APEX_ID, "ok"),
        (LOFT_ID, "ok"),
    ]
    assert result.last_good_feature_id == LOFT_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        20.0 * 20.0 * 30.0 / 3.0, abs=LOFT_TOL
    )
    assert result.properties.surface_area == pytest.approx(
        400.0 + 40.0 * math.sqrt(1000.0), abs=LOFT_TOL
    )
    assert result.mesh_glb_id is not None
    assert result.mesh_glb_id.startswith("sha256:")


def test_evaluate_response_with_body_is_byte_deterministic() -> None:
    """Same loft tree → identical response bytes INCLUDING mesh_glb_id
    (a content hash of a deterministic GLB) — RESEARCH §9."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- Valid loft variants -------------------------------------------------------------


def test_two_wire_sections_loft_a_valid_solid() -> None:
    """Two closed square sections on PERPENDICULAR datum planes loft into ONE
    connected solid — the wire-to-wire (no apex) capability. Volume is not a
    clean closed form (perpendicular sections), so only positivity + a single
    body are asserted here; the analytic lock lives in the golden."""
    base = square_sketch(BASE_ID, plane="XY", half=10.0)
    # A second square on XZ, offset up the +Z axis via its sketch y-centre.
    top = _sketch(
        EXTRA_ID,
        "XZ",
        [
            _line("m1", (-6.0, 24.0), (6.0, 24.0)),
            _line("m2", (6.0, 24.0), (6.0, 36.0)),
            _line("m3", (6.0, 36.0), (-6.0, 36.0)),
            _line("m4", (-6.0, 36.0), (-6.0, 24.0)),
        ],
        [
            {
                "kind": "coincident",
                "a": {"entity": f"m{i + 1}", "point": "end"},
                "b": {"entity": f"m{(i + 1) % 4 + 1}", "point": "start"},
            }
            for i in range(4)
        ],
    )
    result = _post(_request([base, top, loft_input(profiles=[BASE_ID, EXTRA_ID])]))

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume > 0.0
    assert result.properties.topology.shells == 1


def test_three_section_loft_blends_through_all_sections() -> None:
    """A THREE-section loft (square base → mid square → apex) blends through
    every section in list order into one solid — the >2-section capability."""
    base = square_sketch(BASE_ID, plane="XY", half=10.0)
    mid = _sketch(
        EXTRA_ID,
        "XZ",
        [
            _line("m1", (-4.0, 14.0), (4.0, 14.0)),
            _line("m2", (4.0, 14.0), (4.0, 22.0)),
            _line("m3", (4.0, 22.0), (-4.0, 22.0)),
            _line("m4", (-4.0, 22.0), (-4.0, 14.0)),
        ],
        [
            {
                "kind": "coincident",
                "a": {"entity": f"m{i + 1}", "point": "end"},
                "b": {"entity": f"m{(i + 1) % 4 + 1}", "point": "start"},
            }
            for i in range(4)
        ],
    )
    apex = apex_sketch(APEX_ID, height=40.0)
    result = _post(
        _request([base, mid, apex, loft_input(profiles=[BASE_ID, EXTRA_ID, APEX_ID])])
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume > 0.0


def test_loft_cut_removes_material() -> None:
    """Loft-add a pyramid, then loft-cut a smaller apex pyramid coincident with
    it: the cut is a per-feature ok that reduces the body volume."""
    result = _post(
        _request(
            [
                square_sketch(BASE_ID, plane="XY", half=10.0),
                apex_sketch(APEX_ID, height=30.0),
                loft_input(LOFT_ID),
                square_sketch(EXTRA_ID, plane="XY", half=5.0),
                loft_input(LOFT2_ID, profiles=[EXTRA_ID, APEX_ID], operation="cut"),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok", "ok"]
    assert result.properties is not None
    # Outer pyramid 4000 minus a smaller apex pyramid it fully contains.
    assert 0.0 < result.properties.volume < 20.0 * 20.0 * 30.0 / 3.0


# --- Error paths are per-feature values, never transport failures ---------------------


def test_open_section_is_profile_not_closed() -> None:
    """An open section chain → profile_not_closed pinned to that section sketch
    (shared with extrude/revolve/sweep via the same build_profile_face check)."""
    open_base = _sketch(
        BASE_ID,
        "XY",
        [
            _line("l1", (-10.0, -10.0), (10.0, -10.0)),
            _line("l2", (10.0, -10.0), (10.0, 10.0)),
        ],
    )
    result = _post(_request([open_base, apex_sketch(), loft_input()]))

    assert result.features[2].status == "error"
    error = result.features[2].error
    assert error is not None
    assert error.code == "profile_not_closed"
    assert error.upstream_feature_id == BASE_ID


def test_unknown_section_reference_is_reference_unresolved() -> None:
    """A section FeatureRef to a feature that is not an ok sketch of this prefix
    → reference_unresolved pinned to the missing section id."""
    result = _post(
        _request(
            [square_sketch(), apex_sketch(), loft_input(profiles=[BASE_ID, EXTRA_ID])]
        )
    )

    assert result.features[2].status == "error"
    error = result.features[2].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == EXTRA_ID


def test_section_referencing_non_sketch_is_reference_unresolved() -> None:
    """A section that points at the loft's own body-producing feature (not a
    sketch) → reference_unresolved (geometry re-checks §2.2)."""
    result = _post(
        _request(
            [
                square_sketch(BASE_ID),
                apex_sketch(APEX_ID),
                loft_input(LOFT_ID),
                # A second loft whose section points at the first loft feature.
                loft_input(EXTRA_ID, profiles=[BASE_ID, LOFT_ID]),
            ]
        )
    )

    assert result.features[3].status == "error"
    error = result.features[3].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == LOFT_ID


def test_apex_between_wire_sections_is_loft_failed() -> None:
    """An apex point wedged BETWEEN two wire sections is not a valid loft (OCCT
    allows a vertex only at an end) → loft_failed."""
    base = square_sketch(BASE_ID, plane="XY", half=10.0)
    apex = apex_sketch(APEX_ID, plane="XZ", height=15.0)
    top = square_sketch(EXTRA_ID, plane="XY", half=6.0)
    # Order: wire, apex, wire → apex is interior.
    result = _post(
        _request([base, apex, top, loft_input(profiles=[BASE_ID, APEX_ID, EXTRA_ID])])
    )

    assert result.features[3].status == "error"
    error = result.features[3].error
    assert error is not None
    assert error.code == "loft_failed"


def test_cut_with_no_prior_body_is_feature_error() -> None:
    """A loft-cut with nothing to cut → no_prior_body (no body-affecting
    feature precedes it)."""
    result = _post(
        _request([square_sketch(), apex_sketch(), loft_input(operation="cut")])
    )

    assert result.features[2].status == "error"
    error = result.features[2].error
    assert error is not None
    assert error.code == "no_prior_body"
    assert result.mesh_glb_id is None


def test_fewer_than_two_sections_is_request_validation_error() -> None:
    """A single-section loft is rejected by LoftParamsV1.min_length=2 at request
    validation (a clean 422 envelope, never a 500)."""
    payload = _request([square_sketch(), loft_input(profiles=[BASE_ID])])
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 422
