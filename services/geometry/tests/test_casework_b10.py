"""CASEWORK-B10 acceptance: casework on B10's finished faces, on STEP.

``goldens/c2-kitchen-b10-left-wall``, ``c4-vanity-b10-p1`` and
``c4-v3621-b10-p1`` are ``loft.cabinets`` 1.1.0's expansions and
``b10-inside-gypsum`` is B10 with its walls' inside gypsum (``loft.wall``
1.4.0's finish, INTERIOR-WALLS-INSIDE-GYPSUM-GOLDEN), all pinned to the
plugins by ``packages/loft-plugins/tests/test_casework_b10.py``. Geometry
never learns plugins exist: checked here against panels typed from
``docs/reference-parts/casework.md`` C2 and C4 and ``buildings.md`` B10 with
``test_casework``'s and ``test_partitions_b10``'s independent scripts:

1. each cabinet golden's STEP is the script solid for solid, its volume the
   script's exact sum (C4: 6 036.17578125 in^3; V3621: 6 452.42578125);
2. B10 with inside gypsum is B7's script, B10's members with every board
   stopped at the walls' boards, and the walls' 27 inside panels, solid for
   solid, and nothing in it interferes;
3. C2 interferes with nothing of B10 with gypsum, C4 and its V3621 edit
   with nothing of B10 (``b10-partitions``): every pair probed exactly;
4. C4's cut list: melamine, 1/2 and 1/4 plywood sheets, PVC banding by the
   foot, 4 hinges and 3 pairs of 20 in slides, every line priced, the total
   the lines by hand; its Pieces are the 35 panels and the 7 hardware items.

``expected.json`` numbers:
``uv run python services/geometry/tests/test_casework_b10.py``.
"""

# This module extends test_casework.py's independent script and reads its
# goldens the same way, so it uses that module's helpers.
# pyright: reportPrivateUsage=false

import itertools
import json
import math
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from build123d import Solid
from geometry.kernel import measure_shape
from geometry.kernel.interference import probe_overlap
from loft_wire.cut_list import CutListResponse
from loft_wire.price_book import PriceBookResponse

sys.path.insert(0, str(Path(__file__).parent))
from test_casework import (
    SUBFLOOR,
    Spec,
    _book,
    _carcass,
    _cut_list,
    _drawer,
    _front,
    _map,
    _on_b7,
    _request,
    _signature,
    _spec_signature,
    _step,
    _two,
    _unmatched,
    c2_base,
    c2_wall,
    derive,
    volume_in3,
)
from test_outline_b7 import BASE, Member, analytic_volume, box, script
from test_partitions_b10 import (
    COURSES,
    DENSITIES,
    GYP,
    IN,
    P1_X,
    P2_Y,
    RO,
    b10_volume,
    door_unit,
    framing,
    gypsum_boxes,
)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
HOUSE = "b10-inside-gypsum"
C2 = "c2-kitchen-b10-left-wall"
C4 = "c4-vanity-b10-p1"
V3621 = "c4-v3621-b10-p1"
Bounds = tuple[float, float, float, float, float, float]

# --- The cabinets (casework.md) -------------------------------------------------------


def c2_b10() -> list[Spec]:
    """C2 on B10: 1.0.0's C2 on B7 (its runs at Y 186.5 - x), its filler 3
    wide from the back wall's board at Y 186 (X 30..30.75, the fronts' line)
    where B7's was 3.5 from the framing; every other panel where it was."""
    out = [_on_b7(s) for s in c2_base() + c2_wall() if s.role != "filler"]
    filler = Spec(
        "filler", (30, 30.75, 183, 186, SUBFLOOR + 4.5, SUBFLOOR + 84), "plywood"
    )
    return [filler, *out]


