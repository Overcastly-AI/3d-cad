"""INTERIOR-WALLS acceptance: B10, B7 with two partitions, on STEP.

``goldens/b10-partitions`` is B7's outline tree (``b7-outline``) with two
lines added to its sketch, its walls at ``loft.wall`` 1.4.0, one
``loft.interior_wall`` 1.0.0 on them and a 2868 door (``loft.door`` 1.4.0)
in P2: ``model.json`` and ``members.json`` are pinned to the plugins by
``packages/loft-plugins/tests/test_interior_walls.py``. Geometry never learns
plugins exist, so this module imports nothing from them.

Checked against members typed by hand from ``docs/reference-parts/
buildings.md`` B10 (:func:`b10_members`), added to B7's independent script
(``test_outline_b7.script``, which shares no code with the plugins):

1. the STEP's 284 solids are the script's 217 and B10's 67, solid for solid,
   and the volume is B7's 264 852.3788656 in^3 plus B10's 45 623.25 in^3;
2. interference none, every pair probed exactly;
3. the cut list: 2 partitions' studs, plates, door framing and 12 blocks
   under Walls, the 20 gypsum panels as 48 130.5 in^2 bought as 11 sheets
   of 4x8, the door one Each line.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_partitions_b10.py``.
"""

import itertools
import json
import sys
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from build123d import (
    Solid,
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from fastapi.testclient import TestClient
from geometry.kernel import measure_shape
from geometry.kernel.interference import probe_overlap
from geometry.main import app
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMember,
    cut_list_response,
    part_pieces,
)
from loft_wire.cut_list_csv import (
    cut_list_csv,
)
from loft_wire.features import EvaluateTreeRequest, ExportTreeRequest
from loft_wire.price_book import PriceBookResponse

# B7's independent script. pytest imports test modules in importlib mode, so
# put this directory on the path to read it (only its helpers, no tests).
sys.path.insert(0, str(Path(__file__).parent))
from test_outline_b7 import (
    BASE,
    DENSITY,
    IN,
    SPF,
    Member,
    analytic_volume,
    box,
    script,
)

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
NAME = "b10-partitions"
GYP = "gypsum"
DENSITIES = {**DENSITY, GYP: 846.0}

Bounds = tuple[float, float, float, float, float, float]

# --- B10, typed from buildings.md (inches, world) -------------------------------------

T = 1.5  # 2x lumber's thickness
P = 3.5  # a 2x4 partition's depth
STUD_Z = (BASE + T, BASE + 94.125)  # bottom plate to the double top plate
TOP_Z = [(BASE + 94.125, BASE + 95.625), (BASE + 95.625, BASE + 97.125)]
BOTTOM_Z = (BASE, BASE + T)
P1_X = (178.25, 181.75)  # X 180, centred
P2_Y = (130.25, 133.75)  # Y 132, centred
#: P1 from the back wall's inside face (Y 186.5) to the front's (Y 5.5):
#: centres 0.75 from its start, then every 16, the end stud flush.
P1_STUDS = [186.5 - u for u in (0.75, *range(16, 177, 16), 180.25)]
#: P2 from the right wall's inside face (X 282.5) to P1's face (X 181.75),
#: 100.75 long: layout 0.75, 16, ..., 96 and its end stud 100; the door's
#: framing (X 212..252) replaces the studs at u 32, 48 and 64.
P2_STUDS = [282.5 - u for u in (0.75, 16, 80, 96, 100)]
#: The door: a 2868 (32 x 80), rough opening 34 x 82.5 centred on X 232.
RO = (215.0, 249.0)
HEAD = 82.5
HEADER = 5.5  # 2x6 plies on edge
#: Two 2x6 plies fill a 2x4 partition with a 1/2 in spacer (HEADER-PLIES).
PLIES = [(130.25, 131.75), (132.25, 133.75)]
#: Ladder blocks: flat 2x4 (3.5 tall, 1.5 deep), centred 24, 48 and 72
#: above the bottom plate's top, across the bay either side of a partition.
BLOCK_Z = [(BASE + T + c - 1.75, BASE + T + c + 1.75) for c in (24, 48, 72)]
LADDERS = [
    (176.75, 191.25, 4.0, 5.5),  # front wall at P1: studs X 176 and 192
    (176.75, 191.25, 186.5, 188.0),  # back wall at P1: the same studs
    (282.5, 284.0, 123.25, 137.75),  # right wall at P2: studs Y 122.5, 138.5
    (180.25, 181.75, 123.25, 137.75),  # P1 at P2: its studs Y 122.5, 138.5
]
#: Gypsum: 1/2 in, two 48 in courses down from the top plate's top.
G = 0.5
COURSES = [(BASE + 1.125, BASE + 49.125), (BASE + 49.125, BASE + 97.125)]


