"""SECOND-FLOOR acceptance: B7 with a second storey and a stair, on STEP.

``goldens/b7-second-floor`` is B7 drawn today (floor 1.4.0 on its outline,
walls 1.5.0 on it with B7's door and five windows 1.5.0), then a second
``loft.floor`` 1.4.0 on those walls with a framed stairwell, a second storey
of ``loft.wall`` 1.5.0 on it (no openings), the ``loft.roof`` 1.8.0 on those
walls, and a free ``loft.stair`` 1.0.0 from floor 1 through the well.
``model.json`` and ``members.json`` are pinned to the plugins by
``packages/loft-plugins/tests/test_second_floor.py``. Geometry never learns
plugins exist, so this module imports nothing from them.

Checked against an INDEPENDENT script typed from
``docs/reference-parts/buildings.md`` B7 and the IRC, sharing no code with
the plugins: the storey below is ``test_outline_b7``'s B7 with
``test_opening_update_b7``'s plies and spacers and its OSB no longer notched
(the roof went up); floor 2, the well, the upper walls and the stair are
typed here; the roof is ``test_outline_b7``'s rafters and ridge,
``test_ceiling_joists_b7``'s joists and ``test_gable_ends_b7``'s gable ends,
every one moved up 107.09375 in, and the upper walls' OSB notched round the
tails:

1. the STEP's 470 solids are the script's, solid for solid, and the volume
   is B7 today's (b7-update-all, 299 949.387649 in^3: moving the roof up
   moves its 26 notches from the lower OSB to the upper, so it is
   unchanged) plus floor 2 (61 979.625 framing, 35 992.125 subfloor), the
   upper walls and the stair, each by hand;
2. interference none, every pair probed exactly: the stair's head on the far
   header's face, the trimmers beside the doubled layout joists, the headers
   between the trimmers and the tails on the headers, face to face;
3. the cut list: under Floor, 36 joists of 189, 4 tail joists of 31.5, 2
   trimmers of 189 and 4 headers of 43.5 (2x10); under Stairs, 3 stringers
   one piece each, 26 treads, 13 risers, the rail and 3 posts;
4. each body weighs by its member material.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_second_floor_b7.py``.
"""

import dataclasses
import functools
import itertools
import json
import math
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from build123d import Pos, Solid
from geometry.kernel import measure_shape
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMember,
    CutListResponse,
    cut_list_response,
    part_pieces,
)
from loft_wire.price_book import EMPTY_PRICE_BOOK

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_ceiling_joists_b7 as joists
import test_gable_ends_b7 as gables
import test_opening_update_b7 as openings
import test_outline_b7 as b7
import test_update_all_b7 as today

NAME = "b7-second-floor"
IN = b7.IN
SPF, PT, OSB_M, PLY_M = b7.SPF, b7.PT, b7.OSB_M, b7.PLY_M
Member = b7.Member

# --- B7's second storey, typed from buildings.md (inches) ------------------------

PLATE = b7.PLATE  # 108.59375: floor 2's rims and joists bear here
RAISE = PLATE - b7.SILL_T  # 107.09375: floor 1 less its sills, raised
JOIST_TOP = PLATE + b7.JOIST  # 117.84375
SUB2 = JOIST_TOP + b7.PLY  # 118.5625: the upper walls' base
W, L = b7.W, 288.0
#: The well, clear: X 18.25..61.75 (between the joists at 16 and 64, each
#: doubled inside), Y 36..156.
WELL = (18.25, 61.75, 36.0, 156.0)
CUT = (32.0, 48.0)  # the layout joists the well cuts


def floor2_boxes() -> list[tuple[str, str, b7.Bounds]]:
    z = (PLATE, JOIST_TOP)
    x0, x1, y0, y1 = WELL
    out: list[tuple[str, str, b7.Bounds]] = [
        ("Rim", SPF, (0, L, 0, 1.5, *z)),
        ("Rim", SPF, (0, L, W - 1.5, W, *z)),
    ]
    out += [
        ("Joist", SPF, (c - 0.75, c + 0.75, 1.5, W - 1.5, *z))
        for c in b7.layout(L, 16.0)
        if c not in CUT
    ]
    out += [
        ("Tail joist", SPF, (c - 0.75, c + 0.75, a, b, *z))
        for c in CUT
        for a, b in ((1.5, y0 - 3), (y1 + 3, W - 1.5))
    ]
    out += [
        ("Trimmer", SPF, (x0 - 1.5, x0, 1.5, W - 1.5, *z)),
        ("Trimmer", SPF, (x1, x1 + 1.5, 1.5, W - 1.5, *z)),
    ]
    out += [
        ("Header", SPF, (x0, x1, a, a + 1.5, *z))
        for a in (y0 - 3, y0 - 1.5, y1, y1 + 1.5)
    ]
    return out


