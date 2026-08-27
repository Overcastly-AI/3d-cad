"""Stage-1 face signatures + datum-from-face resolution (kernel level).

Covers geometry.kernel.faces: the planar-face fingerprint (normal / centroid /
area), the deterministic derived sketch basis, and the exactly-one-or-error
resolver (docs/design/topological-naming.md 2b/4, datum-planes.md 7). The
HEADLINE gate is the same-enumeration guarantee: the signature the selection
overlay hands a client (the pick side) is byte-for-byte the one
``resolve_face_plane`` matches against (the resolve side), so a picked face
resolves back to itself — the measurement order-equality lesson applied to faces.

Tolerances are the documented kernel bound, never ad-hoc epsilons: a box is
planar-exact in OCCT, so deviation from analytic is round-off only.
"""

import math
from typing import Any

import pytest
from build123d import CenterOf, Compound, Face, Solid
from geometry.kernel import (
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    planar_faces,
    resolve_face_plane,
    selection_overlay,
)
from geometry.kernel import faces as faces_module
from geometry.kernel.faces import (
    CENTROID_TOL_MM,
    PlanarFaceRecord,
    coplanar_signatures_match,
    enclosing_face_match,
    face_signature_dto,
    planar_face_signature,
    planar_signatures_match,
    translated_signatures_match,
)
from geometry.kernel.hole import bore_hole
from geometry.kernel.types import BodyShape
from py_kit.schemas.features import PlanarFaceSignature
from py_kit.schemas.geometry import Vec3

#: Kernel linear tolerance (CLAUDE.md 1e-7) — a ceiling, not a fit.
TOL = 1e-7


def _box() -> Solid:
    """A 40x40x10 box at the origin (base of the boss-on-face golden)."""
    return Solid.make_box(40.0, 40.0, 10.0).translate((-20.0, -20.0, 0.0))


def _top_face_signature() -> PlanarFaceSignature:
    """The analytic signature of the box's +Z top face (z=10, area 1600)."""
    return PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=0.0, y=0.0, z=10.0),
        area_mm2=1600.0,
    )


# --- signatures ------------------------------------------------------------------


def test_box_faces_are_all_planar_with_signatures() -> None:
    records = planar_faces(_box())
    assert len(records) == 6  # a box has six planar faces
    # every record carries a full signature and a resolved plane
    assert all(isinstance(r.signature, PlanarFaceSignature) for r in records)


def test_curved_face_has_no_planar_signature() -> None:
    """A cylinder's lateral face is non-planar → no signature (not sketchable)."""
    cylinder = Solid.make_cylinder(10.0, 25.0)
    planar = planar_faces(cylinder)
    # only the two flat caps are planar; the curved wall is omitted
    assert len(planar) == 2
    for face in cylinder.faces():
        sig = planar_face_signature(face)
        assert (sig is None) == (face.geom_type.name != "PLANE")


def test_derived_sketch_x_dir_is_pinned_from_the_face_normal() -> None:
    """The derived sketch basis pins x_dir from the normal (least-aligned world
    axis, ties broken X<Y<Z) so it is stable across rebuilds (RESEARCH §9): a +Z
    or +/-X face → x_dir +X or +Y respectively. Checked on the six box faces."""
    expected_x_dir = {
        (0.0, 0.0, 1.0): (1.0, 0.0, 0.0),  # +Z top  → +X
        (0.0, 0.0, -1.0): (1.0, 0.0, 0.0),  # -Z base → +X
        (1.0, 0.0, 0.0): (0.0, 1.0, 0.0),  # +X side → +Y
        (-1.0, 0.0, 0.0): (0.0, 1.0, 0.0),  # -X side → +Y
        (0.0, 1.0, 0.0): (1.0, 0.0, 0.0),  # +Y side → +X
        (0.0, -1.0, 0.0): (1.0, 0.0, 0.0),  # -Y side → +X
    }
    for record in planar_faces(_box()):
        normal = (
            record.signature.normal.x,
            record.signature.normal.y,
            record.signature.normal.z,
        )
        want = expected_x_dir[normal]
        assert tuple(record.plane.x_dir) == pytest.approx(want, abs=TOL)
        # x_dir is orthogonal to the normal (a valid in-plane axis)
        assert record.plane.x_dir.dot(record.plane.z_dir) == pytest.approx(0.0, abs=TOL)


# --- resolution ------------------------------------------------------------------


def test_resolve_top_face_yields_the_expected_plane() -> None:
    plane = resolve_face_plane(_box(), _top_face_signature(), 0.0)
    assert tuple(plane.origin) == pytest.approx((0.0, 0.0, 10.0), abs=TOL)
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, 1.0), abs=TOL)
    assert tuple(plane.x_dir) == pytest.approx((1.0, 0.0, 0.0), abs=TOL)


def test_resolve_applies_offset_along_the_face_normal() -> None:
    plane = resolve_face_plane(_box(), _top_face_signature(), 5.0)
    assert tuple(plane.origin) == pytest.approx((0.0, 0.0, 15.0), abs=TOL)
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, 1.0), abs=TOL)


def test_resolve_is_deterministic_across_rebuilds() -> None:
    """The same signature against a freshly rebuilt body resolves to the same
    plane — the face reference survives a rebuild (topo-naming §7.5)."""
    a = resolve_face_plane(_box(), _top_face_signature(), 0.0)
    b = resolve_face_plane(_box(), _top_face_signature(), 0.0)
    assert tuple(a.origin) == tuple(b.origin)
    assert tuple(a.z_dir) == tuple(b.z_dir)
    assert tuple(a.x_dir) == tuple(b.x_dir)


def test_unmatched_signature_is_subshape_unresolved() -> None:
    """A signature no planar face matches (wrong area) is an honest error, not a
    wrong plane — the face 'no longer exists after the rebuild' path (§5).

    NB the fixture states a wrong AREA, not merely a wrong offset: since tier 3
    (QA-2) a +Z face of the right area at the right in-plane station resolves at
    WHATEVER z it now sits at, deliberately and unboundedly (see
    ``test_a_translated_match_is_not_bounded_by_how_far_the_plane_moved``). Area
    900 mm^2 exists on no face of this box at any offset."""
    stale = PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=0.0, y=0.0, z=99.0),  # no face at z=99 ...
        area_mm2=900.0,  # ... and no 900 mm^2 face anywhere on the box
    )
    with pytest.raises(SubshapeUnresolvedError):
        resolve_face_plane(_box(), stale, 0.0)


def _drilled_top(diameter_mm: float) -> tuple[PlanarFaceSignature, BodyShape]:
    """The +Z top-face signature (and body) of the box after an OFF-CENTRE through
    hole of ``diameter_mm`` — the face a SIBLING hole would have been picked
    against. Off-centre so both the area AND the area-centroid shift with the
    diameter (the exact drift that orphans a sibling reference)."""
    box = _box()
    top = next(r.plane for r in planar_faces(box) if r.plane.z_dir.Z > 0.5)
    body = bore_hole(
        box, top, (8.0, 8.0, 10.0), diameter_mm, through_all=True, depth_mm=None
    )
    sig = next(r.signature for r in planar_faces(body) if r.signature.normal.z > 0.5)
    return sig, body


