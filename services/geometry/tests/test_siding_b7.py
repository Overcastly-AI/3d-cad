"""SIDING-TRIM acceptance: B7 drawn today with its exterior finish, on STEP.

``goldens/b7-siding`` is B7 drawn today (floor 1.3.0, walls 1.5.0 on the
floor, the door and five windows 1.5.0 picked by call size with their units
drawn, the roof 1.8.0), every default kept: fibre-cement lap over the OSB
from the foundation top to the top plate, 5/4x4 corner boards and casing,
and the lap carried up the gables. ``model.json``, ``members.json`` and
``fixtures/siding-cases.json.gz`` are pinned to the plugins by
``packages/loft-plugins/tests/test_siding_trim.py``. Geometry never learns
plugins exist, so this module imports nothing from them.

Checked against the INDEPENDENT scripts B7 was accepted on
(``test_outline_b7.script`` with its units, ``test_opening_update_b7``'s
plies and spacers, ``test_ceiling_joists_b7.joists``,
``test_gable_ends_b7.gable_members``) and the finish typed here from
``docs/reference-parts/buildings.md``, sharing no code with the plugins:

1. the STEP's 329 solids are the scripts' 288 and the finish's 41, solid for
   solid: the 5/16 lap outside the OSB (X -3/4 .. -7/16 and so on), the
   front and back from X 3 1/16 to 284 15/16 and the sides from Y 2 1/16 to
   189 15/16, Z 0 to 108.59375, less each cased opening's box and the
   rafter tails over it; 8 corner boards; 23 mitred casing pieces round the
   units (a 3040 cased 43 x 55, a 2030 31 x 43, the door's 37.5 x 82 frame
   44.5 x 85.5); the gables' lap over the gable OSB;
2. interference none, every pair probed exactly;
3. the cut list: one siding line of 6 layers, their measured net area
   88 368.53125 + 2 x 5 705.185554 = 99 778.902 in², x 1.10 / 1 008 = 108.89,
   109 boards; 8 corner boards of 108.59375; 23 casing pieces, 1 099.5 in;
   every line priced;
4. vinyl (8 squares), cedar, 28 ft, 8/12, unsheathed (no finish: it goes
   over the OSB), an L with a hip, B7 turned, B8, B9 and B10 all build with
   no interference.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_siding_b7.py``.
"""

import gzip
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from build123d import Solid
from geometry.harness import build_model_solid
from geometry.kernel import measure_shape
from loft_wire.cut_list import CutListMember, cut_list_response, part_pieces
from loft_wire.features import EvaluateTreeRequest
from loft_wire.price_book import PriceBookResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_ceiling_joists_b7 as joists
import test_gable_ends_b7 as gables
import test_opening_update_b7 as openings
import test_outline_b7 as b7
from _siding_builder import (
    CASED,
    FRONT,
    GABLE,
    LEFT,
    PLATE,
    RINGS,
    RUNS,
    UNITS,
    T,
    casing_outline,
    finish_members,
    finish_volume,
    notch,
)

NAME = "b7-siding"
IN = b7.IN
GOLDENS = b7.GOLDENS
CASES = Path(__file__).resolve().parent / "fixtures" / "siding-cases.json.gz"
FC = "fibre_cement"


def script() -> list[b7.Member]:
    return [
        *b7.script(units=True),
        *(b7.Member(m, mat, b7.box(b)) for m, mat, b in openings.added_boxes()),
        *joists.joists(),
        *gables.gable_members(),
        *finish_members(),
    ]


def house_volume() -> float:
    return (
        b7.analytic_volume(288, units=True)
        + float(openings.added_volume())
        + 11 * joists.joist_volume()
        + (gables.house_volume() - joists.house_volume())
        + finish_volume()
    )


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return b7._step_solids(tmp_path_factory, NAME)  # pyright: ignore[reportPrivateUsage]


# --- 1. The numbers and the STEP ---------------------------------------------------


