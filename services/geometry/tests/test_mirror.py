"""Mirror feature — API-level behavior of the reflect-and-union mirror (P2).

Covers the BACKLOG P2 mirror acceptance beyond the golden harness (the golden
``mirror-triangle-prism-2x`` runs every parametrized gate in ``test_goldens.py``
/ ``test_step_roundtrip.py``): the golden tree evaluated over HTTP populates real
mass properties and a fetchable content-addressed mesh; the REFLECTION-vs-
translation proof is asserted numerically; the overlapping-merge and symmetric
(on-plane) cases are checked by hand-computed volume; the mirror plane resolves
through a `datum` FEATURE ref as well as an origin datum; and every error path —
``no_target_body`` and ``reference_unresolved`` — is a per-feature error pinned
under the strict-prefix rule (design §4.3), never a transport failure.

v1 DESIGN DECISION (option B, the reflective sibling of the ADD pattern): a
mirror reflects the CURRENT body about a plane and unions the reflection into the
single body chain (§7.6). UNLIKE a pattern it does NOT force one connected lump —
a body that clears the plane mirrors to a disjoint TWO-lump body (§MB-0). Numeric
assertions use the documented tree-golden tolerance (measured-then-set,
``goldens/mirror-triangle-prism-2x/expected.json``), not ad-hoc epsilons.
"""

import json
import math
import uuid
from pathlib import Path
from typing import Any

import pytest
from build123d import Edge, Face, Plane, Solid, Vector, Wire
from fastapi.testclient import TestClient
from geometry.kernel.mirror import mirror_union
from geometry.main import app
from py_kit.schemas.features import EvaluateTreeResult

client = TestClient(app)

GOLDEN_MODEL = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "mirror-triangle-prism-2x"
    / "model.json"
)

#: The documented tolerance of the mirror golden (expected.json
#: tolerance_rationale: measured EXACTLY 0.0 on every property except a 6.66e-16
#: float residual on centroid.y; 1e-9 is the reviewed planar ceiling).
MIRROR_TOL = 1e-9

PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fc")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-00000000aaaa")
BODY_ID = uuid.UUID("00000000-0000-0000-0000-00000000bbbb")
MIRROR_ID = uuid.UUID("00000000-0000-0000-0000-00000000cccc")
DATUM_ID = uuid.UUID("00000000-0000-0000-0000-00000000dddd")

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


def rect_sketch(
    feature_id: uuid.UUID, x0: float, y0: float, x1: float, y1: float
) -> dict[str, Any]:
    """A closed rectangle [x0,x1] x [y0,y1] on XY, unconstrained (solver returns
    the input positions bitwise — same posture as the pattern suite)."""
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    entities = [_line(f"e{i + 1}", corners[i], corners[(i + 1) % 4]) for i in range(4)]
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
    distance_mm: float = 6.0,
    *,
    merge: bool = True,
) -> dict[str, Any]:
    """An additive extrude; ``merge=False`` STARTS a second body (§MB-0 Dec. 2)."""
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
                "merge": merge,
            },
        },
    }


def mirror_input(feature_id: uuid.UUID, plane: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "mirror",
            "version": 1,
            "params": {"plane": plane},
        },
    }


def datum_offset_input(
    feature_id: uuid.UUID, base: str, offset_mm: float
) -> dict[str, Any]:
    return {
        "id": str(feature_id),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {"base": base, "offset_mm": offset_mm, "flip": False},
        },
    }


def datum_midplane_input(
    feature_id: uuid.UUID, a: str, b: str, flip: bool = False
) -> dict[str, Any]:
    """A midplane datum between two ORIGIN datum planes (angular bisector for a
    non-parallel pair). Used to author a TILTED, non-principal mirror plane."""
    return {
        "id": str(feature_id),
        "feature": {
            "type": "datum",
            "version": 1,
            "params": {
                "kind": "midplane",
                "a": {"kind": "datum_plane", "plane": a},
                "b": {"kind": "datum_plane", "plane": b},
                "flip": flip,
            },
        },
    }


