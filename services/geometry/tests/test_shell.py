"""Shell feature — API-level behavior of the hollow-to-a-wall feature.

Covers the shell acceptance criteria beyond the golden harness (the golden
``shell-open-top-box-40x25x10-t2`` runs every parametrized gate in
``test_goldens.py`` / ``test_step_roundtrip.py``): the golden tree evaluated
over HTTP populates the analytic mass properties and a fetchable
content-addressed mesh; the empty-faces SEALED hollow is exercised; the picked
face resolves through the SAME stage-1 planar-face signature the ``on_face``
datum uses; and every shell error path — ``no_prior_body``,
``subshape_unresolved``, ``shell_thickness_too_large``, ``shell_failed`` — is a
per-feature error under the strict-prefix rule (§4.3), never a transport failure.

The last section is the **zero-width-slit threshold** (finding SH-1): a thickness
of exactly half an internal wall is refused, and the two thicknesses 0.1 mm either
side of it build sound bodies — the sweep that proves the guard discriminates.

Numeric assertions use the documented golden tolerance (see
``goldens/shell-open-top-box-40x25x10-t2/expected.json`` for the planar box and
``goldens/shell-pinch-boundary-plate-40x40x10-pocket-t1.9/expected.json`` for the
curved pinch-boundary body — both measured-then-set), not ad-hoc epsilons.
"""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from build123d import Axis, CenterOf, Face, Solid, Vector
from fastapi.testclient import TestClient
from geometry.kernel import (
    ShellError,
    ShellThicknessError,
    SubshapeUnresolvedError,
    resolve_faces,
    shell_body,
)
from geometry.kernel.degenerate import find_zero_width_slits
from geometry.kernel.faces import planar_face_signature
from geometry.main import app
from py_kit.schemas.features import EvaluateTreeResult, PlanarFaceSignature
from py_kit.schemas.geometry import Vec3

client = TestClient(app)

GOLDEN_MODEL = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "shell-open-top-box-40x25x10-t2"
    / "model.json"
)

#: The documented shell-golden tolerance (expected.json tolerance_rationale:
#: planar geometry, measured worst deviation 8.9e-16; 1e-9 reviewed ceiling).
SHELL_TOL = 1e-9

#: Analytic open-top-box figures (full derivation in the golden expected.json).
SHELL_VOLUME = 3952.0  # 10000 outer - 6048 cavity (36x21x8)
SHELL_AREA = 4212.0

#: Fixed ids so requests — and therefore responses — are byte-reproducible.
#: The sketch/extrude/shell ids MATCH the golden model.json (posted verbatim).
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e5")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000e5001")
EXTRUDE_ID = uuid.UUID("00000000-0000-0000-0000-0000000e5002")
SHELL_ID = uuid.UUID("00000000-0000-0000-0000-0000000e5003")
TAIL_ID = uuid.UUID("00000000-0000-0000-0000-00000000e5e5")

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
    SAME shape the sketch-on-face / on_face datum uses (topo-naming §4)."""
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


#: The top (+Z, z=10) face signature of the 40x25x10 extruded box.
TOP_FACE = ((0.0, 0.0, 1.0), (20.0, 12.5, 10.0), 1000.0)


def shell_input(
    feature_id: uuid.UUID, thickness_mm: float, refs: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "shell",
            "version": 1,
            "params": {
                "thickness_mm": thickness_mm,
                "faces": {"kind": "faces", "refs": refs},
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


def test_golden_shell_tree_evaluates_over_http() -> None:
    """The committed golden model, posted verbatim: all three features ok, the
    analytic open-top-box volume/area on the wire, a content-addressed mesh id,
    and the hollow topology (11/24/1)."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    result = _post(payload)

    assert [(r.feature_id, r.status) for r in result.features] == [
        (SKETCH_ID, "ok"),
        (EXTRUDE_ID, "ok"),
        (SHELL_ID, "ok"),
    ]
    assert result.last_good_feature_id == SHELL_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(SHELL_VOLUME, abs=SHELL_TOL)
    assert result.properties.surface_area == pytest.approx(SHELL_AREA, abs=SHELL_TOL)
    assert result.properties.topology.faces == 11
    assert result.properties.topology.edges == 24
    assert result.properties.topology.shells == 1
    assert result.mesh_glb_id is not None
    assert result.mesh_glb_id.startswith("sha256:")
    assert result.features[2].data is None  # body-affecting, not a sketch payload