def framing() -> list[tuple[str, Bounds]]:
    """The partitions' framing members and the 12 blocks."""
    x0, x1 = P1_X
    y0, y1 = P2_Y
    out: list[tuple[str, Bounds]] = []
    out += [("Stud", (x0, x1, c - 0.75, c + 0.75, *STUD_Z)) for c in P1_STUDS]
    out += [("Top plate", (x0, x1, 5.5, 186.5, *z)) for z in TOP_Z]
    out.append(("Bottom plate", (x0, x1, 5.5, 186.5, *BOTTOM_Z)))
    out += [("Stud", (c - 0.75, c + 0.75, y0, y1, *STUD_Z)) for c in P2_STUDS]
    out += [
        ("Stud", (RO[0] - 3, RO[0] - 1.5, y0, y1, *STUD_Z)),  # kings
        ("Stud", (RO[1] + 1.5, RO[1] + 3, y0, y1, *STUD_Z)),
        ("Jack", (RO[0] - 1.5, RO[0], y0, y1, BASE + T, BASE + HEAD)),
        ("Jack", (RO[1], RO[1] + 1.5, y0, y1, BASE + T, BASE + HEAD)),
    ]
    out += [
        ("Header", (RO[0] - 1.5, RO[1] + 1.5, a, b, BASE + HEAD, BASE + HEAD + HEADER))
        for a, b in PLIES
    ]
    # Top cripples at the replaced u 48 and 64: X 234.5 and 218.5.
    out += [
        ("Cripple", (c - 0.75, c + 0.75, y0, y1, BASE + HEAD + HEADER, STUD_Z[1]))
        for c in (234.5, 218.5)
    ]
    out += [("Top plate", (181.75, 282.5, y0, y1, *z)) for z in TOP_Z]
    out += [
        ("Bottom plate", (181.75, RO[0], y0, y1, *BOTTOM_Z)),
        ("Bottom plate", (RO[1], 282.5, y0, y1, *BOTTOM_Z)),
    ]
    out += [("Block", (*xy, *z)) for xy in LADDERS for z in BLOCK_Z]
    return out


def gypsum_boxes() -> list[tuple[Bounds, Bounds | None]]:
    """Each panel's box and the notch cut from it: P1's west face whole
    (strips Y 186.5..90.5..5.5), its east face cut at P2 (Y 130.25..133.75);
    P2's faces from X 282.5 to P1's board (X 182.25), the door's rough
    opening cut out (a notch in the upper course's first panel)."""
    out: list[tuple[Bounds, Bounds | None]] = []
    for z0, z1 in COURSES:
        for a, b in ((90.5, 186.5), (5.5, 90.5)):
            out.append(((P1_X[0] - G, P1_X[0], a, b, z0, z1), None))
        for a, b in ((133.75, 186.5), (90.5, 130.25), (5.5, 90.5)):
            out.append(((P1_X[1], P1_X[1] + G, a, b, z0, z1), None))
    for y0, y1 in ((P2_Y[0] - G, P2_Y[0]), (P2_Y[1], P2_Y[1] + G)):
        lower, upper = COURSES
        out += [
            ((RO[1], 282.5, y0, y1, *lower), None),
            ((186.5, RO[0], y0, y1, *lower), None),
            ((182.25, 186.5, y0, y1, *lower), None),
            (
                (186.5, 282.5, y0, y1, *upper),
                (RO[0], RO[1], y0 - 1, y1 + 1, upper[0] - 1, BASE + HEAD),
            ),
            ((182.25, 186.5, y0, y1, *upper), None),
        ]
    return out


def door_unit() -> list[tuple[str, str, Bounds, Bounds | None]]:
    """The 2868 unit (OPENING-UNITS): a frame of 3/4 jambs and head and a
    1-1/4 threshold, 33.5 x 82, P2's depth deep, centred on X 232, round a
    32 x 80 slab 1-3/4 thick at P2's v = 0 face (Y 130.25)."""
    y0, y1 = P2_Y
    frame = (232 - 16.75, 232 + 16.75, y0, y1, BASE, BASE + 82)
    slab = (216.0, 248.0, y0, y0 + 1.75, BASE + 1.25, BASE + 81.25)
    hole = (216.0, 248.0, y0 - 1, y1 + 1, BASE + 1.25, BASE + 81.25)
    return [("Door", SPF, frame, hole), ("Slab", SPF, slab, None)]


