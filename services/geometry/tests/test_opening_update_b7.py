"""OPENING-UPDATE acceptance: B7 updated in one step, on STEP.

``goldens/b7-opening-update`` is ``b7-outline`` after "Update all": its
walls at ``loft.wall`` 1.5.0 (their Exterior finish at its default,
fibre-cement lap with corner boards and casing, SIDING-TRIM: the finish is
``_siding_builder.wall_finish_members``), the door and the five windows at
``loft.door``/``loft.window`` 1.5.0 and the roof at ``loft.roof`` 1.5.0
(the floor, 1.2.0, is offered no update). ``model.json`` and
``members.json`` are pinned to the plugins by
``packages/loft-plugins/tests/test_opening_update.py``. Geometry never
learns plugins exist, so this module imports nothing from them.

Checked against an INDEPENDENT build123d script: B7 from
``test_outline_b7.script`` (typed from the QA-B7-HOUSE round) and, typed
from buildings.md B7's Headers, each opening's middle 2x6 ply (2 to 3.5 in
from the wall's outside face) and its two 1/2 in plywood spacers (1.5 to 2
and 3.5 to 4), each the header's length and its 5.5 depth:

1. the STEP's 235 solids are the script's, solid for solid, and the volume
   is b7-outline's 264 852.3789 in^3 + 6 plies (8.25 x 214.5 = 1 769.625) +
   12 spacers (2.75 x 429 = 1 179.75) = 267 801.7539 in^3;
2. interference none: each spacer meets its plies face to face;
3. the cut list carries 18 plies (3 x 41, 9 x 39.5, 6 x 27.5) and one
   "1/2 plywood" line under Walls, 12 spacers of 2 359.5 in^2 cut from ONE
   4x8, every line priced;
4. the golden's numbers are b7-outline's plus the 18 boxes, by hand.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_opening_update_b7.py``.
"""

import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from build123d import Solid
from geometry.kernel import measure_shape
from loft_wire.cut_list import CutListMember, cut_list_response, part_pieces
from loft_wire.price_book import PriceBookResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _siding_builder as finish
import test_outline_b7 as b7

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
NAME = "b7-opening-update"
IN = b7.IN
SPF, PLY = b7.SPF, b7.PLY_M

#: The header's depth (a 2x6 on edge) and, across the 5.5 in wall from its
#: outside face, the middle ply and the two spacers (IRC R602.7: 1.5 + 0.5 +
#: 1.5 + 0.5 + 1.5).
HEADER = 5.5
MIDDLE = (2.0, 3.5)
SPACERS = ((1.5, 2.0), (3.5, 4.0))


def added_boxes() -> list[tuple[str, str, b7.Bounds]]:
    """Each opening's middle ply and spacers, over the jacks' outer faces
    (the rough opening plus 1.5 each side) from the head up 5.5."""
    out: list[tuple[str, str, b7.Bounds]] = []
    for wall in b7.walls(288.0):
        for o in wall.openings:
            u0, u1 = o.centre - o.width / 2 - 1.5, o.centre + o.width / 2 + 1.5
            z = (o.head, o.head + HEADER)
            out.append(("Header", SPF, wall.box(u0, u1, *MIDDLE, *z)))
            out += [("Spacer", PLY, wall.box(u0, u1, *v, *z)) for v in SPACERS]
    return out


def script() -> list[b7.Member]:
    return [*framed(), *finish.wall_finish_members()]


def framed() -> list[b7.Member]:
    """B7 with the plies and spacers, before its finish."""
    return [
        *b7.script(),
        *(b7.Member(m, mat, b7.box(b)) for m, mat, b in added_boxes()),
    ]


def added_volume() -> Fraction:
    exact = Fraction(0)
    for _, _, (x0, x1, y0, y1, z0, z1) in added_boxes():
        exact += (
            (Fraction(x1) - Fraction(x0))
            * (Fraction(y1) - Fraction(y0))
            * (Fraction(z1) - Fraction(z0))
        )
    return exact


def analytic_volume() -> float:
    return framed_volume() + finish.wall_finish_volume()


def framed_volume() -> float:
    return b7.analytic_volume(288) + float(added_volume())


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return b7._step_solids(tmp_path_factory, NAME)  # pyright: ignore[reportPrivateUsage]


# --- 1. The volume and the STEP against the script ---------------------------------


def test_the_volume_is_b7s_plus_the_plies_and_spacers() -> None:
    """The headers run 41 (the door), 39.5 (three 36 in windows) and 27.5
    (two 24 in windows): 214.5 in. A ply is 1.5 x 5.5 = 8.25 in^2 and a
    spacer 0.5 x 5.5 = 2.75 in^2 in section."""
    lengths = [max(b[1] - b[0], b[3] - b[2]) for _, _, b in added_boxes()]
    assert sorted(lengths) == sorted([41.0] * 3 + [39.5] * 9 + [27.5] * 6)
    plies = Fraction(33, 4) * Fraction(429, 2)  # 8.25 x 214.5 = 1 769.625
    spacers = Fraction(11, 4) * 429  # 2.75 x 429 = 1 179.75
    assert (plies, spacers) == (Fraction(14157, 8), Fraction(4719, 4))
    assert added_volume() == plies + spacers
    assert framed_volume() == pytest.approx(267801.7538656, abs=1e-6)


