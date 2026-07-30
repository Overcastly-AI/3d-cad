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

from typing import Any

import pytest
from build123d import Compound, Solid
from geometry.kernel import (
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    planar_faces,
    resolve_face_plane,
    selection_overlay,
)
from geometry.kernel.faces import (
    PlanarFaceRecord,
    coplanar_signatures_match,
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


def test_a_face_that_moved_AND_changed_shape_stays_an_honest_error() -> None:
    """The documented conservative limit: each tier frees exactly what its edit
    changes. An edit that BOTH translates the plane AND alters the face (thicken the
    plate and enlarge it in x) matches no tier, and inventing a match across two
    simultaneous changes is where a matcher starts guessing. Honest error."""
    stored = _plate_top_signature(10.0)
    grown = Solid.make_box(80.0, 40.0, 16.0)
    with pytest.raises(SubshapeUnresolvedError):
        resolve_face_plane(grown, stored, 0.0)


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
