"""documents part parameter table (PART-PARAMETERS step 3, :mod:`documents.parameters`).

Pinned here:

* GET/PUT, the resolved ``value`` stored on every write, and the optimistic
  ``expected_tree_version`` (stale → 422 ``stale_tree_version``, as every tree
  write);
* every refusal is a 422 with the expression error's code, and leaves the
  table and ``tree_version`` untouched;
* a PUT is ONE history step: undo restores the previous table byte-for-byte,
  redo reapplies it, and a snapshot written before the table existed reads [];
* named versions, ``.loft`` export/import and duplicate carry the table;
* another owner's part is a 404.

SQLite file-per-test like the sibling suites, plus one run on the migrated
Postgres schema.
"""

import asyncio
import json
import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from documents.db import Base
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.expr import MAX_PARAMETERS
from loft_wire.loft_file import LoftTree, LoftVersionList, pack_part, read_loft
from loft_wire.parts import PRINCIPAL_HEADER
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000018a"
OTHER = "6f3f6b64-0000-4000-8000-00000000018b"


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "documents.db"


@pytest.fixture
def client(db_path: Path) -> Iterator[TestClient]:
    url = f"sqlite:///{db_path}"
    asyncio.run(_create_schema(url))
    with TestClient(build_app(DocumentsSettings(postgres_url=url))) as test_client:
        yield test_client


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


def _row(name: str, expression: str, unit: str = "length", **extra: Any) -> Any:
    return {
        "id": extra.pop("id", str(uuid.uuid4())),
        "name": name,
        "expression": expression,
        "unit": unit,
        **extra,
    }


def _sketch() -> dict[str, Any]:
    return {
        "type": "sketch",
        "version": 1,
        "params": {
            "plane": {"kind": "datum_plane", "plane": "XY"},
            "entities": [
                {
                    "construction": False,
                    "id": "e1",
                    "kind": "line",
                    "start": {"x": 0.0, "y": 0.0},
                    "end": {"x": 10.0, "y": 0.0},
                }
            ],
            "constraints": [],
        },
    }


class Part:
    """A part under test, tracking its tree_version."""

    def __init__(self, client: TestClient, name: str = "Bracket") -> None:
        self.client = client
        response = client.post("/api/v1/parts", json={"name": name}, headers=_headers())
        assert response.status_code == 201, response.text
        self.id: str = response.json()["id"]
        self.version = 0

    def put(self, rows: list[dict[str, Any]], version: int | None = None) -> Any:
        response = self.client.put(
            f"/api/v1/parts/{self.id}/parameters",
            json={
                "expected_tree_version": self.version if version is None else version,
                "parameters": rows,
            },
            headers=_headers(),
        )
        if response.status_code == 200:
            self.version = response.json()["tree_version"]
        return response

    def get(self) -> Any:
        response = self.client.get(
            f"/api/v1/parts/{self.id}/parameters", headers=_headers()
        )
        assert response.status_code == 200, response.text
        return response

    def rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = self.get().json()["parameters"]
        return rows

    def add_sketch(self) -> None:
        response = self.client.post(
            f"/api/v1/parts/{self.id}/features",
            json={
                "name": "Sketch1",
                "feature": _sketch(),
                "expected_tree_version": self.version,
            },
            headers=_headers(),
        )
        assert response.status_code == 201, response.text
        self.version = response.json()["tree_version"]

    def step(self, direction: str) -> dict[str, Any]:
        response = self.client.post(
            f"/api/v1/parts/{self.id}/{direction}",
            json={"expected_tree_version": self.version},
            headers=_headers(),
        )
        assert response.status_code == 200, response.text
        self.version = response.json()["tree_version"]
        body: dict[str, Any] = response.json()
        return body


def _table_bytes(part: Part) -> bytes:
    """The table exactly as served, without the moving tree_version."""
    return json.dumps(part.get().json()["parameters"]).encode()


# --- GET / PUT --------------------------------------------------------------------


def test_a_new_part_has_an_empty_table(client: TestClient) -> None:
    part = Part(client)
    assert part.get().json() == {"tree_version": 0, "parameters": []}


