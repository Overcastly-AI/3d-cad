"""SLAB acceptance: B8 on its slab and B2's plain slab, on STEP.

``goldens/b8-slab-house`` is B8 (docs/reference-parts/buildings.md): one
``loft.slab`` 1.0.0 on B7's 288 x 192 outline sketch (4 in thick, a 12 in
thickened edge 12 deep overall, two #4 loops listed), ``loft.wall`` 1.4.0 on
the outline standing on the slab, B7's door and four windows and B7's roof.
``goldens/b2-slab-plain`` is B2's typed 144 x 120 x 4 slab with the edge off.
``model.json`` and ``members.json`` are pinned to the plugins by
``packages/loft-plugins/tests/test_slab.py``. Geometry never learns plugins
exist, so this module imports nothing from them.

Checked here against an INDEPENDENT build123d script: the slab typed from
buildings.md (a 288 x 192 x 12 box less the 264 x 168 x 8 pocket under it),
and B7's walls, openings and roof from ``test_outline_b7.script`` (typed from
the QA-B7-HOUSE round) less its floor, lowered by the subfloor's top
(11.46875) so the walls stand on the slab at Z 0:

1. the STEP's 179 solids are the script's, solid for solid; the slab alone
   is 308 736 in^3 (221 184 + 87 552) and the house b7-outline's volume less
   the floor's 105 299.625 plus the slab's;
2. interference none (the bottom plates sit on the slab, face to face);
3. the cut list: Concrete 308 736 in^3 = 6.62 yd^3, ordered 7.00 with the 5%
   allowance (6.95 rounded up to 1/4); Rebar 2 @ 912, 10 sticks; Anchor bolt
   19 (3 + 3 + 5 + 4 + 4); each priced; B2's plain slab 1.48 yd^3, ordered
   1.75 (1.56 rounded up).

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_slab_b8.py [b2]``.
"""

import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from build123d import Pos, Solid
from geometry.kernel import measure_shape
from loft_wire.cut_list import (
    CutListMember,
    cut_list_csv,
    cut_list_response,
    part_pieces,
)
from loft_wire.price_book import PriceBookResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_outline_b7 as b7

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
B8, B2 = "b8-slab-house", "b2-slab-plain"
IN = b7.IN
CONCRETE = "concrete"
DENSITY = {**b7.DENSITY, CONCRETE: 2400.0}  # kg/m^3

# --- The slab, typed from buildings.md (inches) -------------------------------------

#: B8: X 0..288, Y 0..192, Z -4..0, and the edge ring Z -12..-4, 12 wide.
SLAB_T, EDGE_W, EDGE_D = 4, 12, 12


def slab_volume(length: int, depth: int, edge: bool) -> Fraction:
    """The plate plus the ring (outer less inner, times its depth below)."""
    plate = Fraction(length * depth * SLAB_T)
    if not edge:
        return plate
    ring = length * depth - (length - 2 * EDGE_W) * (depth - 2 * EDGE_W)
    return plate + Fraction(ring * (EDGE_D - SLAB_T))


def slab_solid(length: float, depth: float, edge: bool) -> Solid:
    """A box from Z -12 (or -4) to 0, less the pocket inside the ring."""
    bottom = -EDGE_D if edge else -SLAB_T
    solid = b7.box((0, length, 0, depth, bottom, 0))
    if edge:
        pocket = b7.box(
            (EDGE_W, length - EDGE_W, EDGE_W, depth - EDGE_W, -EDGE_D, -SLAB_T)
        )
        solid = solid.cut(pocket).solids()[0]  # pyright: ignore[reportUnknownMemberType]
    return solid


def script(name: str = B8) -> list[b7.Member]:
    """The golden's bodies as build123d solids, sharing no plugin code."""
    if name == B2:
        return [b7.Member("Slab", CONCRETE, slab_solid(144, 120, False))]
    floor = len(b7.floor_boxes(288.0))
    lowered = [
        b7.Member(m.member, m.material, Pos(0, 0, -b7.BASE * IN) * m.solid)
        for m in b7.script()[floor:]
    ]
    return [b7.Member("Slab", CONCRETE, slab_solid(288, 192, True)), *lowered]


