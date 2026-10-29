"""STAIRS acceptance: B1's stair and the free interior stair, on STEP.

``goldens/b1-stair-30`` is B1 (``loft.deck`` 1.2.0, every default) with a
``loft.stair`` 1.0.0 centred on its rim at X 96; ``b1-stair-30-closed`` the
same with closed risers; ``b1-stair-36`` the deck at a 36 in decking top with
its stair re-laid; ``free-stair-107`` a free stair of 107.09375 in with closed
risers. ``model.json`` and ``members.json`` are pinned to the plugins by
``packages/loft-plugins/tests/test_stair.py``. Geometry never learns plugins
exist, so this module imports nothing from them.

Checked against an independent build123d script typed here from
``docs/reference-parts/buildings.md`` B1 and the IRC, sharing no code with
the plugins:

1. the STEP is the script's solids, solid for solid (the deck's boxes and
   piers, then the stringers' notched profiles, the treads, risers, the
   handrail and its posts), and its volume is the hand sum;
2. the throat, measured on each exported stringer as its least depth under a
   notch, is ``11.25 - R T / sqrt(R^2 + T^2)``;
3. interference none, every pair whose boxes meet probed exactly, the deck's
   members against the stair's among them;
4. the cut list lists the stair under Stairs: stringers one piece of stock
   each (NO-SPLICE-SPANS), treads and risers as lumber, the handrail and its
   posts.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_stair_b1.py``.
"""

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from build123d import Cylinder as _Cylinder
from build123d import GeomType, Pos, Solid, Vector
from fastapi.testclient import TestClient
from geometry.kernel import measure_shape
from geometry.main import app
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMember,
    CutListResponse,
    cut_list_response,
    part_pieces,
)
from loft_wire.features import EvaluateTreeRequest
from loft_wire.price_book import EMPTY_PRICE_BOOK

sys.path.insert(0, str(Path(__file__).parent))
from test_outline_b7 import (
    IN,
    _overlapping,  # pyright: ignore[reportPrivateUsage]
    _step_solids,  # pyright: ignore[reportPrivateUsage]
    _unmatched,  # pyright: ignore[reportPrivateUsage]
    box,
    prism_x,
)

client = TestClient(app)
GOLDENS = Path(__file__).resolve().parent.parent / "goldens"

PT = "southern_pine_pt"
CONCRETE = "concrete"
#: kg/m^3, the library's (loft_wire.materials), typed.
DENSITY = {PT: 582.0, CONCRETE: 2400.0}

# --- B1, typed from buildings.md (inches) ------------------------------------------

WIDTH, DEPTH = 192.0, 144.0
JOIST = 9.25  # 2x10
BOARD, GAP = 5.5, 0.125  # 5/4x6 decking, 1/8 in gaps
BOARDS = 26
#: The last board's far edge, 2.125 past the rim: the stair's top nosing.
NOSE = 25 * (BOARD + GAP) + BOARD  # 146.125
JOIST_X = [0.75, *(16.0 * n for n in range(1, 12)), 191.25]
POST_X = [2.75, 96.0, 189.25]


@dataclass(frozen=True)
class Member:
    member: str
    material: str
    solid: Solid


def deck(height: float) -> list[Member]:
    """B1's members at a decking top of *height*: everything over the posts
    rides up with it, the posts run grade to the beam."""
    top = height - 1.0  # the joists' top, under the 1 in decking
    joist = (top - JOIST, top)
    beam = (top - JOIST - JOIST, top - JOIST)
    out = [
        Member("Ledger", PT, box((0, WIDTH, 0, 1.5, *joist))),
        Member("Rim", PT, box((0, WIDTH, 142.5, 144, *joist))),
        Member("Beam", PT, box((0, WIDTH, 124.5, 126, *beam))),
        Member("Beam", PT, box((0, WIDTH, 126, 127.5, *beam))),
    ]
    out += [
        Member("Joist", PT, box((x - 0.75, x + 0.75, 1.5, 142.5, *joist)))
        for x in JOIST_X
    ]
    out += [
        Member("Post", PT, box((x - 2.75, x + 2.75, 123.25, 128.75, 0, beam[0])))
        for x in POST_X
    ]
    out += [
        Member(
            "Footing",
            CONCRETE,
            (Pos(x * IN, 126 * IN, -6 * IN) * _Cylinder(8 * IN, 12 * IN)).solid(),
        )
        for x in POST_X
    ]
    out += [
        Member(
            "Deck",
            PT,
            box((0, WIDTH, (BOARD + GAP) * i, (BOARD + GAP) * i + BOARD, top, height)),
        )
        for i in range(BOARDS)
    ]
    return out