def subfloor2() -> list[Solid]:
    """Floor 1's panels (48 rows along Y, 96 across, every other row from a
    48), each less the well: the one it crosses in row 2 is two pieces."""
    well = b7.box((*WELL, JOIST_TOP, SUB2))
    out: list[Solid] = []
    for row, y0 in enumerate(range(0, int(W), 48)):
        edges = [0.0, *range(48 if row % 2 else 96, int(L), 96), L]
        for x0, x1 in itertools.pairwise(edges):
            panel = b7.box((x0, x1, y0, y0 + 48, JOIST_TOP, SUB2))
            if panel.bounding_box().overlaps(well.bounding_box()):  # pyright: ignore[reportUnknownMemberType]
                out += list(panel.cut(well).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            else:
                out.append(panel)
    return out


def up(solid: Solid) -> Solid:
    moved = Pos(0, 0, RAISE * IN) * solid
    assert isinstance(moved, Solid)
    return moved


def upper_walls() -> list[b7.Wall]:
    return [dataclasses.replace(w, openings=()) for w in b7.walls(L)]


def upper_framing() -> list[tuple[str, str, b7.Bounds]]:
    out: list[tuple[str, str, b7.Bounds]] = []
    for wall in upper_walls():
        for member, material, *local in b7.wall_frame(wall.length, ()):  # type: ignore[misc]
            x0, x1, y0, y1, z0, z1 = wall.box(*local)  # pyright: ignore[reportUnknownArgumentType]
            out.append((member, material, (x0, x1, y0, y1, z0 + RAISE, z1 + RAISE)))  # pyright: ignore[reportUnknownArgumentType]
    return out


def upper_panels() -> list[b7.Bounds]:
    """48 in from each wall's start, full height; the sides' corner rips."""
    out: list[b7.Bounds] = []
    for wall in upper_walls():
        cuts = [*range(0, math.ceil(wall.length), 48), wall.length]
        spans = list(itertools.pairwise(cuts))
        if wall.length == b7.SIDE:
            spans += [(-b7.D - b7.OSB, 0.0), (b7.SIDE, b7.SIDE + b7.D + b7.OSB)]
        for u0, u1 in spans:
            x0, x1, y0, y1, z0, z1 = wall.box(u0, u1, -b7.OSB, 0, 0, b7.H)
            out.append((x0, x1, y0, y1, z0 + RAISE, z1 + RAISE))
    return out


# --- The stair (IRC R311.7, typed; STAIRS' conventions) ----------------------------

N = 14
R = RAISE / N
T = 10.0  # tread depth, nosing to nosing
D = 11.25  # 2x12 stringers
TREAD_T, BOARD, GAP, RISER_T = 1.0, 5.5, 0.125, 0.75  # 5/4x6, 1x8
C = RISER_T + 2 * BOARD + GAP  # each nosing past its riser line: 11.875
TOP_LINE = T - C  # -1.875: the head, plumb on the far header's face
#: The stair runs -Y with its head on the far header's face (Y 156), so its
#: top nosing is 1.875 in front of it, at Y 154.125.
NOSE = WELL[3] + TOP_LINE
BOTTOM = b7.BASE  # floor 1's subfloor: 11.46875
X0 = 40.0 - 18.0  # 36 wide, centred on X 40
SLOPE = math.hypot(R, T)


def back(j: int) -> float:
    return TOP_LINE + (N - 1 - j) * T


def bottom_edge(u: float) -> float:
    top = N * R - TREAD_T - (u - TOP_LINE) * R / T
    return top - D * SLOPE / T


def stringer_side() -> list[tuple[float, float]]:
    """(u, z from the stair's foot): the head's top, each tooth down, the
    level foot, the bottom edge back up to the plumb head."""
    pts: list[tuple[float, float]] = []
    for j in range(N - 1, 0, -1):
        pts += [(back(j), j * R - TREAD_T), (back(j) + T, j * R - TREAD_T)]
    foot = back(1) + T
    u0 = TOP_LINE + (N * R - TREAD_T - D * SLOPE / T) * T / R
    pts += [(foot, 0.0), (u0, 0.0), (TOP_LINE, bottom_edge(TOP_LINE))]
    return pts


def y(u: float) -> float:
    return NOSE - u


RUN = (N - 1) * T  # 130
BAYS = math.ceil((RUN - 3.5) / 72.0)  # 2: posts at u 0, 63.25, 126.5


def rail_top(u: float) -> float:
    return RAISE - u * R / T + 36.0


def stair() -> list[Member]:
    out: list[Member] = []
    side = [(y(u), BOTTOM + z) for u, z in stringer_side()]
    for k in range(3):
        left = X0 + 17.25 * k
        out.append(Member("Stringer", PT, b7.prism_x(side, left, left + 1.5)))
    for j in range(1, N):
        for b in range(2):
            u = back(j) + RISER_T + b * (BOARD + GAP)
            z = BOTTOM + j * R
            out.append(
                Member("Tread", PT, b7.box((X0, X0 + 36, y(u + BOARD), y(u), z - 1, z)))
            )
    for k in range(1, N):
        u = back(k) + T
        z0, z1 = BOTTOM + (k - 1) * R, BOTTOM + k * R - TREAD_T
        out.append(
            Member("Riser", PT, b7.box((X0, X0 + 36, y(u + RISER_T), y(u), z0, z1)))
        )
    # Left, looking down -Y, is +X: the rail over the +X stringer, its posts
    # outside it.
    v = 1.5 * SLOPE / T
    rail = [
        (y(0), BOTTOM + rail_top(0) - v),
        (y(0), BOTTOM + rail_top(0)),
        (y(RUN), BOTTOM + rail_top(RUN)),
        (y(RUN), BOTTOM + rail_top(RUN) - v),
    ]
    out.append(Member("Handrail", PT, b7.prism_x(rail, X0 + 34.5, X0 + 36)))
    for k in range(BAYS + 1):
        u0 = (RUN - 3.5) * k / BAYS
        post = (X0 + 36, X0 + 39.5, y(u0 + 3.5), y(u0), BOTTOM, BOTTOM + rail_top(u0))
        out.append(Member("Handrail post", PT, b7.box(post)))
    return out


def shoelace(points: list[tuple[float, float]]) -> float:
    n = len(points)
    return (
        abs(
            sum(
                points[i][0] * points[(i + 1) % n][1]
                - points[(i + 1) % n][0] * points[i][1]
                for i in range(n)
            )
        )
        / 2
    )


def stair_volume() -> float:
    stringers = 3 * 1.5 * shoelace(stringer_side())
    treads = 2 * (N - 1) * 36 * BOARD * TREAD_T
    risers = (N - 1) * 36 * RISER_T * (R - TREAD_T)
    rail = 1.5 * RUN * 1.5 * SLOPE / T
    posts = sum(3.5 * 3.5 * rail_top((RUN - 3.5) * k / BAYS) for k in range(BAYS + 1))
    return stringers + treads + risers + rail + posts


# --- The house ---------------------------------------------------------------------


def script() -> list[Member]:
    """Every body: the storey below (B7's floor, framing, plies, spacers and
    OSB with its openings), floor 2, the upper walls and their OSB notched
    round the raised tails, the raised roof, and the stair."""
    tails = [up(s) for s in b7.rafters(L)]
    out = [
        Member(m, mat, b7.box(b))
        for m, mat, b in b7.floor_boxes(L) + b7.framing_boxes(L)
    ]
    for panel, holes in b7.panel_boxes(L):
        solid = b7.box(panel)
        for hole in holes:
            solid = solid.cut(b7.box(hole)).solids()[0]  # pyright: ignore[reportUnknownMemberType]
        out.append(Member("Sheathing", OSB_M, solid))
    out += [Member(m, mat, b7.box(b)) for m, mat, b in openings.added_boxes()]
    out += [Member(m, mat, b7.box(b)) for m, mat, b in floor2_boxes()]
    out += [Member("Subfloor", PLY_M, s) for s in subfloor2()]
    out += [Member(m, mat, b7.box(b)) for m, mat, b in upper_framing()]
    for panel in upper_panels():
        solid = b7.box(panel)
        for tail in tails:
            if solid.bounding_box().overlaps(tail.bounding_box()):  # pyright: ignore[reportUnknownMemberType]
                solid = solid.cut(tail).solids()[0]  # pyright: ignore[reportUnknownMemberType]
        out.append(Member("Sheathing", OSB_M, solid))
    out += [Member("Rafter", SPF, s) for s in tails]
    out.append(Member("Ridge", SPF, up(b7.box(b7.ridge(L)))))
    out += [Member(m.member, m.material, up(m.solid)) for m in joists.joists()]
    out += [Member(m.member, m.material, up(m.solid)) for m in gables.gable_members()]
    return [*out, *stair()]


def _volume(boxes: list[tuple[str, str, b7.Bounds]]) -> Fraction:
    exact = Fraction(0)
    for _, _, (x0, x1, y0, y1, z0, z1) in boxes:
        exact += (
            (Fraction(x1) - Fraction(x0))
            * (Fraction(y1) - Fraction(y0))
            * (Fraction(z1) - Fraction(z0))
        )
    return exact


def floor2_framing() -> Fraction:
    return _volume(floor2_boxes())


def floor2_subfloor() -> Fraction:
    return (Fraction(288 * 192) - Fraction(87, 2) * 120) * Fraction(23, 32)


def upper_volume() -> Fraction:
    osb = sum(
        (Fraction(x1) - Fraction(x0))
        * (Fraction(y1) - Fraction(y0))
        * (Fraction(z1) - Fraction(z0))
        for x0, x1, y0, y1, z0, z1 in upper_panels()
    )
    return _volume(upper_framing()) + osb


def analytic_volume() -> float:
    """B7 today's, floor 2's, the upper walls' and the stair's (in^3)."""
    second = floor2_framing() + floor2_subfloor() + upper_volume()
    return today.analytic_volume() + float(second) + stair_volume()


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return b7._step_solids(tmp_path_factory, NAME)  # pyright: ignore[reportPrivateUsage]


def test_the_storey_numbers_are_buildings_mds() -> None:
    """Floor 2's joists Z 108.59375..117.84375 and finished floor 118.5625;
    the upper walls to 215.6875; the framing 61 979.625 in^3 (floor 1's
    57 817.125 less 2 joists, plus 2 trimmers, 4 tails and 4 headers) and
    the subfloor 50 076 x 23/32; the stair's 14 risers of 7.649554 and 13
    treads of 10 from Y 26 to the far header's face at Y 156."""
    assert (PLATE, JOIST_TOP, SUB2, SUB2 + b7.H) == (
        108.59375,
        117.84375,
        118.5625,
        215.6875,
    )
    assert RAISE == 107.09375
    section = Fraction(3, 2) * Fraction(37, 4)  # 2x10: 13.875 in^2
    assert floor2_framing() == section * (
        2 * 288 + 17 * 189 + 2 * 189 + 4 * Fraction(63, 2) + 4 * Fraction(87, 2)
    )
    assert float(floor2_framing()) == 61979.625
    assert float(floor2_framing() - section * (2 * 288 + 19 * 189)) == 4162.5
    assert float(floor2_subfloor()) == 35992.125
    assert round(R, 6) == 7.649554
    assert (TOP_LINE, NOSE, y(back(1) + T)) == (-1.875, 154.125, 26.0)
    assert round(today.analytic_volume(), 6) == 299949.387649


def test_the_headroom_is_80_39_under_the_near_header() -> None:
    """Under the near header's face (Y 36) the nosing line is 2.1875 risers
    up; the ceiling there is floor 2's underside, 97.125 above floor 1."""
    u = NOSE - WELL[2]
    nosing = RAISE - u * R / T
    assert u == 118.125
    assert PLATE - BOTTOM == 97.125
    assert (PLATE - BOTTOM) - nosing == 80.3916015625


def test_the_step_is_the_independent_script(step_solids: list[Solid]) -> None:
    mine = script()
    assert len(step_solids) == len(mine) == 470
    assert b7._unmatched(step_solids, [m.solid for m in mine]) == []  # pyright: ignore[reportPrivateUsage]
    volume = sum(float(measure_shape(s).volume) for s in step_solids) / IN**3
    assert volume == pytest.approx(analytic_volume(), abs=1e-4)
    scripted = sum(float(measure_shape(m.solid).volume) for m in mine) / IN**3
    assert scripted == pytest.approx(analytic_volume(), abs=1e-4)


def test_nothing_interferes(step_solids: list[Solid]) -> None:
    assert b7._overlapping(step_solids) == []  # pyright: ignore[reportPrivateUsage]


# --- 3. The cut list ---------------------------------------------------------------


@functools.cache
def cut_list() -> CutListResponse:
    """Built once: the part takes about a minute to evaluate."""
    request = b7._request(NAME)  # pyright: ignore[reportPrivateUsage]
    response = b7.client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    extents = BodyExtentsResult.model_validate_json(response.content)
    raw: list[dict[str, Any]] = json.loads(
        (b7.GOLDENS / NAME / "members.json").read_text()
    )
    members = [CutListMember.model_validate(item) for item in raw]
    return cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name=NAME,
        length_unit="in",
        pieces=part_pieces(extents, members, request.materials),
        price_book=EMPTY_PRICE_BOOK,
    )


