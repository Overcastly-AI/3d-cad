"""documents alembic 0032 (ROOFING): shingles by the bundle and underlayment
by the roll priced Each with neither stock nor sheet, drip edge per 10 ft
stick, starter and ridge cap per foot and the fascia's 1x10, offline DDL and a
real up/down/up on a populated Postgres. Same two layers and fixtures as
``test_migration_0031.py``."""

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

_OWNER = "6f3f6b64-0000-4000-8000-0000000320cc"
_BOOK = "6f3f6b64-0000-4000-8000-0000000320bb"
_ROOFING = (
    "(profile IN ('shingle_architectural', 'underlayment_synthetic', "
    "'drip_edge', 'shingle_starter', 'ridge_cap', 'us_1x10', 'us_1x12') OR "
    "material IN ('asphalt_shingle', 'polypropylene', 'aluminium_3105'))"
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


def test_0032_offline_sql_lets_a_bundle_and_a_roll_be_each(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0031:0032")
    assert "DROP CONSTRAINT ck_price_book_entries_each_stock" in sql
    assert "'shingle_architectural', 'underlayment_synthetic'" in sql
    assert "ADD CONSTRAINT ck_price_book_entries_unit_each" in sql
    assert "UPDATE " not in sql.replace("UPDATE alembic_version", "")
    assert "DELETE " not in sql


def test_0032_offline_downgrade_drops_roofing_prices(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0032:0031", downgrade=True)
    assert f"DELETE FROM price_book_entries WHERE {_ROOFING}" in sql
    assert "UPDATE price_books SET version = version + 1" in sql


def test_0032_up_down_up_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """A stored book's prices come through unchanged; a bundle and a roll
    store Each with neither stock nor sheet (0031 refused them), drip edge
    Each at 10 ft, ridge cap per foot and the 1x10 fascia Each at 14 ft; the
    CHECKs still hold a bundle to neither; the downgrade drops the five and
    keeps the rest; the upgrade applies again."""
    alembic_runner(pg_url, "0031", downgrade=True)
    run = asyncio.run
    run(
        _rows(
            pg_url,
            "INSERT INTO price_books (id, owner_id, currency, version) "
            f"VALUES ('{_BOOK}', '{_OWNER}', 'USD', 4)",
        )
    )
    insert = (
        "INSERT INTO price_book_entries (price_book_id, order_index, material, "
        "profile, unit, stock_length_ft, sheet, price_cents) VALUES "
    )
    bundle = (
        f"('{_BOOK}', 2, 'asphalt_shingle', 'shingle_architectural', 'each', "
        "NULL, NULL, 3998)"
    )
    run(
        _rows(
            pg_url,
            insert + f"('{_BOOK}', 0, 'osb', 'osb_7_16', 'each', NULL, '4x8', 2198), "
            f"('{_BOOK}', 1, 'pvc', 'vinyl_d4', 'square', NULL, NULL, 13900)",
        )
    )
    with pytest.raises(IntegrityError):  # 0031 has no Each bundle
        run(_rows(pg_url, insert + bundle))
    every = (
        "SELECT order_index, material, profile, unit, stock_length_ft, sheet, "
        "price_cents FROM price_book_entries "
        f"WHERE price_book_id = '{_BOOK}' ORDER BY order_index"
    )
    before = run(_rows(pg_url, every))
    alembic_runner(pg_url, "0032")
    assert run(_rows(pg_url, every)) == before
    run(
        _rows(
            pg_url,
            insert
            + bundle
            + ", "
            + f"('{_BOOK}', 3, 'polypropylene', 'underlayment_synthetic', 'each', "
            "NULL, NULL, 15900), "
            f"('{_BOOK}', 4, 'aluminium_3105', 'drip_edge', 'each', 10, NULL, 898), "
            f"('{_BOOK}', 5, 'asphalt_shingle', 'ridge_cap', 'linear_foot', NULL, "
            "NULL, 275), "
            f"('{_BOOK}', 6, 'spf_lumber', 'us_1x10', 'each', 14, NULL, 2498)",
        )
    )
    for bad in (
        "7, 'asphalt_shingle', 'shingle_architectural', 'each', 8, NULL, 1",
        "7, 'polypropylene', 'underlayment_synthetic', 'each', NULL, '4x8', 1",
        "7, 'aluminium_3105', 'drip_edge', 'each', NULL, NULL, 1",  # a stick
    ):
        with pytest.raises(IntegrityError):
            run(_rows(pg_url, f"{insert}('{_BOOK}', {bad})"))

    alembic_runner(pg_url, "0031", downgrade=True)
    assert run(_rows(pg_url, every)) == before
    version = "SELECT version FROM price_books WHERE id = '" + _BOOK + "'"
    assert run(_rows(pg_url, version)) == [(5,)]
    alembic_runner(pg_url, "head")
    assert run(_rows(pg_url, every)) == before
    run(_rows(pg_url, insert + bundle))
    run(_rows(pg_url, f"DELETE FROM price_books WHERE id = '{_BOOK}'"))
