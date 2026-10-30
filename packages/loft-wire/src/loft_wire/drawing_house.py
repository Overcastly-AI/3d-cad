"""House drawings (HOUSE-DRAWINGS): the plan, the four elevations and the
materials list a builder takes to a permit desk or a crew.

Revit cuts a floor plan 4'-0" above its level and places schedules as views on
sheets; Chief Architect adds automatic exterior dimensions to opening centres
and places its Materials List on a sheet. A part's drawing gets the same:

* ``plan``: a horizontal section 48 in above the lowest floor, its cut members
  outlined and hatched, with exterior dimension strings to the opening centres
  and the overall framing on every side;
* ``elevation_front`` / ``_back`` / ``_left`` / ``_right``: the four exterior
  elevations (visible lines only), each dimensioning its opening heads and its
  wall plate above the floor;
* ``materials``: the cut list as a yard order (Item, Qty, Size, Length,
  Material, Price) placed on a sheet, line for line the cut-list panel.

Split from :mod:`loft_wire.drawings` (FILE-SIZE-RATCHET). The mixins below
are bases of the drawings DTOs they extend, so every field is additive and a
drawing without house views serializes as it always did.
"""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from loft_wire.plugins import PluginId
from loft_wire.units import LengthUnit


def _unset(value: object) -> bool:
    """``exclude_if``: an empty list or a null is not serialized, so a drawing
    with no house view serializes byte-identically to the pre-house wire."""
    return value is None or value == []


def _drop_default(schema: dict[str, Any]) -> None:
    """Keep the omitted-when-unset field optional in the generated client."""
    schema.pop("default", None)


#: The keyword set every additive house field carries.
_ADDITIVE: dict[str, Any] = {
    "exclude_if": _unset,
    "json_schema_extra": _drop_default,
}

#: The house-drawing view kinds, in the order a set is laid out.
HOUSE_VIEWS: tuple[str, ...] = (
    "plan",
    "elevation_front",
    "elevation_back",
    "elevation_left",
    "elevation_right",
    "materials",
)

#: How far above the lowest floor the plan is cut (Revit's 4'-0").
PLAN_CUT_HEIGHT_MM = 48 * 25.4

#: Upper bound on the members a drawing request names (a house is ~450).
MAX_DRAWING_MEMBERS = 5000


class DrawingMember(BaseModel):
    """One plugin member of the drawn part: which body plays which role.

    Documents knows each base feature's plugin and role (the cut list's
    ``CutListMember``); geometry only receives base features, so the request
    names them. The plan finds its floor from the subfloor or slab, the
    dimension strings their openings from the headers, and the elevations
    their plate from the top plates.
    """

    feature_id: uuid.UUID = Field(description="The base feature that builds the body")
    plugin_id: PluginId | None = Field(
        default=None, description="The plugin whose member it is"
    )
    role: str = Field(
        max_length=64, description="The member's manifest role ('header')"
    )


DimensionSide = Literal["below", "above", "left", "right"]


class AutoDimensionPoint(BaseModel):
    """A witness point of an automatic dimension, in view-plane mm at the scale."""

    x_mm: float
    y_mm: float


class ViewAutoDimension(BaseModel):
    """A dimension the composer draws on its own (Chief's automatic dimensions).

    ``start`` and ``end`` are view-plane points (mm at the view scale, the
    frame of the view's edges). The value is ``value_mm`` (model-true) along
    ``axis``; the dimension line sits ``side`` of the view's drawn extent, on
    string ``tier`` (0 nearest the geometry). The segments of one string share
    a side and a tier and chain end to end.
    """

    start: AutoDimensionPoint = Field(description="First witness point (view mm)")
    end: AutoDimensionPoint = Field(description="Second witness point (view mm)")
    axis: Literal["x", "y"] = Field(description="The view axis measured along")
    side: DimensionSide = Field(description="Which side of the view it is placed")
    tier: int = Field(ge=0, le=8, description="String row, 0 nearest the view")
    value_mm: float = Field(ge=0, description="The model-true length (mm)")


class HouseViewResult(BaseModel):
    """What a house view adds to its ``DrawingViewResult``."""

    auto_dimensions: list[ViewAutoDimension] = Field(
        default_factory=list[ViewAutoDimension],
        **_ADDITIVE,
        description="Automatic dimensions (HOUSE-DRAWINGS): a plan's exterior "
        "strings, an elevation's head and plate heights. Empty for every other "
        "view.",
    )


