"""Casework items: edge banding and cabinet hardware (CASEWORK, RESEARCH §23).

A cabinet's panels are sheet goods (:mod:`loft_wire.sheet_goods`), cut and
counted as sheathing is. What a shop also buys for a cabinet is not a body:
the EDGE BANDING glued on its exposed edges, by the foot, and its HARDWARE,
by the piece, as Mozaik's and Cabinet Vision's material lists carry them.
A ``loft.cabinets`` member states both in its metadata
(:class:`EdgeBanding`, :class:`HardwareCount`), and the cut list sums them
into lines under Casework, priced from the book by the item key here.

* ``edge_banding``: 7/8 in banding for 3/4 panels, per linear foot, in the
  panel's material: wood veneer on plywood (``plywood``) or PVC on melamine
  (``pvc``). The cut list buys whole feet.
* ``hinge``: a concealed (European, 35 mm cup) hinge, Each. The count per
  door is Blum's by door height (the plugin's rule).
* ``slide_<n>``: one PAIR of side-mount drawer slides ``n`` in long (12 to
  24 in, 2 in steps), Each pair.

A key is lowercase with underscores, so it is a valid plugin choice value
and a price-book profile beside the lumber, sheet and unit keys.
"""

from collections.abc import Mapping, Sequence
from typing import Final, Literal

from pydantic import BaseModel, Field

#: A direction in world coordinates.
Vec3 = tuple[float, float, float]

#: Drawer slide lengths sold (in), shortest first.
SLIDE_LENGTHS_IN: Final[tuple[int, ...]] = (12, 14, 16, 18, 20, 22, 24)

#: The casework item keys. A closed literal, like ``SheetGoodKey``.
CaseworkItemKey = Literal[
    "edge_banding",
    "hinge",
    "slide_12",
    "slide_14",
    "slide_16",
    "slide_18",
    "slide_20",
    "slide_22",
    "slide_24",
]

#: The keys a member's hardware may name (not the banding).
HardwareKey = Literal[
    "hinge",
    "slide_12",
    "slide_14",
    "slide_16",
    "slide_18",
    "slide_20",
    "slide_22",
    "slide_24",
]

#: What an item is.
CaseworkItemKind = Literal["banding", "hinge", "slide"]

#: The materials banding is sold in: wood veneer matched to plywood, PVC for
#: melamine.
BandingMaterialKey = Literal["plywood", "pvc"]

#: The library materials casework items are listed in (each a ``MaterialKey``;
#: spelt here so :mod:`loft_wire.materials` can serve this catalogue).
CaseworkMaterialKey = Literal["plywood", "pvc", "steel_1018"]

#: The material hardware is priced and listed as.
HARDWARE_MATERIAL: Final[CaseworkMaterialKey] = "steel_1018"


class CaseworkItem(BaseModel):
    """One item a cabinet buys that is not a panel: banding or hardware."""

    key: CaseworkItemKey
    kind: CaseworkItemKind
    name: str = Field(description="As listed, e.g. 'Drawer slides 22 in, pair'.")
    unit: Literal["each", "linear_foot"] = Field(
        description="How it is priced: banding per linear foot, hardware Each."
    )
    materials: list[CaseworkMaterialKey] = Field(
        description="The materials it is listed and priced in."
    )


def _slide(length: int) -> CaseworkItem:
    return CaseworkItem(
        key=f"slide_{length}",  # pyright: ignore[reportArgumentType]
        kind="slide",
        name=f"Drawer slides {length} in, pair",
        unit="each",
        materials=[HARDWARE_MATERIAL],
    )


#: Every item in display order.
CASEWORK_ITEMS: tuple[CaseworkItem, ...] = (
    CaseworkItem(
        key="edge_banding",
        kind="banding",
        name="Edge banding 7/8 in",
        unit="linear_foot",
        materials=["plywood", "pvc"],
    ),
    CaseworkItem(
        key="hinge",
        kind="hinge",
        name="Concealed hinge",
        unit="each",
        materials=[HARDWARE_MATERIAL],
    ),
    *(_slide(length) for length in SLIDE_LENGTHS_IN),
)

#: Key -> item.
CASEWORK_ITEMS_BY_KEY: Mapping[str, CaseworkItem] = {i.key: i for i in CASEWORK_ITEMS}


def slide_key(length_in: int) -> HardwareKey:
    """``slide_22`` for a 22 in pair; *length_in* must be a sold length."""
    if length_in not in SLIDE_LENGTHS_IN:
        raise ValueError(f"no {length_in} in slide is sold")
    return f"slide_{length_in}"  # pyright: ignore[reportReturnType]


class EdgeBanding(BaseModel):
    """The banding one panel carries: its banded edges' total length and the
    banding's material."""

    length_mm: float = Field(gt=0, allow_inf_nan=False, le=1e6)
    material: BandingMaterialKey


class HardwareCount(BaseModel):
    """Hardware one member carries: a door's hinges, a drawer's slide pair."""

    key: HardwareKey
    quantity: int = Field(ge=1, le=100)


def grain_face(
    extents: tuple[float, float, float],
    axes: tuple[Vec3, Vec3, Vec3] | None,
    grain: Sequence[float],
) -> tuple[float, float]:
    """A grained panel's face as ``(along its grain, across it)`` (mm): of
    its two face extents (*extents* longest first, the thinnest through it),
    the one whose measured axis is more nearly the *grain* direction. With
    no axes (an older geometry service), or a tie, the longer side is taken
    as along the grain."""
    long, short = extents[0], extents[1]
    if axes is None:
        return long, short
    first, second = (
        abs(sum(a * g for a, g in zip(axis, grain, strict=True))) for axis in axes[:2]
    )
    if abs(first - second) <= 1e-6:
        return long, short
    return (long, short) if first > second else (short, long)
