"""Foundation takeoff: concrete, rebar and anchor bolts (SLAB, RESEARCH §23).

What Chief Architect's materials list carries for a foundation and Revit's
structural foundation schedules list: the CONCRETE of each pour by volume,
its reinforcing bars by length and the anchor bolts that hold the sill or
bottom plates down (docs/reference-parts/buildings.md, "Foundation and
partition conventions").

* **Concrete** is one body per pour, listed in cubic yards (46 656 in³ per
  yd³) and ORDERED with a waste allowance (5 % by default, an input of the
  pour: crews order over for spillage and sub-grade variance), then rounded
  UP to the 1/4 yd³ a ready-mix plant batches (:func:`concrete_order_yd3`).
  Priced per cubic yard ordered.
* **Rebar and anchor bolts are listed, not drawn**: they would sit inside the
  concrete (the no-interference rule), and Chief lists them from the
  foundation's settings. A bar is listed by its CENTRELINE length; #4 is
  bought in 20 ft sticks lapped 24 in at each joint, so a closed loop of L
  takes ``ceil(L / 18 ft)`` sticks (:func:`rebar_sticks`).
* **Anchor bolts** (IRC R403.1.6): 1/2 in, one 12 in from each end of each
  plate piece that bears on concrete, the rest at most 72 in apart, at least 2
  per piece (:func:`anchor_bolt_count`). The count is taken from the plate's
  MEASURED length in the cut list, as every length is.
* **Foundation vents and the crawl-space access door** (FOUNDATION-TAKEOFF)
  are bought units set in the openings cut from a stem wall: Chief's
  materials list carries them Each. The pour lists them by size
  (:class:`FoundationOpening`), so the cut list prices each Each.

Each item is a price-book key beside the lumber, sheet and unit keys:
``ready_mix`` per cubic yard, ``rebar_4`` Each per 20 ft stick, and
``anchor_bolt_1_2``, ``foundation_vent`` and ``crawl_access_door`` Each.
Inches are the source of truth (exact binary fractions); millimetres are
derived at x 25.4 exactly. Pure: no I/O.
"""

import math
from collections.abc import Mapping
from fractions import Fraction
from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field

from loft_wire.lumber import MM_PER_INCH
from loft_wire.twist import is_none

#: Cubic inches per cubic yard, exactly (36^3).
IN3_PER_YD3: Final = 46_656

#: Ready-mix is ordered in quarter yards.
CONCRETE_ORDER_STEP_YD3: Final = Fraction(1, 4)

#: The waste allowance a new pour orders with (percent of its net volume).
DEFAULT_CONCRETE_WASTE_PERCENT: Final = 5

#: The highest allowance a pour may take (percent).
MAX_CONCRETE_WASTE_PERCENT: Final = 25

#: A pour orders ``ceil(yd3 x (1 + waste) / step - ORDER_SLACK)`` steps, so a
#: pour of exactly 7 yd³ by the kernel's measure orders 7, not 7.25 by an ulp.
ORDER_SLACK: Final = 1e-9

#: A rebar stick (in): 20 ft, lapped 24 in at each joint.
REBAR_STICK_IN: Final = 240
REBAR_LAP_IN: Final = 24

#: Anchor bolts (IRC R403.1.6): 12 in from each end, at most 72 in apart.
ANCHOR_BOLT_END_IN: Final = 12
ANCHOR_BOLT_SPACING_IN: Final = 72

#: The listed foundation items, by price-book key.
FoundationItemKey = Literal[
    "ready_mix",
    "rebar_4",
    "anchor_bolt_1_2",
    "foundation_vent",
    "crawl_access_door",
]

#: What an item is.
FoundationItemKind = Literal[
    "concrete", "rebar", "anchor_bolt", "foundation_vent", "access_door"
]

#: Items counted Each, by the piece: no length to list.
EACH_ITEMS: Final = frozenset({"anchor_bolt", "foundation_vent", "access_door"})

