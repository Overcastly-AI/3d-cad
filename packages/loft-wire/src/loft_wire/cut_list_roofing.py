"""Roofing and nested trim in the cut list (ROOFING, RESEARCH §23).

Split from :mod:`loft_wire.cut_list` (FILE-SIZE-RATCHET).

**Roofing** (:mod:`loft_wire.roofing`) is listed, not drawn, from the roof
deck's panels: each panel's metadata ``roofing`` lists its MEASURED net
area as shingles and underlayment, and the edges one panel of each plane
carries as drip edge, starter and ridge cap. Under Roof, one line an item:

* shingles and underlayment order ``ceil(net x (1 + waste) / coverage)``
  bundles (1/3 square) or rolls (10 squares) ONCE over the line's total
  area, as a roofer rounds the whole order; the line's quantity is that
  order (each bundle or roll is bought Each);
* drip edge is bought in 10 ft sticks, each run lapped 2 in at every joint
  on its own (a stick does not turn a corner);
* starter and ridge cap in whole feet of the line's total length.

**Nested trim** (TRIM-NESTING, ROOFING): casing, corner boards, fascia and
rake boards (:data:`~loft_wire.cut_list.NESTED_ROLES`) are cut from sticks
as a trim carpenter cuts them, not a stick a piece. Pieces of one system,
member, profile and material are one line, cut from the shortest stock
that covers its longest piece, first fit by decreasing length with a 1/8 in
kerf at each cut (:func:`nest_on_stock`). :mod:`loft_wire.cut_list` imports
this module, so this one reads its types through the module at call time.
"""

from collections.abc import Mapping, Sequence
from typing import Final

import loft_wire.cut_list as cl
from loft_wire.lumber import MM_PER_INCH, stock_lengths_ft
from loft_wire.price_book import PriceBookEntry, PriceKey, PriceUnit
from loft_wire.roofing import (
    EDGE_ITEMS,
    ROOFING_ITEMS_BY_KEY,
    area_order,
    drip_edge_sticks,
    whole_feet,
)

#: The saw kerf lost at each cut of a trim stick (in): a mitre saw's 1/8 in.
TRIM_KERF_IN: Final = 0.125

#: A piece fits a stick within this (in): the inputs' rounding.
_FIT_IN: Final = 1e-6

#: What each roofing item is listed as, as a member.
_MEMBERS: Final[Mapping[str, str]] = {
    "shingle_architectural": "Shingles",
    "underlayment_synthetic": "Underlayment",
    "drip_edge": "Drip edge",
    "shingle_starter": "Starter",
    "ridge_cap": "Ridge cap",
}


def roofing_pieces(
    piece: cl.CutListPiece, member: cl.CutListMember | None
) -> list[cl.CutListPiece]:
    """The roofing a deck panel lists (module docstring): its net area as
    shingles and underlayment, and the edges it carries."""
    if member is None or member.metadata.roofing is None:
        return []
    takeoff = member.metadata.roofing
    out: list[cl.CutListPiece] = []
    for key in (takeoff.shingles, takeoff.underlayment):
        item = ROOFING_ITEMS_BY_KEY[key]
        out.append(
            cl.CutListPiece(
                member=_MEMBERS[key],
                profile=item.name,
                lumber=False,
                material=item.material,
                classification="member",
                length_mm=0.0,
                section_mm=(0.0, 0.0),
                count=piece.count,
                system="roof",
                roofing=item.key,
                roof_area_mm2=piece.area_mm2 or 0.0,
                waste_percent=takeoff.waste_percent,
            )
        )
    for run in takeoff.edges:
        for key in EDGE_ITEMS[run.edge]:
            item = ROOFING_ITEMS_BY_KEY[key]
            out.append(
                cl.CutListPiece(
                    member=_MEMBERS[key],
                    profile=item.name,
                    lumber=False,
                    material=item.material,
                    classification="member",
                    length_mm=run.length_mm,
                    section_mm=(0.0, 0.0),
                    count=piece.count,
                    system="roof",
                    roofing=item.key,
                )
            )
    return out


def roofing_key(piece: cl.CutListPiece) -> tuple[object, ...]:
    """The group of a roofing or nested piece: an area item by its
    allowance too; a nested piece by system, member, profile and material."""
    if piece.roofing is not None:
        key: tuple[object, ...] = ("roofing", piece.roofing, piece.material)
        if piece.roof_area_mm2 is not None:
            key += (piece.waste_percent,)
        return key
    return ("nested", piece.system, piece.member, piece.profile, piece.material)


