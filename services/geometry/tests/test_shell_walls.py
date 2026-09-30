"""A shell never ships a solid whose walls are not the thickness (SHELL-WRONG-SOLID).

OCCT's hollow returned one valid solid that removed material and was still the
wrong part: a plate whose cavity must split into two pockets kept one (5449.66
mm^3 where 4438.70 is true), and a tube whose 3 mm wall has no room for two
2 mm walls came back as a 75.40 mm^3 solid. :mod:`geometry.kernel.shell_walls`
now checks every result against the definition of a shell.

The sweep below is 173 bodies from the families the review swept: plates with
a centred, an offset and two holes, cross-bored plates, tubes, a rod with a
transverse bore, bored spheres and bored blocks, each over a range of
thicknesses. Before the check, 7 of them shipped a wrong solid. The truth comes
from neither offset join. Every body is a box, cylinder or sphere with
cylindrical bores, so its cavity (the points farther than ``t`` from the
boundary) is the shrunk body minus each bore grown by ``t``: an erosion of an
intersection is the intersection of the erosions, and eroding a bore's outside
dilates the bore. That is built by booleans of primitives. Each shell must raise
a typed error or read that volume, with one more shell than the cavity has
pockets.
"""

# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportPrivateUsage=false

import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from build123d import (
    Axis,
    Box,
    BuildLine,
    BuildPart,
    BuildSketch,
    Cone,
    Cylinder,
    Face,
    Line,
    Location,
    Solid,
    Sphere,
    Spline,
    extrude,
    fillet,
    make_face,
)
from geometry.kernel.properties import volume_properties
from geometry.kernel.shell import (
    ShellError,
    ShellThicknessError,
    _same_hollow,
    shell_body,
)
from geometry.kernel.shell_walls import WALL_TOL_MM, FaultKind, ShellDefinition
from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert

#: Every face here is a plane, cylinder or sphere, and both sides of each
#: comparison are integrated by the same rule. Bodies that build read the boolean
#: truth to within 1.4e-10 relative (rod-cross-bore-r6 at t 0.5, 2026-09-30).
VOLUME_REL = 1e-9


def _z_bore(radius: float, x: float = 0.0, y: float = 0.0) -> Solid:
    return Cylinder(radius, 200).solids()[0].moved(Location((x, y, 0)))


def _x_bore(radius: float, z: float = 0.0) -> Solid:
    return (
        Cylinder(radius, 200).solids()[0].rotate(Axis.Y, 90).moved(Location((0, 0, z)))
    )


def _cut(body: Solid, bores: list[Solid]) -> list[Solid]:
    return list(body.cut(*bores).solids()) if bores else [body]


@dataclass(frozen=True)
class Case:
    """A body, as an outer primitive minus bores, both for any grow ``g``: the
    body at g = 0, its cavity at g = t (outer shrunk by t, bores grown by t)."""

    name: str
    thickness: float
    outer: Callable[[float], Solid | None]
    bores: Callable[[float], list[Solid]]

    def body(self) -> Solid:
        outer = self.outer(0.0)
        assert outer is not None
        (solid,) = _cut(outer, self.bores(0.0))
        return solid

    def cavity(self) -> list[Solid]:
        outer = self.outer(self.thickness)
        return [] if outer is None else _cut(outer, self.bores(self.thickness))


def _box(x: float, y: float, z: float) -> Callable[[float], Solid | None]:
    def make(g: float) -> Solid | None:
        if min(x, y, z) <= 2 * g:
            return None
        return Box(x - 2 * g, y - 2 * g, z - 2 * g).solids()[0]

    return make


def _rod(radius: float, height: float) -> Callable[[float], Solid | None]:
    def make(g: float) -> Solid | None:
        if radius <= g or height <= 2 * g:
            return None
        return Cylinder(radius - g, height - 2 * g).solids()[0]

    return make


def _ball(radius: float) -> Callable[[float], Solid | None]:
    def make(g: float) -> Solid | None:
        return Sphere(radius - g).solids()[0] if radius > g else None

    return make


