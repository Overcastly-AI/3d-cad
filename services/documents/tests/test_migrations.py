"""documents alembic tree — offline DDL correctness + real apply/downgrade.

Two layers, per the design doc's §5 plan:

- **Offline render (no DB, always runs):** ``alembic upgrade --sql`` through
  the shared py-kit env, asserting the Postgres-only clauses of
  ``0002_feature_tree`` that the SQLite test dialect cannot express
  (documents/db.py) render exactly as docs/design/feature-tree.md §1.2
  specifies — the deferrable unique, the deferred NO ACTION target FK
  (review-log 🔴 fix), the composite rollback FK with its Postgres-15+
  ``SET NULL`` column list, and the reverse-lookup index.
- **Real apply/downgrade:** against the scratch PostgreSQL server from
  conftest.py (skips with a reason when unavailable): base → head → base →
  head, asserting the tables/columns appear and disappear.
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
from sqlalchemy.ext.asyncio import create_async_engine


def _offline_sql(
    alembic_ini: Path,
    monkeypatch: pytest.MonkeyPatch,
    revision_range: str,
    *,
    downgrade: bool = False,
) -> str:
    """Render migrations offline (``--sql``) — no database involved."""
    # Offline mode only needs a URL for dialect selection; nothing connects.
    monkeypatch.setenv("POSTGRES_URL", "postgresql://loft:unused@db.invalid/loft")
    buffer = io.StringIO()
    config = Config(str(alembic_ini), output_buffer=buffer)
    if downgrade:
        command.downgrade(config, revision_range, sql=True)
    else:
        command.upgrade(config, revision_range, sql=True)
    return buffer.getvalue()


def test_0002_offline_sql_matches_design_ddl(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0001:0002")

    # §1.2 — deferrable unique so renumber shuffles are legal in-transaction.
    assert (
        "CONSTRAINT uq_features_part_order UNIQUE (part_id, order_index) "
        "DEFERRABLE INITIALLY DEFERRED" in sql
    )
    # §2.2 rule 1 — composite-FK target pinning (part_id, id).
    assert "CONSTRAINT uq_features_part_id UNIQUE (part_id, id)" in sql
    # §2.3 (review-log 🔴 fix) — deferred NO ACTION backstop, NOT RESTRICT:
    # whole-part CASCADE deletes must pass the commit-time check.
    assert (
        "CONSTRAINT fk_feature_deps_target FOREIGN KEY(part_id, "
        "references_feature_id) REFERENCES features (part_id, id) "
        "ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED" in sql
    )
    assert "ON DELETE RESTRICT" not in sql
    # §1.2 — parts→features cascade + same-part edge cascade.
    assert "REFERENCES parts (id) ON DELETE CASCADE" in sql
    assert (
        "CONSTRAINT fk_feature_deps_feature FOREIGN KEY(part_id, feature_id) "
        "REFERENCES features (part_id, id) ON DELETE CASCADE" in sql
    )
    # §1.2 — reverse-lookup index (Postgres does not auto-index FK sources).
    assert (
        "CREATE INDEX ix_feature_deps_target ON feature_dependencies "
        "(references_feature_id)" in sql
    )
    # §1.2 — JSONB params + promoted type/version columns.
    assert "params JSONB NOT NULL" in sql
    assert "param_version INTEGER NOT NULL" in sql
    # §5 op 3/4 — parts columns; composite rollback FK with the
    # Postgres-15+ referencing-column list on SET NULL (stack pins PG 16).
    assert "ADD COLUMN tree_version BIGINT DEFAULT 0 NOT NULL" in sql
    assert "ADD COLUMN rollback_feature_id UUID" in sql
    assert (
        "ADD CONSTRAINT fk_parts_rollback_feature FOREIGN KEY"
        "(id, rollback_feature_id) REFERENCES features (part_id, id) "
        "ON DELETE SET NULL (rollback_feature_id)" in sql
    )
    assert "gen_random_uuid()" in sql


def test_0002_offline_downgrade_drops_everything(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0002:0001", downgrade=True)
    assert "DROP CONSTRAINT fk_parts_rollback_feature" in sql
    assert "DROP COLUMN rollback_feature_id" in sql
    assert "DROP COLUMN tree_version" in sql
    assert "DROP INDEX ix_feature_deps_target" in sql
    assert "DROP TABLE feature_dependencies" in sql
    assert "DROP TABLE features" in sql


def test_0003_offline_sql_matches_design_ddl(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0002:0003")

    # §1.2 — assemblies header: OCC counter + one-name-per-owner unique.
    assert "doc_version BIGINT DEFAULT 0 NOT NULL" in sql
    assert "CONSTRAINT uq_assemblies_owner_name UNIQUE (owner_id, name)" in sql
    # §1.2 — instances: deferrable order unique so renumber shuffles are legal.
    assert (
        "CONSTRAINT uq_instances_assembly_order UNIQUE (assembly_id, order_index) "
        "DEFERRABLE INITIALLY DEFERRED" in sql
    )
    # §1.2 — assembly→instances CASCADE; ref_document_id is NOT an FK.
    assert "REFERENCES assemblies (id) ON DELETE CASCADE" in sql
    assert "FOREIGN KEY(ref_document_id)" not in sql
    assert "ref_pinned_version BIGINT" in sql
    assert "placement JSONB NOT NULL" in sql
    # §1.2 — reverse-lookup index for the cross-document 409 pre-check.
    assert (
        "CREATE INDEX ix_instances_ref_document ON instances (ref_document_id)" in sql
    )
    # §1.2 — mates: plain order unique + JSONB params.
    assert "CONSTRAINT uq_mates_assembly_order UNIQUE (assembly_id, order_index)" in sql
    assert "params JSONB NOT NULL" in sql


def test_0003_offline_downgrade_drops_everything(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0003:0002", downgrade=True)
    assert "DROP TABLE mates" in sql
    assert "DROP INDEX ix_instances_ref_document" in sql
    assert "DROP TABLE instances" in sql
    assert "DROP TABLE assemblies" in sql


def test_0004_offline_sql_matches_design_ddl(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0003:0004")

    # §2.2 — drawings header: OCC counter + one-name-per-owner unique.
    assert "doc_version BIGINT DEFAULT 0 NOT NULL" in sql
    assert "CONSTRAINT uq_drawings_owner_name UNIQUE (owner_id, name)" in sql
    # §2.2 — sheets: title_block JSONB + plain per-drawing order unique + CASCADE.
    assert "title_block JSONB" in sql
    assert "CONSTRAINT uq_sheets_drawing_order UNIQUE (drawing_id, order_index)" in sql
    assert "REFERENCES drawings (id) ON DELETE CASCADE" in sql
    # §2.2 — views: cross-document ref (NOT an FK), pin-ready column, scalar
    # scale + position columns, reverse-lookup index for the 409 pre-check.
    assert "FOREIGN KEY(ref_document_id)" not in sql
    assert "ref_pinned_version BIGINT" in sql
    assert "CONSTRAINT uq_views_sheet_order UNIQUE (sheet_id, order_index)" in sql
    assert "REFERENCES sheets (id) ON DELETE CASCADE" in sql
    assert "CREATE INDEX ix_views_ref_document ON views (ref_document_id)" in sql
    # §2.2/§3 — dimensions: view_id CASCADE + JSONB params + per-sheet order.
    assert "REFERENCES views (id) ON DELETE CASCADE" in sql
    assert "CONSTRAINT uq_dimensions_sheet_order UNIQUE (sheet_id, order_index)" in sql
    assert "params JSONB NOT NULL" in sql
    # §2.2 — annotations: per-sheet order unique.
    assert "CONSTRAINT uq_annotations_sheet_order UNIQUE (sheet_id, order_index)" in sql


def test_0004_offline_downgrade_drops_everything(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0004:0003", downgrade=True)
    assert "DROP TABLE annotations" in sql
    assert "DROP INDEX ix_dimensions_view" in sql
    assert "DROP TABLE dimensions" in sql
    assert "DROP INDEX ix_views_ref_document" in sql
    assert "DROP TABLE views" in sql
    assert "DROP TABLE sheets" in sql
    assert "DROP TABLE drawings" in sql


def test_0005_offline_sql_adds_length_unit_with_mm_default(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0004:0005")
    # units.md §U1 — NOT NULL display-unit column, server-default 'mm' so every
    # pre-existing row backfills to canonical mm in one statement.
    assert (
        "ALTER TABLE parts ADD COLUMN length_unit VARCHAR(8) DEFAULT 'mm' NOT NULL"
        in sql
    )
    assert (
        "ALTER TABLE assemblies ADD COLUMN length_unit VARCHAR(8) DEFAULT 'mm' NOT NULL"
        in sql
    )


def test_0005_offline_downgrade_drops_length_unit(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0005:0004", downgrade=True)
    assert "ALTER TABLE assemblies DROP COLUMN length_unit" in sql
    assert "ALTER TABLE parts DROP COLUMN length_unit" in sql


def test_0006_offline_sql_creates_part_snapshots(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0005:0006")
    # undo-redo.md UR1 — the bounded snapshot ring: (part_id, seq) natural PK
    # (its backing index serves every history scan), JSONB full-state payload,
    # part-scoped CASCADE.
    assert "CREATE TABLE part_snapshots" in sql
    assert "seq BIGINT NOT NULL" in sql
    assert "state JSONB NOT NULL" in sql
    assert "CONSTRAINT pk_part_snapshots PRIMARY KEY (part_id, seq)" in sql
    assert (
        "CONSTRAINT fk_part_snapshots_part FOREIGN KEY(part_id) "
        "REFERENCES parts (id) ON DELETE CASCADE" in sql
    )
    # The cursor: NULLable (NULL = history never seeded), app-maintained.
    assert "ALTER TABLE parts ADD COLUMN history_cursor BIGINT" in sql


def test_0006_offline_downgrade_drops_everything(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0006:0005", downgrade=True)
    assert "ALTER TABLE parts DROP COLUMN history_cursor" in sql
    assert "DROP TABLE part_snapshots" in sql


def test_0007_offline_sql_creates_assembly_snapshots(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0006:0007")
    # undo-redo.md UR3 — the assembly ring, mirroring 0006's part ring:
    # (assembly_id, seq) natural PK, JSONB full-state payload, assembly-scoped
    # CASCADE.
    assert "CREATE TABLE assembly_snapshots" in sql
    assert "seq BIGINT NOT NULL" in sql
    assert "state JSONB NOT NULL" in sql
    assert "CONSTRAINT pk_assembly_snapshots PRIMARY KEY (assembly_id, seq)" in sql
    assert (
        "CONSTRAINT fk_assembly_snapshots_assembly FOREIGN KEY(assembly_id) "
        "REFERENCES assemblies (id) ON DELETE CASCADE" in sql
    )
    # The cursor: NULLable (NULL = history never seeded), app-maintained.
    assert "ALTER TABLE assemblies ADD COLUMN history_cursor BIGINT" in sql


def test_0007_offline_downgrade_drops_everything(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0007:0006", downgrade=True)
    assert "ALTER TABLE assemblies DROP COLUMN history_cursor" in sql
    assert "DROP TABLE assembly_snapshots" in sql


async def _table_names(url: str) -> set[str]:
    engine = create_async_engine(async_dsn(url))
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            return {row[0] for row in result}
    finally:
        await engine.dispose()


def test_migrations_apply_and_downgrade_on_real_postgres(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """head → base → head against a real PostgreSQL 16 (conftest fixture —
    ``pg_url`` databases are cloned from the migrated template, so arriving
    here at head IS the apply evidence)."""
    assert asyncio.run(_table_names(pg_url)) >= {
        "parts",
        "features",
        "feature_dependencies",
        "assemblies",
        "instances",
        "mates",
        "drawings",
        "sheets",
        "views",
        "dimensions",
        "annotations",
        "part_snapshots",
        "assembly_snapshots",
        "alembic_version",
    }

    alembic_runner(pg_url, "base", downgrade=True)
    remaining = asyncio.run(_table_names(pg_url))
    assert "assembly_snapshots" not in remaining
    assert "part_snapshots" not in remaining
    assert "features" not in remaining
    assert "feature_dependencies" not in remaining
    assert "parts" not in remaining  # 0001 downgrade too
    assert "assemblies" not in remaining
    assert "instances" not in remaining
    assert "mates" not in remaining
    assert "drawings" not in remaining
    assert "sheets" not in remaining
    assert "views" not in remaining
    assert "dimensions" not in remaining
    assert "annotations" not in remaining

    alembic_runner(pg_url, "head")
    assert asyncio.run(_table_names(pg_url)) >= {
        "parts",
        "features",
        "feature_dependencies",
        "assemblies",
        "instances",
        "mates",
        "drawings",
        "sheets",
        "views",
        "dimensions",
        "annotations",
        "part_snapshots",
        "assembly_snapshots",
    }
