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


def half_profile_sketch(
    feature_id: uuid.UUID,
    radius: float,
    height: float,
    *,
    axis_gap: float = 0.0,
) -> dict[str, Any]:
    """A HALF-profile OPEN along the axis + a construction centerline on it.

    Three REAL edges of a rectangle r in [0, radius], y in [0, height] — the
    on-axis (x=0) edge is OMITTED — plus a ``construction`` centerline 'axis'
    along x=0 that closes the loop. This is the SolidWorks/Fusion idiom: marking
    the on-axis edge construction opens the profile wire, and the revolve closes
    it about the centerline.

    ``axis_gap > 0`` shifts the whole real profile to x in [axis_gap, radius],
    leaving it open along x=axis_gap (NOT the axis) — a genuinely open profile
    the centerline cannot close (over-acceptance guard).
    """
    x0 = axis_gap
    entities: list[dict[str, Any]] = [
        _line("e1", (x0, 0.0), (radius, 0.0)),
        _line("e2", (radius, 0.0), (radius, height)),
        _line("e3", (radius, height), (x0, height)),
        _line("axis", (0.0, height), (0.0, 0.0), construction=True),
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


# --- Construction-centerline axis closes a half-profile (BACKLOG P2) ------------------


def test_construction_centerline_closes_open_half_profile() -> None:
    """The SolidWorks/Fusion idiom: a half-profile OPEN along the axis (its
    on-axis edge is a construction centerline, excluded from the wire) revolves
    360 deg about that centerline into a solid cylinder, V = pi*r^2*h — the
    centerline closes the open profile (was 422 profile_not_closed before)."""
    result = _post(
        _request(
            [
                half_profile_sketch(SKETCH_ID, 12.0, 20.0),
                revolve_input(REVOLVE_ID, SKETCH_ID),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        math.pi * 144.0 * 20.0, abs=REVOLVE_TOL
    )


def test_construction_centerline_partial_angle() -> None:
    """A 90 deg revolve of the same open half-profile about its construction
    centerline sweeps a quarter of the full solid: V = 0.25 * pi*r^2*h."""
    result = _post(
        _request(
            [
                half_profile_sketch(SKETCH_ID, 12.0, 20.0),
                revolve_input(REVOLVE_ID, SKETCH_ID, angle_deg=90.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        0.25 * math.pi * 144.0 * 20.0, abs=REVOLVE_TOL
    )


def test_profile_open_away_from_axis_still_profile_not_closed() -> None:
    """Over-acceptance guard: a profile open along x=5 (NOT the axis) is a
    GENUINELY open profile — the construction centerline at x=0 cannot close it,
    so it stays profile_not_closed (the fallback supplies only the axis edge)."""
    result = _post(
        _request(
            [
                half_profile_sketch(SKETCH_ID, 12.0, 20.0, axis_gap=5.0),
                revolve_input(REVOLVE_ID, SKETCH_ID),
            ]
        )
    )

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "profile_not_closed"
    assert error.upstream_feature_id == SKETCH_ID


# --- Adversarial centerline-closure guards (geometry-qa, 1605a11) ---------------------
#
# The construction-centerline retry (build_revolve_profile_face) promotes ONLY the
# axis line to a closing edge. These guards pin the boundary between "the axis
# legitimately closes a half-profile open exactly along it" and every neighbouring
# case that must instead error — a silently-bridged WRONG solid is the failure the
# green-suite/wrong-volume bar exists to catch. Analytic values are hand-derived.


def _custom_sketch(
    feature_id: uuid.UUID, entities: list[dict[str, Any]]
) -> dict[str, Any]:
    """A sketch feature from an explicit entity list (bespoke geometries)."""
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


def test_axis_shorter_than_open_span_is_profile_not_closed() -> None:
    """Silent-bridge guard: the half-profile is open along x=0 for y in [0,20],
    but the construction centerline only spans y in [0,10]. Promoting that short
    axis edge leaves the profile's (0,20) endpoint dangling (a 10 mm gap, far
    beyond the 1e-4 wire tolerance), so it MUST stay profile_not_closed — the
    retry cannot bridge an axis that fails to reach both open endpoints."""
    result = _post(
        _request(
            [
                _custom_sketch(
                    SKETCH_ID,
                    [
                        _line("e1", (0.0, 0.0), (12.0, 0.0)),
                        _line("e2", (12.0, 0.0), (12.0, 20.0)),
                        _line("e3", (12.0, 20.0), (0.0, 20.0)),
                        _line("axis", (0.0, 0.0), (0.0, 10.0), construction=True),
                    ],
                ),
                revolve_input(REVOLVE_ID, SKETCH_ID),
            ]
        )
    )

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "profile_not_closed"
    assert error.upstream_feature_id == SKETCH_ID
    assert result.mesh_glb_id is None


def test_profile_open_at_axis_and_elsewhere_is_profile_not_closed() -> None:
    """Partial-close guard: a profile open BOTH along the axis (missing left
    edge) AND at the top (missing top edge). The centerline can supply only the
    axis edge, so the top stays open — profile_not_closed, never a partially
    closed / wrong solid."""
    result = _post(
        _request(
            [
                _custom_sketch(
                    SKETCH_ID,
                    [
                        _line("e1", (0.0, 0.0), (12.0, 0.0)),
                        _line("e2", (12.0, 0.0), (12.0, 20.0)),
                        # top edge (12,20)->(0,20) omitted: open at the top too
                        _line("axis", (0.0, 0.0), (0.0, 20.0), construction=True),
                    ],
                ),
                revolve_input(REVOLVE_ID, SKETCH_ID),
            ]
        )
    )

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "profile_not_closed"
    assert result.mesh_glb_id is None


def test_real_on_axis_edge_and_centerline_close_yield_identical_body() -> None:
    """Anti-double-count / seam guard (design intent: the fallback closes exactly
    the face a real on-axis edge would give). A rectangle [0,12]x[0,20] closed by
    a REAL on-axis edge, and the same rectangle left OPEN and closed by a
    construction centerline of the SAME direction, must produce the SAME disc:
    identical volume AND byte-identical mesh (content-addressed GLB) — no seam,
    no doubled edge. Axis line (0,0)->(0,20) is shared so the revolution axis
    direction (hence seam placement) is identical between the two."""
    axis_edge = _line("axis", (0.0, 0.0), (0.0, 20.0), construction=True)
    real_closed = _custom_sketch(
        SKETCH_ID,
        [
            _line("e1", (0.0, 0.0), (12.0, 0.0)),
            _line("e2", (12.0, 0.0), (12.0, 20.0)),
            _line("e3", (12.0, 20.0), (0.0, 20.0)),
            _line("e4", (0.0, 20.0), (0.0, 0.0)),  # REAL on-axis closing edge
            axis_edge,
        ],
    )
    open_centerline = _custom_sketch(
        SKETCH_ID,
        [
            _line("e1", (0.0, 0.0), (12.0, 0.0)),
            _line("e2", (12.0, 0.0), (12.0, 20.0)),
            _line("e3", (12.0, 20.0), (0.0, 20.0)),
            axis_edge,  # closes the open wire via the retry
        ],
    )

    revolve = revolve_input(REVOLVE_ID, SKETCH_ID)
    result_real = _post(_request([real_closed, revolve]))
    result_open = _post(_request([open_centerline, revolve]))

    for result in (result_real, result_open):
        assert [r.status for r in result.features] == ["ok", "ok"]
        assert result.properties is not None
        assert result.properties.volume == pytest.approx(
            math.pi * 144.0 * 20.0, abs=REVOLVE_TOL
        )
    # Byte-identical body: same GLB content hash proves no doubled edge / extra seam.
    assert result_real.mesh_glb_id is not None
    assert result_real.mesh_glb_id == result_open.mesh_glb_id


def test_tilted_construction_centerline_revolves_about_the_tilted_axis() -> None:
    """A non-axis-aligned construction centerline (the 45 deg line y=x through the
    origin) is a valid axis: a closed square [3,5]x[0,1] strictly on one side
    revolves into the correct solid of revolution about that tilted line. Pappus:
    V = 2*pi*d*A, d = perpendicular distance of the centroid (4, 0.5) to y=x =
    |4-0.5|/sqrt(2), A = 2. The kernel is not restricted to principal axes."""
    centroid_distance = abs(4.0 - 0.5) / math.sqrt(2.0)
    expected = 2.0 * math.pi * centroid_distance * 2.0
    result = _post(
        _request(
            [
                _custom_sketch(
                    SKETCH_ID,
                    [
                        _line("e1", (3.0, 0.0), (5.0, 0.0)),
                        _line("e2", (5.0, 0.0), (5.0, 1.0)),
                        _line("e3", (5.0, 1.0), (3.0, 1.0)),
                        _line("e4", (3.0, 1.0), (3.0, 0.0)),
                        _line("axis", (0.0, 0.0), (10.0, 10.0), construction=True),
                    ],
                ),
                revolve_input(REVOLVE_ID, SKETCH_ID),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(expected, abs=REVOLVE_TOL)


def test_straddling_profile_closable_by_centerline_still_axis_intersects() -> None:
    """Ordering guard (the fix builds the face BEFORE the clearance check): an
    OPEN profile whose two ends both sit on the axis but whose body crosses to
    both sides of it (x in [-6,6]) — so the centerline CAN close it into a face —
    must still be rejected as axis_intersects_profile, never a self-intersecting
    swept solid. Build-then-check must not let a closable straddle through."""
    result = _post(
        _request(
            [
                _custom_sketch(
                    SKETCH_ID,
                    [
                        _line("e1", (0.0, 0.0), (-6.0, 10.0)),
                        _line("e2", (-6.0, 10.0), (6.0, 10.0)),  # crosses x=0
                        _line("e3", (6.0, 10.0), (0.0, 20.0)),
                        _line("axis", (0.0, 0.0), (0.0, 20.0), construction=True),
                    ],
                ),
                revolve_input(REVOLVE_ID, SKETCH_ID),
            ]
        )
    )

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "axis_intersects_profile"
    assert result.mesh_glb_id is None


def test_construction_centerline_partial_angle_120_is_exact_third() -> None:
    """A 120 deg revolve of the open half-profile about its centerline sweeps
    exactly one third of the full solid: V = (120/360) * pi*r^2*h (an exact,
    non-quarter fraction — complements the 90 deg guard)."""
    result = _post(
        _request(
            [
                half_profile_sketch(SKETCH_ID, 12.0, 20.0),
                revolve_input(REVOLVE_ID, SKETCH_ID, angle_deg=120.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        (120.0 / 360.0) * math.pi * 144.0 * 20.0, abs=REVOLVE_TOL
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
