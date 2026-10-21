"""``/api/v1/price-book``: the caller's price book (PRICE-BOOK).

One book per user (:mod:`loft_wire.price_book`), read and replaced whole, as
Chief Architect's Master List is one list. Trust model and owner scoping are
:mod:`documents.parts`': the gateway forwards the verified user id and every
query here filters on it, so there is no id in the path and no way to name
another user's book.

A user who never saved a book reads an empty USD book; nothing is written
until the first ``PUT``. A ``PUT`` replaces every entry in one transaction,
with the book row locked (Postgres) so two saves serialize and the later one
wins whole, never a mix of the two.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from loft_wire.price_book import (
    EMPTY_PRICE_BOOK,
    PriceBookEntry,
    PriceBookResponse,
    PriceBookUpdate,
)
from py_kit import get_logger
from py_kit.db import SessionDep
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from documents.db import PriceBook, PriceBookEntryRow
from documents.parts import Principal

_logger = get_logger("documents.price_book")

router = APIRouter(prefix="/api/v1/price-book", tags=["price-book"])


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
                "price_cents": row.price_cents,
            }
        )
        for row in rows
    ]
    return PriceBookResponse.model_validate(
        {"currency": book.currency, "entries": entries, "updated_at": book.updated_at}
    )


@router.get("")
async def get_price_book(owner_id: Principal, session: SessionDep) -> PriceBookResponse:
    """The caller's price book; an empty USD book if they never saved one."""
    book = await _owned_book(session, owner_id)
    if book is None:
        return EMPTY_PRICE_BOOK
    return await _response(session, book)


@router.put("")
async def put_price_book(
    request: PriceBookUpdate, owner_id: Principal, session: SessionDep
) -> PriceBookResponse:
    """Replace the caller's whole price book (at most 500 entries, one price
    per material, profile, unit and stock length, integer cents)."""
    book = await _owned_book(session, owner_id, for_update=True)
    if book is None:
        book = PriceBook(owner_id=owner_id, currency=request.currency)
        session.add(book)
        try:
            await session.flush()
        except IntegrityError:
            # A concurrent first save created it: lock theirs and replace it.
            await session.rollback()
            book = await _owned_book(session, owner_id, for_update=True)
            assert book is not None
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
            price_cents=entry.price_cents,
        )
        for index, entry in enumerate(request.entries)
    )
    await session.commit()
    _logger.info(
        "price_book_saved", owner_id=str(owner_id), entries=len(request.entries)
    )
    return await _response(session, book)