def test_sibling_face_reference_survives_a_neighbours_diameter_edit() -> None:
    """FINDINGS #3: editing hole A's diameter shifts the shared top face's area &
    centroid but NOT its supporting plane, so a sibling hole B on the same face
    STILL resolves. The exact edit-A-then-B-resolves scenario, at the resolver.

    BEFORE (strict signature match): the sibling reference is orphaned
    (``subshape_unresolved``). AFTER (resilient coplanar re-match): it resolves to
    the same top plane."""
    # Hole B was picked against the top face AFTER hole A(Ø6) was drilled.
    sig_b, body6 = _drilled_top(6.0)
    # Initial build: B's stored signature resolves against the Ø6 body (strict).
    plane6 = resolve_face_plane(body6, sig_b, 0.0)
    assert tuple(plane6.origin)[2] == pytest.approx(10.0, abs=TOL)

    # EDIT hole A: Ø6 -> Ø8. The shared top face's area and centroid both move.
    sig_a8, body8 = _drilled_top(8.0)
    # The strict matcher (old behaviour) now FAILS on the drifted area/centroid ...
    assert not planar_signatures_match(sig_a8, sig_b)
    # ... but the strongest invariant (normal + supporting plane) is unchanged ...
    assert coplanar_signatures_match(sig_a8, sig_b)
    # ... so the sibling reference resolves to the same top plane (no orphaning).
    plane8 = resolve_face_plane(body8, sig_b, 0.0)
    assert tuple(plane8.z_dir) == pytest.approx((0.0, 0.0, 1.0), abs=TOL)
    assert tuple(plane8.origin)[2] == pytest.approx(10.0, abs=TOL)


def test_resilient_rematch_does_not_move_the_resolved_origin() -> None:
    """The resilience must not silently TRANSLATE the reference (audit regression A).

    The tier-2 re-match deliberately ignores the area-centroid POSITION — that is
    what an unrelated in-plane edit moves — so returning the matched record's own
    plane hands back an origin at the NEW centroid. On this fixture (a 40x40x10
    plate, off-centre hole at (8,8) going Ø6 -> Ø8) the shared top face's area
    centroid moves (-0.1439,-0.1439) -> (-0.2595,-0.2595): a 0.1156 mm shift in x
    AND y, i.e. every sketch/datum/mate seated on that face silently moves 0.163 mm
    when a NEIGHBOUR's diameter is edited. The z-only assertion above cannot see it
    (z is invariant by construction), so this asserts the full origin.

    The prior test's only visible symptom was resolution succeeding; this one pins
    WHERE it resolves to. Fails on the pre-fix resolver."""
    sig_b, body6 = _drilled_top(6.0)
    plane6 = resolve_face_plane(body6, sig_b, 0.0)
    _sig_a8, body8 = _drilled_top(8.0)
    plane8 = resolve_face_plane(body8, sig_b, 0.0)

    # Same face, same authored anchor: the in-plane origin must not move at all.
    assert tuple(plane8.origin) == pytest.approx(tuple(plane6.origin), abs=TOL)
    # And it IS the stored (picked) centroid, snapped onto the supporting plane.
    stored = (sig_b.centroid.x, sig_b.centroid.y, sig_b.centroid.z)
    assert tuple(plane8.origin) == pytest.approx(stored, abs=TOL)
    # The basis is unchanged too (orientation comes from the matched face).
    assert tuple(plane8.x_dir) == pytest.approx(tuple(plane6.x_dir), abs=TOL)
    assert tuple(plane8.z_dir) == pytest.approx(tuple(plane6.z_dir), abs=TOL)


def test_resilient_rematch_offset_applies_to_the_anchored_origin() -> None:
    """An offset datum on a resiliently re-matched face offsets the ANCHORED
    origin along the normal — the offset composes with the anchor, so an
    offset sketch does not re-acquire the drift the anchor removed."""
    sig_b, _body6 = _drilled_top(6.0)
    _sig_a8, body8 = _drilled_top(8.0)
    plane = resolve_face_plane(body8, sig_b, 5.0)
    offset_origin = (sig_b.centroid.x, sig_b.centroid.y, 15.0)
    assert tuple(plane.origin) == pytest.approx(offset_origin, abs=TOL)


def test_resilient_rematch_still_fails_honestly_when_the_plane_is_gone() -> None:
    """The resilient tier does NOT paper over a genuinely-missing face: a signature
    whose supporting plane exists on NO face of the body is still an honest
    ``subshape_unresolved`` (best-effort, not a guess — §7.3)."""
    gone = PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=0.0, y=0.0, z=42.0),  # +Z plane at z=42: no such face
        area_mm2=123.0,
    )
    with pytest.raises(SubshapeUnresolvedError):
        resolve_face_plane(_box(), gone, 0.0)


# --- tier 3: the face's PLANE MOVED (QA-2, topological-naming.md §12) ------------


def _plate(thickness: float) -> Solid:
    """A 60x40 plate of *thickness*, corner at the origin — the QA-2 bracket base."""
    return Solid.make_box(60.0, 40.0, thickness)


def _plate_top_signature(thickness: float) -> PlanarFaceSignature:
    """The analytic +Z top-face signature of :func:`_plate` (area 2400)."""
    return PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=30.0, y=20.0, z=thickness),
        area_mm2=2400.0,
    )


def test_a_face_reference_survives_the_plane_being_TRANSLATED() -> None:
    """THE QA-2 gate at the resolver. Retyping a plate's thickness 10 -> 16 moves
    the top face 6 mm along its own normal without changing anything ABOUT it —
    same area, same +Z normal, same (x,y) outline. Both earlier tiers pin the
    plane, so the reference was orphaned (`subshape_unresolved`) and every feature
    on that face stranded. Tier 3 resolves it, at the face's NEW plane."""
    stored = _plate_top_signature(10.0)
    thicker = planar_faces(_plate(16.0))
    current = next(r.signature for r in thicker if r.signature.normal.z > 0.5)

    # Neither shipped tier can see it: both require the supporting plane to hold.
    assert not planar_signatures_match(current, stored)
    assert not coplanar_signatures_match(current, stored)
    # The translated tier does, and the resolved plane sits at z=16.
    assert translated_signatures_match(current, stored)
    plane = resolve_face_plane(_plate(16.0), stored, 0.0)
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, 1.0), abs=TOL)
    assert tuple(plane.origin)[2] == pytest.approx(16.0, abs=TOL)


