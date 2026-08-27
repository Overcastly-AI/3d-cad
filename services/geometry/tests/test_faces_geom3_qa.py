"""GEOM-3 independent verification (geometry-qa, 2026-08-16) — the gates the
author's own suite does not contain.

``test_faces.py`` and ``test_faces_geom3_vented_plate.py`` were written by the
builder alongside the change. This file is the second opinion, and each test here
exists because it asks a question those files cannot answer about themselves:

* the DUAL-READ is verified by AUTHORING a selector the old way and by re-deriving
  §12a's admission rule INDEPENDENTLY inside the test, rather than by observing
  that pre-existing fixtures stayed green (a green fixture proves the fixture did
  not change; it does not prove the legacy RULE is unchanged);
* every tier-4a fixture in ``test_faces.py`` has a RECTANGULAR outer wire, whose
  area and length OCCT gets exactly. Tier 4a compares the perimeter against an
  ABSOLUTE 1e-6 mm bound, so a curved outer wire — a filleted plate, a round one —
  is where a false REFUSAL would first appear, and nothing covered one;
* the pick side has TWO routes to the outer invariants (a hole-free face is its
  own region; a holed one builds ``Face(wire)``), and an ordinary revision crosses
  between them when a hole is deleted. Only the same route on both sides was gated;
* and the claim that the three invariants are a FINGERPRINT of the outer wire is
  false — they are all invariant under a rigid motion of the wire about its own
  centroid, which is a limit §12b does not list. It is pinned here as a measured
  number so it cannot be lost.

docs/GEOMETRY-QA.md 2026-08-16 (geometry-qa) carries the evidence and the findings.
"""

import math

import pytest
from build123d import Axis, CenterOf, Compound, Face, Solid, chamfer, fillet
from geometry.kernel import planar_faces, resolve_face_plane
from geometry.kernel.faces import (
    AREA_REL_TOL,
    CENTROID_TOL_MM,
    NORMAL_MAX_ANGLE_TOL,
    PlanarFaceRecord,
    coplanar_signatures_match,
    enclosing_face_match,
    inferred_enclosing_match,
    outer_boundary_match,
    planar_signatures_match,
    translated_signatures_match,
)
from geometry.kernel.hole import bore_hole
from geometry.kernel.types import BodyShape
from py_kit.schemas.features import PlanarFaceSignature
from py_kit.schemas.geometry import Vec3

#: Kernel linear tolerance (CLAUDE.md 1e-7) — a ceiling, not a fit. The outer-wire
#: residuals measured below are 0.0 or ~1e-15, thirteen orders inside it.
TOL = 1e-7


def _drill(body: BodyShape, holes: list[tuple[float, float, float]]) -> BodyShape:
    """*holes* as ``(x, y, diameter)`` bored through the current +Z face."""
    for x, y, diameter in holes:
        top = next(r for r in planar_faces(body) if r.plane.z_dir.Z > 0.5)
        body = bore_hole(
            body,
            top.plane,
            (x, y, top.signature.centroid.z),
            diameter,
            through_all=True,
            depth_mm=None,
        )
    return body


def _top(body: BodyShape) -> PlanarFaceRecord:
    """The largest +Z planar face of *body* — the one a user picks."""
    return max(
        (r for r in planar_faces(body) if r.signature.normal.z > 0.5),
        key=lambda r: r.signature.area_mm2,
    )


def _as_authored_before_geom3(sig: PlanarFaceSignature) -> PlanarFaceSignature:
    """*sig* as a client persisted it BEFORE 2026-08-16: the three original fields.

    This is the whole point of the dual-read gate below — the selector is authored
    the OLD way here, in this file, and then handed to the NEW resolver."""
    return PlanarFaceSignature(
        normal=sig.normal, centroid=sig.centroid, area_mm2=sig.area_mm2
    )


def _m17_plate(thickness: float, hole_a_radius: float) -> BodyShape:
    """The M17 bracket: a 100x40 plate with a Ø30 bore and two mounting holes."""
    plate: BodyShape = Solid.make_box(100.0, 40.0, thickness)
    return _drill(
        plate,
        [(50.0, 20.0, 30.0), (20.0, 20.0, hole_a_radius * 2.0), (80.0, 20.0, 6.6)],
    )


# --- 1. the dual read, verified by authoring a selector the OLD way --------------