#: The library materials the items are made of (each a ``MaterialKey``;
#: spelt here so :mod:`loft_wire.materials` can serve this catalogue).
FoundationMaterialKey = Literal["concrete", "steel_a615", "steel_f1554", "steel_1018"]


class FoundationItem(BaseModel):
    """One listed foundation item: what it is priced and weighed as."""

    key: FoundationItemKey = Field(description="Price-book key, e.g. 'rebar_4'.")
    kind: FoundationItemKind
    name: str = Field(description="As listed, e.g. '#4 rebar'.")
    material: FoundationMaterialKey = Field(
        description="Library material the item is priced as."
    )
    price_unit: Literal["cubic_yard", "each"] = Field(
        description="How a price-book entry prices it: concrete per cubic "
        "yard ordered; a rebar stick, an anchor bolt, a foundation vent or "
        "an access door Each."
    )
    stock_length_ft: int | None = Field(
        default=None,
        description="The stock an Each price is for (ft): 20 for a rebar "
        "stick; null for a bolt or concrete.",
    )


#: The catalogue in display order.
FOUNDATION_ITEMS: tuple[FoundationItem, ...] = (
    FoundationItem(
        key="ready_mix",
        kind="concrete",
        name="Ready-mix concrete",
        material="concrete",
        price_unit="cubic_yard",
    ),
    FoundationItem(
        key="rebar_4",
        kind="rebar",
        name="#4 rebar",
        material="steel_a615",
        price_unit="each",
        stock_length_ft=REBAR_STICK_IN // 12,
    ),
    FoundationItem(
        key="anchor_bolt_1_2",
        kind="anchor_bolt",
        name="1/2 in anchor bolt",
        material="steel_f1554",
        price_unit="each",
    ),
    FoundationItem(
        key="foundation_vent",
        kind="foundation_vent",
        name="Foundation vent",
        material="steel_1018",
        price_unit="each",
    ),
    FoundationItem(
        key="crawl_access_door",
        kind="access_door",
        name="Crawl-space access door",
        material="steel_1018",
        price_unit="each",
    ),
)

#: Key -> item.
FOUNDATION_ITEMS_BY_KEY: Mapping[str, FoundationItem] = {
    item.key: item for item in FOUNDATION_ITEMS
}


def foundation_item_for(profile: str | None) -> FoundationItem | None:
    """The item a member's ``profile`` names, by key or name, or ``None``."""
    if profile is None:
        return None
    for item in FOUNDATION_ITEMS:
        if profile in (item.key, item.name):
            return item
    return None


# --- Member metadata ----------------------------------------------------------------


class ConcretePour(BaseModel):
    """Set on a concrete body (a pour): the cut list lists its MEASURED volume
    in cubic yards and orders it with this allowance."""

    item: Literal["ready_mix"] = "ready_mix"
    waste_percent: int = Field(
        default=DEFAULT_CONCRETE_WASTE_PERCENT,
        ge=0,
        le=MAX_CONCRETE_WASTE_PERCENT,
        description="Ordered over the net volume (percent), then rounded up "
        "to 1/4 yd³.",
    )


class RebarRun(BaseModel):
    """One bar a pour carries, listed not drawn: its centreline length."""

    item: Literal["rebar_4"] = "rebar_4"
    length_mm: float = Field(gt=0, description="Centreline length (mm).")
    closed: bool = Field(
        description="A closed loop (lapped where it closes) or an open run."
    )


#: The most plate pieces one pour lists bolts for.
MAX_BOLTED_PLATES: Final = 256


