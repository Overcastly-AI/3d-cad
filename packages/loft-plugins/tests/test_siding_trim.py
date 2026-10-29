"""SIDING-TRIM: ``loft.wall`` 1.5.0's Exterior finish (siding, corner boards
and casing over the sheathing) and ``loft.roof`` 1.8.0 carrying it up the
gables (Chief Architect's wall-type siding layer and Materials List).

Checked against ``docs/reference-parts/buildings.md`` B7, typed by hand:

* B7 drawn today (floor 1.3.0, walls 1.5.0 on the floor, the door and five
  windows 1.5.0 picked by call size with their units drawn, the roof 1.8.0):
  the OSB's outer face is the envelope X -7/16 .. 288 7/16, Y -7/16 .. 192
  7/16, and the fibre-cement lap (5/16) lies on it from the foundation top
  (Z 0, the floor's sills' underside) to the top plate (108.59375);
* each outside corner is two 5/4x4 boards (1 x 3.5) on the OSB: the front
  or back wall's (it runs through) X -7/16 .. 3 1/16 (and 284 15/16 .. 288
  7/16), the side wall's lapping its edge, Y -1 7/16 .. 2 1/16 (and 189
  15/16 .. 193 7/16): 8 boards of 108.59375; the siding runs between them,
  281.875 along the front and back and 187.875 along each side;
* picture-frame casing, its inner edge on the unit: a 3040's 36 x 48 unit
  centred in its 36.5 x 48.5 rough opening (head 82.5 above the subfloor)
  cased 43 x 55, a 2030's 31 x 43, the 3068's frame (37.5 x 82, on the
  subfloor) 44.5 x 85.5 with its legs on the sill: 23 pieces, long points
  1 099.5 in (the PM's 1 094 cased the door's 36 x 80 slab);
* the siding is cut out round the casing's outer edge: 939.5 x 108.59375 -
  13 565.75 = 88 458.078125 in² as sketched, the rafter tails then notched
  out of it and of the eave walls' corner boards by the roof;
* the gables' siding covers the gable OSB (Y -7/16 .. 192 7/16, plate to
  the rafters' top plane), 5 705.185554 in² a gable.

The geometry golden ``b7-siding`` and the kernel fixture
``siding-cases.json.gz`` are written from here and pinned by this module
(``services/geometry/tests/test_siding_b7.py`` checks them exactly, and the
cut list's 109 boards). Regenerate after a deliberate change (a NEW plugin
version) with ``uv run python packages/loft-plugins/tests/test_siding_trim.py``.
"""

import gzip
import itertools
import json
import sys
import uuid
from collections import Counter
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from loft_plugins import REGISTRY, PluginError, canonical_inputs, update_for
from loft_plugins.updates import update_effect, updated_inputs
from loft_wire.cut_list import ROLE_SYSTEMS, CutListMember
from loft_wire.features import (
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    SketchFeature,
)
from loft_wire.plugins import ChoiceInput, CountInput
from loft_wire.sketch import SketchLine

sys.path.insert(0, str(Path(__file__).parent))
import test_building_outline as outline
import test_crawl_space as crawl
import test_slab as slab
from test_building_outline import (
    B7_FLOOR,
    B7_ROOF,
    B7_STUDS,
    GOLDENS,
    IN,
    OSB,
    WALLS_ID,
    b7_openings,
    boxes,
    house,
    l_sketch,
    members_json,
    members_of,
    rectangle,
    ref,
    request_of,
)
from test_ceiling_joists import B7_GABLE, Rows, roof_of, roofed
from test_interior_walls import b10, titles

WALL_1_4 = REGISTRY.get("loft.wall", "1.4.0")
WALL_1_5 = REGISTRY.get("loft.wall", "1.5.0")
ROOF_1_7 = REGISTRY.get("loft.roof", "1.7.0")
ROOF_1_8 = REGISTRY.get("loft.roof", "1.8.0")
GOLDEN = "b7-siding"
CASES = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "geometry"
    / "tests"
    / "fixtures"
    / "siding-cases.json.gz"
)
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000051d1")

FINISH = ("siding", "corner_board", "casing")
LAP = {"exterior_finish": "fibre_cement_lap_8_25"}
VINYL = {"exterior_finish": "vinyl_d4"}
CEDAR = {"exterior_finish": "cedar_bevel_1_2x8"}
NONE = {"exterior_finish": "none"}

# --- B7, typed from buildings.md (inches) ---------------------------------------------

