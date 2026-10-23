"""documents alembic 0026 (BODY-NAMES): ``parts.body_names``, offline DDL and
a real up/down/up on a populated Postgres. Split from ``test_migrations.py``
(the file-size limit); same two layers, same fixtures."""

import asyncio
import io
from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

_OWNER = "6f3f6b64-0000-4000-8000-0000000260cc"


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


async def _scalar_rows(url: str, statement: str) -> list[tuple[object, ...]]:
    engine = create_async_engine(async_dsn(url))
    try:
        async with engine.begin() as connection:
            result = await connection.execute(sa.text(statement))
            return [tuple(row) for row in result] if result.returns_rows else []
    finally:
        await engine.dispose()


def test_0026_offline_sql_adds_nullable_body_names(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0025:0026")
    # Nullable with no default: catalog-only, every part reads "no rename".
    assert "ALTER TABLE parts ADD COLUMN body_names JSONB;" in sql
    assert "UPDATE " not in sql.replace("UPDATE alembic_version", "")


def test_0026_offline_downgrade_drops_body_names(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0026:0025", downgrade=True)
    assert "ALTER TABLE parts DROP COLUMN body_names" in sql


_NAMED_PART = "6f3f6b64-0000-4000-8000-0000000260aa"


def test_0026_up_down_up_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """BODY-NAMES: an existing part comes through byte-for-byte and reads no
    rename; a rename list round-trips as JSONB; the downgrade drops only the
    column; the upgrade applies again."""
    alembic_runner(pg_url, "0025", downgrade=True)
    run = asyncio.run
    run(
        _scalar_rows(
            pg_url,
            "INSERT INTO parts (id, owner_id, name, tree_version, materials) "
            f"VALUES ('{_NAMED_PART}', '{_OWNER}', 'B7 house', 7, "
            '\'{"default_material": "spf_lumber", "bodies": []}\')',
        )
    )
    parts = (
        "SELECT id, owner_id, name, tree_version, materials::text, updated_at "
        f"FROM parts WHERE id = '{_NAMED_PART}'"
    )
    before = run(_scalar_rows(pg_url, parts))

    alembic_runner(pg_url, "0026")
    assert run(_scalar_rows(pg_url, parts)) == before
    names = f"SELECT body_names FROM parts WHERE id = '{_NAMED_PART}'"
    assert run(_scalar_rows(pg_url, names)) == [(None,)]
    stored = (
        '[{"base_feature_id": "6f3f6b64-0000-4000-8000-0000000260bb", '
        '"name": "Front wall · Stud 3"}]'
    )
    run(
        _scalar_rows(
            pg_url,
            f"UPDATE parts SET body_names = '{stored}'::jsonb "
            f"WHERE id = '{_NAMED_PART}'",
        )
    )
    assert run(
        _scalar_rows(
            pg_url,
            f"SELECT body_names -> 0 ->> 'name' FROM parts WHERE id = '{_NAMED_PART}'",
        )
    ) == [("Front wall · Stud 3",)]

    alembic_runner(pg_url, "0025", downgrade=True)
    column = (
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'parts' AND column_name = 'body_names'"
    )
    assert run(_scalar_rows(pg_url, column)) == []
    assert run(_scalar_rows(pg_url, parts)) == before
    alembic_runner(pg_url, "head")
    assert run(_scalar_rows(pg_url, column)) == [("body_names",)]
    assert run(_scalar_rows(pg_url, names)) == [(None,)]
    run(_scalar_rows(pg_url, f"DELETE FROM parts WHERE id = '{_NAMED_PART}'"))