def test_evaluate_response_with_shell_is_byte_deterministic() -> None:
    """Same tree → identical response bytes incl. mesh_glb_id (a content hash of
    a deterministic GLB) — RESEARCH §9 for the shell path (the FACE ref resolves
    identically each rebuild)."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- Empty faces = a sealed (fully-enclosed) hollow ----------------------------------


def test_empty_faces_is_a_sealed_hollow() -> None:
    """DESIGN DECISION: an empty picked-face list is a valid SEALED hollow (a
    closed shell with a uniform cavity, NO opening), never a 422. The 40x25x10
    box shelled 2 mm on every face -> cavity 36x21x6 -> volume 10000 - 4536 =
    5464 mm^3; the outer envelope is untouched and the result is a single
    closed solid."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                shell_input(SHELL_ID, 2.0, []),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    # cavity 36x21x6 = 4536; sealed hollow removes it from all six sides.
    assert result.properties.volume == pytest.approx(5464.0, abs=SHELL_TOL)
    # A SEALED hollow has TWO disjoint shells: the outer skin and the inner
    # cavity surface (a hollow closed solid, like a hollow sphere) — contrast the
    # OPEN-top golden (1 shell, the opening joins inner and outer into one).
    assert result.properties.topology.shells == 2
    # outer envelope unchanged (inward offset).
    assert result.properties.bounding_box.max.z == pytest.approx(10.0, abs=SHELL_TOL)


# --- Picked-face opening (topological naming §4, reused for shell) --------------------


def test_open_top_shell_matches_the_golden_analytic() -> None:
    """Opening the picked top face gives the analytic open-top box (the golden
    figures) — the FACE signature resolves to exactly one face of the current
    body, leaving that side open."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                shell_input(SHELL_ID, 2.0, [_face_ref(EXTRUDE_ID, *TOP_FACE)]),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(SHELL_VOLUME, abs=SHELL_TOL)
    assert result.properties.topology.faces == 11


def test_picked_face_that_no_longer_exists_is_subshape_unresolved() -> None:
    """A picked face signature that matches no current face is an honest
    per-feature ``subshape_unresolved`` (topo-naming §5), never a 500 and never
    a silent wrong-face retarget: the centroid is at z=99, where no face lives."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                shell_input(
                    SHELL_ID,
                    2.0,
                    [
                        _face_ref(
                            EXTRUDE_ID, (0.0, 0.0, 1.0), (20.0, 12.5, 99.0), 1000.0
                        )
                    ],
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "subshape_unresolved"
    # last-good body is the un-shelled extrude (§4.3 honest fallback).
    assert result.last_good_feature_id == EXTRUDE_ID


# --- Error paths are per-feature values, never transport failures --------------------


def test_shell_with_no_prior_body_is_no_prior_body() -> None:
    """Shell needs a body-affecting feature before it (single body chain, §7.6):
    a sketch-only prefix → ``no_prior_body``, downstream skipped."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                shell_input(SHELL_ID, 2.0, []),
                rectangle_sketch(TAIL_ID),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "error", "skipped"]
    error = result.features[1].error
    assert error is not None
    assert error.code == "no_prior_body"
    assert result.mesh_glb_id is None
    assert result.properties is None


def test_thickness_that_collapses_the_cavity_is_shell_thickness_too_large() -> None:
    """A wall thicker than the smallest half-wall self-intersects / collapses the
    inward cavity. For the open-top 40x25x10 box, t=10 mm fills the whole height
    (the floor reaches the open top): OCCT quietly returns the un-hollowed box,
    and the material-removed invariant catches it as ``shell_thickness_too_large``
    — never a silently wrong solid. HTTP 200, pinned to the feature, last-good is
    the un-shelled extrude."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                shell_input(SHELL_ID, 10.0, [_face_ref(EXTRUDE_ID, *TOP_FACE)]),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "shell_thickness_too_large"
    assert result.last_good_feature_id == EXTRUDE_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(10000.0, abs=SHELL_TOL)


