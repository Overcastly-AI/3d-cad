"""Geometry QA of the shell definition check (SHELL-WRONG-SOLID, 5fda139).

The builder's sweep (test_shell_walls.py) is bored plates, tubes, rods, spheres
and blocks. These are bodies unlike those, each against a truth that uses no
offset:

* a blind pocket in a block. Its cavity is the block shrunk by ``t`` less the
  pocket grown by ``t`` (a rounded box), in closed form below;
* a counterbored plate. Its cavity is the plate shrunk by ``t`` less the bore
  grown by ``t``, and the counterbore grown by ``t``: a cylinder of radius
  ``r + t``, a cylinder of radius ``r`` reaching ``t`` deeper, and the torus
  round the floor's rim. Built by booleans of primitives;
* an open-top tray with vertical and bottom edges rounded ``r`` (near ``t``), a
  box open on two faces, and a spline prism open at both ends, by hand.

OCCT's hollow returns a WRONG solid on three of them. Before 5fda139 all three
shipped. The check must refuse them, and must go on building the right shells
(measured 2026-09-30, geometry QA).
"""

# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

import math
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from build123d import (
    Axis,
    Box,
    BuildLine,
    BuildPart,
    BuildSketch,
    Compound,
    Cylinder,
    Face,
    Location,
    Plane,
    Polyline,
    Solid,
    Spline,
    Torus,
    extrude,
    make_face,
    revolve,
)
from geometry.kernel.properties import volume_properties
from geometry.kernel.shell import ShellError, ShellThicknessError, shell_body
from geometry.kernel.types import BodyShape
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepTools import BRepTools
from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
from OCP.gp import gp_Pnt2d
from OCP.TopAbs import TopAbs_State

#: Every face in the pocket and counterbore cases is a plane, cylinder, sphere or
#: torus; the shells that build read their truth to 1e-12 (2026-09-30). The
#: spline prism reads its hand truth to 1e-7.
VOLUME_REL = 1e-9
SPLINE_VOLUME_REL = 1e-6


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> Solid:
    return (
        Box(x1 - x0, y1 - y0, z1 - z0)
        .solids()[0]
        .moved(Location(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)))
    )


def _z_cylinder(radius: float, z0: float, z1: float, x: float, y: float) -> Solid:
    return Cylinder(radius, z1 - z0).solids()[0].moved(Location((x, y, (z0 + z1) / 2)))


def _volume(solid: BodyShape) -> float:
    return volume_properties(solid).volume


# --- the blind pocket: 40 x 30 x 20 block, s x s pocket d deep from the top ----


@dataclass(frozen=True)
class Pocket:
    x: float
    y: float
    side: float
    depth: float

    def body(self) -> Solid:
        half = self.side / 2
        x, y = self.x, self.y
        pocket = _box(x - half, x + half, y - half, y + half, 20 - self.depth, 50)
        return _box(0, 40, 0, 30, 0, 20).cut(pocket).solids()[0]

    def truth(self, t: float) -> float:
        """The shell's volume by hand. The cavity is the 40 - 2t x 30 - 2t x
        20 - 2t box less the pocket grown by t, which (inside that box) is a
        prism of rounded-square section s^2 + 4 s t + pi t^2 from the pocket
        floor to the box top, over a cap: the floor grown by a half ball,
        s^2 t + s pi t^2 + 2/3 pi t^3. The cap is dropped when it lies wholly
        below the box, and the prism clipped to it (the pocket must be at
        least t from each side wall)."""
        s, floor = self.side, 20 - self.depth
        prism = (s * s + 4 * s * t + math.pi * t * t) * (20 - t - max(floor, t))
        cap = (
            s * s * t + s * math.pi * t * t + 2 / 3 * math.pi * t**3
            if floor - t >= t
            else 0.0
        )
        assert floor - t >= t or floor <= t, "a partly clipped cap is not derived"
        cavity = (40 - 2 * t) * (30 - 2 * t) * (20 - 2 * t) - prism - cap
        return 40 * 30 * 20 - s * s * self.depth - cavity