def test_a_translated_face_resolves_ON_the_face_not_at_the_stale_plane() -> None:
    """Where it resolves to, not just that it resolves (the audit-regression-A
    lesson applied to tier 3). The stored centroid sits at the OLD z, which after the
    edit is a point inside the solid; the resolver projects it onto the matched
    supporting plane, so the returned origin is the same in-plane station at the
    face's NEW place. A drill started at the stale plane would cut a blind pocket
    from mid-material instead of a through hole."""
    stored = _plate_top_signature(10.0)
    plane = resolve_face_plane(_plate(16.0), stored, 0.0)
    assert tuple(plane.origin) == pytest.approx((30.0, 20.0, 16.0), abs=TOL)
    # ... and an offset datum on that face offsets from the NEW plane, not the old.
    offset = resolve_face_plane(_plate(16.0), stored, 5.0)
    assert tuple(offset.origin) == pytest.approx((30.0, 20.0, 21.0), abs=TOL)


def test_a_translated_match_is_not_bounded_by_how_far_the_plane_moved() -> None:
    """Stated because it is a real consequence, not an oversight: tier 3 frees the
    offset ENTIRELY. A 10 mm plate retyped to 160 mm re-anchors exactly as one
    retyped to 16 mm. Bounding the move would need an epsilon with no geometric
    meaning (CLAUDE.md forbids ad-hoc ones) and would make resolution depend on the
    SIZE of the user's edit, which is not an invariant. The identity is carried by
    the normal sense, the area and the in-plane station instead."""
    stored = _plate_top_signature(10.0)
    plane = resolve_face_plane(_plate(160.0), stored, 0.0)
    assert tuple(plane.origin) == pytest.approx((30.0, 20.0, 160.0), abs=TOL)


def test_a_translated_face_reference_NEVER_lands_on_the_OPPOSITE_face() -> None:
    """The guard that makes freeing the offset safe. A plate's bottom face has the
    IDENTICAL area and the IDENTICAL in-plane centroid as its top face — the two
    differ only in the quantity tier 3 just freed and in the SENSE of the normal. So
    a hole drilled in the top of a plate must not re-anchor onto the bottom when the
    plate is thickened, which would drill from the wrong side."""
    top = _plate_top_signature(10.0)
    bottom = next(
        r.signature for r in planar_faces(_plate(16.0)) if r.signature.normal.z < -0.5
    )
    assert bottom.area_mm2 == pytest.approx(top.area_mm2, abs=TOL)
    assert (bottom.centroid.x, bottom.centroid.y) == pytest.approx(
        (top.centroid.x, top.centroid.y), abs=TOL
    )
    assert not translated_signatures_match(bottom, top)
    # And the resolved plane is the top one, outward +Z — never the -Z twin.
    plane = resolve_face_plane(_plate(16.0), top, 0.0)
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, 1.0), abs=TOL)


def test_a_translated_match_still_requires_the_SAME_FACE_shape_and_station() -> None:
    """The other two guards, so tier 3 cannot drift onto a different parallel face.
    A parallel face of a different AREA (a step, a boss top, a pocket floor) and one
    of the same area at a different in-plane STATION are both refused — the offset
    is free, nothing else is."""
    stored = _plate_top_signature(10.0)
    bigger = PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=30.0, y=20.0, z=16.0),
        area_mm2=2400.0 * 1.01,
    )
    moved = PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=45.0, y=20.0, z=16.0),  # same face, shifted 15 mm in-plane
        area_mm2=2400.0,
    )
    assert not translated_signatures_match(bigger, stored)
    assert not translated_signatures_match(moved, stored)


def test_two_stacked_congruent_faces_are_ambiguous_not_a_nearest_guess() -> None:
    """Refuse to guess (§7.2) rather than prefer the nearest plane. Two same-facing
    faces of equal area at the same in-plane station (here a plate with a second
    plate stacked on it, both 60x40) are equally valid translated re-anchors; the
    resolver must error instead of picking one, because "nearest along the normal"
    is right for a small edit and silently wrong for a large one."""
    lower = _plate(10.0)
    upper = _plate(6.0).translate((0.0, 0.0, 20.0))
    # A two-solid compound (the multi-body §MB-0 shape), so the body genuinely
    # carries two +Z faces of equal area at the same station — z=10 and z=26.
    stacked = Compound([lower, upper])
    stored = _plate_top_signature(4.0)  # neither plane — forces tier 3
    with pytest.raises(SubshapeAmbiguousError):
        resolve_face_plane(stacked, stored, 0.0)


def test_a_face_that_moved_AND_GREW_stays_an_honest_error() -> None:
    """The limit that SURVIVES tier 4 (§12a honest limits). Thickening the plate and
    enlarging it in x moves the plane AND changes the face's OUTER boundary — so
    even the outer-boundary tier has nothing invariant left to hold onto, and the
    area band refuses it (the grown top has no interior boundaries at all, so the
    band collapses to ``stored == outer``: 2400 is not 3200). Honest error, and the
    conservative direction on purpose."""
    stored = _plate_top_signature(10.0)
    grown = Solid.make_box(80.0, 40.0, 16.0)
    with pytest.raises(SubshapeUnresolvedError):
        resolve_face_plane(grown, stored, 0.0)


# --- tier 4: the plane MOVED and the boundary CHANGED (M17, §12a) ----------------

#: The M17 bracket base — a 100x40 plate with a Ø30 central bore at (50, 20) and two
#: mounting holes at (18, 20) and (82, 20). Every number below is analytic, so the
#: fixtures state hand-derived signatures rather than recording the kernel's output.
_PLATE_W, _PLATE_H = 100.0, 40.0
_BORE_R, _HOLE_B_R = 15.0, 3.3
_BORE_XY, _HOLE_A_XY, _HOLE_B_XY = (50.0, 20.0), (18.0, 20.0), (82.0, 20.0)


def _m17_plate(thickness: float, hole_a_radius: float) -> BodyShape:
    """The bracket at *thickness* with its first mounting hole at *hole_a_radius*.

    Drilled through the product's own :func:`bore_hole`, not a raw boolean, so the
    fixture is the body the feature path builds."""
    plate: BodyShape = Solid.make_box(_PLATE_W, _PLATE_H, thickness)
    for (x, y), radius in (
        (_BORE_XY, _BORE_R),
        (_HOLE_A_XY, hole_a_radius),
        (_HOLE_B_XY, _HOLE_B_R),
    ):
        top = next(r.plane for r in planar_faces(plate) if r.plane.z_dir.Z > 0.5)
        plate = bore_hole(
            plate,
            top,
            (x, y, thickness),
            radius * 2.0,
            through_all=True,
            depth_mm=None,
        )
    return plate


