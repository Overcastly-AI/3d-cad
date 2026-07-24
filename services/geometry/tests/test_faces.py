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
from build123d import Solid
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
    wrong plane — the face 'no longer exists after the rebuild' path (§5)."""
    stale = PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=1.0),
        centroid=Vec3(x=0.0, y=0.0, z=99.0),  # no face at z=99
        area_mm2=1600.0,
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