def test_the_pocket_truth_is_the_hand_derivation() -> None:
    """One truth by the numbers: the centred 6 x 6 x 8 pocket at t 2 leaves a
    36 x 26 x 16 = 14976 mm^3 box less 96.566 x 6 of prism and 164.153 of cap,
    and the block is 24000 - 288."""
    prism = (36 + 48 + 4 * math.pi) * 6
    cap = 72 + 24 * math.pi + 16 / 3 * math.pi
    assert Pocket(20, 15, 6, 8).truth(2.0) == pytest.approx(
        23712 - (14976 - prism - cap), rel=1e-15
    )
    assert Pocket(20, 15, 6, 8).truth(2.0) == pytest.approx(9479.5516, abs=1e-4)


# --- the counterbored plate: 40 x 40 x 10, bore r 2.5, counterbore r 5 x 4 -----


def _counterbored_plate(x: float, y: float) -> Solid:
    return (
        _box(0, 40, 0, 40, 0, 10)
        .cut(_z_cylinder(2.5, -50, 50, x, y), _z_cylinder(5, 6, 50, x, y))
        .solids()[0]
    )


def _counterbore_truth(x: float, y: float, t: float) -> float:
    grown = [
        _z_cylinder(2.5 + t, -50, 50, x, y),
        _z_cylinder(5 + t, 6, 50, x, y),
        _z_cylinder(5, 6 - t, 50, x, y),
        Torus(5, t).solids()[0].moved(Location((x, y, 6))),
    ]
    cavity = _box(t, 40 - t, t, 40 - t, t, 10 - t).cut(*grown).solids()
    return _volume(_counterbored_plate(x, y)) - sum(_volume(c) for c in cavity)


# --- wrong solids OCCT returns, which the check must refuse -------------------


@dataclass(frozen=True)
class Wrong:
    name: str
    make: Callable[[], Solid]
    thickness: float
    truth: Callable[[], float]
    #: OCCT's raw hollow (Arc join), when it is the same on every rebuild.
    raw: float | None


WRONG = [
    # A 1 mm wall in a block with a pocket 2 mm from its side: OCCT keeps a
    # sliver of the cavity, 4.6 times the right volume.
    Wrong(
        "pocket-near-wall-t1",
        lambda: Pocket(5, 15, 6, 8).body(),
        1.0,
        lambda: Pocket(5, 15, 6, 8).truth(1.0),
        23213.0649,
    ),
    # A pocket 17 deep leaves a 3 mm floor, which a 3 mm wall fills: OCCT
    # returns 14206.04 (a 2.05 mm wall under the pocket) on most rebuilds and
    # an invalid 32569.96 on the rest. Truth 13871.84.
    Wrong(
        "deep-pocket-t3",
        lambda: Pocket(20, 15, 6, 17).body(),
        3.0,
        lambda: Pocket(20, 15, 6, 17).truth(3.0),
        None,
    ),
    # A counterbore 2 mm from two edges at t 3: OCCT drops the cavity along
    # them and returns 36% too much material.
    Wrong(
        "counterbore-in-corner-t3",
        lambda: _counterbored_plate(7, 7),
        3.0,
        lambda: _counterbore_truth(7, 7, 3.0),
        15568.0297,
    ),
]


@pytest.mark.parametrize("case", WRONG, ids=[case.name for case in WRONG])
def test_a_wrong_hollow_of_a_new_family_is_refused(case: Wrong) -> None:
    truth = case.truth()
    if case.raw is not None:
        (raw,) = case.make().hollow([], -case.thickness).solids()
        assert _volume(raw) == pytest.approx(case.raw, abs=1e-3), (
            "OCCT's raw hollow changed: re-derive whether this case still "
            "exercises the check"
        )
        assert abs(case.raw - truth) > 0.01 * truth
    with pytest.raises((ShellError, ShellThicknessError)):
        shell_body(case.make(), [], case.thickness)


# --- right shells of the same families, which must still build ----------------


def _top(body: Solid) -> Face:
    return max(body.faces(), key=lambda face: face.center().Z)


def _face_at(body: Solid, axis: str, value: float) -> Face:
    (face,) = [
        f
        for f in body.faces()
        if abs(getattr(f.center(), axis) - value) < 1e-6
        and abs(abs(getattr(f.normal_at(), axis)) - 1) < 1e-9
    ]
    return face