# --- The stair, typed from STAIRS (inches) -----------------------------------------

T = 11.0  # tread depth, nosing to nosing
D = 11.25  # 2x12
TREAD_T = 1.0  # 5/4x6
PACK = 2 * BOARD + GAP  # two boards a tread: 11.125
RISER_T = 0.75  # 1x8
WIDE = 36.0


@dataclass(frozen=True)
class Stair:
    """A straight stair running +Y from its top nosing at (X *centre*, Y
    *nose*), rise *rise* from Z 0; hung on a rim *overhang* behind the nosing
    (under 1 in decking), or free (``overhang`` None)."""

    rise: float
    centre: float
    nose: float
    overhang: float | None
    closed: bool

    @property
    def n(self) -> int:
        return math.ceil(self.rise / 7.75)

    @property
    def r(self) -> float:
        return self.rise / self.n

    @property
    def c(self) -> float:
        """Each nosing past its riser line: the boards, behind a riser board."""
        return PACK + (RISER_T if self.closed else 0.0)

    @property
    def top_line(self) -> float:
        """The top riser line (u from the nosing): T - c."""
        return T - self.c

    def back(self, j: int) -> float:
        return self.top_line + (self.n - 1 - j) * T

    @property
    def length(self) -> float:
        return math.hypot(self.r, T)

    def top_edge(self, u: float) -> float:
        """Through the tooth points (back(j) + T, j r - 1)."""
        return self.n * self.r - TREAD_T - (u - self.top_line) * self.r / T

    def bottom_edge(self, u: float) -> float:
        return self.top_edge(u) - D * self.length / T

    def stringer(self) -> list[tuple[float, float]]:
        """(u, z): head, teeth from the top, foot (on grade), back up."""
        n, r = self.n, self.r
        pts: list[tuple[float, float]] = []
        if self.overhang is not None:
            head = -self.overhang
            # The head is cut level under the decking (Z rise - 1) back to
            # the rim face, where the top edge stands above it.
            assert self.top_edge(head) > self.rise - 1
            pts += [(head, self.rise - 1), (self.top_line, self.rise - 1)]
        else:
            head = self.top_line
        for j in range(n - 1, 0, -1):
            pts += [(self.back(j), j * r - 1), (self.back(j) + T, j * r - 1)]
        foot = self.back(1) + T
        # The bottom edge meets grade at u0 (the level foot cut's back end).
        u0 = self.top_line + (n * r - 1 - D * self.length / T) * T / r
        pts += [(foot, 0.0), (u0, 0.0), (head, self.bottom_edge(head))]
        return pts

    @property
    def throat(self) -> float:
        return D - self.r * T / self.length

    def y(self, u: float) -> float:
        return self.nose + u

    def members(self) -> list[Member]:
        x0 = self.centre - WIDE / 2
        n, r = self.n, self.r
        out: list[Member] = []
        side = [(self.y(u), z) for u, z in self.stringer()]
        # Three stringers, outer faces flush, 17.25 o.c.
        for k in range(3):
            left = x0 + 17.25 * k
            out.append(Member("Stringer", PT, prism_x(side, left, left + 1.5)))
        start = RISER_T if self.closed else 0.0
        for j in range(1, n):
            for b in range(2):
                y0 = self.y(self.back(j) + start + b * (BOARD + GAP))
                out.append(
                    Member(
                        "Tread",
                        PT,
                        box((x0, x0 + WIDE, y0, y0 + BOARD, j * r - 1, j * r)),
                    )
                )
        if self.closed:
            last = n if self.overhang is not None else n - 1
            for k in range(1, last + 1):
                u = self.back(k) + T if k < n else self.top_line
                top = k * r - 1  # under the tread above (the decking: 1 in too)
                out.append(
                    Member(
                        "Riser",
                        PT,
                        box(
                            (
                                x0,
                                x0 + WIDE,
                                self.y(u),
                                self.y(u + RISER_T),
                                (k - 1) * r,
                                top,
                            )
                        ),
                    )
                )
        # The handrail: its top 36 over the nosing line, from the top nosing
        # to the lowest tread's; 1.5 deep square to the slope.
        run = (n - 1) * T

        def rail_top(u: float) -> float:
            return self.rise - u * r / T + 36.0

        v = 1.5 * self.length / T
        rail = [
            (self.y(0), rail_top(0) - v),
            (self.y(run), rail_top(run) - v),
            (self.y(run), rail_top(run)),
            (self.y(0), rail_top(0)),
        ]
        out.append(Member("Handrail", PT, prism_x(rail, x0, x0 + 1.5)))
        # 4x4 posts outside the left stringer, both ends and <= 72 apart.
        bays = math.ceil((run - 3.5) / 72.0)
        for k in range(bays + 1):
            u0 = (run - 3.5) * k / bays
            out.append(
                Member(
                    "Handrail post",
                    PT,
                    box((x0 - 3.5, x0, self.y(u0), self.y(u0 + 3.5), 0, rail_top(u0))),
                )
            )
        return out