THICKNESSES = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)


def _cases() -> list[Case]:
    cases: list[Case] = []
    for r in (2.0, 4.0, 5.0, 6.0, 7.0, 7.5, 8.0, 8.5, 9.0):
        for t in THICKNESSES:
            cases.append(
                Case(
                    f"plate-hole-r{r}-t{t}",
                    t,
                    _box(40, 20, 10),
                    lambda g, r=r: [_z_bore(r + g)],
                )
            )
    for dy in (1.0, 2.5):
        for r in (5.0, 7.0):
            for t in THICKNESSES:
                cases.append(
                    Case(
                        f"plate-offset-hole-r{r}-y{dy}-t{t}",
                        t,
                        _box(40, 20, 10),
                        lambda g, r=r, dy=dy: [_z_bore(r + g, y=dy)],
                    )
                )
    for r in (3.0, 5.0, 7.0):
        for t in (0.5, 1.0, 1.5, 2.0, 3.0):
            cases.append(
                Case(
                    f"plate-two-holes-r{r}-t{t}",
                    t,
                    _box(60, 20, 10),
                    lambda g, r=r: [_z_bore(r + g, x=-10), _z_bore(r + g, x=10)],
                )
            )
    for rv, rh in ((3.0, 2.0), (5.0, 2.0), (3.0, 3.0)):
        for t in (0.5, 1.0, 1.5, 2.0):
            cases.append(
                Case(
                    f"plate-cross-bore-v{rv}-h{rh}-t{t}",
                    t,
                    _box(40, 20, 10),
                    lambda g, rv=rv, rh=rh: [_z_bore(rv + g), _x_bore(rh + g)],
                )
            )
    for r_in in (3.0, 5.0, 7.0, 8.0):
        for t in (0.5, 1.0, 1.5, 2.0, 3.0):
            cases.append(
                Case(
                    f"tube-10-{r_in}-t{t}",
                    t,
                    _rod(10, 10),
                    lambda g, r_in=r_in: [_z_bore(r_in + g)],
                )
            )
    for r in (2.0, 4.0, 6.0):
        for t in (0.5, 1.0, 2.0, 3.0):
            cases.append(
                Case(
                    f"rod-cross-bore-r{r}-t{t}",
                    t,
                    _rod(10, 40),
                    lambda g, r=r: [_x_bore(r + g)],
                )
            )
    for r in (2.0, 4.0, 6.0):
        for t in (0.5, 1.0, 2.0, 3.0):
            cases.append(
                Case(
                    f"sphere-bore-r{r}-t{t}",
                    t,
                    _ball(10),
                    lambda g, r=r: [_z_bore(r + g)],
                )
            )
    for r in (5.0, 8.0, 10.0, 12.0):
        for t in (1.0, 2.0, 3.0, 5.0):
            cases.append(
                Case(
                    f"block-bore-r{r}-t{t}",
                    t,
                    _box(30, 30, 30),
                    lambda g, r=r: [_z_bore(r + g)],
                )
            )
    for r in (5.0, 8.0):
        for t in (1.0, 2.0, 3.0, 5.0):
            cases.append(
                Case(
                    f"block-cross-bore-r{r}-t{t}",
                    t,
                    _box(30, 30, 30),
                    lambda g, r=r: [_z_bore(r + g), _x_bore(r + g)],
                )
            )
    return cases


CASES = _cases()


def test_the_sweep_is_the_reviews_size() -> None:
    assert len(CASES) >= 170


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_a_shell_is_its_definition_or_refused(case: Case) -> None:
    body = case.body()
    pockets = case.cavity()
    try:
        shelled = shell_body(body, [], case.thickness)
    except (ShellError, ShellThicknessError):
        return
    truth = volume_properties(body).volume - sum(
        volume_properties(pocket).volume for pocket in pockets
    )
    assert pockets, "no cavity fits, yet the shell built one"
    assert volume_properties(shelled).volume == pytest.approx(truth, rel=VOLUME_REL)
    assert len(shelled.shells()) == 1 + len(pockets)