def test_the_step_is_the_independent_scripts(step_solids: list[Solid]) -> None:
    mine = script()
    assert len(step_solids) == len(mine) == 217 + 18 + 4 + 8 + 23
    assert b7._unmatched(step_solids, [m.solid for m in mine]) == []  # pyright: ignore[reportPrivateUsage]
    volume = sum(float(measure_shape(s).volume) for s in step_solids) / IN**3
    assert volume == pytest.approx(analytic_volume(), abs=1e-4)


# --- 2. Interference none ----------------------------------------------------------


def test_nothing_interferes(step_solids: list[Solid]) -> None:
    assert b7._overlapping(step_solids) == []  # pyright: ignore[reportPrivateUsage]


# --- 3. The cut list and its price -------------------------------------------------

#: B7's book (test_outline_b7.BOOK), a 4x8 sheet of 1/2 plywood, $32.98, and
#: the finish's lap ($13.98 a 12 ft board) and 5/4x4 trim (10 ft $14.98, 8 ft
#: $11.98).
BOOK = PriceBookResponse.model_validate(
    {
        "currency": "USD",
        "entries": [
            *(e.model_dump(mode="json") for e in b7.BOOK.entries),
            {
                "material": PLY,
                "profile": "plywood_1_2",
                "unit": "each",
                "sheet": "4x8",
                "price_cents": 3298,
            },
            *(
                {
                    "material": finish.FC,
                    "profile": p,
                    "unit": "each",
                    **stock,
                    "price_cents": c,
                }
                for p, stock, c in [
                    ("fibre_cement_lap_8_25", {"stock_length_ft": 12}, 1398),
                    ("us_5_4x4", {"stock_length_ft": 10}, 1498),
                    ("us_5_4x4", {"stock_length_ft": 8}, 1198),
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


def test_the_cut_list_lists_18_plies_and_one_sheet_of_spacers() -> None:
    """The round's lines with the headers 3 per opening and the spacers one
    line under Walls, 12 pieces cut to size from one 4x8 (a 48 in sheet
    takes eight 5.5 in strips across, each 96 in long holding two of them);
    every line priced: B7's $2,968.79, six more 8 ft 2x6 at $6.48 and the
    sheet, $3,040.65."""
    cut_list = _cut_list()
    headers = sorted(
        (line.quantity, round(line.length_mm / IN, 4))
        for line in cut_list.lines
        if line.member == "Header"
    )
    assert headers == [(3, 41.0), (6, 27.5), (9, 39.5)]
    (spacers,) = [line for line in cut_list.lines if line.member == "Spacer"]
    assert (spacers.profile, spacers.material, spacers.quantity) == (
        "1/2 plywood",
        PLY,
        12,
    )
    assert spacers.system == "walls"
    assert round((spacers.area_mm2 or 0) / IN**2, 6) == 2359.5
    assert (spacers.sheet, spacers.stock_quantity) == ("4x8", 1)
    assert spacers.extended_price_cents == 3298
    # Every other line is b7-outline's, but the headers (12 -> 18 pieces).
    rest = sorted(
        (line.member, line.quantity, round(line.length_mm / IN, 4))
        for line in cut_list.lines
        if line.member not in ("Header", "Spacer", "Subfloor", "Sheathing")
        and line.system != "siding"
    )
    want = sorted(
        (m, q, round(v, 4))
        for m, q, v, _ in b7.HOUSE
        if m not in ("Header", "Subfloor", "Sheathing")
    )
    assert rest == want
    assert cut_list.unpriced_lines == 0
    assert cut_list.unclassified == 0
    # The finish (SIDING-TRIM): the walls' 88 368.53125 in² of lap x 1.10 /
    # 1 008 = 96.43, 97 boards; 8 corner boards on 10 ft and 23 casing
    # pieces on 8 ft stock.
    (siding,) = [line for line in cut_list.lines if line.siding is not None]
    assert (siding.quantity, siding.stock_quantity) == (4, 97)
    lap = 97 * 1398 + 8 * 1498 + 23 * 1198
    assert cut_list.total_price_cents == 296879 + 6 * 648 + 3298 + lap


# --- Mass ---------------------------------------------------------------------------


def test_every_body_weighs_by_its_member_material() -> None:
    request = b7._request(NAME)  # pyright: ignore[reportPrivateUsage]
    response = b7.client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    want = sum(
        float(measure_shape(m.solid).volume) * b7.DENSITY[m.material] * 1e-6
        for m in script()
    )
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


# --- 4. expected.json, by hand from b7-outline's ------------------------------------


def _expected(name: str) -> dict[str, Any]:
    return json.loads((GOLDENS / name / "expected.json").read_text())


def test_the_golden_is_b7_outlines_plus_eighteen_boxes() -> None:
    """Each added body is a separate box: 6 faces, 12 edges and a shell;
    meshed, 4 vertices and 2 triangles a face; the walls' finish adds its
    script's solids as measured (``_siding_builder``). A ply of length L adds
    2 (8.25 + 7 L) in^2 of area and a spacer 2 (2.75 + 6 L): with 214.5 in
    of each ply and 429 in of spacers, 99 + 3 003 + 66 + 5 148 = 8 316 in^2.
    The mass adds 1 769.625 in^3 of SPF (450) and 1 179.75 of plywood (577)."""
    old, new = _expected("b7-outline"), _expected(NAME)
    trim = finish.numbers_of(finish.wall_finish_members())
    assert new["topology"] == {
        "faces": old["topology"]["faces"] + 18 * 6 + trim["faces"],
        "edges": old["topology"]["edges"] + 18 * 12 + trim["edges"],
        "shells": old["topology"]["shells"] + 18 + 35,
    }
    assert new["mesh"] == {
        "vertices": old["mesh"]["vertices"] + 18 * 24 + trim["vertices"],
        "triangles": old["mesh"]["triangles"] + 18 * 12 + trim["triangles"],
    }
    old_p, new_p = old["properties"], new["properties"]
    mm3 = IN**3
    plies, spacers = 1769.625 * mm3, 1179.75 * mm3
    lap = finish.wall_finish_volume() * mm3
    assert new_p["volume"] == pytest.approx(
        old_p["volume"] + plies + spacers + lap, abs=1e-5
    )
    assert new_p["surface_area"] == pytest.approx(
        old_p["surface_area"] + 8316 * IN**2 + trim["area"], abs=1e-5
    )
    added_mass = (plies * 450 + spacers * 577) * 1e-6 + trim["mass"]
    assert new_p["mass_g"] == pytest.approx(old_p["mass_g"] + added_mass, abs=1e-5)
    # The centroid: b7-outline's moment plus each box's volume at its centre,
    # plus the finish's.
    moment = [
        old_p["volume"] * old_p["centroid"][k] + trim["moment"][i]
        for i, k in enumerate("xyz")
    ]
    mass_moment = [
        old_p["mass_g"] * old_p["center_of_mass"][k] + trim["mass_moment"][i]
        for i, k in enumerate("xyz")
    ]
    for _, material, b in added_boxes():
        v = (b[1] - b[0]) * (b[3] - b[2]) * (b[5] - b[4]) * mm3
        density = 450 if material == SPF else 577
        for k in range(3):
            centre = (b[2 * k] + b[2 * k + 1]) / 2 * IN
            moment[k] += v * centre
            mass_moment[k] += v * density * 1e-6 * centre
    for k, axis in enumerate("xyz"):
        assert new_p["centroid"][axis] == pytest.approx(
            moment[k] / new_p["volume"], abs=1e-9
        )
        assert new_p["center_of_mass"][axis] == pytest.approx(
            mass_moment[k] / new_p["mass_g"], abs=1e-9
        )
    box = new_p["bounding_box"]
    # The finish stands 1 7/16 in proud of the framing at its corner boards.
    # The side walls' boards: X -1 7/16 and 289 7/16; Y and Z are the eaves'
    # and the ridge's, as before.
    assert box["min"]["x"] == pytest.approx(-(7 / 16 + 1) * IN, abs=1e-9)
    assert box["max"]["x"] == pytest.approx((288 + 7 / 16 + 1) * IN, abs=1e-9)
    for key in ("y", "z"):
        assert box["min"][key] == old_p["bounding_box"]["min"][key]
        assert box["max"][key] == old_p["bounding_box"]["max"][key]


# --- expected.json's numbers ---------------------------------------------------------


def expected_numbers() -> dict[str, Any]:
    """As test_outline_b7.expected_numbers, over this script."""
    mine = script()
    volume = analytic_volume() * IN**3
    area = sum(float(measure_shape(m.solid).surface_area) for m in mine)
    moments = [0.0, 0.0, 0.0]
    mass = 0.0
    mass_moments = [0.0, 0.0, 0.0]
    vertices = triangles = faces = edges = 0
    for m in mine:
        props = measure_shape(m.solid)
        v = float(props.volume)
        c = props.centroid
        for k, value in enumerate((c.x, c.y, c.z)):
            moments[k] += v * value
            mass_moments[k] += v * b7.DENSITY[m.material] * 1e-6 * value
        mass += v * b7.DENSITY[m.material] * 1e-6
        faces += len(m.solid.faces())
        edges += len(m.solid.edges())
        for face in m.solid.faces():
            loops = face.wires()
            n = sum(len(w.edges()) for w in loops)
            vertices += n
            triangles += n + 2 * (len(loops) - 1) - 2
    total = sum(float(measure_shape(m.solid).volume) for m in mine)
    bb = [m.solid.bounding_box() for m in mine]
    return {
        "volume": volume,
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
