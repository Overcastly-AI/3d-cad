"""Documents persistence — declarative models (parts + feature tree).

Plumbing (engine/session state, DSN normalization, readiness ping) comes from
:mod:`py_kit.db`; only the documents-owned tables live here. Schema changes
ship as alembic migrations under ``services/documents/alembic`` (CLAUDE.md:
migrations only, no ad-hoc SQL); this ORM metadata is the single source those
migrations are written from. Feature-tree tables per
docs/design/feature-tree.md §1.2 (``0002_feature_tree``).

Dialects: production is PostgreSQL via asyncpg. Column types are chosen to be
dialect-portable (``sa.Uuid``, ``DateTime(timezone=True)``, ``JSON`` with a
JSONB variant) so the unit tests can run the same code paths against
SQLite/aiosqlite — see ``tests/test_features.py`` for the honest statement of
that split. Two Postgres-only clauses of the design DDL cannot be expressed
in SQLite and therefore live ONLY in the ``0002_feature_tree`` migration
(offline-render-verified in ``tests/test_migrations.py``):

- ``uq_features_part_order`` is ``DEFERRABLE INITIALLY DEFERRED`` on Postgres
  (SQLite rejects deferrable UNIQUE constraints). App code renumbers
  collision-free (suffix shifts in index order, reorders in two phases) so it
  is correct under IMMEDIATE checking too; the deferred constraint is the
  design's belt-and-braces.
- ``fk_parts_rollback_feature`` — composite, circular with ``features``, with
  the Postgres-15+ ``ON DELETE SET NULL (rollback_feature_id)`` column list.
  SQLite supports neither the column list nor ``ALTER TABLE ADD CONSTRAINT``
  (needed for the circular pair), so the ORM metadata omits it; documents'
  delete path resets the bar explicitly, keeping behavior identical on both
  dialects with the Postgres FK as backstop.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from py_kit.schemas.features import FEATURE_NAME_MAX_LENGTH
from py_kit.schemas.parts import PART_NAME_MAX_LENGTH
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for all documents-owned tables."""


class Part(Base):
    """A part — the root of a (future) parametric feature tree.

    ``owner_id`` is the gateway-verified user id (see
    :mod:`py_kit.schemas.parts` for the trust model); there is no FK to the
    gateway's ``users`` table because identity lives in a DIFFERENT service's
    schema (RESEARCH §3) — cross-service referential integrity is not a thing
    we pretend to have. ``(owner_id, name)`` is unique so the constraint —
    not a racy pre-check — enforces one name per owner; its backing index's
    leftmost column also serves the owner-scoped list scan.
    """

    __tablename__ = "parts"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(PART_NAME_MAX_LENGTH), nullable=False)
    #: Monotonic optimistic-concurrency counter — bumped in the same
    #: transaction as ANY tree mutation (feature-tree.md §1.2).
    tree_version: Mapped[int] = mapped_column(
        sa.BigInteger(), nullable=False, default=0, server_default=sa.text("0")
    )
    #: Rollback bar: id of the last INCLUDED feature; NULL = bar at the tip
    #: (feature-tree.md §3). Composite same-part FK lives in the migration
    #: only (see module docstring); app code maintains the invariant.
    rollback_feature_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
        server_default=sa.text("now()"),
    )

    __table_args__ = (
        sa.UniqueConstraint("owner_id", "name", name="uq_parts_owner_name"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Part(id={self.id!r}, owner_id={self.owner_id!r}, name={self.name!r})"


#: JSONB on Postgres, plain JSON on SQLite (tests) — same Python dict either way.
_JSON_VARIANT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


class Feature(Base):
    """One row of a part's ordered feature tree (feature-tree.md §1.2).

    ``type``/``param_version`` are promoted to real columns (indexable,
    constrainable, data-migration-filterable); ``params`` holds only the
    type-specific payload and is ALWAYS the output of a successful pydantic
    validation (§1.3) — py-kit models are the gate, never a JSON CHECK.
    ``uq_features_part_id`` makes ``(part_id, id)`` a composite-FK target so
    every reference TO a feature pins its part (§2.2 rule 1, DB-enforced).
    """

    __tablename__ = "features"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("parts.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Dense 0..n-1 evaluation order; renumbered on insert/delete/reorder.
    order_index: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    name: Mapped[str] = mapped_column(
        sa.String(FEATURE_NAME_MAX_LENGTH), nullable=False
    )
    type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    param_version: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
        server_default=sa.text("now()"),
    )

    __table_args__ = (
        # DEFERRABLE INITIALLY DEFERRED on Postgres via the migration; SQLite
        # cannot parse deferrable UNIQUE (module docstring). Its backing index
        # also serves the ordered tree scan — no separate index (§1.2).
        sa.UniqueConstraint("part_id", "order_index", name="uq_features_part_order"),
        # Composite-FK target for same-part enforcement (§2.2 rule 1).
        sa.UniqueConstraint("part_id", "id", name="uq_features_part_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"Feature(id={self.id!r}, part_id={self.part_id!r}, "
            f"order_index={self.order_index!r}, type={self.type!r})"
        )


class FeatureDependency(Base):
    """Materialized inter-feature reference edges (feature-tree.md §2.3).

    Derived from validated params on every write; the JSONB stays the source
    of truth for WHAT is referenced. The target-side FK is ``ON DELETE NO
    ACTION DEFERRABLE INITIALLY DEFERRED`` — checked at COMMIT, so whole-part
    CASCADE deletes pass while a lone delete of a still-referenced feature
    that slips past documents' 409 pre-check still fails (corruption
    backstop, review-log 🔴 fix). RESTRICT would break part deletion.
    """

    __tablename__ = "feature_dependencies"

    part_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), nullable=False)
    feature_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True)
    references_feature_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True
    )

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["part_id", "feature_id"],
            ["features.part_id", "features.id"],
            ondelete="CASCADE",
            name="fk_feature_deps_feature",
        ),
        sa.ForeignKeyConstraint(
            ["part_id", "references_feature_id"],
            ["features.part_id", "features.id"],
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
            name="fk_feature_deps_target",
        ),
        # Postgres does not auto-index the referencing side of an FK; this
        # serves reverse lookups ("who references X") and the RI check fired
        # by a feature delete (§1.2).
        sa.Index("ix_feature_deps_target", "references_feature_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"FeatureDependency(feature_id={self.feature_id!r}, "
            f"references_feature_id={self.references_feature_id!r})"
        )