def vanity(W: float) -> list[Spec]:
    """A V<W>21 frameless in melamine: a 6 in false front over two doors."""
    m = "melamine"
    out = _carcass(W, 21, 34.5, 4.5, 0, "stretchers", "", m)
    out.append(_front("false_front", 1 / 16, W - 1 / 16, 21, 28.4375, 34.4375, m))
    out += [_front("door", a, b, 21, 4.5625, 28.3125, m) for a, b in _two(W, 1 / 16)]
    return out


def vdb1521() -> list[Spec]:
    """casework.md C4: 15 x 21 x 34.5, three drawers (6 on top, two of
    11.8125), each box 12.5 wide (13.5 less 1/2 a side) and 20 long (the
    slide in the 20.25 inside depth) from the carcass front, its sides 2
    under its front and its top 3/4 under its opening's (the stretchers'
    underside for the top one)."""
    m = "melamine"
    out = _carcass(15, 21, 34.5, 4.5, 0, "stretchers", "", m)
    out += [
        _front("drawer_front", 1 / 16, 15 - 1 / 16, 21, 28.4375, 34.4375, m),
        _front("drawer_front", 1 / 16, 15 - 1 / 16, 21, 16.5, 28.3125, m),
        _front("drawer_front", 1 / 16, 15 - 1 / 16, 21, 4.5625, 16.375, m),
    ]
    for z0, z1 in ((29, 33), (17.8125, 27.625), (5.875, 15.6875)):
        out += _drawer(1.25, 13.75, 21, 20, z0, z1)
    return out


def on_p1(s: Spec) -> Spec:
    """Run frame -> world on P1's +X board (X 182.25), from Y 186 toward
    the front: X = 182.25 + y, Y = 186 - x, Z on the subfloor."""
    return _map(
        s,
        lambda b: (
            182.25 + b[2],
            182.25 + b[3],
            186 - b[1],
            186 - b[0],
            SUBFLOOR + b[4],
            SUBFLOOR + b[5],
        ),
    )


def c4(width: float = 30) -> list[Spec]:
    vdb = [
        _map(s, lambda b: (b[0] + width, b[1] + width, *b[2:]))  # type: ignore[arg-type]
        for s in vdb1521()
    ]
    return [on_p1(s) for s in vanity(width) + vdb]


def spec(name: str) -> list[Spec]:
    return {C2: c2_b10, C4: c4, V3621: lambda: c4(36)}[name]()


CABINETS = (C2, C4, V3621)


def test_the_script_is_casework_md_s_c4() -> None:
    """VDB1521 2 964.03515625 in^3, V3021 3 072.140625; the run 6 036.17578125
    (V3621: 3 488.390625 + the VDB); C2 1.0.0's less 1/2 x 3/4 x 79.5."""
    assert volume_in3(vdb1521()) == Fraction(296403515625, 10**8)
    assert volume_in3(vanity(30)) == Fraction(3072140625, 10**6)
    assert volume_in3(c4()) == Fraction(603617578125, 10**8)
    assert volume_in3(c4(36)) == Fraction(645242578125, 10**8)
    old = [_on_b7(s) for s in c2_base() + c2_wall()]
    assert volume_in3(c2_b10()) == volume_in3(old) - Fraction(3, 8) * Fraction(159, 2)
    assert len(c2_b10()) == 91 and len(c4()) == 10 + 25


@pytest.mark.parametrize("name", CABINETS)
def test_the_step_is_the_script(name: str, tmp_path: Path) -> None:
    solids = _step(_request(name), tmp_path / f"{name}.step")
    specs = spec(name)
    assert len(solids) == len(specs)
    assert (
        _unmatched([_signature(s) for s in solids], [_spec_signature(s) for s in specs])
        == []
    )
    total = sum(float(measure_shape(s).volume) for s in solids) / IN**3
    assert total == pytest.approx(float(volume_in3(specs)), abs=1e-4)


# --- B10 with the walls' inside gypsum ------------------------------------------------