def _m17_stored_signature() -> PlanarFaceSignature:
    """Hole2's face signature as the DOCUMENT stored it: the top face at z = 10,
    described with the bore cut and Hole1 still at its original Ø6.6.

    Both of its varying fields are functions of what had been cut into the face at
    the moment of the pick, which is the defect M17 is about — after Hole1 is
    retyped to Ø7 and the plate to 14 mm, neither field describes any face of the
    current body."""
    bored = _PLATE_W * _PLATE_H - math.pi * _BORE_R**2
    hole_a_old = math.pi * _HOLE_B_R**2  # Hole1 was Ø6.6 too, before the edit
    area = bored - hole_a_old
    centroid_x = (bored * 50.0 - hole_a_old * _HOLE_A_XY[0]) / area
    return PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=centroid_x, y=20.0, z=10.0),
        area_mm2=area,
    )


def _top_record(body: BodyShape) -> PlanarFaceRecord:
    return next(r for r in planar_faces(body) if r.signature.normal.z > 0.5)


def test_a_face_reference_survives_the_plane_MOVING_AND_the_boundary_CHANGING() -> None:
    """THE M17 gate at the resolver. Two ordinary edits — Hole1 Ø6.6 → 7, then the
    plate 10 → 14 mm — leave Hole2's stored signature wrong in BOTH of its varying
    fields at once, which is the state any face carrying more than one feature ends
    up in. Each edit alone is absorbed (tier 2 for the diameter, tier 3 for the
    thickness); together they defeated all three tiers and stranded 4 of 11 features
    on the audit's bracket. Tier 4 resolves it on the face's OUTER boundary, the one
    invariant an interior hole edit cannot touch."""
    stored = _m17_stored_signature()
    revised = _m17_plate(14.0, 3.5)
    record = _top_record(revised)

    # Not one of the three shipped tiers can see it.
    assert not planar_signatures_match(record.signature, stored)
    assert not coplanar_signatures_match(record.signature, stored)
    assert not translated_signatures_match(record.signature, stored)
    # Tier 4 does — and it resolves at the face's NEW plane, at the stored station.
    assert enclosing_face_match(record, stored)
    plane = resolve_face_plane(revised, stored, 0.0)
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, 1.0), abs=TOL)
    assert tuple(plane.origin) == pytest.approx(
        (stored.centroid.x, stored.centroid.y, 14.0), abs=TOL
    )


def test_the_tier4_anchor_point_is_not_even_ON_the_face() -> None:
    """Why the anchor is the OUTER boundary and not the face. The stored centroid is
    an AREA centroid, and on a plate with a central bore it lands INSIDE that bore —
    a point the face does not contain. A containment test against the face itself
    would reject the very case tier 4 exists for; against the outer region it is
    comfortably inside."""
    stored = _m17_stored_signature()
    record = _top_record(_m17_plate(14.0, 3.5))
    on_plane = (stored.centroid.x, stored.centroid.y, 14.0)
    assert not record.face.is_inside(on_plane, tolerance=CENTROID_TOL_MM)
    assert enclosing_face_match(record, stored)


def test_a_tier4_reference_NEVER_lands_on_the_OPPOSITE_face() -> None:
    """§12's guard 1, still load-bearing with three of the four stored quantities
    freed: a plate's bottom face encloses the IDENTICAL outer region as its top and
    would pass the area band and the containment test alike. Only the sense of the
    normal separates them, so a hole drilled in the top can never re-anchor to the
    bottom."""
    stored = _m17_stored_signature()
    revised = _m17_plate(14.0, 3.5)
    bottom = next(r for r in planar_faces(revised) if r.signature.normal.z < -0.5)
    assert not enclosing_face_match(bottom, stored)
    assert tuple(resolve_face_plane(revised, stored, 0.0).z_dir) == pytest.approx(
        (0.0, 0.0, 1.0), abs=TOL
    )


def test_a_VANISHED_face_is_still_an_honest_error_under_tier4() -> None:
    """The guard that cost the first draft of tier 4 its correctness. Delete the boss
    a reference was picked on and the plate top underneath it contains the stored
    point and is larger — so a tier that only checked containment would silently
    re-anchor the reference onto the plate, replacing a visible failure with wrong
    geometry. The area band's LOWER end refuses it: the plate top's 775 mm² of
    interior holes cannot account for a 2825 mm² difference."""
    boss_top = PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=30.0, y=20.0, z=15.0),
        area_mm2=400.0,  # a 20x20 boss top, now deleted
    )
    without_the_boss = _m17_plate(14.0, 3.3)
    record = _top_record(without_the_boss)
    assert record.face.is_inside((30.0, 20.0, 14.0), tolerance=CENTROID_TOL_MM)
    assert not enclosing_face_match(record, boss_top)
    with pytest.raises(SubshapeUnresolvedError):
        resolve_face_plane(without_the_boss, boss_top, 0.0)


def test_tier4_refuses_a_stored_point_outside_the_outer_boundary() -> None:
    """The in-plane half of the anchor. An area inside the band is not enough — the
    stored centroid must land inside the candidate's outer boundary, so a reference
    authored somewhere else in the model does not adopt this face."""
    stored = _m17_stored_signature()
    elsewhere = PlanarFaceSignature(
        normal=stored.normal,
        centroid=Vec3(x=250.0, y=20.0, z=10.0),  # 150 mm clear of the plate
        area_mm2=stored.area_mm2,
    )
    record = _top_record(_m17_plate(14.0, 3.5))
    assert enclosing_face_match(record, stored)  # the control
    assert not enclosing_face_match(record, elsewhere)


def test_the_tier4_area_band_is_derived_from_the_candidates_own_holes() -> None:
    """Both ends of the band, stated as numbers so the derivation is checkable. The
    candidate is the revised plate top: outer region 4000 mm^2, current area
    4000 - pi * (15^2 + 3.5^2 + 3.3^2) mm^2. Upper end = the outer region (the
    stored face was a subset of it); lower end = 2 * current - outer (the shrinkage
    must be
    attributable to the interior boundaries the candidate actually has). A stored
    area a hair outside either end is refused."""
    record = _top_record(_m17_plate(14.0, 3.5))
    outer = _PLATE_W * _PLATE_H
    current = outer - math.pi * (_BORE_R**2 + 3.5**2 + _HOLE_B_R**2)
    assert record.signature.area_mm2 == pytest.approx(current, abs=1e-9)
    lower = 2.0 * current - outer
    stored = _m17_stored_signature()
    assert lower < stored.area_mm2 < outer  # the M17 case sits inside the band

    def _with_area(area: float, centroid: Vec3 | None = None) -> PlanarFaceSignature:
        return PlanarFaceSignature(
            normal=stored.normal,
            centroid=centroid if centroid is not None else stored.centroid,
            area_mm2=area,
        )

    # The upper end is probed with the OUTER region's own centroid, because GEOM-4
    # now closes the case where the two disagree: a stored area equal to the outer
    # region's leaves nothing to displace the centroid, so `stored == outer` with
    # this fixture's off-centre M17 centroid describes a face that cannot exist and
    # is refused on that ground rather than by the band. Gated by name in
    # ``test_tier4b_refuses_a_full_area_signature_whose_centroid_contradicts_it``.
    at_outer = Vec3(x=50.0, y=20.0, z=10.0)
    assert enclosing_face_match(record, _with_area(outer, at_outer))
    assert enclosing_face_match(record, _with_area(lower))
    assert not enclosing_face_match(record, _with_area(outer * 1.001, at_outer))
    assert not enclosing_face_match(record, _with_area(lower - outer * 0.001))


