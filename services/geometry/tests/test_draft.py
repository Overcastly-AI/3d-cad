"""Draft feature — API-level behavior of the taper-picked-faces feature.

Covers the draft acceptance criteria beyond the golden harness (the golden
``draft-frustum-box-40x40x20-5deg`` runs every parametrized gate in
``test_goldens.py`` / ``test_step_roundtrip.py``): the golden tree evaluated
over HTTP populates the analytic frustum mass properties and a fetchable
content-addressed mesh; the picked faces resolve through the SAME stage-1
planar-face signature shell / the ``on_face`` datum use; and every draft error
path — ``no_prior_body``, ``subshape_unresolved``, ``no_draft_faces``,
``draft_failed`` — is a per-feature error under the strict-prefix rule (§4.3),
never a transport failure.

Numeric assertions use the documented golden tolerance (see
``goldens/draft-frustum-box-40x40x20-5deg/expected.json`` — measured-then-set),
not ad-hoc epsilons.
"""

import json
import math
import uuid
from pathlib import Path
from typing import Any

import pytest
from build123d import CenterOf, Plane, Solid
from fastapi.testclient import TestClient
from geometry.kernel import DraftError, draft_body, resolve_faces
from geometry.kernel.faces import planar_face_signature
from geometry.main import app
from py_kit.schemas.features import EvaluateTreeResult, PlanarFaceSignature
from py_kit.schemas.geometry import Vec3

client = TestClient(app)

GOLDEN_MODEL = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "draft-frustum-box-40x40x20-5deg"
    / "model.json"
)

#: The documented draft-golden tolerance (expected.json tolerance_rationale:
#: slanted-planar geometry, measured worst deviation 7.3e-12; 1e-9 ceiling).
DRAFT_TOL = 1e-9

#: Analytic frustum figures (full derivation in the golden expected.json):
#: 40x40x20 box, all 4 sides drafted inward 5 deg about the XY base -> frustum.
DRAFT_VOLUME = 29282.008273789652
DRAFT_AREA = 6003.990013236674
DRAFT_CENTROID_Z = 9.695243014314576

#: Fixed ids so requests — and therefore responses — are byte-reproducible.
#: The sketch/extrude/draft ids MATCH the golden model.json (posted verbatim).
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d5")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000d5001")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-0000000d5002")
DRAFT_ID = uuid.UUID("00000000-0000-0000-0000-0000000d5003")
TAIL_ID = uuid.UUID("00000000-0000-0000-0000-00000000d5d5")

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


def square_sketch(feature_id: uuid.UUID) -> dict[str, Any]:
    """A closed 40x40 square profile (entities already at position)."""
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(XY_PLANE),
                "entities": [
                    _line("e1", (0.0, 0.0), (40.0, 0.0)),
                    _line("e2", (40.0, 0.0), (40.0, 40.0)),
                    _line("e3", (40.0, 40.0), (0.0, 40.0)),
                    _line("e4", (0.0, 40.0), (0.0, 0.0)),
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


def _face_ref(
    feature_id: uuid.UUID,
    normal: tuple[float, float, float],
    centroid: tuple[float, float, float],
    area_mm2: float,
) -> dict[str, Any]:
    """A stage-1 face SubshapeRef naming ONE planar face by its signature — the
    SAME shape shell / the on_face datum use (topo-naming §4)."""
    return {
        "kind": "subshape",
        "feature_id": str(feature_id),
        "subshape_type": "face",
        "selector": {
            "selector_version": 1,
            "signature": {
                "subshape_type": "face",
                "surface": "plane",
                "normal": {"x": normal[0], "y": normal[1], "z": normal[2]},
                "centroid": {"x": centroid[0], "y": centroid[1], "z": centroid[2]},
                "area_mm2": area_mm2,
            },
        },
    }


#: The four side-face signatures of the 40x40x20 extruded box (area 800 each).
SIDE_FACES = [
    ((1.0, 0.0, 0.0), (40.0, 20.0, 10.0), 800.0),
    ((-1.0, 0.0, 0.0), (0.0, 20.0, 10.0), 800.0),
    ((0.0, 1.0, 0.0), (20.0, 40.0, 10.0), 800.0),
    ((0.0, -1.0, 0.0), (20.0, 0.0, 10.0), 800.0),
]


def draft_input(
    feature_id: uuid.UUID,
    angle_deg: float,
    refs: list[dict[str, Any]],
    *,
    base: str = "XY",
    offset_mm: float = 0.0,
    flip: bool = False,
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "draft",
            "version": 1,
            "params": {
                "angle_deg": angle_deg,
                "neutral_plane": {
                    "kind": "datum",
                    "base": base,
                    "offset_mm": offset_mm,
                    "flip": flip,
                },
                "faces": {"kind": "faces", "refs": refs},
            },
        },
    }


