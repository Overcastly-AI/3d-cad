"""documents ``PUT /api/v1/parts/{id}/last-evaluation`` — the four-state record.

What is under test is not "a column can be written" but the *honesty* of the
claim it makes (docs/design/feature-tree.md §4.4a): a stored status describes ONE
tree version, so every test below fixes the relationship between the recorded
version and the part's current one and asserts which of the four states the API
reports — ``never`` / ``ok`` / ``failed`` / ``stale``. Also gated here: the two
properties that make the record safe to put on a dashboard — the write is
monotonic in ``tree_version`` (a late duplicate cannot resurrect a superseded
verdict) and it is NOT a document edit (``updated_at`` and ``tree_version`` do
not move, so merely opening a part cannot fake "last worked").

Dialect split as in tests/test_parts.py: SQLite via aiosqlite here, PostgreSQL in
production; the row-lock (``FOR UPDATE``) that serialises concurrent recordings is
a Postgres-only effect and is not exercised by this suite.
"""

import asyncio
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from documents.db import Base
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from py_kit.db import async_dsn
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000000a"
OTHER = "6f3f6b64-0000-4000-8000-00000000000b"

#: A non-body-affecting datum feature — the cheapest real TREE edit available,
#: used here only for its ``tree_version`` bump.
DATUM_ENVELOPE: dict[str, Any] = {
    "type": "datum",
    "version": 1,
    "params": {"base": "XY", "offset_mm": 30.0, "flip": False},
}


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    url = f"sqlite:///{tmp_path}/documents.db"
    asyncio.run(_create_schema(url))
    with TestClient(build_app(DocumentsSettings(postgres_url=url))) as test_client:
        yield test_client


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


def _create_part(client: TestClient, name: str = "Bracket") -> dict[str, Any]:
    response = client.post("/api/v1/parts", json={"name": name}, headers=_headers())
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _get_part(client: TestClient, part_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/parts/{part_id}", headers=_headers())
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _tree_version(client: TestClient, part_id: str) -> int:
    response = client.get(f"/api/v1/parts/{part_id}/features", headers=_headers())
    assert response.status_code == 200, response.text
    version: int = response.json()["tree_version"]
    return version


def _add_datum(client: TestClient, part_id: str) -> int:
    """Make a real tree edit; returns the new ``tree_version``."""
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": "Datum1",
            "feature": DATUM_ENVELOPE,
            "expected_tree_version": _tree_version(client, part_id),
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    version: int = response.json()["tree_version"]
    return version


def _record(
    client: TestClient,
    part_id: str,
    *,
    status: str,
    tree_version: int,
    owner: str = OWNER,
) -> Any:
    return client.put(
        f"/api/v1/parts/{part_id}/last-evaluation",
        json={"status": status, "tree_version": tree_version},
        headers=_headers(owner),
    )


def _envelope(body: dict[str, Any]) -> dict[str, Any]:
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    return error


# --- the four states ------------------------------------------------------------


def test_never_evaluated_is_the_only_claim_a_fresh_part_makes(
    client: TestClient,
) -> None:
    part = _create_part(client)
    assert part["eval_state"] == "never"
    assert part["last_eval_status"] is None
    assert part["last_eval_at"] is None
    assert part["last_eval_tree_version"] is None


def test_clean_evaluate_reads_ok_and_carries_the_version_it_describes(
    client: TestClient,
) -> None:
    part = _create_part(client)
    version = _add_datum(client, part["id"])

    response = _record(client, part["id"], status="ok", tree_version=version)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["eval_state"] == "ok"
    assert body["last_eval_status"] == "ok"
    assert body["last_eval_tree_version"] == version
    # Documents' own clock stamped it (the caller sends no timestamp). SQLite
    # round-trips DateTime(timezone=True) NAIVE — the dialect artifact
    # tests/test_parts.py documents — so pin the zone before comparing.
    recorded_at = datetime.fromisoformat(body["last_eval_at"])
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=UTC)
    assert (datetime.now(UTC) - recorded_at).total_seconds() < 60

    assert _get_part(client, part["id"])["eval_state"] == "ok"


def test_failed_evaluate_reads_failed_while_it_still_applies(
    client: TestClient,
) -> None:
    part = _create_part(client)
    version = _add_datum(client, part["id"])
    assert (
        _record(client, part["id"], status="failed", tree_version=version).json()[
            "eval_state"
        ]
        == "failed"
    )
    assert _get_part(client, part["id"])["eval_state"] == "failed"


