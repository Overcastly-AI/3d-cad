"""``/api/v1/price-book`` (PRICE-BOOK): one book per user, read and replaced
whole, owner-scoped by the forwarded principal.

Pinned here: an unsaved book reads empty USD at version 0; a PUT stores
every entry in order and a second PUT replaces them all; refusals (a
negative or float price, a duplicate key, 501 entries) are 422s that leave
the stored book as it was; one user never reads or overwrites another's; a
request without the principal is a 401. SQLite file-per-test, plus the same
on the migrated Postgres schema (BIGINT cents, the CHECKs, the owner unique).

PRICE-BOOK-VERSION: the version is the ETag, a PUT without If-Match is a
428, and of two saves drafted from one version the second is a 412 that
changes nothing, whether they arrive one after the other or at once
(Postgres, the row lock and the owner unique).
"""

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2 as httpx
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
        "sheet": None,
        "price_cents": 398,
    },
    {
        "material": "southern_pine_pt",
        "profile": "us_6x6",
        "unit": "board_foot",
        "stock_length_ft": None,
        "sheet": None,
        "price_cents": 145,
    },
    {
        "material": "spf_lumber",
        "profile": "us_2x8",
        "unit": "linear_foot",
        "stock_length_ft": None,
        "sheet": None,
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


def _version(client: TestClient, headers: Any = None) -> int:
    response = client.get("/api/v1/price-book", headers=headers or _AS_OWNER)
    assert response.status_code == 200, response.text
    assert response.headers["etag"] == f'"{response.json()["version"]}"'
    return response.json()["version"]


def _put(
    client: TestClient,
    entries: list[dict[str, Any]],
    headers: Any = None,
    version: int | None = None,
) -> Any:
    """A save over the book as stored now, or over *version*."""
    headers = headers or _AS_OWNER
    if version is None:
        version = _version(client, headers) if PRINCIPAL_HEADER in headers else 0
    return client.put(
        "/api/v1/price-book",
        json={"currency": "USD", "entries": entries},
        headers={**headers, "If-Match": f'"{version}"'},
    )


def _entries(client: TestClient, headers: Any = None) -> list[dict[str, Any]]:
    response = client.get("/api/v1/price-book", headers=headers or _AS_OWNER)
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def _round_trip(client: TestClient) -> None:
    empty = client.get("/api/v1/price-book", headers=_AS_OWNER)
    assert empty.status_code == 200
    assert empty.json() == {
        "currency": "USD",
        "entries": [],
        "updated_at": None,
        "version": 0,
    }

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


SHEETS: list[dict[str, Any]] = [
    {
        "material": "osb",
        "profile": "osb_7_16",
        "unit": "each",
        "stock_length_ft": None,
        "sheet": "4x9",
        "price_cents": 2498,
    },
    {
        "material": "plywood",
        "profile": "plywood_23_32",
        "unit": "each",
        "stock_length_ft": None,
        "sheet": "4x8",
        "price_cents": 4250,
    },
]


def test_sheet_prices_round_trip(client: TestClient) -> None:
    """SHEATHING: a sheet product priced Each per sheet stores its sheet."""
    assert _put(client, [*BOOK, *SHEETS]).status_code == 200
    assert _entries(client) == [*BOOK, *SHEETS]
    refused = _put(client, [{**SHEETS[0], "sheet": None}])
    assert refused.status_code == 422
    assert _entries(client) == [*BOOK, *SHEETS]


UNITS: list[dict[str, Any]] = [
    {
        "material": "pvc",
        "profile": "window_3040",
        "unit": "each",
        "stock_length_ft": None,
        "sheet": None,
        "price_cents": 28900,
    },
    {
        "material": "spf_lumber",
        "profile": "door_3068",
        "unit": "each",
        "stock_length_ft": None,
        "sheet": None,
        "price_cents": 44900,
    },
]


def test_unit_prices_round_trip(client: TestClient) -> None:
    """OPENING-UNITS: a window or door unit is priced Each per unit, with no
    stock length or sheet."""
    assert _put(client, [*BOOK, *SHEETS, *UNITS]).status_code == 200
    assert _entries(client) == [*BOOK, *SHEETS, *UNITS]
    refused = _put(client, [{**UNITS[0], "stock_length_ft": 8}])
    assert refused.status_code == 422
    assert _entries(client) == [*BOOK, *SHEETS, *UNITS]


FOUNDATION: list[dict[str, Any]] = [
    {
        "material": "concrete",
        "profile": "ready_mix",
        "unit": "cubic_yard",
        "stock_length_ft": None,
        "sheet": None,
        "price_cents": 16500,
    },
    {
        "material": "steel_a615",
        "profile": "rebar_4",
        "unit": "each",
        "stock_length_ft": 20,
        "sheet": None,
        "price_cents": 1498,
    },
    {
        "material": "steel_f1554",
        "profile": "anchor_bolt_1_2",
        "unit": "each",
        "stock_length_ft": None,
        "sheet": None,
        "price_cents": 248,
    },
]


def test_foundation_prices_round_trip(client: TestClient) -> None:
    """SLAB: ready-mix per cubic yard, a #4 stick Each at 20 ft, an anchor
    bolt Each with neither stock nor sheet; any other shape is refused."""
    every = [*BOOK, *SHEETS, *UNITS, *FOUNDATION]
    assert _put(client, every).status_code == 200
    assert _entries(client) == every
    for bad in (
        {**FOUNDATION[0], "unit": "each"},
        {**FOUNDATION[1], "stock_length_ft": 16},
        {**FOUNDATION[2], "stock_length_ft": 8},
        {**BOOK[0], "unit": "cubic_yard", "stock_length_ft": None},
    ):
        assert _put(client, [bad]).status_code == 422, bad
    assert _entries(client) == every


def _stale_save_loses_nothing(client: TestClient) -> None:
    """Two saves drafted from one version: the first is kept, the second is
    412 ``price_book_stale`` and changes nothing; reloading and saving
    again works."""
    assert _version(client) == 0
    first = _put(client, BOOK, version=0)
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1
    assert first.headers["etag"] == '"1"'
    second = _put(client, [BOOK[0]], version=0)
    assert second.status_code == 412, second.text
    assert second.json()["error"]["code"] == "price_book_stale"
    assert second.json()["error"]["details"] == {"version": 1}
    assert _entries(client) == BOOK
    assert _version(client) == 1
    # A save over a version the book has not reached is stale too.
    assert _put(client, [], version=7).status_code == 412
    # Reloaded, the second save goes through over version 1.
    third = _put(client, [BOOK[0]], version=1)
    assert third.status_code == 200
    assert third.json()["version"] == 2
    assert _entries(client) == [BOOK[0]]
    # The other user's book has its own version.
    assert _version(client, _AS_OTHER) == 0


def test_a_stale_save_is_refused_and_loses_nothing(client: TestClient) -> None:
    _stale_save_loses_nothing(client)


def test_a_save_without_if_match_is_428(client: TestClient) -> None:
    for headers in (_AS_OWNER, {**_AS_OWNER, "If-Match": "*"}):
        response = client.put(
            "/api/v1/price-book",
            json={"currency": "USD", "entries": BOOK},
            headers=headers,
        )
        assert response.status_code in (412, 428), response.text
    bare = client.put(
        "/api/v1/price-book",
        json={"currency": "USD", "entries": BOOK},
        headers=_AS_OWNER,
    )
    assert bare.status_code == 428
    assert bare.json()["error"]["code"] == "price_book_version_required"
    assert _entries(client) == []
    assert _version(client) == 0


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
            "sheet": None,
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
        every = [*BOOK, *SHEETS, *UNITS, *FOUNDATION]
        assert _put(client, every).status_code == 200
        assert _entries(client) == every

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
        "'spf_lumber', 'us_2x4', 'each', 8, NULL, -1",
        "'spf_lumber', 'us_2x4', 'each', NULL, NULL, 1",
        "'spf_lumber', 'us_2x4', 'linear_foot', 8, NULL, 1",
        "'osb', 'osb_7_16', 'linear_foot', NULL, '4x9', 1",
        "'osb', 'osb_7_16', 'each', 8, '4x9', 1",
        "'pvc', 'window_3040', 'linear_foot', NULL, NULL, 1",
        "'pvc', 'window_3040', 'each', 8, NULL, 1",
        "'spf_lumber', 'door_3068', 'each', NULL, '4x8', 1",
        "'concrete', 'ready_mix', 'each', NULL, NULL, 1",
        "'concrete', 'ready_mix', 'cubic_yard', 8, NULL, 1",
        "'spf_lumber', 'us_2x4', 'cubic_yard', NULL, NULL, 1",
        "'steel_f1554', 'anchor_bolt_1_2', 'each', 8, NULL, 1",
    ):
        with pytest.raises(IntegrityError):
            asyncio.run(
                bypass(
                    "INSERT INTO price_book_entries (price_book_id, order_index, "
                    "material, profile, unit, stock_length_ft, sheet, "
                    f"price_cents) VALUES ({book}, 99, {values})"
                )
            )
    with pytest.raises(IntegrityError):
        asyncio.run(bypass(f"UPDATE price_books SET version = 0 WHERE id = {book}"))
    with pytest.raises(IntegrityError):
        asyncio.run(
            bypass(
                "INSERT INTO price_books (owner_id, currency) "
                f"VALUES ('{OWNER}', 'USD')"
            )
        )


