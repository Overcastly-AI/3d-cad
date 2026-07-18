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


def _circle(eid: str, center: tuple[float, float], radius: float) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "circle",
        "center": {"x": center[0], "y": center[1]},
        "radius": radius,
    }


def plate_with_holes_sketch(
    feature_id: uuid.UUID,
    holes: list[tuple[tuple[float, float], float]],
    *,
    x0: float = 0.0,
    y0: float = 0.0,
    x1: float = 40.0,
    y1: float = 25.0,
) -> dict[str, Any]:
    """A closed outer rectangle plus inner hole circles in ONE sketch.

    The multi-loop profile: the rectangle is the outer boundary, each circle a
    hole subtracted from the face (build_profile_face classifies by area).
    """
    entities = [
        _line("e1", (x0, y0), (x1, y0)),
        _line("e2", (x1, y0), (x1, y1)),
        _line("e3", (x1, y1), (x0, y1)),
        _line("e4", (x0, y1), (x0, y0)),
    ]
    entities += [
        _circle(f"h{i + 1}", center, radius) for i, (center, radius) in enumerate(holes)
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


def test_disjoint_outer_boundaries_are_profile_unsupported() -> None:
    """Two circles neither of which contains the other are two disjoint outer
    boundaries — a multi-region sketch, unsupported in v1 (a single body is one
    outer boundary with interior holes). Not a hole configuration: the message
    names the disjoint-regions case, and it is a per-feature error, never 500."""
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
    assert "outer boundary" in error.message.lower()


# --- Multi-loop closed profiles: plate with holes (bolt-circle capability) ------------


def test_plate_with_holes_extrudes_with_holes_subtracted() -> None:
    """One sketch of a 40x25 outer rectangle + two r5 holes extrudes to a plate
    with two through-holes: V = (40*25 - 2*pi*25)*10, 8 faces (6 prism + 2 hole
    cylinders). The kernel half of the golden, asserted over HTTP."""
    result = _post(
        _request(
            [
                plate_with_holes_sketch(
                    SKETCH_ID, [((12.0, 12.5), 5.0), ((28.0, 12.5), 5.0)]
                ),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        (40.0 * 25.0 - 2.0 * math.pi * 25.0) * 10.0, abs=EXTRUDE_TOL
    )
    assert result.properties.topology.faces == 8


def test_single_hole_plate_extrudes() -> None:
    """One outer boundary + one hole: the minimal multi-loop profile (a washer
    plate). V = (40*25 - pi*25)*10; 7 faces (6 prism + 1 hole cylinder)."""
    result = _post(
        _request(
            [
                plate_with_holes_sketch(SKETCH_ID, [((20.0, 12.5), 5.0)]),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        (40.0 * 25.0 - math.pi * 25.0) * 10.0, abs=EXTRUDE_TOL
    )
    assert result.properties.topology.faces == 7


def test_cut_with_holed_profile_leaves_material_under_holes() -> None:
    """The holed-profile CUT path is meaningfully different: cutting a block
    with a plate-with-hole profile removes the ring but LEAVES the pillar under
    the hole. add a 40x25x10 block, then cut a full-depth pocket shaped as a
    40x25 outer with a central r5 hole -> only the ring is removed, so the
    remaining volume is exactly the two hole columns' worth: pi*25*10 = the
    material under the single hole for the full 10 mm depth."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                plate_with_holes_sketch(SKETCH2_ID, [((20.0, 12.5), 5.0)]),
                extrude_input(EXTRUDE2_ID, SKETCH2_ID, 10.0, operation="cut"),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 4
    assert result.properties is not None
    # The cut tool is the plate minus its hole; cutting it from the identical
    # block leaves exactly the hole's column: pi*5^2*10.
    assert result.properties.volume == pytest.approx(
        math.pi * 25.0 * 10.0, abs=EXTRUDE_TOL
    )


def test_hole_crossing_outer_boundary_is_profile_unsupported() -> None:
    """A hole poking through the outer boundary is not an interior hole -> a
    legible profile_unsupported, never a 500 (OCCT would build an invalid
    face)."""
    result = _post(
        _request(
            [
                # r10 hole centred near the right edge (x=38) pokes past x=40.
                plate_with_holes_sketch(SKETCH_ID, [((38.0, 12.5), 10.0)]),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
            ]
        )
    )

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "profile_unsupported"


def test_overlapping_holes_are_profile_unsupported() -> None:
    """Two holes that overlap each other are not disjoint interior holes -> a
    legible profile_unsupported (invalid face), never a 500."""
    result = _post(
        _request(
            [
                plate_with_holes_sketch(
                    SKETCH_ID, [((18.0, 12.5), 5.0), ((23.0, 12.5), 5.0)]
                ),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
            ]
        )
    )

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "profile_unsupported"


def test_open_loop_among_closed_loops_is_profile_not_closed() -> None:
    """An open outer boundary (three sides) plus a closed hole circle -> the
    open loop is caught first as profile_not_closed, not profile_unsupported."""
    sketch = plate_with_holes_sketch(SKETCH_ID, [((20.0, 12.5), 5.0)])
    entities = sketch["feature"]["params"]["entities"]
    sketch["feature"]["params"]["entities"] = [
        e for e in entities if e["id"] != "e4"
    ]  # drop the closing edge of the outer rectangle
    result = _post(_request([sketch, extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0)]))

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "profile_not_closed"


def test_plate_with_holes_is_byte_deterministic() -> None:
    """Determinism holds with multi-loop profiles (RESEARCH §9): inner-wire
    ordering is sorted by a geometric key, so the body — and its content-
    addressed mesh id — is byte-reproducible across identical requests."""
    payload = _request(
        [
            plate_with_holes_sketch(
                SKETCH_ID, [((12.0, 12.5), 5.0), ((28.0, 12.5), 5.0)]
            ),
            extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
        ]
    )
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- Multi-disjoint-loop CUT: N independent removal regions (showcase F2) -------------


def test_cut_of_disjoint_loops_removes_each_region_in_one_feature() -> None:
    """A sketch of THREE disjoint circles with no enclosing outer boundary,
    extrude-CUT through a 40x25x10 block, removes all three through-holes in ONE
    feature (BACKLOG #4 / showcase F2). Volume = 10000 - 3*pi*4^2*10; the three
    cylindrical hole walls raise the face count to 6 block + 3 = 9. This is the
    path build_profile_faces unlocks: N disjoint loops -> N cut tools."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                circle_sketch(SKETCH2_ID, (10.0, 12.5), 4.0, count=3),
                extrude_input(EXTRUDE2_ID, SKETCH2_ID, 10.0, operation="cut"),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 4
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        10000.0 - 3.0 * math.pi * 16.0 * 10.0, abs=EXTRUDE_TOL
    )
    # 6 block faces + one cylindrical wall per through-hole; top/bottom stay one
    # face each (now pierced). Cut booleans are clean()ed.
    assert result.properties.topology.faces == 9


def test_add_of_disjoint_loops_stays_multi_body_error_but_cut_succeeds() -> None:
    """The add-vs-cut guard, pinned on the SAME disjoint sketch: an ADD extrude
    of two disjoint loops is a multi-body sketch -> profile_unsupported (Loft
    does NOT support multi-body), while the identical sketch used as a CUT after
    a body succeeds as two independent removal regions. The relaxation is
    CUT-only; the add path is byte-unchanged."""
    disjoint = circle_sketch(SKETCH_ID, (12.0, 12.5), 4.0, count=2)

    add = _post(_request([disjoint, extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0)]))
    assert add.features[1].status == "error"
    assert add.features[1].error is not None
    assert add.features[1].error.code == "profile_unsupported"
    assert "outer boundary" in add.features[1].error.message.lower()

    cut = _post(
        _request(
            [
                rectangle_sketch(SKETCH2_ID),
                extrude_input(EXTRUDE2_ID, SKETCH2_ID, 10.0),
                circle_sketch(SKETCH_ID, (12.0, 12.5), 4.0, count=2),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0, operation="cut"),
            ]
        )
    )
    assert [r.status for r in cut.features] == ["ok"] * 4
    assert cut.properties is not None
    assert cut.properties.volume == pytest.approx(
        10000.0 - 2.0 * math.pi * 16.0 * 10.0, abs=EXTRUDE_TOL
    )


def test_single_outer_multiloop_cut_is_unchanged_by_the_relaxation() -> None:
    """Regression guard: a single-outer-boundary + inner-hole profile CUT still
    resolves to ONE region (build_profile_faces returns a one-element list), so
    the plate-with-hole cut leaves the pillar under the hole exactly as before
    the multi-region path existed — pi*5^2*10, unchanged from
    test_cut_with_holed_profile_leaves_material_under_holes."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                plate_with_holes_sketch(SKETCH2_ID, [((20.0, 12.5), 5.0)]),
                extrude_input(EXTRUDE2_ID, SKETCH2_ID, 10.0, operation="cut"),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 4
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        math.pi * 25.0 * 10.0, abs=EXTRUDE_TOL
    )


def test_cut_with_loop_nested_two_deep_is_profile_unsupported() -> None:
    """Three concentric circles (r15 > r10 > r5) put the innermost loop TWO
    levels deep — a hole inside a hole. The CUT multi-region partition supports
    disjoint regions of one outer boundary + interior holes, not deeper nesting,
    so this is a legible profile_unsupported, never a 500."""
    nested = circle_sketch(SKETCH2_ID, (20.0, 12.5), 15.0)
    nested["feature"]["params"]["entities"] += [
        _circle("m", (20.0, 12.5), 10.0),
        _circle("i", (20.0, 12.5), 5.0),
    ]
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID, 0.0, 0.0, 40.0, 25.0),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                nested,
                extrude_input(EXTRUDE2_ID, SKETCH2_ID, 10.0, operation="cut"),
            ]
        )
    )

    assert result.features[3].status == "error"
    error = result.features[3].error
    assert error is not None
    assert error.code == "profile_unsupported"


def test_disjoint_cut_is_byte_deterministic() -> None:
    """Determinism holds with N disjoint cut regions (RESEARCH §9): _group_regions
    orders the regions by a geometric key, so the multi-cut body — and its
    content-addressed mesh id — is byte-reproducible across identical requests."""
    payload = _request(
        [
            rectangle_sketch(SKETCH_ID),
            extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
            circle_sketch(SKETCH2_ID, (10.0, 12.5), 4.0, count=3),
            extrude_input(EXTRUDE2_ID, SKETCH2_ID, 10.0, operation="cut"),
        ]
    )
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


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


# --- Construction geometry: reference-only, excluded from the profile (BACKLOG #2) ----


def rectangle_with_construction_diagonal(feature_id: uuid.UUID) -> dict[str, Any]:
    """A closed 40x25 rectangle plus a construction diagonal corner-to-corner.

    The diagonal participates in the solve (constrainable/referenceable) but
    must be EXCLUDED from the profile — the rectangle's four real edges are the
    extruded loop, exactly as if the diagonal were not there.
    """
    sketch = rectangle_sketch(feature_id)
    diagonal = {**_line("d1", (0.0, 0.0), (40.0, 25.0)), "construction": True}
    sketch["feature"]["params"]["entities"].append(diagonal)
    return sketch


def test_construction_geometry_is_excluded_from_the_profile() -> None:
    """A closed rectangle + a construction diagonal extrudes to the rectangle
    prism: the diagonal is reference-only and ignored (V = 40*25*10 = 10000,
    the same body as the rectangle alone)."""
    result = _post(
        _request(
            [
                rectangle_with_construction_diagonal(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(10000.0, abs=EXTRUDE_TOL)
    assert result.properties.surface_area == pytest.approx(3300.0, abs=EXTRUDE_TOL)
    # A plain 6-face prism: the diagonal never became a face/edge of the solid.
    assert result.properties.topology.faces == 6
    # The construction entity still rides the solved-sketch payload (§7.10) so
    # the sketcher can render it dashed — reference geometry, not deletion.
    solved = result.features[0].data
    assert solved is not None
    assert {e.id: e.construction for e in solved.entities} == {
        "e1": False,
        "e2": False,
        "e3": False,
        "e4": False,
        "d1": True,
    }


def test_construction_edge_opens_the_profile() -> None:
    """Marking a REAL profile edge construction opens the loop → the profile
    check fails ``profile_not_closed``. Correct CAD semantics, not a bug."""
    sketch = rectangle_sketch(SKETCH_ID)
    for entity in sketch["feature"]["params"]["entities"]:
        if entity["id"] == "e4":  # the closing edge
            entity["construction"] = True
    result = _post(_request([sketch, extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0)]))

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "profile_not_closed"
    assert error.upstream_feature_id == SKETCH_ID


def test_construction_geometry_extrude_is_byte_deterministic() -> None:
    """Determinism holds with construction geometry in the tree (RESEARCH §9):
    the filter preserves input order, so the body — and its content-addressed
    mesh id — is byte-reproducible."""
    payload = _request(
        [
            rectangle_with_construction_diagonal(SKETCH_ID),
            extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
        ]
    )
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


def test_only_construction_geometry_has_nothing_to_extrude() -> None:
    """A sketch of construction curves only is profile_not_closed — the same
    empty-profile outcome as a points-only sketch (nothing bounds a solid)."""
    sketch = rectangle_sketch(SKETCH_ID)
    for entity in sketch["feature"]["params"]["entities"]:
        entity["construction"] = True
    result = _post(_request([sketch, extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0)]))

    assert result.features[1].status == "error"
    error = result.features[1].error
    assert error is not None
    assert error.code == "profile_not_closed"