def test_thickness_that_fails_the_offset_is_shell_failed() -> None:
    """A wall so thick the offset cannot complete (t=12.5 mm collapses the 25 mm
    depth to zero) makes OCCT ``MakeThickSolid`` raise — a diagnosed kernel
    outcome, not a crash: ``shell_failed`` pinned to the feature, HTTP 200. This
    is the belt-and-braces sibling of ``shell_thickness_too_large`` (OCCT
    surfaces a too-thick wall two ways — see kernel/shell.py)."""
    result = _post(
        _request(
            [
                rectangle_sketch(SKETCH_ID),
                extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
                shell_input(SHELL_ID, 12.5, [_face_ref(EXTRUDE_ID, *TOP_FACE)]),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "shell_failed"
    assert result.last_good_feature_id == EXTRUDE_ID


def test_non_positive_thickness_rejected_at_request_validation(
    assert_validation_envelope: Any,
) -> None:
    """thickness_mm has ``gt=0``: a zero/negative thickness is a transport/
    validation failure of the call itself (§4.3) — 422 envelope, the same
    rejection documents applies on the write path (shared model)."""
    payload = _request(
        [
            rectangle_sketch(SKETCH_ID),
            extrude_input(EXTRUDE_ID, SKETCH_ID, 10.0),
            shell_input(SHELL_ID, 0.0, []),
        ]
    )
    response = client.post("/api/v1/evaluate", json=payload)

    assert response.status_code == 422
    assert_validation_envelope(response.json())


# --- Kernel-level: resolve_faces + shell_body directly -------------------------------


def _box() -> Solid:
    """A 40x25x10 box at the origin (the golden's base body)."""
    return Solid.make_box(40.0, 25.0, 10.0)


def _top_sig() -> PlanarFaceSignature:
    """The +Z top face signature of the box (z=10, area 1000)."""
    return PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=20.0, y=12.5, z=10.0),
        area_mm2=1000.0,
    )


def test_resolve_faces_returns_exactly_the_named_face() -> None:
    """One target signature resolves to exactly one Face whose recomputed
    signature matches the target (pick↔resolve, mirroring the edge resolver)."""
    (face,) = resolve_faces(_box(), [_top_sig()])
    sig = planar_face_signature(face)
    assert sig is not None
    normal, centroid, _area = sig
    assert abs(normal.Z - 1.0) < SHELL_TOL
    assert abs(centroid.Z - 10.0) < SHELL_TOL


def test_resolve_faces_dedupes_two_refs_to_the_same_face() -> None:
    """Two refs resolving to the SAME face collapse to one (idempotent) — the
    shell input is deterministic regardless of pick order (RESEARCH §9)."""
    faces = resolve_faces(_box(), [_top_sig(), _top_sig()])
    assert len(faces) == 1


def test_resolve_faces_empty_targets_is_empty() -> None:
    """No targets → no faces (the sealed-hollow request), not an error."""
    assert resolve_faces(_box(), []) == []


def test_resolve_faces_unresolved_raises() -> None:
    """A signature matching no current face is an honest SubshapeUnresolvedError,
    never a silent wrong-face retarget."""
    stale = PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=20.0, y=12.5, z=99.0),
        area_mm2=1000.0,
    )
    with pytest.raises(SubshapeUnresolvedError):
        resolve_faces(_box(), [stale])