def floor_volume() -> Fraction:
    return sum(
        (
            (Fraction(x1) - Fraction(x0))
            * (Fraction(y1) - Fraction(y0))
            * (Fraction(z1) - Fraction(z0))
            for _, _, (x0, x1, y0, y1, z0, z1) in b7.floor_boxes(288.0)
        ),
        Fraction(0),
    )


def analytic_volume(name: str = B8) -> float:
    """in^3: B2's box; B8's slab plus b7-outline's house less its floor."""
    if name == B2:
        return float(slab_volume(144, 120, False))
    return b7.analytic_volume(288) + float(slab_volume(288, 192, True) - floor_volume())


# --- Reading the golden --------------------------------------------------------------


def _members(name: str) -> list[CutListMember]:
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / name / "members.json").read_text()
    )
    return [CutListMember.model_validate(item) for item in raw]


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return b7._step_solids(tmp_path_factory, B8)  # pyright: ignore[reportPrivateUsage]


# --- 1. The STEP against the script ------------------------------------------------


def test_the_volumes_are_the_hand_typed_ones() -> None:
    assert slab_volume(288, 192, True) == 221184 + 87552 == 308736
    assert slab_volume(144, 120, False) == 69120
    assert floor_volume() == Fraction(842397, 8)
    assert analytic_volume() == pytest.approx(
        264852.3788656 - 105299.625 + 308736, abs=1e-6
    )


def test_the_step_is_the_independent_scripts(step_solids: list[Solid]) -> None:
    mine = script()
    assert len(step_solids) == len(mine) == 217 - 39 + 1
    assert b7._unmatched(step_solids, [m.solid for m in mine]) == []  # pyright: ignore[reportPrivateUsage]
    volume = sum(float(measure_shape(s).volume) for s in step_solids) / IN**3
    assert volume == pytest.approx(analytic_volume(), abs=1e-4)


def test_nothing_interferes(step_solids: list[Solid]) -> None:
    assert b7._overlapping(step_solids) == []  # pyright: ignore[reportPrivateUsage]


def test_the_walls_stand_on_the_slab_top() -> None:
    solids = [m.solid for m in script()]
    slab = solids[0].bounding_box()
    assert pytest.approx((-12 * IN, 0.0), abs=1e-9) == (slab.min.Z, slab.max.Z)
    above = min(s.bounding_box().min.Z for s in solids[1:])
    assert above == pytest.approx(0.0, abs=1e-9)


# --- 2. The cut list and its price -------------------------------------------------

#: $165.00 per yd^3 of ready-mix, $14.98 a 20 ft #4 stick, $2.48 a bolt.
BOOK = PriceBookResponse.model_validate(
    {
        "currency": "USD",
        "entries": [
            {
                "material": "concrete",
                "profile": "ready_mix",
                "unit": "cubic_yard",
                "price_cents": 16500,
            },
            {
                "material": "steel_a615",
                "profile": "rebar_4",
                "unit": "each",
                "stock_length_ft": 20,
                "price_cents": 1498,
            },
            {
                "material": "steel_f1554",
                "profile": "anchor_bolt_1_2",
                "unit": "each",
                "price_cents": 248,
            },
        ],
    }
)


def _cut_list(name: str) -> Any:
    request = b7._request(name)  # pyright: ignore[reportPrivateUsage]
    extents = b7._extents(request)  # pyright: ignore[reportPrivateUsage]
    return cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name=name,
        length_unit="in",
        pieces=part_pieces(extents, _members(name), request.materials),
        price_book=BOOK,
    )


