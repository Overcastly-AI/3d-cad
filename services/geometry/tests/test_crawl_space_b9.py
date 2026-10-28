"""CRAWL-SPACE acceptance: B9, B7 on a crawl space, on STEP.

``goldens/b9-crawl-space`` is B9 (docs/reference-parts/buildings.md): B7 as
built (b7-outline's sketch, floor, walls, door, four windows and roof) and
ONE ``loft.foundation`` 1.0.0 on its outline under its floor: an 8 in
poured stem on a 16 x 8 in footing, a 24 in crawl, five 16 x 8 vents and a
24 x 16 access cut from the stem's top. ``model.json`` and ``members.json``
are pinned to the plugins by ``packages/loft-plugins/tests/test_crawl_space.py``.
Geometry never learns plugins exist, so this module imports nothing from them.

Checked here against an INDEPENDENT build123d script: the foundation typed
from buildings.md, a pour each (the footing ring X -4..292, Y -4..196 less
X 12..276, Y 12..180, Z -34.5..-26.5; the stem ring on it, X 0..288, Y 0..192
less X 8..280, Y 8..184, Z -26.5..0, less the vents and access as boxes
through it), and B7 from ``test_outline_b7.script`` (typed from the
QA-B7-HOUSE round), unmoved:

1. the STEP's 219 solids are the script's, solid for solid; the foundation
   is 307 328 in^3 (118 784 + 196 736 - 5 x 1 024 - 3 072) and the whole
   b7-outline's volume plus that;
2. interference none (the stem sits on the footing and the sills on the
   stem, face to face);
3. the cut list: Footing and Stem wall, 2 pours of 307 328 in^3 = 6.59 yd^3,
   ordered 7.00 with the 5% allowance (6.92 rounded up to 1/4); Rebar 888 and
   968, 10 sticks; Anchor bolt 18 (5 + 5 + 4 + 4 for the floor's sills); each
   priced.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_crawl_space_b9.py``.
"""

import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from build123d import Solid
from geometry.kernel import measure_shape
from loft_wire.cut_list import (
    CutListMember,
    cut_list_response,
    part_pieces,
)
from loft_wire.cut_list_csv import cut_list_csv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_outline_b7 as b7
import test_slab_b8 as b8

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
B9 = "b9-crawl-space"
IN = b7.IN
CONCRETE = b8.CONCRETE
DENSITY = b8.DENSITY

# --- The foundation, typed from buildings.md (inches) -------------------------------

Bounds = tuple[float, float, float, float, float, float]

#: The stem (outer, inner) and the footing (outer, inner).
STEM: tuple[Bounds, Bounds] = ((0, 288, 0, 192, -26.5, 0), (8, 280, 8, 184, -26.5, 0))
FOOTING: tuple[Bounds, Bounds] = (
    (-4, 292, -4, 196, -34.5, -26.5),
    (12, 276, 12, 180, -34.5, -26.5),
)
#: 16 x 8 vents at X 24, 144, 264 on the front and 24, 264 on the back.
VENTS: list[Bounds] = [
    (16, 32, 0, 8, -8, 0),
    (136, 152, 0, 8, -8, 0),
    (256, 272, 0, 8, -8, 0),
    (16, 32, 184, 192, -8, 0),
    (256, 272, 184, 192, -8, 0),
]
#: The 24 x 16 access centred on the back.
ACCESS: Bounds = (132, 156, 184, 192, -16, 0)


def _volume(b: Bounds) -> Fraction:
    x0, x1, y0, y1, z0, z1 = (Fraction(v) for v in b)
    return (x1 - x0) * (y1 - y0) * (z1 - z0)


def foundation_volume() -> Fraction:
    return (
        _volume(STEM[0])
        - _volume(STEM[1])
        + _volume(FOOTING[0])
        - _volume(FOOTING[1])
        - sum((_volume(v) for v in [*VENTS, ACCESS]), Fraction(0))
    )


def _one(shape: Any) -> Solid:
    (solid,) = shape.solids()
    return solid


