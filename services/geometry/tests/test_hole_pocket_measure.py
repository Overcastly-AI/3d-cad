"""A blind hole's pocket check measures the pocket, not the body.

HOLE-BLIND-FALSE-DEEP: the check used to subtract two whole-body volumes and
hold the difference to 1e-6 of the analytic pocket. Volume integration error
scales with the BODY, so on a 60 000 mm^3 part whose faces are B-splines the
difference missed a Ø2.5 x 10 pocket by ~1.8 mm^3 and a valid hole was refused
``HOLE_TOO_DEEP``. The kernel now measures the material under the drill
directly (``tool ∩ body``), and allows a shortfall of the boolean's own
tolerance over the pocket's surface.

The hard-parts enclosure STEP is not in the repo, so the body here is a stand-in
for it: Ø8 x 31 bosses in a shelled, filleted box, put through
``BRepBuilderAPI_NurbsConvert`` so every face is a B-spline. Its placement plane
comes from the analytic twin, which occupies the same space.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false

import math
from functools import cache

import pytest
from build123d import Axis, Box, Cylinder, Plane, Solid, fillet, offset
from geometry.kernel.faces import planar_faces
from geometry.kernel.hole import (
    HoleTooDeepError,
    bore_hole,
    cut_counterbore,
    cut_countersink,
)
from geometry.kernel.lumps import lump_count
from geometry.kernel.properties import volume_properties
from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert

#: The enclosure half: a 120 x 80 x 34 box, R8 vertical and R3 floor fillets,
#: shelled 2.5 mm open at the top, a Ø8 x 31 boss standing on the floor in each
#: corner, and a 2.5 mm lip ring on the rim (36.5 mm overall, as the part).
WALL = 2.5
BOSS_H = 31.0
BOSS_TOP = WALL + BOSS_H
BOSS_AT = (50.0, 30.0)
BORE_D = 2.5


def _pocket(depth: float, diameter: float = BORE_D) -> float:
    return math.pi * (diameter / 2.0) ** 2 * depth


@cache
def _boss_part() -> tuple[Solid, Solid, Plane]:
    """``(analytic, bspline, boss_top_plane)`` for the enclosure stand-in."""
    outer = Box(120.0, 80.0, 34.0).translate((0.0, 0.0, 17.0))
    outer = fillet(outer.edges().filter_by(Axis.Z), 8.0)
    outer = fillet(outer.edges().group_by(Axis.Z)[0], 3.0)
    body = offset(outer, -WALL, openings=outer.faces().sort_by(Axis.Z)[-1])
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            at = (sx * BOSS_AT[0], sy * BOSS_AT[1], WALL + BOSS_H / 2.0)
            body = body + Cylinder(4.0, BOSS_H).translate(at)
    rim_z = 34.0 + WALL / 2.0
    lip_out = fillet(Box(116.0, 76.0, WALL).edges().filter_by(Axis.Z), 6.0)
    lip_in = fillet(Box(114.0, 74.0, WALL).edges().filter_by(Axis.Z), 5.0)
    analytic = (body + (lip_out - lip_in).translate((0.0, 0.0, rim_z))).solid()
    (top,) = [
        r.plane
        for r in planar_faces(analytic)
        if r.plane.z_dir.Z > 0.99
        and abs(r.plane.origin.Z - BOSS_TOP) < 1e-9
        and r.plane.origin.X > 0.0
        and r.plane.origin.Y > 0.0
    ]
    bspline = Solid(BRepBuilderAPI_NurbsConvert(analytic.wrapped, True).Shape())
    return analytic, bspline, top


def _boss_centre() -> tuple[float, float, float]:
    return (*BOSS_AT, BOSS_TOP)


def test_the_bspline_body_carries_the_volume_noise_that_tripped_the_old_check() -> None:
    """Precondition: the default (fixed-order) volume of the B-spline twin is off
    by far more than 1e-6 of a Ø2.5 x 10 pocket (4.9e-5 mm^3), so the old
    body-delta check could not have passed on it."""
    analytic, bspline, _ = _boss_part()
    noise = abs(float(bspline.volume) - float(analytic.volume))
    assert noise > 1e3 * 1e-6 * _pocket(10.0)


@pytest.mark.parametrize("depth", [10.0, 25.0, BOSS_TOP - 0.01])
def test_valid_blind_hole_in_a_bspline_boss_builds(depth: float) -> None:
    """The backlog case: Ø2.5 x 10 and x 25 on the Ø8 x 31 boss build, and so
    does a hole 0.01 mm short of the floor's underside. The removed material,
    measured as the drilled-out region itself, is the analytic pocket."""
    _, bspline, top = _boss_part()
    drilled = bore_hole(
        bspline, top, _boss_centre(), BORE_D, through_all=False, depth_mm=depth
    )
    assert drilled.is_valid
    assert lump_count(drilled) == 1
    removed = volume_properties(bspline).volume - volume_properties(drilled).volume
    # Adaptive integration of the two 61-face B-spline bodies agrees with the
    # analytic pocket to ~2e-4 mm^3; 1e-3 is still 49x below a 0.01-deep miss.
    assert removed == pytest.approx(_pocket(depth), abs=1e-3)


def test_the_analytic_twin_drills_the_same_hole() -> None:
    """Same placement on the analytic body removes exactly the analytic pocket,
    so the B-spline case above is the same hole, not a different one."""
    analytic, _, top = _boss_part()
    drilled = bore_hole(
        analytic, top, _boss_centre(), BORE_D, through_all=False, depth_mm=10.0
    )
    removed = float(analytic.volume) - float(drilled.volume)
    assert removed == pytest.approx(_pocket(10.0), abs=1e-9)


@pytest.mark.parametrize("depth", [BOSS_TOP + 0.001, BOSS_TOP + 5.0])
def test_bspline_blind_hole_through_the_floor_is_too_deep(depth: float) -> None:
    """A blind hole that breaks through the floor under the boss is still refused
    on the B-spline body, down to a 1 µm breakthrough."""
    _, bspline, top = _boss_part()
    with pytest.raises(HoleTooDeepError):
        bore_hole(
            bspline, top, _boss_centre(), BORE_D, through_all=False, depth_mm=depth
        )


def test_bspline_blind_hole_through_the_boss_wall_is_too_deep() -> None:
    """A bore 3 mm off the boss axis pokes 0.25 mm out of its Ø8 wall: refused."""
    _, bspline, top = _boss_part()
    with pytest.raises(HoleTooDeepError):
        bore_hole(
            bspline,
            top,
            (BOSS_AT[0] + 3.0, BOSS_AT[1], BOSS_TOP),
            BORE_D,
            through_all=False,
            depth_mm=10.0,
        )


def test_bspline_counterbore_and_countersink_build() -> None:
    """The recess checks share the pocket measurement, so they build on the
    B-spline boss too."""
    _, bspline, top = _boss_part()
    bored = bore_hole(
        bspline, top, _boss_centre(), BORE_D, through_all=False, depth_mm=10.0
    )
    cbored = cut_counterbore(
        bored,
        top,
        _boss_centre(),
        bore_diameter_mm=BORE_D,
        cbore_diameter_mm=5.0,
        cbore_depth_mm=2.0,
    )
    assert lump_count(cbored) == 1
    csunk = cut_countersink(
        bored,
        top,
        _boss_centre(),
        bore_diameter_mm=BORE_D,
        csink_diameter_mm=5.0,
        csink_angle_deg=90.0,
    )
    assert lump_count(csunk) == 1


def test_analytic_breakthrough_of_ten_microns_is_too_deep() -> None:
    """Not loosened: on an exact body a Ø10 blind hole 10.00001 deep in a 10 mm
    block misses 7.9e-4 mm^3, which the old 1e-6-of-pocket bound (7.9e-4) only
    just caught. The boolean-tolerance skin (1e-7 mm x 471 mm^2 = 4.7e-5 mm^3)
    refuses it with 17x to spare."""
    block = Solid.make_box(40.0, 25.0, 10.0)
    (top,) = [r.plane for r in planar_faces(block) if r.plane.z_dir.Z > 0.99]
    with pytest.raises(HoleTooDeepError):
        bore_hole(
            block, top, (20.0, 12.5, 10.0), 10.0, through_all=False, depth_mm=10.00001
        )
    drilled = bore_hole(
        block, top, (20.0, 12.5, 10.0), 10.0, through_all=False, depth_mm=10.0
    )
    assert float(block.volume) - float(drilled.volume) == pytest.approx(
        _pocket(10.0, 10.0), abs=1e-9
    )