def test_a_selector_AUTHORED_the_old_way_still_resolves_against_the_new_resolver() -> (
    None
):
    """The backward-compatibility claim, executed rather than inferred.

    §12b's evidence for it is that three pre-existing artefacts stayed green. That
    shows nothing CHANGED in those artefacts; it does not show that a client which
    stores three fields today still gets an answer, because none of them authors a
    selector after the contract change and then asks the new code. This does: the
    pick side's own signature for the M17 top face, stripped to the three fields a
    pre-2026-08-16 document carries, resolved against the M17 combined revision
    (thickness 10 -> 14 AND Hole1 Ø6.6 -> 7) — the exact edit tier 4 exists for.

    The expected plane is hand-derived, not read back: tier 4's anchor rule
    (§12/§12a, unchanged by §12b) sits at the STORED area centroid projected onto
    the matched plane, so the origin is the stored (x, y) at the plate's new
    z = 14, with the outward +Z normal."""
    stored = _as_authored_before_geom3(_top(_m17_plate(10.0, 3.3)).signature)
    assert stored.outer_area_mm2 is None
    assert stored.outer_centroid is None
    assert stored.outer_perimeter_mm is None

    revised = _m17_plate(14.0, 3.5)
    record = _top(revised)

    # It really is tier 4, and really is the LEGACY leg of it: the three shipped
    # tiers all miss, the dual read routes to the inferred band, and the exact
    # comparison refuses (it has nothing to compare).
    assert not planar_signatures_match(record.signature, stored)
    assert not coplanar_signatures_match(record.signature, stored)
    assert not translated_signatures_match(record.signature, stored)
    assert inferred_enclosing_match(record, stored)
    assert not outer_boundary_match(record, stored)
    assert enclosing_face_match(record, stored)

    plane = resolve_face_plane(revised, stored, 0.0)
    assert tuple(plane.z_dir) == (0.0, 0.0, 1.0)
    assert abs(plane.origin.X - stored.centroid.x) <= TOL
    assert abs(plane.origin.Y - stored.centroid.y) <= TOL
    assert abs(plane.origin.Z - 14.0) <= TOL

    # ... and the NEW-style selector for the same pick lands on the same plane, so
    # the contract change is a widening of what can be stored, not of where a
    # reference ends up.
    modern = _top(_m17_plate(10.0, 3.3)).signature
    assert outer_boundary_match(record, modern)
    modern_plane = resolve_face_plane(revised, modern, 0.0)
    assert tuple(modern_plane.origin) == tuple(plane.origin)
    assert tuple(modern_plane.z_dir) == tuple(plane.z_dir)


def _independently_derived_legacy_rule(
    record: PlanarFaceRecord, target: PlanarFaceSignature
) -> bool:
    """§12a's admission rule, RE-DERIVED here from the design doc's prose.

    Deliberately not a call into ``inferred_enclosing_match`` and deliberately not
    a copy of its code: same-sense normal; the stored area inside
    ``[2*candidate - outer, outer]``; the stored point, projected onto the
    candidate's plane, inside the outer region; and GEOM-4's necessary condition
    that a stored area equal to the outer region's leaves the centroid nowhere to
    go. A second opinion from a different derivation is the only thing that catches
    a rule quietly changing under a suite that agrees with itself (CLAUDE.md)."""
    sig = record.signature
    dot = (
        sig.normal.x * target.normal.x
        + sig.normal.y * target.normal.y
        + sig.normal.z * target.normal.z
    )
    if 1.0 - dot > NORMAL_MAX_ANGLE_TOL:
        return False
    region = Face(record.face.outer_wire())  # the region, holes plugged
    outer_area = float(region.area)
    slack = max(abs(target.area_mm2), 1.0) * AREA_REL_TOL
    if target.area_mm2 > outer_area + slack:
        return False
    if target.area_mm2 < 2.0 * sig.area_mm2 - outer_area - slack:
        return False
    normal = (sig.normal.x, sig.normal.y, sig.normal.z)
    stored_point = (target.centroid.x, target.centroid.y, target.centroid.z)
    on_plane = (sig.centroid.x, sig.centroid.y, sig.centroid.z)
    gap = sum((stored_point[i] - on_plane[i]) * normal[i] for i in range(3))
    projected = tuple(stored_point[i] - gap * normal[i] for i in range(3))
    if abs(target.area_mm2 - outer_area) <= slack:
        centre = region.center(CenterOf.MASS)
        in_plane = [centre.X, centre.Y, centre.Z]
        along = sum(in_plane[i] * normal[i] for i in range(3))
        centre_projected = tuple(in_plane[i] - along * normal[i] for i in range(3))
        stored_along = sum(projected[i] * normal[i] for i in range(3))
        stored_in_plane = tuple(
            projected[i] - stored_along * normal[i] for i in range(3)
        )
        if math.dist(stored_in_plane, centre_projected) > CENTROID_TOL_MM:
            return False
    return bool(region.is_inside(projected, tolerance=CENTROID_TOL_MM))


