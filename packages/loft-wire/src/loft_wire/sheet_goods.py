"""Sheet goods: structural panels and the sheets they are sold in (SHEATHING).

Wall sheathing and subfloor are cut from 4 ft wide sheets, as Chief
Architect's wall and floor structure layers and Medeek's sheathing options
build them. A panel is the piece fastened to the framing; it is cut from the
SHORTEST sheet that covers it (a 97.125 in tall wall panel from a 4x9), and
the cut list buys the sheets the panels are cut from, each panel a sheet
unless an earlier offcut covers it whole (SHEET-COUNT-PIECES,
:func:`loft_wire.cut_list.sheets_to_cut`).

Gypsum board (INTERIOR-WALLS) is the finish a partition and an exterior
wall's inside face are hung with: 1/2 in (the US wall default) or 5/8 in
(Type X), sold in 4x8 and 4x12 sheets and hung horizontally. A ceiling
(GYPSUM-SHEETS) is hung in 1/2 in sag-resistant ceiling board, a product of
its own. Each product is cut from the sheets it is sold in
(:data:`SHEET_SIZES_FOR`): structural panels from 4x8, 4x9 and 4x10, gypsum
from 4x8 and 4x12. A panel whose plugin names the sheet it is hung from
(:attr:`loft_wire.plugins.MemberMetadata.sheet`, gypsum hung from 4x12s) is
cut from that sheet, so one choice is one cut-list line.

A product is a material at a thickness, named as the trade sells it:
"7/16 OSB", "23/32 plywood", "1/2 gypsum". APA performance-category panels
are sold under their nominal thickness and built to it within tolerance, so
the nominal thickness is the modelled one (unlike lumber,
:mod:`loft_wire.lumber`). Inches are the source of truth (exact binary
fractions); millimetres are derived once.

A key is ``<material>_<numerator>_<denominator>``, so it is a valid plugin
choice value and a price-book profile beside the lumber keys.
"""

from collections.abc import Mapping
from typing import Final, Literal

from pydantic import BaseModel, Field

from loft_wire.lumber import MM_PER_INCH

#: The library materials sheet goods are made of (each a ``MaterialKey``;
#: spelt here so :mod:`loft_wire.materials` can serve this library).
SheetMaterialKey = Literal["osb", "plywood", "gypsum", "melamine"]

#: The built-in sheet products. A closed literal, like ``LumberProfileKey``.
SheetGoodKey = Literal[
    "osb_7_16",
    "plywood_15_32",
    "plywood_23_32",
    "gypsum_1_2",
    "gypsum_5_8",
    "plywood_3_4",
    "melamine_3_4",
    "plywood_1_2",
    "plywood_1_4",
    "gypsum_ceiling_1_2",
]

#: The sheet sizes sold, by name (width x length, ft).
SheetSizeKey = Literal["4x8", "4x9", "4x10", "4x12"]


class SheetGood(BaseModel):
    """One sheet product: a material at a thickness."""

    key: SheetGoodKey
    name: str = Field(description="As sold, e.g. '7/16 OSB'.")
    material: SheetMaterialKey = Field(description="Library material of the panels.")
    thickness_in: float = Field(gt=0, description="Thickness (in).")
    thickness_mm: float = Field(gt=0, description="Thickness (mm).")


class SheetSize(BaseModel):
    """One sheet size: 4 ft wide, 8, 9, 10 or 12 ft long."""

    key: SheetSizeKey
    width_in: float = Field(gt=0, description="The short side (in): 48.")
    length_in: float = Field(gt=0, description="The long side (in).")

    @property
    def area_in2(self) -> float:
        return self.width_in * self.length_in

    @property
    def width_mm(self) -> float:
        return self.width_in * MM_PER_INCH

    @property
    def length_mm(self) -> float:
        return self.length_in * MM_PER_INCH

    @property
    def area_mm2(self) -> float:
        return self.width_mm * self.length_mm


def _good(
    key: SheetGoodKey, name: str, material: SheetMaterialKey, thickness_in: float
) -> SheetGood:
    return SheetGood(
        key=key,
        name=name,
        material=material,
        thickness_in=thickness_in,
        thickness_mm=thickness_in * MM_PER_INCH,
    )