def test_a_tree_edit_makes_the_verdict_stale_not_wrong(client: TestClient) -> None:
    """The whole point of the design: after the tree moves, a recorded
    ``failed`` stops asserting ``failed`` — it says "unknown" — without the raw
    record being rewritten or lost."""
    part = _create_part(client)
    version = _add_datum(client, part["id"])
    _record(client, part["id"], status="failed", tree_version=version)

    new_version = _add_datum(client, part["id"])
    assert new_version > version

    fetched = _get_part(client, part["id"])
    assert fetched["eval_state"] == "stale"
    # The raw record is untouched and still says WHAT it saw and WHEN, so a UI
    # can show "failed 20 min ago, tree changed since" rather than nothing.
    assert fetched["last_eval_status"] == "failed"
    assert fetched["last_eval_tree_version"] == version
    assert fetched["last_eval_at"] is not None

    # Re-evaluating the current tree makes the claim current again.
    assert (
        _record(client, part["id"], status="ok", tree_version=new_version).json()[
            "eval_state"
        ]
        == "ok"
    )


def test_a_result_for_a_tree_that_already_moved_records_as_stale_immediately(
    client: TestClient,
) -> None:
    """An evaluate raced by an edit: the result is honestly about the OLD tree,
    so it is recorded (never discarded — it is newer than what we had) and reads
    ``stale`` at once, rather than being passed off as current."""
    part = _create_part(client)
    old_version = _add_datum(client, part["id"])
    _add_datum(client, part["id"])

    body = _record(client, part["id"], status="ok", tree_version=old_version).json()
    assert body["last_eval_tree_version"] == old_version
    assert body["eval_state"] == "stale"


# --- the provenance pair a client compares --------------------------------------


def test_the_part_row_reports_the_live_tree_version(client: TestClient) -> None:
    """``tree_version`` on the part row is the DENOMINATOR of every staleness
    check (``is_stale_for_tree``), so it must be the LIVE counter — the same
    number the feature-tree read reports — and it must be readable WITHOUT
    fetching the tree. A viewport that must download a whole feature tree to
    learn the current version cannot afford to ask, which is how "up to date"
    ends up inferred from request state instead (docs/UI-REVIEW.md F2)."""
    part = _create_part(client)
    assert part["tree_version"] == 0

    version = _add_datum(client, part["id"])
    fetched = _get_part(client, part["id"])
    assert fetched["tree_version"] == version
    assert fetched["tree_version"] == _tree_version(client, part["id"])


def test_the_pair_a_client_holds_says_stale_before_any_re_evaluate(
    client: TestClient,
) -> None:
    """The F2 capability at the API: a client that evaluated at version N holds a
    body stamped N; when someone else edits the tree, the part row alone — five
    scalars, no tree fetch — reports N+1, so the two numbers disagree and the
    displayed body is KNOWN stale. Note this is true even before the next
    evaluate is recorded: the derived ``eval_state`` and the raw pair agree."""
    part = _create_part(client)
    evaluated_at = _add_datum(client, part["id"])
    _record(client, part["id"], status="ok", tree_version=evaluated_at)

    current = _get_part(client, part["id"])
    assert current["tree_version"] == evaluated_at == current["last_eval_tree_version"]
    assert current["eval_state"] == "ok"

    edited_elsewhere = _add_datum(client, part["id"])
    after = _get_part(client, part["id"])
    assert after["tree_version"] == edited_elsewhere
    assert after["last_eval_tree_version"] == evaluated_at
    assert after["tree_version"] != after["last_eval_tree_version"]
    assert after["eval_state"] == "stale"


# --- properties that make it safe on a dashboard --------------------------------


def test_a_superseded_write_is_a_no_op(client: TestClient) -> None:
    """Two evaluates in flight: the older one landing last must not resurrect
    its verdict."""
    part = _create_part(client)
    first = _add_datum(client, part["id"])
    second = _add_datum(client, part["id"])

    _record(client, part["id"], status="ok", tree_version=second)
    late = _record(client, part["id"], status="failed", tree_version=first)

    assert late.status_code == 200, late.text
    body = late.json()
    assert body["last_eval_status"] == "ok"
    assert body["last_eval_tree_version"] == second
    assert body["eval_state"] == "ok"


