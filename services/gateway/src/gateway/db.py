"""Gateway persistence — declarative models (users).

The gateway owns the identity store (users) per RESEARCH §3 — auth is a
gateway concern, so users live HERE, not in the documents service. Plumbing
(engine/session state, DSN normalization, readiness ping) comes from
:mod:`py_kit.db` (extracted there on its second real use — documents parts).
Schema changes ship as alembic migrations under ``services/gateway/alembic``
(CLAUDE.md: migrations only, no ad-hoc SQL); the ORM metadata below is the
single source those migrations are written from.

Dialects: production is PostgreSQL via asyncpg. The column types are chosen
to be dialect-portable (``sa.Uuid``, ``DateTime(timezone=True)``) so the unit
tests can run the same code paths against SQLite/aiosqlite in sandboxes
without a Postgres daemon — see ``tests/test_auth.py`` for the honest
statement of that split.
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: RFC 5321 upper bound for a full email address.
EMAIL_MAX_LENGTH = 320

#: Generous bound for the argon2 encoded hash string (current output ~97 ch).
PASSWORD_HASH_MAX_LENGTH = 255


class Base(DeclarativeBase):
    """Declarative base for all gateway-owned tables."""


class User(Base):
    """An account — email/password identity, argon2 hash at rest.

    ``email`` is stored lowercase-normalized (done at the route layer) and
    unique; the constraint — not a racy pre-check — is what enforces
    one-account-per-email. The plaintext password never touches this model.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        sa.String(EMAIL_MAX_LENGTH), unique=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        sa.String(PASSWORD_HASH_MAX_LENGTH), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        """Identify the row WITHOUT the hash — keep secrets out of any log."""
        return f"User(id={self.id!r}, email={self.email!r})"
