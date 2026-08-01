"""``/api/v1/materials`` — the built-in material library, served not hardcoded.

One table of densities exists (``py_kit.schemas.materials.MATERIALS``) and this
route hands it out, so the material picker and the mass readout read the SAME
numbers the kernel multiplies by (CLAUDE.md DRY: a second copy in TS would drift
silently, and a drifted density is a wrong mass nobody notices).

Static vocabulary, not document state: no owner scoping and no principal header
(documents is internal either way — apps/web reaches this through the gateway).
It lives in documents rather than geometry because material ASSIGNMENT is a
document property; the density it resolves to is what geometry consumes.
"""

from fastapi import APIRouter
from py_kit.schemas.materials import MATERIALS, MaterialLibraryResponse

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])


@router.get("")
async def list_materials() -> MaterialLibraryResponse:
    """The built-in materials, in display order (metals, then polymers).

    v1 is a closed library (docs/design/materials.md §1/§5): a fixed
    ``MaterialKey`` literal means an unknown material is a parse error at the
    boundary instead of a silent "no mass" three services later. User-defined
    materials extend this response additively when they land.
    """
    return MaterialLibraryResponse(materials=list(MATERIALS))