def test_shell_body_open_top_is_the_analytic_volume() -> None:
    """Kernel op directly: open the top face, 2 mm wall → 3952 mm^3 (open-top
    box), a single connected shell."""
    box = _box()
    top = next(
        f
        for f in box.faces()
        if abs(f.normal_at(f.center(CenterOf.MASS)).Z - 1.0) < SHELL_TOL
        and abs(f.center(CenterOf.MASS).Z - 10.0) < 1e-6
    )
    result = shell_body(box, [top], 2.0)
    assert result.volume == pytest.approx(SHELL_VOLUME, abs=SHELL_TOL)
    assert len(result.shells()) == 1


def test_shell_body_collapsing_thickness_raises_thickness_error() -> None:
    """The material-removed invariant: a thickness that collapses the cavity
    (OCCT quietly returns the un-hollowed box) is a ShellThicknessError, never a
    silently wrong (full-volume) solid."""
    box = _box()
    top = next(
        f
        for f in box.faces()
        if abs(f.normal_at(f.center(CenterOf.MASS)).Z - 1.0) < SHELL_TOL
        and abs(f.center(CenterOf.MASS).Z - 10.0) < 1e-6
    )
    with pytest.raises(ShellThicknessError):
        shell_body(box, [top], 10.0)


def test_shell_body_offset_failure_raises_shell_error() -> None:
    """A thickness so large the OCCT offset cannot complete is a ShellError
    (belt-and-braces), never a bare kernel exception escaping the boundary."""
    box = _box()
    top = next(
        f
        for f in box.faces()
        if abs(f.normal_at(f.center(CenterOf.MASS)).Z - 1.0) < SHELL_TOL
        and abs(f.center(CenterOf.MASS).Z - 10.0) < 1e-6
    )
    with pytest.raises(ShellError):
        shell_body(box, [top], 12.5)


# --- The zero-width-slit threshold (finding SH-1) ------------------------------------
#
# A thickness of exactly HALF an internal wall lands the two inward offsets on the
# same plane: the wall stays solid and the cavity pinches to zero width, leaving
# coincident faces with no material between them. The three tests below are one
# threshold sweep on ONE body — refused at the pinch, sound 0.1 mm either side —
# so the guard is proved to DISCRIMINATE rather than to blanket-refuse the layout.
# The sound side below is also the new golden
# `shell-pinch-boundary-plate-40x40x10-pocket-t1.9` (full hand derivation there).

#: The documented tolerance of that golden (CURVED composition tier, measured
#: worst residual 5.46e-12; expected.json tolerance_rationale). Not an ad-hoc
#: epsilon and not the planar SHELL_TOL: this body carries 16 cylindrical faces.
PINCH_TOL = 1e-8

#: The SH-1 / CM-4 layout: 40x40x10 plate, [4,12]x[10,30] through-pocket, r3 on
#: every Z-parallel edge. Both r3 roundings cancel in plan (1600 - 9(4-pi) minus
#: 160 - 9(4-pi) = 1440), so the pre-shell body is exactly 14400 mm^3. The rib
#: between the outer wall and the pocket wall is 4.0 mm.
PINCH_BODY_VOLUME = 14400.0
PINCH_RIB_MM = 4.0
#: t = rib/2 exactly: the refused thickness.
PINCH_THICKNESS = 2.0
#: Sound neighbour BELOW: cavity plan 1120.8 - 22.8pi over a height of 8.1
#: (derivation in the golden's expected.json) -> 5321.52 + 184.68pi.
BELOW_THICKNESS = 1.9
BELOW_VOLUME = 5901.709331264961


def _pinch_body() -> Solid:
    """The SH-1 layout up to (not including) the shell."""
    plate = Solid.make_box(40.0, 40.0, 10.0)
    cutter = Solid.make_box(8.0, 20.0, 10.0).translate(Vector(4.0, 10.0, 0.0))
    pocketed: Solid = (plate - cutter).solids()[0]
    return pocketed.fillet(3.0, pocketed.edges().filter_by(Axis.Z)).solids()[0]  # pyright: ignore[reportUnknownMemberType]


