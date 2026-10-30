"""DECK-GUARD-OPENING acceptance: B1's guard opens at its stair, on STEP.

``goldens/b1-stair-30-guard-opening`` is B1 at ``loft.deck`` 1.3.0 with its
guard on the open sides and every other default, and a ``loft.stair`` 1.0.0
centred on its rim at X 96 (b1-stair-30's stair); ``b1-stair-30-guard-corner``
the same stair flush with the deck's left corner, centred at X 18. Their
``model.json`` and ``members.json`` are pinned to the plugins by
``packages/loft-plugins/tests/test_deck_guard_opening.py``. Geometry never
learns plugins exist, so this module imports nothing from them.

Checked against an independent build123d script typed from
``docs/reference-parts/buildings.md`` B1, IRC R312 and Chief Architect's
deck railing (a railing breaks where a stair lands), sharing no code with
the plugins (B1's framing and its stair are ``test_stair_b1``'s script):

1. the STEP is the script's solids, solid for solid, and its volume the
   hand sum;
2. the front guard opens between the stair's outer stringer faces (X 78 to
   114; at the corner X 0 to 36), with a post each side whose face is the
   stringer's, or the corner post alone where the run to the corner is
   shorter than two posts;
3. interference none, every pair whose boxes meet probed exactly;
4. the cut list's guard lines are the hand counts.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_deck_guard_opening_b1.py``.
"""

import itertools
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from build123d import Solid
from geometry.kernel import measure_shape

sys.path.insert(0, str(Path(__file__).parent))
from test_outline_b7 import (
    IN,
    _overlapping,  # pyright: ignore[reportPrivateUsage]
    _step_solids,  # pyright: ignore[reportPrivateUsage]
    _unmatched,  # pyright: ignore[reportPrivateUsage]
    box,
)
from test_stair_b1 import (
    B1_STAIR,
    DECK_30,
    DENSITY,
    NOSE,
    PT,
    Member,
    Stair,
    cut_list,
    deck,
    stair_volume,
)

WIDTH, DEPTH, FLOOR = 192.0, 144.0, 30.0

# --- The guard, typed from buildings.md B1 and IRC R312 (inches) ------------------

POST = 3.5  # 4x4
RAIL_T, RAIL_W = 1.5, 3.5  # 2x4 on edge
BAL = 1.5  # 2x2
TOP = FLOOR + 36.0
BOTTOM_RAIL = (FLOOR + 3.5, FLOOR + 3.5 + RAIL_W)  # Z 33.5..37
TOP_RAIL = (TOP - RAIL_W, TOP)  # Z 62.5..66


def run_posts(lo: float, hi: float) -> list[float]:
    """Post centres on a run lo..hi: one at each end, equally spaced, no
    more than 72 in apart (R312's 4x4 guard, 6 ft posts)."""
    first, last = lo + POST / 2, hi - POST / 2
    bays = math.ceil((last - first) / 72.0 - 1e-9)
    return [first + (last - first) * k / bays for k in range(bays + 1)]


@dataclass(frozen=True)
class Case:
    """One golden: the stair, its opening on the front (its outer stringer
    faces), the front's runs of posts, and the guard's hand numbers."""

    stair: Stair
    opening: tuple[float, float]
    front: list[list[float]]
    #: Posts, rail inches over both courses, balusters.
    posts: int
    rail: float
    balusters: int
    #: The cut list's rail lines: (quantity, length).
    rails: list[tuple[int, float]]
    #: The front's posts (X spans), and a post the opening may hold (the
    #: corner's, on the deck, when the stair is flush with it).
    front_posts: list[tuple[float, float]]
    corner_in_opening: bool = False

    @property
    def guard_volume(self) -> float:
        return (
            self.posts * POST * POST * 36
            + self.rail * RAIL_T * RAIL_W
            + self.balusters * BAL * BAL * (TOP_RAIL[0] - BOTTOM_RAIL[1])
        )


#: Both sides are whole runs, Y 0..144: posts at 1.75, 72, 142.25, two bays
#: of 66.75 clear and 12 balusters each ((66.75 - 4) / 5.5 -> 12).
SIDE = [run_posts(0.0, DEPTH)]