def test_the_dual_read_gives_a_LEGACY_selector_the_12a_rule_and_nothing_else() -> None:
    """A sweep, against an independently-derived oracle rather than against the
    resolver's own arithmetic.

    Sixty-plus legacy signatures — the pick side's own output for six bodies,
    stripped, plus synthetic probes at both ends of the band and at the GEOM-4
    boundary — are put to every planar face of every body, and the four-tier entry
    must agree with :func:`_independently_derived_legacy_rule` on all of them. That
    is the property "a document saved yesterday resolves exactly as it did" reduces
    to, and it is stronger than any count of unchanged fixtures."""
    bodies: dict[str, BodyShape] = {
        "plain 100x40x14": Solid.make_box(100.0, 40.0, 14.0),
        "m17 t10": _m17_plate(10.0, 3.3),
        "m17 t14": _m17_plate(14.0, 3.5),
        "lightened": _drill(
            Solid.make_box(100.0, 100.0, 14.0),
            [(25.0, 25.0, 40.0), (75.0, 25.0, 40.0), (25.0, 75.0, 40.0)],
        ),
        "boss 70x70": Solid.make_box(70.0, 70.0, 10.0).translate((15.0, -15.0, 15.0)),
        "round r40": Solid.make_cylinder(40.0, 12.0),
    }
    targets: list[PlanarFaceSignature] = []
    for body in bodies.values():
        for record in planar_faces(body):
            targets.append(_as_authored_before_geom3(record.signature))
    reference = _as_authored_before_geom3(_top(bodies["m17 t10"]).signature)
    for factor in (0.2, 0.5, 0.9, 0.999999, 1.0, 1.000001, 1.3):
        targets.append(
            PlanarFaceSignature(
                normal=reference.normal,
                centroid=reference.centroid,
                area_mm2=reference.area_mm2 * factor,
            )
        )
    for area in (4000.0, 3999.0):
        for x, y in ((50.0, 20.0), (5.0, 3.0), (49.9999, 20.0)):
            targets.append(
                PlanarFaceSignature(
                    normal=reference.normal,
                    centroid=Vec3(x=x, y=y, z=10.0),
                    area_mm2=area,
                )
            )

    compared = 0
    admitted = 0
    for label, body in bodies.items():
        for record in planar_faces(body):
            for target in targets:
                compared += 1
                expected = _independently_derived_legacy_rule(record, target)
                assert enclosing_face_match(record, target) is expected, (
                    label,
                    record.index,
                    target.area_mm2,
                )
                admitted += int(expected)
    assert compared >= 1400  # measured 1440 — the sweep is real, not one lucky pair
    assert admitted > 0  # ... and it is not vacuously all-refusals


# --- 2. a CURVED outer wire, which no tier-4a fixture has ------------------------


def _filleted_plate(
    thickness: float, holes: list[tuple[float, float, float]]
) -> BodyShape:
    """A 100x60 plate with R8 corners — an outer wire of four lines and four ARCS."""
    box = Solid.make_box(100.0, 60.0, thickness)
    body: BodyShape = fillet(box.edges().filter_by(Axis.Z), radius=8.0)
    return _drill(body, holes)


def _chamfered_plate(
    thickness: float, holes: list[tuple[float, float, float]]
) -> BodyShape:
    box = Solid.make_box(100.0, 60.0, thickness)
    body: BodyShape = chamfer(box.edges().filter_by(Axis.Z), length=6.0)
    return _drill(body, holes)


def _round_plate(
    thickness: float, holes: list[tuple[float, float, float]]
) -> BodyShape:
    return _drill(Solid.make_cylinder(40.0, thickness), holes)


