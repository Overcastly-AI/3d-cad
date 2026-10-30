"""The cut list as a yard order (HOUSE-DRAWINGS, CUT-LIST-PDF).

Chief Architect places its Materials List on a sheet; a builder hands the
yard a list of what to load: how many, what size, how long, of what, and what
it costs. One :class:`~loft_wire.drawing_house.YardOrderLine` per cut-list
line, in the cut list's order, so the sheet equals the cut-list panel line for
line and to the cent: the quantity is what is bought (stock pieces, sheets,
units, the ready-mix order), the price the line's extended price.

The drawing's materials table, its PDF and its CSV are all written from this
one function, so they cannot disagree.
"""

import csv
import io

from loft_wire.cut_list import EACH_ITEMS, SYSTEM_LABELS, CutListLine, CutListResponse
from loft_wire.cut_list_csv import (
    csv_text,
    format_cents,
    format_length,
    format_yd3,
    total_label,
)
from loft_wire.drawing_house import YARD_ORDER_COLUMNS, YardOrder, YardOrderLine
from loft_wire.feet_inches import feet_inches
from loft_wire.materials import MATERIALS_BY_KEY
from loft_wire.stock import splice_label
from loft_wire.units import LengthUnit

#: A cell with nothing to say (a unit has no length to cut).
DASH = ""

#: Each currency's symbol (the price book's only currency is USD).
_SYMBOLS: dict[str, str] = {"USD": "$"}


def format_money(cents: int, currency: str = "USD") -> str:
    """Integer cents as the panel writes them: ``$1,234.56`` (``formatMoney``)."""
    sign = "-" if cents < 0 else ""
    whole, part = divmod(abs(cents), 100)
    symbol = _SYMBOLS.get(currency, f"{currency} ")
    return f"{sign}{symbol}{whole:,}.{part:02d}"


def display_length(value_mm: float, unit: LengthUnit) -> str:
    """A measured length in the document's unit: feet-inch in an imperial
    document, else the unit's number and symbol (``2440 mm``)."""
    if unit in ("in", "ft"):
        return feet_inches(value_mm)
    return f"{format_length(value_mm, unit)} {unit}"


def _qty_size_length(line: CutListLine, unit: LengthUnit) -> tuple[str, str, str]:
    """What the yard loads for *line*: (Qty, Size, Length)."""
    profile = line.profile or ""
    if line.casework is not None:
        if line.casework == "edge_banding":
            return f"{line.stock_quantity or 0} ft", profile, DASH
        return str(line.quantity), profile, DASH
    if line.item == "concrete":
        if line.bags is not None:
            return f"{line.bags} bags", profile, DASH
        order = DASH if line.order_yd3 is None else f"{format_yd3(line.order_yd3)} yd3"
        return order, profile, DASH
    if line.item == "rebar":
        return (
            str(line.stock_quantity or 0),
            profile,
            f"{line.stock_length_ft or 20} ft",
        )
    if line.item in EACH_ITEMS:
        return str(line.quantity), line.member or profile, DASH
    if line.unit is not None:
        return str(line.quantity), f"{profile} {line.unit}".strip(), DASH
    if line.area_mm2 is not None:
        if line.sheet is None or line.stock_quantity is None:
            return str(line.quantity), profile, DASH
        return str(line.stock_quantity), profile, line.sheet
    if line.classification == "unclassified" or line.profile is None:
        size = " x ".join(display_length(v, unit) for v in line.section_mm)
        return str(line.quantity), size, display_length(line.length_mm, unit)
    pieces = line.stock_pieces_ft or []
    if len(pieces) > 1:
        return str(line.stock_quantity or line.quantity), profile, splice_label(pieces)
    if line.stock_length_ft is not None:
        qty = line.stock_quantity if line.stock_quantity is not None else line.quantity
        return str(qty), profile, f"{line.stock_length_ft} ft"
    # No stock it may be bought in (a joist past the longest stock): the
    # pieces at their measured length, unpriced.
    return str(line.quantity), profile, display_length(line.length_mm, unit)


def yard_order(cut_list: CutListResponse) -> YardOrder:
    """*cut_list* as a yard order: one line per cut-list line, in order."""
    lines: list[YardOrderLine] = []
    for line in cut_list.lines:
        qty, size, length = _qty_size_length(line, cut_list.length_unit)
        cents = line.extended_price_cents
        lines.append(
            YardOrderLine(
                system=SYSTEM_LABELS[line.system],
                item=line.member or line.profile or "Body",
                qty=qty,
                size=size,
                length=length,
                material=(
                    ""
                    if line.material is None
                    else MATERIALS_BY_KEY[line.material].name
                ),
                price="" if cents is None else format_money(cents, cut_list.currency),
                price_cents=cents,
            )
        )
    total = cut_list.total_price_cents
    return YardOrder(
        name=cut_list.name,
        currency=cut_list.currency,
        lines=lines,
        total="" if total is None else format_money(total, cut_list.currency),
        total_cents=total,
        total_label=total_label(cut_list.unpriced_lines),
    )


def yard_order_csv(order: YardOrder) -> str:
    """The yard order as CSV (RFC 4180, CRLF): its columns, a row per line
    and the Total row; money as plain numbers, text escaped against
    spreadsheet formulas (``csv_text``)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    header = [*YARD_ORDER_COLUMNS[:-1], f"Price ({order.currency})"]
    writer.writerow(["System", *header])
    for line in order.lines:
        writer.writerow(
            [
                line.system,
                csv_text(line.item),
                csv_text(line.qty),
                csv_text(line.size),
                csv_text(line.length),
                csv_text(line.material),
                "" if line.price_cents is None else format_cents(line.price_cents),
            ]
        )
    total = ["" for _ in range(len(header) + 1)]
    total[0] = order.total_label
    total[-1] = "" if order.total_cents is None else format_cents(order.total_cents)
    writer.writerow(total)
    return out.getvalue()


def yard_order_filename(name: str) -> str:
    """``<name> materials.csv``, with path and quote characters dropped."""
    safe = "".join(c for c in name if c not in '\\/:*?"<>|\r\n').strip() or "materials"
    return f"{safe} materials.csv"
