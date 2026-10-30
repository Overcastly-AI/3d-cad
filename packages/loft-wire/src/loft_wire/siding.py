"""Siding and exterior trim: what a wall's Exterior finish is bought as
(SIDING-TRIM, RESEARCH §23).

Chief Architect's wall types carry a siding layer, and its Materials List
counts siding by the AREA it covers, net of the openings, with corner
boards and exterior casing as lines of their own; a builder's estimate does
the same, then adds a waste allowance and rounds up to what the yard sells
(VISION 2026-10-29: net area plus an editable 10 %, not course by course).
US yards sell fibre-cement lap by the 12 ft board and vinyl by the SQUARE
(100 ft² of wall covered).

* **The layer is drawn, the boards are not.** A wall's siding is one body
  per connected region of its face (the cased openings and the corner boards
  cut out), drawn at the product's own thickness on the sheathing's outer
  face, as Chief draws a wall type's siding layer. Its MEASURED net area
  (the body's volume over its thickness) is what is bought.
* **The order** is ``ceil(net x (1 + waste) / coverage)`` whole boards or
  squares (:func:`siding_order`), the coverage being what one board covers
  at its exposure (8.25 in lap at 7 in: 7 x 144 = 1 008 in²) or a square's
  14 400 in².
* **Trim** is 5/4x4 (1 x 3.5 in), bought as lumber: a corner board on each
  face of every outside corner and picture-frame casing round every window
  and door unit, in the finish's trim material (fibre-cement trim with lap,
  cellular PVC with vinyl, cedar with cedar).

Each product is a price-book key beside the lumber, sheet and unit keys: a
board ``each`` at its 12 ft stock length (or per linear foot), vinyl per
``square``. Inches are the source of truth (exact binary fractions where the
trade's sizes are); millimetres are derived at x 25.4 exactly. Pure: no I/O.
"""

import math
from collections.abc import Mapping
from typing import Final, Literal

from pydantic import BaseModel, Field

from loft_wire.lumber import MM_PER_INCH

#: Square inches in a square: 100 ft² of wall covered.
IN2_PER_SQUARE: Final = 14_400

#: The waste allowance a new wall orders its siding with (percent of the net
#: area): the editable 10 % of VISION 2026-10-29.
DEFAULT_SIDING_WASTE_PERCENT: Final = 10

#: The highest allowance a wall may take (percent): a cut-up elevation with
#: many openings runs 15-20 %.
MAX_SIDING_WASTE_PERCENT: Final = 30

#: An order is ``ceil(units - ORDER_SLACK)``, so an area that is exactly 100
#: boards by the kernel's measure orders 100, not 101 by an ulp.
ORDER_SLACK: Final = 1e-9

#: The built-in siding products, by price-book key.
SidingProductKey = Literal["fibre_cement_lap_8_25", "vinyl_d4", "cedar_bevel_1_2x8"]

#: The library materials the products and their trim are made of (each a
#: ``MaterialKey``; spelt here so :mod:`loft_wire.materials` can serve this
#: catalogue).
SidingMaterialKey = Literal["fibre_cement", "pvc", "western_red_cedar"]

#: How a product is sold: whole boards of its stock length, or squares.
SidingSale = Literal["board", "square"]

#: The trim's lumber profile: 5/4x4, 1 x 3.5 in actual.
TRIM_PROFILE: Final = "us_5_4x4"
#: The trim's actual size (in): its thickness off the sheathing and its face.
TRIM_THICKNESS_IN: Final = 1.0
TRIM_WIDTH_IN: Final = 3.5


class SidingProduct(BaseModel):
    """One siding product: how it is drawn, what it covers and how it is sold."""

    key: SidingProductKey = Field(description="Price-book key, e.g. 'vinyl_d4'.")
    name: str = Field(description="As listed, e.g. 'Fibre-cement lap 8-1/4'.")
    label: str = Field(description="As the Exterior finish offers it.")
    material: SidingMaterialKey = Field(
        description="Library material the product is drawn, weighed and priced as."
    )
    trim_material: SidingMaterialKey = Field(
        description="The library material of its 5/4x4 corner boards and casing."
    )
    thickness_in: float = Field(
        gt=0, description="The drawn layer's thickness (in): one board's."
    )
    width_in: float = Field(gt=0, description="A board's (or course's) face (in).")
    exposure_in: float = Field(gt=0, description="What a course shows (in).")
    sale: SidingSale = Field(description="Sold by the board or by the square.")
    stock_length_ft: int | None = Field(
        default=None,
        description="A board's stock length (ft), what an 'each' price is for; "
        "null for a product sold by the square.",
    )
    coverage_in2: float = Field(
        gt=0,
        description="Wall area one board (exposure x length) or one square "
        "covers (in²).",
    )
    price_unit: Literal["each", "square"] = Field(
        description="How a price-book entry prices it: a board Each at its "
        "stock length (or per linear foot), vinyl per square."
    )

    @property
    def thickness_mm(self) -> float:
        return self.thickness_in * MM_PER_INCH


