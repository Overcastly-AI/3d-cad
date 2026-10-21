"""Price book: what the user pays for lumber (PRICE-BOOK, RESEARCH §27).

Chief Architect's Master List feeds its materials list a price per item, and
SolidWorks' Cost property feeds a BOM column; Loft's price book does the same
for the cut list. One book per user (no workspaces yet), stored by documents
(``price_books``, ``price_book_entries``) and read and written whole through
the gateway (``GET``/``PUT /api/v1/price-book``).

Each entry prices one material and lumber profile in one unit:

* ``each``: one stock piece of ``stock_length_ft`` ("SPF 2x4 x 8 ft = $3.98");
* ``linear_foot``: per foot of stock, for any stock length;
* ``board_foot``: per board foot (nominal thickness x nominal width (in) x
  stock length (ft) / 12; a 2x4 x 8 is 5.333 BF), for any stock length.

Money is integer cents, never a float: the wire carries ``price_cents`` as a
JSON integer (a ``398.0`` or ``"398"`` is refused), and Python prices with
ints. USD only for now; the ISO code is stored so a later currency is a value,
not a migration. Pricing a cut list is :func:`loft_wire.cut_list.price_lines`.
"""

from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loft_wire.lumber import STOCK_LENGTHS_FT, LumberProfileKey
from loft_wire.materials import MaterialKey

#: The currencies a book may be kept in (ISO 4217). USD only for now.
Currency = Literal["USD"]

#: The unit an entry's price is per.
PriceUnit = Literal["each", "linear_foot", "board_foot"]

#: Most entries one book holds (a lumber yard's dimensional list is ~200).
MAX_PRICE_BOOK_ENTRIES: Final = 500

#: Highest price of one entry, in cents ($100,000.00): far above any stock
#: piece of lumber, and low enough that 500 lines of any assembly's
#: quantities stay exact in a JavaScript number.
MAX_PRICE_CENTS: Final = 10_000_000

#: An entry's identity: one price per (material, profile, unit, stock length).
PriceKey = tuple[str, str, str, int | None]


class PriceBookEntry(BaseModel):
    """One price: a material and profile, per stock piece, foot or board foot."""

    model_config = ConfigDict(extra="forbid")

    material: MaterialKey = Field(description="Library material, e.g. 'spf_lumber'.")
    profile: LumberProfileKey = Field(description="Lumber profile, e.g. 'us_2x4'.")
    unit: PriceUnit = Field(
        description="'each' (one stock piece of `stock_length_ft`), "
        "'linear_foot' or 'board_foot' (any stock length)."
    )
    stock_length_ft: int | None = Field(
        default=None,
        description="The stock length an 'each' price is for (ft); null for "
        "a per-foot or per-board-foot price.",
    )
    price_cents: int = Field(
        strict=True,
        ge=0,
        le=MAX_PRICE_CENTS,
        description="Price in the book's currency's minor unit (cents), as an "
        "integer: 398 is $3.98.",
    )

    @model_validator(mode="after")
    def _stock_length_matches_unit(self) -> "PriceBookEntry":
        if self.unit == "each":
            if self.stock_length_ft not in STOCK_LENGTHS_FT:
                raise ValueError(
                    "An 'each' price needs a stock length of "
                    f"{', '.join(str(n) for n in STOCK_LENGTHS_FT)} ft."
                )
        elif self.stock_length_ft is not None:
            raise ValueError(
                "Only an 'each' price has a stock length; a per-foot or "
                "per-board-foot price applies to every stock length."
            )
        return self

    @property
    def key(self) -> PriceKey:
        return (self.material, self.profile, self.unit, self.stock_length_ft)


class PriceBookUpdate(BaseModel):
    """``PUT /api/v1/price-book``: the whole book, replacing the stored one."""

    model_config = ConfigDict(extra="forbid")

    currency: Currency = Field(default="USD", description="ISO 4217 code.")
    entries: list[PriceBookEntry] = Field(
        default_factory=list[PriceBookEntry],
        max_length=MAX_PRICE_BOOK_ENTRIES,
        description="Every entry, in the user's order; one per material, "
        "profile, unit and stock length.",
    )

    @model_validator(mode="after")
    def _one_price_per_key(self) -> "PriceBookUpdate":
        seen: set[PriceKey] = set()
        for index, entry in enumerate(self.entries):
            if entry.key in seen:
                raise ValueError(
                    f"Entry {index + 1} repeats an earlier entry's material, "
                    "profile, unit and stock length; a book holds one price "
                    "for each."
                )
            seen.add(entry.key)
        return self


class PriceBookResponse(BaseModel):
    """The caller's price book. A user who never saved one has an empty USD
    book (``updated_at`` null)."""

    currency: Currency
    entries: list[PriceBookEntry] = Field(default_factory=list[PriceBookEntry])
    updated_at: datetime | None = Field(
        default=None, description="When the book was last saved; null if never."
    )


#: The book of a user who never saved one.
EMPTY_PRICE_BOOK: Final = PriceBookResponse(currency="USD")
