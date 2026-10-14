"""The section view's cutting-plane parameters (drawings-section.md §1).

Split out of :mod:`loft_wire.drawings` (FILE-SIZE-RATCHET) and re-exported from
there, so ``from loft_wire.drawings import SectionViewParams`` keeps working.
"""

from pydantic import BaseModel, Field

from loft_wire.features import GeomRef


class SectionViewParams(BaseModel):
    """The cutting plane + half selection of a section view (drawings-section.md §1).

    v1 specifies the section's cutting plane by DATUM REFERENCE, not a drawn cutting
    line (§1): ``plane`` is the shipped :data:`~loft_wire.features.GeomRef`
    (``DatumPlaneRef`` for one of the XY/XZ/YZ origin planes, or a ``FeatureRef`` to
    an axis-aligned offset / midplane datum FEATURE in the referenced part) — the
    EXACT union a sketch's plane reference uses, so no parallel plane taxonomy is
    introduced (DRY). The geometry service resolves it, checks the v1 axis-aligned
    precondition (a non-principal normal is a typed ``section_plane_not_principal``,
    §7), cuts, and hatches. ``flip`` chooses which half is removed (§4): ``false``
    (default) removes the eye-side material (the standard "cut away what is between
    you and the plane"), ``true`` the far side.
    """

    plane: GeomRef = Field(
        description="The cutting plane, as a datum reference (reused GeomRef): a "
        "DatumPlaneRef (XY/XZ/YZ) or a FeatureRef to an axis-aligned offset/midplane "
        "datum. A non-principal-axis normal is out of v1 (typed error, §7)."
    )
    flip: bool = Field(
        default=False,
        description="Which half is removed (§4): false (default) removes the eye-side "
        "material; true the far side.",
    )