def test_the_floor_lists_its_joists_tails_trimmers_and_headers() -> None:
    lines = [line for line in cut_list().lines if line.system == "floor"]
    got = {
        (line.member, line.profile, round(line.length_mm / IN, 6)): line.quantity
        for line in lines
        if line.member in ("Joist", "Tail joist", "Trimmer", "Header")
    }
    assert got == {
        ("Joist", "2x10", 189.0): 19 + 17,
        ("Tail joist", "2x10", 31.5): 4,
        ("Trimmer", "2x10", 189.0): 2,
        ("Header", "2x10", 43.5): 4,
    }
    sills = [line for line in lines if line.member == "Sill"]
    assert sum(line.quantity for line in sills) == 4  # floor 1's only


def stringer_length() -> float:
    head = stringer_side()[0]
    foot = (back(1) + T, 0.0)
    return ((foot[0] - head[0]) * T + (head[1] - foot[1]) * R) / SLOPE


def test_the_stair_is_listed_under_stairs() -> None:
    """3 stringers one piece each (the head's top to the foot's toe along
    the slope), 26 treads and 13 risers of 36, the rail (its run along the
    slope plus its plumb cut) and 3 posts."""
    lines = [line for line in cut_list().lines if line.system == "stairs"]

    def stock(inches: float) -> int:
        return next(ft for ft in (8, 10, 12, 14, 16, 18, 20) if ft * 12 >= inches)

    rail = RUN * SLOPE / T + 1.5 * R / T
    posts = sorted(rail_top((RUN - 3.5) * k / BAYS) for k in range(BAYS + 1))
    want = [
        ("Stringer", "2x12", 3, round(stringer_length(), 4), stock(stringer_length())),
        ("Tread", "5/4x6", 26, 36.0, 8),
        ("Riser", "1x8", 13, 36.0, 8),
        ("Handrail", "2x2", 1, round(rail, 4), stock(rail)),
        *[("Handrail post", "4x4", 1, round(p, 4), stock(p)) for p in posts],
    ]
    got = [
        (
            line.member,
            line.profile,
            line.quantity,
            round(line.length_mm / IN, 4),
            line.stock_length_ft,
        )
        for line in lines
    ]
    assert got == want
    assert {line.member: line.one_piece for line in lines}["Stringer"]