def test_the_race_on_postgres(pg_url: str) -> None:
    """The stale save on the migrated schema, then the real race: two saves
    drafted from one version sent at once (each its own session and
    transaction, on one event loop). Exactly one is saved and the other is a
    412; the stored book is the winner's, whole, never a mix and never the
    loser's. Twice: over a saved book (the row lock) and over a never-saved
    one (the owner unique)."""
    with TestClient(build_app(DocumentsSettings(postgres_url=pg_url))) as client:
        _stale_save_loses_nothing(client)  # leaves our book at version 2

    app = build_app(DocumentsSettings(postgres_url=pg_url))
    books = ([BOOK[0]], [BOOK[1], BOOK[2]])

    async def race(http: httpx.AsyncClient, headers: dict[str, str], version: int):
        responses = await asyncio.gather(
            *(
                http.put(
                    "/api/v1/price-book",
                    json={"currency": "USD", "entries": entries},
                    headers={**headers, "If-Match": f'"{version}"'},
                )
                for entries in books
            )
        )
        codes = [r.status_code for r in responses]
        assert sorted(codes) == [200, 412], [r.text for r in responses]
        loser = responses[codes.index(412)].json()["error"]
        assert loser["code"] == "price_book_stale"
        stored = (await http.get("/api/v1/price-book", headers=headers)).json()
        assert stored["entries"] == books[codes.index(200)]
        assert stored["version"] == version + 1

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://documents"
            ) as http:
                await race(http, _AS_OWNER, 2)
                await race(http, _AS_OTHER, 0)

    asyncio.run(scenario())
