"""documents alembic 0030 (DECK-FOOTINGS): bagged concrete and post base
prices, offline DDL and a real up/down/up on a populated Postgres. Same two
layers and fixtures as ``test_migration_0028.py``."""

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

_OWNER = "6f3f6b64-0000-4000-8000-0000000300cc"
_BOOK = "6f3f6b64-0000-4000-8000-0000000300bb"
_EACH_ITEM = (
    "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_' "
    "OR profile IN ('anchor_bolt_1_2', 'foundation_vent', 'crawl_access_door', "
    "'concrete_bag_80') OR substr(profile, 1, 10) = 'post_base_')"
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


def test_0030_offline_sql_lets_bags_and_post_bases_be_priced_each(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0029:0030")
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


def test_0030_offline_downgrade_drops_bag_and_post_base_prices(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0030:0029", downgrade=True)
    assert (
        "DELETE FROM price_book_entries WHERE (profile = 'concrete_bag_80' OR "
        "substr(profile, 1, 10) = 'post_base_')" in sql
    )
    # The books that held one move on a version first, as 0029's do.
    assert "UPDATE price_books SET version = version + 1" in sql


def test_0030_up_down_up_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """A stored book's lumber, unit, bolt, vent and hinge prices come through
    unchanged; a bag and a post base store 'each' with no stock, and the
    CHECKs refuse either with a stock length or a sheet; the downgrade drops
    them and keeps the rest; the upgrade applies again."""
    alembic_runner(pg_url, "0029", downgrade=True)
    run = asyncio.run
    run(
        _rows(
            pg_url,
            "INSERT INTO price_books (id, owner_id, currency, version) "
            f"VALUES ('{_BOOK}', '{_OWNER}', 'USD', 2)",
        )
    )
    insert = (
        "INSERT INTO price_book_entries (price_book_id, order_index, material, "
        "profile, unit, stock_length_ft, sheet, price_cents) VALUES "
    )
    run(
        _rows(
            pg_url,
            insert + f"('{_BOOK}', 0, 'southern_pine_pt', 'us_6x6', 'each', 8, NULL, "
            "2998), "
            f"('{_BOOK}', 1, 'steel_f1554', 'anchor_bolt_1_2', 'each', NULL, NULL, "
            "189), "
            f"('{_BOOK}', 2, 'steel_1018', 'hinge', 'each', NULL, NULL, 450), "
            f"('{_BOOK}', 3, 'concrete', 'ready_mix', 'cubic_yard', NULL, NULL, "
            "16500), "
            f"('{_BOOK}', 6, 'steel_1018', 'foundation_vent', 'each', NULL, NULL, "
            "1898)",
        )
    )
    every = (
        "SELECT order_index, material, profile, unit, stock_length_ft, sheet, "
        "price_cents FROM price_book_entries "
        f"WHERE price_book_id = '{_BOOK}' ORDER BY order_index"
    )
    before = run(_rows(pg_url, every))
    bag = f"('{_BOOK}', 4, 'concrete', 'concrete_bag_80', 'each', NULL, NULL, 648)"
    base = f"('{_BOOK}', 5, 'steel_1018', 'post_base_6x6', 'each', NULL, NULL, 2897)"
    with pytest.raises(IntegrityError):  # 0029 cannot hold a bag price
        run(_rows(pg_url, insert + bag))

    alembic_runner(pg_url, "0030")
    assert run(_rows(pg_url, every)) == before
    run(_rows(pg_url, insert + bag + ", " + base))
    for bad in (
        "7, 'concrete', 'concrete_bag_80', 'each', 8, NULL, 1",  # no stock length
        "7, 'steel_1018', 'post_base_4x4', 'each', NULL, '4x8', 1",  # no sheet
        "7, 'concrete', 'concrete_bag_80', 'cubic_yard', NULL, NULL, 1",  # Each
        "7, 'southern_pine_pt', 'us_2x4', 'each', NULL, NULL, 1",  # lumber needs one
    ):
        with pytest.raises(IntegrityError):
            run(_rows(pg_url, f"{insert}('{_BOOK}', {bad})"))

    alembic_runner(pg_url, "0029", downgrade=True)
    assert run(_rows(pg_url, every)) == before
    version = "SELECT version FROM price_books WHERE id = '" + _BOOK + "'"
    assert run(_rows(pg_url, version)) == [(3,)]
    alembic_runner(pg_url, "head")
    assert run(_rows(pg_url, every)) == before
    run(_rows(pg_url, f"DELETE FROM price_books WHERE id = '{_BOOK}'"))
