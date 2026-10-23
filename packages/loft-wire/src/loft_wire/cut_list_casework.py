"""Casework banding and hardware in the cut list (CASEWORK, RESEARCH §23).

Split from :mod:`loft_wire.cut_list` (FILE-SIZE-RATCHET). A cabinet panel's
edge banding and hardware are not bodies: they come from its member's
metadata (:mod:`loft_wire.casework`) and are summed into one line per item
and material, banding by its length (bought in whole feet, priced per foot)
and hinges and slide pairs Each. :mod:`loft_wire.cut_list` imports this
module, so this one reads its types through the module at call time.
"""

import math
from collections.abc import Sequence

import loft_wire.cut_list as cl
from loft_wire.casework import CASEWORK_ITEMS_BY_KEY, HARDWARE_MATERIAL, CaseworkItemKey
from loft_wire.materials import MaterialKey


def casework_pieces(member: "cl.CutListMember", count: int) -> "list[cl.CutListPiece]":
    """A cabinet member's banding and hardware as item pieces (CASEWORK)."""
    system = cl.system_for_plugin(member.plugin_id)
    meta = member.metadata
    found: list[tuple[CaseworkItemKey, MaterialKey, float, int]] = []
    if meta.banding is not None:
        found.append(("edge_banding", meta.banding.material, meta.banding.length_mm, 1))
    for hardware in meta.hardware or []:
        found.append((hardware.key, HARDWARE_MATERIAL, 0.0, hardware.quantity))
    return [
        cl.CutListPiece(
            member=CASEWORK_ITEMS_BY_KEY[key].name,
            profile=CASEWORK_ITEMS_BY_KEY[key].name,
            lumber=False,
            material=material,
            classification="member",
            length_mm=length,
            section_mm=(0.0, 0.0),
            count=count * quantity,
            system=system,
            casework=key,
        )
        for key, material, length, quantity in found
    ]


def casework_line(
    pieces: "Sequence[cl.CutListPiece]", quantity: int
) -> "cl.CutListLine":
    """Casework items of one key and material as one line: hardware Each
    (*quantity* pieces), banding as its summed length, bought in whole feet
    (the stock quantity), its quantity the banded panels."""
    first = pieces[0]
    banding = first.casework == "edge_banding"
    total = round(sum(p.length_mm * p.count for p in pieces), 6)
    feet = math.ceil(total / cl.MM_PER_FOOT - 1e-9) if banding else quantity
    return cl.CutListLine(
        system=first.system,
        member=first.member,
        profile=first.profile,
        material=first.material,
        classification="member",
        quantity=quantity,
        length_mm=total,
        total_length_mm=total,
        section_mm=[0.0, 0.0],
        stock_length_ft=None,
        waste_mm=None,
        stock_quantity=feet,
        unit_price_cents=None,
        price_unit=None,
        extended_price_cents=None,
        casework=first.casework,
    )
