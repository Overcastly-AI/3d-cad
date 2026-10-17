"""PRICE-BOOK acceptance on MEASURED buildings: B1 and B2 priced from the
sample book in BACKLOG item 6.

Every piece is measured by geometry from the goldens (B1:
``b1-deck-framing-16ft``; B2: ``b2-walls-door-window`` and ``b2-roof-6-12``,
the shed's walls with their door and window, and its 6/12 roof) and priced by
:mod:`loft_wire.cut_list` as the gateway prices it. The totals are typed from
the backlog's hand-worked numbers, never recorded from the code: B1 $943.94
($839.54 with 1 line unpriced without the 6x6 price), B2 $396.07, and an
assembly placing B1 once and B2 twice $1,736.08.
"""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.main import app
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMember,
    CutListPiece,
    CutListResponse,
    cut_list_csv,
    cut_list_response,
    part_pieces,
)
from loft_wire.features import EvaluateTreeRequest
from loft_wire.price_book import PriceBookResponse, PriceBookUpdate

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
PT, SPF = "southern_pine_pt", "spf_lumber"


def _each(material: str, profile: str, feet: int, cents: int) -> dict[str, Any]:
    return {
        "material": material,
        "profile": profile,
        "unit": "each",
        "stock_length_ft": feet,
        "price_cents": cents,
    }


def _per(material: str, profile: str, unit: str, cents: int) -> dict[str, Any]:
    return {
        "material": material,
        "profile": profile,
        "unit": unit,
        "price_cents": cents,
    }


#: BACKLOG item 6's sample book.
SAMPLE_BOOK: list[dict[str, Any]] = [
    _each(PT, "us_2x10", 16, 2847),
    _each(PT, "us_2x10", 12, 1998),
    _per(PT, "us_6x6", "board_foot", 145),
    _per(PT, "us_5_4x6", "linear_foot", 112),
    _each(PT, "us_2x4", 8, 527),
    _each(PT, "us_2x4", 10, 697),
    _each(PT, "us_2x4", 12, 837),
    _each(SPF, "us_2x4", 8, 398),
    _each(SPF, "us_2x4", 10, 548),
    _each(SPF, "us_2x4", 12, 658),
    _each(SPF, "us_2x6", 8, 648),
    _per(SPF, "us_2x8", "linear_foot", 94),
]


def _book(entries: list[dict[str, Any]]) -> PriceBookResponse:
    update = PriceBookUpdate.model_validate({"entries": entries})
    return PriceBookResponse(currency=update.currency, entries=update.entries)


def _pieces(name: str, count: int = 1) -> list[CutListPiece]:
    """Golden *name*'s bodies, measured by geometry, as cut-list pieces."""
    request = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / name / "members.json").read_text()
    )
    members = [CutListMember.model_validate(item) for item in raw]
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    extents = BodyExtentsResult.model_validate_json(response.content)
    return part_pieces(extents, members, request.materials, count=count)


def _b1(count: int = 1) -> list[CutListPiece]:
    return _pieces("b1-deck-framing-16ft", count)


def _b2(count: int = 1) -> list[CutListPiece]:
    return [
        *_pieces("b2-walls-door-window", count),
        *_pieces("b2-roof-6-12", count),
    ]


def _priced(
    pieces: list[CutListPiece],
    entries: list[dict[str, Any]] = SAMPLE_BOOK,
    kind: Any = "part",
) -> CutListResponse:
    return cut_list_response(
        document_id=uuid.uuid4(),
        document_kind=kind,
        name="Priced",
        length_unit="in",
        pieces=pieces,
        price_book=_book(entries),
    )


def _by_member(cut_list: CutListResponse) -> dict[str, int | None]:
    totals: dict[str, int | None] = {}
    for line in cut_list.lines:
        assert line.member is not None
        if line.extended_price_cents is None:
            totals[line.member] = None
        else:
            totals[line.member] = (totals.get(line.member) or 0) + (
                line.extended_price_cents
            )
    return totals


def test_b1_totals_943_94() -> None:
    cut_list = _priced(_b1())
    # beam 2 x 28.47 (and the ledger and rim at 28.47), joists 13 x 19.98,
    # posts 3 x 34.80 (6x6 x 8 ft = 24 BF x 1.45), decking 26 x 17.92.
    assert _by_member(cut_list) == {
        "Ledger": 2847,
        "Rim": 2847,
        "Beam": 5694,
        "Joist": 25974,
        "Post": 10440,
        "Deck": 46592,
    }
    assert (cut_list.total_price_cents, cut_list.unpriced_lines) == (94394, 0)
    assert cut_list_csv(cut_list).endswith(",Total,,,,,,,,,,,,,943.94\r\n")


def test_b1_without_the_6x6_price_is_839_54_with_one_line_unpriced() -> None:
    book = [entry for entry in SAMPLE_BOOK if entry["profile"] != "us_6x6"]
    cut_list = _priced(_b1(), book)
    assert _by_member(cut_list)["Post"] is None
    assert (cut_list.total_price_cents, cut_list.unpriced_lines) == (83954, 1)
    assert cut_list_csv(cut_list).endswith(
        ',"Total of priced lines, 1 unpriced",,,,,,,,,,,,,839.54\r\n'
    )


def test_b2_totals_396_07() -> None:
    cut_list = _priced(_b2())
    members = _by_member(cut_list)
    # studs 36 x 3.98, rafters 14 x 6.48, ridge 12 ft x 0.94.
    assert (members["Stud"], members["Rafter"], members["Ridge"]) == (
        14328,
        9072,
        1128,
    )
    assert (cut_list.total_price_cents, cut_list.unpriced_lines) == (39607, 0)
    assert cut_list_csv(cut_list).endswith(",Total,,,,,,,,,,,,,396.07\r\n")


@pytest.mark.parametrize("order", ["b1-first", "b2-first"])
def test_an_assembly_of_b1_and_two_b2_totals_1736_08(order: str) -> None:
    """As the gateway builds it: each part's pieces times its quantity, one
    grouped list across the assembly."""
    pieces = [*_b1(), *_b2(count=2)]
    if order == "b2-first":
        pieces = [*_b2(count=2), *_b1()]
    cut_list = _priced(pieces, kind="assembly")
    assert (cut_list.total_price_cents, cut_list.unpriced_lines) == (173608, 0)
    assert cut_list_csv(cut_list).endswith(",Total,,,,,,,,,,,,,1736.08\r\n")