class HouseEvaluateInput(BaseModel):
    """What a drawing evaluation needs to know about the part's plugin members."""

    members: list[DrawingMember] = Field(
        default_factory=list[DrawingMember],
        max_length=MAX_DRAWING_MEMBERS,
        **_ADDITIVE,
        description="The part's plugin members (HOUSE-DRAWINGS): a plan finds its "
        "floor, openings and framing by role. Empty: a plan is cut 48 in above the "
        "part's lowest point and draws no strings.",
    )


class HouseLayout(BaseModel):
    """What a house sheet adds to its ``SheetLayout``."""

    length_unit: LengthUnit | None = Field(
        default=None,
        **_ADDITIVE,
        description="The drawn document's unit. 'in' or 'ft' prints every length "
        "as architectural feet-inch to 1/16 in (8'-1 1/8\"); null or metric "
        "keeps millimetres to 3 places.",
    )


#: A yard-order row's kind: a system heading, a line, or the total.
YardOrderRowKind = Literal["group", "line", "total"]

#: The yard order's columns, as the sheet and the CSV head them.
YARD_ORDER_COLUMNS: tuple[str, ...] = (
    "Item",
    "Qty",
    "Size",
    "Length",
    "Material",
    "Price",
)


class YardOrderLine(BaseModel):
    """One cut-list line as a yard orders it: what, how many, how long, the price."""

    system: str = Field(description="The cut-list system heading ('Walls')")
    item: str = Field(description="The member ('Stud'), or the profile")
    qty: str = Field(description="What is bought: stock pieces, sheets, units")
    size: str = Field(description="Profile or product ('2x6', '7/16 OSB')")
    length: str = Field(description="Stock length or sheet ('12 ft', '4x8')")
    material: str = Field(description="Material name, or empty")
    price: str = Field(description="Extended price ('$1,234.56'), or empty")
    price_cents: int | None = Field(description="Extended price in cents, or null")


class YardOrder(BaseModel):
    """The cut list as a yard order: its lines in the cut list's order."""

    name: str = Field(description="The document the order is for")
    currency: str = Field(description="ISO 4217 code")
    lines: list[YardOrderLine] = Field(default_factory=list[YardOrderLine])
    total: str = Field(description="The priced lines' total ('$2,868.87'), or empty")
    total_cents: int | None = Field(description="The total in cents, or null")
    total_label: str = Field(description="'Total', or how many lines it leaves out")


class HouseComposeInput(BaseModel):
    """What a materials sheet adds to its ``ComposeDrawingRequest``."""

    materials: YardOrder | None = Field(
        default=None,
        **_ADDITIVE,
        description="The drawn part's cut list as a yard order, for a sheet with a "
        "`materials` view (the gateway prices it from the caller's book). Null for "
        "every other sheet.",
    )


class ComposedTableRow(BaseModel):
    """One placed row of the materials table."""

    kind: YardOrderRowKind
    y: float = Field(description="Text baseline (mm, SVG space)")
    cells: list[str] = Field(description="One string per column (a group: one)")


class ComposedTableBlock(BaseModel):
    """One column-flow block of the materials table: its frame and rows."""

    x: float
    y: float
    width: float
    height: float
    header_y: float = Field(description="Header text baseline (mm)")
    rows: list[ComposedTableRow]


class ComposedMaterialsTable(BaseModel):
    """The placed materials list (Chief's Materials List on a sheet).

    A bordered table in sheet-mm SVG space: the column x positions and
    alignments, a header row, then the rows. A table taller than the drawing
    area flows into further columns of the same width, each with its header.
    """

    x: float
    y: float
    width: float
    height: float
    row_height: float
    text_mm: float
    columns: list[str] = Field(description="Column headings")
    column_dx: list[float] = Field(
        description="Each column's left edge from its block's left edge (mm)"
    )
    column_w: list[float] = Field(description="Each column's width (mm)")
    align: list[Literal["left", "right"]] = Field(description="Text alignment")
    blocks: list[ComposedTableBlock] = Field(
        description="The table's blocks, left to right"
    )


class HouseComposedSheet(BaseModel):
    """What a materials sheet adds to its ``ComposedSheet``."""

    materials_table: ComposedMaterialsTable | None = Field(
        default=None,
        **_ADDITIVE,
        description="The placed materials list (HOUSE-DRAWINGS); null on a sheet "
        "with no `materials` view.",
    )
