"""The cut list as CSV (CUT-LIST): RFC 4180 rows in the document unit,
money as plain numbers, every text cell escaped against spreadsheet
formulas. Split from :mod:`loft_wire.cut_list` (the file-size limit); the
lines and their order are that module's."""

import csv
import io
from collections.abc import Mapping
from typing import Final

from loft_wire.cut_list import (
    MM_PER_FOOT,
    SYSTEM_LABELS,
    CutListLine,
    CutListResponse,
    splice_label,
)
from loft_wire.foundation import volume_yd3
from loft_wire.lumber import MM_PER_INCH
from loft_wire.materials import MATERIALS_BY_KEY
from loft_wire.price_book import Currency, PriceUnit
from loft_wire.units import LengthUnit

# --- CSV ----------------------------------------------------------------------------

#: Millimetres per display unit.
_MM_PER_UNIT: Final[Mapping[LengthUnit, float]] = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": MM_PER_INCH,
    "ft": MM_PER_FOOT,
}

#: Decimals an area is written with, per unit (1 mm^2 or finer).
_AREA_DECIMALS: Final[Mapping[LengthUnit, int]] = {
    "mm": 0,
    "cm": 2,
    "m": 6,
    "in": 4,
    "ft": 6,
}

#: Decimals a length is written with, per unit (about 1 um in each).
_DECIMALS: Final[Mapping[LengthUnit, int]] = {
    "mm": 3,
    "cm": 4,
    "m": 6,
    "in": 4,
    "ft": 5,
}


def format_length(value_mm: float, unit: LengthUnit) -> str:
    """*value_mm* in *unit*, trailing zeros trimmed (``141``, ``10.5``)."""
    text = f"{value_mm / _MM_PER_UNIT[unit]:.{_DECIMALS[unit]}f}"
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return "0" if text in ("-0", "") else text


def format_area(value_mm2: float, unit: LengthUnit) -> str:
    """*value_mm2* in square *unit*, trailing zeros trimmed (``45893``)."""
    text = f"{value_mm2 / _MM_PER_UNIT[unit] ** 2:.{_AREA_DECIMALS[unit]}f}"
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return "0" if text in ("-0", "") else text


#: The CSV's columns (lengths in the document unit, money in the currency).
def csv_header(unit: LengthUnit, currency: Currency = "USD") -> list[str]:
    return [
        "Item",
        "System",
        "Member",
        "Profile",
        f"Section ({unit})",
        "Material",
        "Qty",
        f"Length ({unit})",
        f"Total length ({unit})",
        f"Area (sq {unit})",
        "Stock",
        f"Waste each ({unit})",
        "Stock qty",
        f"Unit price ({currency})",
        "Price unit",
        f"Extended ({currency})",
    ]


#: How the CSV names each price unit.
PRICE_UNIT_LABELS: Final[Mapping[PriceUnit, str]] = {
    "each": "Each",
    "linear_foot": "Per ft",
    "board_foot": "Per BF",
    "cubic_yard": "Per yd3",
}


def format_cents(cents: int) -> str:
    """*cents* as a plain number of the major unit (``1736.08``), with no
    symbol or separator, so a spreadsheet reads it as a number."""
    sign = "-" if cents < 0 else ""
    whole, part = divmod(abs(cents), 100)
    return f"{sign}{whole}.{part:02d}"


def total_label(unpriced: int) -> str:
    """The Total row's label: ``Total``, or ``Total of priced lines, N
    unpriced`` when the total leaves lines out."""
    return "Total" if unpriced == 0 else f"Total of priced lines, {unpriced} unpriced"


#: A cell starting with one of these is a FORMULA to Excel, LibreOffice and
#: Google Sheets (``=HYPERLINK(...)``, ``+cmd|...``, ``@SUM``, a leading tab or
#: CR). Member text comes from a plugin's metadata, which a shared ``.loft``
#: carries for a plugin this server may not have, so it is untrusted.
FORMULA_TRIGGERS: Final = ("=", "+", "-", "@", "\t", "\r")