def b10_members() -> list[Member]:
    out = [Member(m, SPF, box(b)) for m, b in framing()]
    for outer, notch in gypsum_boxes():
        solid = box(outer)
        if notch is not None:
            solid = solid.cut(box(notch)).solids()[0]  # pyright: ignore[reportUnknownMemberType]
        out.append(Member("Gypsum", GYP, solid))
    for member, material, outer, hole in door_unit():
        solid = box(outer)
        if hole is not None:
            solid = solid.cut(box(hole)).solids()[0]  # pyright: ignore[reportUnknownMemberType]
        out.append(Member(member, material, solid))
    return out


def _vol(b: Bounds) -> Fraction:
    x0, x1, y0, y1, z0, z1 = (Fraction(v) for v in b)
    return (x1 - x0) * (y1 - y0) * (z1 - z0)


def b10_volume() -> Fraction:
    """B10's members in exact rationals (in^3)."""
    total = sum((_vol(b) for _, b in framing()), Fraction(0))
    for outer, notch in gypsum_boxes():
        total += _vol(outer)
        if notch is not None:
            x0, x1, _, _, _, z1 = notch
            y0, y1 = outer[2], outer[3]
            total -= _vol((x0, x1, y0, y1, outer[4], z1))
    for _, _, outer, hole in door_unit():
        total += _vol(outer)
        if hole is not None:
            total -= _vol((hole[0], hole[1], outer[2], outer[3], hole[4], hole[5]))
    return total


def everything() -> list[Member]:
    return script() + b10_members()


# --- Reading the golden ---------------------------------------------------------------


def _request() -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / NAME / "model.json").read_text()
    )


def _members() -> list[CutListMember]:
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / NAME / "members.json").read_text()
    )
    return [CutListMember.model_validate(item) for item in raw]


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    request = ExportTreeRequest.model_validate(
        {**_request().model_dump(mode="json"), "format": "step"}
    )
    response = client.post("/api/v1/export/tree", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    path = tmp_path_factory.mktemp("step") / f"{NAME}.step"
    path.write_bytes(response.content)
    return list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def _signature(solid: Solid) -> tuple[float, ...]:
    bb = solid.bounding_box()
    values = (bb.min.X, bb.max.X, bb.min.Y, bb.max.Y, bb.min.Z, bb.max.Z)
    volume = float(measure_shape(solid).volume) / IN**3
    return (volume, *(v / IN for v in values))


def _unmatched(
    ours: Sequence[Solid], theirs: Sequence[Solid]
) -> list[tuple[float, ...]]:
    """Each of *ours* paired with one of *theirs* of the same volume (1e-4
    in^3) and bounds (1e-5 in); what finds no partner."""
    left = [_signature(s) for s in theirs]
    missing: list[tuple[float, ...]] = []
    for sig in (_signature(s) for s in ours):
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


# --- 1. The STEP against the script ---------------------------------------------------


def test_b10s_members_add_45_623_25_cubic_inches() -> None:
    """Studs 18 + 2 kings at 486.28125, 2 jacks at 425.25, plates 3 x 950.25
    and 2 x 528.9375, bottom plates 174.5625 + 175.875, two plies 305.25 x 2,
    two cripples 32.15625 each, 12 blocks at 76.125; gypsum 48 130.5 in^2 x
    1/2; the door frame 33.5 x 82 x 3.5 less its 32 x 80 opening, and the
    slab 32 x 80 x 1.75."""
    framing_in3 = (
        20 * Fraction(48628125, 100000)
        + 2 * Fraction(42525, 100)
        + 3 * Fraction(95025, 100)
        + 2 * Fraction(5289375, 10000)
        + Fraction(1745625, 10000)
        + Fraction(175875, 1000)
        + 2 * Fraction(30525, 100)
        + 2 * Fraction(3215625, 100000)
        + 12 * Fraction(76125, 1000)
    )
    gypsum = Fraction(481305, 10) * Fraction(1, 2)
    door = (Fraction(335, 10) * 82 - 32 * 80) * Fraction(7, 2) + 32 * 80 * Fraction(
        7, 4
    )
    assert b10_volume() == framing_in3 + gypsum + door
    assert float(b10_volume()) == 45623.25


def test_the_step_is_b7s_script_and_b10s_members(step_solids: list[Solid]) -> None:
    mine = everything()
    assert len(step_solids) == len(mine) == 217 + 67
    assert _unmatched(step_solids, [m.solid for m in mine]) == []
    volume = sum(float(measure_shape(s).volume) for s in step_solids) / IN**3
    assert volume == pytest.approx(analytic_volume(288) + float(b10_volume()), abs=1e-4)


# --- 2. Interference none -------------------------------------------------------------


def test_nothing_interferes(step_solids: list[Solid]) -> None:
    boxes = [s.bounding_box() for s in step_solids]
    bad: list[tuple[int, int, float]] = []
    for i, j in itertools.combinations(range(len(step_solids)), 2):
        a, b = boxes[i], boxes[j]
        if all(
            min(getattr(a.max, k), getattr(b.max, k))
            > max(getattr(a.min, k), getattr(b.min, k))
            for k in ("X", "Y", "Z")
        ):
            probe = probe_overlap(step_solids[i], step_solids[j])
            if probe.unresolved or probe.volume_mm3 != 0.0:
                bad.append((i, j, probe.volume_mm3))
    assert bad == []


# --- 3. The cut list ------------------------------------------------------------------

#: A yard's prices: 2x4 SPF 8 ft $3.98 (studs, blocks, cripples, jacks) and
#: 16 ft $8.98 (plates), 1/2 gypsum 4x8 $14.98, a 2868 prehung door $229.
BOOK = PriceBookResponse.model_validate(
    {
        "currency": "USD",
        "entries": [
            {
                "material": SPF,
                "profile": "us_2x4",
                "unit": "each",
                "stock_length_ft": 8,
                "price_cents": 398,
            },
            {
                "material": SPF,
                "profile": "us_2x4",
                "unit": "each",
                "stock_length_ft": 16,
                "price_cents": 898,
            },
            {
                "material": GYP,
                "profile": "gypsum_1_2",
                "unit": "each",
                "sheet": "4x8",
                "price_cents": 1498,
            },
            {
                "material": SPF,
                "profile": "door_2868",
                "unit": "each",
                "price_cents": 22900,
            },
        ],
    }
)


def _cut_list() -> Any:
    request = _request()
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    extents = BodyExtentsResult.model_validate_json(response.content)
    return cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B10",
        length_unit="in",
        pieces=part_pieces(extents, _members(), request.materials),
        price_book=BOOK,
    )


