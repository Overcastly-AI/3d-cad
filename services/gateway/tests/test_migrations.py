"""gateway alembic tree — offline DDL for the session tables.

The gateway had no migration test until its second revision; this renders
``0002_auth_sessions`` offline (``alembic upgrade --sql``: no database, always
runs) and asserts the Postgres DDL the security design leans on: the unique
digest (lookup AND the guarantee that one token names one row), and the two
CASCADEs (deleting a user ends their sessions; deleting a session ends its
tokens). A real apply against PostgreSQL 16 was run by hand when this landed;
the documents suite owns the scratch-Postgres fixtures, and moving them to
py-kit for one revision was not worth it yet.
"""

import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _offline_sql(
    monkeypatch: pytest.MonkeyPatch, revision_range: str, *, downgrade: bool = False
) -> str:
    # Offline mode only needs a URL for dialect selection; nothing connects.
    monkeypatch.setenv("POSTGRES_URL", "postgresql://loft:unused@db.invalid/loft")
    buffer = io.StringIO()
    config = Config(str(ALEMBIC_INI), output_buffer=buffer)
    if downgrade:
        command.downgrade(config, revision_range, sql=True)
    else:
        command.upgrade(config, revision_range, sql=True)
    return buffer.getvalue()


def test_0002_offline_sql_creates_the_session_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _offline_sql(monkeypatch, "0001:0002")
    assert "CREATE TABLE auth_sessions" in sql
    assert "CREATE TABLE refresh_tokens" in sql
    assert (
        "CONSTRAINT fk_auth_sessions_user FOREIGN KEY(user_id) "
        "REFERENCES users (id) ON DELETE CASCADE" in sql
    )
    assert (
        "CONSTRAINT fk_refresh_tokens_session FOREIGN KEY(session_id) "
        "REFERENCES auth_sessions (id) ON DELETE CASCADE" in sql
    )
    assert "CONSTRAINT uq_refresh_tokens_token_hash UNIQUE (token_hash)" in sql
    assert "token_hash VARCHAR(64) NOT NULL" in sql
    assert "expires_at TIMESTAMP WITH TIME ZONE NOT NULL" in sql
    assert "revoked_at TIMESTAMP WITH TIME ZONE" in sql
    assert "used_at TIMESTAMP WITH TIME ZONE" in sql
    assert "CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id)" in sql
    assert (
        "CREATE INDEX ix_refresh_tokens_session_id ON refresh_tokens (session_id)"
        in sql
    )
    assert "UPDATE alembic_version SET version_num='0002'" in sql


def test_0002_offline_downgrade_drops_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _offline_sql(monkeypatch, "0002:0001", downgrade=True)
    assert "DROP TABLE refresh_tokens" in sql
    assert "DROP TABLE auth_sessions" in sql
    # Tokens first: they reference sessions.
    assert sql.index("DROP TABLE refresh_tokens") < sql.index(
        "DROP TABLE auth_sessions"
    )


def test_0003_offline_sql_links_a_spent_token_to_its_successor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _offline_sql(monkeypatch, "0002:0003")
    assert "ALTER TABLE refresh_tokens ADD COLUMN replaced_by_id UUID" in sql
    assert (
        "ALTER TABLE refresh_tokens ADD CONSTRAINT fk_refresh_tokens_replaced_by "
        "FOREIGN KEY(replaced_by_id) REFERENCES refresh_tokens (id) "
        "ON DELETE SET NULL" in sql
    )
    down = _offline_sql(monkeypatch, "0003:0002", downgrade=True)
    assert "ALTER TABLE refresh_tokens DROP COLUMN replaced_by_id" in down