def test_put_stores_the_table_with_resolved_values(client: TestClient) -> None:
    part = Part(client)
    rows = [
        _row("half", "width / 2"),
        _row("width", "1 in + 14.6", comment="overall width"),
        _row("draft", "atan(1)", "angle"),
    ]
    response = part.put(rows)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tree_version"] == 1
    assert [row["name"] for row in body["parameters"]] == ["half", "width", "draft"]
    assert [row["value"] for row in body["parameters"]] == pytest.approx(
        [20.0, 40.0, 45.0]
    )
    assert body["parameters"][1]["comment"] == "overall width"
    assert [row["id"] for row in body["parameters"]] == [row["id"] for row in rows]
    assert part.get().json() == body
    # A table write is a tree edit: the feature tree's version moved with it.
    tree = client.get(f"/api/v1/parts/{part.id}/features", headers=_headers())
    assert tree.json()["tree_version"] == 1
    assert tree.json()["can_undo"] is True


def test_put_refuses_a_stale_tree_version(client: TestClient) -> None:
    part = Part(client)
    assert part.put([_row("a", "1")]).status_code == 200
    stale = part.put([_row("a", "2")], version=0)
    assert stale.status_code == 422
    assert stale.json()["error"]["code"] == "stale_tree_version"
    assert [row["value"] for row in part.rows()] == [1.0]


@pytest.mark.parametrize(
    ("rows", "code"),
    [
        ([("a", "2 +")], "expression_syntax"),
        ([("a", "b * 2")], "expression_unknown_name"),
        ([("pi", "3")], "expression_name_invalid"),
        ([("my-width", "3")], "expression_name_invalid"),
        ([("a", "1"), ("a", "2")], "expression_name_invalid"),
        ([("a", "1 / 0")], "expression_domain"),
        ([("a", "sqrt(0 - 1)")], "expression_domain"),
        ([("a", "5 deg")], "expression_units"),
        ([("a", "__import__('os').system('true')")], "expression_syntax"),
    ],
)
def test_a_table_that_does_not_evaluate_is_a_422_and_changes_nothing(
    client: TestClient, rows: list[tuple[str, str]], code: str
) -> None:
    part = Part(client)
    assert part.put([_row("keep", "7")]).status_code == 200
    before = part.get().json()
    response = part.put([_row(name, text) for name, text in rows])
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == code
    assert part.get().json() == before


def test_a_cycle_is_a_422_naming_the_chain(client: TestClient) -> None:
    part = Part(client)
    response = part.put([_row("a", "b + 1"), _row("b", "a * 2")])
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "expression_cycle"
    assert error["details"]["chain"] == ["a", "b", "a"]
    assert "a -> b -> a" in error["message"]


def test_an_unknown_name_names_the_row(client: TestClient) -> None:
    part = Part(client)
    response = part.put([_row("a", "1"), _row("b", "a + missing")])
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "expression_unknown_name"
    assert error["details"]["parameter"] == "b"
    assert "missing" in error["message"]


def test_the_input_limits_hold(client: TestClient) -> None:
    part = Part(client)
    too_many = [_row(f"p{index}", "1") for index in range(MAX_PARAMETERS + 1)]
    assert part.put(too_many).status_code == 422
    assert part.put([_row("a", "1" * 257)]).status_code == 422
    assert part.put([_row("a" * 65, "1")]).status_code == 422
    assert part.put([_row("a", "1", comment="x" * 501)]).status_code == 422
    assert part.put([_row("a", "1", unit="furlong")]).status_code == 422
    assert part.put([_row("a", "1", value=5.0)]).status_code == 422
    repeated = _row("a", "1")
    assert part.put([repeated, {**repeated, "name": "b"}]).status_code == 422
    assert part.rows() == []
    assert part.put(too_many[:MAX_PARAMETERS]).status_code == 200
    assert len(part.rows()) == MAX_PARAMETERS


def test_another_owners_part_is_a_404(client: TestClient) -> None:
    part = Part(client)
    assert part.put([_row("a", "1")]).status_code == 200
    path = f"/api/v1/parts/{part.id}/parameters"
    assert client.get(path, headers=_headers(OTHER)).status_code == 404
    foreign = client.put(
        path,
        json={"expected_tree_version": 1, "parameters": []},
        headers=_headers(OTHER),
    )
    assert foreign.status_code == 404
    assert [row["name"] for row in part.rows()] == ["a"]
    missing = f"/api/v1/parts/{uuid.uuid4()}/parameters"
    assert client.get(missing, headers=_headers()).status_code == 404


# --- renames between parameters --------------------------------------------------


def _renamed(rows: list[dict[str, Any]], names: dict[str, str]) -> list[dict[str, Any]]:
    """The stored rows as a client sends them back, with some names changed."""
    return [
        {
            "id": row["id"],
            "name": names.get(row["name"], row["name"]),
            "expression": row["expression"],
            "unit": row["unit"],
            "comment": row["comment"],
        }
        for row in rows
    ]


