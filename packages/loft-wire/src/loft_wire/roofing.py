"""Roofing: what a roof's covering is bought as (ROOFING, RESEARCH §23).

Chief Architect's roof planes carry a sheathing layer and a roofing layer,
and its Materials List counts the roofing in SQUARES (100 ft² of roof) and
the drip edge by length; a roofer's estimate does the same, adds a waste
allowance for the cuts at the rakes, hips and valleys, and rounds up to what
the yard sells. The deck (7/16 OSB) is DRAWN, a panel a sheet piece, and
listed as every sheet good is. What lies on it is LISTED, not drawn (it is
thinner than the tolerance a section would read, and Chief lists it from
the plane's settings), from the deck panels' metadata (:class:`RoofingTakeoff`):

* **Shingles** (architectural, laminated) by the bundle, 3 bundles a square,
  over the deck's MEASURED net area plus the roof's waste allowance (10 % by
  default): ``ceil(net x (1 + waste) / 1/3 square)`` bundles
  (:func:`bundles`), once over the line's total.
* **Underlayment** (synthetic) by the 10-square roll, over the same area
  and allowance (its laps): ``ceil(net x (1 + waste) / 10 squares)``.
* **Drip edge** on every eave and rake, in 10 ft sticks lapped 2 in at each
  joint: a run of L in takes ``ceil((L - 2) / 118)`` sticks
  (:func:`drip_edge_sticks`), each run on its own.
* **Starter** along the eaves and **ridge cap** along the ridge, by the
  foot, bought in whole feet of the line's total.

The runs are the roof's EDGES as the plugin lays them (:class:`RoofEdgeRun`),
listed on one deck panel of each plane, as a pour lists its rebar. Each
product is a price-book key beside the lumber, sheet and unit keys:
``shingle_architectural`` Each per bundle, ``underlayment_synthetic`` Each per
roll, ``drip_edge`` Each per 10 ft stick, ``shingle_starter`` and
``ridge_cap`` per linear foot. Inches are the source of truth; millimetres
are derived at x 25.4 exactly. Pure: no I/O.
"""

import math
from collections.abc import Mapping
from typing import Final, Literal

from pydantic import BaseModel, Field

from loft_wire.lumber import MM_PER_INCH

#: Square inches in a square: 100 ft² of roof.
IN2_PER_SQUARE: Final = 14_400

#: The waste allowance a roof orders its shingles and underlayment with
#: (percent of the deck's net area): a gable's cuts at its rakes and ridge.
DEFAULT_ROOFING_WASTE_PERCENT: Final = 10

#: The highest allowance a roof may take (percent): a cut-up hip and valley
#: roof runs 15-20 %.
MAX_ROOFING_WASTE_PERCENT: Final = 30

#: An order is ``ceil(units - ORDER_SLACK)``, so an area that is exactly 17
#: bundles by the kernel's measure orders 17, not 18 by an ulp.
ORDER_SLACK: Final = 1e-9

#: A drip-edge stick (in): 10 ft, lapped 2 in at each joint.
DRIP_EDGE_STICK_IN: Final = 120
DRIP_EDGE_LAP_IN: Final = 2

#: The listed roofing items, by price-book key.
RoofingItemKey = Literal[
    "shingle_architectural",
    "underlayment_synthetic",
    "drip_edge",
    "shingle_starter",
    "ridge_cap",
]

#: The library materials the items are made of (each a ``MaterialKey``;
#: spelt here so :mod:`loft_wire.materials` can serve this catalogue).
RoofingMaterialKey = Literal["asphalt_shingle", "polypropylene", "aluminium_3105"]

#: How an item is bought: by area (bundles, rolls), by the stick or by the foot.
RoofingSale = Literal["area", "stick", "foot"]

#: A roof edge a run lies along.
RoofEdge = Literal["eave", "rake", "ridge"]


class RoofingItem(BaseModel):
    """One listed roofing item: what it covers and how it is priced."""

    key: RoofingItemKey = Field(description="Price-book key, e.g. 'drip_edge'.")
    name: str = Field(description="As listed, e.g. 'Drip edge'.")
    material: RoofingMaterialKey = Field(
        description="Library material the item is priced as."
    )
    sale: RoofingSale = Field(
        description="'area': whole units over a net area plus waste (a bundle "
        "of shingles, a roll of underlayment); 'stick': drip edge per stick, "
        "each run lapped on its own; 'foot': whole feet of the line's length."
    )
    coverage_in2: float | None = Field(
        default=None,
        description="Roof one unit covers (in²): a bundle 1/3 square, a roll "
        "10 squares; null for an item bought by length.",
    )
    stock_length_ft: int | None = Field(
        default=None,
        description="The stick an Each price is for (ft): 10 for drip edge; "
        "null otherwise.",
    )
    price_unit: Literal["each", "linear_foot"] = Field(
        description="How a price-book entry prices it: a bundle, a roll or a "
        "stick Each; starter and ridge cap per linear foot."
    )