def test_the_truth_is_the_hand_derivation() -> None:
    """Two sweep truths by hand. The plate with a centred r5 hole at t 1: the
    cavity is the 38 x 18 x 8 box less the r6 disc, 8 (684 - 36 pi). A sphere
    of radius 10 bored r4 at t 2: the napkin ring of radius 8 bored r6,
    4/3 pi (64 - 36)^(3/2)."""
    (plate,) = [c for c in CASES if c.name == "plate-hole-r5.0-t1.0"]
    (cavity,) = plate.cavity()
    assert cavity.volume == pytest.approx(8 * (684 - 36 * math.pi), rel=1e-12)
    (ball,) = [c for c in CASES if c.name == "sphere-bore-r4.0-t2.0"]
    (ring,) = ball.cavity()
    assert volume_properties(ring).volume == pytest.approx(
        4 / 3 * math.pi * 28**1.5, rel=1e-9
    )


# --- the two reported bodies --------------------------------------------------


def _offset_plate() -> Solid:
    """40 x 20 x 10, bored r7 at y = 1: at t = 2 the bore grown to r9 spans
    y -8..10 against the inner strip -8..8, so it cuts the cavity in two, the
    pockets touching along the line y = -8."""
    return (Box(40, 20, 10) - _z_bore(7.0, y=1.0)).solids()[0]


def _thin_tube() -> Solid:
    """Radii 10 / 7, 10 tall: a 3 mm wall."""
    return (Cylinder(10, 10) - _z_bore(7.0)).solids()[0]


def test_the_offset_plate_truth_is_the_hand_derivation() -> None:
    """The review's 4438.70 mm^3. The cavity section is the 36 x 16 rectangle
    less the r9 disc centred at y = 1, clipped to |y| <= 8: the disc minus its
    cap above y = 8 (1 mm from the top of the disc at y = 10, so 7 from its
    centre): 81 pi - (81 acos(7/9) - 7 sqrt(32)). The hollow is 8000 - 490 pi
    less 6 x that section."""
    disc = 81 * math.pi - (81 * math.acos(7 / 9) - 7 * math.sqrt(32))
    truth = 8000 - 490 * math.pi - 6 * (36 * 16 - disc)
    assert truth == pytest.approx(4438.700, abs=1e-3)
    (case,) = [c for c in CASES if c.name == "plate-offset-hole-r7.0-y1.0-t2.0"]
    body = case.body()
    pockets = case.cavity()
    assert len(pockets) == 2
    reading = volume_properties(body).volume - sum(
        volume_properties(pocket).volume for pocket in pockets
    )
    assert reading == pytest.approx(truth, rel=VOLUME_REL)


def test_the_offset_plate_is_refused_where_its_pocket_is_missing() -> None:
    """Both joins keep one pocket: 5449.66 mm^3. The pocket they drop is
    named, and so is the cause."""
    raw = _offset_plate().hollow([], -2.0).solids()
    assert volume_properties(raw[0]).volume == pytest.approx(5449.66, abs=1e-2)
    with pytest.raises(ShellError, match="missing the cavity at") as refusal:
        shell_body(_offset_plate(), [], 2.0)
    assert "splits into separate pockets" in str(refusal.value)


def test_the_thin_tube_is_too_thick_for_a_2mm_wall() -> None:
    """Both joins return 75.40 mm^3 of crossed offsets. The 3 mm wall fits a
    wall under 1.5 mm and the message says so."""
    raw = _thin_tube().hollow([], -2.0).solids()
    assert raw[0].volume == pytest.approx(75.398, abs=1e-3)
    with pytest.raises(ShellThicknessError, match=r"use a wall under 1\.5 mm"):
        shell_body(_thin_tube(), [], 2.0)


def test_a_refusal_names_the_same_place_on_every_rebuild() -> None:
    messages: set[str] = set()
    for _ in range(3):
        with pytest.raises(ShellError) as refusal:
            shell_body(_offset_plate(), [], 2.0)
        messages.add(str(refusal.value))
    assert len(messages) == 1