def test_a_rename_rewrites_the_parameters_that_read_it(client: TestClient) -> None:
    part = Part(client)
    assert (
        part.put([_row("W", "40"), _row("H", "W - 15", comment="h")]).status_code == 200
    )
    before = part.rows()
    response = part.put(_renamed(before, {"W": "Wid"}))
    assert response.status_code == 200, response.text
    after = part.rows()
    assert [(r["id"], r["name"], r["expression"], r["value"]) for r in after] == [
        (before[0]["id"], "Wid", "40", 40.0),
        (before[1]["id"], "H", "Wid - 15", 25.0),
    ]
    assert after[1]["comment"] == "h"
    # One undo step restores the old names and formula together.
    part.step("undo")
    assert part.rows() == before


def test_a_swap_is_a_swap_and_a_row_the_put_writes_is_taken_as_written(
    client: TestClient,
) -> None:
    part = Part(client)
    assert (
        part.put([_row("a", "1"), _row("b", "a + 1"), _row("c", "a * 3")]).status_code
        == 200
    )
    stored = part.rows()
    swapped = _renamed(stored, {"a": "b", "b": "a"})
    swapped[2]["expression"] = "b * 3"  # the client already followed the rename
    assert part.put(swapped).status_code == 200
    assert [(r["name"], r["expression"], r["value"]) for r in part.rows()] == [
        ("b", "1", 1.0),
        ("a", "b + 1", 2.0),
        ("c", "b * 3", 3.0),
    ]


def test_a_rename_past_the_formula_cap_is_a_422_naming_the_row(
    client: TestClient,
) -> None:
    part = Part(client)
    assert (
        part.put([_row("W", "1"), _row("H", "+".join(["W"] * 128))]).status_code == 200
    )
    before = part.get().json()
    response = part.put(_renamed(before["parameters"], {"W": "Width"}))
    assert response.status_code == 422
    error = response.json()["error"]
    assert (error["code"], error["details"]["parameter"]) == (
        "expression_too_complex",
        "H",
    )
    assert part.get().json() == before


# --- history ----------------------------------------------------------------------


def test_put_then_undo_restores_the_table_byte_for_byte_and_redo_reapplies(
    client: TestClient,
) -> None:
    part = Part(client)
    part.add_sketch()
    assert (
        part.put([_row("w", "40", comment="first"), _row("h", "w/4")]).status_code
        == 200
    )
    first = _table_bytes(part)
    assert part.put([_row("w", "55"), _row("t", "3 mm")]).status_code == 200
    second = _table_bytes(part)
    assert first != second

    part.step("undo")
    assert _table_bytes(part) == first
    part.step("undo")
    assert part.rows() == []
    # The feature the table was edited around is untouched by its undo.
    tree = client.get(f"/api/v1/parts/{part.id}/features", headers=_headers())
    assert len(tree.json()["features"]) == 1
    part.step("redo")
    assert _table_bytes(part) == first
    part.step("redo")
    assert _table_bytes(part) == second


def test_a_snapshot_from_before_the_table_reads_empty(
    client: TestClient, db_path: Path
) -> None:
    part = Part(client)
    part.add_sketch()  # seeds snapshots 0 (empty) and 1 (the sketch)
    with sqlite3.connect(db_path) as connection:
        stored = connection.execute("SELECT seq, state FROM part_snapshots").fetchall()
        for seq, state in stored:
            old = json.loads(state)
            old.pop("parameters")
            connection.execute(
                "UPDATE part_snapshots SET state = ? WHERE seq = ?",
                (json.dumps(old), seq),
            )
    assert part.put([_row("w", "40")]).status_code == 200
    part.step("undo")
    assert part.rows() == []
    part.step("redo")
    assert [row["name"] for row in part.rows()] == ["w"]


# --- versions, .loft, duplicate ---------------------------------------------------


def _save(part: Part, name: str) -> None:
    response = part.client.post(
        f"/api/v1/parts/{part.id}/versions", json={"name": name}, headers=_headers()
    )
    assert response.status_code == 201, response.text


