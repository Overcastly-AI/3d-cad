"""Geometry-QA for SHELL-SEALED-DETERMINISM (1fda3e0, fixed by 8dcc120): two
sealed-Shell checks that test_shell_determinism does not make, each against a
number derived outside the kernel. Both failed at 1fda3e0 and pass at its
parent and at 8dcc120.

* A cavity that splits into THREE pockets (two bores across a plate). The
  builder's plates split in two. The analytic hollow is the plate minus the
  eroded plate: the box shrunk by t, minus each bore grown by t and clipped to
  the shrunk strip, over z in [t, H - t].
* The volume Loft reports for a sealed spline hollow is the volume its STEP
  file has. At 1fda3e0 the case-2 prism at t 0.5 re-imported 8.3e-6 from its
  polygon truth while Loft reported 1.84e-2 below it: the exported part was
  right and the mass properties were not.

A body the kernel cannot hollow may raise; it must never return a wrong solid.
"""

# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportPrivateUsage=false

import importlib.util
import math
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest
from build123d import Box, Cylinder, Edge, Face, Location, Solid, Vector, Wire, extrude
from geometry.kernel import export_step_bytes
from geometry.kernel.imports import import_step_solid
from geometry.kernel.properties import volume_properties
from geometry.kernel.shell import ShellError, shell_body

TESTS = Path(__file__).resolve().parent

#: Planar and cylindrical faces only, so the analytic value is exact. Every
#: bored plate that builds reads within 3e-12 of it.
ANALYTIC_TOL = 1e-6

#: The case-2 sealed hollow, Loft's reading against its STEP re-import, mm^3.
#: Arc (the parent, and 8dcc120) measured within 3.2e-5 at t 0.5 to 2 over 3
#: rebuilds; 1fda3e0 was 1.84e-2 apart at t 0.5 and 5.0e-4 at t 1.
STEP_AGREEMENT_TOL = 1e-4


@cache
def _qa() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "offset_qa_round1_sealed", TESTS / "test_offset_surface_qa.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- a cavity that splits into three pockets ---------------------------------

LENGTH, WIDTH, HEIGHT, BORE_R, BORE_XS, WALL = 60.0, 20.0, 10.0, 7.0, (20.0, 40.0), 2.0


def _disc_in_strip(radius: float, half_width: float) -> float:
    """Area of a disc of *radius* inside the strip |y| <= *half_width*."""
    if radius <= half_width:
        return math.pi * radius * radius

    def primitive(y: float) -> float:
        return y * math.sqrt(radius * radius - y * y) + radius * radius * math.asin(
            y / radius
        )

    return primitive(half_width) - primitive(-half_width)


def _two_bore_plate() -> Solid:
    body = (
        Box(LENGTH, WIDTH, HEIGHT)
        .solids()[0]
        .moved(Location((LENGTH / 2, WIDTH / 2, HEIGHT / 2)))
    )
    for x in BORE_XS:
        bore = Cylinder(BORE_R, 3 * HEIGHT).moved(Location((x, WIDTH / 2, HEIGHT / 2)))
        body = body.cut(bore).solids()[0]
    return body


def test_the_three_pocket_truth_is_the_hand_derivation() -> None:
    """Grown bores r 9 span y 1..19 across the shrunk strip 2..18 and x 11..29,
    31..49 inside 2..58, apart: three pockets. Each clipped disc is
    2 (8 sqrt 17 + 81 asin(8/9)) = 243.353 mm^2; the section 56*16 - 2*243.353
    = 409.294; the hollow 12000 - 980 pi - 6 * 409.294 = 6465.388 mm^3."""
    assert _disc_in_strip(9.0, 8.0) == pytest.approx(
        2 * (8 * math.sqrt(17) + 81 * math.asin(8 / 9)), rel=1e-15
    )
    assert _truth() == pytest.approx(6465.388, abs=1e-3)


def _truth() -> float:
    bores = len(BORE_XS)
    solid = LENGTH * WIDTH * HEIGHT - bores * math.pi * BORE_R**2 * HEIGHT
    section = (LENGTH - 2 * WALL) * (WIDTH - 2 * WALL) - bores * _disc_in_strip(
        BORE_R + WALL, WIDTH / 2 - WALL
    )
    return solid - section * (HEIGHT - 2 * WALL)


def test_a_three_pocket_cavity_is_its_analytic_hollow_or_refused() -> None:
    """At 1fda3e0 the Intersection join kept one pocket: 7923.277 mm^3 where
    6465.388 is right (+22.5%), 2 shells where there are 4. Arc raises
    ShellError, which is acceptable. A wrong solid is not."""
    try:
        body = shell_body(_two_bore_plate(), [], WALL)
    except ShellError:
        return
    assert volume_properties(body).volume == pytest.approx(_truth(), abs=ANALYTIC_TOL)
    assert len(body.shells()) == 4


# --- a sealed spline hollow reads what its STEP file reads -------------------


def _case2_prism() -> Solid:
    fit = tuple(_qa().CASE2_FIT)
    wire = Wire(
        [
            Edge.make_line((0, 0, 0), (40.0, 0, 0)),
            Edge.make_line((40.0, 0, 0), (40.0, fit[0][1], 0)),
            Edge.make_spline([Vector(x, y, 0) for x, y in fit]),
            Edge.make_line((0, fit[-1][1], 0), (0, 0, 0)),
        ]
    )
    return extrude(Face(wire), 20.0).solids()[0]


@pytest.mark.parametrize("wall", [0.5, 1.0])
def test_a_sealed_spline_hollow_reads_what_its_step_file_reads(wall: float) -> None:
    body = shell_body(_case2_prism(), [], wall)
    assert len(body.shells()) == 2
    reimported = import_step_solid(export_step_bytes(body).decode())
    assert len(reimported.shells()) == 2
    assert volume_properties(reimported).volume == pytest.approx(
        volume_properties(body).volume, abs=STEP_AGREEMENT_TOL
    )