def test_a_plain_face_with_nothing_cut_into_it_rescues_only_itself() -> None:
    """The band's degenerate case, and the reason a plain plate cannot swallow a
    reference. With no interior boundaries the band collapses to ``stored == outer``
    — there is nothing to attribute a difference to — so tier 4 adds exactly zero
    reach on an unmachined face."""
    plain = _top_record(Solid.make_box(_PLATE_W, _PLATE_H, 14.0))
    at_area = PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=50.0, y=20.0, z=10.0),
        area_mm2=_PLATE_W * _PLATE_H,
    )
    smaller = PlanarFaceSignature(
        normal=at_area.normal, centroid=at_area.centroid, area_mm2=3000.0
    )
    assert enclosing_face_match(plain, at_area)
    assert not enclosing_face_match(plain, smaller)


def test_two_tier4_candidates_are_ambiguous_not_a_smallest_region_guess() -> None:
    """Refuse to guess (§7.2), carried into tier 4. Two identical machined plates
    stacked in a compound both pass the normal, the band and the containment test
    for one stored signature; the resolver must error rather than prefer the nearer
    or the smaller."""
    stored = _m17_stored_signature()
    lower = _m17_plate(14.0, 3.5)
    upper = _m17_plate(14.0, 3.5).translate((0.0, 0.0, 40.0))
    stacked = Compound([lower, upper])
    with pytest.raises(SubshapeAmbiguousError):
        resolve_face_plane(stacked, stored, 0.0)


def test_tier4_is_never_consulted_when_an_earlier_tier_matches(
    monkeypatch: Any,
) -> None:
    """The ADDITIVE property (§12a guard 4), asserted rather than argued: tier 4 runs
    only on an empty result from tier 3, so no reference that resolves today can be
    re-targeted by it. A strict match and a translated match must both complete
    without the outer-boundary tier ever being asked."""
    calls: list[str] = []
    real = faces_module.enclosing_face_match

    def _spy(candidate: PlanarFaceRecord, target: PlanarFaceSignature) -> bool:
        calls.append("called")
        return real(candidate, target)

    monkeypatch.setattr(faces_module, "enclosing_face_match", _spy)
    resolve_face_plane(_box(), _top_face_signature(), 0.0)  # tier 1
    resolve_face_plane(_plate(16.0), _plate_top_signature(10.0), 0.0)  # tier 3
    assert calls == []
    # ... and it IS reached (so the spy is wired) when nothing above it matches.
    resolve_face_plane(_m17_plate(14.0, 3.5), _m17_stored_signature(), 0.0)
    assert calls != []


def test_two_matching_faces_is_subshape_ambiguous(monkeypatch: Any) -> None:
    """The defensive ambiguity branch (§7.2 — refuse to guess). Two distinct
    planar faces of a manifold solid cannot actually share a centroid, so face
    ambiguity is unreachable with real bodies today; this exercises the branch
    that becomes load-bearing for edge/vertex signatures (stage 2)."""
    target = _top_face_signature()
    twin = PlanarFaceRecord(
        index=0,
        signature=target,
        plane=resolve_face_plane(_box(), target, 0.0),
        face=planar_faces(_box())[0].face,
    )

    def _two_matching(_body: Solid) -> list[PlanarFaceRecord]:
        return [twin, twin]

    monkeypatch.setattr("geometry.kernel.faces.planar_faces", _two_matching)
    with pytest.raises(SubshapeAmbiguousError):
        resolve_face_plane(_box(), target, 0.0)


# --- tier 4a: the OUTER-WIRE invariants, compared not inferred (GEOM-3, §12b) -----
#
# The stored signature now carries three pure functions of the face's outer wire
# (`outer_area_mm2` / `outer_centroid` / `outer_perimeter_mm`), so tier 4 stops
# INFERRING a bound on the quantity it was missing and starts COMPARING it. These
# gates are in two halves, deliberately: the ones that prove the invariant really is
# invariant (so the rescue still works), and the ones that prove an honest error
# stays honest (so the rescue is not bought with silent wrong geometry).


def _vented_plate(
    thickness: float = 10.0, radius: float = 4.5, n: int = 8, width: float = 100.0
) -> BodyShape:
    """The GEOM-3 shape: a *width* square plate with an *n* x *n* grid of through
    holes — an ordinary grille or lightened web, not a contrived part.

    At the default 8x8 Ø9 in 100x100 the top face is 40.7 % open, which is where
    §12a's inferred band degenerates: its lower end ``2*current - outer`` falls to
    1857 mm^2, so it admits any stored face down to 18.6 % of the plate."""
    body: BodyShape = Solid.make_box(width, width, thickness)
    pitch = width / n
    for i in range(n):
        for j in range(n):
            top = next(r.plane for r in planar_faces(body) if r.plane.z_dir.Z > 0.5)
            body = bore_hole(
                body,
                top,
                (pitch * (i + 0.5), pitch * (j + 0.5), thickness),
                radius * 2.0,
                through_all=True,
                depth_mm=None,
            )
    return body


def _edge_holed_plate(radius: float, thickness: float = 10.0) -> BodyShape:
    """A 40x40 plate of *thickness* with ONE hole of *radius* 8 mm in from the -X rim.

    At r = 6 the hole spans x = 2..14 and is INTERIOR: the top face's outer wire is
    still the 40x40 square. At r = 10 it spans x = -2..18 and BREACHES the rim, which
    is GEOM-5's case — the edit stops being interior and the outer wire itself
    changes. The plate stays a single lump either way, so the difference under test is
    the boundary and nothing else."""
    plate: BodyShape = Solid.make_box(40.0, 40.0, thickness)
    top = next(r.plane for r in planar_faces(plate) if r.plane.z_dir.Z > 0.5)
    return bore_hole(
        plate,
        top,
        (8.0, 20.0, thickness),
        radius * 2.0,
        through_all=True,
        depth_mm=None,
    )


def _top_signature_of(body: BodyShape) -> PlanarFaceSignature:
    """The +Z face signature the PICK side would hand a client for *body* — the
    largest one, so a plate with a boss yields the plate top rather than the boss."""
    return max(
        (r.signature for r in planar_faces(body) if r.signature.normal.z > 0.5),
        key=lambda s: s.area_mm2,
    )