# --- the definition check on raw OCCT results ---------------------------------


def _top(body: Solid) -> list[Face]:
    return [max(body.faces(), key=lambda face: face.center().Z)]


def test_the_check_finds_each_raw_fault() -> None:
    plate = ShellDefinition(_offset_plate(), [], 2.0)
    assert plate.cavity_exists
    fault = plate.fault(_offset_plate().hollow([], -2.0).solids()[0])
    assert fault is not None and fault.kind is FaultKind.MISSING
    tube = ShellDefinition(_thin_tube(), [], 2.0)
    assert not tube.cavity_exists
    fault = tube.fault(_thin_tube().hollow([], -2.0).solids()[0])
    assert fault is not None and fault.kind is FaultKind.WALL
    # The cavity face it samples first is thinner than asked: the tube has 3 mm.
    assert fault.wall_mm is not None and fault.wall_mm < 2.0 - 100 * WALL_TOL_MM


@pytest.mark.parametrize(
    ("make", "open_top"),
    [
        (lambda: Box(40, 25, 10).solids()[0], False),
        (lambda: Box(40, 25, 10).solids()[0], True),
        # The flared cup meets its opening at an obtuse rim, where OCCT carries
        # the offset wall up to the opening instead of rounding it: the check
        # must not call that a wrong wall.
        (lambda: Cone(8, 12, 20).solids()[0], True),
        (lambda: Cone(12, 8, 20).solids()[0], True),
        (lambda: fillet(Box(40, 25, 10).edges(), 2.0).solids()[0], False),
    ],
    ids=["box-sealed", "box-open", "flared-cup", "tapered-cup", "filleted-box"],
)
def test_the_check_accepts_a_right_shell(
    make: Callable[[], Solid], open_top: bool
) -> None:
    body = make()
    opened = _top(body) if open_top else []
    result = body.hollow(opened, -1.0).solids()[0]
    definition = ShellDefinition(body, opened, 1.0)
    assert definition.fault(result) is None
    assert definition.cavity_exists


# --- messages that name the real cause (geometry QA, SHELL-WRONG-SOLID) -------


def _nurbs(solid: Solid) -> Solid:
    return Solid(BRepBuilderAPI_NurbsConvert(solid.wrapped, True).Shape())


@pytest.mark.parametrize(
    "make",
    [lambda: Sphere(10).solids()[0], lambda: Cylinder(10, 20).solids()[0]],
    ids=["sphere", "cylinder"],
)
def test_a_nurbs_body_the_offset_fails_on_is_a_shell_error(
    make: Callable[[], Solid],
) -> None:
    """OCCT raises StdFail_NotDone on both, at any thickness. That is a typed
    ShellError that blames the B-spline faces, not the thickness."""
    with pytest.raises(ShellError, match="B-spline") as refusal:
        shell_body(_nurbs(make()), [], 1.0)
    assert "StdFail_NotDone" in str(refusal.value)
    assert "too large" not in str(refusal.value)


def test_an_unhollowed_filleted_box_blames_the_fillet_not_the_thickness() -> None:
    """Every edge of the 40 x 25 x 10 box filleted r2, t 2.0001: OCCT returns
    the body un-hollowed, yet a 35.9998 x 20.9998 x 5.9998 cavity fits. It used
    to say "reduce below the smallest half-wall" (5 mm here). It builds at 2.01."""
    body = fillet(Box(40, 25, 10).edges(), 2.0).solids()[0]
    with pytest.raises(ShellError, match="without its cavity") as refusal:
        shell_body(body, [], 2.0001)
    assert "2 mm radius of a rounded face" in str(refusal.value)
    assert "too large" not in str(refusal.value)
    assert len(shell_body(body, [], 2.01).shells()) == 2


# --- the Intersection route agrees in centroid and inertia too ------------------