#: The catalogue in list order. Architectural shingles are laminated
#: asphalt shingles sold 3 bundles to the square (GAF Timberline HDZ, Owens
#: Corning Duration); synthetic underlayment a 10-square roll (GAF
#: FeltBuster, 1 000 ft²); drip edge a 10 ft stick of aluminium.
ROOFING_ITEMS: tuple[RoofingItem, ...] = (
    RoofingItem(
        key="shingle_architectural",
        name="Architectural shingles",
        material="asphalt_shingle",
        sale="area",
        coverage_in2=IN2_PER_SQUARE / 3,
        price_unit="each",
    ),
    RoofingItem(
        key="underlayment_synthetic",
        name="Synthetic underlayment",
        material="polypropylene",
        sale="area",
        coverage_in2=10 * IN2_PER_SQUARE,
        price_unit="each",
    ),
    RoofingItem(
        key="drip_edge",
        name="Drip edge",
        material="aluminium_3105",
        sale="stick",
        stock_length_ft=10,
        price_unit="each",
    ),
    RoofingItem(
        key="shingle_starter",
        name="Starter strip",
        material="asphalt_shingle",
        sale="foot",
        price_unit="linear_foot",
    ),
    RoofingItem(
        key="ridge_cap",
        name="Ridge cap",
        material="asphalt_shingle",
        sale="foot",
        price_unit="linear_foot",
    ),
)

#: Key -> item.
ROOFING_ITEMS_BY_KEY: Mapping[str, RoofingItem] = {i.key: i for i in ROOFING_ITEMS}

#: What each edge is listed as: an eave takes drip edge and starter, a rake
#: drip edge, the ridge its cap.
EDGE_ITEMS: Mapping[RoofEdge, tuple[RoofingItemKey, ...]] = {
    "eave": ("drip_edge", "shingle_starter"),
    "rake": ("drip_edge",),
    "ridge": ("ridge_cap",),
}


def roofing_item_for(name: str | None) -> RoofingItem | None:
    """The item a line's ``profile`` names, by key or name, or ``None``."""
    if name is None:
        return None
    for item in ROOFING_ITEMS:
        if name in (item.key, item.name):
            return item
    return None


def area_order(item: RoofingItem, net_area_in2: float, waste_percent: int) -> int:
    """Whole bundles or rolls of *item* over *net_area_in2* of roof with
    *waste_percent* over: ``ceil(net x (1 + waste) / coverage)``."""
    if net_area_in2 <= 0 or item.coverage_in2 is None:
        return 0
    units = net_area_in2 * (100 + waste_percent) / (100 * item.coverage_in2)
    return max(0, math.ceil(units - ORDER_SLACK))


def bundles(net_area_in2: float, waste_percent: int) -> int:
    """Architectural shingles: 3 bundles a square (module docstring)."""
    return area_order(
        ROOFING_ITEMS_BY_KEY["shingle_architectural"], net_area_in2, waste_percent
    )


def drip_edge_sticks(run_in: float) -> int:
    """10 ft sticks for one run of *run_in*, lapped 2 in at each joint."""
    if run_in <= 0:
        return 0
    reach = DRIP_EDGE_STICK_IN - DRIP_EDGE_LAP_IN
    return max(1, math.ceil((run_in - DRIP_EDGE_LAP_IN) / reach - ORDER_SLACK))


def whole_feet(length_in: float) -> int:
    """The whole feet bought for *length_in* of starter or ridge cap."""
    return max(0, math.ceil(length_in / 12 - ORDER_SLACK))


class RoofEdgeRun(BaseModel):
    """One edge of a roof plane, listed on a deck panel (ROOFING): an eave
    (drip edge and starter), a rake (drip edge) or the ridge (ridge cap), by
    its length along the edge."""

    edge: RoofEdge
    length_mm: float = Field(gt=0, description="Along the edge (mm).")

    @property
    def length_in(self) -> float:
        return self.length_mm / MM_PER_INCH


class RoofingTakeoff(BaseModel):
    """Set on each roof deck panel (ROOFING): the cut list buys the shingles
    and underlayment over its MEASURED net area with this allowance, and
    lists the edges it carries (one panel of each plane carries them)."""

    shingles: Literal["shingle_architectural"] = Field(
        default="shingle_architectural", description="The shingle product."
    )
    underlayment: Literal["underlayment_synthetic"] = Field(
        default="underlayment_synthetic", description="The underlayment."
    )
    waste_percent: int = Field(
        default=DEFAULT_ROOFING_WASTE_PERCENT,
        ge=0,
        le=MAX_ROOFING_WASTE_PERCENT,
        description="Ordered over the net area (percent), then rounded up to "
        "whole bundles and rolls.",
    )
    edges: list[RoofEdgeRun] = Field(
        default_factory=list[RoofEdgeRun],
        max_length=16,
        description="The plane's edges, on its first deck panel only: its "
        "eave, its rakes and (on one plane) the ridge.",
    )


__all__ = [
    "DEFAULT_ROOFING_WASTE_PERCENT",
    "DRIP_EDGE_LAP_IN",
    "DRIP_EDGE_STICK_IN",
    "EDGE_ITEMS",
    "IN2_PER_SQUARE",
    "MAX_ROOFING_WASTE_PERCENT",
    "ROOFING_ITEMS",
    "ROOFING_ITEMS_BY_KEY",
    "RoofEdge",
    "RoofEdgeRun",
    "RoofingItem",
    "RoofingItemKey",
    "RoofingMaterialKey",
    "RoofingTakeoff",
    "area_order",
    "bundles",
    "drip_edge_sticks",
    "roofing_item_for",
    "whole_feet",
]