B1_STAIR = Stair(30.0, 96.0, NOSE, 2.125, closed=False)
CASES: dict[str, tuple[float | None, Stair]] = {
    "b1-stair-30": (30.0, B1_STAIR),
    "b1-stair-30-closed": (30.0, Stair(30.0, 96.0, NOSE, 2.125, closed=True)),
    "b1-stair-36": (36.0, Stair(36.0, 96.0, NOSE, 2.125, closed=False)),
    "free-stair-107": (None, Stair(107.09375, 0.0, 0.0, None, closed=True)),
}
each_case = pytest.mark.parametrize("name", sorted(CASES))


def script(name: str) -> list[Member]:
    height, stair = CASES[name]
    return ([] if height is None else deck(height)) + stair.members()


# --- 1. The STEP against the script ------------------------------------------------


@pytest.fixture(scope="module")
def solids(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[Solid]]:
    return {name: _step_solids(tmp_path_factory, name) for name in CASES}


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


def test_b1_stringer_is_the_strip_less_three_notches() -> None:
    """B1's stringer by hand: the strip between its edges (11.25 x L / T
    tall) from the rim face (u -2.125) to the bottom riser (u 32.875), less
    the three R x T / 2 notches, the triangle above the head's level cut and
    the one under the foot's: the shoelace of the typed profile agrees."""
    s = B1_STAIR
    drop = D * s.length / T
    strip = drop * 35.0  # a parallelogram: its vertical depth x its run
    notches = 3 * 7.5 * 11 / 2
    slope = 7.5 / 11
    head = 2.0 * (2.0 * slope) / 2  # above Z 29 from u -2.125 to -0.125
    under = (32.875 - 22.43804289979181) * -s.bottom_edge(32.875) / 2
    # The foot triangle's apex is where the bottom edge meets grade.
    assert s.bottom_edge(22.43804289979181) == pytest.approx(0.0, abs=1e-9)
    assert shoelace(s.stringer()) == pytest.approx(
        strip - notches - head - under, abs=1e-9
    )


def stair_volume(stair: Stair) -> float:
    """The stair's members by hand (in^3)."""
    n, r = stair.n, stair.r
    run = (n - 1) * T
    stringers = 3 * 1.5 * shoelace(stair.stringer())
    treads = 2 * (n - 1) * WIDE * BOARD * TREAD_T
    risers = 0.0
    if stair.closed:
        count = n if stair.overhang is not None else n - 1
        risers = count * WIDE * RISER_T * (r - 1)
    rail = 1.5 * run * 1.5 * stair.length / T
    bays = math.ceil((run - 3.5) / 72.0)
    posts = sum(
        3.5 * 3.5 * (stair.rise - (run - 3.5) * k / bays * r / T + 36.0)
        for k in range(bays + 1)
    )
    return stringers + treads + risers + rail + posts


#: B1's deck (buildings.md: 64 497.75 in^3 of framing and decking, 3 piers
#: of 768 pi in^3), and at a 36 in decking top 6 in more of each post.
DECK_30 = 64497.75 + 3 * 768 * math.pi
DECK_36 = DECK_30 + 3 * 5.5 * 5.5 * 6


def hand_volume(name: str) -> float:
    height, stair = CASES[name]
    framing = 0.0 if height is None else DECK_30 if height == 30 else DECK_36
    return framing + stair_volume(stair)


@each_case
def test_the_step_is_the_independent_scripts(
    solids: dict[str, list[Solid]], name: str
) -> None:
    mine = script(name)
    assert len(solids[name]) == len(mine)
    assert _unmatched(solids[name], [m.solid for m in mine]) == []
    volume = sum(float(measure_shape(s).volume) for s in solids[name]) / IN**3
    assert volume == pytest.approx(hand_volume(name), abs=1e-4)


def test_the_hand_volumes() -> None:
    """The stair alone, member by member (in^3)."""
    assert stair_volume(B1_STAIR) == pytest.approx(
        3 * 1.5 * shoelace(B1_STAIR.stringer())
        + 6 * 36 * 5.5
        + 1.5 * 33 * 1.5 * math.sqrt(177.25) / 11
        + 12.25 * (66 + 66 - 29.5 * 7.5 / 11),
        abs=1e-9,
    )