def _tray() -> Solid:
    """40 x 30 x 20, its vertical and bottom edges rounded r 3."""
    block = _box(0, 40, 0, 30, 0, 20)
    rounded = block.fillet(3.0, [e for e in block.edges() if e.center().Z < 20 - 1e-6])
    return rounded.solids()[0]


def _tray_truth(t: float) -> float:
    """The tray is the base a x b rectangle (a = 34, b = 24, at z = 3) swept up
    to 20 and grown by 3 below; its open-top shell leaves that grown by 3 - t:
    a rounded prism of section ab + 2(a + b)p + pi p^2 up 17 mm, over a cap
    ab p + (a + b) pi p^2 / 2 + 2/3 pi p^3, with p = 3 - t."""
    a, b = 34.0, 24.0

    def cup(p: float) -> float:
        return (a * b + 2 * (a + b) * p + math.pi * p * p) * 17 + (
            a * b * p + (a + b) * math.pi * p * p / 2 + 2 / 3 * math.pi * p**3
        )

    return cup(3.0) - cup(3.0 - t)


def _spline_prism() -> Solid:
    points = [
        (20 * math.cos(2 * math.pi * k / 12), 12 * math.sin(2 * math.pi * k / 12))
        for k in range(12)
    ]
    with BuildPart() as part:
        with BuildSketch():
            with BuildLine():
                Spline(*points, periodic=True)
            make_face()
        extrude(amount=20)
    assert part.part is not None
    return part.part.solids()[0]


def _spline_truth(t: float) -> float:
    """Open at both ends, the cavity is the section's inner parallel set times
    20: A - P t + pi t^2 (Steiner; the section's smallest radius of curvature,
    7.2 mm, is above t). A is the prism's volume / 20: build123d's face area
    reads 754.29999 where the section is 754.28471 (shoelace, and OCCT's
    adaptive integration), which alone would put the truth 0.3 mm^3 off."""
    body = _spline_prism()
    (section,) = [f for f in body.faces() if f.center().Z < 1e-6]
    perimeter = sum(edge.length for edge in section.edges())
    area = _volume(body) / 20
    return _volume(body) - (area - perimeter * t + math.pi * t * t) * 20


@dataclass(frozen=True)
class Right:
    name: str
    make: Callable[[], Solid]
    opened: Callable[[Solid], list[Face]]
    thickness: float
    truth: Callable[[], float]
    rel: float = VOLUME_REL


RIGHT = [
    *(
        Right(
            f"pocket-t{t}",
            lambda: Pocket(20, 15, 6, 8).body(),
            lambda _: [],
            t,
            lambda t=t: Pocket(20, 15, 6, 8).truth(t),
        )
        for t in (1.0, 2.0, 3.0)
    ),
    *(
        Right(
            f"counterbore-t{t}",
            lambda: _counterbored_plate(20, 20),
            lambda _: [],
            t,
            lambda t=t: _counterbore_truth(20, 20, t),
        )
        for t in (1.0, 2.0)
    ),
    *(
        Right(
            f"tray-r3-open-t{t}",
            _tray,
            lambda body: [_top(body)],
            t,
            lambda t=t: _tray_truth(t),
        )
        for t in (2.9, 2.99)
    ),
    Right(
        "box-open-top-and-front-t2",
        lambda: _box(0, 40, 0, 30, 0, 20),
        lambda body: [_face_at(body, "Z", 20), _face_at(body, "Y", 0)],
        2.0,
        lambda: 24000 - 36 * 28 * 18,
    ),
    Right(
        "spline-prism-open-ends-t1",
        _spline_prism,
        lambda body: [_face_at(body, "Z", 20), _face_at(body, "Z", 0)],
        1.0,
        lambda: _spline_truth(1.0),
        SPLINE_VOLUME_REL,
    ),
]


@pytest.mark.parametrize("case", RIGHT, ids=[case.name for case in RIGHT])
def test_a_right_shell_of_a_new_family_still_builds(case: Right) -> None:
    body = case.make()
    shelled = shell_body(body, case.opened(body), case.thickness)
    assert _volume(shelled) == pytest.approx(case.truth(), rel=case.rel)


