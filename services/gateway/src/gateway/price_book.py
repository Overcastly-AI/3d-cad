"""``/api/v1/price-book``: the caller's lumber price book (PRICE-BOOK).

Thin, auth-gated forwards over :mod:`documents.price_book`: the caller comes
from the JWT and documents scopes the book to that user, so there is no id to
name and no way to reach another user's book. The body is
:class:`loft_wire.price_book.PriceBookUpdate`, validated here (at most 500
entries, integer cents from 0 to $100,000, one price per key) before anything
goes upstream. The cut list routes read the same book to price their lines
(:func:`caller_price_book`).

PRICE-BOOK-VERSION: the book's version is its ``ETag``; a ``PUT`` sends it
back in ``If-Match`` and documents refuses a stale one with 412 (428 with
none). Both headers pass through here unchanged.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status
from loft_wire.price_book import (
    PriceBookResponse,
    PriceBookUpdate,
    PriceBookVersionEnvelope,
    price_book_etag,
)

from gateway.auth import CurrentUser
from gateway.db import User
from gateway.parts import forward_documents
from gateway.upstream import raise_upstream_error

_SERVICE = "Documents"

router = APIRouter(prefix="/api/v1/price-book", tags=["price-book"])

#: ``If-Match``: the version the saved book was drafted from.
IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        max_length=64,
        description='The book\'s version as read: its ETag (e.g. "3"), or '
        '"0" for a book never saved. Required; a save drafted from an older '
        "version is refused with 412 price_book_stale.",
    ),
]


async def caller_price_book(http_request: Request, user: User) -> PriceBookResponse:
    """The authenticated caller's price book (empty if never saved)."""
    upstream = await forward_documents(http_request, user, "GET", "/api/v1/price-book")
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return PriceBookResponse.model_validate_json(upstream.content)


@router.get("")
async def get_price_book(
    user: CurrentUser, http_request: Request, response: Response
) -> PriceBookResponse:
    """Your price book: what you pay per stock piece, sheet, linear foot or
    board foot for each material and profile, in integer cents. Empty (USD,
    version 0) until you save one. The `ETag` is its `version`."""
    book = await caller_price_book(http_request, user)
    response.headers["ETag"] = price_book_etag(book.version)
    return book


@router.put(
    "",
    responses={
        412: {
            "model": PriceBookVersionEnvelope,
            "description": "The book was saved since the If-Match version: "
            "`price_book_stale`, `details.version` its version now.",
        },
        428: {
            "model": PriceBookVersionEnvelope,
            "description": "No If-Match: `price_book_version_required`.",
        },
    },
)
async def put_price_book(
    request: PriceBookUpdate,
    user: CurrentUser,
    http_request: Request,
    response: Response,
    if_match: IfMatch = None,
) -> PriceBookResponse:
    """Replace your whole price book, if it is still the version you read.
    Send that version as `If-Match` (the GET's `ETag`); a book saved since is
    refused with 412 `price_book_stale` and kept as it is. At most 500
    entries; each a material, a profile, a unit (`each` with its
    `stock_length_ft`, or its `sheet` for a sheet product; `linear_foot` or
    `board_foot`) and `price_cents`, an integer from 0 to 10,000,000; one
    price per material, profile, unit and stock length or sheet (else a 422)."""
    upstream = await forward_documents(
        http_request,
        user,
        "PUT",
        "/api/v1/price-book",
        request.model_dump_json(),
        headers=None if if_match is None else {"If-Match": if_match},
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    saved = PriceBookResponse.model_validate_json(upstream.content)
    response.headers["ETag"] = price_book_etag(saved.version)
    return saved