G = 0.5
#: The walls' inside boards (buildings.md B10, interior_wall's corners): the
#: front and back run between the side walls' framing (X 5.5..282.5), the
#: sides stop at them (Y 6..186); each laid in 96 in strips from its wall's
#: start (front from X 282.5, back from X 5.5, left from Y 6, right from Y
#: 186), its rough openings (B7's: the door 38 x 82.5 at X 144, 36 x 48
#: windows' 36.5 x 48.5 at X 60, 228 and the back's 144, the sides' 24 x 36
#: at Y 96) and the partitions meeting it cut out.
INSIDE: list[
    tuple[
        str,
        tuple[float, float],
        list[tuple[float, float]],
        list[tuple[float, float, float, float]],
    ]
] = [
    (
        "y",
        (5.5, 6.0),
        [(186.5, 282.5), (90.5, 186.5), (5.5, 90.5)],
        [
            (125, 163, -1, 82.5),
            (209.75, 246.25, 34, 82.5),
            (41.75, 78.25, 34, 82.5),
            (*P1_X, -1, 99),
        ],
    ),
    (
        "y",
        (186.0, 186.5),
        [(5.5, 101.5), (101.5, 197.5), (197.5, 282.5)],
        [(125.75, 162.25, 34, 82.5), (*P1_X, -1, 99)],
    ),
    ("x", (5.5, 6.0), [(6, 102), (102, 186)], [(83.75, 108.25, 46, 82.5)]),
    (
        "x",
        (282.0, 282.5),
        [(90, 186), (6, 90)],
        [(83.75, 108.25, 46, 82.5), (*P2_Y, -1, 99)],
    ),
]
#: The partitions' boards, now stopped at the walls' boards: P1's both faces
#: Y 6..186 (96 from its start at the back), its +X cut at P2; P2's from X
#: 282 to P1's board, the door's rough opening cut out.
PARTITIONS: list[
    tuple[
        str,
        tuple[float, float],
        list[tuple[float, float]],
        list[tuple[float, float, float, float]],
    ]
] = [
    ("x", (P1_X[0] - G, P1_X[0]), [(90, 186), (6, 90)], []),
    ("x", (P1_X[1], P1_X[1] + G), [(90, 186), (6, 90)], [(*P2_Y, -1, 99)]),
    ("y", (P2_Y[0] - G, P2_Y[0]), [(186, 282), (182.25, 186)], [(*RO, -1, 82.5)]),
    ("y", (P2_Y[1], P2_Y[1] + G), [(186, 282), (182.25, 186)], [(*RO, -1, 82.5)]),
]


def _panel(
    axis: str, across: tuple[float, float], a: float, b: float, z: tuple[float, float]
) -> Bounds:
    if axis == "y":  # along X, at a Y
        return (a, b, *across, *z)
    return (*across, a, b, *z)


def boards(
    faces: list[
        tuple[
            str,
            tuple[float, float],
            list[tuple[float, float]],
            list[tuple[float, float, float, float]],
        ]
    ],
) -> list[tuple[Bounds, list[Bounds]]]:
    """Each panel's box (every course of every strip) and the cuts in it."""
    out: list[tuple[Bounds, list[Bounds]]] = []
    for axis, (c0, c1), strips, cuts in faces:
        for z in COURSES:
            for a, b in strips:
                panel = _panel(axis, (c0, c1), a, b, z)
                holes = [
                    _panel(axis, (c0 - 1, c1 + 1), ca, cb, (BASE + za, BASE + zb))
                    for ca, cb, za, zb in cuts
                    if min(b, cb) > max(a, ca)
                    and min(z[1], BASE + zb) > max(z[0], BASE + za)
                ]
                out.append((panel, holes))
    return out


def _vol(b: Bounds) -> Fraction:
    x0, x1, y0, y1, z0, z1 = (Fraction(v) for v in b)
    return (x1 - x0) * (y1 - y0) * (z1 - z0)


def _clip(b: Bounds, c: Bounds) -> Bounds:
    """*c* within *b*."""
    return (
        max(b[0], c[0]),
        min(b[1], c[1]),
        max(b[2], c[2]),
        min(b[3], c[3]),
        max(b[4], c[4]),
        min(b[5], c[5]),
    )