CASES: dict[str, Case] = {
    # At X 96 (X 78..114): runs 0..78 and 114..192, posts 1.75, 39, 76.25 and
    # 115.75, 153, 190.25; four 33.75 bays of 6 balusters. Posts 10; rails
    # 2 x (133.5 + 4 x 33.75 + 133.5) = 804 (the closed guard's 890: the front
    # 192 - 36 - 6 x 3.5 = 135 a course against 192 - 4 x 3.5 = 178).
    "b1-stair-30-guard-opening": Case(
        stair=B1_STAIR,
        opening=(78.0, 114.0),
        front=[run_posts(0.0, 78.0), run_posts(114.0, WIDTH)],
        posts=10,
        rail=804.0,
        balusters=72,
        rails=[(8, 66.75), (8, 33.75)],
        front_posts=[
            (0.0, 3.5),
            (37.25, 40.75),
            (74.5, 78.0),
            (114.0, 117.5),
            (151.25, 154.75),
            (188.5, 192.0),
        ],
    ),
    # Flush at X 18 (X 0..36): the run to the corner is 0 in, so the corner
    # post (the left side's, X 0..3.5) alone stands there and is the
    # opening's post on that side. The run 36..192 (156 in): posts 37.75 and
    # 190.25, (152.5 / 72 -> 3 bays) 50.8333 apart, three bays of 47.3333
    # clear and 8 balusters each (43.3333 / 5.5 -> 8). Posts 3 + 3 + 3 = 9;
    # rails 2 x (133.5 + 3 x 47.3333 + 133.5) = 2 x 409 = 818 (the front
    # 192 - 36 - 4 x 3.5 = 142 a course); balusters 24 + 24 + 24 = 72.
    "b1-stair-30-guard-corner": Case(
        stair=Stair(30.0, 18.0, NOSE, 2.125, closed=False),
        opening=(0.0, 36.0),
        front=[[POST / 2], run_posts(36.0, WIDTH)],
        posts=9,
        rail=818.0,
        balusters=72,
        rails=[(8, 66.75), (6, 47.3333)],
        front_posts=[
            (0.0, 3.5),
            (36.0, 39.5),
            (86.833333, 90.333333),
            (137.666667, 141.166667),
            (188.5, 192.0),
        ],
        corner_in_opening=True,
    ),
}
each_case = pytest.mark.parametrize("name", sorted(CASES))


def _plan(
    u0: float, u1: float, across: float, fixed: float, axis: str
) -> tuple[float, float, float, float]:
    """A member's plan: u0..u1 along a side whose centre line is *fixed*."""
    if axis == "x":
        return (u0, u1, fixed - across / 2, fixed + across / 2)
    return (fixed - across / 2, fixed + across / 2, u0, u1)


def bay(s0: float, s1: float, fixed: float, axis: str) -> list[Member]:
    """A bay's two rails and its balusters, the fewest leaving no gap over
    4 in, equally spaced."""
    out = [
        Member("Rail", PT, box((*_plan(s0, s1, RAIL_T, fixed, axis), *z)))
        for z in (BOTTOM_RAIL, TOP_RAIL)
    ]
    clear = s1 - s0
    n = math.ceil((clear - 4.0) / (BAL + 4.0) - 1e-9)
    space = (clear - n * BAL) / (n + 1)
    for k in range(n):
        c0 = s0 + space * (k + 1) + BAL * k
        plan = _plan(c0, c0 + BAL, BAL, fixed, axis)
        out.append(Member("Baluster", PT, box((*plan, BOTTOM_RAIL[1], TOP_RAIL[0]))))
    return out


def guard(case: Case) -> list[Member]:
    """Posts (each corner once), then rails, then balusters, as built."""
    half = POST / 2
    sides = (
        (SIDE, half, "y"),
        (case.front, DEPTH - half, "x"),
        (SIDE, WIDTH - half, "y"),
    )
    centres: set[tuple[float, float]] = set()
    for runs, fixed, axis in sides:
        for run in runs:
            for s in run:
                centres.add((s, fixed) if axis == "x" else (fixed, s))
    out = [
        Member(
            "Guard post", PT, box((x - half, x + half, y - half, y + half, FLOOR, TOP))
        )
        for x, y in sorted(centres)
    ]
    for runs, fixed, axis in sides:
        for run in runs:
            for a, b in itertools.pairwise(run):
                out += bay(a + half, b - half, fixed, axis)
    return out


def script(name: str) -> list[Member]:
    case = CASES[name]
    return deck(FLOOR) + case.stair.members() + guard(case)


def hand_volume(name: str) -> float:
    case = CASES[name]
    return DECK_30 + stair_volume(case.stair) + case.guard_volume


# --- 1. The STEP against the script ------------------------------------------------


@pytest.fixture(scope="module")
def solids(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[Solid]]:
    return {name: _step_solids(tmp_path_factory, name) for name in CASES}


@each_case
def test_the_hand_counts(name: str) -> None:
    """The script's guard is the case's hand numbers."""
    case = CASES[name]
    members = guard(case)
    count = {"Guard post": 0, "Rail": 0, "Baluster": 0}
    for m in members:
        count[m.member] += 1
    assert count == {
        "Guard post": case.posts,
        "Rail": sum(q for q, _ in case.rails),
        "Baluster": case.balusters,
    }
    assert sum(q * length for q, length in case.rails) == pytest.approx(
        case.rail, abs=1e-3
    )


def test_the_hand_volumes() -> None:
    assert CASES["b1-stair-30-guard-opening"].guard_volume == pytest.approx(
        4410 + 4221 + 4131, abs=1e-9
    )
    assert CASES["b1-stair-30-guard-corner"].guard_volume == pytest.approx(
        3969 + 4294.5 + 4131, abs=1e-9
    )


