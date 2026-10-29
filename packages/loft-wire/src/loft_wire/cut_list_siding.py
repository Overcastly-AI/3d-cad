"""Siding in the cut list (SIDING-TRIM, RESEARCH §23).

Split from :mod:`loft_wire.cut_list` (FILE-SIZE-RATCHET). A siding body (its
metadata's ``siding``, :mod:`loft_wire.siding`) is a LAYER: it is listed by
its MEASURED net area, its volume over its thinnest extent (the cased
openings and corner boards are cut out of it), under Siding and trim. Bodies
of one product, material and waste allowance are one line, whichever
feature drew them (a wall's faces and a roof's gables), and the line orders
``ceil(net x (1 + waste) / coverage)`` whole boards or squares ONCE over its
total, as a builder's estimate rounds the whole order, not each wall.

A board line is priced by an ``each`` entry for its product at its 12 ft
stock length, else a per-foot entry times the board's feet; a vinyl line by
a ``square`` entry; times the boards or squares ordered. The corner boards
and casing are 5/4x4 lumber, listed and priced as lumber under the same
system. :mod:`loft_wire.cut_list` imports this module, so this one reads its
types through the module at call time.
"""

from collections.abc import Mapping, Sequence

import loft_wire.cut_list as cl
from loft_wire.lumber import MM_PER_INCH
from loft_wire.materials import MaterialKey
from loft_wire.price_book import PriceBookEntry, PriceKey, PriceUnit
from loft_wire.siding import SIDING_PRODUCTS_BY_KEY, SidingProduct, siding_order


def siding_piece(
    body: cl.BodyExtent,
    member: cl.CutListMember,
    material: MaterialKey | None,
    count: int,
) -> cl.CutListPiece:
    """A siding body as a piece: its thinnest extent through it, its net
    area its volume over that, under Siding and trim."""
    takeoff = member.metadata.siding
    assert takeoff is not None
    extents = body.extents_mm
    thickness = extents[2]
    return cl.CutListPiece(
        member=member.title,
        profile=member.metadata.profile,
        lumber=False,
        material=material,
        classification="member",
        length_mm=extents[0],
        section_mm=(thickness, extents[1]),
        count=count,
        area_mm2=body.volume_mm3 / thickness if thickness > 0 else 0.0,
        system="siding",
        siding=takeoff.product,
        waste_percent=takeoff.waste_percent,
    )


def _members_of(pieces: Sequence[cl.CutListPiece]) -> str | None:
    members: list[str] = []
    for piece in pieces:
        if piece.member is not None and piece.member not in members:
            members.append(piece.member)
    return ", ".join(members) or None


def siding_line(pieces: Sequence[cl.CutListPiece], quantity: int) -> cl.CutListLine:
    """Siding bodies of one product, material and allowance as one line:
    their net area and the boards or squares it orders (module docstring)."""
    first = pieces[0]
    assert first.siding is not None
    product = SIDING_PRODUCTS_BY_KEY[first.siding]
    area = sum((p.area_mm2 or 0.0) * p.count for p in pieces)
    waste = first.waste_percent or 0
    order = siding_order(product, area / MM_PER_INCH**2, waste)
    board = (
        0.0
        if product.stock_length_ft is None
        else product.stock_length_ft * cl.MM_PER_FOOT
    )
    return cl.CutListLine(
        system="siding",
        member=_members_of(pieces),
        profile=product.name,
        material=first.material,
        classification=first.classification,
        quantity=quantity,
        length_mm=round(board, 6),
        total_length_mm=round(board * order, 6),
        section_mm=[
            round(first.section_mm[0], 6),
            round(product.width_in * MM_PER_INCH, 6),
        ],
        area_mm2=round(area, 6),
        stock_length_ft=product.stock_length_ft,
        waste_mm=None,
        stock_quantity=order,
        unit_price_cents=None,
        price_unit=None,
        extended_price_cents=None,
        waste_percent=waste,
        siding=product.key,
    )


def siding_price(
    line: cl.CutListLine, entries: Mapping[PriceKey, PriceBookEntry]
) -> tuple[int, PriceUnit] | None:
    """The price (cents) of one board or square of *line* and the unit that
    priced it, or ``None`` when the book has none (module docstring)."""
    if line.siding is None or line.material is None:
        return None
    product: SidingProduct = SIDING_PRODUCTS_BY_KEY[line.siding]
    if product.sale == "square":
        entry = entries.get((line.material, product.key, "square", None, None))
        return None if entry is None else (entry.price_cents, "square")
    feet = product.stock_length_ft
    entry = entries.get((line.material, product.key, "each", feet, None))
    if entry is not None:
        return entry.price_cents, "each"
    entry = entries.get((line.material, product.key, "linear_foot", None, None))
    if entry is not None and feet is not None:
        return entry.price_cents * feet, "linear_foot"
    return None