def test_tier4a_is_EXACT_on_a_curved_outer_wire_not_merely_within_tolerance() -> None:
    """Tier 4a compares the outer perimeter against an ABSOLUTE 1e-6 mm bound, and
    every fixture that exercises it has a straight-line outer wire, where OCCT's
    length and area are exact by construction. An arc is integrated, so a curved
    outer wire is where a residual would first appear — and a residual above the
    bound is a FALSE REFUSAL: a rescue the legacy band would have made and 4a
    loses, i.e. the fix regressing the case it was built to keep.

    Measured across a thickness retype plus an interior hole edit (the tier-4
    combination) on three curved outer wires: the residual is 0.0 on the area and
    0.0 on the perimeter, and at most 7.1e-15 mm on the in-plane centroid. The
    assertion is EQUALITY for the first two, because that is what was measured —
    stating it as a tolerance would hide a future drift into one."""
    cases = {
        "R8 filleted rectangle": (
            _filleted_plate(10.0, [(30.0, 30.0, 6.6)]),
            _filleted_plate(14.0, [(30.0, 30.0, 7.0)]),
        ),
        "C6 chamfered rectangle": (
            _chamfered_plate(10.0, [(30.0, 30.0, 6.6)]),
            _chamfered_plate(14.0, [(30.0, 30.0, 7.0)]),
        ),
        "round plate R40": (
            _round_plate(10.0, [(20.0, 0.0, 6.6)]),
            _round_plate(14.0, [(20.0, 0.0, 7.0)]),
        ),
    }
    for label, (before, after) in cases.items():
        stored = _top(before).signature
        record = _top(after)
        assert stored.outer_area_mm2 is not None
        assert stored.outer_perimeter_mm is not None
        assert stored.outer_centroid is not None
        assert record.signature.outer_area_mm2 is not None
        assert record.signature.outer_perimeter_mm is not None
        assert record.signature.outer_centroid is not None
        assert record.signature.outer_area_mm2 == stored.outer_area_mm2, label
        assert record.signature.outer_perimeter_mm == stored.outer_perimeter_mm, label
        assert (
            math.dist(
                (stored.outer_centroid.x, stored.outer_centroid.y),
                (record.signature.outer_centroid.x, record.signature.outer_centroid.y),
            )
            <= TOL
        ), label
        # ... and the face's OWN pair moved, so this is a real tier-4 question.
        assert record.signature.area_mm2 != stored.area_mm2, label
        assert outer_boundary_match(record, stored), label
        plane = resolve_face_plane(after, stored, 0.0)
        assert abs(plane.origin.Z - 14.0) <= TOL, label


def test_the_hole_free_SHORTCUT_and_the_region_BUILD_agree_across_a_DELETED_hole() -> (
    None
):
    """The pick side has two routes to the same three numbers — a face with one
    wire IS its own region, a holed one builds ``Face(outer_wire())`` — and §12b's
    own rejected-alternatives paragraph names "two routes that could disagree
    numerically" as the thing to avoid. The shortcut is nevertheless a second
    route, and the ordinary revision that crosses between them is DELETING the last
    hole in a face: the stored side went through the region build, the candidate
    side takes the shortcut.

    ``test_a_hole_free_face_IS_its_own_outer_region_bit_for_bit`` compares the two
    routes on the same box; this compares them ACROSS the edit, on a curved wire
    too, and requires the match to survive. Note the legacy band REFUSES this case
    (a deleted hole is exactly what its lower end is built to refuse), so tier 4a
    is strictly better here — which is worth having gated, because it is the
    clearest case where the contract change buys back a rescue rather than only
    removing a wrong one."""
    for label, before, after in (
        (
            "rectangle",
            Solid.make_box(100.0, 60.0, 10.0),
            Solid.make_box(100.0, 60.0, 14.0),
        ),
        ("R8 filleted", _filleted_plate(10.0, []), _filleted_plate(14.0, [])),
        ("round R40", _round_plate(10.0, []), _round_plate(14.0, [])),
    ):
        holed = _drill(before, [(20.0, 12.0, 6.6)])
        stored = _top(holed).signature
        record = _top(after)
        assert len(record.face.wires()) == 1, label  # the shortcut route
        assert len(_top(holed).face.wires()) == 2, label  # the region-build route
        assert record.signature.outer_area_mm2 == stored.outer_area_mm2, label
        assert record.signature.outer_perimeter_mm == stored.outer_perimeter_mm, label
        assert outer_boundary_match(record, stored), label
        assert not inferred_enclosing_match(
            record, _as_authored_before_geom3(stored)
        ), label