def test_the_intersection_route_needs_the_same_centroid_and_inertia() -> None:
    """Same validity, shells, faces, volume and area are not enough: a moved
    copy differs in centroid, a turned one (about its centroid) in inertia."""
    body = Box(40, 25, 10).solids()[0]
    arc = body.hollow([], -2.0).solids()[0]
    assert _same_hollow(arc, arc.moved(Location((0, 0, 0))))
    assert not _same_hollow(arc, arc.moved(Location((1e-3, 0, 0))))
    turned = arc.rotate(Axis.Z, 90)
    assert turned.volume == pytest.approx(arc.volume, rel=1e-12)
    assert not _same_hollow(arc, turned)


# --- a right shell with one pocket filled (review of 5fda139) ------------------


def _random_plates(seed: int, count: int) -> list[Case]:
    """Seeded plates bored once to three times, some cross-bored, like the
    review's: 40 x 20 x 10, bores r1.5 to 8 apart by 0.6 mm or more."""
    rng = random.Random(seed)
    cases: list[Case] = []
    for index in range(count):
        t = round(rng.uniform(0.4, 3.2), 2)
        bores: list[tuple[float, float, float]] = []
        for _ in range(rng.choice([1, 2, 2, 3])):
            r = round(rng.uniform(1.5, 8.0), 3)
            y_room = 10 - r - 0.6
            bores.append(
                (
                    r,
                    round(rng.uniform(-20 + r + 0.6, 20 - r - 0.6), 3),
                    round(rng.uniform(-y_room, y_room), 3) if y_room > 0 else 0.0,
                )
            )
        cross = None
        if rng.random() < 0.3:
            rh = round(rng.uniform(1.0, 3.5), 3)
            cross = (
                rh,
                round(rng.uniform(-10 + rh + 0.6, 10 - rh - 0.6), 3),
                round(rng.uniform(-5 + rh + 0.6, 5 - rh - 0.6), 3),
            )
        apart = all(
            math.dist(a[1:], b[1:]) > a[0] + b[0] + 0.6
            for i, a in enumerate(bores)
            for b in bores[i + 1 :]
        )
        if not apart:
            continue

        def tools(
            g: float,
            bores: list[tuple[float, float, float]] = bores,
            cross: tuple[float, float, float] | None = cross,
        ) -> list[Solid]:
            grown = [_z_bore(r + g, x, y) for r, x, y in bores]
            if cross is not None:
                grown.append(
                    _x_bore(cross[0] + g, z=cross[2]).moved(Location((0, cross[1], 0)))
                )
            return grown

        cases.append(Case(f"random-{seed}-{index}-t{t}", t, _box(40, 20, 10), tools))
    return cases


def _filled_cases() -> list[tuple[str, Solid, list[Solid], float]]:
    """Bodies whose true cavity has two or more pockets: the sweep's, and
    seeded random plates."""
    found = []
    for case in [*CASES, *_random_plates(7, 60)]:
        pockets = case.cavity()
        if len(pockets) < 2:
            continue
        try:
            body = case.body()
        except ValueError:  # the bores cut the plate in two
            continue
        found.append((case.name, body, pockets, case.thickness))
    return found


FILLED = _filled_cases()

#: The smallest pocket the check must see when it is the one left out (mm^3).
#: Measured 2026-09-30 over the sweep and 300 seeded random plates, with the
#: 6 x 6 grid and the corner samples: 8 of 109 missed, the largest 1.47 mm^3
#: (a 3 x 3 grid missed 14, up to 26.9 mm^3: the four corner slivers of the
#: 30 mm cube bored r8 at t 5, which the corner samples now catch).
SMALLEST_SEEN_MM3 = 2.0


