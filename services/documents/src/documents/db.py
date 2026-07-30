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
from py_kit.schemas.assemblies import (
    ASSEMBLY_NAME_MAX_LENGTH,
    INSTANCE_NAME_MAX_LENGTH,
)
from py_kit.schemas.drawings import (
    DRAWING_NAME_MAX_LENGTH,
    SHEET_NAME_MAX_LENGTH,
)
from py_kit.schemas.features import FEATURE_NAME_MAX_LENGTH
from py_kit.schemas.parts import (
    PART_NAME_MAX_LENGTH,
    PartEvalScope,
    PartEvalState,
    PartEvalStatus,
    derive_part_eval_scope,
    derive_part_eval_state,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


#: JSONB on Postgres, plain JSON on SQLite (tests) — same Python dict either way.
_JSON_VARIANT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


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
    #: Document DISPLAY unit (docs/design/units.md §U1) — presentation metadata
    #: only; storage/kernel stay canonical mm. NOT NULL, server-default 'mm' so
    #: pre-units rows backfill to mm (the migration adds the same default).
    length_unit: Mapped[str] = mapped_column(
        sa.String(8), nullable=False, default="mm", server_default=sa.text("'mm'")
    )
    #: What the part's bodies are made of (docs/design/materials.md §2): a
    #: serialized :class:`~py_kit.schemas.materials.MaterialAssignment` — one
    #: document default plus per-body overrides. NULL is the honest "nobody has
    #: said", which every pre-materials row backfills to and which reports NO
    #: mass (never 0 g, never a default steel). Unlike ``length_unit`` this is an
    #: INPUT to evaluation (mass is derived from it), so a write bumps
    #: ``tree_version`` AND leaves the last-evaluate record behind as stale.
    materials: Mapped[dict[str, Any] | None] = mapped_column(
        _JSON_VARIANT, nullable=True
    )
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
    #: Undo/redo cursor (docs/design/undo-redo.md): the ``part_snapshots.seq``
    #: whose state IS the current tree; NULL = history never seeded (no
    #: mutation yet). Maintained by :mod:`documents.history` in the same
    #: transaction as every tree write.
    history_cursor: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    #: Last-evaluate record (docs/design/feature-tree.md §4.4a) — four NULLABLE
    #: columns, all-null meaning "never evaluated", written together by the
    #: gateway's post-evaluate bookkeeping and by nothing else. Evaluation
    #: RESULTS still are not stored (§4.4: they stay derivable and disposable);
    #: this is only the verdict a register needs, and it is version-stamped so
    #: :func:`~py_kit.schemas.parts.derive_part_eval_state` can tell a current
    #: claim from a stale one instead of assuming.
    last_eval_status: Mapped[PartEvalStatus | None] = mapped_column(
        sa.String(16), nullable=True
    )
    last_eval_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    #: The ``tree_version`` the recorded status describes — NOT the current one.
    last_eval_tree_version: Mapped[int | None] = mapped_column(
        sa.BigInteger(), nullable=True
    )
    #: How much of the tree that status covers (audit J3): ``'whole'`` or
    #: ``'rolled_back'``. Derived by DOCUMENTS at record time — it is the only
    #: service that knows the bar exists — from whether any feature sat past the
    #: travel stop. NULL on a row written before this column existed; that is
    #: "unknown", never "whole" (see :func:`~py_kit.schemas.parts.
    #: derive_part_eval_scope`), and the part's next evaluate rewrites it.
    last_eval_scope: Mapped[PartEvalScope | None] = mapped_column(
        sa.String(16), nullable=True
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

    @property
    def eval_state(self) -> PartEvalState:
        """Rebuild health as of THIS row — the response's ``eval_state``.

        A plain Python property over columns the row already carries, so
        ``PartResponse.model_validate(part)`` picks it up through
        ``from_attributes`` and the owner-scoped LIST stays exactly ONE query
        (no per-row lookup, no N+1 — the collapse `cf4e006` made for drawing
        trees is not reintroduced here).
        """
        return derive_part_eval_state(
            last_eval_status=self.last_eval_status,
            last_eval_tree_version=self.last_eval_tree_version,
            tree_version=self.tree_version,
        )

    @property
    def eval_scope(self) -> PartEvalScope | None:
        """How much of the tree :attr:`eval_state` speaks for (J3).

        Same posture as :attr:`eval_state` — a plain property over columns the
        row already has, so the owner-scoped LIST stays exactly one query. Note
        it reads the STORED scope rather than the part's current
        ``rollback_feature_id``: the two agree whenever the verdict is live
        (moving the bar bumps ``tree_version``, which makes the record stale),
        and the stored one is a fact about the evaluate that ran, which is what
        the verdict is a claim about.
        """
        return derive_part_eval_scope(
            eval_state=self.eval_state, last_eval_scope=self.last_eval_scope
        )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Part(id={self.id!r}, owner_id={self.owner_id!r}, name={self.name!r})"


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
    #: Envelope-level suppress flag (py-kit :class:`FeatureEnvelopeBase`,
    #: feature-tree.md §4.3a): True skips this feature at rebuild — the body is
    #: built from the non-suppressed prefix and later features rebuild off the
    #: last non-suppressed body. Persisted BESIDE ``params`` (it is orthogonal to
    #: every feature type, never a modeling parameter), so the read paths
    #: (``_to_response``, the evaluation-request) pass it back through
    #: ``FEATURE_REGISTRY.load(...)``. NOT NULL, server-default false so pre-
    #: suppress rows backfill to unsuppressed (the migration adds the same
    #: default; ``metadata.create_all`` renders it too — the native/e2e path).
    suppressed: Mapped[bool] = mapped_column(
        sa.Boolean(), nullable=False, default=False, server_default=sa.text("false")
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


class PartSnapshot(Base):
    """One entry of a part's bounded undo/redo history (docs/design/undo-redo.md).

    ``state`` is the part's FULL serialized mutable child state — the ordered
    features (id / order_index / type / param_version / params / name +
    timestamps), the ``feature_dependencies`` edges, and the
    ``rollback_feature_id`` pointer — captured in the SAME transaction as the
    tree write that produced it. Undo/redo restore a snapshot VERBATIM (every
    entity id byte-preserved; ids are never regenerated), which is the
    load-bearing decision of the design: re-creating entities with fresh ids
    would orphan every downstream ``feature_dependencies`` reference on redo.

    ``seq`` is per-part monotonic and CONTIGUOUS within the retained window:
    appends use ``cursor + 1`` (after truncating any redo tail), pruning only
    ever drops from the floor, so ``documents.history`` can address adjacent
    snapshots as ``cursor ± 1``. The ring keeps at most
    :data:`documents.history.HISTORY_MAX` rows per part.
    """

    __tablename__ = "part_snapshots"

    part_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("parts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(sa.BigInteger(), primary_key=True)
    state: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"PartSnapshot(part_id={self.part_id!r}, seq={self.seq!r})"


class Assembly(Base):
    """An assembly — a graph of instances + mates (docs/design/assemblies.md §1.1).

    A FIRST-CLASS document type, sibling of :class:`Part` under the document
    umbrella (design §1.1) — its own tables, reusing the part model's PATTERNS
    (owner-scoped auth, uniform-404 visibility, an optimistic-concurrency
    counter, alembic-only DDL) but NOT its tables: an assembly is a graph, not
    an ordered single-body feature history. ``owner_id`` is the gateway-verified
    user id (no cross-service FK — RESEARCH §3, same posture as :class:`Part`);
    ``(owner_id, name)`` is unique so the constraint enforces one name per owner
    and its backing index serves the owner-scoped list scan.
    """

    __tablename__ = "assemblies"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), nullable=False)
    name: Mapped[str] = mapped_column(
        sa.String(ASSEMBLY_NAME_MAX_LENGTH), nullable=False
    )
    #: Document DISPLAY unit (docs/design/units.md §U1) — presentation metadata
    #: only; storage/kernel stay canonical mm. NOT NULL, server-default 'mm' so
    #: pre-units rows backfill to mm (the migration adds the same default).
    length_unit: Mapped[str] = mapped_column(
        sa.String(8), nullable=False, default="mm", server_default=sa.text("'mm'")
    )
    #: Monotonic optimistic-concurrency counter — bumped in the same
    #: transaction as ANY instance/mate mutation (assemblies.md §1.2).
    doc_version: Mapped[int] = mapped_column(
        sa.BigInteger(), nullable=False, default=0, server_default=sa.text("0")
    )
    #: Undo/redo cursor (docs/design/undo-redo.md UR3): the
    #: ``assembly_snapshots.seq`` whose state IS the current graph; NULL =
    #: history never seeded (no mutation yet). Maintained by
    #: :mod:`documents.assembly_history` in the same transaction as every
    #: graph/header write — the exact :class:`Part` pattern.
    history_cursor: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
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
        sa.UniqueConstraint("owner_id", "name", name="uq_assemblies_owner_name"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"Assembly(id={self.id!r}, owner_id={self.owner_id!r}, name={self.name!r})"
        )


class Instance(Base):
    """One placed instance of a part / sub-assembly in an assembly (§1.2).

    References another DOCUMENT (a part or a sub-assembly) by id — a
    CROSS-DOCUMENT reference, NOT a DB FK (design §1.2): like :class:`Part`'s
    ``owner_id``, integrity is app-enforced in documents at write time
    (existence, acyclicity, 409-with-dependents), because the reference must
    survive the referenced doc's independent lifecycle. ``ref_pinned_version``
    is present but NULL in v1 (design §1.3 — the schema is pin-ready; v1 tracks
    the referenced document's tip). ``placement`` is the Placement DTO (§1.5)
    stored as JSONB. ``order_index`` is a stable display/BOM order — NOT an
    evaluation order (an assembly is a graph, not a linear history — §1.1); it
    is renumbered dense on insert/delete/reorder exactly like a feature's.
    ``uq_instances_assembly_order`` is DEFERRABLE INITIALLY DEFERRED on Postgres
    (migration only; SQLite cannot express it — the split documented for
    :class:`Feature`), but app code renumbers collision-free so it is correct
    under IMMEDIATE checking too.
    """

    __tablename__ = "instances"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    assembly_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("assemblies.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Cross-document reference (part / sub-assembly) — app-enforced, no FK.
    ref_document_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), nullable=False)
    ref_document_kind: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    #: Pin-ready (§1.3): NULL in v1 = track the referenced document's tip.
    ref_pinned_version: Mapped[int | None] = mapped_column(
        sa.BigInteger(), nullable=True
    )
    name: Mapped[str] = mapped_column(
        sa.String(INSTANCE_NAME_MAX_LENGTH), nullable=False
    )
    grounded: Mapped[bool] = mapped_column(
        sa.Boolean(), nullable=False, default=False, server_default=sa.text("false")
    )
    #: The Placement DTO (position + quaternion), JSONB on Postgres.
    placement: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    #: Dense 0..n-1 stable order; renumbered on insert/delete/reorder.
    order_index: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
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
        # cannot parse deferrable UNIQUE (see :class:`Feature`). Its backing
        # index also serves the ordered instance scan — no separate index.
        sa.UniqueConstraint(
            "assembly_id", "order_index", name="uq_instances_assembly_order"
        ),
        # Reverse lookup of "which instances reference document X" — the
        # cross-document 409-with-dependents pre-check (design §1.2).
        sa.Index("ix_instances_ref_document", "ref_document_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"Instance(id={self.id!r}, assembly_id={self.assembly_id!r}, "
            f"ref_document_id={self.ref_document_id!r})"
        )


class Mate(Base):
    """One constraint edge of an assembly's mate graph (design §1.2/§2.1).

    ``type`` is promoted to a real column (indexable/filterable) exactly as a
    :class:`Feature`'s is; ``params`` holds the full :data:`~py_kit.schemas.
    assemblies.Mate` payload (including its ``type`` discriminator) as JSONB and
    is ALWAYS the output of a successful pydantic validation — py-kit models are
    the gate, never a JSON CHECK. The instances a mate constrains live INSIDE
    ``params`` (the mate's geometry/instance refs), so — like the cross-document
    ``ref_document_id`` — membership is app-enforced at write time, not a DB FK.
    ``order_index`` is a stable order for solve determinism (§2.2), renumbered
    dense on insert/delete.
    """

    __tablename__ = "mates"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    assembly_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("assemblies.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Dense 0..n-1 stable order (determinism); renumbered on insert/delete.
    order_index: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
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
        sa.UniqueConstraint(
            "assembly_id", "order_index", name="uq_mates_assembly_order"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"Mate(id={self.id!r}, assembly_id={self.assembly_id!r}, "
            f"type={self.type!r})"
        )


class AssemblySnapshot(Base):
    """One entry of an assembly's bounded undo/redo history (undo-redo.md UR3).

    The assembly sibling of :class:`PartSnapshot` — same mechanism
    (:mod:`documents.history_core`), different serialized state: ``state`` is
    the assembly's FULL mutable state — the mutable header fields
    (``name`` / ``length_unit``, because the assembly PATCH is a history
    event), the ordered instances (every column: id / ref / pin / name /
    grounded / placement / order_index + timestamps) and the ordered mates
    (id / order_index / type / params + timestamps) — captured in the SAME
    transaction as the write that produced it. Undo/redo restore a snapshot
    VERBATIM (instance/mate ids byte-preserved, never re-minted), so a
    mate's instance references inside its params JSONB stay valid across any
    undo/redo distance.

    ``seq`` is per-assembly monotonic and CONTIGUOUS within the retained
    window (appends at ``cursor + 1`` after redo-tail truncation, pruning
    only from the floor); the ring keeps at most
    :data:`documents.history_core.HISTORY_MAX` rows per assembly.
    """

    __tablename__ = "assembly_snapshots"

    assembly_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("assemblies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(sa.BigInteger(), primary_key=True)
    state: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"AssemblySnapshot(assembly_id={self.assembly_id!r}, seq={self.seq!r})"


class Drawing(Base):
    """A drawing — a layout of sheets/views/dimensions/annotations (drawings.md §2).

    A FIRST-CLASS document type, sibling of :class:`Part` / :class:`Assembly`
    under the document umbrella (design §2.1) — its own tables, reusing their
    PATTERNS (owner-scoped auth, uniform-404 visibility, an optimistic-concurrency
    counter, alembic-only DDL, cross-document 409-with-dependents) but NOT their
    tables: a drawing is a LAYOUT that *references* parts/assemblies, not a part
    history or an instance graph. ``owner_id`` is the gateway-verified user id (no
    cross-service FK — RESEARCH §3, same posture as :class:`Part`);
    ``(owner_id, name)`` is unique so the constraint enforces one name per owner
    and its backing index serves the owner-scoped list scan. Nothing references a
    drawing (it is a pure leaf consumer, design §2.2), so no acyclicity walk is
    needed.
    """

    __tablename__ = "drawings"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), nullable=False)
    name: Mapped[str] = mapped_column(
        sa.String(DRAWING_NAME_MAX_LENGTH), nullable=False
    )
    #: Monotonic optimistic-concurrency counter — bumped in the same
    #: transaction as ANY sheet/view/dimension/annotation mutation (§2.1).
    doc_version: Mapped[int] = mapped_column(
        sa.BigInteger(), nullable=False, default=0, server_default=sa.text("0")
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
        sa.UniqueConstraint("owner_id", "name", name="uq_drawings_owner_name"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"Drawing(id={self.id!r}, owner_id={self.owner_id!r}, name={self.name!r})"
        )


class Sheet(Base):
    """One sheet of a drawing (design §2.2).

    ``title_block`` is the free-text TitleBlock DTO as JSONB (nullable — a sheet
    may carry none). ``order_index`` is a stable dense 0..n-1 order renumbered on
    insert/delete; ``uq_sheets_drawing_order`` is a plain UNIQUE (app renumbers
    collision-free — shift-down on delete is monotone, so it is correct under
    IMMEDIATE checking, no deferrable clause needed). Its backing index also
    serves the ordered sheet scan.
    """

    __tablename__ = "sheets"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    drawing_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(SHEET_NAME_MAX_LENGTH), nullable=False)
    size: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    orientation: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    projection: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    #: The free-text TitleBlock DTO (JSONB on Postgres); NULL when unset.
    title_block: Mapped[dict[str, Any] | None] = mapped_column(
        _JSON_VARIANT, nullable=True
    )
    order_index: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
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
        sa.UniqueConstraint(
            "drawing_id", "order_index", name="uq_sheets_drawing_order"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"Sheet(id={self.id!r}, drawing_id={self.drawing_id!r}, name={self.name!r})"
        )


class View(Base):
    """One projected view on a sheet, referencing a part / assembly (design §2.2).

    References another DOCUMENT (a part or an assembly) by id — a CROSS-DOCUMENT
    reference, NOT a DB FK (design §2.2, identical to an assembly instance):
    integrity is app-enforced in documents at write time (existence,
    409-with-dependents), because the reference must survive the referenced doc's
    independent lifecycle. ``ref_pinned_version`` is present but NULL in v1
    (design §2.3 — the schema is pin-ready; v1 tracks the referenced document's
    tip). ``projection`` is the standard orthographic / iso direction (all
    documents stores — HLR is geometry's job); ``scale_num``/``scale_den`` are the
    exact rational scale and ``pos_x_mm``/``pos_y_mm`` the sheet placement. A view
    owns its dimensions (``dimensions.view_id`` CASCADE).
    """

    __tablename__ = "views"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    sheet_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("sheets.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Cross-document reference (part / assembly) — app-enforced, no FK.
    ref_document_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), nullable=False)
    ref_document_kind: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    #: Pin-ready (§2.3): NULL in v1 = track the referenced document's tip.
    ref_pinned_version: Mapped[int | None] = mapped_column(
        sa.BigInteger(), nullable=True
    )
    projection: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    scale_num: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    scale_den: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    pos_x_mm: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    pos_y_mm: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    #: Placement mode (drawing-export.md §4.2): True (default) = the composer
    #: auto-places (bounds-aware); False = a persisted drag-to-place position the
    #: composer honors verbatim. Server-default true so every pre-existing view
    #: backfills to auto-layout in one statement (the additive-optional posture the
    #: ``section_params`` / ``suppressed`` columns carry).
    auto_place: Mapped[bool] = mapped_column(
        sa.Boolean(), nullable=False, server_default=sa.text("true")
    )
    #: A ``section`` view's cutting plane + flip (drawings-section.md §1) as JSONB —
    #: the validated :class:`~py_kit.schemas.drawings.SectionViewParams` payload; NULL
    #: for every non-section view, so existing views are untouched (additive).
    section_params: Mapped[dict[str, Any] | None] = mapped_column(
        _JSON_VARIANT, nullable=True
    )
    order_index: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
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
        sa.UniqueConstraint("sheet_id", "order_index", name="uq_views_sheet_order"),
        # ONE view per projection per sheet (engineering audit H3, migration 0011).
        # The whole stack keys a sheet's views by PROJECTION — the composer's
        # anchor map and the frontend's `viewIdByProjection` are both
        # `dict[projection, …]` — so a second `front`/`section` view on one sheet
        # collapsed to a single composed view AND made a drag-to-place PATCH
        # persist onto the OTHER view's row. The schema now says what the code
        # assumed; multi-section sheets need view-id keying end-to-end (BACKLOG).
        sa.UniqueConstraint("sheet_id", "projection", name="uq_views_sheet_projection"),
        # Reverse lookup of "which views reference document X" — the
        # cross-document 409-with-dependents pre-check (design §2.2).
        sa.Index("ix_views_ref_document", "ref_document_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"View(id={self.id!r}, sheet_id={self.sheet_id!r}, "
            f"ref_document_id={self.ref_document_id!r})"
        )


class Dimension(Base):
    """One dimension annotating a view (design §2.2/§3).

    ``type`` is promoted to a real column (indexable/filterable) exactly as a
    :class:`Feature`/:class:`Mate` type is; ``params`` holds the full
    :data:`~py_kit.schemas.drawings.Dimension` payload (including its geometry
    signature refs) as JSONB and is ALWAYS the output of a successful pydantic
    validation — py-kit models are the gate, never a JSON CHECK. A dimension is
    pinned to its ``view_id`` (CASCADE — deleting a view removes its dimensions)
    and ordered per SHEET (``uq_dimensions_sheet_order`` — design §2.2). Plain
    UNIQUE; app renumbers collision-free on delete.
    """

    __tablename__ = "dimensions"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    sheet_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("sheets.id", ondelete="CASCADE"),
        nullable=False,
    )
    view_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("views.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    type: Mapped[str] = mapped_column(sa.String(16), nullable=False)
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
        sa.UniqueConstraint(
            "sheet_id", "order_index", name="uq_dimensions_sheet_order"
        ),
        # Reverse lookup for the view→dimensions cascade renumber on the app side.
        sa.Index("ix_dimensions_view", "view_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"Dimension(id={self.id!r}, view_id={self.view_id!r}, type={self.type!r})"
        )


class Annotation(Base):
    """One annotation (v1: a note) on a sheet (design §2.2).

    ``type`` is promoted to a real column; ``params`` holds the full
    :data:`~py_kit.schemas.drawings.Annotation` payload (text + position) as
    JSONB, always the output of a successful pydantic validation. Ordered per
    SHEET (``uq_annotations_sheet_order``); plain UNIQUE, app renumbers
    collision-free on delete.
    """

    __tablename__ = "annotations"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    sheet_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("sheets.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    type: Mapped[str] = mapped_column(sa.String(16), nullable=False)
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
        sa.UniqueConstraint(
            "sheet_id", "order_index", name="uq_annotations_sheet_order"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"Annotation(id={self.id!r}, sheet_id={self.sheet_id!r}, "
            f"type={self.type!r})"
        )