def test_b8_lists_its_concrete_rebar_and_bolts_priced() -> None:
    cut_list = _cut_list(B8)
    foundation = [line for line in cut_list.lines if line.system == "foundation"]
    assert [(line.member, line.item, line.quantity) for line in foundation] == [
        ("Slab", "concrete", 1),
        ("Rebar", "rebar", 2),
        ("Anchor bolt", "anchor_bolt", 19),
    ]
    concrete, rebar, bolts = foundation
    # 308 736 in^3 / 46 656 = 6.617 yd^3; x 1.05 = 6.948, ordered 7.
    assert concrete.volume_mm3 == pytest.approx(308736 * IN**3, abs=1e-3)
    assert round(concrete.volume_mm3 / IN**3 / 46656, 2) == 6.62
    assert (concrete.order_yd3, concrete.waste_percent) == (7.0, 5)
    assert (concrete.unit_price_cents, concrete.extended_price_cents) == (16500, 115500)
    # Two loops of 912 in (76 ft): ceil(76 / 18) = 5 sticks each.
    assert round(rebar.length_mm / IN, 6) == 912
    assert (rebar.stock_length_ft, rebar.stock_quantity) == (20, 10)
    assert rebar.extended_price_cents == 10 * 1498
    assert (bolts.stock_quantity, bolts.extended_price_cents) == (19, 19 * 248)
    # The bottom plates the bolts were counted on: front cut at the door.
    plates = [
        (line.quantity, round(line.length_mm / IN, 4))
        for line in cut_list.lines
        if line.member == "Bottom plate"
    ]
    assert plates == [(2, 125.0), (2, 181.0), (1, 288.0)]
    assert cut_list.unclassified == 0
    csv = cut_list_csv(cut_list).split("\r\n")
    assert csv[1].startswith("1,Foundation,Slab,Ready-mix concrete,,")
    assert csv[1].endswith(",6.62 yd3 net + 5% waste,,7.00,165.00,Per yd3,1155.00")


def test_b2s_plain_slab_is_1_48_yd3_and_orders_1_75() -> None:
    (line,) = _cut_list(B2).lines
    assert line.volume_mm3 == pytest.approx(69120 * IN**3, abs=1e-4)
    assert round(line.volume_mm3 / IN**3 / 46656, 2) == 1.48
    # 1.4815 x 1.05 = 1.556, rounded up to 1/4: 1.75 ($288.75).
    assert (line.order_yd3, line.extended_price_cents) == (1.75, 28875)


def test_every_body_weighs_by_its_member_material() -> None:
    for name in (B8, B2):
        request = b7._request(name)  # pyright: ignore[reportPrivateUsage]
        assert request.materials is not None
        assert request.materials.default_material is None
        response = b7.client.post(
            "/api/v1/evaluate", json=request.model_dump(mode="json")
        )
        assert response.status_code == 200, response.text
        want = sum(
            float(measure_shape(m.solid).volume) * DENSITY[m.material] * 1e-6
            for m in script(name)
        )
        assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


# --- expected.json's numbers ---------------------------------------------------------


def expected_numbers(name: str = B8) -> dict[str, Any]:
    """The golden's mass properties, topology and mesh counts from the
    script: volume analytic, the rest measured on the script's solids; a
    planar face of n vertices on h holes meshes as n + 2h - 2 triangles."""
    mine = script(name)
    volume = analytic_volume(name) * IN**3
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
            mass_moments[k] += v * DENSITY[m.material] * 1e-6 * value
        mass += v * DENSITY[m.material] * 1e-6
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


@pytest.mark.parametrize("name", [B8, B2])
def test_expected_json_is_the_scripts_numbers(name: str) -> None:
    expected = json.loads((GOLDENS / name / "expected.json").read_text())
    numbers = expected_numbers(name)
    tolerance = expected["tolerance"]
    props = expected["properties"]
    assert props["volume"] == pytest.approx(numbers["volume"], abs=tolerance)
    assert props["surface_area"] == pytest.approx(
        numbers["surface_area"], abs=tolerance
    )
    assert props["mass_g"] == pytest.approx(numbers["mass_g"], abs=tolerance)
    for key, got in (
        ("centroid", props["centroid"]),
        ("center_of_mass", props["center_of_mass"]),
    ):
        assert [got[k] for k in "xyz"] == pytest.approx(numbers[key], abs=tolerance)
    box = props["bounding_box"]
    assert [box["min"][k] for k in "xyz"] + [box["max"][k] for k in "xyz"] == (
        pytest.approx(numbers["bbox"], abs=1e-9)
    )
    assert expected["topology"] == numbers["topology"]
    assert expected["mesh"] == numbers["mesh"]


if __name__ == "__main__":
    which = B2 if sys.argv[1:2] == ["b2"] else B8
    json.dump(expected_numbers(which), sys.stdout, indent=2)
    sys.stdout.write("\n")
