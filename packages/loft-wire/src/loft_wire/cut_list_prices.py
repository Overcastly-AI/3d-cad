"""Prices on a cut list (PRICE-BOOK, RESEARCH §27).

Split from :mod:`loft_wire.cut_list` (FILE-SIZE-RATCHET), which re-exports
every name here. Each line is priced on the stock pieces bought
(:func:`price_lines`), in integer cents; a line the book does not price
stays null. :mod:`loft_wire.cut_list` imports this module at its end, so the
names it reads from there exist by then.
"""

import math
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Final

from loft_wire.casework import CASEWORK_ITEMS_BY_KEY
from loft_wire.cut_list import MM_PER_FOOT, CutListLine, lumber_for
from loft_wire.foundation import foundation_item_for
from loft_wire.lumber import (
    COMMON_MAX_STOCK_FT,
    COMMON_STOCK_LENGTHS_FT,
    LumberProfile,
    stock_lengths_ft,
)
from loft_wire.materials import MaterialKey
from loft_wire.price_book import (
    PriceBookEntry,
    PriceBookResponse,
    PriceKey,
    PriceUnit,
)
from loft_wire.sheet_goods import sheet_good_for
from loft_wire.stock import (
    _covers,  # pyright: ignore[reportPrivateUsage]
    _splice_tiers,  # pyright: ignore[reportPrivateUsage]
)


def nominal_size_in(profile: LumberProfile) -> tuple[Fraction, Fraction]:
    """A profile's NOMINAL thickness and width (in), exactly, from its name as
    sold: ``2x4`` is (2, 4), ``5/4x6`` is (5/4, 6). Board feet are counted on
    the nominal size, as yards sell them."""
    thickness, width = profile.name.split("x")
    return Fraction(thickness), Fraction(width)


def _round_half_up(value: Fraction) -> int:
    """*value* (cents, non-negative) to a whole cent, half up, as an invoice."""
    return math.floor(value + Fraction(1, 2))


def stock_piece_price(
    entry: PriceBookEntry, profile: LumberProfile, stock_length_ft: int
) -> int:
    """The price (cents) of ONE stock piece of *stock_length_ft* under *entry*,
    rounded once per piece: per foot x feet, or per board foot x nominal
    thickness x width x feet / 12."""
    if entry.unit == "each":
        return entry.price_cents
    if entry.unit == "linear_foot":
        return entry.price_cents * stock_length_ft
    thickness, width = nominal_size_in(profile)
    board_feet = thickness * width * stock_length_ft / 12
    return _round_half_up(board_feet * entry.price_cents)


#: Which unit wins when the book prices a line more than one way (lumber).
PRICE_PRECEDENCE: Final[tuple[PriceUnit, ...]] = ("each", "linear_foot", "board_foot")


def _price_stock(
    entries: Mapping[PriceKey, PriceBookEntry],
    material: MaterialKey,
    lumber: LumberProfile,
    options: Sequence[tuple[int, ...]],
) -> tuple[int, PriceUnit, tuple[int, ...]] | None:
    """The price (cents) of one member's stock, the unit that priced it and
    the stock it prices, from the equally good *options* (one stock length,
    or the tied splices, best first). Each prices a splice whose every piece
    has an 'each' entry, the cheapest such (ties: the first); else a per-foot
    entry prices the feet bought, else a per-board-foot entry, both on the
    first option. One unit per line; each piece rounded once."""

    def entry(unit: PriceUnit, feet: int | None) -> PriceBookEntry | None:
        return entries.get((material, lumber.key, unit, feet, None))

    best: tuple[int, int] | None = None
    for index, stock in enumerate(options):
        found = [entry("each", feet) for feet in stock]
        if all(e is not None for e in found):
            cents = sum(e.price_cents for e in found if e is not None)
            if best is None or (cents, index) < best:
                best = (cents, index)
    if best is not None:
        return best[0], "each", options[best[1]]
    for unit in PRICE_PRECEDENCE[1:]:
        found_entry = entry(unit, None)
        if found_entry is not None:
            stock = options[0]
            cents = sum(stock_piece_price(found_entry, lumber, ft) for ft in stock)
            return cents, unit, stock
    return None


def _stock_tiers(
    line: CutListLine, lengths: Sequence[int]
) -> tuple[tuple[tuple[int, ...], ...], ...]:
    """The stock a yard may sell one member of *line* as, in tiers of equally
    good options, the line's own choice first. A length not every yard
    stocks (18, 22 or 24 ft) falls to the next longer, up to the first that
    every yard does (:data:`~loft_wire.lumber.COMMON_STOCK_LENGTHS_FT`): a
    yard with no 18 ft quotes 20 ft, what Loft bought before it listed
    18 ft. A common length stands alone, so a 12 ft line the book does not
    price stays blank (its blank asks for the price) rather than buy 16 ft.
    Then, for a member that may splice and is longer than the
    :data:`~loft_wire.lumber.COMMON_MAX_STOCK_FT` every yard stocks, every
    splice tier (:func:`stock_splice_tiers`), so a 24 ft plate is 16 + 8 at
    a yard with no 24 ft. A one-piece member is never spliced."""
    tiers: list[tuple[tuple[int, ...], ...]] = []
    for feet in lengths:
        if _covers(line.length_mm, feet):
            tiers.append(((feet,),))
            if feet in COMMON_STOCK_LENGTHS_FT:
                break
    if not line.one_piece and not _covers(line.length_mm, COMMON_MAX_STOCK_FT):
        tiers.extend(_splice_tiers(line.length_mm, tuple(lengths)))
    return tuple(tiers)