def boards_volume(panels: list[tuple[Bounds, list[Bounds]]]) -> Fraction:
    """Each panel's box less its cuts within it (the cuts never overlap)."""
    return sum(
        (
            _vol(p) - sum((_vol(_clip(p, h)) for h in holes), Fraction(0))
            for p, holes in panels
        ),
        Fraction(0),
    )


def house_members() -> list[Member]:
    """B7's script, B10's framing and door, its partitions' boards and the
    walls' inside boards: every panel a box less its cuts, split where a cut
    crosses it."""
    out = script()
    out += [Member(m, "spf_lumber", box(b)) for m, b in framing()]
    for panel, holes in boards(PARTITIONS + INSIDE):
        solid: Any = box(panel)
        for hole in holes:
            solid = solid.cut(box(hole))
        out += [Member("Gypsum", GYP, s) for s in solid.solids()]
    for member, material, outer, hole in door_unit():
        solid = box(outer)
        if hole is not None:
            solid = solid.cut(box(hole)).solids()[0]  # pyright: ignore[reportUnknownMemberType]
        out.append(Member(member, material, solid))
    return out


def house_volume() -> Fraction:
    """B10's added members in exact rationals, its boards re-laid: b10's
    framing and door (b10_volume less its own boards) plus these boards."""
    old_boards = Fraction(481305, 10) * Fraction(1, 2)
    assert len(gypsum_boxes()) == 20
    return b10_volume() - old_boards + boards_volume(boards(PARTITIONS + INSIDE))


def test_the_boards_by_hand() -> None:
    """The partitions' 20 boards lose 1/2 at each end where they meet a wall
    board: P1's faces 180 x 96 (were 181), P2's 99.75 (were 100.25), less the
    same cuts (P2 on P1's +X face, the door's rough opening above the
    boards' 1.125 floor gap). The walls' boards: (277 x 2 + 180 x 2) x 96
    less the five windows, the door and the three junctions."""
    part = boards_volume(boards(PARTITIONS)) * 2  # areas (in^2)
    p1 = 2 * 180 * 96 - 3.5 * 96
    p2 = 2 * (99.75 * 96 - 34 * (82.5 - 1.125))
    assert part == Fraction(p1 + p2)
    inside = boards_volume(boards(INSIDE)) * 2
    windows = 3 * 36.5 * 48.5 + 2 * 24.5 * 36.5
    door = 38 * (82.5 - 1.125)
    junctions = 3 * 3.5 * 96
    want = (277 * 2 + 180 * 2) * 96 - windows - door - junctions
    assert inside == Fraction(want)
    # 20 panels, 7 of them split in two where a cut crosses them whole.
    assert len(boards(INSIDE)) == 20
    assert len(house_members()) == 217 + 45 + 20 + 27 + 2


@pytest.fixture(scope="module")
def house_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return _step(_request(HOUSE), tmp_path_factory.mktemp("step") / f"{HOUSE}.step")


def test_the_house_is_the_script_and_nothing_interferes(
    house_solids: list[Solid],
) -> None:
    mine = house_members()
    assert len(house_solids) == len(mine)
    want = [_signature(m.solid) for m in mine]
    got = [_signature(s) for s in house_solids]
    assert _close(got, want) == []
    volume = sum(float(measure_shape(s).volume) for s in house_solids) / IN**3
    assert volume == pytest.approx(
        analytic_volume(288) + float(house_volume()), abs=1e-4
    )
    assert _interfering(house_solids, house_solids, same=True) == []


def _close(got: list[tuple[float, ...]], want: list[tuple[float, ...]]) -> list[Any]:
    left = list(want)
    missing: list[Any] = []
    for sig in got:
        k = next(
            (
                k
                for k, other in enumerate(left)
                if abs(sig[0] - other[0]) <= 1e-4
                and all(
                    abs(a - b) <= 1e-5 for a, b in zip(sig[1:], other[1:], strict=True)
                )
            ),
            None,
        )
        if k is None:
            missing.append(sig)
        else:
            left.pop(k)
    return missing + left


