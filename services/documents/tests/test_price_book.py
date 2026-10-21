"""``/api/v1/price-book`` (PRICE-BOOK): one book per user, read and replaced
whole, owner-scoped by the forwarded principal.

Pinned here: an unsaved book reads empty USD; a PUT stores every entry in
order and a second PUT replaces them all; refusals (a negative or float
price, a duplicate key, 501 entries) are 422s that leave the stored book as
it was; one user never reads or overwrites another's; a request without the
principal is a 401. SQLite file-per-test, plus the same on the migrated
Postgres schema (BIGINT cents, the CHECKs, the owner unique).
"""

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from documents.db import Base
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.parts import PRINCIPAL_HEADER
from py_kit.db import async_dsn
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-0000000022aa"
OTHER = "6f3f6b64-0000-4000-8000-0000000022bb"

_AS_OWNER = {PRINCIPAL_HEADER: OWNER}
_AS_OTHER = {PRINCIPAL_HEADER: OTHER}

BOOK: list[dict[str, Any]] = [
    {
        "material": "spf_lumber",
        "profile": "us_2x4",
        "unit": "each",
        "stock_length_ft": 8,
        "price_cents": 398,
    },
    {
        "material": "southern_pine_pt",
        "profile": "us_6x6",
        "unit": "board_foot",
        "stock_length_ft": None,
        "price_cents": 145,
    },
    {
        "material": "spf_lumber",
        "profile": "us_2x8",
        "unit": "linear_foot",
        "stock_length_ft": None,
        "price_cents": 94,
    },
]


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    url = f"sqlite:///{tmp_path / 'documents.db'}"
    asyncio.run(_create_schema(url))
    with TestClient(build_app(DocumentsSettings(postgres_url=url))) as test_client:
        yield test_client


def _put(client: TestClient, entries: list[dict[str, Any]], headers: Any = None) -> Any:
    return client.put(
        "/api/v1/price-book",
        json={"currency": "USD", "entries": entries},
        headers=headers or _AS_OWNER,
    )


def _entries(client: TestClient, headers: Any = None) -> list[dict[str, Any]]:
    response = client.get("/api/v1/price-book", headers=headers or _AS_OWNER)
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def _round_trip(client: TestClient) -> None:
    empty = client.get("/api/v1/price-book", headers=_AS_OWNER)
    assert empty.status_code == 200
    assert empty.json() == {"currency": "USD", "entries": [], "updated_at": None}

    saved = _put(client, BOOK)
    assert saved.status_code == 200, saved.text
    assert saved.json()["entries"] == BOOK
    assert saved.json()["updated_at"] is not None
    assert _entries(client) == BOOK

    # A second save replaces the whole book, in its new order.
    again = [BOOK[2], {**BOOK[0], "price_cents": 412}]
    assert _put(client, again).status_code == 200
    assert _entries(client) == again

    # Refusals leave the stored book as it was.
    for bad in (
        [{**BOOK[0], "price_cents": -1}],
        [{**BOOK[0], "price_cents": 3.98}],
        [BOOK[0], {**BOOK[0], "price_cents": 1}],
        [{**BOOK[0], "stock_length_ft": None}],
        [{**BOOK[1], "stock_length_ft": 8}],
        [BOOK[0]] * 501,
    ):
        refused = _put(client, bad)
        assert refused.status_code == 422, refused.text
    assert _entries(client) == again

    # The other user sees an empty book, and their save leaves ours alone.
    assert _entries(client, _AS_OTHER) == []
    assert _put(client, [BOOK[1]], _AS_OTHER).status_code == 200
    assert _entries(client, _AS_OTHER) == [BOOK[1]]
    assert _entries(client) == again

    # Emptying a book keeps it (and its currency), with no entries.
    assert _put(client, []).status_code == 200
    assert _entries(client) == []
    assert _entries(client, _AS_OTHER) == [BOOK[1]]


def test_a_book_round_trips_and_is_the_owners_alone(client: TestClient) -> None:
    _round_trip(client)


def test_no_principal_is_a_401(client: TestClient) -> None:
    assert client.get("/api/v1/price-book").status_code == 401
    assert _put(client, BOOK, {"X-Unrelated": "1"}).status_code == 401
    assert (
        client.get(
            "/api/v1/price-book", headers={PRINCIPAL_HEADER: "not-a-uuid"}
        ).status_code
        == 401
    )


def test_the_full_500_entry_book_saves(client: TestClient) -> None:
    profiles = [
        "us_1x4", "us_1x6", "us_5_4x6", "us_2x2", "us_2x3", "us_2x4", "us_2x6",
        "us_2x8", "us_2x10", "us_2x12", "us_4x4", "us_4x6", "us_6x6",
    ]  # fmt: skip
    woods = ["spf_lumber", "dfl_lumber", "southern_pine_pt", "lvl", "glulam_dfl"]
    entries = [
        {
            "material": material,
            "profile": profile,
            "unit": "each",
            "stock_length_ft": feet,
            "price_cents": 10_000_000,
        }
        for material in woods
        for profile in profiles
        for feet in (8, 10, 12, 14, 16, 20)
    ][:500]
    assert _put(client, entries).status_code == 200
    assert _entries(client) == entries


# --- Postgres ---------------------------------------------------------------------


def test_the_book_on_postgres_with_the_migrated_schema(pg_url: str) -> None:
    with TestClient(build_app(DocumentsSettings(postgres_url=pg_url))) as client:
        _round_trip(client)

    async def bypass(statement: str) -> None:
        engine = create_async_engine(async_dsn(pg_url))
        try:
            async with engine.begin() as connection:
                await connection.execute(sa.text(statement))
        finally:
            await engine.dispose()

    # The database's backstops, for a write that skipped the wire's rules.
    book = f"(SELECT id FROM price_books WHERE owner_id = '{OWNER}')"
    for values in (
        "'spf_lumber', 'us_2x4', 'each', 8, -1",
        "'spf_lumber', 'us_2x4', 'each', NULL, 1",
        "'spf_lumber', 'us_2x4', 'linear_foot', 8, 1",
    ):
        with pytest.raises(IntegrityError):
            asyncio.run(
                bypass(
                    "INSERT INTO price_book_entries (price_book_id, order_index, "
                    "material, profile, unit, stock_length_ft, price_cents) "
                    f"VALUES ({book}, 99, {values})"
                )
            )
    with pytest.raises(IntegrityError):
        asyncio.run(
            bypass(
                "INSERT INTO price_books (owner_id, currency) "
                f"VALUES ('{OWNER}', 'USD')"
            )
        )
