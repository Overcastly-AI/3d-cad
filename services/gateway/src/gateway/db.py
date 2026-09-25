"""Gateway persistence — declarative models (users, auth sessions).

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


#: Hex length of a SHA-256 digest — the at-rest form of a refresh token.
REFRESH_TOKEN_HASH_LENGTH = 64


class AuthSession(Base):
    """One sign-in: the family every rotated refresh token belongs to.

    Created by register/login. ``expires_at`` is the ABSOLUTE bound — no
    rotation can extend a session past it — and ``revoked_at`` ends the whole
    family at once (logout, or refresh-token reuse detected). Access tokens
    carry this row's id as ``sid`` and are re-checked against it on every
    request, so revoking a session also kills the access tokens minted from it
    instead of leaving them valid until ``exp``. See
    :mod:`gateway.auth.security` for the full design.
    """

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=sa.text("now()"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class RefreshToken(Base):
    """One refresh token of a session — stored as a SHA-256 digest only.

    Single use: a successful refresh stamps ``used_at`` and issues a successor.
    Presenting a token whose ``used_at`` is already set is REUSE — the token
    was copied — and revokes the whole session. The plaintext exists only in
    the client's httpOnly cookie; a database read discloses nothing usable
    (the token is 256 random bits, so an unsalted digest cannot be reversed).
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        sa.String(REFRESH_TOKEN_HASH_LENGTH), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=sa.text("now()"),
    )
    #: Idle bound: never later than the session's absolute ``expires_at``.
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    #: The token issued when this one was spent. It is what lets a client that
    #: lost the rotation response retry inside the reuse interval (see
    #: :data:`gateway.auth.security.REFRESH_REUSE_INTERVAL_S`).
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