class AnchorBolts(BaseModel):
    """Set on a plate that bears on concrete: the cut list counts its bolts
    from the plate's measured length (:func:`anchor_bolt_count`). Set on a
    POUR instead (CRAWL-SPACE: a stem wall under a floor framed by another
    feature), it lists the bolts cast in for each plate piece *plates_mm*."""

    item: Literal["anchor_bolt_1_2"] = "anchor_bolt_1_2"
    plates_mm: list[Annotated[float, Field(gt=0)]] | None = Field(
        default=None,
        exclude_if=is_none,
        max_length=MAX_BOLTED_PLATES,
        description="On a pour: the length (mm) of each plate piece it bolts "
        "(the floor's sills on a stem wall), each counted by R403.1.6. Absent "
        "on a plate, whose bolts are counted from its measured length.",
    )

    def count(self, measured_length_in: float) -> int:
        """The bolts listed: for each of *plates_mm*, or for the plate
        *measured_length_in* long that carries them."""
        if self.plates_mm is None:
            return anchor_bolt_count(measured_length_in)
        return sum(anchor_bolt_count(mm / MM_PER_INCH) for mm in self.plates_mm)


#: The most opening sizes one pour lists, and the most of one size.
MAX_FOUNDATION_OPENINGS: Final = 16
MAX_OPENINGS_OF_A_SIZE: Final = 10_000

#: The largest opening a pour lists (mm): 10 ft either way.
MAX_OPENING_MM: Final = 3048.0


class FoundationOpening(BaseModel):
    """Set on a stem wall's pour (FOUNDATION-TAKEOFF): *quantity* units of
    one item and size set in the openings cut from it, a foundation vent or
    the crawl-space access door, listed Each by the cut list."""

    item: Literal["foundation_vent", "crawl_access_door"]
    width_mm: float = Field(gt=0, le=MAX_OPENING_MM, description="Along the wall (mm).")
    height_mm: float = Field(gt=0, le=MAX_OPENING_MM, description="Tall (mm).")
    quantity: int = Field(ge=1, le=MAX_OPENINGS_OF_A_SIZE)

    @property
    def size(self) -> str:
        """Its size as sold, width by height in inches: ``16 x 8``."""
        return " x ".join(
            f"{round(mm / MM_PER_INCH, 4):g}" for mm in (self.width_mm, self.height_mm)
        )


# --- The arithmetic -----------------------------------------------------------------


def volume_yd3(volume_mm3: float) -> float:
    """*volume_mm3* in cubic yards."""
    return volume_mm3 / (IN3_PER_YD3 * MM_PER_INCH**3)


def concrete_order_yd3(volume_mm3: float, waste_percent: int) -> Fraction:
    """The cubic yards ordered for ONE pour of net *volume_mm3*: plus the
    allowance, rounded UP to 1/4 yd³ (buildings.md B8: 6.62 yd³ net, x 1.05 =
    6.95, orders 7). Each pour is its own delivery (FOUNDATION-TAKEOFF), so
    pours are rounded one by one, never on their sum."""
    wanted = volume_yd3(volume_mm3) * (100 + waste_percent) / 100
    steps = math.ceil(wanted / CONCRETE_ORDER_STEP_YD3 - ORDER_SLACK)
    return max(steps, 0) * CONCRETE_ORDER_STEP_YD3


def rebar_sticks(length_in: float, closed: bool) -> int:
    """The 20 ft sticks a bar of *length_in* takes, lapped 24 in at each
    joint: a closed loop ``ceil(L / 216)`` (every stick adds 18 ft, the loop's
    own closing lap included), an open run one stick to 240 in and one more
    per 216 beyond."""
    reach = REBAR_STICK_IN - REBAR_LAP_IN
    if closed:
        return max(1, math.ceil(length_in / reach - ORDER_SLACK))
    if length_in <= REBAR_STICK_IN + ORDER_SLACK:
        return 1
    return 1 + math.ceil((length_in - REBAR_STICK_IN) / reach - ORDER_SLACK)


def anchor_bolt_count(plate_length_in: float) -> int:
    """IRC R403.1.6's bolts in one plate piece: one 12 in from each end, the
    rest equally spaced at most 72 in, at least 2:
    ``max(2, ceil((L - 24) / 72) + 1)`` (B8: 125 takes 3, 181 4, 288 5)."""
    between = plate_length_in - 2 * ANCHOR_BOLT_END_IN
    if between <= 0:
        return 2
    return max(2, math.ceil(between / ANCHOR_BOLT_SPACING_IN - ORDER_SLACK) + 1)