def nest_on_stock(lengths_in: Sequence[float], stock_in: float) -> int:
    """Sticks of *stock_in* the pieces *lengths_in* are cut from: longest
    first, each into the first stick it still fits (a kerf at each cut after
    a stick's first), else a new stick (first fit decreasing)."""
    used: list[float] = []
    for length in sorted(lengths_in, reverse=True):
        for i, taken in enumerate(used):
            if taken + TRIM_KERF_IN + length <= stock_in + _FIT_IN:
                used[i] = taken + TRIM_KERF_IN + length
                break
        else:
            used.append(length)
    return len(used)


def roofing_line(pieces: Sequence[cl.CutListPiece], quantity: int) -> cl.CutListLine:
    """One roofing item's line, or one nested trim line (module docstring)."""
    first = pieces[0]
    if first.roofing is None:
        return _nested_line(pieces, quantity)
    item = ROOFING_ITEMS_BY_KEY[first.roofing]
    runs = [(p.length_mm, p.count) for p in pieces]
    total = sum(length * count for length, count in runs)
    area: float | None = None
    waste: int | None = None
    if item.sale == "area":
        area = sum((p.roof_area_mm2 or 0.0) * p.count for p in pieces)
        waste = first.waste_percent or 0
        order = area_order(item, area / MM_PER_INCH**2, waste)
        quantity = max(order, 1)
    elif item.sale == "stick":
        order = sum(drip_edge_sticks(length / MM_PER_INCH) * n for length, n in runs)
    else:
        order = whole_feet(total / MM_PER_INCH)
    return cl.CutListLine(
        system="roof",
        member=first.member,
        profile=item.name,
        material=item.material,
        classification="member",
        quantity=quantity,
        length_mm=round(max(length for length, _ in runs), 6),
        total_length_mm=round(total, 6),
        section_mm=[0.0, 0.0],
        area_mm2=None if area is None else round(area, 6),
        stock_length_ft=item.stock_length_ft,
        waste_mm=None,
        stock_quantity=order,
        unit_price_cents=None,
        price_unit=None,
        extended_price_cents=None,
        waste_percent=waste,
        roofing=item.key,
    )


def _nested_line(pieces: Sequence[cl.CutListPiece], quantity: int) -> cl.CutListLine:
    """Trim pieces of one member, profile and material cut from sticks."""
    first = pieces[0]
    cuts = sorted(
        (round(p.length_mm, 6) for p in pieces for _ in range(p.count)), reverse=True
    )
    total = sum(cuts)
    lengths = stock_lengths_ft(cl.lumber_for(first.profile))
    stock = next(
        (
            ft
            for ft in lengths
            if cuts[0] <= ft * cl.MM_PER_FOOT + _FIT_IN * MM_PER_INCH
        ),
        None,
    )
    sticks = (
        None
        if stock is None or not first.lumber
        else nest_on_stock([c / MM_PER_INCH for c in cuts], stock * 12.0)
    )
    thickness, width = (round(v, 6) for v in first.section_mm)
    return cl.CutListLine(
        system=first.system,
        member=first.member,
        profile=first.profile,
        material=first.material,
        classification=first.classification,
        quantity=quantity,
        length_mm=cuts[0],
        total_length_mm=round(total, 6),
        section_mm=[thickness, width],
        stock_length_ft=None if sticks is None else stock,
        stock_pieces_ft=None if sticks is None or stock is None else [stock],
        waste_mm=(
            None
            if sticks is None or stock is None
            else max(0.0, round(sticks * stock * cl.MM_PER_FOOT - total, 6))
        ),
        stock_quantity=sticks,
        unit_price_cents=None,
        price_unit=None,
        extended_price_cents=None,
        nested=True,
        cuts_mm=cuts,
    )


def roofing_price(
    line: cl.CutListLine, entries: Mapping[PriceKey, PriceBookEntry]
) -> tuple[int, PriceUnit] | None:
    """The price (cents) of one bundle, roll, stick or foot of a roofing
    *line* and the unit that priced it, or ``None`` when the book has none."""
    if line.roofing is None:
        return None
    item = ROOFING_ITEMS_BY_KEY[line.roofing]
    entry = entries.get(
        (item.material, item.key, item.price_unit, item.stock_length_ft, None)
    )
    return None if entry is None else (entry.price_cents, entry.unit)
