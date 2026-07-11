"""Revolve feature — API-level behavior of the second body-affecting feature.

Covers the BACKLOG Ready #5 acceptance criteria beyond the golden harness (the
golden ``revolve-annulus-r10-20-h15`` runs every parametrized gate in
``test_goldens.py`` / ``test_step_roundtrip.py``): the golden tree evaluated
over HTTP populates real mass properties and a fetchable content-addressed
mesh; ``add``/``cut``, partial-angle, and touching-axis semantics are
numerically checked; and every revolve error path — ``profile_not_closed``,
``no_axis``, ``axis_intersects_profile``, ``no_prior_body``,
``reference_unresolved`` — is a per-feature error pinned under the strict-prefix
rule (design §4.3), never a transport failure.

Numeric assertions use the documented tree-golden tolerance (see
``goldens/revolve-annulus-r10-20-h15/expected.json`` — measured-then-set), not
ad-hoc epsilons.
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
    / "revolve-annulus-r10-20-h15"
    / "model.json"
)

#: The documented tolerance of the revolve golden (expected.json
#: tolerance_rationale: measured worst deviation 1.82e-12 mm^3 on volume;
#: 1e-9 is the reviewed ceiling). Every revolve in this suite is the same
#: curved GProp path.
REVOLVE_TOL = 1e-9

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fc")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-00000000aaaa")
REVOLVE_ID = uuid.UUID("00000000-0000-0000-0000-00000000bbbb")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-00000000cccc")

XY_PLANE: dict[str, Any] = {"kind": "datum_plane", "plane": "XY"}


def _line(
    eid: str,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    construction: bool = False,
) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "line",
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
        "construction": construction,
    }


def profile_sketch(
    feature_id: uuid.UUID,
    x0: float,
    x1: float,
    height: float,
    *,
    axis_x: float = 0.0,
    close: bool = True,
    axis_kind: str = "line",
) -> dict[str, Any]:
    """A rectangle profile [x0,x1] x [0,height] plus a construction axis line.

    ``close=False`` drops the closing edge (broken-profile flavour).
    ``axis_kind="point"`` swaps the axis line for a point entity (a bad axis
    reference). ``axis_x`` places the vertical axis line.
    """
    entities: list[dict[str, Any]] = [
        _line("e1", (x0, 0.0), (x1, 0.0)),
        _line("e2", (x1, 0.0), (x1, height)),
        _line("e3", (x1, height), (x0, height)),
    ]
    if close:
        entities.append(_line("e4", (x0, height), (x0, 0.0)))
    if axis_kind == "line":
        entities.append(
            _line("axis", (axis_x, 0.0), (axis_x, height), construction=True)
        )
    else:
        entities.append(
            {
                "id": "axis",
                "kind": "point",
                "construction": True,
                "position": {"x": axis_x, "y": 0.0},
            }
        )
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


def revolve_input(
    feature_id: uuid.UUID,
    profile_id: uuid.UUID,
    *,
    axis_entity: str = "axis",
    angle_deg: float = 360.0,
    operation: str = "add",
    direction: str = "normal",
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "revolve",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile_id)},
                "axis": {"kind": "sketch_line", "entity": axis_entity},
                "angle_deg": angle_deg,
                "operation": operation,
                "direction": direction,
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
    """The committed revolve golden, posted verbatim: both features ok, the
    annulus volume 4500*pi on the wire, content-addressed mesh id."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    result = _post(payload)

    assert [(r.feature_id, r.status) for r in result.features] == [
        (SKETCH_ID, "ok"),
        (REVOLVE_ID, "ok"),
    ]
    assert result.last_good_feature_id == REVOLVE_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(4500.0 * math.pi, abs=REVOLVE_TOL)
    assert result.properties.surface_area == pytest.approx(
        1500.0 * math.pi, abs=REVOLVE_TOL
    )
    assert result.mesh_glb_id is not None
    assert result.mesh_glb_id.startswith("sha256:")


