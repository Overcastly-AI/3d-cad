"""Datum-plane kernel math — offset (origin + chained) and midplane conventions.

Covers geometry.kernel.datum (docs/design/datum-planes.md §3a/§7/§7a): the one
offset rule both offset kinds share, and every documented midplane convention —
parallel (incl. anti-parallel outward face normals), identical/coplanar,
perpendicular (the documented normal-sign rule, not a guess), oblique
non-through-origin (the min-norm intersection origin), the flip rule, and the
deterministic basis (x_dir pinned from the normal, the on_face rule).

All expectations are ANALYTIC (hand-derived plane equations), asserted at the
documented kernel bound — never recorded output, never ad-hoc epsilons.
"""

import math

import pytest
from build123d import Plane
from geometry.kernel import build_datum_plane, midplane_between, offset_plane

#: Kernel linear tolerance (CLAUDE.md 1e-7) — a ceiling, not a fit; the
#: values below are exact double math, deviations are round-off only.
TOL = 1e-7

#: 1/sqrt(2) — the unit-bisector component of two perpendicular unit normals.
INV_SQRT2 = 1.0 / math.sqrt(2.0)


# --- offset_plane (the shared offset rule; chaining = composing it) ---------------


def test_offset_plane_slides_along_own_normal() -> None:
    plane = offset_plane(Plane.XY, 30.0, flip=False)
    assert tuple(plane.origin) == pytest.approx((0.0, 0.0, 30.0), abs=TOL)
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, 1.0), abs=TOL)
    assert tuple(plane.x_dir) == pytest.approx((1.0, 0.0, 0.0), abs=TOL)


def test_offset_plane_zero_is_the_parent() -> None:
    plane = offset_plane(Plane.XY, 0.0, flip=False)
    assert tuple(plane.origin) == pytest.approx(tuple(Plane.XY.origin), abs=TOL)
    assert tuple(plane.z_dir) == pytest.approx(tuple(Plane.XY.z_dir), abs=TOL)


def test_offset_plane_flip_negates_z_keeps_x() -> None:
    plane = offset_plane(Plane.XY, 30.0, flip=True)
    assert tuple(plane.origin) == pytest.approx((0.0, 0.0, 30.0), abs=TOL)
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, -1.0), abs=TOL)
    assert tuple(plane.x_dir) == pytest.approx((1.0, 0.0, 0.0), abs=TOL)


def test_chained_offsets_compose_to_the_analytic_composite() -> None:
    """origin XY -> +10 -> +20 is the XY+30 plane (datum-planes §7 chaining)."""
    a = build_datum_plane("XY", 10.0, False)
    b = offset_plane(a, 20.0, flip=False)
    assert tuple(b.origin) == pytest.approx((0.0, 0.0, 30.0), abs=TOL)
    assert tuple(b.z_dir) == pytest.approx((0.0, 0.0, 1.0), abs=TOL)


def test_chained_offset_from_a_flipped_parent_offsets_along_the_flipped_normal() -> (
    None
):
    """A chain reads its PARENT'S resolved normal: XY+30 flipped (normal -Z),
    then +5, lands at z = 25 with normal -Z — the composite the chain literally
    says, not the origin datum's frame."""
    parent = build_datum_plane("XY", 30.0, True)
    child = offset_plane(parent, 5.0, flip=False)
    assert tuple(child.origin) == pytest.approx((0.0, 0.0, 25.0), abs=TOL)
    assert tuple(child.z_dir) == pytest.approx((0.0, 0.0, -1.0), abs=TOL)


# --- midplane: parallel conventions ------------------------------------------------


def test_midplane_between_parallel_planes_is_the_analytic_midway_plane() -> None:
    """XY and XY+30 -> the z=15 plane; normal = side a's (+Z), x_dir = +X."""
    plane = midplane_between(Plane.XY, Plane.XY.offset(30.0), flip=False)
    assert tuple(plane.origin) == pytest.approx((0.0, 0.0, 15.0), abs=TOL)
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, 1.0), abs=TOL)
    assert tuple(plane.x_dir) == pytest.approx((1.0, 0.0, 0.0), abs=TOL)


def test_midplane_between_antiparallel_face_planes_bisects_the_slab() -> None:
    """The founder case: a box's OUTWARD top (+Z at z=20) and bottom (-Z at
    z=0) faces — anti-parallel normals — yield the z=10 horizontal midplane
    with side a's normal (+Z), never a degenerate zero normal."""
    top = Plane(origin=(20.0, 12.5, 20.0), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
    bottom = Plane(origin=(20.0, 12.5, 0.0), x_dir=(1, 0, 0), z_dir=(0, 0, -1))
    plane = midplane_between(top, bottom, flip=False)
    assert tuple(plane.origin) == pytest.approx((20.0, 12.5, 10.0), abs=TOL)
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, 1.0), abs=TOL)