#: The products in display order.
SHEET_GOODS: tuple[SheetGood, ...] = (
    _good("osb_7_16", "7/16 OSB", "osb", 7 / 16),
    _good("plywood_15_32", "15/32 plywood", "plywood", 15 / 32),
    _good("plywood_23_32", "23/32 plywood", "plywood", 23 / 32),
    _good("gypsum_1_2", "1/2 gypsum", "gypsum", 1 / 2),
    _good("gypsum_5_8", "5/8 gypsum", "gypsum", 5 / 8),
    # Casework (CASEWORK): cabinet panels are cut to their nominal thickness,
    # carcass and fronts 3/4, drawer boxes 1/2 on a 1/4 bottom.
    _good("plywood_3_4", "3/4 plywood", "plywood", 3 / 4),
    _good("melamine_3_4", "3/4 melamine", "melamine", 3 / 4),
    _good("plywood_1_2", "1/2 plywood", "plywood", 1 / 2),
    _good("plywood_1_4", "1/4 plywood", "plywood", 1 / 4),
    # A ceiling (GYPSUM-SHEETS): 1/2 in sag-resistant board (ASTM C1396
    # ceiling board), sold apart from wall board, as a yard stocks it.
    _good("gypsum_ceiling_1_2", "1/2 ceiling gypsum", "gypsum", 1 / 2),
)

#: Key -> product.
SHEET_GOODS_BY_KEY: Mapping[SheetGoodKey, SheetGood] = {g.key: g for g in SHEET_GOODS}

#: The sheet sizes, shortest first: a panel is cut from the first that covers it.
SHEET_SIZES: tuple[SheetSize, ...] = (
    SheetSize(key="4x8", width_in=48.0, length_in=96.0),
    SheetSize(key="4x9", width_in=48.0, length_in=108.0),
    SheetSize(key="4x10", width_in=48.0, length_in=120.0),
    SheetSize(key="4x12", width_in=48.0, length_in=144.0),
)

#: Key -> size.
SHEET_SIZES_BY_KEY: Mapping[SheetSizeKey, SheetSize] = {s.key: s for s in SHEET_SIZES}

#: The sheets each material's products are sold in, shortest first: OSB and
#: plywood in 4x8, 4x9 and 4x10 (SHEATHING), gypsum board in 4x8 and 4x12
#: (INTERIOR-WALLS: 4x12 is the long-wall choice).
SHEET_SIZES_FOR: Mapping[SheetMaterialKey, tuple[SheetSizeKey, ...]] = {
    "osb": ("4x8", "4x9", "4x10"),
    "plywood": ("4x8", "4x9", "4x10"),
    "gypsum": ("4x8", "4x12"),
    # Melamine is sold in 4x8 only (CASEWORK).
    "melamine": ("4x8",),
}

#: How far a panel may exceed a sheet and still be cut from it (mm): far
#: below any real cut, far above the kernel's measuring noise.
SHEET_FIT_TOLERANCE_MM: Final = 1e-6


def sheet_good_for(profile: str | None) -> SheetGood | None:
    """The product a member's ``profile`` names, by key or name, or ``None``."""
    if profile is None:
        return None
    for good in SHEET_GOODS:
        if profile in (good.key, good.name):
            return good
    return None


def covering_sheet(
    length_mm: float,
    width_mm: float,
    good: SheetGood | None = None,
    hung: SheetSizeKey | None = None,
) -> SheetSize | None:
    """The shortest sheet *good* is sold in (a structural panel's 4x8, 4x9 or
    4x10 when ``None``) that a ``length x width`` panel (its in-plane
    extents, mm, either order) is cut from, or ``None`` when none covers it.
    A panel *hung* from a named sheet its product is sold in is cut from
    that sheet when it covers the panel (GYPSUM-SHEETS: a 37 in end piece of
    a wall hung from 4x12s is cut from a 4x12, not bought as a 4x8)."""
    long, short = max(length_mm, width_mm), min(length_mm, width_mm)
    keys: tuple[SheetSizeKey, ...] = SHEET_SIZES_FOR[
        "osb" if good is None else good.material
    ]
    if hung is not None and hung in keys:
        keys = (hung, *(key for key in keys if key != hung))
    for size in (SHEET_SIZES_BY_KEY[key] for key in keys):
        if (
            short <= size.width_mm + SHEET_FIT_TOLERANCE_MM
            and long <= size.length_mm + SHEET_FIT_TOLERANCE_MM
        ):
            return size
    return None