def price_lines(
    lines: Sequence[CutListLine], book: PriceBookResponse
) -> list[CutListLine]:
    """*lines* priced from *book*, on the stock pieces bought: each line's
    unit price is an 'each' entry for its stock length (for a spliced line,
    for every piece of a splice, :func:`_price_stock`), from the first tier
    of :func:`_stock_tiers` (its own stock, past 18, 22 or 24 ft a longer
    single length, then for a member that may splice, the fewest pieces,
    then least waste) the book
    prices, its offcut recomputed, else a per-foot entry
    on the feet bought, else a per-board-foot entry (for its material and
    profile), and its extended price is that times its stock quantity (one
    per piece, a splice set counting once), so the offcut is paid for. A
    sheet line is priced by the 'each' entry for its product and sheet,
    times its sheets, and a unit line by the 'each' entry for its unit key
    and material, times its units. A foundation line (SLAB) is priced by its
    item's entry: ready-mix per cubic yard times the yards ordered, bagged
    concrete Each per bag times its bags, a rebar line Each per 20 ft stick
    times its sticks, anchor bolts and post bases Each. A line
    with no stock or no entry stays unpriced (null)."""
    entries = {entry.key: entry for entry in book.entries}
    priced: list[CutListLine] = []
    for line in lines:
        lumber = lumber_for(line.profile)
        good = sheet_good_for(line.profile)
        stock = line.stock_pieces_ft
        quantity = line.stock_quantity
        unit_price: int | None = None
        unit: PriceUnit | None = None
        update: dict[str, object] = {}
        if line.roofing is not None:
            from loft_wire.cut_list_roofing import roofing_price

            found_roofing = roofing_price(line, entries)
            if found_roofing is not None:
                unit_price, unit = found_roofing
        elif line.nested:
            # Nested trim: its sticks, all of one stock length (ROOFING).
            if lumber is not None and line.material is not None and stock:
                found_nested = _price_stock(
                    entries, line.material, lumber, (tuple(stock),)
                )
                if found_nested is not None:
                    unit_price, unit = found_nested[0], found_nested[1]
        elif line.siding is not None:
            from loft_wire.cut_list_siding import siding_price

            found_siding = siding_price(line, entries)
            if found_siding is not None:
                unit_price, unit = found_siding
        elif line.casework is not None:
            kind = CASEWORK_ITEMS_BY_KEY[line.casework]
            entry = None
            if line.material is not None:
                entry = entries.get((line.material, kind.key, kind.unit, None, None))
            if entry is not None:
                unit_price, unit = entry.price_cents, entry.unit
        elif (
            item := foundation_item_for(line.profile) if line.item is not None else None
        ) is not None:
            if line.material is not None:
                key = (line.material, item.key, item.price_unit)
                entry = entries.get((*key, item.stock_length_ft, None))
                if entry is not None:
                    unit_price, unit = entry.price_cents, entry.unit
        elif line.unit is not None:
            if line.unit_key is not None and line.material is not None:
                entry = entries.get((line.material, line.unit_key, "each", None, None))
                if entry is not None:
                    unit_price, unit = entry.price_cents, "each"
        elif (
            good is not None
            and line.sheet is not None
            and line.material is not None
            and quantity is not None
        ):
            entry = entries.get((line.material, good.key, "each", None, line.sheet))
            if entry is not None:
                unit_price, unit = entry.price_cents, "each"
        elif (
            lumber is not None
            and line.material is not None
            and stock
            and quantity is not None
        ):
            tiers = _stock_tiers(line, stock_lengths_ft(lumber))
            if not tiers or tuple(stock) not in tiers[0]:
                tiers = ((tuple(stock),),)
            found = None
            for options in tiers:
                found = _price_stock(entries, line.material, lumber, options)
                if found is not None:
                    break
            if found is not None:
                unit_price, unit, bought = found
                update["stock_pieces_ft"] = list(bought)
                # The stock shown is the stock bought: an 18 ft line priced
                # at 20 ft reads 20 ft, a 24 ft line spliced 16 + 8 none.
                update["stock_length_ft"] = bought[0] if len(bought) == 1 else None
                update["waste_mm"] = max(
                    0.0, round(sum(bought) * MM_PER_FOOT - line.length_mm, 6)
                )
        priced.append(
            line.model_copy(
                update={
                    **update,
                    "unit_price_cents": unit_price,
                    "price_unit": unit,
                    "extended_price_cents": _extended(line, unit_price, quantity),
                }
            )
        )
    return priced


def _extended(
    line: CutListLine, unit_price: int | None, quantity: int | None
) -> int | None:
    """Unit price x stock quantity (a bagged pour's bags); for ready-mix, x
    the cubic yards ORDERED (a multiple of 1/4, so exact), rounded once,
    half up."""
    if unit_price is None:
        return None
    if line.item == "concrete" and line.bags is None:
        if line.order_yd3 is None:
            return None
        return _round_half_up(Fraction(line.order_yd3) * unit_price)
    return None if quantity is None else unit_price * quantity