PLATE = 1.5 + 9.25 + 23 / 32 + 97.125  # 108.59375
SUB = 1.5 + 9.25 + 23 / 32  # the subfloor's top: 11.46875
S = 7 / 16  # the OSB
LAP_T = 5 / 16
W = 192.0

#: The call sizes B7's openings are picked by.
SIZES = {
    "Door": "door_3068",
    "Window 1": "window_3040",
    "Window 2": "window_3040",
    "Window 3": "window_3040",
    "Window 4": "window_2030",
    "Window 5": "window_2030",
}


@contextmanager
def today() -> Generator[None]:
    """test_building_outline's tree builder with every plugin at its newest."""
    with (
        mock.patch.object(outline, "FLOOR", REGISTRY.latest("loft.floor")),
        mock.patch.object(outline, "WALL", REGISTRY.latest("loft.wall")),
        mock.patch.object(outline, "ROOF", REGISTRY.latest("loft.roof")),
    ):
        yield


def b7_today(
    length: float = 288.0,
    walls: dict[str, Any] | None = None,
    roof: dict[str, Any] | None = None,
    wall: Any = None,
) -> Rows:
    """B7 drawn today: every opening picked by its call size, its unit drawn,
    measured from its wall's start as buildings.md places it (its walls at
    *wall*'s release when given)."""
    door, window = REGISTRY.latest("loft.door"), REGISTRY.latest("loft.window")
    openings = [
        (
            door if p.manifest.id == "loft.door" else window,
            name,
            seg,
            {**raw, "measure_from": "start", "size": SIZES[name]},
        )
        for p, name, seg, raw in b7_openings(length)
    ]
    with today(), mock.patch.object(outline, "WALL", wall or WALL_1_5):
        return house(
            rectangle(length, 192),
            openings,
            {**B7_STUDS, **(walls or {})},
            B7_FLOOR,
            B7_GABLE if roof is None else roof,
        )


def walls_of(rows: Rows) -> list[ExpandedMember]:
    return next(ms for fid, _, ms in rows if fid == WALLS_ID)


def of_role(members: list[ExpandedMember], role: str) -> list[ExpandedMember]:
    return [m for m in members if m.role == role]


def section_of(rows: Rows, member: ExpandedMember) -> SketchFeature:
    by_id = {m.id: m.feature for m in members_of(rows)}
    assert isinstance(member.feature, ExtrudeFeature)
    sketch = by_id[member.feature.params.profile.feature_id]
    assert isinstance(sketch, SketchFeature)
    return sketch


def loops_of(sketch: SketchFeature) -> list[list[tuple[float, float]]]:
    """The sketch's closed loops (in, its own x and y), in order: each loop's
    lines run on until one ends where the loop began."""
    out: list[list[tuple[float, float]]] = []
    loop: list[tuple[float, float]] = []
    for line in sketch.params.entities:
        assert isinstance(line, SketchLine)
        loop.append((line.start.x / IN, line.start.y / IN))
        if (line.end.x / IN, line.end.y / IN) == loop[0]:
            out.append(loop)
            loop = []
    assert not loop
    return out


def shoelace(loop: list[tuple[float, float]]) -> float:
    return (
        sum(a[0] * b[1] - b[0] * a[1] for a, b in itertools.pairwise([*loop, loop[0]]))
        / 2
    )


def face_area(rows: Rows, member: ExpandedMember) -> float:
    """A layer's sketched area (in^2): its outer loop less its holes."""
    return abs(sum(shoelace(loop) for loop in loops_of(section_of(rows, member))))