def _boss_top_signature(
    side_x: float, side_y: float, z_mm: float
) -> PlanarFaceSignature:
    """The signature a pick on the top of a *side_x* x *side_y* boss produces, taken
    from a REAL body so all six fields are the kernel's own rather than hand-typed.
    The boss is centred on (50, 50) — the vented plate's own centre — because a boss
    concentric with the plate under it is the case no centroid test can separate."""
    boss = Solid.make_box(side_x, side_y, 10.0).translate(
        (50.0 - side_x / 2.0, 50.0 - side_y / 2.0, z_mm - 10.0)
    )
    return _top_signature_of(boss)


def _outer(
    sig: PlanarFaceSignature,
) -> tuple[float, tuple[float, float, float], float]:
    """*sig*'s three outer-wire invariants, ASSERTING all three are present.

    The assertion is the point, not boilerplate: the fields are optional on the DTO
    (so a pre-§12b selector still validates), and a partial signature is refused by
    the matcher, so every test that reads them is also gating that the pick side
    emitted a complete set."""
    assert sig.outer_area_mm2 is not None
    assert sig.outer_centroid is not None
    assert sig.outer_perimeter_mm is not None
    return (
        sig.outer_area_mm2,
        (sig.outer_centroid.x, sig.outer_centroid.y, sig.outer_centroid.z),
        sig.outer_perimeter_mm,
    )


def _legacy(sig: PlanarFaceSignature) -> PlanarFaceSignature:
    """*sig* as a selector persisted BEFORE §12b — the three original fields only."""
    return PlanarFaceSignature(
        normal=sig.normal, centroid=sig.centroid, area_mm2=sig.area_mm2
    )


def test_the_outer_invariants_are_UNTOUCHED_by_any_interior_edit() -> None:
    """THE CLAIM §12b rests on, measured rather than argued. Tier 4a is only as good
    as "no interior edit changes the outer wire", so this drills a hole, enlarges it,
    moves it, adds a second and deletes one again — every edit that makes ``area_mm2``
    and ``centroid`` stale — and requires all three outer invariants to come back
    BIT-IDENTICAL, not merely within tolerance."""
    reference = _outer(_top_signature_of(Solid.make_box(100.0, 40.0, 10.0)))
    assert reference[0] == 4000.0
    assert reference[2] == 280.0

    def _drilled(holes: list[tuple[float, float, float]]) -> PlanarFaceSignature:
        body: BodyShape = Solid.make_box(100.0, 40.0, 10.0)
        for x, y, diameter in holes:
            top = next(r.plane for r in planar_faces(body) if r.plane.z_dir.Z > 0.5)
            body = bore_hole(
                body, top, (x, y, 10.0), diameter, through_all=True, depth_mm=None
            )
        return _top_signature_of(body)

    edits = {
        "one hole": [(30.0, 20.0, 6.6)],
        "the same hole enlarged": [(30.0, 20.0, 7.0)],
        "the same hole moved": [(35.0, 24.0, 7.0)],
        "a second hole added": [(35.0, 24.0, 7.0), (70.0, 12.0, 5.0)],
        "the first hole deleted": [(70.0, 12.0, 5.0)],
        "a central bore too": [(70.0, 12.0, 5.0), (50.0, 20.0, 30.0)],
    }
    stale: set[tuple[float, float]] = set()
    for label, holes in edits.items():
        sig = _drilled(holes)
        assert _outer(sig) == reference, label
        stale.add((sig.area_mm2, sig.centroid.x))
    # ... while the pair the OLD signature stored as identity moved every time. It has
    # to be the PAIR: moving a hole leaves the area untouched and shifts the centroid,
    # which is exactly why neither quantity alone is an identity.
    assert len(stale) == len(edits)
    assert len({area for area, _x in stale}) == len(edits) - 1


def test_a_deleted_boss_top_no_longer_swallows_a_reference_on_a_VENTED_plate() -> None:
    """THE GEOM-3 GATE, on the shape the code review measured. Place a sketch on a
    boss, delete the boss, and the plate underneath contains the stored point and is
    larger — so §12a's inferred band, whose width is twice what is currently cut out
    of the face, admitted it and re-anchored the sketch onto the plate. Silent wrong
    geometry replacing a visible failure, on a plate 40.7 % open: a grille, not a
    pathological part. The review's table was 70x70 / 60x60 / 50x50 all RESOLVING and
    only 40x40 staying honest. With the outer wire STORED there is nothing to infer —
    a boss top's outer region is its own side^2 and the plate's is 10000 mm^2 — so
    every one of them is refused."""
    plate = _vented_plate()
    record = next(r for r in planar_faces(plate) if r.signature.area_mm2 > 5000.0)
    outer = _outer(record.signature)[0]
    assert outer == 10000.0
    current = record.signature.area_mm2
    assert current == pytest.approx(10000.0 - 64.0 * math.pi * 4.5**2, abs=1e-9)
    # The band the review derived, reproduced: it reaches down to 18.6 % of the plate.
    assert 2.0 * current - outer == pytest.approx(1857.0, abs=0.1)

    for side in (70.0, 60.0, 50.0, 40.0):
        stored = _boss_top_signature(side, side, 15.0)
        assert _outer(stored)[0] == pytest.approx(side * side, abs=1e-9)
        assert not enclosing_face_match(record, stored), side
    with pytest.raises(SubshapeUnresolvedError):
        resolve_face_plane(plate, _boss_top_signature(70.0, 70.0, 15.0), 0.0)


def test_the_LEGACY_band_still_swallows_it_which_is_why_the_contract_changed() -> None:
    """The other half of the truth, gated so nobody has to take §12b's word for it.
    A selector persisted before the outer invariants existed carries only the three
    original numbers, so it MUST keep taking the inferred band — the geometry service
    is stateless and cannot upgrade a signature it does not own. The consequence is
    that GEOM-3 is fixed for selectors authored from now on and NOT for one saved
    yesterday, and the review's exact table is what those still get. Asserted here so
    the residual exposure is a fact in the suite rather than a caveat in a doc, and so
    a future change to the legacy path cannot pass unnoticed."""
    plate = _vented_plate()
    record = next(r for r in planar_faces(plate) if r.signature.area_mm2 > 5000.0)
    admitted = {
        side: enclosing_face_match(record, _legacy(_boss_top_signature(side, side, 15)))
        for side in (70.0, 60.0, 50.0, 40.0)
    }
    assert admitted == {70.0: True, 60.0: True, 50.0: True, 40.0: False}


