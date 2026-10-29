"""US dimensional lumber: nominal name, actual dressed size (LUMBER-MATERIALS).

The profile library the building plugins (RESEARCH §23) cut members from, as a
SolidWorks weldment draws members from a profile library. Lumber is sold by
its NOMINAL size and built at its ACTUAL size: a "2x4" is 1.5 x 3.5 in. Using
the nominal size would put every joist 1/2 in too wide and every mass about a
third too heavy, so the actual size is the only one geometry ever sees.

Actual sizes are the minimum dressed sizes of the American Softwood Lumber
Standard, DOC PS 20-20 (ALSC): dry (19 % moisture or less) for boards,
decking and dimension lumber up to 4 in nominal thick, and green for timbers
5 in nominal and thicker (a 6x6 is 5.5 x 5.5 in; PS 20 publishes no dry size
for timbers). Inches are the source of truth (every value below is an exact
binary fraction); millimetres are derived once, at x 25.4 exactly.

US sizes first; metric CLS and European sizes come later as further keys
(founder, 2026-10-15). A key is ``us_<nominal>`` with ``/`` spelt ``_``, so
it is a valid plugin choice value (``loft_wire.plugins.InputName``).
"""

from collections.abc import Mapping
from typing import Final, Literal

from pydantic import BaseModel, Field

#: Millimetres per inch, exactly (international inch, 1959).
MM_PER_INCH: Final = 25.4

#: Standard US lumber stock lengths (ft), shortest first: what the cut list
#: suggests and what an 'each' price may be for. Grading rules sell lumber
#: in 2 ft multiples (WWPA, SPIB), and US yards stock dimension lumber to
#: 24 ft for joists and rafters; boards, decking and timbers to 20 ft
#: (:func:`stock_lengths_ft`, RESEARCH §27).
STOCK_LENGTHS_FT: Final[tuple[int, ...]] = (8, 10, 12, 14, 16, 18, 20, 22, 24)

#: The stock lengths every US yard carries (ft): 18 ft is stocked less
#: widely, and 22 and 24 ft are dimension lumber only, not stocked everywhere.
COMMON_STOCK_LENGTHS_FT: Final[tuple[int, ...]] = (8, 10, 12, 14, 16, 20)

#: The longest of :data:`COMMON_STOCK_LENGTHS_FT`.
COMMON_MAX_STOCK_FT: Final = 20

#: The built-in profile keys. A closed literal, like ``MaterialKey``: an
#: unknown profile is a parse error at the boundary.
LumberProfileKey = Literal[
    "us_1x2",
    "us_1x4",
    "us_1x6",
    "us_1x8",
    "us_5_4x6",
    "us_2x2",
    "us_2x3",
    "us_2x4",
    "us_2x6",
    "us_2x8",
    "us_2x10",
    "us_2x12",
    "us_4x4",
    "us_4x6",
    "us_6x6",
    "us_6x8",
    "us_8x8",
    "us_8x10",
    "us_8x12",
    "us_10x10",
    "us_10x12",
    "us_12x12",
]

#: PS 20 product class: what the size rule is.
LumberCategory = Literal["board", "decking", "dimension", "timber"]


class LumberProfile(BaseModel):
    """One lumber section: nominal name and actual dressed size.

    ``thickness`` is the smaller dimension and ``width`` the larger (equal for
    a square post), as the trade names them: "2x10" is 2 nominal thick by 10
    nominal wide, 1.5 x 9.25 in actual.
    """

    key: LumberProfileKey
    name: str = Field(description="Nominal size as sold, e.g. '2x10' or '5/4x6'.")
    category: LumberCategory = Field(
        description="PS 20 class: board, decking, dimension (2-4 in thick) or "
        "timber (5 in and thicker)."
    )
    thickness_in: float = Field(gt=0, description="Actual thickness (in).")
    width_in: float = Field(gt=0, description="Actual width (in).")
    thickness_mm: float = Field(gt=0, description="Actual thickness (mm).")
    width_mm: float = Field(gt=0, description="Actual width (mm).")
    source: str = Field(description="Standard the actual size comes from.")