@pytest.mark.parametrize(
    ("name", "body", "pockets", "wall"), FILLED, ids=[case[0] for case in FILLED]
)
def test_a_right_shell_with_a_pocket_filled_is_refused(
    name: str, body: Solid, pockets: list[Solid], wall: float
) -> None:
    """The right shell (the body less its true pockets, by booleans) passes
    the check; with its smallest pocket left solid it fails, as long as that
    pocket is not smaller than the check resolves."""
    del name
    pockets = sorted(pockets, key=lambda pocket: pocket.volume)
    (right,) = body.cut(*pockets).solids()
    (filled,) = body.cut(*pockets[1:]).solids()
    assert ShellDefinition(body, [], wall).fault(right) is None
    if pockets[0].volume >= SMALLEST_SEEN_MM3:
        fault = ShellDefinition(body, [], wall).fault(filled)
        assert fault is not None and fault.kind is FaultKind.MISSING


def test_the_filled_pocket_set_is_not_empty() -> None:
    small = [case for case in FILLED if min(p.volume for p in case[2]) < 2.0]
    assert len(FILLED) >= 40
    assert len(FILLED) - len(small) >= 30


# --- the hint says the cavity splits only when it does --------------------------


def test_a_sphere_boss_the_kernel_cannot_hollow_is_not_blamed_on_pockets() -> None:
    """A sphere half sunk in a plate: OCCT raises at every thickness, and
    nothing splits. The message must not say it does."""
    boss = (Box(40, 40, 10) + Sphere(8).moved(Location((0, 0, 5)))).solids()[0]
    with pytest.raises(ShellError, match="could not build this cavity") as refusal:
        shell_body(boss, [], 1.0)
    assert "pocket" not in str(refusal.value)


# --- the check's cost stays linear in the faces (review of 5fda139) -------------


def _vented_lid(slots: int) -> Solid:
    """The review's perf body: a 300 x 100 x 30 lid, vertical edges rounded
    r6, with 5 x *slots* vents 4 x 10 x 10 cut in its top."""
    lid = fillet(Box(300, 100, 30).edges().filter_by(Axis.Z), 6).solids()[0]
    vents = [
        Box(4, 10, 10)
        .solids()[0]
        .moved(Location((-140 + 280 * i / (slots - 1), -40 + 20 * j, 15)))
        for i in range(slots)
        for j in range(5)
    ]
    return lid.cut(*vents).solids()[0]


#: The check's time on the 410-face lid, opened at the bottom at t 1.5, as a
#: share of OCCT's own hollow of it, both timed in the test so a loaded runner
#: slows both. Measured 2026-09-30: 1.2 s against 5.5 s (0.2). At 5fda139 (a
#: compound distance per query, O(faces^2)) the check took about 12 s (2.2).
LID_CHECK_SHARE = 0.75


def test_the_check_on_a_410_face_lid_stays_cheap() -> None:
    lid = _vented_lid(16)
    assert len(lid.faces()) == 410
    opened = [min(lid.faces(), key=lambda face: face.center().Z)]
    start = time.perf_counter()
    result = lid.hollow(opened, -1.5).solids()[0]
    hollow = time.perf_counter() - start
    start = time.perf_counter()
    fault = ShellDefinition(lid, opened, 1.5).fault(result)
    check = time.perf_counter() - start
    assert fault is None
    assert check < LID_CHECK_SHARE * hollow, (
        f"check {check:.2f} s, hollow {hollow:.2f} s"
    )


# --- spline prisms the check must accept (re-review of 38f240f) ----------------

#: Fit points of spline-walled prisms (the spline, then down to y = -20 and
#: back to x = 0, extruded 12). r33, r63 and r72 were refused at 38f240f: the
#: index's boxes (``BRepBndLib.Add``) left their extruded spline face up to
#: 0.0316 mm outside, so it read as off itself. The seed11 ones are
#: random(11) draws.
SPLINE_PRISMS: dict[str, list[tuple[float, float]]] = {
    "r33": [(0, 1.99), (16, 13.85), (32, 13.33), (48, -2.89), (64, 9.15), (80, 11.24)],
    "r63": [(0, -0.76), (16, -2.66), (32, 7.9), (48, 13.93), (64, -1.2), (80, 8.22)],
    "r72": [(0, -5.29), (80 / 3, -1.92), (160 / 3, 13.02), (80, -7.17)],
    "seed11-0": [(0, 11.05), (20, 10.85), (40, 9.19), (60, 1.94), (80, 10.81)],
    "seed11-1": [(0, -3.94), (26.666667, 3.26), (53.333333, 5.86), (80, 9.45)],
    "seed11-2": [(0, 1.83), (26.666667, -4.88), (53.333333, 3.85), (80, 11.59)],
    "seed11-3": [
        (0, -7.08),
        (16, 13.61),
        (32, 13.22),
        (48, 6.39),
        (64, 5.54),
        (80, -4.54),
    ],
}

