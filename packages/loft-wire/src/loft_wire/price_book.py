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

Sheet goods (SHEATHING) are priced ``each`` per SHEET: a product such as
``osb_7_16`` keyed by its ``sheet`` size ("7/16 OSB 4x9 = $24.98"), with no
stock length, as Chief Architect prices a sheet in its materials list.

The book has a ``version`` (PRICE-BOOK-VERSION): 0 until the first save, then
one more on every save. ``GET`` serves it in the body and as the ``ETag``;
a ``PUT`` names the version it was drafted from in ``If-Match`` and is refused
with 412 (:data:`PRICE_BOOK_STALE`) when the book has been saved since, so a
save never overwrites one it did not read (RESEARCH §27).

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
from loft_wire.sheet_goods import (
    SHEET_GOODS_BY_KEY,
    SheetGoodKey,
    SheetSizeKey,
)

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

#: An entry's identity: one price per (material, profile, unit, stock
#: length, sheet).
PriceKey = tuple[str, str, str, int | None, str | None]

#: The error code of a ``PUT`` drafted from a book saved since (412).
PRICE_BOOK_STALE: Final = "price_book_stale"

#: The error code of a ``PUT`` with no ``If-Match`` (428).
PRICE_BOOK_VERSION_REQUIRED: Final = "price_book_version_required"


def price_book_etag(version: int) -> str:
    """The strong ``ETag`` of a book at *version*: the version, quoted."""
    return f'"{version}"'


def parse_if_match(value: str) -> int | None:
    """The version an ``If-Match`` names (``"3"``, or a bare ``3``), or
    ``None`` when it names none (``*`` is not accepted: a save names the book
    it read)."""
    text = value.strip()
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        text = text[1:-1]
    if not text.isascii() or not text.isdigit() or len(text) > 18:
        return None
    return int(text)


class PriceBookEntry(BaseModel):
    """One price: a material and profile, per stock piece, foot or board foot."""

    model_config = ConfigDict(extra="forbid")

    material: MaterialKey = Field(description="Library material, e.g. 'spf_lumber'.")
    profile: LumberProfileKey | SheetGoodKey = Field(
        description="Lumber profile, e.g. 'us_2x4', or sheet product, e.g. 'osb_7_16'."
    )
    unit: PriceUnit = Field(
        description="'each' (one stock piece of `stock_length_ft`, or one "
        "sheet of `sheet`), 'linear_foot' or 'board_foot' (any stock length; "
        "lumber only)."
    )
    stock_length_ft: int | None = Field(
        default=None,
        description="The stock length a lumber 'each' price is for (ft); null "
        "for a sheet or a per-foot or per-board-foot price.",
    )
    sheet: SheetSizeKey | None = Field(
        default=None,
        description="The sheet a sheet product's 'each' price is for "
        "('4x8', '4x9', '4x10'); null for lumber.",
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
        if self.profile in SHEET_GOODS_BY_KEY:
            if self.unit != "each" or self.sheet is None:
                raise ValueError(
                    "A sheet product is priced 'each' per sheet: name its "
                    "sheet (4x8, 4x9 or 4x10)."
                )
            if self.stock_length_ft is not None:
                raise ValueError("A sheet price has a sheet size, not a stock length.")
            return self
        if self.sheet is not None:
            raise ValueError("Only a sheet product's price has a sheet size.")
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
        return (
            self.material,
            self.profile,
            self.unit,
            self.stock_length_ft,
            self.sheet,
        )


class PriceBookUpdate(BaseModel):
    """``PUT /api/v1/price-book``: the whole book, replacing the stored one."""

    model_config = ConfigDict(extra="forbid")

    currency: Currency = Field(default="USD", description="ISO 4217 code.")
    entries: list[PriceBookEntry] = Field(
        default_factory=list[PriceBookEntry],
        max_length=MAX_PRICE_BOOK_ENTRIES,
        description="Every entry, in the user's order; one per material, "
        "profile, unit and stock length or sheet.",
    )

    @model_validator(mode="after")
    def _one_price_per_key(self) -> "PriceBookUpdate":
        seen: set[PriceKey] = set()
        for index, entry in enumerate(self.entries):
            if entry.key in seen:
                raise ValueError(
                    f"Entry {index + 1} repeats an earlier entry's material, "
                    "profile, unit and stock length or sheet; a book holds one "
                    "price for each."
                )
            seen.add(entry.key)
        return self


class PriceBookResponse(BaseModel):
    """The caller's price book. A user who never saved one has an empty USD
    book (``updated_at`` null, ``version`` 0)."""

    currency: Currency
    entries: list[PriceBookEntry] = Field(default_factory=list[PriceBookEntry])
    updated_at: datetime | None = Field(
        default=None, description="When the book was last saved; null if never."
    )
    version: int = Field(
        default=0,
        ge=0,
        description="0 until the first save, then one more per save. Send it "
        "back as `If-Match` on the `PUT` (also served as the `ETag`).",
    )


#: The book of a user who never saved one.
EMPTY_PRICE_BOOK: Final = PriceBookResponse(currency="USD")


class PriceBookVersionDetails(BaseModel):
    """A 412's ``details``: the version the book is at now."""

    version: int = Field(ge=0, description="The stored book's version now.")


class PriceBookVersionError(BaseModel):
    """The ``error`` member of a price-book 412 or 428 (the py-kit envelope,
    with typed ``details``)."""

    code: str = Field(
        description="'price_book_stale' (412) or 'price_book_version_required' "
        "(428): the machine code a client branches on."
    )
    message: str
    details: PriceBookVersionDetails | None = Field(
        default=None, description="The book's version now (412); null on a 428."
    )
    request_id: str | None = None


class PriceBookVersionEnvelope(BaseModel):
    """A refused save as it appears on the wire (the standard envelope)."""

    error: PriceBookVersionError