def _restore(part: Part, seq: int) -> None:
    response = part.client.post(
        f"/api/v1/parts/{part.id}/versions/{seq}/restore",
        json={"expected_tree_version": part.version},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    part.version = response.json()["tree_version"]


def test_a_named_version_round_trips_its_parameters(client: TestClient) -> None:
    part = Part(client)
    part.add_sketch()
    assert part.put([_row("w", "40"), _row("a", "15", "angle")]).status_code == 200
    saved = _table_bytes(part)
    _save(part, "Rev A")
    assert part.put([_row("w", "99")]).status_code == 200

    _restore(part, 1)
    assert _table_bytes(part) == saved
    # The restore is one undoable edit, parameters included.
    part.step("undo")
    assert [row["value"] for row in part.rows()] == [99.0]
    listed = client.get(f"/api/v1/parts/{part.id}/loft-versions", headers=_headers())
    [version] = listed.json()["versions"]
    assert [row["name"] for row in version["tree"]["parameters"]] == ["w", "a"]


def test_a_version_without_parameters_keeps_its_tree_bytes(client: TestClient) -> None:
    part = Part(client)
    part.add_sketch()
    _save(part, "Rev A")
    listed = client.get(f"/api/v1/parts/{part.id}/loft-versions", headers=_headers())
    assert "parameters" not in listed.json()["versions"][0]["tree"]
    assert part.put([_row("w", "1")]).status_code == 200
    _restore(part, 1)
    assert part.rows() == []


def _export(client: TestClient, part_id: str) -> bytes:
    tree = client.get(f"/api/v1/parts/{part_id}/loft-tree", headers=_headers())
    listed = client.get(f"/api/v1/parts/{part_id}/loft-versions", headers=_headers())
    assert tree.status_code == 200 and listed.status_code == 200
    return pack_part(
        document_id=uuid.UUID(part_id),
        tree=LoftTree.model_validate(tree.json()),
        loft_version="test",
        versions=LoftVersionList.model_validate(listed.json()).versions,
    )


def test_a_loft_export_and_import_carry_the_table(client: TestClient) -> None:
    part = Part(client)
    part.add_sketch()
    assert part.put([_row("w", "40")]).status_code == 200
    _save(part, "Rev A")
    assert part.put([_row("w", "40"), _row("h", "w / 2")]).status_code == 200
    archive = read_loft(_export(client, part.id))
    created = client.post(
        "/api/v1/parts/import-loft",
        json={
            "document_id": str(archive.manifest.document_id),
            "tree": archive.tree.model_dump(mode="json"),
            "versions": [v.model_dump(mode="json") for v in archive.versions],
        },
        headers=_headers(),
    )
    assert created.status_code == 201, created.text
    copy = Part(client, "unused")
    copy.id = created.json()["id"]
    copy.version = 1
    assert copy.rows() == part.rows()
    _restore(copy, 1)
    assert [row["name"] for row in copy.rows()] == ["w"]


def test_an_import_with_a_bad_table_is_refused(client: TestClient) -> None:
    part = Part(client)
    assert part.put([_row("w", "40")]).status_code == 200
    tree = client.get(f"/api/v1/parts/{part.id}/loft-tree", headers=_headers()).json()
    tree["parameters"][0]["expression"] = "w + 1"
    response = client.post(
        "/api/v1/parts/import-loft",
        json={"document_id": str(uuid.uuid4()), "tree": tree, "versions": []},
        headers=_headers(),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "expression_cycle"


def test_duplicate_copies_the_table(client: TestClient) -> None:
    part = Part(client)
    assert part.put([_row("w", "40")]).status_code == 200
    response = client.post(f"/api/v1/parts/{part.id}/duplicate", headers=_headers())
    assert response.status_code == 201, response.text
    copy = Part(client, "unused")
    copy.id = response.json()["id"]
    assert copy.rows() == part.rows()


# --- Postgres ---------------------------------------------------------------------


def test_parameters_on_postgres_with_the_migrated_schema(pg_url: str) -> None:
    """PUT, undo/redo and a version restore on the real JSONB column."""
    with TestClient(build_app(DocumentsSettings(postgres_url=pg_url))) as client:
        part = Part(client)
        assert part.get().json()["parameters"] == []
        part.add_sketch()
        assert (
            part.put(
                [_row("width", "40", comment="é"), _row("h", "width/4")]
            ).status_code
            == 200
        )
        first = _table_bytes(part)
        _save(part, "Rev A")
        assert part.put([_row("width", "50")]).status_code == 200
        part.step("undo")
        assert _table_bytes(part) == first
        part.step("redo")
        assert [row["value"] for row in part.rows()] == [50.0]
        _restore(part, 1)
        assert _table_bytes(part) == first
        cycle = part.put([_row("a", "b"), _row("b", "a")])
        assert cycle.status_code == 422
        assert cycle.json()["error"]["details"]["chain"] == ["a", "b", "a"]
