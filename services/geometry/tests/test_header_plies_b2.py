"""HEADER-PLIES acceptance: B2's four walls in 2x6 with its door and window
at ``loft.window``/``loft.door`` 1.4.0, on STEP.

``goldens/b2-2x6-walls-header-plies`` is the four walls' expansions
(``model.json``) and their members' metadata (``members.json``), pinned to
the plugins by ``packages/loft-plugins/tests/test_header_plies.py``. Each
opening's header fills the 5-1/2 in wall with three 2x6 plies and two 1/2 in
spacers (IRC R602.7). Checked here against members typed by hand from B2's
plan at 2x6 (:func:`spec_boxes`), never from the plugin:

1. the cut list lists three header plies per opening (3 x 41 and
   3 x 27.5), and a price book prices them by the stock piece;
2. the exported STEP's solids are the typed members box for box, summing
   to 45 201.75 in^3, and none enters a rough opening;
3. interference none: no two solids overlap, the middle ply included.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from build123d import Solid, import_step  # pyright: ignore[reportUnknownVariableType]
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
from loft_wire.features import EvaluateTreeRequest, ExportTreeRequest
from loft_wire.price_book import PriceBookEntry, PriceBookResponse

client = TestClient(app)

GOLDEN = "b2-2x6-walls-header-plies"
GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
IN = 25.4
SPF, PT = "spf_lumber", "southern_pine_pt"

Bounds = tuple[float, float, float, float, float, float]  # x0, x1, y0, y1, z0, z1 (in)

# --- The members, typed from B2's plan at 2x6 --------------------------------------

#: Layout stud centres along X on the front and back walls: 0.75, every 16,
#: an end stud flush at 143.25 (144 is a multiple of 16, so the front's
#: layout from X 144 lands on the same X).
LONG = [0.75, 16, 32, 48, 64, 80, 96, 112, 128, 143.25]
#: Left side wall, from Y 5.5 upward: 5.5 + (0.75, 16, ..., 96, 108.25); the
#: side walls are 109 long between the 5.5 in front and back walls.
LEFT = [6.25, 21.5, 37.5, 53.5, 69.5, 85.5, 101.5, 113.75]
#: Right side wall, from Y 114.5 downward: 114.5 - (0.75, 16, ..., 108.25).
RIGHT = [113.75, 98.5, 82.5, 66.5, 50.5, 34.5, 18.5, 6.25]

D = 5.5  # the wall's depth: a 2x6 on the flat
STUD_Z = (1.5, 94.125)  # bottom plate to the double top plate
TOP_Z = [(94.125, 95.625), (95.625, 97.125)]
#: Three 2x6 plies on edge across 5.5: 1.5 + 0.5 + 1.5 + 0.5 + 1.5.
PLIES = [(0.0, 1.5), (2.0, 3.5), (4.0, 5.5)]
HEADER_Z = (82.5, 88.0)  # head 82.5, a 2x6 on edge (5.5) above it


def _front() -> list[Bounds]:
    """Y 0..5.5. The door (a 3068: rough opening 38 x 82.5 centred on X 72):
    kings X 50..51.5 and 92.5..94, jacks 51.5..53 and 91..92.5 to the head,
    three plies X 51.5..92.5, top cripples at the replaced X 64 and 80, the
    bottom plate cut out of X 53..91."""
    studs = [x for x in LONG if x not in (64, 80)]
    out: list[Bounds] = [(x - 0.75, x + 0.75, 0, D, *STUD_Z) for x in studs]
    out += [(50, 51.5, 0, D, *STUD_Z), (92.5, 94, 0, D, *STUD_Z)]
    out += [(51.5, 53, 0, D, 1.5, 82.5), (91, 92.5, 0, D, 1.5, 82.5)]
    out += [(51.5, 92.5, y0, y1, *HEADER_Z) for y0, y1 in PLIES]
    out += [(x - 0.75, x + 0.75, 0, D, 88, 94.125) for x in (64, 80)]
    out += [(0, 144, 0, D, *z) for z in TOP_Z]
    return [*out, (0, 53, 0, D, 0, 1.5), (91, 144, 0, D, 0, 1.5)]


def _left() -> list[Bounds]:
    out: list[Bounds] = [(0, D, y - 0.75, y + 0.75, *STUD_Z) for y in LEFT]
    out += [(0, D, 5.5, 114.5, *z) for z in TOP_Z]
    return [*out, (0, D, 5.5, 114.5, 0, 1.5)]


def _back() -> list[Bounds]:
    out: list[Bounds] = [(x - 0.75, x + 0.75, 114.5, 120, *STUD_Z) for x in LONG]
    out += [(0, 144, 114.5, 120, *z) for z in TOP_Z]
    return [*out, (0, 144, 114.5, 120, 0, 1.5)]


def _right() -> list[Bounds]:
    """X 138.5..144. The window (a 2030: rough opening 24.5 x 36.5 centred on
    Y 60, Y 47.75..72.25, sill 46, head 82.5): kings Y 44.75..46.25 and
    73.75..75.25, jacks 46.25..47.75 and 72.25..73.75, three plies
    Y 46.25..73.75 at X 142.5..144, 140.5..142 and 138.5..140 (in from the
    exterior face X 144), a flat sill Z 44.5..46, and top and bottom
    cripples at the replaced Y 50.5 and 66.5."""
    x0, x1 = 144 - D, 144.0
    studs = [y for y in RIGHT if y not in (50.5, 66.5)]
    out: list[Bounds] = [(x0, x1, y - 0.75, y + 0.75, *STUD_Z) for y in studs]
    out += [(x0, x1, 44.75, 46.25, *STUD_Z), (x0, x1, 73.75, 75.25, *STUD_Z)]
    out += [(x0, x1, 46.25, 47.75, 1.5, 82.5), (x0, x1, 72.25, 73.75, 1.5, 82.5)]
    out += [(144 - v1, 144 - v0, 46.25, 73.75, *HEADER_Z) for v0, v1 in PLIES]
    out += [(x0, x1, 47.75, 72.25, 44.5, 46)]
    for y in (50.5, 66.5):
        out += [
            (x0, x1, y - 0.75, y + 0.75, 88, 94.125),
            (x0, x1, y - 0.75, y + 0.75, 1.5, 44.5),
        ]
    out += [(x0, x1, 5.5, 114.5, *z) for z in TOP_Z]
    return [*out, (x0, x1, 5.5, 114.5, 0, 1.5)]


def spec_boxes() -> list[Bounds]:
    return _front() + _left() + _back() + _right()


#: The rough openings (in): nothing may enter them.
OPENINGS: list[Bounds] = [(53, 91, 0, D, 0, 82.5), (138.5, 144, 47.75, 72.25, 46, 82.5)]

#: The wall cut list (kings are studs): member, profile, material, qty,
#: length (in), stock (ft). Every member is a 2x6.
TABLE: list[tuple[str, str, str, int, float, int]] = [
    ("Stud", "2x6", SPF, 36, 92.625, 8),
    ("Jack", "2x6", SPF, 4, 81.0, 8),
    ("Header", "2x6", SPF, 3, 27.5, 8),
    ("Header", "2x6", SPF, 3, 41.0, 8),
    ("Cripple", "2x6", SPF, 4, 6.125, 8),
    ("Cripple", "2x6", SPF, 2, 43.0, 8),
    ("Top plate", "2x6", SPF, 4, 109.0, 10),
    ("Top plate", "2x6", SPF, 4, 144.0, 12),
    ("Bottom plate", "2x6", PT, 2, 53.0, 8),
    ("Bottom plate", "2x6", PT, 2, 109.0, 10),
    ("Bottom plate", "2x6", PT, 1, 144.0, 12),
    ("Sill", "2x6", SPF, 1, 24.5, 8),
]
#: The cut list's lengths summed (5 479 in) x 8.25 in^2.
VOLUME_IN3 = 45201.75


def _request() -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / GOLDEN / "model.json").read_text()
    )


def _members() -> list[CutListMember]:
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / GOLDEN / "members.json").read_text()
    )
    return [CutListMember.model_validate(item) for item in raw]


def test_the_spec_is_the_cut_list() -> None:
    """The typed boxes and the typed list agree: 66 members, 5 479 in."""
    boxes = spec_boxes()
    assert len(boxes) == sum(row[3] for row in TABLE) == 66
    assert sum(row[3] * row[4] for row in TABLE) == 5479
    volume = sum((b[1] - b[0]) * (b[3] - b[2]) * (b[5] - b[4]) for b in boxes)
    assert volume == VOLUME_IN3 == 5479 * 8.25


def test_the_cut_list_lists_three_plies_per_opening_and_prices_them() -> None:
    request = _request()
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    extents = BodyExtentsResult.model_validate_json(response.content)
    # A yard's 2x6 SPF 8 ft at $6.48 each.
    book = PriceBookResponse(
        currency="USD",
        entries=[
            PriceBookEntry(
                material=SPF,
                profile="us_2x6",
                unit="each",
                stock_length_ft=8,
                price_cents=648,
            )
        ],
    )
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B2 2x6 walls",
        length_unit="in",
        pieces=part_pieces(extents, _members(), request.materials),
        price_book=book,
    )
    rows = [
        (
            line.member,
            line.profile,
            line.material,
            line.quantity,
            round(line.length_mm / IN, 6),
            line.stock_length_ft,
        )
        for line in cut_list.lines
    ]
    # The lines' order is the cut list's own concern (CUT-LIST-PANEL).
    assert sorted(rows) == sorted(TABLE)
    assert cut_list.unclassified == 0
    headers = [line for line in cut_list.lines if line.member == "Header"]
    # Each ply is one 8 ft piece: 3 x $6.48 per opening.
    assert sorted((round(h.length_mm / IN, 6), h.quantity) for h in headers) == [
        (27.5, 3),
        (41, 3),
    ]
    assert [h.extended_price_cents for h in headers] == [3 * 648, 3 * 648]


def _box_in(solid: Solid) -> Bounds:
    box = solid.bounding_box()
    values = (box.min.X, box.max.X, box.min.Y, box.max.Y, box.min.Z, box.max.Z)
    return tuple(round(v / IN, 6) + 0.0 for v in values)  # type: ignore[return-value]


def test_the_step_is_the_spec_and_nothing_interferes(tmp_path: Path) -> None:
    request = ExportTreeRequest.model_validate(
        {**_request().model_dump(mode="json"), "format": "step"}
    )
    response = client.post("/api/v1/export/tree", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    path = tmp_path / f"{GOLDEN}.step"
    path.write_bytes(response.content)
    solids: list[Solid] = list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    got = Counter(_box_in(s) for s in solids)
    want = Counter(tuple(float(v) + 0.0 for v in b) for b in spec_boxes())
    assert got == want
    volume_in3 = sum(float(measure_shape(s).volume) for s in solids) / IN**3
    assert volume_in3 == pytest.approx(VOLUME_IN3, abs=1e-4)
    for box in got:
        for hole in OPENINGS:
            inside = all(
                min(box[k + 1], hole[k + 1]) - max(box[k], hole[k]) > 1e-9
                for k in (0, 2, 4)
            )
            assert not inside, (box, hole)
    bounds = [s.bounding_box() for s in solids]
    for i in range(len(solids)):
        for j in range(i + 1, len(solids)):
            a, b = bounds[i], bounds[j]
            if all(
                min(getattr(a.max, k), getattr(b.max, k))
                - max(getattr(a.min, k), getattr(b.min, k))
                > 1e-6
                for k in ("X", "Y", "Z")
            ):
                probe = probe_overlap(solids[i], solids[j])
                assert not probe.unresolved and probe.volume_mm3 == 0.0, (i, j)
