"""Window and door units: the US size catalogue (OPENING-UNITS, RESEARCH §23).

A window or door is bought as a UNIT and picked by its call size, as Chief
Architect's and Revit's window and door families are typed: four digits, feet
and inches of the width, then of the height. ``3040`` is a 3'0" x 4'0" window
and ``3068`` a 3'0" x 6'8" door. The width and height come from the code;
nothing else is typed.

**What the size names.** For a window, the unit itself (its frame's outside):
a 3040 is 36 x 48 in. For a door, the SLAB a prehung unit is hung with: a
3068 is a 36 x 80 in slab. Makers differ (some call a window by its rough
opening), so a maker's line states its own sizes and rough openings.

**Rough openings** follow standard framing practice (RESEARCH §23): a window's
is the unit plus 1/2 in each way, a door's the slab plus 2 in wide and 2-1/2 in
tall (room for the jambs, shims and threshold). They are what ``loft.window``
and ``loft.door`` have framed since 1.0.0 (B2's 24.5 x 36.5 and 38 x 82.5).

**Pricing.** A unit is one cut-list line, priced Each by its key
(``window_3040``, ``door_3068``) and its frame's material, beside the lumber
keys in the price book (:mod:`loft_wire.price_book`). The key is
``<kind>_<code>``, so it is a valid plugin choice value as the lumber and sheet
keys are.

Inches are the source of truth (exact binary fractions); millimetres are
derived at x 25.4 exactly.
"""

from collections.abc import Mapping
from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field, StringConstraints

from loft_wire.lumber import MM_PER_INCH

#: What a unit is.
OpeningKind = Literal["window", "door"]

#: A call size: feet and inches of the width, then of the height ("3068").
UNIT_CODE_PATTERN: Final = r"^[0-9]{4}$"

#: A unit's price-book key: ``window_3040``, ``door_3068``.
UNIT_KEY_PATTERN: Final = r"^(window|door)_[0-9]{4}$"

UnitCode = Annotated[str, StringConstraints(pattern=UNIT_CODE_PATTERN)]
OpeningUnitKey = Annotated[str, StringConstraints(pattern=UNIT_KEY_PATTERN)]

#: The library materials a unit's frame is made of (each a ``MaterialKey``;
#: spelt here so :mod:`loft_wire.materials` can serve this catalogue).
UnitMaterialKey = Literal["pvc", "spf_lumber"]

#: Rough opening less unit, in inches (width, height): a window's 1/2 in
#: each way, a door's 2 in and 2-1/2 in over its slab.
RO_ALLOWANCE_IN: Final[Mapping[OpeningKind, tuple[float, float]]] = {
    "window": (0.5, 0.5),
    "door": (2.0, 2.5),
}

#: The frame material a built-in unit is priced and weighed as: a vinyl
#: window, a wood-jambed door.
UNIT_MATERIAL: Final[Mapping[OpeningKind, UnitMaterialKey]] = {
    "window": "pvc",
    "door": "spf_lumber",
}


class OpeningUnitSize(BaseModel):
    """One catalogue size: its code, the unit (or slab) it names, and the
    rough opening it is framed in."""

    key: OpeningUnitKey = Field(description="Price-book key, e.g. 'window_3040'.")
    kind: OpeningKind
    code: UnitCode = Field(description="Call size, e.g. '3040'.")
    name: str = Field(description="As listed, e.g. 'Window 3040'.")
    label: str = Field(description="Its size as written, e.g. 3'0\" x 4'0\".")
    width_in: float = Field(
        gt=0, description="The unit's width (in); a door's, its slab's."
    )
    height_in: float = Field(
        gt=0, description="The unit's height (in); a door's, its slab's."
    )
    ro_width_in: float = Field(gt=0, description="Rough opening width (in).")
    ro_height_in: float = Field(gt=0, description="Rough opening height (in).")
    material: UnitMaterialKey = Field(
        description="The frame's library material: what the unit is priced "
        "and weighed as."
    )

    @property
    def width_mm(self) -> float:
        return self.width_in * MM_PER_INCH

    @property
    def height_mm(self) -> float:
        return self.height_in * MM_PER_INCH


def code_size_in(code: str) -> tuple[int, int]:
    """The width and height (in) a call size names: ``3068`` is 3'0" x 6'8",
    36 x 80."""
    a, b, c, d = (int(ch) for ch in code)
    return 12 * a + b, 12 * c + d


def unit_key(kind: OpeningKind, code: str) -> str:
    """``window_3040``."""
    return f"{kind}_{code}"


def _feet_inches(inches: int) -> str:
    return f"{inches // 12}'{inches % 12}\""


def _size(kind: OpeningKind, code: str) -> OpeningUnitSize:
    width, height = code_size_in(code)
    dw, dh = RO_ALLOWANCE_IN[kind]
    return OpeningUnitSize(
        key=unit_key(kind, code),
        kind=kind,
        code=code,
        name=f"{kind.capitalize()} {code}",
        label=f"{_feet_inches(width)} x {_feet_inches(height)}",
        width_in=float(width),
        height_in=float(height),
        ro_width_in=width + dw,
        ro_height_in=height + dh,
        material=UNIT_MATERIAL[kind],
    )


#: The built-in US windows: single-hung and slider call sizes stocked by US
#: yards, 2'0" to 6'0" wide.
WINDOW_CODES: Final[tuple[str, ...]] = (
    "2020",
    "2030",
    "2040",
    "2050",
    "2060",
    "2630",
    "2640",
    "2650",
    "2660",
    "3020",
    "3030",
    "3040",
    "3050",
    "3060",
    "4030",
    "4040",
    "4050",
    "5030",
    "5040",
    "6030",
    "6040",
)

#: The built-in US doors: 6'8" slabs 2'0" to 3'0" wide, and a 3'0" x 8'0".
DOOR_CODES: Final[tuple[str, ...]] = ("2068", "2468", "2668", "2868", "3068", "3080")

#: The built-in catalogue in display order: windows, then doors.
OPENING_UNITS: tuple[OpeningUnitSize, ...] = tuple(
    [_size("window", c) for c in WINDOW_CODES] + [_size("door", c) for c in DOOR_CODES]
)

#: Key -> size.
OPENING_UNITS_BY_KEY: Mapping[str, OpeningUnitSize] = {u.key: u for u in OPENING_UNITS}


def catalogue(kind: OpeningKind) -> dict[str, OpeningUnitSize]:
    """The built-in sizes of one kind, by code, in display order."""
    return {u.code: u for u in OPENING_UNITS if u.kind == kind}


class OpeningUnitPart(BaseModel):
    """A member that is part of a bought unit (``MemberMetadata.unit``): the
    cut list lists the unit once, as an Each line, on its ``counted`` body
    (the frame), and skips its other bodies (glazing, a door's slab)."""

    kind: OpeningKind
    key: OpeningUnitKey | None = Field(
        default=None,
        description="Price-book key ('window_3040'); null for a custom size, "
        "which no catalogue prices.",
    )
    counted: bool = Field(
        description="True on the one body the unit is listed and priced on."
    )