def test_the_finish_numbers_are_buildings_mds() -> None:
    """939.5 = 2 x 281.875 + 2 x 187.875; the cased openings 13 565.75; the
    gable OSB's area test_gable_ends_b7's; the casing's long points 1 099.5."""
    assert (
        2 * (RUNS[FRONT][1] - RUNS[FRONT][0]) + 2 * (RUNS[LEFT][1] - RUNS[LEFT][0])
        == 939.5
    )
    assert 3 * CASED["3040"] + 2 * CASED["2030"] + CASED["3068"] == 13565.75
    assert pytest.approx(gables.gable_osb_area(), abs=1e-9) == GABLE
    longs = sum(
        (1 if door else 2) * (o1 - o0) + 2 * (p1 - p0)
        for _, unit, door in UNITS
        for o0, o1, p0, p1 in [casing_outline(unit, door)]
    )
    assert longs == 1099.5
    assert notch(T) / T == pytest.approx(4.0703125, abs=1e-12)
    rings = 3 * RINGS["3040"] + 2 * RINGS["2030"] + RINGS["3068"]
    assert rings == 3578.75
    mine = finish_members()
    volume = sum(float(measure_shape(m.solid).volume) for m in mine) / IN**3
    assert volume == pytest.approx(finish_volume(), abs=1e-6)


def test_the_step_is_the_scripts_and_the_finish(step_solids: list[Solid]) -> None:
    mine = script()
    assert len(step_solids) == len(mine) == 288 + 41
    assert b7._unmatched(step_solids, [m.solid for m in mine]) == []  # pyright: ignore[reportPrivateUsage]
    volume = sum(float(measure_shape(s).volume) for s in step_solids) / IN**3
    assert volume == pytest.approx(house_volume(), abs=1e-4)


# --- 2. Interference none ---------------------------------------------------------


def test_nothing_interferes(step_solids: list[Solid]) -> None:
    assert b7._overlapping(step_solids) == []  # pyright: ignore[reportPrivateUsage]


# --- 3. The cut list --------------------------------------------------------------

#: B7's book and its units (test_outline_b7.UNIT_BOOK), the spacers' 1/2
#: plywood, the joists' 16 ft 2x8, the gables' 4x8 OSB, and the finish: a
#: 12 ft board of lap $13.98, 5/4x4 fibre-cement trim at 10 ft $14.98 and
#: 8 ft $11.98.
BOOK = PriceBookResponse.model_validate(
    {
        "currency": "USD",
        "entries": [
            *(e.model_dump(mode="json") for e in b7.UNIT_BOOK.entries),
            *(
                {"material": m, "profile": p, "unit": "each", **stock, "price_cents": c}
                for m, p, stock, c in [
                    (b7.PLY_M, "plywood_1_2", {"sheet": "4x8"}, 3298),
                    (b7.SPF, "us_2x8", {"stock_length_ft": 16}, 1797),
                    (b7.OSB_M, "osb_7_16", {"sheet": "4x8"}, 2198),
                    (FC, "fibre_cement_lap_8_25", {"stock_length_ft": 12}, 1398),
                    (FC, "us_5_4x4", {"stock_length_ft": 10}, 1498),
                    (FC, "us_5_4x4", {"stock_length_ft": 8}, 1198),
                ]
            ),
        ],
    }
)


def _cut_list() -> Any:
    request = b7._request(NAME)  # pyright: ignore[reportPrivateUsage]
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / NAME / "members.json").read_text()
    )
    members = [CutListMember.model_validate(item) for item in raw]
    return cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B7",
        length_unit="in",
        pieces=part_pieces(b7._extents(request), members, request.materials),  # pyright: ignore[reportPrivateUsage]
        price_book=BOOK,
    )


def test_the_siding_is_109_boards_of_its_measured_net_area() -> None:
    """The walls' 4 layers and the gables' 2, measured: (939.5 x 108.59375
    - 13 565.75) - 22 x 4.0703125 + 2 x 5 705.185554 = 99 778.902 in², x
    1.10 / 1 008 = 108.886: 109 boards (the walls alone 96.43, 97; the PM's
    100 counted 960 x 108.59375 at the framing, under the corner boards,
    and cased the door's slab)."""
    cut_list = _cut_list()
    (siding,) = [line for line in cut_list.lines if line.siding is not None]
    assert (siding.system, siding.member, siding.quantity) == ("siding", "Siding", 6)
    net = (939.5 * PLATE - 13565.75) - 22 * notch(T) / T + 2 * GABLE
    assert net == pytest.approx(99778.902, abs=1e-3)
    assert (siding.area_mm2 or 0) / IN**2 == pytest.approx(net, abs=1e-4)
    assert (siding.stock_quantity, siding.waste_percent) == (109, 10)
    assert siding.extended_price_cents == 109 * 1398