def csv_text(value: str) -> str:
    """*value* safe as a CSV text cell: a formula trigger at its start, or
    after leading whitespace (a spreadsheet may skip it, so ``" =1+1"`` can
    still be a formula), is escaped with a single quote (OWASP, CSV
    injection), so the cell reads as text."""
    if value.startswith(FORMULA_TRIGGERS) or value.lstrip().startswith(
        FORMULA_TRIGGERS
    ):
        return f"'{value}"
    return value


def format_yd3(value: float) -> str:
    """Cubic yards to 2 places, as ready-mix is listed (``6.62``)."""
    return f"{value:.2f}"


def _stock(line: CutListLine) -> str:
    if line.item == "concrete":
        net = volume_yd3(line.volume_mm3 or 0.0)
        return f"{format_yd3(net)} yd3 net + {line.waste_percent or 0}% waste"
    if line.item == "anchor_bolt":
        return "Each"
    if line.unit is not None:
        return "Unit"
    if line.sheet is not None:
        return f"{line.sheet} sheet"
    if line.stock_pieces_ft:
        return splice_label(line.stock_pieces_ft)
    if line.stock_note is not None:
        return csv_text(line.stock_note)
    return "" if line.stock_length_ft is None else f"{line.stock_length_ft} ft"


def _money(cents: int | None) -> str:
    return "" if cents is None else format_cents(cents)


def cut_list_csv(cut_list: CutListResponse) -> str:
    """The cut list as CSV (RFC 4180, CRLF), one row per line, then a Total
    row of the priced lines. Every text cell goes through :func:`csv_text`;
    numbers are written by this module, money as plain numbers, and an
    unpriced line's price cells are blank (never 0)."""
    unit = cut_list.length_unit
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    header = csv_header(unit, cut_list.currency)
    writer.writerow(header)
    for item, line in enumerate(cut_list.lines, start=1):
        sheet = line.area_mm2 is not None
        # A pour has no length to cut, a bolt no length at all.
        no_length = sheet or line.item in ("concrete", "anchor_bolt")
        stock_qty = (
            format_yd3(line.order_yd3)
            if line.order_yd3 is not None
            else ("" if line.stock_quantity is None else line.stock_quantity)
        )
        material = "" if line.material is None else MATERIALS_BY_KEY[line.material].name
        writer.writerow(
            [
                item,
                SYSTEM_LABELS[line.system],
                csv_text(line.member or ""),
                csv_text(line.profile or "Unclassified"),
                ""
                if line.item is not None
                else " x ".join(format_length(v, unit) for v in line.section_mm),
                csv_text(material),
                line.quantity,
                "" if no_length else format_length(line.length_mm, unit),
                "" if no_length else format_length(line.total_length_mm, unit),
                "" if line.area_mm2 is None else format_area(line.area_mm2, unit),
                _stock(line),
                "" if line.waste_mm is None else format_length(line.waste_mm, unit),
                stock_qty,
                _money(line.unit_price_cents),
                "" if line.price_unit is None else PRICE_UNIT_LABELS[line.price_unit],
                _money(line.extended_price_cents),
            ]
        )
    blank: list[object] = [""] * len(header)
    member, profile, qty = (header.index(h) for h in ("Member", "Profile", "Qty"))
    for missing in cut_list.missing:
        row = list(blank)
        row[member], row[profile], row[qty] = (
            "Deleted part",
            "Not listed",
            missing.quantity,
        )
        writer.writerow(row)
    total = list(blank)
    # In the first text column (System), so a sort by Member keeps it apart.
    total[1] = total_label(cut_list.unpriced_lines)
    total[-1] = _money(cut_list.total_price_cents)
    writer.writerow(total)
    return out.getvalue()


def cut_list_filename(name: str) -> str:
    """``<name> cut list.csv``, with path and quote characters dropped."""
    safe = "".join(c for c in name if c not in '\\/:*?"<>|\r\n').strip() or "cut-list"
    return f"{safe} cut list.csv"