def test_evaluate_response_with_body_is_byte_deterministic() -> None:
    """Same revolve tree → identical response bytes INCLUDING mesh_glb_id
    (a content hash of a deterministic GLB) — RESEARCH §9."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- Valid revolve variants ----------------------------------------------------------


def test_profile_touching_axis_revolves_to_a_solid_disc() -> None:
    """A profile whose inner edge lies ON the axis (x0=0) is valid — it revolves
    into a solid disc, V = pi*r^2*h. Touching the axis is allowed (not a
    self-intersection)."""
    result = _post(
        _request(
            [
                profile_sketch(SKETCH_ID, 0.0, 20.0, 15.0),
                revolve_input(REVOLVE_ID, SKETCH_ID),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        math.pi * 400.0 * 15.0, abs=REVOLVE_TOL
    )


def test_partial_angle_revolves_a_fraction_of_the_full_solid() -> None:
    """A 180 deg revolve of the annulus profile sweeps exactly half the full
    solid: V = 0.5 * pi*(r_o^2 - r_i^2)*h."""
    result = _post(
        _request(
            [
                profile_sketch(SKETCH_ID, 10.0, 20.0, 15.0),
                revolve_input(REVOLVE_ID, SKETCH_ID, angle_deg=180.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        0.5 * math.pi * 300.0 * 15.0, abs=REVOLVE_TOL
    )


def test_revolve_cut_removes_a_revolved_pocket() -> None:
    """Revolve-add a solid disc, then revolve-cut a coaxial inner cylinder:
    the result is the annulus, V = pi*(r_o^2 - r_i^2)*h."""
    result = _post(
        _request(
            [
                profile_sketch(SKETCH_ID, 0.0, 20.0, 15.0),
                revolve_input(REVOLVE_ID, SKETCH_ID),
                profile_sketch(EXTRUDE_ID, 0.0, 10.0, 15.0),
                revolve_input(
                    uuid.UUID("00000000-0000-0000-0000-00000000dddd"),
                    EXTRUDE_ID,
                    operation="cut",
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        math.pi * (400.0 - 100.0) * 15.0, abs=REVOLVE_TOL
    )


# --- Error paths are per-feature values, never transport failures ---------------------


def test_axis_intersecting_profile_is_a_feature_error() -> None:
    """A profile straddling the axis (x in [-5, 5], axis at x=0) would sweep
    material through itself — rejected as axis_intersects_profile, pinned to
    the upstream sketch."""
    result = _post(
        _request(
            [
                profile_sketch(SKETCH_ID, -5.0, 5.0, 15.0),
                revolve_input(REVOLVE_ID, SKETCH_ID),
            ]
        )
    )

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "axis_intersects_profile"
    assert error.upstream_feature_id == SKETCH_ID
    assert result.mesh_glb_id is None


def test_unknown_axis_reference_is_no_axis() -> None:
    """An axis id absent from the sketch → no_axis (bad axis reference)."""
    result = _post(
        _request(
            [
                profile_sketch(SKETCH_ID, 10.0, 20.0, 15.0),
                revolve_input(REVOLVE_ID, SKETCH_ID, axis_entity="nope"),
            ]
        )
    )

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "no_axis"


def test_non_line_axis_reference_is_no_axis() -> None:
    """An axis id that resolves to a POINT entity (not a line) → no_axis."""
    result = _post(
        _request(
            [
                profile_sketch(SKETCH_ID, 10.0, 20.0, 15.0, axis_kind="point"),
                revolve_input(REVOLVE_ID, SKETCH_ID),
            ]
        )
    )

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "no_axis"


def test_open_profile_is_profile_not_closed() -> None:
    """An open profile chain → profile_not_closed pinned to the sketch (shared
    with extrude via the same build_profile_face check)."""
    result = _post(
        _request(
            [
                profile_sketch(SKETCH_ID, 10.0, 20.0, 15.0, close=False),
                revolve_input(REVOLVE_ID, SKETCH_ID),
            ]
        )
    )

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "profile_not_closed"
    assert error.upstream_feature_id == SKETCH_ID


def test_cut_with_no_prior_body_is_feature_error() -> None:
    result = _post(
        _request(
            [
                profile_sketch(SKETCH_ID, 0.0, 20.0, 15.0),
                revolve_input(REVOLVE_ID, SKETCH_ID, operation="cut"),
            ]
        )
    )

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "no_prior_body"
    assert result.mesh_glb_id is None


def test_profile_referencing_non_sketch_is_reference_unresolved() -> None:
    """A revolve profiled on another revolve — geometry re-checks §2.2 and pins
    the upstream id."""
    result = _post(
        _request(
            [
                profile_sketch(SKETCH_ID, 0.0, 20.0, 15.0),
                revolve_input(REVOLVE_ID, SKETCH_ID),
                revolve_input(EXTRUDE_ID, REVOLVE_ID),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == REVOLVE_ID
