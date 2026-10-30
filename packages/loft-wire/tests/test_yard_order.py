"""The cut list as a yard order (HOUSE-DRAWINGS, CUT-LIST-PDF): one line per
cut-list line, in its order, the quantity what is bought and the price the
line's extended price, so the materials sheet equals the panel to the cent."""

import csv
import io
import uuid
from typing import Any

from loft_wire.cut_list import CutListLine, CutListResponse
from loft_wire.yard_order import (
    format_money,
    yard_order,
    yard_order_csv,
    yard_order_filename,
)

IN = 25.4


def _line(**over: Any) -> CutListLine:
    base: dict[str, Any] = {
        "system": "walls",
        "member": "Stud",
        "profile": "2x6",
        "material": "spf_lumber",
        "classification": "member",
        "quantity": 48,
        "length_mm": 92.625 * IN,
        "total_length_mm": 48 * 92.625 * IN,
        "section_mm": [1.5 * IN, 5.5 * IN],
        "stock_length_ft": 8,
        "waste_mm": 3.375 * IN,
        "stock_quantity": 48,
        "unit_price_cents": 498,
        "price_unit": "each",
        "extended_price_cents": 48 * 498,
    }
    base.update(over)
    return CutListLine.model_validate(base)


def _cut_list(lines: list[CutListLine], unit: str = "in") -> CutListResponse:
    priced = [ln.extended_price_cents for ln in lines if ln.extended_price_cents]
    return CutListResponse.model_validate(
        {
            "document_id": str(uuid.uuid4()),
            "document_kind": "part",
            "name": "B7",
            "length_unit": unit,
            "lines": [ln.model_dump() for ln in lines],
            "total_quantity": sum(ln.quantity for ln in lines),
            "unclassified": 0,
            "currency": "USD",
            "total_price_cents": sum(priced) if priced else None,
            "unpriced_lines": sum(1 for ln in lines if ln.extended_price_cents is None),
        }
    )


LINES = [
    _line(),
    _line(
        member="Top plate",
        quantity=2,
        length_mm=288 * IN,
        stock_length_ft=None,
        stock_pieces_ft=[16, 8],
        stock_quantity=2,
        unit_price_cents=1495,
        extended_price_cents=2990,
    ),
    _line(
        system="sheathing",
        member="Sheathing",
        profile="7/16 OSB",
        material="osb",
        quantity=24,
        sheet="4x9",
        area_mm2=100.0,
        stock_length_ft=None,
        stock_quantity=20,
        unit_price_cents=1899,
        extended_price_cents=20 * 1899,
    ),
    _line(
        system="walls",
        member="Window",
        profile="3040",
        material="pvc",
        quantity=3,
        unit="window",
        stock_length_ft=None,
        waste_mm=None,
        stock_quantity=3,
        unit_price_cents=31900,
        extended_price_cents=95700,
    ),
    _line(
        member="Joist",
        profile="2x10",
        quantity=1,
        length_mm=300 * IN,
        stock_length_ft=None,
        waste_mm=None,
        stock_quantity=None,
        unit_price_cents=None,
        price_unit=None,
        extended_price_cents=None,
        stock_note="One piece, longer than 24 ft stock: a joist is not spliced",
    ),
]


def test_one_yard_line_per_cut_list_line_in_order() -> None:
    order = yard_order(_cut_list(LINES))
    assert [ln.item for ln in order.lines] == [
        "Stud",
        "Top plate",
        "Sheathing",
        "Window",
        "Joist",
    ]
    assert [ln.system for ln in order.lines] == [
        "Walls",
        "Walls",
        "Sheathing",
        "Walls",
        "Walls",
    ]


def test_what_is_bought() -> None:
    stud, plate, osb, window, joist = yard_order(_cut_list(LINES)).lines
    assert (stud.qty, stud.size, stud.length) == ("48", "2x6", "8 ft")
    assert stud.material == "Spruce-pine-fir (SPF) lumber"
    # A spliced plate is one set of 16 + 8 per member.
    assert (plate.qty, plate.length) == ("2", "16 ft + 8 ft")
    # Sheets bought, not panels cut.
    assert (osb.qty, osb.size, osb.length) == ("20", "7/16 OSB", "4x9")
    assert (window.qty, window.size, window.length) == ("3", "3040 window", "")
    # No stock it may be bought in: its measured length, in feet-inch.
    assert (joist.qty, joist.length, joist.price) == ("1", "25'-0\"", "")


def test_prices_are_the_lines_extended_prices_to_the_cent() -> None:
    order = yard_order(_cut_list(LINES))
    assert [ln.price_cents for ln in order.lines] == [
        ln.extended_price_cents for ln in LINES
    ]
    assert order.lines[0].price == "$239.04"
    assert order.total_cents == 23904 + 2990 + 37980 + 95700
    assert order.total == "$1,605.74"
    assert order.total_label == "Total of priced lines, 1 unpriced"


def test_money_reads_as_the_panel_writes_it() -> None:
    assert format_money(0) == "$0.00"
    assert format_money(5) == "$0.05"
    assert format_money(286887) == "$2,868.87"
    assert format_money(123456789) == "$1,234,567.89"


def test_csv_is_the_same_lines_with_a_total_row() -> None:
    order = yard_order(_cut_list(LINES))
    rows = list(csv.reader(io.StringIO(yard_order_csv(order))))
    assert rows[0] == [
        "System",
        "Item",
        "Qty",
        "Size",
        "Length",
        "Material",
        "Price (USD)",
    ]
    assert len(rows) == 1 + len(LINES) + 1
    assert rows[1] == [
        "Walls",
        "Stud",
        "48",
        "2x6",
        "8 ft",
        "Spruce-pine-fir (SPF) lumber",
        "239.04",
    ]
    assert [r[-1] for r in rows[1:-1]] == ["239.04", "29.90", "379.80", "957.00", ""]
    assert rows[-1][0] == "Total of priced lines, 1 unpriced"
    assert rows[-1][-1] == "1605.74"


def test_a_formula_in_a_member_name_is_text() -> None:
    order = yard_order(_cut_list([_line(member="=HYPERLINK(1)")]))
    rows = list(csv.reader(io.StringIO(yard_order_csv(order))))
    assert rows[1][1] == "'=HYPERLINK(1)"


def test_a_metric_document_lists_millimetres() -> None:
    joist = LINES[-1]
    order = yard_order(_cut_list([joist], unit="mm"))
    assert order.lines[0].length == "7620 mm"


def test_filename() -> None:
    assert yard_order_filename('B7 "house"') == "B7 house materials.csv"