def _interfering(
    ours: list[Solid], theirs: list[Solid], same: bool = False
) -> list[tuple[int, int, float]]:
    """Pairs (one of *ours*, one of *theirs*) whose boxes overlap and whose
    common volume, probed exactly, is not zero (or unresolved)."""
    a_boxes = [s.bounding_box() for s in ours]
    b_boxes = a_boxes if same else [s.bounding_box() for s in theirs]
    pairs = (
        itertools.combinations(range(len(ours)), 2)
        if same
        else itertools.product(range(len(ours)), range(len(theirs)))
    )
    bad: list[tuple[int, int, float]] = []
    for i, j in pairs:
        a, b = a_boxes[i], b_boxes[j]
        if all(
            min(getattr(a.max, k), getattr(b.max, k))
            - max(getattr(a.min, k), getattr(b.min, k))
            > 1e-6
            for k in ("X", "Y", "Z")
        ):
            probe = probe_overlap(ours[i], theirs[j])
            if probe.unresolved or probe.volume_mm3 != 0.0:
                bad.append((i, j, probe.volume_mm3))
    return bad


# --- 3. The cabinets against the house ------------------------------------------------


@pytest.fixture(scope="module")
def b10_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return _step(
        _request("b10-partitions"),
        tmp_path_factory.mktemp("step") / "b10-partitions.step",
    )


def test_c2_touches_nothing_of_b10_with_gypsum(
    house_solids: list[Solid], tmp_path: Path
) -> None:
    run = _step(_request(C2), tmp_path / f"{C2}.step")
    assert _interfering(run, run, same=True) == []
    assert _interfering(run, house_solids) == []
    # The backs are on the left wall's board: their faces at X 6.
    assert min(s.bounding_box().min.X for s in run) == pytest.approx(6 * IN, abs=1e-9)


@pytest.mark.parametrize("name", [C4, V3621])
def test_c4_touches_nothing_of_b10(
    name: str, b10_solids: list[Solid], tmp_path: Path
) -> None:
    run = _step(_request(name), tmp_path / f"{name}.step")
    assert _interfering(run, run, same=True) == []
    assert _interfering(run, b10_solids) == []
    assert min(s.bounding_box().min.X for s in run) == pytest.approx(
        182.25 * IN, abs=1e-9
    )
    # V3621 ends 3/4 clear of P2's board (Y 134.25).
    low = min(s.bounding_box().min.Y for s in run) / IN
    assert low == pytest.approx(141.0 if name == C4 else 135.0, abs=1e-9)


# --- 4. C4's cut list -----------------------------------------------------------------

C4_BOOK: list[tuple[str, str, str, str | None, int]] = [
    ("melamine", "melamine_3_4", "each", "4x8", 4298),
    ("plywood", "plywood_1_2", "each", "4x8", 5498),
    ("plywood", "plywood_1_4", "each", "4x8", 2698),
    ("pvc", "edge_banding", "linear_foot", None, 35),
    ("steel_1018", "hinge", "each", None, 450),
    ("steel_1018", "slide_20", "each", None, 1299),
]


