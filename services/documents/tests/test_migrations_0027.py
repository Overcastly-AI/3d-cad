"""Migration 0027 (SLAB): concrete, rebar and anchor-bolt prices.

The offline DDL, and an up/down/up against a stored book on the scratch
PostgreSQL server (conftest.py), as test_migrations.py does for 0025.
"""

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

#: The owner of the books seeded below (test_migrations.py's).
_OWNER = "6f3f6b64-0000-4000-8000-0000000160bb"


def _offline_sql(
    alembic_ini: Path,
    monkeypatch: pytest.MonkeyPatch,
    revision_range: str,
    *,
    downgrade: bool = False,
) -> str:
    """Render migrations offline (``--sql``): no database involved."""
    monkeypatch.setenv("POSTGRES_URL", "postgresql://loft:unused@db.invalid/loft")
    buffer = io.StringIO()
    config = Config(str(alembic_ini), output_buffer=buffer)
    if downgrade:
        command.downgrade(config, revision_range, sql=True)
    else:
        command.upgrade(config, revision_range, sql=True)
    return buffer.getvalue()


async def _scalar_rows(url: str, statement: str) -> list[tuple[object, ...]]:
    engine = create_async_engine(async_dsn(url))
    try:
        async with engine.begin() as connection:
            result = await connection.execute(sa.text(statement))
            return [tuple(row) for row in result] if result.returns_rows else []
    finally:
        await engine.dispose()


def test_0027_offline_sql_lets_concrete_rebar_and_bolts_be_priced(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0026:0027")
    item = (
        "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_' "
        "OR profile = 'anchor_bolt_1_2')"
    )
    assert (
        "ADD CONSTRAINT ck_price_book_entries_each_stock CHECK ((unit = 'each') = "
        f"(stock_length_ft IS NOT NULL OR sheet IS NOT NULL OR {item}))" in sql
    )
    assert (
        "ADD CONSTRAINT ck_price_book_entries_unit_each CHECK "
        f"(NOT {item} OR (stock_length_ft IS NULL AND sheet IS NULL))" in sql
    )
    assert (
        "ADD CONSTRAINT ck_price_book_entries_cubic_yard CHECK "
        "((unit = 'cubic_yard') = (profile = 'ready_mix' AND stock_length_ft "
        "IS NULL AND sheet IS NULL))" in sql
    )
    # No row is rewritten on the way up.
    assert "UPDATE " not in sql.replace("UPDATE alembic_version", "")
    assert "DELETE " not in sql


def test_0027_offline_downgrade_deletes_only_foundation_prices(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0027:0026", downgrade=True)
    assert (
        "DELETE FROM price_book_entries WHERE profile IN "
        "('ready_mix', 'rebar_4', 'anchor_bolt_1_2')" in sql
    )
    assert "DROP CONSTRAINT ck_price_book_entries_cubic_yard" in sql


_SLAB_BOOK = "6f3f6b64-0000-4000-8000-0000000260bb"


def test_0027_up_down_up_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """SLAB: 0027 against a stored book. Its lumber, sheet and unit prices
    come through unchanged; ready-mix stores per cubic yard and a bolt Each
    with neither stock nor sheet, and the CHECKs refuse ready-mix Each, a
    cubic yard of anything else, a cubic yard with a stock length, and a
    lumber Each with no stock still; the downgrade drops the foundation
    prices and keeps the rest; the upgrade applies again."""
    alembic_runner(pg_url, "0026", downgrade=True)
    run = asyncio.run
    run(
        _scalar_rows(
            pg_url,
            "INSERT INTO price_books (id, owner_id, currency, version) "
            f"VALUES ('{_SLAB_BOOK}', '{_OWNER}', 'USD', 2)",
        )
    )
    insert = (
        "INSERT INTO price_book_entries (price_book_id, order_index, material, "
        "profile, unit, stock_length_ft, sheet, price_cents) VALUES "
    )
    run(
        _scalar_rows(
            pg_url,
            insert + f"('{_SLAB_BOOK}', 0, 'spf_lumber', 'us_2x6', 'each', 8, "
            f"NULL, 648), ('{_SLAB_BOOK}', 1, 'pvc', 'window_3040', 'each', NULL, "
            "NULL, 28900)",
        )
    )
    every = (
        "SELECT order_index, material, profile, unit, stock_length_ft, sheet, "
        "price_cents FROM price_book_entries ORDER BY order_index"
    )
    before = run(_scalar_rows(pg_url, every))
    book = f"'{_SLAB_BOOK}'"
    concrete = f"({book}, 2, 'concrete', 'ready_mix', 'cubic_yard', NULL, NULL, 16500)"
    bolt = f"({book}, 3, 'steel_f1554', 'anchor_bolt_1_2', 'each', NULL, NULL, 248)"
    rebar = f"({book}, 4, 'steel_a615', 'rebar_4', 'each', 20, NULL, 1498)"
    with pytest.raises(IntegrityError):  # 0026 cannot hold a bolt price
        run(_scalar_rows(pg_url, insert + bolt))

    alembic_runner(pg_url, "0027")
    assert run(_scalar_rows(pg_url, every)) == before
    run(_scalar_rows(pg_url, f"{insert}{concrete}, {bolt}, {rebar}"))
    for bad in (
        "5, 'concrete', 'ready_mix', 'each', NULL, NULL, 1",  # per yd3 only
        "5, 'spf_lumber', 'us_2x4', 'cubic_yard', NULL, NULL, 1",  # ready-mix only
        "5, 'concrete', 'ready_mix', 'cubic_yard', 8, NULL, 1",  # no stock length
        "5, 'steel_f1554', 'anchor_bolt_1_2', 'each', 8, NULL, 1",  # no stock
        "5, 'spf_lumber', 'us_2x4', 'each', NULL, NULL, 1",  # lumber needs one
    ):
        with pytest.raises(IntegrityError):
            run(_scalar_rows(pg_url, f"{insert}('{_SLAB_BOOK}', {bad})"))

    alembic_runner(pg_url, "0026", downgrade=True)
    assert run(_scalar_rows(pg_url, every)) == before
    alembic_runner(pg_url, "head")
    assert run(_scalar_rows(pg_url, every)) == before
    run(_scalar_rows(pg_url, f"DELETE FROM price_books WHERE id = '{_SLAB_BOOK}'"))
