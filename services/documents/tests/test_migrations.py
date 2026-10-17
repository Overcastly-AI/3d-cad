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
from sqlalchemy.exc import IntegrityError
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


def test_0009_offline_sql_adds_suppressed_with_false_default(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0008:0009")
    # feature-tree.md §4.3a — NOT NULL suppress flag, server-default false so
    # every pre-existing feature backfills to unsuppressed in one statement.
    assert (
        "ALTER TABLE features ADD COLUMN suppressed BOOLEAN DEFAULT false NOT NULL"
        in sql
    )


def test_0009_offline_downgrade_drops_suppressed(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0009:0008", downgrade=True)
    assert "ALTER TABLE features DROP COLUMN suppressed" in sql


def test_0010_offline_sql_adds_auto_place_with_true_default(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0009:0010")
    # drawing-export.md §4.2 — NOT NULL drag-to-place flag, server-default true so
    # every pre-existing view backfills to bounds-aware auto-layout in one statement.
    assert (
        "ALTER TABLE views ADD COLUMN auto_place BOOLEAN DEFAULT true NOT NULL" in sql
    )


def test_0010_offline_downgrade_drops_auto_place(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0010:0009", downgrade=True)
    assert "ALTER TABLE views DROP COLUMN auto_place" in sql


def test_0011_offline_sql_dedupes_then_adds_projection_unique(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0010:0011")
    # audit H3 — the invariant the compose layer + frontend already assumed.
    assert (
        "ADD CONSTRAINT uq_views_sheet_projection UNIQUE (sheet_id, projection)" in sql
    )
    # Pre-existing duplicates are dropped (lowest order_index per projection kept)
    # BEFORE the constraint, else the ALTER would fail on real data...
    dedupe = sql.index("DELETE FROM views")
    assert "PARTITION BY sheet_id, projection ORDER BY order_index, id" in sql
    # ...and the holes that leaves are renumbered dense (the append position is
    # count(*)), parked out of range first so no row collides mid-statement.
    park = sql.index("order_index + 1000000")
    renumber = sql.index("PARTITION BY sheet_id ORDER BY order_index, id")
    constraint = sql.index("uq_views_sheet_projection")
    assert dedupe < park < renumber < constraint


def test_0011_offline_downgrade_drops_projection_unique(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0011:0010", downgrade=True)
    assert "DROP CONSTRAINT uq_views_sheet_projection" in sql


def test_0012_offline_sql_adds_the_nullable_last_evaluate_record(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0011:0012")
    # feature-tree.md §4.4a — three NULLABLE columns; all-NULL IS the "never
    # evaluated" state, so there is deliberately NO server default to invent a
    # verdict for a part nobody ever evaluated.
    assert "ALTER TABLE parts ADD COLUMN last_eval_status VARCHAR(16)" in sql
    assert "ALTER TABLE parts ADD COLUMN last_eval_at TIMESTAMP WITH TIME ZONE" in sql
    assert "ALTER TABLE parts ADD COLUMN last_eval_tree_version BIGINT" in sql
    assert "NOT NULL" not in sql
    assert "DEFAULT" not in sql
    # The version stamp is what makes staleness DERIVABLE rather than assumed;
    # a status column on its own would be the stored-BOM-number failure mode.
    assert sql.index("last_eval_status") < sql.index("last_eval_tree_version")


def test_0012_offline_downgrade_drops_the_record(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0012:0011", downgrade=True)
    assert "ALTER TABLE parts DROP COLUMN last_eval_tree_version" in sql
    assert "ALTER TABLE parts DROP COLUMN last_eval_at" in sql
    assert "ALTER TABLE parts DROP COLUMN last_eval_status" in sql


def test_0014_offline_sql_adds_the_nullable_scope(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0013:0014")
    assert "ALTER TABLE parts ADD COLUMN last_eval_scope VARCHAR(16)" in sql
    # No backfill and no default: a row written before the column existed does
    # not know its scope, and defaulting it to 'whole' would re-create the
    # over-claim (audit J3) the column exists to prevent.
    assert "NOT NULL" not in sql
    assert "DEFAULT" not in sql
    assert "UPDATE parts" not in sql


def test_0014_offline_downgrade_drops_the_scope(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0014:0013", downgrade=True)
    assert "ALTER TABLE parts DROP COLUMN last_eval_scope" in sql


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


def test_0015_offline_sql_renders_the_partial_uniques(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#WS2 — the folder tree, and per-FOLDER document name uniqueness.

    The assertions worth having here are the PARTIAL predicates. Uniqueness that
    only covers filed documents would silently permit two unfiled "Bracket"s
    (SQL treats NULLs as distinct), which is the state most documents are in;
    the ``WHERE folder_id IS NULL`` half is the one that closes it, and it is
    invisible from the ORM metadata alone.
    """
    sql = _offline_sql(alembic_ini, monkeypatch, "0014:0015")

    # The tree: self-FK, RESTRICT so a folder delete can never take a folder
    # with it, and sibling-name uniqueness split over the NULL boundary.
    assert "CREATE TABLE folders" in sql
    assert (
        "CONSTRAINT fk_folders_parent FOREIGN KEY(parent_id) REFERENCES folders (id) "
        "ON DELETE RESTRICT" in sql
    )
    assert (
        "CREATE UNIQUE INDEX uq_folders_parent_name ON folders "
        "(owner_id, kind, parent_id, name) WHERE parent_id IS NOT NULL" in sql
    )
    assert (
        "CREATE UNIQUE INDEX uq_folders_root_name ON folders (owner_id, kind, name) "
        "WHERE parent_id IS NULL" in sql
    )

    for table in ("parts", "assemblies", "drawings"):
        assert f"ALTER TABLE {table} ADD COLUMN folder_id UUID" in sql
        # RESTRICT: the DB backstop behind the 409-with-contents refusal.
        assert (
            f"ALTER TABLE {table} ADD CONSTRAINT fk_{table}_folder "
            "FOREIGN KEY(folder_id) REFERENCES folders (id) ON DELETE RESTRICT" in sql
        )
        # The old per-owner rule goes; the per-folder PAIR replaces it.
        assert f"ALTER TABLE {table} DROP CONSTRAINT" in sql
        assert (
            f"CREATE UNIQUE INDEX uq_{table}_folder_name ON {table} "
            "(owner_id, folder_id, name) WHERE folder_id IS NOT NULL" in sql
        )
        assert (
            f"CREATE UNIQUE INDEX uq_{table}_unfiled_name ON {table} (owner_id, name) "
            "WHERE folder_id IS NULL" in sql
        )
        # The owner-scoped list scan the dropped constraint used to serve.
        assert f"CREATE INDEX ix_{table}_owner ON {table} (owner_id)" in sql


def test_0015_offline_downgrade_restores_the_owner_unique(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0015:0014", downgrade=True)
    assert "DROP TABLE folders" in sql
    for table in ("parts", "assemblies", "drawings"):
        assert f"DROP INDEX uq_{table}_folder_name" in sql
        assert f"ALTER TABLE {table} DROP COLUMN folder_id" in sql
        assert (
            f"ALTER TABLE {table} ADD CONSTRAINT uq_{table}_owner_name "
            "UNIQUE (owner_id, name)" in sql
        )


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
        "part_versions",
        "folders",
        "alembic_version",
    }

    alembic_runner(pg_url, "base", downgrade=True)
    remaining = asyncio.run(_table_names(pg_url))
    assert "folders" not in remaining
    assert "part_versions" not in remaining
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
        "part_versions",
        "folders",
    }


def test_0016_offline_sql_adds_the_pending_column_and_the_journal(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0015:0016")
    # Nullable, no default: catalog-only, and every existing part is pending.
    assert "ALTER TABLE parts ADD COLUMN ref_names_checked_version BIGINT" in sql
    # The retry backoff: a constant default (catalog-only on Postgres 11+).
    assert (
        "ALTER TABLE parts ADD COLUMN ref_names_attempts INTEGER DEFAULT 0 NOT NULL"
        in sql
    )
    assert (
        "ALTER TABLE parts ADD COLUMN ref_names_next_try_at TIMESTAMP WITH TIME ZONE"
        in sql
    )
    assert "UPDATE parts" not in sql
    assert "CREATE TABLE ref_name_backfills" in sql
    assert "REFERENCES parts (id) ON DELETE CASCADE" in sql
    assert "params_before JSONB NOT NULL" in sql
    assert "CREATE INDEX ix_ref_name_backfills_part_id" in sql


def test_0016_offline_downgrade_drops_both(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0016:0015", downgrade=True)
    assert "DROP TABLE ref_name_backfills" in sql
    assert "ALTER TABLE parts DROP COLUMN ref_names_checked_version" in sql
    assert "ALTER TABLE parts DROP COLUMN ref_names_attempts" in sql
    assert "ALTER TABLE parts DROP COLUMN ref_names_next_try_at" in sql


async def _scalar_rows(url: str, statement: str) -> list[tuple[object, ...]]:
    engine = create_async_engine(async_dsn(url))
    try:
        async with engine.begin() as connection:
            result = await connection.execute(sa.text(statement))
            return [tuple(row) for row in result] if result.returns_rows else []
    finally:
        await engine.dispose()


_PART = "6f3f6b64-0000-4000-8000-0000000160aa"
_OWNER = "6f3f6b64-0000-4000-8000-0000000160bb"
_FEATURE = "6f3f6b64-0000-4000-8000-0000000160cc"
_PARAMS = (
    '{"plane": {"kind": "datum_plane", "plane": "XY"}, '
    '"entities": [], "constraints": []}'
)


def test_0016_up_and_down_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """DESIGN-INTENT-BACKFILL: 0016 against real rows, both directions. The
    part and its feature must come through byte-for-byte, the part must read
    as pending after the upgrade, a journal row must cascade with its part,
    and the downgrade must remove exactly what the upgrade added."""
    alembic_runner(pg_url, "0015", downgrade=True)
    run = asyncio.run
    run(
        _scalar_rows(
            pg_url,
            "INSERT INTO parts (id, owner_id, name, tree_version) "
            f"VALUES ('{_PART}', '{_OWNER}', 'Old bracket', 7)",
        )
    )
    run(
        _scalar_rows(
            pg_url,
            "INSERT INTO features (id, part_id, order_index, name, type, "
            "param_version, params) VALUES "
            f"('{_FEATURE}', '{_PART}', 0, 'Sketch1', 'sketch', 1, '{_PARAMS}')",
        )
    )
    snapshot = "SELECT id, owner_id, name, tree_version, updated_at FROM parts"
    features = "SELECT id, params::text, param_version, updated_at FROM features"
    parts_before = run(_scalar_rows(pg_url, snapshot))
    features_before = run(_scalar_rows(pg_url, features))

    alembic_runner(pg_url, "0016")
    assert run(_scalar_rows(pg_url, snapshot)) == parts_before
    assert run(_scalar_rows(pg_url, features)) == features_before
    assert run(
        _scalar_rows(
            pg_url, "SELECT ref_names_attempts, ref_names_next_try_at FROM parts"
        )
    ) == [(0, None)]
    assert run(_scalar_rows(pg_url, "SELECT ref_names_checked_version FROM parts")) == [
        (None,)
    ]
    run(
        _scalar_rows(
            pg_url,
            "INSERT INTO ref_name_backfills (id, part_id, kind, trigger, "
            "tree_version_before, tree_version_after, params_before, params_after) "
            f"VALUES (gen_random_uuid(), '{_PART}', 'backfill', 'open', 7, 8, "
            "'{}', '{}')",
        )
    )
    assert run(_scalar_rows(pg_url, "SELECT count(*) FROM ref_name_backfills")) == [
        (1,)
    ]

    alembic_runner(pg_url, "0015", downgrade=True)
    assert "ref_name_backfills" not in run(_table_names(pg_url))
    columns = run(
        _scalar_rows(
            pg_url,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'parts'",
        )
    )
    for column in (
        "ref_names_checked_version",
        "ref_names_attempts",
        "ref_names_next_try_at",
    ):
        assert (column,) not in columns
    assert run(_scalar_rows(pg_url, snapshot)) == parts_before
    assert run(_scalar_rows(pg_url, features)) == features_before

    alembic_runner(pg_url, "head")
    run(
        _scalar_rows(
            pg_url,
            "INSERT INTO ref_name_backfills (id, part_id, kind, "
            "tree_version_before, tree_version_after, params_before, params_after) "
            f"VALUES (gen_random_uuid(), '{_PART}', 'backfill', 7, 8, '{{}}', '{{}}')",
        )
    )
    run(_scalar_rows(pg_url, f"DELETE FROM parts WHERE id = '{_PART}'"))
    assert run(_scalar_rows(pg_url, "SELECT count(*) FROM ref_name_backfills")) == [
        (0,)
    ]


def test_0017_offline_sql_creates_part_versions(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0016:0017")
    assert "CREATE TABLE part_versions" in sql
    assert "REFERENCES parts (id) ON DELETE CASCADE" in sql
    assert "tree JSONB NOT NULL" in sql
    assert "seq BIGINT NOT NULL" in sql
    assert "message VARCHAR(2000) DEFAULT '' NOT NULL" in sql
    assert "author VARCHAR(80)" in sql
    assert "CONSTRAINT uq_part_versions_part_seq UNIQUE (part_id, seq)" in sql
    # Additive only: no existing table is altered or rewritten.
    assert "ALTER TABLE" not in sql
    assert "UPDATE " not in sql.replace("UPDATE alembic_version", "")


def test_0017_offline_downgrade_drops_part_versions(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0017:0016", downgrade=True)
    assert "DROP TABLE part_versions" in sql
    assert "ALTER TABLE" not in sql


_VERSION_PART = "6f3f6b64-0000-4000-8000-0000000170aa"


def test_0017_up_and_down_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """LOFT-VERSIONS: 0017 against real rows, both directions. Existing parts and
    features come through byte-for-byte; a version row stores, keeps its seq
    unique per part and cascades with its part; the downgrade drops exactly the
    table."""
    alembic_runner(pg_url, "0016", downgrade=True)
    run = asyncio.run
    run(
        _scalar_rows(
            pg_url,
            "INSERT INTO parts (id, owner_id, name, tree_version) "
            f"VALUES ('{_VERSION_PART}', '{_OWNER}', 'Old bracket', 3)",
        )
    )
    run(
        _scalar_rows(
            pg_url,
            "INSERT INTO features (id, part_id, order_index, name, type, "
            "param_version, params) VALUES "
            f"('{_FEATURE}', '{_VERSION_PART}', 0, 'Sketch1', 'sketch', 1, "
            f"'{_PARAMS}')",
        )
    )
    snapshot = "SELECT id, owner_id, name, tree_version, updated_at FROM parts"
    features = "SELECT id, params::text, param_version, updated_at FROM features"
    parts_before = run(_scalar_rows(pg_url, snapshot))
    features_before = run(_scalar_rows(pg_url, features))

    alembic_runner(pg_url, "0017")
    assert run(_scalar_rows(pg_url, snapshot)) == parts_before
    assert run(_scalar_rows(pg_url, features)) == features_before
    insert = (
        "INSERT INTO part_versions (id, part_id, seq, name, tree, tree_sha256, "
        "size_bytes, feature_count) VALUES (gen_random_uuid(), "
        f"'{_VERSION_PART}', 1, 'Rev A', '{{}}', '{'0' * 64}', 2, 0)"
    )
    run(_scalar_rows(pg_url, insert))
    assert run(
        _scalar_rows(pg_url, "SELECT seq, message, author FROM part_versions")
    ) == [(1, "", None)]
    with pytest.raises(IntegrityError):
        run(_scalar_rows(pg_url, insert))  # (part_id, seq) is unique

    alembic_runner(pg_url, "0016", downgrade=True)
    assert "part_versions" not in run(_table_names(pg_url))
    assert run(_scalar_rows(pg_url, snapshot)) == parts_before
    assert run(_scalar_rows(pg_url, features)) == features_before

    alembic_runner(pg_url, "head")
    run(_scalar_rows(pg_url, insert))
    run(_scalar_rows(pg_url, f"DELETE FROM parts WHERE id = '{_VERSION_PART}'"))
    assert run(_scalar_rows(pg_url, "SELECT count(*) FROM part_versions")) == [(0,)]


def test_0018_offline_sql_adds_parameters_and_expressions(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0017:0018")
    # A constant default: catalog-only on Postgres 11+, every part reads [].
    assert "ALTER TABLE parts ADD COLUMN parameters JSONB DEFAULT '[]' NOT NULL" in sql
    assert "ALTER TABLE features ADD COLUMN expressions JSONB" in sql
    assert "expressions JSONB NOT NULL" not in sql
    assert "UPDATE " not in sql.replace("UPDATE alembic_version", "")


def test_0018_offline_downgrade_drops_both_columns(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0018:0017", downgrade=True)
    assert "ALTER TABLE features DROP COLUMN expressions" in sql
    assert "ALTER TABLE parts DROP COLUMN parameters" in sql


_PARAMETER_PART = "6f3f6b64-0000-4000-8000-0000000180aa"
_PARAMETER_FEATURE = "6f3f6b64-0000-4000-8000-0000000180cc"


def test_0018_up_down_up_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """PART-PARAMETERS: 0018 against real rows. Existing parts and features
    come through byte-for-byte and read an empty table and no expressions; a
    stored table round-trips as JSONB; the downgrade drops exactly the two
    columns; and the upgrade applies again."""
    alembic_runner(pg_url, "0017", downgrade=True)
    run = asyncio.run
    run(
        _scalar_rows(
            pg_url,
            "INSERT INTO parts (id, owner_id, name, tree_version) "
            f"VALUES ('{_PARAMETER_PART}', '{_OWNER}', 'Old plate', 4)",
        )
    )
    run(
        _scalar_rows(
            pg_url,
            "INSERT INTO features (id, part_id, order_index, name, type, "
            "param_version, params) VALUES "
            f"('{_PARAMETER_FEATURE}', '{_PARAMETER_PART}', 0, 'Sketch1', "
            f"'sketch', 1, '{_PARAMS}')",
        )
    )
    parts = "SELECT id, owner_id, name, tree_version, updated_at FROM parts"
    features = "SELECT id, params::text, param_version, updated_at FROM features"
    parts_before = run(_scalar_rows(pg_url, parts))
    features_before = run(_scalar_rows(pg_url, features))

    alembic_runner(pg_url, "0018")
    assert run(_scalar_rows(pg_url, parts)) == parts_before
    assert run(_scalar_rows(pg_url, features)) == features_before
    assert run(_scalar_rows(pg_url, "SELECT parameters::text FROM parts")) == [("[]",)]
    assert run(_scalar_rows(pg_url, "SELECT expressions FROM features")) == [(None,)]
    table = (
        '[{"id": "6f3f6b64-0000-4000-8000-0000000180dd", "name": "w", '
        '"expression": "40", "unit": "length", "comment": "", "value": 40.0}]'
    )
    run(
        _scalar_rows(
            pg_url,
            f"UPDATE parts SET parameters = '{table}'::jsonb "
            f"WHERE id = '{_PARAMETER_PART}'",
        )
    )
    run(
        _scalar_rows(
            pg_url,
            'UPDATE features SET expressions = \'{"/distance_mm": "w"}\'::jsonb',
        )
    )
    assert run(
        _scalar_rows(pg_url, "SELECT parameters -> 0 ->> 'expression' FROM parts")
    ) == [("40",)]
    with pytest.raises(IntegrityError):  # NOT NULL
        run(_scalar_rows(pg_url, "UPDATE parts SET parameters = NULL"))

    alembic_runner(pg_url, "0017", downgrade=True)
    columns = (
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE (table_name = 'parts' AND column_name = 'parameters') "
        "OR (table_name = 'features' AND column_name = 'expressions')"
    )
    assert run(_scalar_rows(pg_url, columns)) == []
    assert run(_scalar_rows(pg_url, features)) == features_before
    assert run(
        _scalar_rows(pg_url, "SELECT id, owner_id, name, tree_version FROM parts")
    ) == [(row[0], row[1], row[2], row[3]) for row in parts_before]

    alembic_runner(pg_url, "head")
    assert sorted(run(_scalar_rows(pg_url, columns))) == [
        ("features", "expressions"),
        ("parts", "parameters"),
    ]
    assert run(_scalar_rows(pg_url, "SELECT parameters::text FROM parts")) == [("[]",)]


def test_0019_offline_sql_creates_assembly_patterns(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0018:0019")
    assert "CREATE TABLE assembly_patterns" in sql
    assert "REFERENCES assemblies (id) ON DELETE CASCADE" in sql
    assert "params JSONB NOT NULL" in sql
    assert "driven_count INTEGER" in sql
    assert "driven_count INTEGER NOT NULL" not in sql
    assert (
        "CONSTRAINT uq_assembly_patterns_order UNIQUE (assembly_id, order_index)" in sql
    )
    # Additive only: no existing table is altered or rewritten.
    assert "ALTER TABLE" not in sql
    assert "UPDATE " not in sql.replace("UPDATE alembic_version", "")


def test_0019_offline_downgrade_drops_assembly_patterns(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0019:0018", downgrade=True)
    assert "DROP TABLE assembly_patterns" in sql
    assert "ALTER TABLE" not in sql


_PATTERN_ASSEMBLY = "6f3f6b64-0000-4000-8000-0000000190aa"
_PATTERN_INSTANCE = "6f3f6b64-0000-4000-8000-0000000190bb"
_PATTERN_MATE = "6f3f6b64-0000-4000-8000-0000000190cc"


def test_0019_up_down_up_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """ASM-A3-PATTERN: 0019 against real rows. An existing assembly, its
    instance, mate and history snapshot come through byte-for-byte; a pattern
    row stores, keeps its order unique per assembly and cascades with its
    assembly; the downgrade drops exactly the table; the upgrade applies
    again."""
    alembic_runner(pg_url, "0018", downgrade=True)
    run = asyncio.run
    placement = '{"position": {"x": 0, "y": 0, "z": 0}}'
    for statement in (
        "INSERT INTO assemblies (id, owner_id, name, doc_version) "
        f"VALUES ('{_PATTERN_ASSEMBLY}', '{_OWNER}', 'Old stage', 4)",
        "INSERT INTO instances (id, assembly_id, ref_document_id, "
        "ref_document_kind, name, placement, order_index) VALUES "
        f"('{_PATTERN_INSTANCE}', '{_PATTERN_ASSEMBLY}', gen_random_uuid(), "
        f"'part', 'Rail <1>', '{placement}', 0)",
        "INSERT INTO mates (id, assembly_id, order_index, type, params) VALUES "
        f"('{_PATTERN_MATE}', '{_PATTERN_ASSEMBLY}', 0, 'lock', "
        f'\'{{"type": "lock", "a_instance_id": "{_PATTERN_INSTANCE}", '
        f'"b_instance_id": "{_PATTERN_INSTANCE}"}}\')',
        "INSERT INTO assembly_snapshots (assembly_id, seq, state) VALUES "
        f"('{_PATTERN_ASSEMBLY}', 1, '{{\"instances\": [], \"mates\": []}}')",
    ):
        run(_scalar_rows(pg_url, statement))
    reads = (
        "SELECT id, name, doc_version, updated_at FROM assemblies",
        "SELECT id, name, placement::text, order_index, updated_at FROM instances",
        "SELECT id, params::text, updated_at FROM mates",
        "SELECT seq, state::text FROM assembly_snapshots",
    )
    before = [run(_scalar_rows(pg_url, read)) for read in reads]

    alembic_runner(pg_url, "0019")
    assert [run(_scalar_rows(pg_url, read)) for read in reads] == before
    insert = (
        "INSERT INTO assembly_patterns (assembly_id, order_index, type, params) "
        f"VALUES ('{_PATTERN_ASSEMBLY}', 0, 'linear', '{{\"count\": 3}}')"
    )
    run(_scalar_rows(pg_url, insert))
    assert run(
        _scalar_rows(pg_url, "SELECT type, driven_count FROM assembly_patterns")
    ) == [("linear", None)]
    with pytest.raises(IntegrityError):
        run(_scalar_rows(pg_url, insert))  # (assembly_id, order_index) is unique

    alembic_runner(pg_url, "0018", downgrade=True)
    assert "assembly_patterns" not in run(_table_names(pg_url))
    assert [run(_scalar_rows(pg_url, read)) for read in reads] == before

    alembic_runner(pg_url, "head")
    run(_scalar_rows(pg_url, insert))
    run(
        _scalar_rows(pg_url, f"DELETE FROM assemblies WHERE id = '{_PATTERN_ASSEMBLY}'")
    )
    assert run(_scalar_rows(pg_url, "SELECT count(*) FROM assembly_patterns")) == [(0,)]


def test_0020_offline_sql_adds_clear_title_block_with_false_default(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0019:0020")
    # BIKE2-DRAWING-SCALE: only views a new "Lay out" creates opt in; every stored
    # view backfills to false and composes as it did.
    assert (
        "ALTER TABLE views ADD COLUMN clear_title_block BOOLEAN DEFAULT false NOT NULL"
        in sql
    )


def test_0020_offline_downgrade_drops_clear_title_block(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0020:0019", downgrade=True)
    assert "ALTER TABLE views DROP COLUMN clear_title_block" in sql


_CTB_DRAWING = "6f3f6b64-0000-4000-8000-0000000200aa"
_CTB_SHEET = "6f3f6b64-0000-4000-8000-0000000200bb"


def test_0020_backfills_stored_views_to_false(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """A view stored before 0020 reads back clear_title_block = false (so the
    composer leaves its drawing exactly as it was), with every other column
    untouched; the downgrade drops only the column."""
    alembic_runner(pg_url, "0019", downgrade=True)
    run = asyncio.run
    for statement in (
        "INSERT INTO drawings (id, owner_id, name, doc_version) "
        f"VALUES ('{_CTB_DRAWING}', '{_OWNER}', 'Stored sheet', 2)",
        "INSERT INTO sheets (id, drawing_id, name, size, orientation, projection, "
        f"order_index) VALUES ('{_CTB_SHEET}', '{_CTB_DRAWING}', 'Sheet 1', 'A4', "
        "'landscape', 'third_angle', 0)",
        "INSERT INTO views (id, sheet_id, ref_document_id, ref_document_kind, "
        "projection, scale_num, scale_den, pos_x_mm, pos_y_mm, order_index) VALUES "
        f"(gen_random_uuid(), '{_CTB_SHEET}', gen_random_uuid(), 'part', 'right', "
        "2, 1, 202.0, 75.6, 0)",
    ):
        run(_scalar_rows(pg_url, statement))
    read = (
        "SELECT projection, scale_num, pos_x_mm, pos_y_mm, auto_place, updated_at "
        "FROM views"
    )
    before = run(_scalar_rows(pg_url, read))

    alembic_runner(pg_url, "0020")
    assert run(_scalar_rows(pg_url, read)) == before
    assert run(_scalar_rows(pg_url, "SELECT clear_title_block FROM views")) == [
        (False,)
    ]

    alembic_runner(pg_url, "0019", downgrade=True)
    assert run(_scalar_rows(pg_url, read)) == before
    alembic_runner(pg_url, "head")


def test_0021_offline_sql_creates_assembly_mirrors(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0020:0021")
    assert "CREATE TABLE assembly_mirrors" in sql
    assert "REFERENCES assemblies (id) ON DELETE CASCADE" in sql
    assert "params JSONB NOT NULL" in sql
    assert (
        "CONSTRAINT uq_assembly_mirrors_order UNIQUE (assembly_id, order_index)" in sql
    )
    # Additive only: no existing table is altered or rewritten.
    assert "ALTER TABLE" not in sql
    assert "UPDATE " not in sql.replace("UPDATE alembic_version", "")


def test_0021_offline_downgrade_drops_assembly_mirrors(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0021:0020", downgrade=True)
    assert "DROP TABLE assembly_mirrors" in sql
    assert "ALTER TABLE" not in sql


_MIRROR_ASSEMBLY = "6f3f6b64-0000-4000-8000-0000000210aa"
_MIRROR_INSTANCE = "6f3f6b64-0000-4000-8000-0000000210bb"


def test_0021_up_down_up_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """ASM-MIRROR-COMPONENT: 0021 against real rows. An existing assembly, its
    instance, pattern and history snapshot come through byte-for-byte; a
    mirror row stores, keeps its order unique per assembly and cascades with
    its assembly; the downgrade drops exactly the table; the upgrade applies
    again."""
    alembic_runner(pg_url, "0020", downgrade=True)
    run = asyncio.run
    placement = '{"position": {"x": 0, "y": 0, "z": 0}}'
    for statement in (
        "INSERT INTO assemblies (id, owner_id, name, doc_version) "
        f"VALUES ('{_MIRROR_ASSEMBLY}', '{_OWNER}', 'Old crankset', 3)",
        "INSERT INTO instances (id, assembly_id, ref_document_id, "
        "ref_document_kind, name, placement, order_index) VALUES "
        f"('{_MIRROR_INSTANCE}', '{_MIRROR_ASSEMBLY}', gen_random_uuid(), "
        f"'part', 'Crank arm <1>', '{placement}', 0)",
        "INSERT INTO assembly_patterns (assembly_id, order_index, type, params) "
        f"VALUES ('{_MIRROR_ASSEMBLY}', 0, 'linear', '{{\"count\": 2}}')",
        "INSERT INTO assembly_snapshots (assembly_id, seq, state) VALUES "
        f"('{_MIRROR_ASSEMBLY}', 1, '{{\"instances\": [], \"mates\": []}}')",
    ):
        run(_scalar_rows(pg_url, statement))
    reads = (
        "SELECT id, name, doc_version, updated_at FROM assemblies",
        "SELECT id, name, placement::text, order_index, updated_at FROM instances",
        "SELECT type, params::text, updated_at FROM assembly_patterns",
        "SELECT seq, state::text FROM assembly_snapshots",
    )
    before = [run(_scalar_rows(pg_url, read)) for read in reads]

    alembic_runner(pg_url, "0021")
    assert [run(_scalar_rows(pg_url, read)) for read in reads] == before
    params = (
        f'{{"seed_instance_ids": ["{_MIRROR_INSTANCE}"], '
        '"plane": {"kind": "origin_plane", "plane": "yz"}}'
    )
    insert = (
        "INSERT INTO assembly_mirrors (assembly_id, order_index, params) "
        f"VALUES ('{_MIRROR_ASSEMBLY}', 0, '{params}')"
    )
    run(_scalar_rows(pg_url, insert))
    assert run(
        _scalar_rows(
            pg_url, "SELECT params->>'seed_instance_ids' FROM assembly_mirrors"
        )
    ) == [(f'["{_MIRROR_INSTANCE}"]',)]
    with pytest.raises(IntegrityError):
        run(_scalar_rows(pg_url, insert))  # (assembly_id, order_index) is unique

    alembic_runner(pg_url, "0020", downgrade=True)
    assert "assembly_mirrors" not in run(_table_names(pg_url))
    assert [run(_scalar_rows(pg_url, read)) for read in reads] == before

    alembic_runner(pg_url, "head")
    run(_scalar_rows(pg_url, insert))
    run(_scalar_rows(pg_url, f"DELETE FROM assemblies WHERE id = '{_MIRROR_ASSEMBLY}'"))
    assert run(_scalar_rows(pg_url, "SELECT count(*) FROM assembly_mirrors")) == [(0,)]


def test_0022_offline_sql_creates_price_books(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0021:0022")
    assert "CREATE TABLE price_books" in sql
    assert "CONSTRAINT uq_price_books_owner UNIQUE (owner_id)" in sql
    assert "CREATE TABLE price_book_entries" in sql
    assert "REFERENCES price_books (id) ON DELETE CASCADE" in sql
    # Money is an integer column, never a float or numeric.
    assert "price_cents BIGINT NOT NULL" in sql
    assert "FLOAT" not in sql and "NUMERIC" not in sql and "REAL" not in sql
    assert "CONSTRAINT ck_price_book_entries_price CHECK (price_cents >= 0)" in sql
    assert (
        "CONSTRAINT ck_price_book_entries_stock_length CHECK "
        "((unit = 'each') = (stock_length_ft IS NOT NULL))" in sql
    )
    assert (
        "CONSTRAINT uq_price_book_entries_order UNIQUE (price_book_id, order_index)"
        in sql
    )
    # Additive only: no existing table is altered or rewritten.
    assert "ALTER TABLE" not in sql
    assert "UPDATE " not in sql.replace("UPDATE alembic_version", "")


def test_0022_offline_downgrade_drops_price_books(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0022:0021", downgrade=True)
    assert sql.index("DROP TABLE price_book_entries") < sql.index(
        "DROP TABLE price_books"
    )
    assert "ALTER TABLE" not in sql


_PRICE_PART = "6f3f6b64-0000-4000-8000-0000000220aa"
_PRICE_BOOK = "6f3f6b64-0000-4000-8000-0000000220bb"


def test_0022_up_down_up_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """PRICE-BOOK: 0022 against real rows. An existing part, assembly and
    mirror come through unchanged; a book and its entries store (cents as
    BIGINT, the CHECKs and the one-book-per-owner unique hold, entries cascade
    with their book); the downgrade drops exactly the two tables; the upgrade
    applies again."""
    alembic_runner(pg_url, "0021", downgrade=True)
    run = asyncio.run
    placement = '{"position": {"x": 0, "y": 0, "z": 0}}'
    for statement in (
        "INSERT INTO parts (id, owner_id, name) "
        f"VALUES ('{_PRICE_PART}', '{_OWNER}', 'B1 deck')",
        "INSERT INTO assemblies (id, owner_id, name, doc_version) "
        f"VALUES ('{_MIRROR_ASSEMBLY}', '{_OWNER}', 'Yard', 2)",
        "INSERT INTO instances (id, assembly_id, ref_document_id, "
        "ref_document_kind, name, placement, order_index) VALUES "
        f"('{_MIRROR_INSTANCE}', '{_MIRROR_ASSEMBLY}', '{_PRICE_PART}', "
        f"'part', 'B1 deck <1>', '{placement}', 0)",
        "INSERT INTO assembly_mirrors (assembly_id, order_index, params) "
        f"VALUES ('{_MIRROR_ASSEMBLY}', 0, '{{\"seed_instance_ids\": []}}')",
    ):
        run(_scalar_rows(pg_url, statement))
    reads = (
        "SELECT id, owner_id, name, tree_version, updated_at FROM parts",
        "SELECT id, name, doc_version, updated_at FROM assemblies",
        "SELECT id, name, placement::text, order_index FROM instances",
        "SELECT order_index, params::text, updated_at FROM assembly_mirrors",
    )
    before = [run(_scalar_rows(pg_url, read)) for read in reads]

    alembic_runner(pg_url, "0022")
    assert [run(_scalar_rows(pg_url, read)) for read in reads] == before
    book = (
        "INSERT INTO price_books (id, owner_id, currency) "
        f"VALUES ('{_PRICE_BOOK}', '{_OWNER}', 'USD')"
    )
    entries = (
        "INSERT INTO price_book_entries (price_book_id, order_index, material, "
        "profile, unit, stock_length_ft, price_cents) VALUES "
        f"('{_PRICE_BOOK}', 0, 'southern_pine_pt', 'us_2x10', 'each', 16, 2847), "
        f"('{_PRICE_BOOK}', 1, 'southern_pine_pt', 'us_6x6', 'board_foot', NULL, "
        "145), "
        f"('{_PRICE_BOOK}', 2, 'spf_lumber', 'us_2x8', 'linear_foot', NULL, "
        "9000000000)"
    )
    run(_scalar_rows(pg_url, book))
    run(_scalar_rows(pg_url, entries))
    assert run(
        _scalar_rows(
            pg_url,
            "SELECT unit, stock_length_ft, price_cents FROM price_book_entries "
            "ORDER BY order_index",
        )
    ) == [
        ("each", 16, 2847),
        ("board_foot", None, 145),
        ("linear_foot", None, 9_000_000_000),
    ]
    with pytest.raises(IntegrityError):  # one book per owner
        run(
            _scalar_rows(
                pg_url,
                "INSERT INTO price_books (owner_id, currency) "
                f"VALUES ('{_OWNER}', 'USD')",
            )
        )
    for bad in (
        "0, 'spf_lumber', 'us_2x4', 'each', 8, 1",  # order is unique per book
        "5, 'spf_lumber', 'us_2x4', 'each', 8, -1",  # no negative price
        "5, 'spf_lumber', 'us_2x4', 'each', NULL, 1",  # each needs a length
        "5, 'spf_lumber', 'us_2x4', 'board_foot', 8, 1",  # and only each
    ):
        with pytest.raises(IntegrityError):
            run(
                _scalar_rows(
                    pg_url,
                    "INSERT INTO price_book_entries (price_book_id, order_index, "
                    "material, profile, unit, stock_length_ft, price_cents) "
                    f"VALUES ('{_PRICE_BOOK}', {bad})",
                )
            )

    alembic_runner(pg_url, "0021", downgrade=True)
    tables = run(_table_names(pg_url))
    assert "price_books" not in tables and "price_book_entries" not in tables
    assert [run(_scalar_rows(pg_url, read)) for read in reads] == before

    alembic_runner(pg_url, "head")
    run(_scalar_rows(pg_url, book))
    run(_scalar_rows(pg_url, entries))
    run(_scalar_rows(pg_url, f"DELETE FROM price_books WHERE id = '{_PRICE_BOOK}'"))
    assert run(_scalar_rows(pg_url, "SELECT count(*) FROM price_book_entries")) == [
        (0,)
    ]
    assert [run(_scalar_rows(pg_url, read)) for read in reads] == before


def test_0023_offline_sql_adds_sheets_and_a_version(
    alembic_ini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = _offline_sql(alembic_ini, monkeypatch, "0022:0023")
    assert (
        "ALTER TABLE price_books ADD COLUMN version INTEGER DEFAULT 1 NOT NULL" in sql
    )
    assert "ALTER TABLE price_book_entries ADD COLUMN sheet VARCHAR(8)" in sql
    assert (
        "ALTER TABLE price_book_entries DROP CONSTRAINT "
        "ck_price_book_entries_stock_length" in sql
    )
    assert (
        "ADD CONSTRAINT ck_price_book_entries_each_stock CHECK ((unit = 'each') = "
        "(stock_length_ft IS NOT NULL OR sheet IS NOT NULL))" in sql
    )
    assert (
        "ADD CONSTRAINT ck_price_book_entries_one_stock CHECK "
        "(stock_length_ft IS NULL OR sheet IS NULL)" in sql
    )
    assert "ADD CONSTRAINT ck_price_books_version CHECK (version >= 1)" in sql
    # No row is rewritten on the way up.
    assert "UPDATE " not in sql.replace("UPDATE alembic_version", "")
    assert "DELETE " not in sql


_SHEET_BOOK = "6f3f6b64-0000-4000-8000-0000000230bb"


def test_0023_up_down_up_on_a_populated_database(
    pg_url: str, alembic_runner: Callable[..., None]
) -> None:
    """SHEATHING and PRICE-BOOK-VERSION: 0023 against a stored book. Its
    lumber prices come through unchanged at version 1; a sheet price stores
    and the new CHECKs hold; the downgrade drops the version and the sheet
    prices (an older Loft cannot hold them) and keeps every lumber price; the
    upgrade applies again."""
    alembic_runner(pg_url, "0022", downgrade=True)
    run = asyncio.run
    run(
        _scalar_rows(
            pg_url,
            "INSERT INTO price_books (id, owner_id, currency) "
            f"VALUES ('{_SHEET_BOOK}', '{_OWNER}', 'USD')",
        )
    )
    run(
        _scalar_rows(
            pg_url,
            "INSERT INTO price_book_entries (price_book_id, order_index, material, "
            "profile, unit, stock_length_ft, price_cents) VALUES "
            f"('{_SHEET_BOOK}', 0, 'southern_pine_pt', 'us_2x10', 'each', 16, 2847), "
            f"('{_SHEET_BOOK}', 1, 'spf_lumber', 'us_2x8', 'linear_foot', NULL, 94)",
        )
    )
    lumber = (
        "SELECT order_index, material, profile, unit, stock_length_ft, price_cents "
        "FROM price_book_entries ORDER BY order_index"
    )
    before = run(_scalar_rows(pg_url, lumber))

    alembic_runner(pg_url, "0023")
    assert run(_scalar_rows(pg_url, lumber)) == before
    assert run(_scalar_rows(pg_url, "SELECT version FROM price_books")) == [(1,)]
    assert run(_scalar_rows(pg_url, "SELECT sheet FROM price_book_entries")) == [
        (None,),
        (None,),
    ]
    run(
        _scalar_rows(
            pg_url,
            "INSERT INTO price_book_entries (price_book_id, order_index, material, "
            "profile, unit, sheet, price_cents) VALUES "
            f"('{_SHEET_BOOK}', 2, 'osb', 'osb_7_16', 'each', '4x9', 2498)",
        )
    )
    run(_scalar_rows(pg_url, "UPDATE price_books SET version = 2"))
    for bad in (
        "3, 'osb', 'osb_7_16', 'each', 8, '4x9', 1",  # a length and a sheet
        "3, 'osb', 'osb_7_16', 'linear_foot', NULL, '4x9', 1",  # only each
        "3, 'spf_lumber', 'us_2x4', 'each', NULL, NULL, 1",  # each needs one
    ):
        with pytest.raises(IntegrityError):
            run(
                _scalar_rows(
                    pg_url,
                    "INSERT INTO price_book_entries (price_book_id, order_index, "
                    "material, profile, unit, stock_length_ft, sheet, price_cents) "
                    f"VALUES ('{_SHEET_BOOK}', {bad})",
                )
            )
    with pytest.raises(IntegrityError):
        run(_scalar_rows(pg_url, "UPDATE price_books SET version = 0"))

    alembic_runner(pg_url, "0022", downgrade=True)
    assert run(_scalar_rows(pg_url, lumber)) == before
    columns = run(
        _scalar_rows(
            pg_url,
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_name IN ('price_books', 'price_book_entries') "
            "AND column_name IN ('version', 'sheet')",
        )
    )
    assert columns == []
    with pytest.raises(IntegrityError):  # 0022's CHECK is back
        run(
            _scalar_rows(
                pg_url,
                "INSERT INTO price_book_entries (price_book_id, order_index, "
                "material, profile, unit, stock_length_ft, price_cents) VALUES "
                f"('{_SHEET_BOOK}', 5, 'spf_lumber', 'us_2x4', 'each', NULL, 1)",
            )
        )

    alembic_runner(pg_url, "head")
    assert run(_scalar_rows(pg_url, lumber)) == before
    assert run(_scalar_rows(pg_url, "SELECT version FROM price_books")) == [(1,)]
    run(_scalar_rows(pg_url, f"DELETE FROM price_books WHERE id = '{_SHEET_BOOK}'"))