def test_recording_is_not_a_document_edit(client: TestClient) -> None:
    """Opening a part evaluates it; if that moved ``updated_at`` the register's
    LAST WORKED column — the thing this feature exists to sit beside — would be
    a lie. ``tree_version`` must not move either (it is not a tree write)."""
    part = _create_part(client)
    version = _add_datum(client, part["id"])
    before = _get_part(client, part["id"])

    _record(client, part["id"], status="failed", tree_version=version)

    after = _get_part(client, part["id"])
    assert after["updated_at"] == before["updated_at"]
    assert _tree_version(client, part["id"]) == version
    assert after["eval_state"] == "failed"


def test_rename_and_re_unit_carry_the_record_forward(client: TestClient) -> None:
    """A header-only PATCH bumps ``tree_version`` but cannot change what the
    tree evaluates to, so the verdict follows it instead of going ``stale`` —
    renaming a part must not grey out its health."""
    part = _create_part(client)
    version = _add_datum(client, part["id"])
    _record(client, part["id"], status="ok", tree_version=version)

    renamed = client.patch(
        f"/api/v1/parts/{part['id']}",
        json={"expected_tree_version": version, "name": "Bracket plate"},
        headers=_headers(),
    )
    assert renamed.status_code == 200, renamed.text
    body = renamed.json()
    assert body["eval_state"] == "ok"
    assert body["last_eval_tree_version"] == version + 1

    re_united = client.patch(
        f"/api/v1/parts/{part['id']}",
        json={"expected_tree_version": version + 1, "length_unit": "in"},
        headers=_headers(),
    )
    assert re_united.json()["eval_state"] == "ok"


def test_a_never_evaluated_part_is_not_given_a_record_by_a_rename(
    client: TestClient,
) -> None:
    part = _create_part(client)
    renamed = client.patch(
        f"/api/v1/parts/{part['id']}",
        json={"expected_tree_version": 0, "name": "Renamed"},
        headers=_headers(),
    )
    assert renamed.json()["eval_state"] == "never"
    assert renamed.json()["last_eval_tree_version"] is None


# --- the register read ----------------------------------------------------------


@contextmanager
def _statements() -> Generator[list[str]]:
    """Collect every SQL statement executed while the block runs."""
    seen: list[str] = []

    def before(
        _conn: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        seen.append(statement)

    event.listen(Engine, "before_cursor_execute", before)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", before)


def test_list_carries_health_for_every_row_in_one_query(client: TestClient) -> None:
    """The register reads a whole drawer, so this must not become an N+1: the
    derived state is a property over columns the row already has (the collapse
    `cf4e006` made for drawing trees stays made)."""
    for index in range(3):
        part = _create_part(client, name=f"Part {index}")
        version = _add_datum(client, part["id"])
        if index:
            _record(
                client,
                part["id"],
                status="ok" if index == 1 else "failed",
                tree_version=version,
            )

    with _statements() as seen:
        response = client.get("/api/v1/parts", headers=_headers())
    assert response.status_code == 200, response.text
    parts = response.json()["parts"]
    assert [part["eval_state"] for part in parts] == ["never", "ok", "failed"]
    selects = [sql for sql in seen if "FROM parts" in sql]
    assert len(selects) == 1, selects


# --- auth / visibility ----------------------------------------------------------


def test_foreign_part_is_a_uniform_404_and_records_nothing(client: TestClient) -> None:
    part = _create_part(client)
    version = _add_datum(client, part["id"])
    response = _record(
        client, part["id"], status="failed", tree_version=version, owner=OTHER
    )
    assert response.status_code == 404
    assert _envelope(response.json())["code"] == "part_not_found"
    assert _get_part(client, part["id"])["eval_state"] == "never"


def test_missing_principal_header_401(client: TestClient) -> None:
    part = _create_part(client)
    response = client.put(
        f"/api/v1/parts/{part['id']}/last-evaluation",
        json={"status": "ok", "tree_version": 0},
    )
    assert response.status_code == 401
    assert _envelope(response.json())["code"] == "missing_principal"


def test_an_unknown_status_is_rejected(client: TestClient) -> None:
    """The stored vocabulary is the DTO's, not free text — a register cannot be
    handed a status nothing knows how to render."""
    part = _create_part(client)
    response = _record(client, part["id"], status="probably-fine", tree_version=0)
    assert response.status_code == 422
    assert _envelope(response.json())["code"] == "validation_error"