def _board(
    key: SidingProductKey,
    name: str,
    label: str,
    material: SidingMaterialKey,
    thickness: float,
    width: float,
    exposure: float,
) -> SidingProduct:
    return SidingProduct(
        key=key,
        name=name,
        label=label,
        material=material,
        trim_material=material,
        thickness_in=thickness,
        width_in=width,
        exposure_in=exposure,
        sale="board",
        stock_length_ft=12,
        coverage_in2=exposure * 144,
        price_unit="each",
    )


#: The catalogue in the order the Exterior finish offers it (the default
#: first). Fibre-cement lap is James Hardie's HardiePlank 8.25 x 5/16 at its
#: 7 in exposure, on 12 ft boards; vinyl is a builder-grade double 4 (two 4 in
#: courses, 0.044 in gauge) sold by the square; cedar is 1/2 x 8 bevel
#: (7-1/4 in face, 15/32 in butt) at the 1 in lap WRCLA asks, a 6-1/4 in
#: exposure, on 12 ft boards.
SIDING_PRODUCTS: tuple[SidingProduct, ...] = (
    _board(
        "fibre_cement_lap_8_25",
        "Fibre-cement lap 8-1/4",
        "Lap, fibre cement 8-1/4 in at 7 in",
        "fibre_cement",
        5 / 16,
        8.25,
        7.0,
    ),
    SidingProduct(
        key="vinyl_d4",
        name="Vinyl siding, double 4",
        label="Vinyl, double 4 in",
        material="pvc",
        trim_material="pvc",
        thickness_in=0.044,
        width_in=8.0,
        exposure_in=8.0,
        sale="square",
        coverage_in2=IN2_PER_SQUARE,
        price_unit="square",
    ),
    _board(
        "cedar_bevel_1_2x8",
        "Cedar bevel 1/2x8",
        "Cedar bevel 1/2 x 8 at 6-1/4 in",
        "western_red_cedar",
        15 / 32,
        7.25,
        6.25,
    ),
)

#: Key -> product.
SIDING_PRODUCTS_BY_KEY: Mapping[str, SidingProduct] = {
    p.key: p for p in SIDING_PRODUCTS
}


def siding_product_for(profile: str | None) -> SidingProduct | None:
    """The product a member's ``profile`` names, by key or name, or ``None``."""
    if profile is None:
        return None
    for product in SIDING_PRODUCTS:
        if profile in (product.key, product.name):
            return product
    return None


def siding_order(
    product: SidingProduct, net_area_in2: float, waste_percent: int
) -> int:
    """Whole boards or squares for *net_area_in2* of wall with
    *waste_percent* over: ``ceil(net x (1 + waste) / coverage)``."""
    if net_area_in2 <= 0:
        return 0
    units = net_area_in2 * (100 + waste_percent) / (100 * product.coverage_in2)
    return max(0, math.ceil(units - ORDER_SLACK))


class SidingTakeoff(BaseModel):
    """Set on a siding body (SIDING-TRIM): the cut list lists its MEASURED net
    area and orders its product with this allowance, in whole boards or
    squares."""

    product: SidingProductKey = Field(description="The siding product.")
    waste_percent: int = Field(
        default=DEFAULT_SIDING_WASTE_PERCENT,
        ge=0,
        le=MAX_SIDING_WASTE_PERCENT,
        description="Ordered over the net area (percent), then rounded up to "
        "whole boards or squares.",
    )


__all__ = [
    "DEFAULT_SIDING_WASTE_PERCENT",
    "IN2_PER_SQUARE",
    "MAX_SIDING_WASTE_PERCENT",
    "SIDING_PRODUCTS",
    "SIDING_PRODUCTS_BY_KEY",
    "TRIM_PROFILE",
    "TRIM_THICKNESS_IN",
    "TRIM_WIDTH_IN",
    "SidingMaterialKey",
    "SidingProduct",
    "SidingProductKey",
    "SidingSale",
    "SidingTakeoff",
    "siding_order",
    "siding_product_for",
]