def test_every_body_weighs_by_its_member_material() -> None:
    request = b7._request(NAME)  # pyright: ignore[reportPrivateUsage]
    response = b7.client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    want = sum(
        float(measure_shape(m.solid).volume) * b7.DENSITY[m.material] * 1e-6
        for m in script()
    )
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


def expected_numbers() -> dict[str, Any]:
    """As test_update_all_b7.expected_numbers, over this script."""
    mine = script()
    area = 0.0
    moments = [0.0, 0.0, 0.0]
    mass = 0.0
    mass_moments = [0.0, 0.0, 0.0]
    vertices = triangles = faces = edges = 0
    total = 0.0
    for m in mine:
        props = measure_shape(m.solid)
        v = float(props.volume)
        total += v
        area += float(props.surface_area)
        c = props.centroid
        density = b7.DENSITY[m.material] * 1e-6
        for k, value in enumerate((c.x, c.y, c.z)):
            moments[k] += v * value
            mass_moments[k] += v * density * value
        mass += v * density
        faces += len(m.solid.faces())
        edges += len(m.solid.edges())
        for face in m.solid.faces():
            loops = face.wires()
            n = sum(len(w.edges()) for w in loops)
            vertices += n
            triangles += n + 2 * (len(loops) - 1) - 2
    bb = [m.solid.bounding_box() for m in mine]
    return {
        "volume": analytic_volume() * IN**3,
        "surface_area": area,
        "centroid": [x / total for x in moments],
        "mass_g": mass,
        "center_of_mass": [x / mass for x in mass_moments],
        "bbox": [
            min(b.min.X for b in bb),
            min(b.min.Y for b in bb),
            min(b.min.Z for b in bb),
            max(b.max.X for b in bb),
            max(b.max.Y for b in bb),
            max(b.max.Z for b in bb),
        ],
        "topology": {"faces": faces, "edges": edges, "shells": len(mine)},
        "mesh": {"vertices": vertices, "triangles": triangles},
    }


if __name__ == "__main__":
    json.dump(expected_numbers(), sys.stdout, indent=2)
    sys.stdout.write("\n")