def test_tier4a_rescues_the_M17_revision_that_tier4b_was_introduced_for() -> None:
    """The rescue must SURVIVE the contract change — a fix that restores the honest
    error by refusing everything would be no fix at all. The M17 bracket's top face
    is picked before either edit, the plate is thickened 10 -> 14 AND Hole1 widened
    Ø6.6 -> 7, and the reference still resolves, at the stored in-plane station on
    the face's new plane. The outer wire is what carries it: a 100x40 rectangle,
    4000 mm^2 / 280 mm about (50, 20), before and after."""
    stored = _top_signature_of(_m17_plate(10.0, 3.3))
    revised = _m17_plate(14.0, 3.5)
    record = _top_record(revised)

    stored_outer = _outer(stored)
    assert (stored_outer[0], stored_outer[2]) == (4000.0, 280.0)
    candidate_outer = _outer(record.signature)
    assert (candidate_outer[0], candidate_outer[2]) == (4000.0, 280.0)
    # Not one of the three shipped tiers can see it, exactly as in the §12a gate.
    assert not planar_signatures_match(record.signature, stored)
    assert not coplanar_signatures_match(record.signature, stored)
    assert not translated_signatures_match(record.signature, stored)
    assert enclosing_face_match(record, stored)

    plane = resolve_face_plane(revised, stored, 0.0)
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, 1.0), abs=TOL)
    assert tuple(plane.origin) == pytest.approx(
        (stored.centroid.x, stored.centroid.y, 14.0), abs=TOL
    )


def test_tier4a_refuses_the_same_outer_AREA_and_CENTROID_in_another_SHAPE() -> None:
    """Why the perimeter is stored and not just the area and the centroid. An 80x50
    boss top and a 100x40 plate top are both 4000 mm^2 about the same point, so a
    two-quantity fingerprint would let a deleted boss re-anchor onto the plate — the
    GEOM-3 defect one notch down. Their outer wires are 260 mm and 280 mm long."""
    plate = _top_record(Solid.make_box(100.0, 40.0, 14.0).translate((0.0, 0.0, 0.0)))
    boss = _boss_top_signature(80.0, 50.0, 25.0)
    # Shift the boss signature onto the plate's own centre so ONLY the shape differs.
    boss = PlanarFaceSignature(
        normal=boss.normal,
        centroid=Vec3(x=50.0, y=20.0, z=25.0),
        area_mm2=boss.area_mm2,
        outer_area_mm2=boss.outer_area_mm2,
        outer_centroid=Vec3(x=50.0, y=20.0, z=25.0),
        outer_perimeter_mm=boss.outer_perimeter_mm,
    )
    assert _outer(boss)[0] == pytest.approx(4000.0, abs=1e-9)
    assert _outer(plate.signature)[0] == pytest.approx(4000.0, abs=1e-9)
    assert _outer(boss)[2] == pytest.approx(260.0, abs=1e-9)
    assert _outer(plate.signature)[2] == pytest.approx(280.0, abs=1e-9)
    assert not enclosing_face_match(plate, boss)


def test_tier4a_refuses_the_same_outer_PERIMETER_and_CENTROID_at_another_AREA() -> None:
    """The mirror of the test above, and it exists because an ablation survived
    without it. Dropping the outer-AREA comparison altogether left every other gate
    green — the shapes those tests use differ in perimeter as well, so the area was
    never the discriminator anywhere. A 70x70 boss top and a 100x40 plate top have the
    SAME outer perimeter (280 mm) about the same point and differ only in area (4900
    against 4000 mm^2), which isolates it. Three invariants are claimed, so three have
    to be load-bearing on their own."""
    plate = _top_record(Solid.make_box(100.0, 40.0, 14.0))
    boss = _boss_top_signature(70.0, 70.0, 25.0)
    boss = PlanarFaceSignature(
        normal=boss.normal,
        centroid=Vec3(x=50.0, y=20.0, z=25.0),
        area_mm2=boss.area_mm2,
        outer_area_mm2=boss.outer_area_mm2,
        outer_centroid=Vec3(x=50.0, y=20.0, z=25.0),
        outer_perimeter_mm=boss.outer_perimeter_mm,
    )
    assert _outer(boss)[2] == pytest.approx(280.0, abs=1e-9)
    assert _outer(plate.signature)[2] == pytest.approx(280.0, abs=1e-9)
    assert _outer(boss)[0] == pytest.approx(4900.0, abs=1e-9)
    assert _outer(plate.signature)[0] == pytest.approx(4000.0, abs=1e-9)
    assert not enclosing_face_match(plate, boss)


def test_tier4a_pins_the_in_plane_station_while_freeing_the_offset() -> None:
    """The two halves of the centroid comparison, separately. A plate thickened by
    any amount still matches (the offset along the normal is free, unbounded, exactly
    as tier 3 frees it); the SAME outer wire parked somewhere else in the plane does
    not (a reference authored on another part of the model must not adopt this
    face)."""
    stored = _top_signature_of(Solid.make_box(100.0, 40.0, 10.0))
    for thickness in (14.0, 160.0):
        record = _top_record(Solid.make_box(100.0, 40.0, thickness))
        assert enclosing_face_match(record, stored), thickness
    shifted = _top_record(
        Solid.make_box(100.0, 40.0, 14.0).translate((250.0, 0.0, 0.0))
    )
    assert not enclosing_face_match(shifted, stored)


def test_tier4a_NEVER_lands_on_the_OPPOSITE_face() -> None:
    """§12's guard 1, unchanged and still the load-bearing one. A plate's bottom face
    encloses the IDENTICAL outer wire as its top — same area, same perimeter, same
    in-plane centroid — so the three new invariants separate them not at all. Only
    the sense of the normal does."""
    stored = _top_signature_of(_m17_plate(10.0, 3.3))
    revised = _m17_plate(14.0, 3.5)
    bottom = next(r for r in planar_faces(revised) if r.signature.normal.z < -0.5)
    assert _outer(bottom.signature)[0] == _outer(stored)[0]
    assert _outer(bottom.signature)[2] == _outer(stored)[2]
    assert not enclosing_face_match(bottom, stored)
    assert tuple(resolve_face_plane(revised, stored, 0.0).z_dir) == pytest.approx(
        (0.0, 0.0, 1.0), abs=TOL
    )


def test_a_PARTIAL_outer_signature_is_refused_rather_than_downgraded() -> None:
    """A signature carrying some but not all three outer fields is a bug, not a
    legacy selector. Falling back to the inferred band would be a downgrade path
    straight into the defect §12b closes, so each of the three partial shapes is
    refused outright — even though the same target with NO outer fields at all is
    accepted by the legacy band (asserted here as the control, so the test is about
    the partiality and not about the target)."""
    plate = _vented_plate()
    record = next(r for r in planar_faces(plate) if r.signature.area_mm2 > 5000.0)
    full = _boss_top_signature(70.0, 70.0, 15.0)
    assert enclosing_face_match(record, _legacy(full))  # the control
    for dropped in ("outer_area_mm2", "outer_centroid", "outer_perimeter_mm"):
        partial = full.model_copy(update={dropped: None})
        assert not enclosing_face_match(record, partial), dropped