def test_the_partitions_list_under_walls_and_the_gypsum_buys_eleven_sheets() -> None:
    cut_list = _cut_list()
    walls = [line for line in cut_list.lines if line.system == "walls"]
    gypsum = [line for line in walls if line.profile == "1/2 gypsum"]
    assert len(gypsum) == 1
    assert gypsum[0].member == "Gypsum"
    assert gypsum[0].quantity == 20
    assert round(gypsum[0].area_mm2 / IN**2, 6) == 48130.5
    assert (gypsum[0].sheet, gypsum[0].stock_quantity) == ("4x8", 11)
    assert gypsum[0].extended_price_cents == 11 * 1498
    blocks = [line for line in walls if line.member == "Block"]
    assert [(b.profile, b.quantity, round(b.length_mm / IN, 6)) for b in blocks] == [
        ("2x4", 12, 14.5)
    ]
    assert blocks[0].extended_price_cents == 12 * 398
    door = [line for line in walls if line.unit == "door"]
    assert [(d.profile, d.quantity, d.unit_key) for d in door] == [
        ("2868", 1, "door_2868")
    ]
    assert door[0].extended_price_cents == 22900
    studs = [line for line in walls if line.member == "Stud" and line.profile == "2x4"]
    # 13 in P1, 5 in P2 and P2's two kings, 92.625 long.
    assert [(s.quantity, round(s.length_mm / IN, 6)) for s in studs] == [(20, 92.625)]
    assert cut_list.unclassified == 0
    assert "Walls" in cut_list_csv(cut_list)


# --- Mass -----------------------------------------------------------------------------


def test_every_body_weighs_by_its_material() -> None:
    request = _request()
    response = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    want = sum(
        float(measure_shape(m.solid).volume) * DENSITIES[m.material] * 1e-6
        for m in everything()
    )
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


# --- expected.json's numbers ----------------------------------------------------------


def expected_numbers() -> dict[str, Any]:
    """The golden's mass properties, topology and mesh counts from the
    script: volume analytic, the rest measured on the script's solids; a
    planar face of n vertices on h holes meshes as n + 2h - 2 triangles."""
    mine = everything()
    volume = (analytic_volume(288) + float(b10_volume())) * IN**3
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
            mass_moments[k] += v * DENSITIES[m.material] * 1e-6 * value
        mass += v * DENSITIES[m.material] * 1e-6
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