def _pinch_top(body: Solid) -> list[Face]:
    return [
        f
        for f in body.faces()
        if abs(f.center(CenterOf.MASS).Z - 10.0) < 1e-9
        and abs(f.normal_at(f.center(CenterOf.MASS)).Z - 1.0) < 1e-9
    ]


def test_thickness_that_pinches_a_rib_to_zero_width_is_refused() -> None:
    """SH-1: t = exactly half a 4 mm rib is ``shell_thickness_too_large``, and the
    message tells the user what to change.

    Not a success-with-warning: at this exact value OCCT is unreliable in KIND
    (the same chain WITHOUT the r3 fillet returns 14172.183 mm^3 where 6308.531 is
    correct), and no repair pass removes the slit — the reasoning and its measured
    evidence live on :class:`ShellThicknessError`.
    """
    body = _pinch_body()
    assert body.volume == pytest.approx(PINCH_BODY_VOLUME, abs=PINCH_TOL)

    with pytest.raises(ShellThicknessError) as raised:
        shell_body(body, _pinch_top(body), PINCH_THICKNESS)

    message = str(raised.value)
    assert "zero-width slit" in message
    assert f"{PINCH_RIB_MM} mm" in message, message
    assert "112 mm^2" in message, message
    assert "a little thicker" in message, message


def test_the_pinch_guard_discriminates_a_tenth_of_a_millimetre() -> None:
    """Both neighbours build, so the refusal is a knife edge and not a policy.

    BELOW (t=1.9): the cavity survives as a 0.2 mm slot; volume is the analytic
    5321.52 + 184.68pi (the golden's derivation). ABOVE (t=2.1): the two offsets
    cross and the rib merges into solid material, so the body is sound with MORE
    material than the thinner wall left — asserted as the hand-derivable ordering
    ``below < above < unshelled`` rather than a recorded scalar, because OCCT does
    not follow the Minkowski erosion where two offsets cross (measured 0.95 mm^3
    off it on the sharp-cornered variant), so no closed form is honest there.
    """
    body = _pinch_body()
    below = shell_body(body, _pinch_top(body), BELOW_THICKNESS)
    above = shell_body(body, _pinch_top(body), PINCH_THICKNESS + 0.1)

    assert below.volume == pytest.approx(BELOW_VOLUME, abs=PINCH_TOL)
    assert not find_zero_width_slits(below)
    assert not find_zero_width_slits(above)
    assert BELOW_VOLUME < above.volume < PINCH_BODY_VOLUME


def test_the_pinch_gap_is_void_below_the_threshold_and_solid_above() -> None:
    """What the threshold MEANS geometrically, on a hand-derived probe.

    At the rib, the outer wall offsets to x = t and the pocket wall to x = 4 - t.
    So the 0.2 mm box ``[1.9,2.1] x [19.9,20.1] x [5.9,6.1]`` (at the pocket's y
    centre, mid-cavity in z, inside the dilated pocket's flat 14 mm face) is
    entirely CAVITY at t=1.9 (the slot runs x in [1.9,2.1] there) and entirely
    MATERIAL at t=2.1 (the walls have merged). At t=2.0 the two boundaries
    coincide in that box: the slit.
    """
    probe = Solid.make_box(0.2, 0.2, 0.2).translate(Vector(1.9, 19.9, 5.9))
    body = _pinch_body()

    below = shell_body(body, _pinch_top(body), BELOW_THICKNESS)
    # build123d types the boolean common as ShapeList[Unknown] | None (the OCP
    # wheel ships no stubs) — the same scoped relaxation kernel/removal.py takes.
    below_common = below.intersect(probe)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert below_common is None or not below_common.solids(), (
        "the 0.2 mm gap at the rib must be VOID below the threshold"
    )

    above = shell_body(body, _pinch_top(body), PINCH_THICKNESS + 0.1)
    above_common = above.intersect(probe)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert above_common is not None
    solid_volume = sum(s.volume for s in above_common.solids())
    assert solid_volume == pytest.approx(0.2**3, abs=PINCH_TOL)