def test_a_hole_that_BREACHES_the_outer_boundary_changes_it_and_fails_SAFE() -> None:
    """GEOM-5 — the honest limit most likely to be met in practice, and the one that
    makes "no interior edit can touch the outer wire" conditional. Open a lightening
    hole out until it reaches the rim (a scallop, an edge slot) and the edit stops
    being interior: the outer wire itself changes and the stored invariants no longer
    describe it. It fails SAFE — refused, not mis-resolved.

    The SCOPE of the limit is narrower than it first sounds, and measuring it is what
    made that clear: a breach on its own is absorbed by TIER 2, correctly, because the
    supporting plane has not moved and tier 2 exists for in-plane boundary changes.
    Tier 4 only gets the question when the plane moved too, so the fixture retypes the
    thickness as well — which is the same "both at once" combination §12a is about."""
    interior = _top_signature_of(_edge_holed_plate(6.0))
    assert _outer(interior)[0] == pytest.approx(1600.0, abs=1e-9)
    assert _outer(interior)[2] == pytest.approx(160.0, abs=1e-9)

    # A breach ALONE: the plane is untouched, so tier 2 resolves it and should.
    breached_only = _edge_holed_plate(10.0)  # spans x -2..18: it bites the rim
    assert tuple(resolve_face_plane(breached_only, interior, 0.0).origin) == (
        pytest.approx(interior.centroid.x, abs=TOL),
        pytest.approx(interior.centroid.y, abs=TOL),
        pytest.approx(10.0, abs=TOL),
    )

    # A breach AND a thickness retype: tier 4 is the tier in play, and it refuses.
    breached = _edge_holed_plate(10.0, thickness=14.0)
    record = next(r for r in planar_faces(breached) if r.signature.normal.z > 0.5)
    outer_area, _outer_centroid, outer_perimeter = _outer(record.signature)
    assert outer_area < 1600.0 - 1.0  # the outer REGION lost the scalloped bite
    assert outer_perimeter != pytest.approx(160.0, abs=1e-6)
    assert not enclosing_face_match(record, interior)
    with pytest.raises(SubshapeUnresolvedError):
        resolve_face_plane(breached, interior, 0.0)


def test_a_hole_free_face_IS_its_own_outer_region_bit_for_bit() -> None:
    """The shortcut that keeps the pick side cheap, asserted as an equality rather
    than assumed. A face with exactly one wire is the region that wire encloses, so
    :func:`outer_boundary_invariants` answers from the face's own area and centroid
    instead of building a region — and the two routes agree to the last bit, which is
    what makes the shortcut behaviour-neutral rather than merely close."""
    for record in planar_faces(Solid.make_box(50.0, 40.0, 10.0)):
        rebuilt = Face(record.face.outer_wire())
        area, centroid, _perimeter = _outer(record.signature)
        assert area == float(rebuilt.area)
        assert area == record.signature.area_mm2
        rebuilt_centroid = rebuilt.center(CenterOf.MASS)
        assert centroid == (
            rebuilt_centroid.X,
            rebuilt_centroid.Y,
            rebuilt_centroid.Z,
        )


def test_the_pick_side_emits_the_outer_invariants_for_every_planar_face() -> None:
    """The contract half: a client that picks a face gets a signature it can store,
    and every planar face carries all three fields (never a partial one, which the
    matcher would refuse). Holed and hole-free faces alike."""
    body = _m17_plate(10.0, 3.3)
    overlay = selection_overlay(body, 0.1)
    planar = [f.signature for f in overlay.faces if f.signature is not None]
    assert len(planar) == 6
    for signature in planar:
        _outer(signature)  # asserts all three are present on every planar face
    top = next(s for s in planar if s.normal.z > 0.5)
    top_area, _top_centroid, top_perimeter = _outer(top)
    assert top_area == pytest.approx(4000.0, abs=1e-9)
    assert top_perimeter == pytest.approx(280.0, abs=1e-9)
    # ... and the holed top face's OWN area is smaller, which is the whole point.
    assert top.area_mm2 < top_area


def test_tier4b_refuses_a_full_area_signature_whose_centroid_contradicts_it() -> None:
    """GEOM-4, on the legacy path. ``outer*C_outer = stored*C_stored +
    removed*C_removed`` leaves nothing to displace the centroid when the stored area
    already EQUALS the outer region's, so a plain 100x40 face claiming 4000 mm^2 with
    a centroid at (5, 3) describes no face that could exist. The inferred band tested
    only containment and accepted it; it now refuses. It does NOT touch the
    vented-plate case above — a boss and the plate under it share a centroid — so this
    is a strengthening, not the GEOM-3 fix."""
    plain = _top_record(Solid.make_box(100.0, 40.0, 14.0))
    honest = PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=50.0, y=20.0, z=10.0),
        area_mm2=4000.0,
    )
    bogus = PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=5.0, y=3.0, z=10.0),  # inside the region, but impossible
        area_mm2=4000.0,
    )
    assert plain.face.is_inside((5.0, 3.0, 14.0), tolerance=CENTROID_TOL_MM)
    assert enclosing_face_match(plain, honest)  # the control
    assert not enclosing_face_match(plain, bogus)


# --- same-enumeration guarantee (pick side == resolve side) ----------------------


def test_overlay_faces_match_the_resolver_enumeration() -> None:
    """The HEADLINE gate: the overlay's planar-face signatures are byte-for-byte
    the resolver's ``planar_faces`` enumeration, in the same order — a picked
    signature resolves to the SAME face (the measurement order-equality lesson,
    applied to faces)."""
    box = _box()
    overlay = selection_overlay(box, 0.1)
    records = planar_faces(box)

    overlay_planar = [f for f in overlay.faces if f.signature is not None]
    assert [f.index for f in overlay_planar] == [r.index for r in records]
    assert [f.signature for f in overlay_planar] == [r.signature for r in records]
    # every box face is planar → the overlay marks all pickable
    assert all(f.planar for f in overlay.faces)
    assert len(overlay.faces) == 6


def test_a_picked_overlay_signature_resolves_back_to_its_face() -> None:
    """Round-trip: pick a planar face's overlay signature, resolve it, and land
    on that face's plane — what the datum-on-face pick UI will do end to end."""
    box = _box()
    overlay = selection_overlay(box, 0.1)
    top = next(
        f.signature
        for f in overlay.faces
        if f.signature is not None and f.signature.normal.z > 0.5
    )
    assert top is not None
    plane = resolve_face_plane(box, top, 0.0)
    assert tuple(plane.origin) == pytest.approx((0.0, 0.0, 10.0), abs=TOL)


def test_face_signature_dto_shares_construction_with_planar_faces() -> None:
    """DRY: face_signature_dto (pick side) and planar_faces (resolve side) build
    the identical DTO for the same face."""
    box = _box()
    faces = box.faces()
    records = planar_faces(box)
    by_index = {r.index: r.signature for r in records}
    for index, face in enumerate(faces):
        dto = face_signature_dto(face)
        assert dto == by_index.get(index)