# --- 2. The throat, measured on the B-rep ------------------------------------------


def measured_throat(stringer: Solid) -> float:
    """The least distance from a vertex off the stringer's bottom edge face
    (the sloped plane square to X) to that face: a notch's inside corner."""
    sloped = [
        f
        for f in stringer.faces()
        if f.geom_type == GeomType.PLANE
        and abs(f.normal_at().X) < 1e-9
        and min(abs(f.normal_at().Y), abs(f.normal_at().Z)) > 1e-3
    ]
    (bottom,) = sloped
    n = bottom.normal_at()
    origin = bottom.center()
    distances: list[float] = []
    for vertex in stringer.vertices():
        v = Vector(vertex)
        distances.append(abs((v - origin).dot(n)))
    return min(d for d in distances if d > 1e-6) / IN


@each_case
def test_the_throat_is_measured_on_every_stringer(
    solids: dict[str, list[Solid]], name: str
) -> None:
    _, stair = CASES[name]
    stringers = [
        s
        for s in solids[name]
        if any(
            f.geom_type == GeomType.PLANE
            and abs(f.normal_at().X) < 1e-9
            and min(abs(f.normal_at().Y), abs(f.normal_at().Z)) > 1e-3
            for f in s.faces()
        )
        and s.bounding_box().min.Z / IN < 1e-6
        and pytest.approx(1.5, abs=1e-6) == s.bounding_box().size.X / IN
    ]
    assert len(stringers) == 3
    for stringer in stringers:
        assert measured_throat(stringer) == pytest.approx(stair.throat, abs=1e-6)
    # buildings.md's figures (the 36 in deck's is 5.2257, not the PM's 5.2258).
    want = {
        "b1-stair-30": 5.0533,
        "b1-stair-30-closed": 5.0533,
        "b1-stair-36": 5.2257,
        "free-stair-107": 4.9697,
    }
    assert round(stair.throat, 4) == want[name]


# --- 3. Interference none ----------------------------------------------------------


@each_case
def test_nothing_interferes(solids: dict[str, list[Solid]], name: str) -> None:
    assert _overlapping(solids[name]) == []


def test_the_stair_meets_the_deck_face_to_face(
    solids: dict[str, list[Solid]],
) -> None:
    """Each stringer's head is cut plumb on the rim's face (Y 144) and level
    under the last board (Z 29): it touches both and shares nothing."""
    every = solids["b1-stair-30"]
    rim = next(
        s
        for s in every
        if pytest.approx(142.5, abs=1e-6) == s.bounding_box().min.Y / IN
        and pytest.approx(192, abs=1e-6) == s.bounding_box().size.X / IN
    )
    stringers = [
        s
        for s in every
        if pytest.approx(144, abs=1e-6) == s.bounding_box().min.Y / IN
        and pytest.approx(1.5, abs=1e-6) == s.bounding_box().size.X / IN
    ]
    assert len(stringers) == 3
    for stringer in stringers:
        gap: float = stringer.distance_to(rim)  # pyright: ignore[reportUnknownMemberType]
        assert gap == pytest.approx(0.0, abs=1e-6)
        assert pytest.approx(29, abs=1e-6) == stringer.bounding_box().max.Z / IN


# --- 4. The cut list ---------------------------------------------------------------


def _request(name: str) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )


def cut_list(name: str) -> CutListResponse:
    request = _request(name)
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    extents = BodyExtentsResult.model_validate_json(response.content)
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / name / "members.json").read_text()
    )
    members = [CutListMember.model_validate(item) for item in raw]
    return cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name=name,
        length_unit="in",
        pieces=part_pieces(extents, members, request.materials),
        price_book=EMPTY_PRICE_BOOK,
    )


def stringer_length(stair: Stair) -> float:
    """Long point to long point along the slope: from the head's highest
    back corner to the foot's toe, projected on (T, -R) / L."""
    head = stair.stringer()[0]
    foot = (stair.back(1) + T, 0.0)
    return ((foot[0] - head[0]) * T + (head[1] - foot[1]) * stair.r) / stair.length


def rail_length(stair: Stair) -> float:
    """The handrail's plumb-cut ends: its run along the slope plus the cut."""
    run = (stair.n - 1) * T
    return run * stair.length / T + 1.5 * stair.r / T