#: Their shells' volumes (mm^3) under d512ac8, before any check, measured
#: 2026-09-30 with volume_properties; the current kernel read the same to the
#: last bit on all 42 (t 0.5, 1, 2; sealed and open-top).
D512AC8_VOLUMES: dict[tuple[str, float, bool], float] = {
    ("r33", 0.5, False): 3548.2127585236713,
    ("r33", 0.5, True): 2461.0185703085713,
    ("r33", 2.0, False): 12731.406121592323,
    ("r33", 2.0, True): 9047.454473717089,
    ("r63", 0.5, False): 3114.4721780264713,
    ("r63", 0.5, True): 2220.7004393645625,
    ("r63", 2.0, False): 10980.012413927523,
    ("r63", 2.0, True): 8030.651787648509,
    ("r72", 0.5, False): 2939.7627831759123,
    ("r72", 0.5, True): 2072.7861506109757,
    ("r72", 2.0, False): 10456.228490054385,
    ("r72", 2.0, True): 7566.974810792819,
    ("seed11-0", 0.5, False): 3446.41884463569,
    ("seed11-0", 0.5, True): 2394.4884776288773,
    ("seed11-0", 2.0, False): 12318.354500048066,
    ("seed11-0", 2.0, True): 8750.721109708851,
    ("seed11-1", 0.5, False): 3056.609561750465,
    ("seed11-1", 0.5, True): 2143.1410396297706,
    ("seed11-1", 2.0, False): 10900.960497451373,
    ("seed11-1", 2.0, True): 7837.971349268868,
    ("seed11-2", 0.5, False): 2889.067141163967,
    ("seed11-2", 0.5, True): 2090.5873155140775,
    ("seed11-2", 2.0, False): 10153.14529398744,
    ("seed11-2", 2.0, True): 7577.525803910223,
    ("seed11-3", 0.5, False): 3364.706901395743,
    ("seed11-3", 0.5, True): 2294.488492227346,
    ("seed11-3", 2.0, False): 12148.672750157386,
    ("seed11-3", 2.0, True): 8458.608423001428,
}

#: A sealed Arc hollow of a spline wall moves by up to 1.8e-5 mm^3 between
#: builds (kernel/shell.py); this is 5x that.
SPLINE_VOLUME_ABS = 1e-4


def _spline_prism(points: list[tuple[float, float]]) -> Solid:
    end = points[-1][0]
    with BuildPart() as part:
        with BuildSketch():
            with BuildLine():
                Spline(*points)
                Line(points[-1], (end, -20))
                Line((end, -20), (0, -20))
                Line((0, -20), points[0])
            make_face()
        extrude(amount=12)
    built = part.part
    assert built is not None
    return built.solids()[0]


@pytest.mark.parametrize(
    ("name", "wall", "open_top"),
    list(D512AC8_VOLUMES),
    ids=[f"{n}-t{w}-{'open' if o else 'sealed'}" for n, w, o in D512AC8_VOLUMES],
)
def test_a_spline_prism_builds_as_it_did_before_the_check(
    name: str, wall: float, open_top: bool
) -> None:
    body = _spline_prism(SPLINE_PRISMS[name])
    opened = _top(body) if open_top else []
    shelled = shell_body(body, opened, wall)
    assert volume_properties(shelled).volume == pytest.approx(
        D512AC8_VOLUMES[(name, wall, open_top)], abs=SPLINE_VOLUME_ABS
    )