def test_the_trim_is_8_corner_boards_and_1099_5_in_of_casing() -> None:
    cut_list = _cut_list()
    boards = [line for line in cut_list.lines if line.member == "Corner board"]
    assert [
        (b.quantity, round(b.length_mm / IN, 6), b.stock_length_ft) for b in boards
    ] == [(8, 108.59375, 10)]
    casing = [line for line in cut_list.lines if line.member == "Casing"]
    lengths = Counter({round(line.length_mm / IN, 6): line.quantity for line in casing})
    assert lengths == Counter({31.0: 4, 43.0: 10, 44.5: 1, 55.0: 6, 85.5: 2})
    assert sum(k * n for k, n in lengths.items()) == 1099.5
    assert all(line.system == "siding" and line.profile == "5/4x4" for line in casing)
    trim = 8 * 1498 + 23 * 1198
    assert sum(line.extended_price_cents or 0 for line in [*boards, *casing]) == trim


def test_every_line_is_priced() -> None:
    cut_list = _cut_list()
    assert cut_list.unpriced_lines == 0
    assert cut_list.unclassified == 0
    assert cut_list.total_price_cents == sum(
        line.extended_price_cents or 0 for line in cut_list.lines
    )


# --- 4. The other finishes and houses ----------------------------------------------


def _cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(gzip.decompress(CASES.read_bytes()))
    return cases


#: Each case's finish: siding layers, corner boards, casing pieces, gable
#: layers. The L has 5 outside corners (10 boards) and an inside one (none);
#: B7 turned has no openings and its gables run through; B10's roof is
#: 1.6.0, so its gables are bare.
COUNTS = {
    "b7-vinyl": (4, 8, 23, 2),
    "b7-cedar": (4, 8, 23, 2),
    "b7-336": (4, 8, 23, 2),
    "b7-8-12": (4, 8, 23, 2),
    "b7-unsheathed": (0, 0, 0, 0),
    "l-hip": (6, 10, 0, 0),
    "along-y-moved": (4, 8, 0, 2),
    "b9": (4, 8, 23, 2),
    "b8": (4, 8, 23, 2),
    "b10": (4, 8, 23, 0),
}


@pytest.mark.parametrize("case", _cases(), ids=[c["name"] for c in _cases()])
def test_each_case_builds_its_finish_with_no_interference(case: dict[str, Any]) -> None:
    request = EvaluateTreeRequest.model_validate(case["request"])
    solids: list[Solid] = list(build_model_solid(request).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    assert len(solids) == case["bodies"]
    assert all(s.is_valid for s in solids)
    assert b7._overlapping(solids) == []  # pyright: ignore[reportPrivateUsage]
    found = (case["siding"], case["corner_board"], case["casing"], case["gable_siding"])
    assert found == COUNTS[case["name"]]


# --- Mass and expected.json's numbers -----------------------------------------------


def test_every_body_weighs_by_its_member_material() -> None:
    request = b7._request(NAME)  # pyright: ignore[reportPrivateUsage]
    response = b7.client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    want = sum(
        float(measure_shape(m.solid).volume) * b7.DENSITY[m.material] * 1e-6
        for m in script()
    )
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


def numbers(mine: Sequence[b7.Member], volume_in3: float) -> dict[str, Any]:
    """A golden's mass properties, topology and mesh counts from a script:
    the volume analytic, the rest measured on its solids; a planar face of
    n vertices on h holes meshes as n + 2h - 2 triangles."""
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
        "volume": volume_in3 * IN**3,
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


def expected_numbers() -> dict[str, Any]:
    return numbers(script(), house_volume())


if __name__ == "__main__":
    json.dump(expected_numbers(), sys.stdout, indent=2)
    sys.stdout.write("\n")
