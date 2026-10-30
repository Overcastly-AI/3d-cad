"""DECK-GUARD-OPENING acceptance: B1's guard opens at its stair, on STEP.

``goldens/b1-stair-30-guard-opening`` is B1 at ``loft.deck`` 1.3.0 with its
guard on the open sides and every other default, and a ``loft.stair`` 1.0.0
centred on its rim at X 96 (b1-stair-30's stair). ``model.json`` and
``members.json`` are pinned to the plugins by
``packages/loft-plugins/tests/test_deck_guard_opening.py``. Geometry never
learns plugins exist, so this module imports nothing from them.

Checked against an independent build123d script typed from
``docs/reference-parts/buildings.md`` B1, IRC R312 and Chief Architect's
deck railing (a railing breaks where a stair lands), sharing no code with
the plugins (B1's framing and its stair are ``test_stair_b1``'s script):

1. the STEP is the script's solids, solid for solid, and its volume the
   hand sum;
2. the front guard opens between the stair's outer stringer faces, X 78 to
   X 114, with a post each side whose face is the stringer's;
3. interference none, every pair whose boxes meet probed exactly;
4. the cut list's guard lines are the hand counts: 10 posts, rails 8 of
   66.75 and 8 of 33.75 (86 in less than the closed guard's 890), 72
   balusters.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_deck_guard_opening_b1.py``.
"""

import itertools
import json
import math
import sys
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
    PT,
    Member,
    cut_list,
    deck,
    stair_volume,
)

NAME = "b1-stair-30-guard-opening"
WIDTH, DEPTH, FLOOR = 192.0, 144.0, 30.0

# --- The guard, typed from buildings.md B1 and IRC R312 (inches) ------------------

POST = 3.5  # 4x4
RAIL_T, RAIL_W = 1.5, 3.5  # 2x4 on edge
BAL = 1.5  # 2x2
TOP = FLOOR + 36.0
BOTTOM_RAIL = (FLOOR + 3.5, FLOOR + 3.5 + RAIL_W)  # Z 33.5..37
TOP_RAIL = (TOP - RAIL_W, TOP)  # Z 62.5..66
#: The stair's outer stringer faces: its 36 in width centred at X 96.
OPENING = (78.0, 114.0)


def run_posts(lo: float, hi: float) -> list[float]:
    """Post centres on a run lo..hi: one at each end, equally spaced, no
    more than 72 in apart (R312's 4x4 guard, 6 ft posts)."""
    first, last = lo + POST / 2, hi - POST / 2
    bays = math.ceil((last - first) / 72.0 - 1e-9)
    return [first + (last - first) * k / bays for k in range(bays + 1)]


#: B1's three open sides, each as its runs: the left (X line 1.75) and the
#: right (X 190.25) whole, Y 0..144; the front (Y 142.25) broken at the stair.
LEFT = [run_posts(0.0, DEPTH)]  # 1.75, 72, 142.25
RIGHT = [run_posts(0.0, DEPTH)]
FRONT = [run_posts(0.0, OPENING[0]), run_posts(OPENING[1], WIDTH)]


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


def guard() -> list[Member]:
    """Posts (each corner once), then rails, then balusters, as built."""
    half = POST / 2
    centres: set[tuple[float, float]] = set()
    for runs, fixed, axis in (
        (LEFT, half, "y"),
        (FRONT, DEPTH - half, "x"),
        (RIGHT, WIDTH - half, "y"),
    ):
        for run in runs:
            for s in run:
                centres.add((s, fixed) if axis == "x" else (fixed, s))
    out = [
        Member(
            "Guard post", PT, box((x - half, x + half, y - half, y + half, FLOOR, TOP))
        )
        for x, y in sorted(centres)
    ]
    for runs, fixed, axis in (
        (LEFT, half, "y"),
        (FRONT, DEPTH - half, "x"),
        (RIGHT, WIDTH - half, "y"),
    ):
        for run in runs:
            for a, b in itertools.pairwise(run):
                out += bay(a + half, b - half, fixed, axis)
    return out


def script() -> list[Member]:
    return deck(FLOOR) + B1_STAIR.members() + guard()


#: The guard by hand (in^3): 10 posts of 3.5 x 3.5 x 36; the rails, 2 x
#: (133.5 + 135 + 133.5) = 804 in of 1.5 x 3.5; 72 balusters of 1.5 x 1.5 x
#: 25.5. The front's rails are 192 - 36 - 6 x 3.5 = 135 a course.
GUARD_VOLUME = 10 * 3.5 * 3.5 * 36 + 804 * 1.5 * 3.5 + 72 * 1.5 * 1.5 * 25.5


def hand_volume() -> float:
    return DECK_30 + stair_volume(B1_STAIR) + GUARD_VOLUME


# --- 1. The STEP against the script ------------------------------------------------


@pytest.fixture(scope="module")
def solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return _step_solids(tmp_path_factory, NAME)


