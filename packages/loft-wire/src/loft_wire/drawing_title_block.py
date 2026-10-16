"""The placed title block of a composed sheet, and the kind of drawing it names.

Split out of :mod:`loft_wire.drawings` (FILE-SIZE-RATCHET) and re-exported from it,
so every import and every generated schema name is unchanged.
"""

from typing import Literal

from pydantic import BaseModel, Field

#: What a sheet drafts, as its title block names it: a part drawing or an assembly
#: drawing (bike round 2: an assembly sheet read "PART DRAWING").
DrawingKind = Literal["part", "assembly"]

#: The title block's fixed kind caption per :data:`DrawingKind` — one table the SVG,
#: PDF and DXF serializers stamp from (the on-screen sheet mirrors it).
DRAWING_KIND_CAPTION: dict[DrawingKind, str] = {
    "part": "LOFT · PART DRAWING",
    "assembly": "LOFT · ASSEMBLY DRAWING",
}


class ComposedTitleBlock(BaseModel):
    """The placed bottom-right title block (drawing-export.md §4.2).

    Geometry (box + the two internal rules) plus the stamped values: the always-on
    drawing ``title`` (truncated to fit), ``scale`` label and ``size`` display, plus
    the OPTIONAL free-text :class:`TitleBlock` fields ``author`` / ``date`` / ``notes``
    (each truncated to fit its cell, ``None`` when unset). The fixed captions ("TITLE" /
    "SCALE" / "SIZE" / the ``kind`` caption ("LOFT · PART DRAWING" or "LOFT · ASSEMBLY
    DRAWING", :data:`DRAWING_KIND_CAPTION`) and, for the optional fields, "DRAWN" /
    "DATE" / "NOTES") are the serializer's rendering constants (matching the on-screen
    title block). A ``None`` optional field is stamped by NO serializer — caption and
    value both omitted — so a title block with no free-text composes byte-identically to
    its pre-free-text golden (the additive posture the notes/bend-table fields carry).
    """

    x: float
    y: float
    width: float
    height: float
    split_x: float = Field(description="X of the vertical rule (left | right cells)")
    mid_y: float = Field(description="Y of the horizontal rule in the right cell")
    title: str = Field(description="Drawing title, truncated to fit the cell")
    scale: str = Field(description="Scale label ('1:1')")
    size: str = Field(description="Sheet size, display form ('A4', 'ANSI A')")
    kind: DrawingKind = Field(
        default="part",
        description="What the sheet drafts; the title block's kind caption reads "
        "'LOFT · PART DRAWING' or 'LOFT · ASSEMBLY DRAWING'",
    )
    author: str | None = Field(
        default=None,
        description="Author/drafter, truncated to fit; None (stamps nothing) when the "
        "authored field is unset or blank",
    )
    date: str | None = Field(
        default=None,
        description="Free-text date, truncated to fit; None (stamps nothing) when the "
        "authored field is unset or blank",
    )
    notes: str | None = Field(
        default=None,
        description="Free-text notes, truncated to fit; None (stamps nothing) when the "
        "authored field is unset or blank",
    )