def footing_solid() -> Solid:
    return _one(b7.box(FOOTING[0]).cut(b7.box(FOOTING[1])))  # pyright: ignore[reportUnknownMemberType]


def stem_solid() -> Solid:
    stem = b7.box(STEM[0]).cut(b7.box(STEM[1]))  # pyright: ignore[reportUnknownMemberType]
    for hole in [*VENTS, ACCESS]:
        stem = stem.cut(b7.box(hole))  # pyright: ignore[reportUnknownMemberType]
    return _one(stem)


def script() -> list[b7.Member]:
    """The golden's bodies as build123d solids, sharing no plugin code: B7
    as b7-outline builds it, then the foundation."""
    return [
        *b7.script(),
        b7.Member("Footing", CONCRETE, footing_solid()),
        b7.Member("Stem wall", CONCRETE, stem_solid()),
    ]


def analytic_volume() -> float:
    return b7.analytic_volume(288) + float(foundation_volume())


def _members() -> list[CutListMember]:
    raw: list[dict[str, Any]] = json.loads((GOLDENS / B9 / "members.json").read_text())
    return [CutListMember.model_validate(item) for item in raw]


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return b7._step_solids(tmp_path_factory, B9)  # pyright: ignore[reportPrivateUsage]


# --- 1. The STEP against the script ------------------------------------------------


def test_the_volumes_are_the_hand_typed_ones() -> None:
    # buildings.md B9: 7 424 in^2 x 26.5 and 14 848 in^2 x 8.
    assert _volume(STEM[0]) - _volume(STEM[1]) == 7424 * Fraction(53, 2) == 196736
    assert _volume(FOOTING[0]) - _volume(FOOTING[1]) == 14848 * 8 == 118784
    assert [_volume(v) for v in VENTS] == [1024] * 5
    assert _volume(ACCESS) == 3072
    assert foundation_volume() == 307328
    # 307 328 / 46 656 = 6.587 yd^3; x 1.05 = 6.916, ordered 7.00.
    assert round(307328 / 46656, 2) == 6.59
    assert round(307328 / 46656 * 1.05, 2) == 6.92
    pours = [footing_solid(), stem_solid()]
    measured = [float(measure_shape(p).volume) / IN**3 for p in pours]
    assert measured == pytest.approx([118784, 196736 - 5120 - 3072], abs=1e-6)


def test_the_step_is_the_independent_scripts(step_solids: list[Solid]) -> None:
    mine = script()
    assert len(step_solids) == len(mine) == 217 + 2
    assert b7._unmatched(step_solids, [m.solid for m in mine]) == []  # pyright: ignore[reportPrivateUsage]
    volume = sum(float(measure_shape(s).volume) for s in step_solids) / IN**3
    assert volume == pytest.approx(analytic_volume(), abs=1e-4)


def test_nothing_interferes(step_solids: list[Solid]) -> None:
    assert b7._overlapping(step_solids) == []  # pyright: ignore[reportPrivateUsage]


def test_the_stem_sits_on_the_footing_and_the_sills_on_the_stem() -> None:
    mine = script()
    footing, stem = (m.solid.bounding_box() for m in mine[-2:])
    assert pytest.approx((-34.5 * IN, -26.5 * IN), abs=1e-9) == (
        footing.min.Z,
        footing.max.Z,
    )
    assert pytest.approx((-26.5 * IN, 0.0), abs=1e-9) == (stem.min.Z, stem.max.Z)
    above = min(m.solid.bounding_box().min.Z for m in mine[:-2])
    assert above == pytest.approx(0.0, abs=1e-9)


# --- 2. The cut list and its price -------------------------------------------------


def _cut_list() -> Any:
    request = b7._request(B9)  # pyright: ignore[reportPrivateUsage]
    extents = b7._extents(request)  # pyright: ignore[reportPrivateUsage]
    return cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name=B9,
        length_unit="in",
        pieces=part_pieces(extents, _members(), request.materials),
        price_book=b8.BOOK,
    )