def box_of(b: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(round(v, 6) + 0.0 for v in b)


# --- The expected bodies, by hand -----------------------------------------------------

#: Each outline wall's siding box (x0, x1, y0, y1, z0, z1): front and back
#: between their corner boards, the sides between the lapping ones.
SIDING_BOXES = sorted(
    [
        (3.0625, 284.9375, -0.75, -0.4375, 0.0, PLATE),
        (3.0625, 284.9375, 192.4375, 192.75, 0.0, PLATE),
        (-0.75, -0.4375, 2.0625, 189.9375, 0.0, PLATE),
        (288.4375, 288.75, 2.0625, 189.9375, 0.0, PLATE),
    ]
)
CORNER_BOXES = sorted(
    [
        # The front and back walls' (through): on their OSB, to its end.
        (-0.4375, 3.0625, -1.4375, -0.4375, 0.0, PLATE),
        (284.9375, 288.4375, -1.4375, -0.4375, 0.0, PLATE),
        (-0.4375, 3.0625, 192.4375, 193.4375, 0.0, PLATE),
        (284.9375, 288.4375, 192.4375, 193.4375, 0.0, PLATE),
        # The sides' (fitted): lapping the other's 1 in edge.
        (-1.4375, -0.4375, -1.4375, 2.0625, 0.0, PLATE),
        (-1.4375, -0.4375, 189.9375, 193.4375, 0.0, PLATE),
        (288.4375, 289.4375, -1.4375, 2.0625, 0.0, PLATE),
        (288.4375, 289.4375, 189.9375, 193.4375, 0.0, PLATE),
    ]
)


def casing_boxes() -> list[tuple[float, ...]]:
    """Each casing piece's box: (x or y span, z span) per opening, the
    window units centred in their rough openings, the door's frame on the
    subfloor."""
    out: list[tuple[float, ...]] = []

    def frame(
        a0: float, a1: float, z0: float, z1: float, door: bool
    ) -> list[tuple[float, float, float, float]]:
        # (a0, a1, z0, z1) of each piece, the casing 3.5 outside the unit.
        b0 = z0 if door else z0 - 3.5
        pieces = [(a0 - 3.5, a1 + 3.5, z1, z1 + 3.5)]  # head
        if not door:
            pieces.append((a0 - 3.5, a1 + 3.5, b0, z0))  # sill
        pieces.append((a0 - 3.5, a0, b0, z1 + 3.5))
        pieces.append((a1, a1 + 3.5, b0, z1 + 3.5))
        return pieces

    front = (-1.4375, -0.4375)
    back = (192.4375, 193.4375)
    left = (-1.4375, -0.4375)
    right = (288.4375, 289.4375)
    win = (SUB + 34.25, SUB + 82.25)  # a 3040 in its rough opening
    small = (SUB + 46.25, SUB + 82.25)  # a 2030
    for x in (60.0, 228.0):
        for a0, a1, z0, z1 in frame(x - 18, x + 18, *win, False):
            out.append((a0, a1, *front, z0, z1))
    for a0, a1, z0, z1 in frame(144 - 18.75, 144 + 18.75, SUB, SUB + 82, True):
        out.append((a0, a1, *front, z0, z1))
    for a0, a1, z0, z1 in frame(126.0, 162.0, *win, False):
        out.append((a0, a1, *back, z0, z1))
    for x0, x1 in (left, right):
        for a0, a1, z0, z1 in frame(84.0, 108.0, *small, False):
            out.append((x0, x1, a0, a1, z0, z1))
    return sorted(box_of(b) for b in out)


#: The cased openings (unit + 3.5 each way): what is cut out of the siding.
CASED = {"3040": 43 * 55, "2030": 31 * 43, "3068": 44.5 * 85.5}


def wall_area(along: float, cased: list[str]) -> float:
    return along * PLATE - sum(CASED[c] for c in cased)


#: The siding as sketched, by wall, clockwise from the front: the front
#: (e1), the left (e4), the back (e3) and the right (e2).
AREAS = {
    "e1": wall_area(281.875, ["3068", "3040", "3040"]),
    "e4": wall_area(187.875, ["2030"]),
    "e3": wall_area(281.875, ["3040"]),
    "e2": wall_area(187.875, ["2030"]),
}


# --- B7 -------------------------------------------------------------------------------


def test_b7_sides_each_face_between_its_corner_boards() -> None:
    rows = b7_today()
    members = members_of(rows)
    assert sorted(box_of(b) for b in boxes(members, ("siding",))) == SIDING_BOXES
    assert sorted(box_of(b) for b in boxes(members, ("corner_board",))) == CORNER_BOXES
    for m in of_role(walls_of(rows), "siding"):
        assert m.metadata is not None and m.metadata.siding is not None
        assert (m.metadata.profile, m.metadata.material) == (
            "Fibre-cement lap 8-1/4",
            "fibre_cement",
        )
        assert m.metadata.siding.model_dump() == {
            "product": "fibre_cement_lap_8_25",
            "waste_percent": 10,
        }
    for role in ("corner_board", "casing"):
        for m in of_role(walls_of(rows), role):
            assert m.metadata is not None
            assert (m.metadata.profile, m.metadata.material) == (
                "5/4x4",
                "fibre_cement",
            )


def test_the_siding_is_the_face_less_the_cased_openings() -> None:
    """939.5 x 108.59375 = 102 023.828125 less 13 565.75: 88 458.078125 in²
    as sketched, each cased opening a hole of the siding (the door's too:
    the siding runs on under it to the foundation top)."""
    rows = b7_today()
    siding = of_role(walls_of(rows), "siding")
    assert [m.name for m in siding] == [f"{e}/siding/0" for e in AREAS]
    for m in siding:
        line = (m.name or "").split("/")[0]
        assert face_area(rows, m) == pytest.approx(AREAS[line], abs=1e-6), line
    assert sum(AREAS.values()) == pytest.approx(88458.078125, abs=1e-9)
    assert 939.5 * PLATE - 13565.75 == 88458.078125
    holes = [len(loops_of(section_of(rows, m))) - 1 for m in siding]
    assert holes == [3, 1, 1, 1]


def test_the_casing_is_a_picture_frame_round_each_unit() -> None:
    rows = b7_today()
    members = members_of(rows)
    assert sorted(box_of(b) for b in boxes(members, ("casing",))) == casing_boxes()
    casing = of_role(walls_of(rows), "casing")
    assert len(casing) == 23
    longs = sorted(
        round(max(b[1] - b[0], b[3] - b[2], b[5] - b[4]), 6)
        for b in boxes(members, ("casing",))
    )
    assert sum(longs) == 1099.5
    assert Counter(longs) == Counter({43.0: 10, 55.0: 6, 31.0: 4, 85.5: 2, 44.5: 1})
    # Mitred: a head's long point is the casing's outer edge, its short the
    # unit's (43 and 36 for a 3040).
    head = next(m for m in casing if (m.name or "").endswith("/head"))
    loop = loops_of(section_of(rows, head))[0]
    xs = sorted({round(x, 9) for x, _ in loop})
    assert len(loop) == 4 and len(xs) == 4
    assert round(xs[-1] - xs[0], 9) in (43.0, 44.5, 31.0)
    assert round(xs[2] - xs[1], 9) in (36.0, 37.5, 24.0)


def test_a_door_is_cased_on_its_frame_not_its_slab() -> None:
    """The PM cased the 3068's 36 x 80 slab (43 x 83.5); the unit is its
    prehung frame, 37.5 x 82 (3/4 jambs, a 1-1/4 threshold): 44.5 x 85.5,
    215.5 in of casing, not 210."""
    rows = b7_today()
    door = [
        b
        for b in boxes(members_of(rows), ("casing",))
        if b[2] == -1.4375 and 121 < b[0] < 167
    ]
    assert sorted(box_of(b) for b in door) == [
        (121.75, 125.25, -1.4375, -0.4375, SUB, SUB + 85.5),
        (121.75, 166.25, -1.4375, -0.4375, SUB + 82, SUB + 85.5),
        (162.75, 166.25, -1.4375, -0.4375, SUB, SUB + 85.5),
    ]


def test_the_roof_notches_the_siding_and_corner_boards_round_its_tails() -> None:
    """Each of the 26 tails is cut from the OSB it crossed and, after it,
    the siding (the 22 inner tails) or an eave wall's corner board (the 4
    end rafters, X 0..1.5 and 286.5..288, inside the boards' X -7/16 ..
    3 1/16 and 284 15/16 .. 288 7/16)."""
    rows = b7_today()
    names = {m.id: (m.role, m.name) for m in walls_of(rows)}
    hits: Counter[str] = Counter()
    for m in of_role(roof_of(rows), "cutter"):
        assert isinstance(m.feature, ExtrudeFeature)
        cut = m.feature.params.cut_bodies
        assert isinstance(cut, list)
        roles = [names[r.feature_id][0] for r in cut]
        assert roles[0] == "sheathing"
        outer = [r for r in roles if r != "sheathing"]
        assert len(outer) == 1
        hits[outer[0]] += 1
    assert hits == Counter({"siding": 22, "corner_board": 4})


def test_the_gables_are_sided_over_their_osb() -> None:
    """Roof 1.8.0: each end wall's lap over its gable OSB, Y -7/16 .. 192
    7/16 from the plate to the rafters' top plane, peaked at Y 96: the
    OSB's 5 705.185554 in² a gable, in the wall's product and allowance."""
    rows = b7_today()
    gables = of_role(roof_of(rows), "gable_siding")
    assert [m.name for m in gables] == ["e4/siding", "e2/siding"]
    found = sorted(box_of(b) for b in boxes(members_of(rows), ("gable_siding",)))
    top = PLATE - 7.25 / 3 + 96 / 2 + 7.25 * 1.25**0.5
    assert found == [
        box_of((-0.75, -0.4375, -0.4375, 192.4375, PLATE, top)),
        box_of((288.4375, 288.75, -0.4375, 192.4375, PLATE, top)),
    ]
    for m in gables:
        assert face_area(rows, m) == pytest.approx(5705.185554, abs=1e-6)
        assert m.metadata is not None and m.metadata.siding is not None
        assert m.metadata.siding.product == "fibre_cement_lap_8_25"
        assert m.metadata.material == "fibre_cement"


@pytest.mark.parametrize(
    ("finish", "thickness", "material"),
    [(VINYL, 0.044, "pvc"), (CEDAR, 15 / 32, "western_red_cedar")],
)
def test_vinyl_and_cedar_are_their_own_layer_and_trim(
    finish: dict[str, str], thickness: float, material: str
) -> None:
    rows = b7_today(walls=finish)
    members = members_of(rows)
    found = sorted(box_of(b) for b in boxes(members, ("siding",)))
    front = next(b for b in found if b[2] < 0)
    assert front[3] - front[2] == pytest.approx(thickness, abs=1e-9)
    for role in ("siding", "corner_board", "casing", "gable_siding"):
        assert {
            m.metadata.material for m in members if m.role == role and m.metadata
        } == {material}
    # The trim and the cuts do not move with the layer.
    assert sorted(box_of(b) for b in boxes(members, ("corner_board",))) == CORNER_BOXES
    assert sorted(box_of(b) for b in boxes(members, ("casing",))) == casing_boxes()


def test_the_allowance_is_the_walls_input() -> None:
    rows = b7_today(walls={"siding_waste_percent": 15})
    for m in [
        *of_role(walls_of(rows), "siding"),
        *of_role(roof_of(rows), "gable_siding"),
    ]:
        assert m.metadata is not None and m.metadata.siding is not None
        assert m.metadata.siding.waste_percent == 15


def test_none_is_1_4_0_member_for_member_and_1_5_0_appends_the_finish() -> None:
    """1.5.0 is 1.4.0's members in order, then per wall (clockwise from the
    front) its siding plane, its siding, its corner boards and its casing.
    With None, 1.4.0 exactly; and roof 1.8.0 on it is 1.7.0 exactly."""
    old = b7_today(walls=NONE)
    with today(), mock.patch.object(outline, "WALL", WALL_1_4):
        stored = house(
            rectangle(288, 192),
            [
                (
                    REGISTRY.latest(p.manifest.id),
                    n,
                    s,
                    {**r, "measure_from": "start", "size": SIZES[n]},
                )
                for p, n, s, r in b7_openings()
            ],
            B7_STUDS,
            B7_FLOOR,
            None,
        )
    assert walls_of(old) == walls_of(stored)
    assert roof_of(old) == roof_of(roofed(old[:-1], B7_GABLE, ROOF_1_7))
    new = walls_of(b7_today())
    assert new[: len(walls_of(old))] == walls_of(old)
    tail = new[len(walls_of(old)) :]
    roles = [m.role for m in tail if m.role != "siding_section"]
    e1 = ["siding_plane", "siding", "corner_board", "corner_board", *["casing"] * 11]
    e2 = ["siding_plane", "siding", "corner_board", "corner_board", *["casing"] * 4]
    e3 = ["siding_plane", "siding", "corner_board", "corner_board", *["casing"] * 4]
    assert roles == [*e1, *e2, *e3, *e2]


def test_on_a_slab_the_siding_starts_at_the_slab_top() -> None:
    """B8: the walls stand on the slab's top (Z 0); the siding starts there
    too, so the door's casing legs stand on its bottom edge and the door's
    cut-out is a notch in it, not a hole."""
    with (
        mock.patch.object(slab, "WALL_1_4", WALL_1_5),
        mock.patch.object(slab, "ROOF", ROOF_1_8),
    ):
        rows = slab.b8()
    members = members_of(rows)
    found = boxes(members, ("siding",))
    assert {(b[4], b[5]) for b in found} == {(0.0, 97.125)}
    front = next(m for m in members if m.role == "siding" and m.name == "e1/siding/0")
    loops = loops_of(section_of(rows, front))
    assert len(loops) == 3  # the two windows; the door notches the outline
    assert face_area(rows, front) == pytest.approx(
        281.875 * 97.125 - 2 * CASED["3040"] - CASED["3068"], abs=1e-6
    )


def test_on_a_crawl_space_the_siding_starts_at_the_stem_top() -> None:
    """B9: the floor stands on the stem wall's top; the siding starts at the
    floor's underside, the foundation top."""
    with mock.patch.object(outline, "WALL", WALL_1_5):
        rows = crawl.b9()
    found = boxes(members_of(rows), ("siding",))
    assert {(b[4], b[5]) for b in found} == {(0.0, PLATE)}


def test_an_l_sides_its_inside_corner_with_no_board() -> None:
    """The L (240 x 192, the notch at X 144..240, Y 120..192) on 2x4 walls
    with 7/16 OSB: 5 outside corners, 10 boards; at the inside corner (X 144,
    Y 120) the through wall (along X, the first line's way) runs its siding
    to the fitted wall's OSB face and the fitted wall's starts at the
    through wall's siding face, so they close the corner with no overlap."""
    with (
        mock.patch.object(outline, "WALL", WALL_1_5),
        mock.patch.object(outline, "ROOF", ROOF_1_8),
    ):
        rows = house(l_sketch(), [], OSB, None, {"style": "hip"})
    members = members_of(rows)
    assert len(boxes(members, ("corner_board",))) == 10
    found = sorted(box_of(b) for b in boxes(members, ("siding",)))
    # The notch's two faces: along X at Y 120 (outside +Y) and along Y at X
    # 144 (outside +X), meeting at the inside corner (144, 120).
    along_x = next(b for b in found if b[2] == 120 + S)
    along_y = next(b for b in found if b[0] == 144 + S)
    assert along_x[0] == 144 + S  # through: runs to the other's OSB face
    assert along_y[2] == 120 + S + LAP_T  # fitted: from the other's siding
    for a in found:
        for b in found:
            if a is not b:
                assert not all(
                    min(a[k + 1], b[k + 1]) - max(a[k], b[k]) > 1e-9 for k in (0, 2, 4)
                )


def test_a_line_wall_is_sided_end_to_end() -> None:
    """B2's front wall typed (144 long, its OSB, a 3068 door at 72): its
    siding runs U 0..144 from its base to its top, the door's three casing
    pieces cut out of it; no corner boards (a typed wall's corners are a
    later rung)."""
    raw = {
        "start_x_mm": 144 * IN,
        "direction_deg": 180.0,
        "length_mm": 144 * IN,
        **OSB,
    }
    wall_id = uuid.UUID("00000000-0000-0000-0000-0000000002f0")
    door = outline.opening(
        REGISTRY.latest("loft.door"),
        "Door",
        wall_id,
        {"offset_mm": 72 * IN, "measure_from": "start"},
        {wall_id: outline.envelope(WALL_1_5, raw)},
    )
    members = outline.expand(WALL_1_5, wall_id, raw, {}, (door,))
    found = boxes(members, ("siding",))
    assert [box_of(b) for b in found] == [(0.0, 144.0, -0.75, -0.4375, 0.0, 97.125)]
    assert not of_role(members, "corner_board")
    assert len(of_role(members, "casing")) == 3


def test_an_unsheathed_wall_takes_no_finish() -> None:
    """The finish goes over the sheathing: B7 with Exterior sheathing None
    is 1.4.0's walls exactly, and its roof sides no gable."""
    rows = b7_today(walls={"sheathing": "none"})
    stored = b7_today(walls={"sheathing": "none"}, wall=WALL_1_4)
    assert walls_of(rows) == walls_of(stored)
    assert not of_role(roof_of(rows), "gable_siding")


def test_b10s_partitions_change_nothing_outside() -> None:
    rows = b10(wall_plugin=WALL_1_5)
    found = sorted(box_of(b) for b in boxes(members_of(rows), ("siding",)))
    assert found == SIDING_BOXES


# --- Refusals -------------------------------------------------------------------------


def _window_at(offset: float, segment: str = "e1", width: float = 36.0) -> Rows:
    window = REGISTRY.latest("loft.window")
    with today():
        return house(
            rectangle(288, 192),
            [
                (
                    window,
                    "Window 1",
                    segment,
                    {
                        "offset_mm": offset * IN,
                        "measure_from": "start",
                        "size": "custom",
                        "width_mm": width * IN,
                    },
                )
            ],
            B7_STUDS,
            B7_FLOOR,
            None,
        )


def test_a_casing_on_a_corner_board_is_refused() -> None:
    """The front wall's first stud is U 0..1.5, so a 36 in window's king may
    stand on it from a centre of U 22.75; its casing (the centre less 21.5)
    then clears the corner board (U -7/16 .. 3 1/16) from U 24.5625 only."""
    _window_at(24.5625)
    with pytest.raises(PluginError, match=r"Window 1: its casing .* corner board"):
        _window_at(23.0)


def test_casings_that_overlap_are_refused() -> None:
    """Two windows framed king to king (rough openings 6 in apart) put their
    units 6.5 in apart, under the 7 in two casings take."""
    window = REGISTRY.latest("loft.window")
    raw = {"measure_from": "start", "size": "window_3040"}
    with today(), pytest.raises(PluginError, match="casing overlaps"):
        house(
            rectangle(288, 192),
            [
                (window, "Window 1", "e1", {**raw, "offset_mm": 60 * IN}),
                (window, "Window 2", "e1", {**raw, "offset_mm": (60 + 42.5) * IN}),
            ],
            B7_STUDS,
            B7_FLOOR,
            None,
        )


# --- The update, the manifest ---------------------------------------------------------


def test_an_update_from_1_4_0_takes_the_lap_default_and_adds_its_members() -> None:
    update = update_for("loft.wall", "1.4.0", REGISTRY)
    assert update is not None and update.to_version == "1.5.0"
    assert "fibre-cement lap" in update.summary
    stored = canonical_inputs(WALL_1_4.manifest, {"outline": ref(WALLS_ID)})
    moved = canonical_inputs(WALL_1_5.manifest, updated_inputs(update, stored))
    assert moved["exterior_finish"] == "fibre_cement_lap_8_25"
    assert moved["siding_waste_percent"] == 10
    for version in ("1.2.0", "1.3.0"):
        found = update_for("loft.wall", version, REGISTRY)
        assert found is not None and found.to_version == "1.5.0"


def test_the_update_names_what_it_adds_and_re_lays_nothing() -> None:
    before, after = walls_of(b7_today(walls=NONE)), walls_of(b7_today())
    effect = update_effect([("loft.wall", before, after)], REGISTRY)
    assert effect.adds == ("4 siding layers", "8 corner boards", "23 casing pieces")
    assert effect.relays == ()
    assert (
        effect.sentence == "Adds 4 siding layers, 8 corner boards and 23 casing pieces."
    )
    roof_update = update_for("loft.roof", "1.7.0", REGISTRY)
    assert roof_update is not None and roof_update.to_version == "1.8.0"
    rows = b7_today()
    stored = roof_of(roofed(rows[:-1], B7_GABLE, ROOF_1_7))
    effect = update_effect([("loft.roof", stored, roof_of(rows))], REGISTRY)
    assert (effect.adds, effect.relays) == (("2 gable siding layers",), ())


def test_new_walls_are_1_5_0_and_offer_the_finish() -> None:
    assert REGISTRY.latest("loft.wall").manifest.version == "1.5.0"
    assert REGISTRY.latest("loft.roof").manifest.version == "1.8.0"
    inputs = {i.name: i for i in WALL_1_5.manifest.inputs}
    old = [i.name for i in WALL_1_4.manifest.inputs]
    assert [n for n in inputs if n not in old] == [
        "exterior_finish",
        "siding_waste_percent",
    ]
    finish = inputs["exterior_finish"]
    assert isinstance(finish, ChoiceInput)
    assert finish.default == "fibre_cement_lap_8_25"
    assert [o.label for o in finish.options] == [
        "Lap, fibre cement 8-1/4 in at 7 in",
        "Vinyl, double 4 in",
        "Cedar bevel 1/2 x 8 at 6-1/4 in",
        "None",
    ]
    waste = inputs["siding_waste_percent"]
    assert isinstance(waste, CountInput)
    assert (waste.default, waste.minimum, waste.maximum) == (10, 0, 30)
    roles = {r.role: r.title for r in WALL_1_5.manifest.members}
    assert (roles["siding"], roles["corner_board"], roles["casing"]) == (
        "Siding",
        "Corner board",
        "Casing",
    )
    assert ROOF_1_8.manifest.inputs == ROOF_1_7.manifest.inputs
    assert {r.role for r in ROOF_1_8.manifest.members} - {
        r.role for r in ROOF_1_7.manifest.members
    } == {"gable_siding"}
    assert {k for k, v in ROLE_SYSTEMS.items() if v == "siding"} == {
        ("loft.wall", "siding"),
        ("loft.wall", "corner_board"),
        ("loft.wall", "casing"),
        ("loft.roof", "gable_siding"),
    }


# --- The golden and the kernel's cases ------------------------------------------------


def metadata_of(rows: Rows) -> list[CutListMember]:
    names = {
        **titles(),
        **{
            (p.manifest.id, r.role): r.title
            for p in (
                REGISTRY.latest("loft.floor"),
                WALL_1_5,
                ROOF_1_8,
                REGISTRY.latest("loft.door"),
                REGISTRY.latest("loft.window"),
            )
            for r in p.manifest.members
        },
    }
    out: list[CutListMember] = []
    for _, env, members in rows:
        plugin_id = getattr(getattr(env, "params", None), "plugin_id", None)
        for m in members:
            if m.metadata is not None:
                out.append(
                    CutListMember(
                        feature_id=m.id,
                        role=m.role,
                        title=names[(str(plugin_id), m.role)],
                        plugin_id=plugin_id,
                        metadata=m.metadata,
                    )
                )
    return out


def golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """B7 drawn today, every default kept (fibre-cement lap)."""
    rows = b7_today()
    request = request_of(rows).model_copy(update={"part_id": PART_ID})
    return request, metadata_of(rows)


def _finish_counts(rows: Rows) -> dict[str, int]:
    found = Counter(m.role for m in members_of(rows))
    return {r: found[r] for r in (*FINISH, "gable_siding")}


def built_cases() -> Iterator[tuple[str, Rows]]:
    moved = rectangle(192, 288).model_dump(mode="json")
    for e in moved["params"]["entities"]:
        if e["id"] == "origin":
            e["position"] = {"x": 24 * IN, "y": 36 * IN}
    yield "b7-vinyl", b7_today(walls=VINYL)
    yield "b7-cedar", b7_today(walls=CEDAR)
    yield "b7-336", b7_today(336)
    yield "b7-8-12", b7_today(roof={**B7_GABLE, "pitch": "rise_8"})
    yield "b7-unsheathed", b7_today(walls={"sheathing": "none"})
    with (
        mock.patch.object(outline, "WALL", WALL_1_5),
        mock.patch.object(outline, "ROOF", ROOF_1_8),
    ):
        yield "l-hip", house(l_sketch(), [], OSB, None, {"style": "hip"})
        yield (
            "along-y-moved",
            house(
                SketchFeature.model_validate(moved),
                [],
                B7_STUDS,
                {},
                {"slope_walls": ["e2", "e4"], **B7_ROOF},
            ),
        )
        yield "b9", crawl.b9()
    with (
        mock.patch.object(slab, "WALL_1_4", WALL_1_5),
        mock.patch.object(slab, "ROOF", ROOF_1_8),
    ):
        yield "b8", slab.b8()
    yield "b10", b10(wall_plugin=WALL_1_5)


def cases() -> str:
    """B7 in vinyl and cedar, at 28 ft, at 8/12 and unsheathed, the L with a
    hip, B7 turned off the origin (its gables through walls), B9 on its
    crawl space, B8 on its slab and B10 with its partitions; each with its
    counts."""
    out = [
        {
            "name": name,
            "bodies": sum(1 for m in members_of(rows) if m.metadata is not None),
            **_finish_counts(rows),
            "request": request_of(rows).model_dump(mode="json"),
        }
        for name, rows in built_cases()
    ]
    return json.dumps(out, separators=(",", ":"), sort_keys=True)


def test_the_golden_is_the_plugins_expansion() -> None:
    request, metadata = golden()
    folder = GOLDENS / GOLDEN
    assert (folder / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (folder / "members.json").read_text() == members_json(metadata)


def test_the_golden_is_b7_today_with_its_finish() -> None:
    """b7-update-all's 317 bodies (the finish and the gables' siding
    included) with the 12 unit bodies: 329."""
    _, metadata = golden()
    assert len(metadata) == 317 + 12 == 329
    count = Counter(m.title for m in metadata)
    assert (count["Siding"], count["Corner board"], count["Casing"]) == (6, 8, 23)


def test_the_kernel_cases_are_the_plugins_expansion() -> None:
    assert gzip.decompress(CASES.read_bytes()).decode() == cases()


if __name__ == "__main__":
    request, metadata = golden()
    (GOLDENS / GOLDEN).mkdir(parents=True, exist_ok=True)
    (GOLDENS / GOLDEN / "model.json").write_text(
        request.model_dump_json(indent=2) + "\n"
    )
    (GOLDENS / GOLDEN / "members.json").write_text(members_json(metadata))
    sys.stdout.write(f"{GOLDEN}: {len(request.features)} features\n")
    CASES.write_bytes(gzip.compress(cases().encode(), mtime=0))
    sys.stdout.write(f"{CASES.name}\n")