#: name -> the Stairs lines (member, profile, qty, length in, stock ft), by
#: hand: B1's stringer 602.5 / sqrt(177.25) = 45.2547 in, 8 ft stock (no
#: 6 ft lumber is sold: the spec's "6 ft" is a slip), its rail 40.9633.
def stairs_table(name: str) -> list[tuple[str, str, int, float, int]]:
    _, stair = CASES[name]
    n, r = stair.n, stair.r
    run = (n - 1) * T
    bays = math.ceil((run - 3.5) / 72.0)
    posts = sorted(
        stair.rise - (run - 3.5) * k / bays * r / T + 36.0 for k in range(bays + 1)
    )

    def stock(inches: float) -> int:
        return next(ft for ft in (8, 10, 12, 14, 16, 18, 20) if ft * 12 >= inches)

    rows = [
        ("Stringer", "2x12", 3, stringer_length(stair), stock(stringer_length(stair))),
        ("Tread", "5/4x6", 2 * (n - 1), 36.0, 8),
    ]
    if stair.closed:
        count = n if stair.overhang is not None else n - 1
        rows.append(("Riser", "1x8", count, 36.0, 8))
    rows.append(("Handrail", "2x2", 1, rail_length(stair), stock(rail_length(stair))))
    rows += [("Handrail post", "4x4", 1, p, stock(p)) for p in posts]
    return rows


@each_case
def test_the_cut_list_lists_the_stair_under_stairs(name: str) -> None:
    lines = [line for line in cut_list(name).lines if line.system == "stairs"]
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
    want = [
        (m, p, q, round(length, 4), ft) for m, p, q, length, ft in stairs_table(name)
    ]
    assert got == want
    one_piece = {line.member: line.one_piece for line in lines}
    assert one_piece["Stringer"] and one_piece["Handrail"]
    assert one_piece["Handrail post"] and not one_piece["Tread"]
    assert all(line.material == PT for line in lines)


def test_b1s_numbers_are_the_specs() -> None:
    rows = stairs_table("b1-stair-30")
    assert round(rows[0][3], 4) == 45.2547 and rows[0][4] == 8
    assert rows[1] == ("Tread", "5/4x6", 6, 36.0, 8)
    assert B1_STAIR.n == 4 and B1_STAIR.r == 7.5


def test_the_deck_keeps_its_cut_list() -> None:
    """The deck's lines are buildings.md's table whichever stair it carries."""
    rows = [
        (line.member, line.profile, line.quantity, round(line.length_mm / IN, 6))
        for line in cut_list("b1-stair-30").lines
        if line.system == "deck"
    ]
    assert rows == [
        ("Ledger", "2x10", 1, 192.0),
        ("Rim", "2x10", 1, 192.0),
        ("Beam", "2x10", 2, 192.0),
        ("Joist", "2x10", 13, 141.0),
        ("Post", "6x6", 3, 10.5),
        ("Deck", "5/4x6", 26, 192.0),
    ]


# --- expected.json -----------------------------------------------------------------


def expected_numbers(name: str) -> dict[str, Any]:
    """A golden's mass properties and topology from the script: the volume
    by hand, the rest measured on the script's solids."""
    mine = script(name)
    volume = hand_volume(name) * IN**3
    area = sum(float(measure_shape(m.solid).surface_area) for m in mine)
    moments = [0.0, 0.0, 0.0]
    mass = 0.0
    mass_moments = [0.0, 0.0, 0.0]
    faces = edges = 0
    for m in mine:
        props = measure_shape(m.solid)
        v = float(props.volume)
        c = props.centroid
        for k, value in enumerate((c.x, c.y, c.z)):
            moments[k] += v * value
            mass_moments[k] += v * DENSITY[m.material] * 1e-6 * value
        mass += v * DENSITY[m.material] * 1e-6
        faces += len(m.solid.faces())
        edges += len(m.solid.edges())
    total = sum(float(measure_shape(m.solid).volume) for m in mine)
    bb = [m.solid.bounding_box() for m in mine]
    return {
        "volume": volume,
        "surface_area": area,
        "centroid": [x / total for x in moments],
        "mass_g": mass,
        "center_of_mass": [x / mass for x in mass_moments],
        "bbox_min": [
            min(b.min.X for b in bb),
            min(b.min.Y for b in bb),
            min(b.min.Z for b in bb),
        ],
        "bbox_max": [
            max(b.max.X for b in bb),
            max(b.max.Y for b in bb),
            max(b.max.Z for b in bb),
        ],
        "faces": faces,
        "edges": edges,
        "shells": len(mine),
    }


if __name__ == "__main__":
    for case in sys.argv[1:] or sorted(CASES):
        sys.stderr.write(f"{case}: {json.dumps(expected_numbers(case))}\n")
