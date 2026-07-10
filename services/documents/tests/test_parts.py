"""documents parts CRUD — ownership scoping, envelopes, readiness.

Test-vs-prod dialect split (stated honestly, same posture as the gateway's
tests/test_auth.py): production runs PostgreSQL via asyncpg; this suite runs
the SAME application code against SQLite via aiosqlite (file-per-test),
because the sandbox has no Postgres daemon. The column types in
:mod:`documents.db` are dialect-portable on purpose. What that split does
NOT cover:

- The duplicate-name 409 relies on ``IntegrityError`` from
  ``uq_parts_owner_name``. SQLite raises it too (asserted here), but the
  asyncpg ``UniqueViolationError`` → ``IntegrityError`` mapping itself is
  only exercised against real Postgres (compose stack / e2e).
- Native ``UUID`` / ``TIMESTAMPTZ`` columns and the ``now()`` server default
  are Postgres-rendered (verified via the alembic offline SQL), not executed
  here — SQLite always receives the client-side Python defaults.
- Concurrent-commit races on the unique constraint are not simulated.

Everything above the driver — principal handling, ownership scoping, uniform
404s, envelope shapes — is dialect-independent and covered here.
"""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from documents.db import Base
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from py_kit.db import async_dsn
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000000a"
OTHER = "6f3f6b64-0000-4000-8000-00000000000b"


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """A file-backed SQLite database with the parts schema applied."""
    url = f"sqlite:///{tmp_path}/documents.db"
    asyncio.run(_create_schema(url))
    return url


