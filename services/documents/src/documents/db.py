"""Documents persistence — declarative models (parts).

Plumbing (engine/session state, DSN normalization, readiness ping) comes from
:mod:`py_kit.db`; only the documents-owned tables live here. Schema changes
ship as alembic migrations under ``services/documents/alembic`` (CLAUDE.md:
migrations only, no ad-hoc SQL); this ORM metadata is the single source those
migrations are written from. Feature-tree tables extend this schema later per
docs/design/feature-tree.md §5 (``0002_feature_tree``).

Dialects: production is PostgreSQL via asyncpg. Column types are chosen to be
dialect-portable (``sa.Uuid``, ``DateTime(timezone=True)``) so the unit tests
can run the same code paths against SQLite/aiosqlite in sandboxes without a
Postgres daemon — see ``tests/test_parts.py`` for the honest statement of
that split.
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from py_kit.schemas.parts import PART_NAME_MAX_LENGTH
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