# --- 3. the honest limit §12b does not list --------------------------------------


def _adapter_bracket(with_top_flange: bool) -> BodyShape:
    """A transition bracket: a 100x40 bottom flange, a 30x30 column, and a 40x100
    TOP flange rotated 90 degrees — an ordinary adapter between two bolt patterns.

    Both flange faces enclose 4000 mm^2 behind a 280 mm wire about the SAME
    in-plane centroid, and the wires are 90 degrees apart."""
    lumps = [
        Solid.make_box(100.0, 40.0, 10.0).translate((-50.0, -20.0, 0.0)),
        Solid.make_box(30.0, 30.0, 30.0).translate((-15.0, -15.0, 10.0)),
    ]
    if with_top_flange:
        lumps.append(Solid.make_box(40.0, 100.0, 10.0).translate((-20.0, -50.0, 40.0)))
    body: BodyShape = lumps[0]
    for lump in lumps[1:]:
        fused = body + lump
        assert isinstance(fused, Solid | Compound)
        body = fused
    return body


def test_the_outer_invariant_TRIPLE_is_NOT_a_fingerprint_of_the_outer_wire() -> None:
    """A KNOWN LIMIT, pinned as a number so it cannot be lost (GEOM-QA finding,
    docs/GEOMETRY-QA.md 2026-08-16).

    §12b says tier 4a "narrows congruent from 'an area inside a band, somewhere
    inside the region' to 'the same outer wire, to tolerance'". It does not: an
    area, a perimeter and a centroid are all invariant under any RIGID MOTION of
    the wire about its own centroid, so a face and a 90-degree-rotated congruent
    face agree on all three EXACTLY. The perimeter separates 12b's own 80x50 boss
    from a 100x40 plate; it cannot separate a 40x100 flange from a 100x40 one.

    Measured on the adapter bracket above: the reference is picked on the top
    flange at z = 50 and the top flange is removed. The three shipped tiers all
    miss (the plane is gone; the surviving flange's own area is 3100, not 4000), so
    tier 4 takes the question and BOTH legs say yes — the reference silently drops
    **40 mm**. This is NOT a regression: the legacy band admits it too, so 12b
    neither introduced nor closed it. It is recorded because the section claims a
    fingerprint it does not have, and because the invariant set — not any fixture —
    is where this blind spot lives. The test goes red when a shape-sensitive
    invariant (a second area moment, a Hu-style descriptor) is added.
    """
    stored = max(
        (r for r in planar_faces(_adapter_bracket(True)) if r.signature.normal.z > 0.5),
        key=lambda r: r.signature.centroid.z,
    ).signature
    # Round-off from the union boolean, not a fit: 1e-9 is the same bound the
    # revision goldens document, and the residual measured here is 1e-12.
    assert stored.outer_area_mm2 == pytest.approx(4000.0, abs=1e-9)
    assert stored.outer_perimeter_mm == pytest.approx(280.0, abs=1e-9)
    assert stored.centroid.z == pytest.approx(50.0, abs=TOL)

    without = _adapter_bracket(False)
    survivor = next(
        r
        for r in planar_faces(without)
        if r.signature.normal.z > 0.5 and abs(r.signature.centroid.z - 10.0) <= TOL
    )
    # A different wire: 100 x 40 where the stored one is 40 x 100.
    assert survivor.signature.outer_area_mm2 == pytest.approx(
        stored.outer_area_mm2, abs=1e-9
    )
    assert survivor.signature.outer_perimeter_mm == pytest.approx(
        stored.outer_perimeter_mm, abs=1e-9
    )
    assert survivor.signature.area_mm2 == pytest.approx(3100.0, abs=1e-9)

    assert not planar_signatures_match(survivor.signature, stored)
    assert not coplanar_signatures_match(survivor.signature, stored)
    assert not translated_signatures_match(survivor.signature, stored)
    assert outer_boundary_match(survivor, stored)  # <- the limit
    assert inferred_enclosing_match(survivor, _as_authored_before_geom3(stored))

    plane = resolve_face_plane(without, stored, 0.0)
    assert abs(plane.origin.Z - 10.0) <= TOL
    assert abs((stored.centroid.z - plane.origin.Z) - 40.0) <= TOL