_DRY = "DOC PS 20-20 minimum dressed size, dry"
_GREEN = "DOC PS 20-20 minimum dressed size, green (timbers)"


def _profile(
    key: LumberProfileKey,
    name: str,
    category: LumberCategory,
    thickness_in: float,
    width_in: float,
) -> LumberProfile:
    return LumberProfile(
        key=key,
        name=name,
        category=category,
        thickness_in=thickness_in,
        width_in=width_in,
        thickness_mm=thickness_in * MM_PER_INCH,
        width_mm=width_in * MM_PER_INCH,
        source=_GREEN if category == "timber" else _DRY,
    )


#: The library in display order: boards, decking, dimension, timbers.
LUMBER_PROFILES: tuple[LumberProfile, ...] = (
    _profile("us_1x2", "1x2", "board", 0.75, 1.5),
    _profile("us_1x4", "1x4", "board", 0.75, 3.5),
    _profile("us_1x6", "1x6", "board", 0.75, 5.5),
    # A closed stair's riser boards (STAIRS), ripped to the riser.
    _profile("us_1x8", "1x8", "board", 0.75, 7.25),
    _profile("us_5_4x6", "5/4x6", "decking", 1.0, 5.5),
    _profile("us_2x2", "2x2", "dimension", 1.5, 1.5),
    _profile("us_2x3", "2x3", "dimension", 1.5, 2.5),
    _profile("us_2x4", "2x4", "dimension", 1.5, 3.5),
    _profile("us_2x6", "2x6", "dimension", 1.5, 5.5),
    _profile("us_2x8", "2x8", "dimension", 1.5, 7.25),
    _profile("us_2x10", "2x10", "dimension", 1.5, 9.25),
    _profile("us_2x12", "2x12", "dimension", 1.5, 11.25),
    _profile("us_4x4", "4x4", "dimension", 3.5, 3.5),
    _profile("us_4x6", "4x6", "dimension", 3.5, 5.5),
    _profile("us_6x6", "6x6", "timber", 5.5, 5.5),
    # S4S timbers for timber framing (TIMBER-FRAME): green, 1/2 in under
    # nominal on each face (PS 20-20 Table 3, 5 in and thicker).
    _profile("us_6x8", "6x8", "timber", 5.5, 7.5),
    _profile("us_8x8", "8x8", "timber", 7.5, 7.5),
    _profile("us_8x10", "8x10", "timber", 7.5, 9.5),
    _profile("us_8x12", "8x12", "timber", 7.5, 11.5),
    _profile("us_10x10", "10x10", "timber", 9.5, 9.5),
    _profile("us_10x12", "10x12", "timber", 9.5, 11.5),
    _profile("us_12x12", "12x12", "timber", 11.5, 11.5),
)

#: Key -> profile.
LUMBER_PROFILES_BY_KEY: Mapping[LumberProfileKey, LumberProfile] = {
    p.key: p for p in LUMBER_PROFILES
}


def lumber_profile(key: LumberProfileKey) -> LumberProfile:
    """The profile for *key* (a ``KeyError`` for a key outside the literal)."""
    return LUMBER_PROFILES_BY_KEY[key]


def stock_lengths_ft(profile: LumberProfile | None) -> tuple[int, ...]:
    """The stock lengths (ft) *profile* is sold in, shortest first: every
    :data:`STOCK_LENGTHS_FT` for dimension lumber (2 to 4 in thick, to
    24 ft), else to :data:`COMMON_MAX_STOCK_FT` (boards, decking, timbers,
    or a profile not in the library)."""
    if profile is not None and profile.category == "dimension":
        return STOCK_LENGTHS_FT
    return tuple(ft for ft in STOCK_LENGTHS_FT if ft <= COMMON_MAX_STOCK_FT)