def test_the_hand_counts() -> None:
    """The script's guard is the docstring's: posts at 1.75, 39, 76.25 and
    115.75, 153, 190.25 on the front; 12 balusters a 66.75 side bay and 6 a
    33.75 front bay."""
    assert FRONT == [[1.75, 39.0, 76.25], [115.75, 153.0, 190.25]]
    assert LEFT == [[1.75, 72.0, 142.25]]
    members = guard()
    count = {m.member: 0 for m in members}
    for m in members:
        count[m.member] += 1
    assert count == {"Guard post": 10, "Rail": 16, "Baluster": 72}
    assert pytest.approx(4410 + 4221 + 4131, abs=1e-9) == GUARD_VOLUME


def test_the_step_is_the_independent_scripts(solids: list[Solid]) -> None:
    mine = script()
    assert len(solids) == len(mine)
    assert _unmatched(solids, [m.solid for m in mine]) == []
    volume = sum(float(measure_shape(s).volume) for s in solids) / IN**3
    assert volume == pytest.approx(hand_volume(), abs=1e-4)


# --- 2. The opening ------------------------------------------------------------------


def _bounds(s: Solid) -> tuple[float, ...]:
    bb = s.bounding_box()
    return tuple(
        round(v / IN, 6)
        for v in (bb.min.X, bb.max.X, bb.min.Y, bb.max.Y, bb.min.Z, bb.max.Z)
    )


def test_the_guard_opens_between_the_outer_stringer_faces(solids: list[Solid]) -> None:
    """No guard member stands over X 78..114 on the front; a post's face is
    on each outer stringer's: X 74.5..78 and X 114..117.5."""
    every = [_bounds(s) for s in solids]
    # The front guard: on the decking, on its line Y 140.5..144 (the
    # stair's handrail starts at its top nosing, Y 146.125).
    over_decking = [
        b
        for b in every
        if b[4] >= FLOOR - 1e-6 and b[2] >= 140.5 - 1e-6 and b[3] <= 144 + 1e-6
    ]
    assert over_decking, "the front guard"
    for b in over_decking:
        assert b[1] <= OPENING[0] + 1e-6 or b[0] >= OPENING[1] - 1e-6, b
    posts = sorted(b for b in over_decking if b[5] == TOP and b[1] - b[0] == POST)
    assert [(b[0], b[1]) for b in posts] == [
        (0.0, 3.5), (37.25, 40.75), (74.5, 78.0),
        (114.0, 117.5), (151.25, 154.75), (188.5, 192.0),
    ]  # fmt: skip
    stringers = sorted(
        b
        for b in every
        if b[2] == 144.0 and round(b[1] - b[0], 6) == 1.5 and b[4] == 0.0
    )
    assert (stringers[0][0], stringers[-1][1]) == OPENING


# --- 3. Interference none ----------------------------------------------------------


def test_nothing_interferes(solids: list[Solid]) -> None:
    assert _overlapping(solids) == []


# --- 4. The cut list ---------------------------------------------------------------


def test_the_cut_list_loses_the_opened_rail() -> None:
    """The guard's lines (Deck): 10 posts at 36, rails 8 x 66.75 (the sides)
    and 8 x 33.75 (the front's runs; the closed guard's 6 x 59.3333), 72
    balusters at 25.5. Rail in all: 534 + 270 = 804 in, 86 less than the
    closed guard's 534 + 356 = 890."""
    rows = [
        (line.member, line.profile, line.quantity, round(line.length_mm / IN, 4))
        for line in cut_list(NAME).lines
        if line.member in ("Guard post", "Rail", "Baluster")
    ]
    assert sorted(rows) == sorted(
        [
            ("Guard post", "4x4", 10, 36.0),
            ("Rail", "2x4", 8, 66.75),
            ("Rail", "2x4", 8, 33.75),
            ("Baluster", "2x2", 72, 25.5),
        ]
    )
    rail = sum(q * length for m, _, q, length in rows if m == "Rail")
    assert rail == pytest.approx(890 - 86, abs=1e-9)


def test_the_stair_and_the_framing_keep_their_cut_list() -> None:
    """The deck's framing and the stair's lines are b1-stair-30's."""
    mine = [
        (line.system, line.member, line.quantity, round(line.length_mm / IN, 4))
        for line in cut_list(NAME).lines
        if line.member not in ("Guard post", "Rail", "Baluster")
    ]
    theirs = [
        (line.system, line.member, line.quantity, round(line.length_mm / IN, 4))
        for line in cut_list("b1-stair-30").lines
    ]
    assert mine == theirs


# --- expected.json -----------------------------------------------------------------


def expected_numbers() -> dict[str, Any]:
    """The golden's mass properties and topology from the script: the volume
    by hand, the rest measured on the script's solids."""
    mine = script()
    volume = hand_volume() * IN**3
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
    sys.stderr.write(f"{NAME}: {json.dumps(expected_numbers())}\n")