def test_c4_prices_to_the_last_line_plywood_included() -> None:
    """Melamine 6 805.984375 in^2 (V3021 4 096.1875 + VDB 2 709.796875) on 2
    sheets, 1/2 plywood 1 488.375 and 1/4 plywood 750 on one sheet each;
    578.75 in of PVC banding, 49 ft bought; 4 hinges, 3 pairs of 20 in
    slides. Pieces: 35 bodies and 7 hardware items, never the banding."""
    book: PriceBookResponse = _book(C4_BOOK)
    cut: CutListResponse = _cut_list(C4, book)
    assert cut.unpriced_lines == 0
    by = {(line.casework or line.profile): line for line in cut.lines}
    sheets = {
        p: (by[p].sheet, by[p].stock_quantity, round((by[p].area_mm2 or 0) / IN**2, 6))
        for p in ("3/4 melamine", "1/2 plywood", "1/4 plywood")
    }
    assert sheets == {
        "3/4 melamine": ("4x8", 2, 6805.984375),
        "1/2 plywood": ("4x8", 1, 1488.375),
        "1/4 plywood": ("4x8", 1, 750.0),
    }
    band = by["edge_banding"]
    assert band.total_length_mm / IN == pytest.approx(578.75)
    assert band.stock_quantity == math.ceil(578.75 / 12) == 49
    assert (by["hinge"].quantity, by["slide_20"].quantity) == (4, 3)
    hand = 2 * 4298 + 5498 + 2698 + 49 * 35 + 4 * 450 + 3 * 1299
    assert cut.total_price_cents == hand
    assert sum(line.extended_price_cents or 0 for line in cut.lines) == hand
    assert cut.total_quantity == 35 + 4 + 3


# --- expected.json --------------------------------------------------------------------


def house_expected() -> dict[str, Any]:
    """As test_partitions_b10.expected_numbers: the volume analytic, the
    rest measured on the script's solids."""
    mine = house_members()
    volume = (analytic_volume(288) + float(house_volume())) * IN**3
    moments = [0.0, 0.0, 0.0]
    mass_moments = [0.0, 0.0, 0.0]
    mass = area = total = 0.0
    vertices = triangles = faces = edges = 0
    for m in mine:
        props = measure_shape(m.solid)
        v = float(props.volume)
        rho = DENSITIES[m.material] * 1e-6
        c = props.centroid
        for k, value in enumerate((c.x, c.y, c.z)):
            moments[k] += v * value
            mass_moments[k] += v * rho * value
        mass += v * rho
        total += v
        area += float(props.surface_area)
        faces += len(m.solid.faces())
        edges += len(m.solid.edges())
        for face in m.solid.faces():
            loops = face.wires()
            n = sum(len(w.edges()) for w in loops)
            vertices += n
            triangles += n + 2 * (len(loops) - 1) - 2
    bb = [m.solid.bounding_box() for m in mine]
    return {
        "volume": volume,
        "surface_area": area,
        "centroid": dict(zip("xyz", (x / total for x in moments), strict=True)),
        "mass_g": mass,
        "center_of_mass": dict(
            zip("xyz", (x / mass for x in mass_moments), strict=True)
        ),
        "bounding_box": {
            "min": {
                "x": min(b.min.X for b in bb),
                "y": min(b.min.Y for b in bb),
                "z": min(b.min.Z for b in bb),
            },
            "max": {
                "x": max(b.max.X for b in bb),
                "y": max(b.max.Y for b in bb),
                "z": max(b.max.Z for b in bb),
            },
        },
        "topology": {"faces": faces, "edges": edges, "shells": len(mine)},
        "mesh": {"vertices": vertices, "triangles": triangles},
    }


def cabinet_expected(name: str) -> dict[str, Any]:
    d = derive(spec(name))

    def point(c: tuple[Fraction, Fraction, Fraction]) -> dict[str, float]:
        return {"x": float(c[0]), "y": float(c[1]), "z": float(c[2])}

    return {
        "volume": float(d.volume),
        "surface_area": float(d.area),
        "centroid": point(d.centroid),
        "mass_g": float(d.mass_g),
        "center_of_mass": point(d.com),
        "bounding_box": {
            "min": {"x": d.bounds[0], "y": d.bounds[2], "z": d.bounds[4]},
            "max": {"x": d.bounds[1], "y": d.bounds[3], "z": d.bounds[5]},
        },
        "topology": {"faces": d.faces, "edges": d.edges, "shells": d.shells},
        "mesh": {"vertices": d.vertices, "triangles": d.triangles},
    }


if __name__ == "__main__":
    out = {name: cabinet_expected(name) for name in CABINETS}
    out[HOUSE] = house_expected()
    print(json.dumps(out, indent=1))