def test_b9_lists_its_concrete_rebar_and_bolts_priced() -> None:
    cut_list = _cut_list()
    foundation = [line for line in cut_list.lines if line.system == "foundation"]
    assert [(line.member, line.item, line.quantity) for line in foundation] == [
        ("Footing, Stem wall", "concrete", 2),
        ("Rebar", "rebar", 1),
        ("Rebar", "rebar", 1),
        ("Anchor bolt", "anchor_bolt", 18),
    ]
    concrete, inner, outer, bolts = foundation  # rebar lines by length
    assert concrete.volume_mm3 == pytest.approx(307328 * IN**3, abs=1e-3)
    assert round(concrete.volume_mm3 / IN**3 / 46656, 2) == 6.59
    assert (concrete.order_yd3, concrete.waste_percent) == (7.0, 5)
    assert (concrete.unit_price_cents, concrete.extended_price_cents) == (16500, 115500)
    # Loops of 968 (80.67 ft) and 888 (74 ft): 5 sticks each.
    assert [round(r.length_mm / IN, 6) for r in (inner, outer)] == [888, 968]
    assert [r.stock_quantity for r in (inner, outer)] == [5, 5]
    assert outer.extended_price_cents + inner.extended_price_cents == 10 * 1498
    assert (bolts.stock_quantity, bolts.extended_price_cents) == (18, 18 * 248)
    # The bolts are for the floor's sills: 2 of 288 and 2 of 181.
    sills = [
        (line.quantity, round(line.length_mm / IN, 4))
        for line in cut_list.lines
        if line.member == "Sill" and line.system == "floor"
    ]
    assert sorted(sills) == [(2, 181.0), (2, 288.0)]
    assert cut_list.unclassified == 0
    csv = cut_list_csv(cut_list).split("\r\n")
    assert csv[1].startswith('1,Foundation,"Footing, Stem wall",Ready-mix concrete,,')
    assert csv[1].endswith(",6.59 yd3 net + 5% waste,,7.00,165.00,Per yd3,1155.00")


def test_every_body_weighs_by_its_member_material() -> None:
    request = b7._request(B9)  # pyright: ignore[reportPrivateUsage]
    assert request.materials is not None
    assert request.materials.default_material is None
    response = b7.client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    want = sum(
        float(measure_shape(m.solid).volume) * DENSITY[m.material] * 1e-6
        for m in script()
    )
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


# --- expected.json's numbers ---------------------------------------------------------


def expected_numbers() -> dict[str, Any]:
    """The golden's mass properties, topology and mesh counts from the
    script: volume analytic, the rest measured on the script's solids; a
    planar face of n vertices on h holes meshes as n + 2h - 2 triangles."""
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
        "foundation_topology": [
            (len(m.solid.faces()), len(m.solid.edges())) for m in mine[-2:]
        ],
    }


def test_the_foundations_faces_are_the_hand_count() -> None:
    """A ring prism is 10 faces (top and bottom, each with a hole, and 4 + 4
    sides), 24 edges and 16 vertices: V - E + F - holes = 16 - 24 + 10 - 2 =
    0, one handle. The footing is one. On the stem, each of the six openings
    through its top splits the top once more and adds a bottom and two jambs
    (+3 faces), its 2 + 2 jamb and 2 + 2 sill edges and the two top edges it
    cuts in two (+12 edges, +8 vertices): 10 - 1 + 6 + 18 = 33 faces, 96
    edges, 64 vertices (64 - 96 + 33 - 1 = 0)."""
    footing, stem = footing_solid(), stem_solid()
    assert (len(footing.faces()), len(footing.edges())) == (10, 24)
    assert (len(stem.faces()), len(stem.edges())) == (33, 96)
    assert len(stem.vertices()) == 64


def test_expected_json_is_the_scripts_numbers() -> None:
    expected = json.loads((GOLDENS / B9 / "expected.json").read_text())
    numbers = expected_numbers()
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
    json.dump(expected_numbers(), sys.stdout, indent=2)
    sys.stdout.write("\n")