def _reflect_point(
    p: tuple[float, float, float],
    origin: tuple[float, float, float],
    normal: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Independent reflection-matrix oracle: reflect *p* across the plane through
    *origin* with unit *normal*. reflect(x) = x - 2((x-o)·n) n. No build123d — a
    pure-Python check the kernel reflection is compared against."""
    ox, oy, oz = origin
    nx, ny, nz = normal
    dx, dy, dz = p[0] - ox, p[1] - oy, p[2] - oz
    d = dx * nx + dy * ny + dz * nz
    return (p[0] - 2 * d * nx, p[1] - 2 * d * ny, p[2] - 2 * d * nz)


def _request(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"part_id": str(PART_ID), "tree_version": 3, "features": features}


def _post(payload: dict[str, Any]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200, response.text
    return EvaluateTreeResult.model_validate(response.json())


# --- The golden tree over HTTP -------------------------------------------------------


def test_golden_tree_evaluates_with_body_artifact_over_http() -> None:
    """The committed mirror golden, posted verbatim: all three features ok, the
    disjoint two-lump body volume 72 mm^3 (2V), 2 shells, content-addressed
    mesh id."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    result = _post(payload)

    assert [(r.feature_id, r.status) for r in result.features] == [
        (SKETCH_ID, "ok"),
        (BODY_ID, "ok"),
        (MIRROR_ID, "ok"),
    ]
    assert result.last_good_feature_id == MIRROR_ID
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(72.0, abs=MIRROR_TOL)
    assert result.properties.surface_area == pytest.approx(168.0, abs=MIRROR_TOL)
    # A disjoint reflection is a legitimately TWO-lump body (§MB-0), NOT a
    # pattern_disjoint error — the mirror does not force one connected lump.
    assert result.properties.topology.shells == 2
    assert result.properties.topology.faces == 10
    assert result.mesh_glb_id is not None
    assert result.mesh_glb_id.startswith("sha256:")


def test_evaluate_response_is_byte_deterministic() -> None:
    """Same mirror tree → identical response bytes INCLUDING mesh_glb_id (a
    content hash of a deterministic GLB) — RESEARCH §9."""
    payload: dict[str, Any] = json.loads(GOLDEN_MODEL.read_text(encoding="utf-8"))
    first = client.post("/api/v1/evaluate", json=payload)
    second = client.post("/api/v1/evaluate", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# --- Reflection proof: a true reflection, not a translation --------------------------


def test_mirror_is_a_reflection_not_a_translation() -> None:
    """The reflection-vs-translation discriminator (BACKLOG P2 acceptance).

    A CHIRAL right-triangle prism (right angle at (2,0), legs to (5,0)/(2,4))
    extruded 6 mm sits entirely at x>0, then mirrored about YZ (x=0). Because
    Shape.mirror is a handedness-reversing isometry, the reflected right angle
    lands at x=-2 (nearest the plane), so the union is mirror-symmetric about
    x=0 → centroid.x is EXACTLY 0. A pure TRANSLATION of this chiral profile that
    reproduced the same disjoint bounding box [-5,5] (a -7 mm shift) would put the
    reflected right angle at x=-5 instead, giving combined centroid.x = -0.5 mm.
    So centroid.x == 0 (to 1e-9) machine-proves a reflection, not a translation;
    a translation would fail this assert by 0.5 mm.
    """
    result = _post(
        _request(
            [
                {
                    "id": str(SKETCH_ID),
                    "feature": {
                        "type": "sketch",
                        "version": 1,
                        "params": {
                            "plane": dict(XY_PLANE),
                            "entities": [
                                _line("e1", (2.0, 0.0), (5.0, 0.0)),
                                _line("e2", (5.0, 0.0), (2.0, 4.0)),
                                _line("e3", (2.0, 4.0), (2.0, 0.0)),
                            ],
                            "constraints": [],
                        },
                    },
                },
                extrude_input(BODY_ID, SKETCH_ID),
                mirror_input(MIRROR_ID, {"kind": "datum_plane", "plane": "YZ"}),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    # Reflection symmetry: centroid ON the mirror plane (a translation gives -0.5).
    assert result.properties.centroid.x == pytest.approx(0.0, abs=MIRROR_TOL)
    # The reflected lump occupies the REFLECTED coordinates x in [-5,-2]: the AABB
    # spans [-5,5] symmetric about x=0, and the source-only body was x in [2,5].
    bbox = result.properties.bounding_box
    assert bbox.min.x == pytest.approx(-5.0, abs=MIRROR_TOL)
    assert bbox.max.x == pytest.approx(5.0, abs=MIRROR_TOL)
    assert result.properties.volume == pytest.approx(72.0, abs=MIRROR_TOL)


# --- Overlapping and symmetric (on-plane) cases handled sanely -----------------------


def test_overlapping_mirror_merges_to_one_solid() -> None:
    """A box straddling the mirror plane reflects into an OVERLAPPING copy that
    merges to ONE connected solid — the union volume is computed by hand.

    Box x in [-1,4], y in [0,4], z in [0,6] (V = 5*4*6 = 120). Mirror about YZ
    reflects it to x in [-4,1]; the two overlap in x in [-1,1] (width 2, volume
    2*4*6 = 48). Union = 120 + 120 - 48 = 192 mm^3 over x in [-4,4], and — the
    overlap merging the lumps — exactly ONE shell (not the disjoint 2)."""
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, -1.0, 0.0, 4.0, 4.0),
                extrude_input(BODY_ID, SKETCH_ID),
                mirror_input(MIRROR_ID, {"kind": "datum_plane", "plane": "YZ"}),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(192.0, abs=MIRROR_TOL)
    assert result.properties.topology.shells == 1
    bbox = result.properties.bounding_box
    assert bbox.min.x == pytest.approx(-4.0, abs=MIRROR_TOL)
    assert bbox.max.x == pytest.approx(4.0, abs=MIRROR_TOL)


def test_symmetric_body_mirror_is_a_no_op() -> None:
    """A body already SYMMETRIC about the mirror plane reflects onto itself — the
    union is the body itself, unchanged (the on-plane case handled sanely by
    clean() collapsing the coincident geometry). Box x in [-3,3] mirrored about
    YZ stays the same 6*4*6 = 144 mm^3 solid, 1 shell."""
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, -3.0, 0.0, 3.0, 4.0),
                extrude_input(BODY_ID, SKETCH_ID),
                mirror_input(MIRROR_ID, {"kind": "datum_plane", "plane": "YZ"}),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(144.0, abs=MIRROR_TOL)
    assert result.properties.topology.shells == 1
    assert result.properties.topology.faces == 6


# --- The mirror plane resolves through a datum FEATURE ref ----------------------------


def test_mirror_about_an_offset_datum_feature_plane() -> None:
    """The plane FeatureRef path: a mirror about an earlier OFFSET datum feature
    reflects the body across that datum's plane. The XZ origin datum's normal is
    -Y, so an offset of +8 slides the plane to y=-8 (build123d Plane.XZ.z_dir =
    -Y). A box at y in [0,4] reflected across y=-8 lands at y in [-20,-16] —
    disjoint 2V (2*96 = 192), symmetric about y=-8 (centroid.y = -8). Proves the
    datum-feature plane resolves through the same funnel a sketch plane uses."""
    result = _post(
        _request(
            [
                # A datum plane parallel to XZ, slid +8 mm along its normal (-Y).
                datum_offset_input(DATUM_ID, "XZ", 8.0),
                rect_sketch(SKETCH_ID, 0.0, 0.0, 4.0, 4.0),
                extrude_input(BODY_ID, SKETCH_ID),
                mirror_input(
                    MIRROR_ID,
                    {"kind": "feature", "feature_id": str(DATUM_ID)},
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok"]
    assert result.properties is not None
    # Box V = 4*4*6 = 96; disjoint mirror = 192; the two lumps at y in [0,4] and
    # y in [-20,-16] straddle y=-8 symmetrically → centroid.y = -8, 2 shells.
    assert result.properties.volume == pytest.approx(192.0, abs=MIRROR_TOL)
    assert result.properties.centroid.y == pytest.approx(-8.0, abs=MIRROR_TOL)
    assert result.properties.topology.shells == 2


# --- ADVERSARIAL GUARDS (geometry-qa 2026-07-23, commit 1497bac) ---------------------
# Push past the single axis-aligned-origin-plane golden: a TILTED datum, a
# multi-lump source, and mirrored-lump chirality/validity. See docs/GEOMETRY-QA.md.


def test_mirror_about_a_tilted_non_principal_midplane_datum() -> None:
    """PROBE 1 — mirror about a TILTED (non-principal) datum plane.

    The single mirror golden mirrors about an axis-aligned ORIGIN plane (YZ),
    and the offset-datum test uses an axis-PARALLEL plane; neither would catch a
    plane-resolution bug that mirrors about a principal plane / the origin
    instead of an arbitrarily-oriented datum. Here the mirror plane is a MIDPLANE
    datum between the XZ and YZ origin datums: their angular bisector is the plane
    x = y (normal (1,-1,0)/sqrt2 through the world origin), which reflects every
    point (x,y,z) -> (y,x,z) — an x<->y SWAP, a genuinely tilted 45deg reflection
    no principal-plane mirror reproduces.

    Source: a box x in [2,5], y in [0,1], z in [0,3] (V = 3*1*3 = 9), which clears
    the x=y plane (min x = 2 > max y = 1). Its reflection swaps x<->y to x in
    [0,1], y in [2,5], z in [0,3] — DISJOINT (source x>=2, reflection x<=1), so
    the union is a two-lump body of 2V = 18 mm^3, 2 shells, 12 faces.

    INDEPENDENT ORACLE (pure-Python _reflect_point, no build123d): the union of
    two equal-volume disjoint lumps is centred at midpoint(c, reflect(c)) where
    c = (3.5,0.5,1.5) is the source centroid. That midpoint is (2,2,1.5), which
    lies ON the x=y plane. A plane-resolution bug mirroring about YZ (x=0) instead
    would put the reflection at x in [-5,-2] -> centroid (0, 0.5, 1.5), FAILING
    this assert by 2 mm in x — the discriminator that a tilted datum resolved.
    """
    plane_origin = (0.0, 0.0, 0.0)
    inv_sqrt2 = 2.0**-0.5
    plane_normal = (inv_sqrt2, -inv_sqrt2, 0.0)
    source_centroid = (3.5, 0.5, 1.5)
    reflected = _reflect_point(source_centroid, plane_origin, plane_normal)
    # Oracle: reflection swaps x<->y exactly.
    assert reflected == pytest.approx((0.5, 3.5, 1.5), abs=MIRROR_TOL)
    expected_centroid = tuple(
        (source_centroid[i] + reflected[i]) / 2 for i in range(3)
    )  # (2.0, 2.0, 1.5), on the mirror plane

    result = _post(
        _request(
            [
                datum_midplane_input(DATUM_ID, "XZ", "YZ"),
                rect_sketch(SKETCH_ID, 2.0, 0.0, 5.0, 1.0),
                extrude_input(BODY_ID, SKETCH_ID, distance_mm=3.0),
                mirror_input(
                    MIRROR_ID, {"kind": "feature", "feature_id": str(DATUM_ID)}
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok"]
    assert result.properties is not None
    c = result.properties.centroid
    assert (c.x, c.y, c.z) == pytest.approx(expected_centroid, abs=MIRROR_TOL)
    # Centroid lies ON the tilted plane: n . (c - o) == 0 (the reflection oracle).
    signed = (
        (c.x - plane_origin[0]) * plane_normal[0]
        + (c.y - plane_origin[1]) * plane_normal[1]
        + (c.z - plane_origin[2]) * plane_normal[2]
    )
    assert signed == pytest.approx(0.0, abs=MIRROR_TOL)
    assert result.properties.volume == pytest.approx(18.0, abs=MIRROR_TOL)
    assert result.properties.topology.shells == 2
    assert result.properties.topology.faces == 12


def test_mirror_of_a_multi_lump_source_doubles_every_lump() -> None:
    """PROBE 4 — mirror a source that is ALREADY a multi-lump compound.

    Every existing mirror test feeds a single-lump source. Here the source of the
    SECOND mirror is itself a disjoint TWO-lump body (the output of the first
    mirror), so the feature must reflect EVERY lump and union them, doubling the
    count 2 -> 4 (not reflecting only one lump, not collapsing to a single solid).

    Tree: chiral triangular prism (V = 36, x in [2,5], y in [0,4], z in [0,6])
    -> mirror about YZ -> two disjoint lumps at x in [2,5] and x in [-5,-2]
    (V = 72) -> mirror about an XZ-offset datum at y = -8 (XZ.z_dir = -Y, offset
    +8) -> reflects BOTH lumps from y in [0,4] to y in [-20,-16], all four
    disjoint. Union V = 4*36 = 144, centroid (0, -8, 3) (x-symmetric about x=0
    and y-symmetric about y=-8), 4 shells, 20 faces (4 prisms * 5)."""
    tri = [
        _line("e1", (2.0, 0.0), (5.0, 0.0)),
        _line("e2", (5.0, 0.0), (2.0, 4.0)),
        _line("e3", (2.0, 4.0), (2.0, 0.0)),
    ]
    second_mirror = uuid.UUID("00000000-0000-0000-0000-00000000ceee")
    result = _post(
        _request(
            [
                {
                    "id": str(SKETCH_ID),
                    "feature": {
                        "type": "sketch",
                        "version": 1,
                        "params": {
                            "plane": dict(XY_PLANE),
                            "entities": tri,
                            "constraints": [],
                        },
                    },
                },
                extrude_input(BODY_ID, SKETCH_ID),
                mirror_input(MIRROR_ID, {"kind": "datum_plane", "plane": "YZ"}),
                datum_offset_input(DATUM_ID, "XZ", 8.0),
                mirror_input(
                    second_mirror, {"kind": "feature", "feature_id": str(DATUM_ID)}
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok", "ok"]
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(144.0, abs=MIRROR_TOL)
    assert result.properties.centroid.x == pytest.approx(0.0, abs=MIRROR_TOL)
    assert result.properties.centroid.y == pytest.approx(-8.0, abs=MIRROR_TOL)
    # Count DOUBLED from the two-lump source, not stuck at 2 and not merged to 1.
    assert result.properties.topology.shells == 4
    assert result.properties.topology.faces == 20
    bbox = result.properties.bounding_box
    assert bbox.min.x == pytest.approx(-5.0, abs=MIRROR_TOL)
    assert bbox.max.x == pytest.approx(5.0, abs=MIRROR_TOL)
    assert bbox.min.y == pytest.approx(-20.0, abs=MIRROR_TOL)
    assert bbox.max.y == pytest.approx(4.0, abs=MIRROR_TOL)


def test_mirrored_lump_is_a_valid_positive_volume_solid() -> None:
    """PROBE 3 — chirality: a mirror flips handedness; the reflected solid must
    stay a VALID, OUTWARD, POSITIVE-volume solid (not inside-out / negative).

    A kernel-level check (the HTTP wire exposes only aggregate mass properties):
    build a CHIRAL right-triangle prism, reflect it with Shape.mirror, and assert
    the reflected lump ALONE has positive volume equal to the source and passes
    OCCT's own validity check (Shape.is_valid, the BRepCheck_Analyzer verdict —
    it fails a solid whose faces face inward or whose shell is not closed).
    Then confirm mirror_union's disjoint two-lump result is likewise valid."""
    pts = [Vector(2, 0, 0), Vector(5, 0, 0), Vector(2, 4, 0), Vector(2, 0, 0)]
    face = Face(Wire([Edge.make_line(pts[i], pts[i + 1]) for i in range(3)]))
    prism = Solid.extrude(face, Vector(0, 0, 6))
    assert prism.volume == pytest.approx(36.0, abs=MIRROR_TOL)
    assert prism.is_valid

    reflected = prism.mirror(Plane.YZ)
    # Handedness-reversed but a PROPER solid: positive volume, not a negated one.
    assert reflected.volume == pytest.approx(36.0, abs=MIRROR_TOL)
    assert reflected.volume > 0.0
    assert reflected.is_valid
    # Reflected right angle lands at x=-2 (nearest the plane) -> centroid x=-3.
    rc = reflected.center()
    rc_xyz = (rc.X, rc.Y, rc.Z)
    assert rc_xyz == pytest.approx((-3.0, 4.0 / 3.0, 3.0), abs=MIRROR_TOL)

    union = mirror_union(prism, Plane.YZ)
    assert union.volume == pytest.approx(72.0, abs=MIRROR_TOL)
    assert union.is_valid


# --- Cut-aware mirror: reflect the CUT, don't fill the hole (FINDINGS #2) -------------

HOLE_FEATURE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d2")


def hole_feature_input(
    feature_id: uuid.UUID,
    face_feature: uuid.UUID,
    face_centroid: tuple[float, float, float],
    face_area: float,
    position: tuple[float, float, float],
    diameter_mm: float,
) -> dict[str, Any]:
    """A through-all Hole FEATURE on a body's +Z face (the flagship Hole)."""
    return {
        "id": str(feature_id),
        "feature": {
            "type": "hole",
            "version": 1,
            "params": {
                "face": {
                    "kind": "subshape",
                    "feature_id": str(face_feature),
                    "subshape_type": "face",
                    "selector": {
                        "selector_version": 1,
                        "signature": {
                            "subshape_type": "face",
                            "surface": "plane",
                            "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
                            "centroid": {
                                "x": face_centroid[0],
                                "y": face_centroid[1],
                                "z": face_centroid[2],
                            },
                            "area_mm2": face_area,
                        },
                    },
                },
                "position": {"x": position[0], "y": position[1], "z": position[2]},
                "diameter_mm": diameter_mm,
                "depth": {"kind": "through_all"},
            },
        },
    }


def test_mirror_of_a_holed_plate_reflects_the_hole_not_fills_it() -> None:
    """FINDINGS #2 regression: mirroring a plate-with-hole about its own midplane
    must reflect the HOLE (a hole on both sides), NOT reflect the filled body and
    union it into a featureless brick.

    Plate [0,40] x [0,40] x [0,20] (V=32000), a single r4 through-hole drilled by
    the Hole feature at (10,20), mirrored about a YZ-offset datum at x=20 (the
    plate midplane). The reflected hole lands at x=30, so the result is a plate
    with TWO r4 through-holes -> V = 32000 - 2*pi*16*20. The pre-fix whole-body
    union filled the hole and returned exactly 32000 (a solid brick, 6 faces): this
    asserts BOTH the drilled volume AND the two cylinder walls (8 faces), so the old
    behaviour FAILS on volume and on topology.
    """
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, 0.0, 0.0, 40.0, 40.0),
                extrude_input(BODY_ID, SKETCH_ID, 20.0),
                hole_feature_input(
                    HOLE_FEATURE_ID,
                    BODY_ID,
                    (20.0, 20.0, 20.0),
                    1600.0,
                    (10.0, 20.0, 20.0),
                    8.0,
                ),
                datum_offset_input(DATUM_ID, "YZ", 20.0),
                mirror_input(
                    MIRROR_ID, {"kind": "feature", "feature_id": str(DATUM_ID)}
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "ok", "ok", "ok"]
    assert result.properties is not None
    two_holes = 2 * math.pi * 4.0**2 * 20.0
    assert result.properties.volume == pytest.approx(
        32000.0 - two_holes, abs=MIRROR_TOL
    )
    # A holed plate is one solid with two cylinder walls — NOT the filled 6-face brick.
    assert result.properties.topology.faces == 8
    assert result.properties.topology.shells == 1
    # Holes at x=10,30 symmetric about the x=20 midplane -> centroid on it.
    assert result.properties.centroid.x == pytest.approx(20.0, abs=MIRROR_TOL)
    assert result.properties.centroid.y == pytest.approx(20.0, abs=MIRROR_TOL)


# --- Clearing-plane mirror: complete the part, never a silent no-op -------------------
# Code review 2026-07-25 (regression B): `_prev_cut_tools` fires on ANY preceding
# extrude-cut / Hole and the mirror took `mirror_cut` unconditionally, which never
# verified that anything was removed. Both canonical "mirror about a plane the body
# only touches" workflows therefore returned the body UNCHANGED with every feature
# `ok`. The golden mirror-cut-clearing-plane-block-40x40x20 locks the first chain end
# to end (mass properties + topology + mesh + STEP round-trip); these lock the second
# chain and the API-level behaviour of both.

POCKET_SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e1")
POCKET_CUT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e2")
POCKET2_SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e3")
POCKET2_CUT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e4")


def extrude_cut_input(
    feature_id: uuid.UUID, profile_id: uuid.UUID, distance_mm: float
) -> dict[str, Any]:
    """An extrude-CUT of *profile_id* — the pocket-forming sibling of extrude_input."""
    return {
        "id": str(feature_id),
        "feature": {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": str(profile_id)},
                "distance_mm": distance_mm,
                "operation": "cut",
                "direction": "normal",
            },
        },
    }


def test_extrude_cut_then_mirror_about_a_clearing_plane_completes_the_part() -> None:
    """REGRESSION B (headline): "complete the symmetric half".

    A 40x40x20 block with a 10x20x10 pocket, mirrored about a datum at x=40 — the
    block's own +X FACE, a plane the body only touches. The reflected pocket tool
    lands at x in [60,70], entirely outside the body, so the pre-fix `body.cut(...)`
    removed NOTHING and returned the untouched 30000 mm^3 block at x in [0,40] with
    every feature reporting `ok` — the user's part silently never completed.

    The mirror now reads a removal it cannot reach as "reflect and union the BODY"
    (whose reflection already carries its own pocket): an 80 mm part, 60000 mm^3,
    a notch in EACH half, fused across the shared x=40 face into ONE solid. Volume
    (2x), AABB (2x in x) and face count (11 -> 16) each fail on the old behaviour.
    Analytic values + tolerance: the golden's expected.json."""
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, 0.0, 0.0, 40.0, 40.0),
                extrude_input(BODY_ID, SKETCH_ID, 20.0),
                rect_sketch(POCKET_SKETCH_ID, 10.0, 10.0, 20.0, 30.0),
                extrude_cut_input(POCKET_CUT_ID, POCKET_SKETCH_ID, 10.0),
                datum_offset_input(DATUM_ID, "YZ", 40.0),
                mirror_input(
                    MIRROR_ID, {"kind": "feature", "feature_id": str(DATUM_ID)}
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 6
    assert result.properties is not None
    # 2 * (40*40*20 - 10*20*10); the silent no-op returned 30000.
    assert result.properties.volume == pytest.approx(60000.0, abs=MIRROR_TOL)
    bbox = result.properties.bounding_box
    assert bbox.min.x == pytest.approx(0.0, abs=MIRROR_TOL)
    assert bbox.max.x == pytest.approx(80.0, abs=MIRROR_TOL)
    # 6 outer faces + 5 per notch; the no-op body had 11 (one notch).
    assert result.properties.topology.faces == 16
    assert result.properties.topology.shells == 1
    assert result.properties.centroid.x == pytest.approx(40.0, abs=MIRROR_TOL)


def test_hole_then_mirror_about_a_clearing_plane_duplicates_the_holed_body() -> None:
    """REGRESSION B, the Hole-sourced twin: "duplicate across a clearing plane".

    The same silent no-op reached through `state.last_hole_tools` instead of a
    reconstructed extrude-cut tool. A 40x40x20 plate with one r4 through-hole at
    x=10, mirrored about its +X face (x=40): the reflected bore lands at x=70,
    misses the body, and the pre-fix mirror returned the unchanged single-holed
    plate. Now the reflection of the ALREADY-DRILLED plate is unioned in, giving the
    80 mm part with a hole in each half — 64000 - 2*(pi*4^2*20) mm^3, 8 faces (6
    outer + 2 cylinder walls). The pre-fix result was 32000 - 320*pi over x in
    [0,40] with 7 faces."""
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, 0.0, 0.0, 40.0, 40.0),
                extrude_input(BODY_ID, SKETCH_ID, 20.0),
                hole_feature_input(
                    HOLE_FEATURE_ID,
                    BODY_ID,
                    (20.0, 20.0, 20.0),
                    1600.0,
                    (10.0, 20.0, 20.0),
                    8.0,
                ),
                datum_offset_input(DATUM_ID, "YZ", 40.0),
                mirror_input(
                    MIRROR_ID, {"kind": "feature", "feature_id": str(DATUM_ID)}
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 5
    assert result.properties is not None
    two_holes = 2 * math.pi * 4.0**2 * 20.0
    assert result.properties.volume == pytest.approx(
        64000.0 - two_holes, abs=MIRROR_TOL
    )
    assert result.properties.topology.faces == 8
    assert result.properties.topology.shells == 1
    bbox = result.properties.bounding_box
    assert bbox.max.x == pytest.approx(80.0, abs=MIRROR_TOL)


def test_mirror_preserves_a_cut_that_precedes_the_mirrored_one() -> None:
    """The guard on the FIX itself: an EARLIER removal must survive the mirror.

    The tempting "general" fix — `mirror_union` then re-subtract both tool sets —
    fills every removal the reflection covers, and only the IMMEDIATELY-preceding
    cut's tools are known (`_prev_cut_tools`), so it would silently WELD SHUT any
    earlier pocket: strictly worse than the bug it fixes. Two pockets then a
    midplane mirror: 32000 - 800 (pocket A, x in [4,8]) - 800 (pocket B, x in
    [14,18]) - 800 (B's reflection at x in [22,26]) = 29600 mm^3. A union-then-recut
    implementation returns 30400 (A filled); the pre-fix code also returns 29600, so
    this test is a NON-regression lock, not a bug reproduction."""
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, 0.0, 0.0, 40.0, 40.0),
                extrude_input(BODY_ID, SKETCH_ID, 20.0),
                rect_sketch(POCKET_SKETCH_ID, 4.0, 10.0, 8.0, 30.0),
                extrude_cut_input(POCKET_CUT_ID, POCKET_SKETCH_ID, 10.0),
                rect_sketch(POCKET2_SKETCH_ID, 14.0, 10.0, 18.0, 30.0),
                extrude_cut_input(POCKET2_CUT_ID, POCKET2_SKETCH_ID, 10.0),
                datum_offset_input(DATUM_ID, "YZ", 20.0),
                mirror_input(
                    MIRROR_ID, {"kind": "feature", "feature_id": str(DATUM_ID)}
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 8
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(29600.0, abs=MIRROR_TOL)
    # 6 outer + 5 per notch * 3 notches = 21; a filled pocket A would read 16.
    assert result.properties.topology.faces == 21
    assert result.properties.topology.shells == 1


# --- Error paths are per-feature values, never transport failures ---------------------


# --- An INTERVENING feature must not shadow the cut a mirror reflects (CM-1) ---------
#
# The composition matrix (GEOMETRY-QA 2026-07-25) reached the FINDINGS #2
# featureless-brick symptom again: the mirror sniffed the IMMEDIATELY-preceding
# body-affecting feature for its cut source, so an unrelated chamfer / fillet /
# boss between the hole and the mirror made it take `mirror_union`, whose
# reflection FILLS the bore (31640.0 mm^3 with no cylindrical face where
# 29629.3807 is correct). The feature layer now RECORDS each cut's removal tools
# and the mirror reflects the most recent cut of the active body, so no feature in
# between can shadow it. The pattern deliberately KEEPS the immediate-predecessor
# rule (its fallback is a different reading, not lost geometry) — locked by
# `test_pattern_after_an_intervening_fillet_unions_whole_body_not_recut`.

CHAMFER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000f1")
FILLET_ID = uuid.UUID("00000000-0000-0000-0000-0000000000f2")


def _z_edge_modifier(
    feature_id: uuid.UUID, kind: str, size_mm: float
) -> dict[str, Any]:
    """A fillet/chamfer of the four Z-parallel edges — an unrelated modifier to
    sit between a cut and the mirror (the `axis_parallel` edge predicate)."""
    size = "radius_mm" if kind == "fillet" else "distance_mm"
    return {
        "id": str(feature_id),
        "feature": {
            "type": kind,
            "version": 1,
            "params": {
                "edges": {"kind": "axis_parallel", "axis": "Z"},
                size: size_mm,
            },
        },
    }


@pytest.mark.parametrize(
    ("kind", "removed"),
    [
        # A chamfer d3 on the four corners of a 40x40x20 plate: 4 * (d^2/2) * h.
        ("chamfer", 4.0 * 20.0 * (3.0**2 / 2.0)),
        # A fillet r3 on the same corners: 4 * (r^2 - pi r^2 / 4) * h.
        ("fillet", 20.0 * 4.0 * (3.0**2 - math.pi * 3.0**2 / 4.0)),
    ],
)
def test_mirror_keeps_the_hole_across_an_intervening_modifier(
    kind: str, removed: float
) -> None:
    """CM-1 (P0): hole -> <chamfer|fillet> -> midplane mirror keeps BOTH bores.

    A 40x40x20 plate, one Ø8 through-hole at x=10, an unrelated corner
    chamfer/fillet 20+ mm from the bore, then a mirror about x=20. The bore must
    still reflect to x=30, so the volume is the modified plate minus TWO bores and
    the topology carries two cylinder walls (8 faces + 4 chamfer/fillet faces = 12).
    Pre-fix: the bore vanished entirely (31640.0 / 31845.4867, no cylindrical face).
    """
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, 0.0, 0.0, 40.0, 40.0),
                extrude_input(BODY_ID, SKETCH_ID, 20.0),
                hole_feature_input(
                    HOLE_FEATURE_ID,
                    BODY_ID,
                    (20.0, 20.0, 20.0),
                    1600.0,
                    (10.0, 20.0, 20.0),
                    8.0,
                ),
                _z_edge_modifier(
                    CHAMFER_ID if kind == "chamfer" else FILLET_ID, kind, 3.0
                ),
                datum_offset_input(DATUM_ID, "YZ", 20.0),
                mirror_input(
                    MIRROR_ID, {"kind": "feature", "feature_id": str(DATUM_ID)}
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 6
    assert result.properties is not None
    two_bores = 2 * math.pi * 4.0**2 * 20.0
    assert result.properties.volume == pytest.approx(
        32000.0 - removed - two_bores, abs=MIRROR_TOL
    )
    # 6 outer + 4 modifier faces + 2 cylinder walls; a filled bore reads 10.
    assert result.properties.topology.faces == 12
    assert result.properties.topology.shells == 1
    # Bores at x=10 and x=30 are symmetric about the mirror plane, as are the four
    # modified corners → the centroid sits exactly on x=20.
    assert result.properties.centroid.x == pytest.approx(20.0, abs=MIRROR_TOL)


def test_mirror_does_not_reflect_a_cut_made_in_another_body() -> None:
    """The recorded cut applies to ITS body only (§MB-0).

    A pocketed 40x40x20 plate, then a SECOND body (``merge: false``) that clears
    it, then a mirror about the second body's own -X face at x=60. The recorded
    pocket tool belongs to body A, so the mirror must not reflect it into body B:
    body B (a 20x20x10 block at x in [60,80]) reflects and unions to two 4000 mm^3
    lumps = 8000, leaving body A's 30000 mm^3 untouched — 38000 mm^3 in total.
    """
    block_sketch = uuid.UUID("00000000-0000-0000-0000-0000000000f3")
    block_body = uuid.UUID("00000000-0000-0000-0000-0000000000f4")
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, 0.0, 0.0, 40.0, 40.0),
                extrude_input(BODY_ID, SKETCH_ID, 20.0),
                rect_sketch(POCKET_SKETCH_ID, 10.0, 10.0, 20.0, 30.0),
                extrude_cut_input(POCKET_CUT_ID, POCKET_SKETCH_ID, 10.0),
                rect_sketch(block_sketch, 60.0, 0.0, 80.0, 20.0),
                extrude_input(block_body, block_sketch, 10.0, merge=False),
                datum_offset_input(DATUM_ID, "YZ", 60.0),
                mirror_input(
                    MIRROR_ID, {"kind": "feature", "feature_id": str(DATUM_ID)}
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok"] * 8
    assert result.properties is not None
    # A: 40*40*20 - 10*20*10 = 30000; B doubled: 2 * 20*20*10 = 8000.
    assert result.properties.volume == pytest.approx(38000.0, abs=MIRROR_TOL)
    bbox = result.properties.bounding_box
    assert bbox.min.x == pytest.approx(0.0, abs=MIRROR_TOL)
    assert bbox.max.x == pytest.approx(80.0, abs=MIRROR_TOL)


def test_mirror_before_any_body_is_no_target_body() -> None:
    """A mirror with no prior body-affecting feature → no_target_body (the same
    posture as a pattern before any body)."""
    result = _post(
        _request([mirror_input(MIRROR_ID, {"kind": "datum_plane", "plane": "YZ"})])
    )

    assert result.features[0].status == "error"
    error = result.features[0].error
    assert error is not None
    assert error.code == "no_target_body"
    assert result.mesh_glb_id is None


def test_mirror_plane_referencing_a_missing_feature_is_reference_unresolved() -> None:
    """A plane FeatureRef that resolves to no earlier datum of this prefix →
    reference_unresolved pinned to the referenced feature; the seed body stays
    last-good (strict-prefix rule)."""
    missing = uuid.UUID("00000000-0000-0000-0000-0000000000ee")
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, 0.0, 0.0, 4.0, 4.0),
                extrude_input(BODY_ID, SKETCH_ID),
                mirror_input(
                    MIRROR_ID, {"kind": "feature", "feature_id": str(missing)}
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == missing
    # Strict-prefix: the last-good body (the extrude) is still tessellated.
    assert result.last_good_feature_id == BODY_ID
    assert result.mesh_glb_id is not None


def test_mirror_plane_referencing_a_non_datum_feature_is_reference_unresolved() -> None:
    """A plane FeatureRef pointing at a non-`datum` feature (the extrude body) is
    not a resolvable plane → reference_unresolved (geometry re-checks the slot's
    datum-only rule; it must not trust its callers)."""
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, 0.0, 0.0, 4.0, 4.0),
                extrude_input(BODY_ID, SKETCH_ID),
                mirror_input(
                    MIRROR_ID, {"kind": "feature", "feature_id": str(BODY_ID)}
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok", "ok", "error"]
    error = result.features[2].error
    assert error is not None
    assert error.code == "reference_unresolved"
    assert error.upstream_feature_id == BODY_ID


# --- CM-5: the mirror reflects a REVOLVE / SWEEP / LOFT cut too -----------------------
#
# The FINDINGS #2 featureless brick, alive for the three NON-EXTRUDE cuts until
# 2026-07-30: only extrude-cut and Hole wrote the v1 cut slot, so a `body`-scope
# mirror after a revolve/sweep/loft cut had no cut on record, took `mirror_union`,
# and the reflection FILLED the void — the plate came back as the bare brick with
# every feature `ok`. `record_cut_tools` now also fires in the shared `_cut_active`
# funnel, which is the ONE place all three verbs cut, so no verb can be forgotten.
# Measured over the whole suite, neither v1 reader's answer changed on any chain
# that existed before (docs/GEOMETRY-QA.md 2026-07-30).

REVCUT_DATUM_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c5")
CUT_SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c6")
CUT_FEATURE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c7")
PATH_SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c8")
LOFT_DATUM_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c9")
LOFT_SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-0000000000ca")

#: The CM-5 fixture plate: [0,40]^2 x 20, mirrored about x=20 — the SAME plate and
#: plane the hole/CM-1 tests above use, so a reflected r4 bore must land on the
#: SAME number they assert (61989.3807), whichever verb cut it.
CM5_PLATE_V = 40.0 * 40.0 * 20.0
CM5_BORE_R = 4.0
CM5_BORE_AT = (10.0, 20.0)
CM5_BORE_DV = -(math.pi * CM5_BORE_R**2 * 20.0)
#: The loft row: an 8x8 (z=0) -> 6x6 (z=20) tapered through-pocket at the same
#: place. Prismatoid rule (h/3)(A1 + A2 + sqrt(A1 A2)) — exact for a frustum.
CM5_LOFT_LOW, CM5_LOFT_HIGH = 8.0, 6.0
CM5_LOFT_DV = -(
    20.0
    / 3.0
    * (
        CM5_LOFT_LOW**2
        + CM5_LOFT_HIGH**2
        + math.sqrt(CM5_LOFT_LOW**2 * CM5_LOFT_HIGH**2)
    )
)


def _sketch_on(
    feature_id: uuid.UUID, entities: list[dict[str, Any]], plane: dict[str, Any]
) -> dict[str, Any]:
    """An unconstrained sketch of *entities* on an arbitrary resolved *plane*."""
    return {
        "id": str(feature_id),
        "feature": {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": dict(plane),
                "entities": entities,
                "constraints": [],
            },
        },
    }


def _rect_entities(x0: float, y0: float, x1: float, y1: float) -> list[dict[str, Any]]:
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [_line(f"e{i + 1}", corners[i], corners[(i + 1) % 4]) for i in range(4)]


def _revolve_cut_bore() -> list[dict[str, Any]]:
    """A r4 through-bore at (10,20) cut by a REVOLVE about a vertical axis.

    The axis has to lie in the sketch plane, so the profile is drawn on a datum
    parallel to YZ at x=10 (u = world +Y, v = world +Z): the construction line at
    u=20 is the world vertical through (10,20), and the 4x20 rectangle beside it
    sweeps the full bore.
    """
    return [
        datum_offset_input(REVCUT_DATUM_ID, "YZ", CM5_BORE_AT[0]),
        _sketch_on(
            CUT_SKETCH_ID,
            [
                *_rect_entities(CM5_BORE_AT[1], 0.0, CM5_BORE_AT[1] + CM5_BORE_R, 20.0),
                {
                    **_line("ax", (CM5_BORE_AT[1], 0.0), (CM5_BORE_AT[1], 20.0)),
                    "construction": True,
                },
            ],
            {"kind": "feature", "feature_id": str(REVCUT_DATUM_ID)},
        ),
        {
            "id": str(CUT_FEATURE_ID),
            "feature": {
                "type": "revolve",
                "version": 1,
                "params": {
                    "profile": {
                        "kind": "feature",
                        "feature_id": str(CUT_SKETCH_ID),
                    },
                    "axis": {"kind": "sketch_line", "entity": "ax"},
                    "angle_deg": 360.0,
                    "operation": "cut",
                },
            },
        },
    ]


def _sweep_cut_bore() -> list[dict[str, Any]]:
    """The same r4 bore, cut by SWEEPING the circle up a straight +Z path.

    The path is a relative trajectory from the profile's own location (the v1
    sweep limit), so a 25 mm vertical line on XZ takes the XY circle clean through
    the 20 mm plate.
    """
    return [
        _sketch_on(
            CUT_SKETCH_ID,
            [
                {
                    "id": "c1",
                    "kind": "circle",
                    "center": {"x": CM5_BORE_AT[0], "y": CM5_BORE_AT[1]},
                    "radius": CM5_BORE_R,
                }
            ],
            XY_PLANE,
        ),
        _sketch_on(
            PATH_SKETCH_ID,
            [_line("p1", (0.0, 0.0), (0.0, 25.0))],
            {"kind": "datum_plane", "plane": "XZ"},
        ),
        {
            "id": str(CUT_FEATURE_ID),
            "feature": {
                "type": "sweep",
                "version": 1,
                "params": {
                    "profile": {
                        "kind": "feature",
                        "feature_id": str(CUT_SKETCH_ID),
                    },
                    "path": {"kind": "feature", "feature_id": str(PATH_SKETCH_ID)},
                    "operation": "cut",
                },
            },
        },
    ]


def _loft_cut_pocket() -> list[dict[str, Any]]:
    """An 8x8 -> 6x6 tapered through-pocket at (10,20), cut by a LOFT between two
    parallel sections (XY and a datum XY@20)."""
    cx, cy = CM5_BORE_AT
    return [
        _sketch_on(
            CUT_SKETCH_ID,
            _rect_entities(
                cx - CM5_LOFT_LOW / 2,
                cy - CM5_LOFT_LOW / 2,
                cx + CM5_LOFT_LOW / 2,
                cy + CM5_LOFT_LOW / 2,
            ),
            XY_PLANE,
        ),
        datum_offset_input(LOFT_DATUM_ID, "XY", 20.0),
        _sketch_on(
            LOFT_SKETCH_ID,
            _rect_entities(
                cx - CM5_LOFT_HIGH / 2,
                cy - CM5_LOFT_HIGH / 2,
                cx + CM5_LOFT_HIGH / 2,
                cy + CM5_LOFT_HIGH / 2,
            ),
            {"kind": "feature", "feature_id": str(LOFT_DATUM_ID)},
        ),
        {
            "id": str(CUT_FEATURE_ID),
            "feature": {
                "type": "loft",
                "version": 1,
                "params": {
                    "profiles": [
                        {"kind": "feature", "feature_id": str(CUT_SKETCH_ID)},
                        {"kind": "feature", "feature_id": str(LOFT_SKETCH_ID)},
                    ],
                    "operation": "cut",
                },
            },
        },
    ]


@pytest.mark.parametrize(
    ("verb", "cut", "delta", "faces"),
    [
        ("revolve", _revolve_cut_bore(), CM5_BORE_DV, 8),
        ("sweep", _sweep_cut_bore(), CM5_BORE_DV, 8),
        ("loft", _loft_cut_pocket(), CM5_LOFT_DV, 14),
    ],
    ids=["revolve", "sweep", "loft"],
)
def test_mirror_reflects_a_revolve_sweep_or_loft_cut(
    verb: str, cut: list[dict[str, Any]], delta: float, faces: int
) -> None:
    """CM-5 (P1): plate -> <revolve|sweep|loft> CUT -> midplane mirror keeps the void.

    This is FINDINGS #2's own fixture with the bore cut by a different VERB: a
    40x40x20 plate, a Ø8 through-bore at (10,20), a mirror about x=20. So the two
    bore rows must land on FINDINGS #2's exact numbers — **29989.3807 mm^3**
    correct versus **32000.0** for the filled brick — which cross-checks the three
    cut funnels against the hole funnel rather than against themselves. The loft row
    is the same chain with a tapered pocket (30026.6667 vs 32000.0).

    Pre-fix all three returned 32000.0 with **6 faces / 12 edges** — the bare
    plate, every feature reporting `ok`.
    """
    del verb
    result = _post(
        _request(
            [
                rect_sketch(SKETCH_ID, 0.0, 0.0, 40.0, 40.0),
                extrude_input(BODY_ID, SKETCH_ID, 20.0),
                *cut,
                datum_offset_input(DATUM_ID, "YZ", 20.0),
                mirror_input(
                    MIRROR_ID, {"kind": "feature", "feature_id": str(DATUM_ID)}
                ),
            ]
        )
    )

    assert [r.status for r in result.features] == ["ok"] * (4 + len(cut))
    assert result.properties is not None
    assert result.properties.volume == pytest.approx(
        CM5_PLATE_V + 2.0 * delta, abs=MIRROR_TOL
    ), "the mirror FILLED the void (32000.0 is the featureless brick)"
    assert result.properties.topology.faces == faces
    assert result.properties.topology.shells == 1
    bbox = result.properties.bounding_box
    assert bbox.max.x == pytest.approx(40.0, abs=MIRROR_TOL), (
        "the mirror unioned the whole BODY instead of reflecting the removal"
    )
