"""``/api/v1/materials`` — the built-in material library, served not hardcoded.

One table of densities exists (``loft_wire.materials.MATERIALS``) and this
route hands it out, so the material picker and the mass readout read the SAME
numbers the kernel multiplies by (CLAUDE.md DRY: a second copy in TS would drift
silently, and a drifted density is a wrong mass nobody notices).

Static vocabulary, not document state: no owner scoping and no principal header
(documents is internal either way — apps/web reaches this through the gateway).
It lives in documents rather than geometry because material ASSIGNMENT is a
document property; the density it resolves to is what geometry consumes.
"""

from fastapi import APIRouter
from loft_wire.casework import CASEWORK_ITEMS
from loft_wire.foundation import FOUNDATION_ITEMS
from loft_wire.lumber import LUMBER_PROFILES
from loft_wire.materials import MATERIALS, MaterialLibraryResponse
from loft_wire.opening_units import OPENING_UNITS
from loft_wire.sheet_goods import SHEET_GOODS, SHEET_SIZES

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])


@router.get("")
async def list_materials() -> MaterialLibraryResponse:
    """The built-in materials, lumber profiles, sheet goods, window and door
    units, foundation items and casework items, in display order.

    v1 is a closed library (docs/design/materials.md §1/§5): a fixed
    ``MaterialKey`` literal means an unknown material is a parse error at the
    boundary instead of a silent "no mass" three services later. User-defined
    materials extend this response additively when they land.
    """
    return MaterialLibraryResponse(
        materials=list(MATERIALS),
        profiles=list(LUMBER_PROFILES),
        sheet_goods=list(SHEET_GOODS),
        sheet_sizes=list(SHEET_SIZES),
        opening_units=list(OPENING_UNITS),
        foundation_items=list(FOUNDATION_ITEMS),
        casework_items=list(CASEWORK_ITEMS),
    )
