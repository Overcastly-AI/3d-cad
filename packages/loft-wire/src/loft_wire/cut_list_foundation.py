"""Foundation items in the cut list (SLAB, FOUNDATION-TAKEOFF, RESEARCH §23).

Split from :mod:`loft_wire.cut_list` (FILE-SIZE-RATCHET). A pour is listed by
its measured volume, one line per member, and each pour (each copy of a
placed part too) is ordered as its own delivery, rounded up to 1/4 yd³ after
its allowance; rebar, anchor bolts and a stem wall's vents and access door
are listed, not drawn, from the pour's or plate's metadata
(:mod:`loft_wire.foundation`). A line of bagged pours (DECK-FOOTINGS: a
deck's piers) buys whole 80 lb bags over its total volume, and a footing
under a post lists its post base. :mod:`loft_wire.cut_list` imports this module,
so this one reads its types through the module at call time.
"""

from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Final

import loft_wire.cut_list as cl
from loft_wire.foundation import (
    FOUNDATION_ITEMS_BY_KEY,
    concrete_bags,
    concrete_order_yd3,
    foundation_item_for,
    rebar_sticks,
)
from loft_wire.lumber import MM_PER_INCH

#: How a vent or access door line names its member, before its size.
_OPENING_MEMBER: Final[Mapping[str, str]] = {
    "foundation_vent": "Vent",
    "access_door": "Access door",
}


def listed_pieces(
    piece: cl.CutListPiece, member: cl.CutListMember | None
) -> list[cl.CutListPiece]:
    """The items *member*'s body carries but does not draw (SLAB): a pour's
    rebar runs, a plate's anchor bolts, counted from *piece*, the body as
    measured, a stem wall's vents and access door (FOUNDATION-TAKEOFF), and
    a footing's post base (DECK-FOOTINGS). Listed under Foundation, after the
    body."""
    if member is None:
        return []
    metadata = member.metadata
    out: list[cl.CutListPiece] = []
    for run in metadata.rebar or ():
        item = FOUNDATION_ITEMS_BY_KEY[run.item]
        out.append(
            cl.CutListPiece(
                member="Rebar",
                profile=item.name,
                lumber=False,
                material=item.material,
                classification="member",
                length_mm=run.length_mm,
                section_mm=(0.0, 0.0),
                count=piece.count,
                system="foundation",
                item="rebar",
                closed=run.closed,
            )
        )
    if metadata.concrete is not None and metadata.concrete.post_base is not None:
        item = FOUNDATION_ITEMS_BY_KEY[metadata.concrete.post_base]
        out.append(
            cl.CutListPiece(
                member="Post base",
                profile=item.name,
                lumber=False,
                material=item.material,
                classification="member",
                length_mm=0.0,
                section_mm=(0.0, 0.0),
                count=piece.count,
                system="foundation",
                item="post_base",
            )
        )
    if metadata.anchor_bolts is not None:
        item = FOUNDATION_ITEMS_BY_KEY[metadata.anchor_bolts.item]
        bolts = metadata.anchor_bolts.count(piece.length_mm / MM_PER_INCH)
        out.append(
            cl.CutListPiece(
                member="Anchor bolt",
                profile=item.name,
                lumber=False,
                material=item.material,
                classification="member",
                length_mm=0.0,
                section_mm=(0.0, 0.0),
                count=piece.count * bolts,
                system="foundation",
                item="anchor_bolt",
            )
        )
    for opening in metadata.foundation_openings or ():
        item = FOUNDATION_ITEMS_BY_KEY[opening.item]
        out.append(
            cl.CutListPiece(
                member=f"{_OPENING_MEMBER[item.kind]} {opening.size}",
                profile=item.name,
                lumber=False,
                material=item.material,
                classification="member",
                length_mm=0.0,
                section_mm=(0.0, 0.0),
                count=piece.count * opening.quantity,
                system="foundation",
                item=item.kind,
            )
        )
    return out


def _members_of(pieces: Sequence[cl.CutListPiece]) -> str | None:
    members: list[str] = []
    for piece in pieces:
        if piece.member is not None and piece.member not in members:
            members.append(piece.member)
    return ", ".join(members) or None


def concrete_line(pieces: Sequence[cl.CutListPiece], quantity: int) -> cl.CutListLine:
    """Pours of one member, product, material and allowance as one line:
    their measured volume, and the cubic yards they order, each pour (each
    copy of a placed part too) rounded up on its own, as each is its own
    delivery, unless they share one (a deck's piers: their sum rounded
    once); or, bagged, the whole bags their total takes (module docstring)."""
    first = pieces[0]
    volume = sum((p.volume_mm3 or 0.0) * p.count for p in pieces)
    waste = first.waste_percent or 0
    item = foundation_item_for(first.profile)
    bags = (
        concrete_bags(volume, waste)
        if item is not None and item.key == "concrete_bag_80"
        else None
    )
    order = (
        concrete_order_yd3(volume, waste)
        if all(p.one_delivery for p in pieces)
        else sum(
            (concrete_order_yd3(p.volume_mm3 or 0.0, waste) * p.count for p in pieces),
            Fraction(0),
        )
    )
    length = round(max(p.length_mm for p in pieces), 6)
    return cl.CutListLine(
        system=first.system,
        member=_members_of(pieces),
        profile=first.profile,
        material=first.material,
        classification=first.classification,
        quantity=quantity,
        length_mm=length,
        total_length_mm=round(sum(p.length_mm * p.count for p in pieces), 6),
        section_mm=[round(v, 6) for v in first.section_mm],
        stock_length_ft=None,
        waste_mm=None,
        stock_quantity=bags,
        unit_price_cents=None,
        price_unit=None,
        extended_price_cents=None,
        item="concrete",
        volume_mm3=round(volume, 6),
        order_yd3=None if bags is not None else float(order),
        waste_percent=waste,
        bags=bags,
    )


#: The stick a rebar line is bought in (ft).
_REBAR_STICK_FT: Final = FOUNDATION_ITEMS_BY_KEY["rebar_4"].stock_length_ft


def item_line(piece: cl.CutListPiece, quantity: int) -> cl.CutListLine:
    """Rebar runs of one length, bought in 20 ft sticks (each run lapped
    on its own), or anchor bolts, vents, access doors or post bases, Each."""
    length = round(piece.length_mm, 6)
    rebar = piece.item == "rebar"
    sticks = (
        rebar_sticks(length / MM_PER_INCH, piece.closed) * quantity
        if rebar
        else quantity
    )
    return cl.CutListLine(
        system=piece.system,
        member=piece.member,
        profile=piece.profile,
        material=piece.material,
        classification=piece.classification,
        quantity=quantity,
        length_mm=length,
        total_length_mm=round(length * quantity, 6),
        section_mm=[0.0, 0.0],
        stock_length_ft=_REBAR_STICK_FT if rebar else None,
        waste_mm=None,
        stock_quantity=sticks,
        unit_price_cents=None,
        price_unit=None,
        extended_price_cents=None,
        item=piece.item,
    )
