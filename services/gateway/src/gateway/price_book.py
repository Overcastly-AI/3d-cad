"""``/api/v1/price-book``: the caller's lumber price book (PRICE-BOOK).

Thin, auth-gated forwards over :mod:`documents.price_book`: the caller comes
from the JWT and documents scopes the book to that user, so there is no id to
name and no way to reach another user's book. The body is
:class:`loft_wire.price_book.PriceBookUpdate`, validated here (at most 500
entries, integer cents from 0 to $100,000, one price per key) before anything
goes upstream. The cut list routes read the same book to price their lines
(:func:`caller_price_book`).
"""

from fastapi import APIRouter, Request, status
from loft_wire.price_book import PriceBookResponse, PriceBookUpdate

from gateway.auth import CurrentUser
from gateway.db import User
from gateway.parts import forward_documents
from gateway.upstream import raise_upstream_error

_SERVICE = "Documents"

router = APIRouter(prefix="/api/v1/price-book", tags=["price-book"])


async def caller_price_book(http_request: Request, user: User) -> PriceBookResponse:
    """The authenticated caller's price book (empty if never saved)."""
    upstream = await forward_documents(http_request, user, "GET", "/api/v1/price-book")
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return PriceBookResponse.model_validate_json(upstream.content)


@router.get("")
async def get_price_book(user: CurrentUser, http_request: Request) -> PriceBookResponse:
    """Your price book: what you pay per stock piece, linear foot or board
    foot for each material and lumber profile, in integer cents. Empty (USD)
    until you save one."""
    return await caller_price_book(http_request, user)


@router.put("")
async def put_price_book(
    request: PriceBookUpdate, user: CurrentUser, http_request: Request
) -> PriceBookResponse:
    """Replace your whole price book. At most 500 entries; each a material,
    a profile, a unit (`each` with its `stock_length_ft`, `linear_foot` or
    `board_foot`) and `price_cents`, an integer from 0 to 10,000,000; one
    price per material, profile, unit and stock length (else a 422)."""
    upstream = await forward_documents(
        http_request, user, "PUT", "/api/v1/price-book", request.model_dump_json()
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return PriceBookResponse.model_validate_json(upstream.content)
