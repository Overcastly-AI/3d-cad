"""documents alembic 0031 (SIDING-TRIM): siding priced per board or per
square and its 5/4x4 trim, offline DDL and a real up/down/up on a populated
Postgres. Same two layers and fixtures as ``test_migration_0030.py``."""

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

_OWNER = "6f3f6b64-0000-4000-8000-0000000310cc"
_BOOK = "6f3f6b64-0000-4000-8000-0000000310bb"
_SIDING = (
    "(profile IN ('fibre_cement_lap_8_25', 'vinyl_d4', 'cedar_bevel_1_2x8', "
    "'us_5_4x4') OR material IN ('fibre_cement', 'western_red_cedar'))"
)


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


def test_0031_offline_sql_holds_the_square_to_vinyl(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0030:0031")
    assert (
        "ADD CONSTRAINT ck_price_book_entries_square CHECK ((unit = 'square') = "
        "(profile = 'vinyl_d4' AND stock_length_ft IS NULL AND sheet IS NULL))"
    ) in sql
    assert "UPDATE " not in sql.replace("UPDATE alembic_version", "")
    assert "DELETE " not in sql


def test_0031_offline_downgrade_drops_siding_and_trim_prices(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0031:0030", downgrade=True)
    assert f"DELETE FROM price_book_entries WHERE {_SIDING}" in sql
    assert "UPDATE price_books SET version = version + 1" in sql


def test_0031_up_down_up_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """A stored book's prices come through unchanged; a lap board stores
    'each' at 12 ft, the trim per foot and vinyl per square, which the CHECK
    holds to vinyl with no stock or sheet; the downgrade drops the three and
    keeps the rest; the upgrade applies again."""
    alembic_runner(pg_url, "0030", downgrade=True)
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
            f"('{_BOOK}', 1, 'concrete', 'ready_mix', 'cubic_yard', NULL, NULL, "
            "16500)",
        )
    )
    every = (
        "SELECT order_index, material, profile, unit, stock_length_ft, sheet, "
        "price_cents FROM price_book_entries "
        f"WHERE price_book_id = '{_BOOK}' ORDER BY order_index"
    )
    before = run(_rows(pg_url, every))
    vinyl = f"('{_BOOK}', 4, 'pvc', 'vinyl_d4', 'square', NULL, NULL, 13900)"
    alembic_runner(pg_url, "0031")
    assert run(_rows(pg_url, every)) == before
    run(
        _rows(
            pg_url,
            insert
            + f"('{_BOOK}', 2, 'fibre_cement', 'fibre_cement_lap_8_25', 'each', 12, "
            "NULL, 1398), "
            f"('{_BOOK}', 3, 'fibre_cement', 'us_5_4x4', 'linear_foot', NULL, NULL, "
            "145), " + vinyl,
        )
    )
    for bad in (
        "5, 'pvc', 'vinyl_d4', 'square', 12, NULL, 1",  # no stock length
        "5, 'pvc', 'vinyl_d4', 'square', NULL, '4x8', 1",  # no sheet
        "5, 'osb', 'osb_7_16', 'square', NULL, NULL, 1",  # vinyl only
        "5, 'pvc', 'vinyl_d4', 'linear_foot', NULL, NULL, 1",  # per square
    ):
        with pytest.raises(IntegrityError):
            run(_rows(pg_url, f"{insert}('{_BOOK}', {bad})"))

    alembic_runner(pg_url, "0030", downgrade=True)
    assert run(_rows(pg_url, every)) == before
    version = "SELECT version FROM price_books WHERE id = '" + _BOOK + "'"
    assert run(_rows(pg_url, version)) == [(3,)]
    alembic_runner(pg_url, "head")
    assert run(_rows(pg_url, every)) == before
    run(_rows(pg_url, insert + vinyl))
    run(_rows(pg_url, f"DELETE FROM price_books WHERE id = '{_BOOK}'"))