def _all_side_refs() -> list[dict[str, Any]]:
    return [_face_ref(EXTRUDE_ID, *sig) for sig in SIDE_FACES]


def _request(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"part_id": str(PART_ID), "tree_version": 6, "features": features}


def _post(payload: dict[str, Any]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200
    return EvaluateTreeResult.model_validate(response.json())


# --- The golden tree over HTTP -------------------------------------------------------


def test_golden_draft_tree_evaluates_over_http() -> None:
    """The committed golden model, posted verbatim: all three features ok, the
    analytic frustum volume/area on the wire, a content-addressed mesh id, and
    the box-like frustum topology (6/12/1)."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    result = _post(payload)

    assert [(r.feature_id, r.status) for r in result.features] == [
        (SKETCH_ID, "ok"),
        (EXTRUDE_ID, "ok"),
        (DRAFT_ID, "ok"),
    ]
    assert result.last_good_feature_id == DRAFT_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(DRAFT_VOLUME, abs=DRAFT_TOL)
    assert result.properties.surface_area == pytest.approx(DRAFT_AREA, abs=DRAFT_TOL)
    assert result.properties.centroid.z == pytest.approx(
        DRAFT_CENTROID_Z, abs=DRAFT_TOL
    )
    assert result.properties.topology.faces == 6
    assert result.properties.topology.edges == 12
    assert result.properties.topology.shells == 1
    # base 40x40 unchanged (on the neutral plane); envelope untouched.
    assert result.properties.bounding_box.max.x == pytest.approx(40.0, abs=DRAFT_TOL)
    assert result.mesh_glb_id is not None
    assert result.mesh_glb_id.startswith("sha256:")
    assert result.features[2].data is None  # body-affecting, not a sketch payload


def test_evaluate_response_with_draft_is_byte_deterministic() -> None:
    """Same tree → identical response bytes incl. mesh_glb_id (a content hash of
    a deterministic GLB) — RESEARCH §9 for the draft path (the four FACE refs
    resolve identically each rebuild)."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


def test_negative_angle_tapers_outward() -> None:
    """SIGN convention: a NEGATIVE angle tapers the far (pull-normal) end OUTWARD,
    so the drafted body's volume EXCEEDS the base box (the opposite mold half) —
    the mirror of the golden's positive inward taper."""
    result = _post(
        _request(
            [
                square_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 20.0),
                draft_input(DRAFT_ID, -5.0, _all_side_refs()),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    # outward taper widens the top -> volume above the 32000 base box.
    assert result.properties.volume > 32000.0
    # the top now overhangs the base, so the x-extent exceeds 40.
    assert result.properties.bounding_box.max.x > 40.0


# --- Error paths are per-feature values, never transport failures --------------------


def test_draft_with_no_prior_body_is_no_prior_body() -> None:
    """Draft modifies the single body chain (§7.6): a sketch-only prefix →
    ``no_prior_body``, downstream skipped."""
    result = _post(
        _request(
            [
                square_sketch(SKETCH_ID),
                draft_input(DRAFT_ID, 5.0, _all_side_refs()),
                square_sketch(TAIL_ID),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "error", "skipped"]
    error = result.features[1].error
    assert error is not None
    assert error.code == "no_prior_body"
    assert result.mesh_glb_id is None
    assert result.properties is None


def test_empty_faces_is_no_draft_faces() -> None:
    """Unlike shell (empty = sealed hollow), a draft with NO faces has nothing to
    taper → ``no_draft_faces`` (never a silent no-op), pinned to the feature,
    last-good is the un-drafted extrude."""
    result = _post(
        _request(
            [
                square_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 20.0),
                draft_input(DRAFT_ID, 5.0, []),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "no_draft_faces"
    assert result.last_good_feature_id == EXTRUDE_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(32000.0, abs=DRAFT_TOL)


def test_picked_face_that_no_longer_exists_is_subshape_unresolved() -> None:
    """A picked face signature that matches no current face is an honest
    per-feature ``subshape_unresolved`` (topo-naming §5), never a 500 and never a
    silent wrong-face retarget.

    The fixture has to state a face that is GENUINELY absent, and since tier 3 (QA-2)
    and tier 4 (M17, §12a) that is a higher bar than it looks: the offset along the
    normal is free, and so is the in-plane station within the face's outer boundary.
    A +X plane pushed out to x=999 with the RIGHT area is therefore the same face,
    re-anchored, and resolves — correctly. The area is what makes this one absent:
    this box's +X face is 800 mm² of solid plane with nothing cut into it, so no
    interior edit can produce a 300 mm² face there, at any offset."""
    result = _post(
        _request(
            [
                square_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 20.0),
                draft_input(
                    DRAFT_ID,
                    5.0,
                    [_face_ref(EXTRUDE_ID, (1.0, 0.0, 0.0), (999.0, 20.0, 0.0), 300.0)],
                ),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "subshape_unresolved"
    assert result.last_good_feature_id == EXTRUDE_ID


def test_angle_that_collapses_the_faces_is_draft_failed() -> None:
    """An angle too large for the geometry collapses the tapered faces (at 45 deg
    the 40-wide top pinches to a point / self-intersects for the 20-tall box):
    OCCT RAISES (Standard_ConstructionError), diagnosed as ``draft_failed`` —
    never a crash and never a silently wrong body. HTTP 200, last-good is the
    un-drafted extrude."""
    result = _post(
        _request(
            [
                square_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 20.0),
                draft_input(DRAFT_ID, 45.0, _all_side_refs()),
            ]
        )
    )
    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "draft_failed"
    assert result.last_good_feature_id == EXTRUDE_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(32000.0, abs=DRAFT_TOL)


def test_angle_out_of_range_rejected_at_request_validation(
    assert_validation_envelope: Any,
) -> None:
    """angle_deg has ``gt=-90, lt=90``: an out-of-range angle is a transport/
    validation failure of the call itself (§4.3) — 422 envelope, the same
    rejection documents applies on the write path (shared model)."""
    payload = _request(
        [
            square_sketch(SKETCH_ID),
            extrude_input(EXTRUDE_ID, SKETCH_ID, 20.0),
            draft_input(DRAFT_ID, 90.0, _all_side_refs()),
        ]
    )
    response = client.post("/api/v1/evaluate", json=payload)

    assert response.status_code == 422
    assert_validation_envelope(response.json())


# --- Kernel-level: draft_body directly -----------------------------------------------


def _box() -> Solid:
    """A 40x40x20 box at the origin (the golden's base body)."""
    return Solid.make_box(40.0, 40.0, 20.0)


def _side_faces(box: Solid) -> list[Any]:
    return [
        f
        for f in box.faces()
        if abs(f.normal_at(f.center(CenterOf.MASS)).Z) < DRAFT_TOL
    ]


def _base_neutral() -> Plane:
    """Neutral plane = the XY base at z=0, pull +Z (the golden's neutral plane)."""
    return Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, 0, 1))


def test_resolve_faces_returns_the_four_side_faces() -> None:
    """The four side signatures resolve to exactly four Faces, each vertical."""
    targets = [
        PlanarFaceSignature(
            normal=Vec3(x=n[0], y=n[1], z=n[2]),
            centroid=Vec3(x=c[0], y=c[1], z=c[2]),
            area_mm2=a,
        )
        for (n, c, a) in SIDE_FACES
    ]
    faces = resolve_faces(_box(), targets)
    assert len(faces) == 4
    for f in faces:
        assert abs(f.normal_at(f.center(CenterOf.MASS)).Z) < DRAFT_TOL


def test_draft_body_four_sides_is_the_analytic_frustum() -> None:
    """Kernel op directly: draft the four sides inward 5 deg about the base →
    29282.008.. mm^3 (the analytic frustum), a single connected solid, and a
    box-like 6/12 topology (draft tilts faces in place, never splits them)."""
    box = _box()
    result = draft_body(box, _side_faces(box), _base_neutral(), 5.0)
    assert result.volume == pytest.approx(DRAFT_VOLUME, abs=DRAFT_TOL)
    assert len(result.solids()) == 1
    assert len(result.faces()) == 6
    # top shrank to (40 - 2*20*tan5)^2; base unchanged, so the top face is smaller.
    top = math.pow(40.0 - 2 * 20.0 * math.tan(math.radians(5.0)), 2)
    top_face = next(
        f
        for f in result.faces()
        if abs(f.normal_at(f.center(CenterOf.MASS)).Z - 1.0) < DRAFT_TOL
    )
    sig = planar_face_signature(top_face)
    assert sig is not None
    assert sig[2] == pytest.approx(top, abs=1e-6)


def test_draft_body_collapsing_angle_raises_draft_error() -> None:
    """An angle that collapses / self-intersects the tapered faces makes OCCT
    raise (Standard_ConstructionError); draft_body diagnoses it as a DraftError,
    never a bare kernel exception escaping the boundary and never a silent bad
    body (OCCT raises here rather than mis-building — contrast shell)."""
    box = _box()
    with pytest.raises(DraftError):
        draft_body(box, _side_faces(box), _base_neutral(), 45.0)