@pytest.fixture
def client(db_url: str) -> Iterator[TestClient]:
    """App over the test DB, with the lifespan running (engine owned)."""
    settings = DocumentsSettings(postgres_url=db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


def _envelope(body: dict[str, Any]) -> dict[str, Any]:
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    return error


def _assert_same_part(a: dict[str, Any], b: dict[str, Any]) -> None:
    """Same part, timestamps compared as instants.

    SQLite dialect artifact (see module docstring): ``DateTime(timezone=True)``
    round-trips as a NAIVE datetime on SQLite, so a timestamp freshly
    committed (tz-aware, in-memory) and re-read (naive, from disk) serializes
    with/without the UTC suffix. Postgres/TIMESTAMPTZ has no such split.
    """
    assert {k: v for k, v in a.items() if not k.endswith("_at")} == {
        k: v for k, v in b.items() if not k.endswith("_at")
    }

    def as_utc(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    for key in ("created_at", "updated_at"):
        assert as_utc(a[key]) == as_utc(b[key])


def _create(
    client: TestClient, name: str = "Bracket", owner: str = OWNER
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/parts", json={"name": name}, headers=_headers(owner)
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


# --- create -------------------------------------------------------------------


def test_create_part_returns_full_dto(client: TestClient) -> None:
    body = _create(client)
    assert set(body) == {"id", "name", "owner_id", "created_at", "updated_at"}
    uuid.UUID(body["id"])  # well-formed id
    assert body["name"] == "Bracket"
    assert body["owner_id"] == OWNER


def test_create_part_trims_whitespace(client: TestClient) -> None:
    body = _create(client, name="  Bracket  ")
    assert body["name"] == "Bracket"


def test_create_duplicate_name_same_owner_409(client: TestClient) -> None:
    _create(client)
    response = client.post(
        "/api/v1/parts", json={"name": "Bracket"}, headers=_headers()
    )
    assert response.status_code == 409
    assert _envelope(response.json())["code"] == "part_name_taken"


def test_create_same_name_different_owner_ok(client: TestClient) -> None:
    _create(client, owner=OWNER)
    body = _create(client, owner=OTHER)
    assert body["owner_id"] == OTHER


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_create_invalid_name_422(client: TestClient, name: str) -> None:
    response = client.post("/api/v1/parts", json={"name": name}, headers=_headers())
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"


# --- principal header (gateway trust boundary) ---------------------------------


def test_missing_principal_header_401(client: TestClient) -> None:
    response = client.get("/api/v1/parts")
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "missing_principal"


def test_malformed_principal_header_401(client: TestClient) -> None:
    response = client.get("/api/v1/parts", headers=_headers("not-a-uuid"))
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "invalid_principal"


# --- list (owner-scoped) --------------------------------------------------------


def test_list_empty(client: TestClient) -> None:
    response = client.get("/api/v1/parts", headers=_headers())
    assert response.status_code == 200
    assert response.json() == {"parts": []}


def test_list_is_owner_scoped_and_ordered(client: TestClient) -> None:
    first = _create(client, name="First")
    second = _create(client, name="Second")
    _create(client, name="Foreign", owner=OTHER)

    response = client.get("/api/v1/parts", headers=_headers())
    assert response.status_code == 200
    parts = response.json()["parts"]
    assert [part["id"] for part in parts] == [first["id"], second["id"]]
    assert all(part["owner_id"] == OWNER for part in parts)

    other = client.get("/api/v1/parts", headers=_headers(OTHER))
    assert [part["name"] for part in other.json()["parts"]] == ["Foreign"]


# --- get -----------------------------------------------------------------------


def test_get_part(client: TestClient) -> None:
    created = _create(client)
    response = client.get(f"/api/v1/parts/{created['id']}", headers=_headers())
    assert response.status_code == 200
    _assert_same_part(response.json(), created)


def test_get_unknown_id_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/parts/{uuid.uuid4()}", headers=_headers())
    assert response.status_code == 404
    assert _envelope(response.json())["code"] == "part_not_found"


def test_get_foreign_part_is_uniform_404(client: TestClient) -> None:
    """Someone else's part id answers exactly like a nonexistent one, so a
    response never reveals whether a foreign part exists."""
    created = _create(client, owner=OTHER)
    foreign = client.get(f"/api/v1/parts/{created['id']}", headers=_headers())
    unknown = client.get(f"/api/v1/parts/{uuid.uuid4()}", headers=_headers())
    assert foreign.status_code == unknown.status_code == 404
    a, b = _envelope(foreign.json()), _envelope(unknown.json())
    a.pop("request_id")
    b.pop("request_id")
    assert a == b


def test_get_malformed_id_422(client: TestClient) -> None:
    response = client.get("/api/v1/parts/not-a-uuid", headers=_headers())
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"


# --- delete --------------------------------------------------------------------


def test_delete_part_204_then_gone(client: TestClient) -> None:
    created = _create(client)
    response = client.delete(f"/api/v1/parts/{created['id']}", headers=_headers())
    assert response.status_code == 204
    assert response.content == b""

    gone = client.get(f"/api/v1/parts/{created['id']}", headers=_headers())
    assert gone.status_code == 404
    again = client.delete(f"/api/v1/parts/{created['id']}", headers=_headers())
    assert again.status_code == 404


def test_delete_foreign_part_404_and_survives(client: TestClient) -> None:
    created = _create(client, owner=OTHER)
    response = client.delete(f"/api/v1/parts/{created['id']}", headers=_headers())
    assert response.status_code == 404
    # Still there for its real owner.
    still = client.get(f"/api/v1/parts/{created['id']}", headers=_headers(OTHER))
    assert still.status_code == 200


# --- database posture -----------------------------------------------------------


def test_parts_routes_503_without_database_configured() -> None:
    with TestClient(build_app(DocumentsSettings(postgres_url=None))) as client:
        response = client.get("/api/v1/parts", headers=_headers())
    assert response.status_code == 503
    assert _envelope(response.json())["code"] == "database_unavailable"


def test_readyz_reports_postgres_ok_with_database(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"]["postgres"] == "ok"


def test_readyz_503_when_database_unreachable_without_dsn_leak() -> None:
    """HARD readiness: a dead DB is a 503, and the body carries the exception
    *type* only — never the DSN (it embeds credentials)."""
    settings = DocumentsSettings(
        postgres_url="postgresql://loft:hunter2-dsn-password@127.0.0.1:9/loft"
    )
    with TestClient(build_app(settings)) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["postgres"].startswith("error: ")
    assert "hunter2-dsn-password" not in response.text
    assert "127.0.0.1" not in response.text
