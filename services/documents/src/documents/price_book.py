"""``/api/v1/price-book``: the caller's price book (PRICE-BOOK).

One book per user (:mod:`loft_wire.price_book`), read and replaced whole, as
Chief Architect's Master List is one list. Trust model and owner scoping are
:mod:`documents.parts`': the gateway forwards the verified user id and every
query here filters on it, so there is no id in the path and no way to name
another user's book.

A user who never saved a book reads an empty USD book at version 0; nothing
is written until the first ``PUT``. A ``PUT`` replaces every entry in one
transaction, with the book row locked (Postgres) so two saves serialize.

PRICE-BOOK-VERSION: every save adds one to the book's ``version``, served as
the ``ETag``. A ``PUT`` must name the version it was drafted from in
``If-Match`` (428 without one); a book saved since is refused with 412
``price_book_stale`` and left exactly as it is. Of two saves drafted from
one version the second is refused, never merged and never silently lost:
the check runs under the row lock, and two first saves race on the owner
unique.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, Response
from loft_wire.price_book import (
    EMPTY_PRICE_BOOK,
    PRICE_BOOK_STALE,
    PRICE_BOOK_VERSION_REQUIRED,
    PriceBookEntry,
    PriceBookResponse,
    PriceBookUpdate,
    parse_if_match,
    price_book_etag,
)
from py_kit import get_logger
from py_kit.db import SessionDep
from py_kit.errors import ApiError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from documents.db import PriceBook, PriceBookEntryRow
from documents.parts import Principal

_logger = get_logger("documents.price_book")

router = APIRouter(prefix="/api/v1/price-book", tags=["price-book"])


class StalePriceBookError(ApiError):
    """The book was saved since the ``If-Match`` version was read (412)."""

    status_code = 412
    code = PRICE_BOOK_STALE


class PriceBookVersionRequiredError(ApiError):
    """A ``PUT`` named no version to check against (428, RFC 6585)."""

    status_code = 428
    code = PRICE_BOOK_VERSION_REQUIRED


#: ``If-Match``: the version the saved book was drafted from (its ``ETag``).
IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        max_length=64,
        description='The book\'s version as read (its ETag, e.g. "3"; "0" '
        "for a book never saved). Required: a save drafted from an older "
        "version is refused with 412.",
    ),
]


async def _owned_book(
    session: AsyncSession, owner_id: uuid.UUID, *, for_update: bool = False
) -> PriceBook | None:
    statement = select(PriceBook).where(PriceBook.owner_id == owner_id)
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def _response(session: AsyncSession, book: PriceBook) -> PriceBookResponse:
    rows = (
        await session.execute(
            select(PriceBookEntryRow)
            .where(PriceBookEntryRow.price_book_id == book.id)
            .order_by(PriceBookEntryRow.order_index)
        )
    ).scalars()
    entries = [
        PriceBookEntry.model_validate(
            {
                "material": row.material,
                "profile": row.profile,
                "unit": row.unit,
                "stock_length_ft": row.stock_length_ft,
                "sheet": row.sheet,
                "price_cents": row.price_cents,
            }
        )
        for row in rows
    ]
    return PriceBookResponse.model_validate(
        {
            "currency": book.currency,
            "entries": entries,
            "updated_at": book.updated_at,
            "version": book.version,
        }
    )


def _stale(current: int) -> StalePriceBookError:
    return StalePriceBookError(
        "The price book was saved elsewhere since you opened it. Reload it, "
        "then make your changes again.",
        details={"version": current},
        headers={"ETag": price_book_etag(current)},
    )


@router.get("")
async def get_price_book(
    owner_id: Principal, session: SessionDep, response: Response
) -> PriceBookResponse:
    """The caller's price book; an empty USD book (version 0) if they never
    saved one. The ``ETag`` is its version."""
    book = await _owned_book(session, owner_id)
    result = EMPTY_PRICE_BOOK if book is None else await _response(session, book)
    response.headers["ETag"] = price_book_etag(result.version)
    return result


@router.put("")
async def put_price_book(
    request: PriceBookUpdate,
    owner_id: Principal,
    session: SessionDep,
    response: Response,
    if_match: IfMatch = None,
) -> PriceBookResponse:
    """Replace the caller's whole price book (at most 500 entries, one price
    per material, profile, unit and stock length or sheet, integer cents),
    if it is still at the ``If-Match`` version (else 412)."""
    if if_match is None:
        raise PriceBookVersionRequiredError(
            "Name the price book version you are saving over in If-Match."
        )
    expected = parse_if_match(if_match)
    book = await _owned_book(session, owner_id, for_update=True)
    current = 0 if book is None else book.version
    if expected != current:
        raise _stale(current)
    if book is None:
        book = PriceBook(owner_id=owner_id, currency=request.currency, version=1)
        session.add(book)
        try:
            await session.flush()
        except IntegrityError:
            # A concurrent first save created it: this one was drafted from
            # the empty book, so it is stale.
            await session.rollback()
            theirs = await _owned_book(session, owner_id)
            raise _stale(1 if theirs is None else theirs.version) from None
    else:
        book.version = current + 1
    book.currency = request.currency
    book.updated_at = datetime.now(UTC)
    await session.execute(
        delete(PriceBookEntryRow).where(PriceBookEntryRow.price_book_id == book.id)
    )
    session.add_all(
        PriceBookEntryRow(
            price_book_id=book.id,
            order_index=index,
            material=entry.material,
            profile=entry.profile,
            unit=entry.unit,
            stock_length_ft=entry.stock_length_ft,
            sheet=entry.sheet,
            price_cents=entry.price_cents,
        )
        for index, entry in enumerate(request.entries)
    )
    await session.commit()
    _logger.info(
        "price_book_saved",
        owner_id=str(owner_id),
        entries=len(request.entries),
        version=book.version,
    )
    saved = await _response(session, book)
    response.headers["ETag"] = price_book_etag(saved.version)
    return saved
