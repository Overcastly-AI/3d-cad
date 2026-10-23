"""documents alembic 0028 (CASEWORK): casework banding and hardware prices,
offline DDL and a real up/down/up on a populated Postgres. Same two layers
and fixtures as ``test_migration_0026.py``."""

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

_OWNER = "6f3f6b64-0000-4000-8000-0000000280cc"
_BOOK = "6f3f6b64-0000-4000-8000-0000000280bb"
_UNIT = (
    "(substr(profile, 1, 7) = 'window_' OR substr(profile, 1, 5) = 'door_' "
    "OR profile = 'anchor_bolt_1_2')"
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


def test_0028_offline_sql_lets_hardware_be_priced_each(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0027:0028")
    assert (
        "ADD CONSTRAINT ck_price_book_entries_each_stock CHECK ((unit = 'each') = "
        f"(stock_length_ft IS NOT NULL OR sheet IS NOT NULL OR {_UNIT} "
        f"OR {_HARDWARE}))" in sql
    )
    assert (
        "ADD CONSTRAINT ck_price_book_entries_item_stock CHECK "
        f"(NOT ({_HARDWARE} OR profile = 'edge_banding') OR "
        "(stock_length_ft IS NULL AND sheet IS NULL))" in sql
    )
    # No row is rewritten on the way up.
    assert "UPDATE " not in sql.replace("UPDATE alembic_version", "")
    assert "DELETE " not in sql


def test_0028_offline_downgrade_drops_casework_prices(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0028:0027", downgrade=True)
    assert "DELETE FROM price_book_entries WHERE" in sql
    assert "DROP CONSTRAINT ck_price_book_entries_item_stock" in sql


def test_0028_up_down_up_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """A stored book's lumber, sheet and unit prices come through unchanged;
    a hinge stores 'each' and banding 'linear_foot' with no stock, and the
    CHECKs refuse hardware with a stock length or a sheet, banding with a
    stock length, and a lumber 'each' with no stock still; the downgrade
    drops the casework prices and keeps the rest; the upgrade applies
    again."""
    alembic_runner(pg_url, "0027", downgrade=True)
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
            insert + f"('{_BOOK}', 0, 'spf_lumber', 'us_2x6', 'each', 8, NULL, 648), "
            f"('{_BOOK}', 1, 'melamine', 'melamine_3_4', 'each', NULL, '4x8', 4298), "
            f"('{_BOOK}', 2, 'pvc', 'window_3040', 'each', NULL, NULL, 28900)",
        )
    )
    every = (
        "SELECT order_index, material, profile, unit, stock_length_ft, sheet, "
        "price_cents FROM price_book_entries "
        f"WHERE price_book_id = '{_BOOK}' ORDER BY order_index"
    )
    before = run(_rows(pg_url, every))
    hinge = f"('{_BOOK}', 3, 'steel_1018', 'hinge', 'each', NULL, NULL, 450)"
    banding = f"('{_BOOK}', 4, 'pvc', 'edge_banding', 'linear_foot', NULL, NULL, 35)"
    with pytest.raises(IntegrityError):  # 0027 cannot hold a hinge price
        run(_rows(pg_url, insert + hinge))

    alembic_runner(pg_url, "0028")
    assert run(_rows(pg_url, every)) == before
    run(_rows(pg_url, insert + hinge + ", " + banding))
    for bad in (
        "5, 'steel_1018', 'slide_22', 'each', 8, NULL, 1",  # no stock length
        "5, 'steel_1018', 'hinge', 'each', NULL, '4x8', 1",  # no sheet
        "5, 'steel_1018', 'slide_22', 'linear_foot', NULL, NULL, 1",  # Each
        "5, 'plywood', 'edge_banding', 'linear_foot', 8, NULL, 1",  # any length
        "5, 'spf_lumber', 'us_2x4', 'each', NULL, NULL, 1",  # lumber needs one
    ):
        with pytest.raises(IntegrityError):
            run(_rows(pg_url, f"{insert}('{_BOOK}', {bad})"))

    alembic_runner(pg_url, "0027", downgrade=True)
    assert run(_rows(pg_url, every)) == before
    alembic_runner(pg_url, "head")
    assert run(_rows(pg_url, every)) == before
    run(_rows(pg_url, f"DELETE FROM price_books WHERE id = '{_BOOK}'"))