def test_midplane_side_order_signs_the_parallel_normal() -> None:
    """The documented sign rule: swapping a and b of the anti-parallel pair
    keeps the same geometric plane but signs the normal by the NEW side a."""
    top = Plane(origin=(0.0, 0.0, 20.0), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
    bottom = Plane(origin=(0.0, 0.0, 0.0), x_dir=(1, 0, 0), z_dir=(0, 0, -1))
    plane = midplane_between(bottom, top, flip=False)
    assert tuple(plane.origin) == pytest.approx((0.0, 0.0, 10.0), abs=TOL)
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, -1.0), abs=TOL)


def test_midplane_of_identical_planes_is_the_plane_itself() -> None:
    """The degenerate case degenerates cleanly (datum-planes §7a): both sides
    the same plane -> that plane, canonical basis."""
    side = Plane.XY.offset(7.0)
    plane = midplane_between(side, side, flip=False)
    assert tuple(plane.origin) == pytest.approx((0.0, 0.0, 7.0), abs=TOL)
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, 1.0), abs=TOL)
    assert tuple(plane.x_dir) == pytest.approx((1.0, 0.0, 0.0), abs=TOL)


# --- midplane: angular conventions --------------------------------------------------


def test_midplane_between_perpendicular_planes_follows_the_sign_rule() -> None:
    """XY (normal +Z) and XZ (normal -Y, build123d) intersect along world X;
    of the two 45-degree bisectors the documented rule picks
    normalize(n_a + n_b) = (0, -1, 1)/sqrt(2) — deterministic, never a guess."""
    plane = midplane_between(Plane.XY, Plane.XZ, flip=False)
    assert tuple(plane.origin) == pytest.approx((0.0, 0.0, 0.0), abs=TOL)
    assert tuple(plane.z_dir) == pytest.approx((0.0, -INV_SQRT2, INV_SQRT2), abs=TOL)
    # basis rule: x_dir pinned from the normal (least-aligned world axis = X)
    assert tuple(plane.x_dir) == pytest.approx((1.0, 0.0, 0.0), abs=TOL)


def test_midplane_between_oblique_offset_planes_passes_through_their_line() -> None:
    """XY+10 (z=10, normal +Z) and YZ+5 (x=5, normal +X) meet along the line
    {x=5, z=10}; the bisector has normal (1,0,1)/sqrt(2) and the min-norm
    origin (5, 0, 10) — every value a hand-derived plane equation."""
    plane = midplane_between(Plane.XY.offset(10.0), Plane.YZ.offset(5.0), flip=False)
    assert tuple(plane.origin) == pytest.approx((5.0, 0.0, 10.0), abs=TOL)
    assert tuple(plane.z_dir) == pytest.approx((INV_SQRT2, 0.0, INV_SQRT2), abs=TOL)
    # the origin lies on BOTH input planes (it is on the intersection line)
    assert pytest.approx(10.0, abs=TOL) == plane.origin.Z
    assert pytest.approx(5.0, abs=TOL) == plane.origin.X


def test_midplane_flip_negates_the_normal_and_keeps_x_dir() -> None:
    """`flip` is the same rule as offset: z_dir negated, x_dir kept (sketch +u
    unchanged, +v flips) — deterministic_x_dir is sign-symmetric by design."""
    plane = midplane_between(Plane.XY, Plane.XY.offset(30.0), flip=True)
    unflipped = midplane_between(Plane.XY, Plane.XY.offset(30.0), flip=False)
    assert tuple(plane.origin) == pytest.approx((0.0, 0.0, 15.0), abs=TOL)
    assert tuple(plane.z_dir) == pytest.approx((0.0, 0.0, -1.0), abs=TOL)
    assert tuple(plane.x_dir) == pytest.approx(tuple(unflipped.x_dir), abs=TOL)


def test_midplane_is_deterministic() -> None:
    """Same inputs -> bitwise-identical plane (RESEARCH §9): pure double math,
    no iteration order, no kernel state."""
    args = (Plane.XY.offset(10.0), Plane.YZ.offset(5.0))
    first = midplane_between(*args, flip=False)
    second = midplane_between(*args, flip=False)
    assert tuple(first.origin) == tuple(second.origin)
    assert tuple(first.z_dir) == tuple(second.z_dir)
    assert tuple(first.x_dir) == tuple(second.x_dir)
