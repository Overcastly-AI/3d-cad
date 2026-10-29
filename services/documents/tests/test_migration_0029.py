"""documents alembic 0029 (FOUNDATION-TAKEOFF): foundation vent and access
door prices, offline DDL and a real up/down/up on a populated Postgres. Same
two layers and fixtures as ``test_migration_0028.py``."""

import asyncio
import io
from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from py_kit.db import async_dsn
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

_OWNER = "6f3f6b64-0000-4000-8000-0000000290cc"
_BOOK = "6f3f6b64-0000-4000-8000-0000000290bb"
_OTHER_OWNER = "6f3f6b64-0000-4000-8000-0000000291cc"
_OTHER = "6f3f6b64-0000-4000-8000-0000000291bb"
_EACH_ITEM = (
    "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_' "
    "OR profile IN ('anchor_bolt_1_2', 'foundation_vent', 'crawl_access_door'))"
)
_HARDWARE = "(profile = 'hinge' OR substr(profile, 1, 6) = 'slide_')"


def _offline_sql(
    alembic_ini: Path,
    monkeypatch: pytest.MonkeyPatch,
    revision_range: str,
    *,
    downgrade: bool = False,
) -> str:
    """Render migrations offline (``--sql``) — no database involved."""
    monkeypatch.setenv("POSTGRES_URL", "postgresql://loft:unused@db.invalid/loft")
    buffer = io.StringIO()
    config = Config(str(alembic_ini), output_buffer=buffer)
    if downgrade:
        command.downgrade(config, revision_range, sql=True)
    else:
        command.upgrade(config, revision_range, sql=True)
    return buffer.getvalue()


async def _rows(url: str, statement: str) -> list[tuple[object, ...]]:
    engine = create_async_engine(async_dsn(url))
    try:
        async with engine.begin() as connection:
            result = await connection.execute(sa.text(statement))
            return [tuple(row) for row in result] if result.returns_rows else []
    finally:
        await engine.dispose()


def test_0029_offline_sql_lets_vents_and_access_doors_be_priced_each(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0028:0029")
    assert (
        "ADD CONSTRAINT ck_price_book_entries_each_stock CHECK ((unit = 'each') = "
        f"(stock_length_ft IS NOT NULL OR sheet IS NOT NULL OR {_EACH_ITEM} "
        f"OR {_HARDWARE}))" in sql
    )
    assert (
        "ADD CONSTRAINT ck_price_book_entries_unit_each CHECK "
        f"(NOT {_EACH_ITEM} OR (stock_length_ft IS NULL AND sheet IS NULL))" in sql
    )
    # No row is rewritten on the way up.
    assert "UPDATE " not in sql.replace("UPDATE alembic_version", "")
    assert "DELETE " not in sql


def test_0029_offline_downgrade_drops_their_prices_and_moves_the_book_on(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0029:0028", downgrade=True)
    bump = sql.index("UPDATE price_books SET version = version + 1")
    assert bump < sql.index("DELETE FROM price_book_entries WHERE")


def test_0029_up_down_up_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """A stored book's lumber, unit and bolt prices come through unchanged; a
    vent and an access door store 'each' with no stock, and the CHECKs refuse
    either with a stock length, a sheet or another unit; the downgrade drops
    their prices, moves only that book's version on and keeps the rest; the
    upgrade applies again."""
    alembic_runner(pg_url, "0028", downgrade=True)
    run = asyncio.run
    run(
        _rows(
            pg_url,
            "INSERT INTO price_books (id, owner_id, currency, version) "
            f"VALUES ('{_BOOK}', '{_OWNER}', 'USD', 2), "
            f"('{_OTHER}', '{_OTHER_OWNER}', 'USD', 5)",
        )
    )
    insert = (
        "INSERT INTO price_book_entries (price_book_id, order_index, material, "
        "profile, unit, stock_length_ft, sheet, price_cents) VALUES "
    )
    run(
        _rows(
            pg_url,
            insert + f"('{_BOOK}', 0, 'spf_lumber', 'us_2x6', 'each', 8, NULL, 648), "
            f"('{_BOOK}', 1, 'pvc', 'window_3040', 'each', NULL, NULL, 28900), "
            f"('{_BOOK}', 2, 'steel_f1554', 'anchor_bolt_1_2', 'each', NULL, NULL, "
            "248), "
            f"('{_OTHER}', 0, 'concrete', 'ready_mix', 'cubic_yard', NULL, NULL, "
            "16500)",
        )
    )
    every = (
        "SELECT price_book_id, order_index, material, profile, unit, "
        "stock_length_ft, sheet, price_cents FROM price_book_entries "
        "ORDER BY price_book_id, order_index"
    )
    versions = "SELECT id::text, version FROM price_books ORDER BY id"
    before = run(_rows(pg_url, every))
    vent = f"('{_BOOK}', 3, 'steel_1018', 'foundation_vent', 'each', NULL, NULL, 1298)"
    door = (
        f"('{_BOOK}', 4, 'steel_1018', 'crawl_access_door', 'each', NULL, NULL, 4997)"
    )
    with pytest.raises(IntegrityError):  # 0028 cannot hold a vent price
        run(_rows(pg_url, insert + vent))

    alembic_runner(pg_url, "0029")
    assert run(_rows(pg_url, every)) == before
    run(_rows(pg_url, insert + vent + ", " + door))
    for bad in (
        "5, 'steel_1018', 'foundation_vent', 'each', 8, NULL, 1",  # no stock
        "5, 'steel_1018', 'crawl_access_door', 'each', NULL, '4x8', 1",  # no sheet
        "5, 'steel_1018', 'foundation_vent', 'linear_foot', NULL, NULL, 1",  # Each
        "5, 'spf_lumber', 'us_2x4', 'each', NULL, NULL, 1",  # lumber needs one
    ):
        with pytest.raises(IntegrityError):
            run(_rows(pg_url, f"{insert}('{_BOOK}', {bad})"))

    alembic_runner(pg_url, "0028", downgrade=True)
    assert run(_rows(pg_url, every)) == before
    # Only the book that lost prices moves on, so its stale draft is refused.
    assert run(_rows(pg_url, versions)) == [(_BOOK, 3), (_OTHER, 5)]
    alembic_runner(pg_url, "head")
    assert run(_rows(pg_url, every)) == before
    run(_rows(pg_url, f"DELETE FROM price_books WHERE id IN ('{_BOOK}', '{_OTHER}')"))