# The sealed cross-bored rod that rebuilt only half the time is in
# tests/test_shell_heal.py (SHELL-HEAL-NONDETERMINISM).


# --- a turned part: a wrong wall 5fda139 shipped (QA of 38f240f) ---------------


#: Spline profiles (r, z) of turned parts, revolved about z.
TURNED = {
    # r 7.38 at the base to 19.81 at z 20 and 10.38 at the top.
    "turned": [
        (7.38, 0.0),
        (19.18, 5.0),
        (15.69, 10.0),
        (17.9, 15.0),
        (19.81, 20.0),
        (19.13, 25.0),
        (10.38, 30.0),
    ],
    # QA rev14 (of 930a9af): at t 2 OCCT's hollow has a band of walls down to
    # 1.85 mm at z 3.6 to 3.9. 5fda139 refused it; 38f240f's 2 x 2 wall grid
    # (the whole side wall is one face) shipped 7077.370 mm^3.
    "rev14": [
        (13.16, 0.0),
        (17.0, 5.0),
        (11.62, 10.0),
        (14.35, 15.0),
        (15.69, 20.0),
        (10.87, 25.0),
        (6.95, 30.0),
    ],
}


def _turned(name: str = "turned") -> Solid:
    """A spline profile revolved: every side face is a surface of revolution."""
    profile = TURNED[name]
    height = profile[-1][1]
    with BuildPart() as part:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Spline(*profile)
                Polyline(profile[-1], (0, height), (0, 0), profile[0])
            make_face()
        revolve(axis=Axis.Z)
    assert part.part is not None
    return part.part.solids()[0]


def _cavity_walls(body: Solid, shelled: BodyShape, grid: int = 20) -> list[float]:
    """The wall at a grid of points on every face of every cavity shell (all
    shells but the outer, the largest): each point's distance to the body's
    faces by BRepExtrema. It uses no offset and none of the check. The distance
    is to a compound of faces: to a solid, BRepExtrema reads 0 inside it."""
    skin = Compound(body.faces()).wrapped
    shells = list(shelled.shells())
    outer = max(shells, key=lambda shell: shell.area)
    walls: list[float] = []
    for shell in shells:
        if shell is outer:
            continue
        for face in shell.faces():
            surface = BRepAdaptor_Surface(face.wrapped)
            umin, umax, vmin, vmax = BRepTools.UVBounds_s(face.wrapped)
            inside = BRepTopAdaptor_FClass2d(face.wrapped, 1e-9)
            for i in range(grid):
                u = umin + (i + 0.5) / grid * (umax - umin)
                for j in range(grid):
                    v = vmin + (j + 0.5) / grid * (vmax - vmin)
                    if inside.Perform(gp_Pnt2d(u, v)) != TopAbs_State.TopAbs_IN:
                        continue
                    point = BRepBuilderAPI_MakeVertex(surface.Value(u, v)).Vertex()
                    walls.append(BRepExtrema_DistShapeShape(point, skin).Value())
    return walls


@pytest.mark.parametrize(
    ("name", "thickness", "must_build"),
    [("turned", 1.0, True), ("turned", 1.5, False), ("rev14", 2.0, False)],
)
def test_a_sealed_turned_part_is_its_shell_or_refused(
    name: str, thickness: float, must_build: bool
) -> None:
    """At t 1.5 OCCT's hollow has cavity walls from 1.397 mm up (0.03 mm at z
    28.5 on a finer grid), and 5fda139 shipped it, 8017.894 mm^3, on 10 of 10
    rebuilds: none of its samples fell on the thin wall. 38f240f refuses it (a
    1.368 mm wall at x -6.995, y 17.99, z 2.392), 10 of 10. At t 1 the hollow
    is right, every sampled cavity wall 1.00000 mm, and must still ship."""
    body = _turned(name)
    try:
        shelled = shell_body(body, [], thickness)
    except (ShellError, ShellThicknessError):
        assert not must_build, "a right shell of a turned part was refused"
        return
    walls = _cavity_walls(body, shelled)
    assert len(walls) > 100
    assert min(walls) == pytest.approx(thickness, abs=1e-3)
    assert max(walls) == pytest.approx(thickness, abs=1e-3)