@each_case
def test_the_step_is_the_independent_scripts(
    solids: dict[str, list[Solid]], name: str
) -> None:
    mine = script(name)
    assert len(solids[name]) == len(mine)
    assert _unmatched(solids[name], [m.solid for m in mine]) == []
    volume = sum(float(measure_shape(s).volume) for s in solids[name]) / IN**3
    assert volume == pytest.approx(hand_volume(name), abs=1e-4)


# --- 2. The opening ------------------------------------------------------------------


def _bounds(s: Solid) -> tuple[float, ...]:
    bb = s.bounding_box()
    return tuple(
        round(v / IN, 6)
        for v in (bb.min.X, bb.max.X, bb.min.Y, bb.max.Y, bb.min.Z, bb.max.Z)
    )


@each_case
def test_the_guard_opens_between_the_outer_stringer_faces(
    solids: dict[str, list[Solid]], name: str
) -> None:
    """No guard member stands over the opening on the front but, at the
    corner, the corner post; a post's face is on each outer stringer's or
    the corner post stands for it."""
    case = CASES[name]
    lo, hi = case.opening
    every = [_bounds(s) for s in solids[name]]
    # The front guard: on the decking, on its line Y 140.5..144 (the
    # stair's handrail starts at its top nosing, Y 146.125).
    over_decking = [
        b
        for b in every
        if b[4] >= FLOOR - 1e-6 and b[2] >= 140.5 - 1e-6 and b[3] <= 144 + 1e-6
    ]
    assert over_decking, "the front guard"
    for b in over_decking:
        if case.corner_in_opening and (b[0], b[1], b[5]) == (0.0, POST, TOP):
            continue
        assert b[1] <= lo + 1e-6 or b[0] >= hi - 1e-6, b
    posts = sorted(b for b in over_decking if b[5] == TOP and b[1] - b[0] == POST)
    assert [(b[0], b[1]) for b in posts] == case.front_posts
    stringers = sorted(
        b
        for b in every
        if b[2] == 144.0 and round(b[1] - b[0], 6) == 1.5 and b[4] == 0.0
    )
    assert (stringers[0][0], stringers[-1][1]) == case.opening


# --- 3. Interference none ----------------------------------------------------------


@each_case
def test_nothing_interferes(solids: dict[str, list[Solid]], name: str) -> None:
    assert _overlapping(solids[name]) == []


# --- 4. The cut list ---------------------------------------------------------------


@each_case
def test_the_cut_list_loses_the_opened_rail(name: str) -> None:
    """The guard's lines (Deck): its posts at 36, its rails (the sides' 8 x
    66.75 and the front's runs), its balusters at 25.5; rail in all 804 in
    at X 96 and 818 at the corner, against the closed guard's 890."""
    case = CASES[name]
    rows = [
        (line.member, line.profile, line.quantity, round(line.length_mm / IN, 4))
        for line in cut_list(name).lines
        if line.member in ("Guard post", "Rail", "Baluster")
    ]
    assert sorted(rows) == sorted(
        [
            ("Guard post", "4x4", case.posts, 36.0),
            *(("Rail", "2x4", q, length) for q, length in case.rails),
            ("Baluster", "2x2", case.balusters, 25.5),
        ]
    )
    rail = sum(q * length for m, _, q, length in rows if m == "Rail")
    assert rail == pytest.approx(case.rail, abs=1e-3)


@each_case
def test_the_stair_and_the_framing_keep_their_cut_list(name: str) -> None:
    """The deck's framing and the stair's lines are b1-stair-30's."""
    mine = [
        (line.system, line.member, line.quantity, round(line.length_mm / IN, 4))
        for line in cut_list(name).lines
        if line.member not in ("Guard post", "Rail", "Baluster")
    ]
    theirs = [
        (line.system, line.member, line.quantity, round(line.length_mm / IN, 4))
        for line in cut_list("b1-stair-30").lines
    ]
    assert mine == theirs


# --- expected.json -----------------------------------------------------------------


def expected_numbers(name: str) -> dict[str, Any]:
    """A golden's mass properties and topology from the script: the volume
    by hand, the rest measured on the script's solids."""
    mine = script(name)
    volume = hand_volume(name) * IN**3
    area = 0.0
    moments = [0.0, 0.0, 0.0]
    mass = 0.0
    mass_moments = [0.0, 0.0, 0.0]
    faces = edges = 0
    total = 0.0
    for m in mine:
        props = measure_shape(m.solid)
        v = float(props.volume)
        total += v
        area += float(props.surface_area)
        c = props.centroid
        for k, value in enumerate((c.x, c.y, c.z)):
            moments[k] += v * value
            mass_moments[k] += v * DENSITY[m.material] * 1e-6 * value
        mass += v * DENSITY[m.material] * 1e-6
        faces += len(m.solid.faces())
        edges += len(m.solid.edges())
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
