"""documents folders — filing, the four #WS2 decisions, and the rules SQL can't hold.

Dialect posture is :mod:`tests.test_parts`' (SQLite here, Postgres in
production/e2e), with ONE addition that matters to this slice: the per-folder
name uniqueness is a pair of PARTIAL unique indexes precisely so the rule under
test is the rule in production — ``NULLS NOT DISTINCT`` would have been
Postgres-only and this suite would have been asserting a different constraint
from the one that ships. The "two unfiled documents may not share a name" test
below is the one that would have caught that.

Each test is aimed at a decision stated in :mod:`py_kit.schemas.folders`, not at
the happy path: contents survive a refused delete, a folder cannot swallow its
own parent, a move reports where the server actually put the document, and
filing does not pretend to be an edit.
"""

import asyncio
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from documents.db import Base
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from py_kit.db import async_dsn
from py_kit.schemas.folders import MAX_FOLDER_DEPTH
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-0000000000c1"
OTHER = "6f3f6b64-0000-4000-8000-0000000000c2"


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


def _folder(
    client: TestClient,
    name: str,
    *,
    kind: str = "part",
    parent: str | None = None,
    owner: str = OWNER,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/folders",
        json={"name": name, "kind": kind, "parent_id": parent},
        headers=_headers(owner),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _part(client: TestClient, name: str, owner: str = OWNER) -> dict[str, Any]:
    response = client.post(
        "/api/v1/parts", json={"name": name}, headers=_headers(owner)
    )
    assert response.status_code == 201, response.text
    return response.json()


def _move_part(
    client: TestClient, part_id: str, folder_id: str | None, owner: str = OWNER
):
    return client.post(
        f"/api/v1/parts/{part_id}/move",
        json={"folder_id": folder_id},
        headers=_headers(owner),
    )


# --- the tree itself --------------------------------------------------------------


def test_creates_lists_and_nests_folders(client: TestClient) -> None:
    root = _folder(client, "Gearbox")
    child = _folder(client, "Housings", parent=root["id"])

    listed = client.get("/api/v1/folders?kind=part", headers=_headers()).json()
    assert [f["name"] for f in listed["folders"]] == ["Gearbox", "Housings"]
    by_id = {f["id"]: f for f in listed["folders"]}
    # Counts are DIRECT and come from the server: Gearbox holds one FOLDER and
    # no documents, and nothing here lets a client add the two together.
    assert by_id[root["id"]]["child_folder_count"] == 1
    assert by_id[root["id"]]["document_count"] == 0
    assert by_id[child["id"]]["parent_id"] == root["id"]


def test_folder_tree_is_per_kind(client: TestClient) -> None:
    """Decision 1: each drawer has its own tree; they never bleed."""
    _folder(client, "Gearbox", kind="part")
    _folder(client, "Gearbox", kind="drawing")  # same name, different drawer: fine

    parts = client.get("/api/v1/folders?kind=part", headers=_headers()).json()
    drawings = client.get("/api/v1/folders?kind=drawing", headers=_headers()).json()
    assert [f["kind"] for f in parts["folders"]] == ["part"]
    assert [f["kind"] for f in drawings["folders"]] == ["drawing"]

    # ...and a folder may not be nested under one from another drawer.
    drawing_folder = drawings["folders"][0]
    refused = client.post(
        "/api/v1/folders",
        json={"name": "Sub", "kind": "part", "parent_id": drawing_folder["id"]},
        headers=_headers(),
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "folder_kind_mismatch"


def test_sibling_names_are_unique_per_folder_including_the_root(
    client: TestClient,
) -> None:
    parent = _folder(client, "Gearbox")
    _folder(client, "Housings", parent=parent["id"])

    duplicate_sibling = client.post(
        "/api/v1/folders",
        json={"name": "Housings", "kind": "part", "parent_id": parent["id"]},
        headers=_headers(),
    )
    assert duplicate_sibling.status_code == 409
    assert duplicate_sibling.json()["error"]["code"] == "folder_name_taken"

    # The ROOT is where a plain composite UNIQUE would have silently allowed a
    # duplicate (SQL treats NULLs as distinct) — the partial index closes it.
    duplicate_root = client.post(
        "/api/v1/folders",
        json={"name": "Gearbox", "kind": "part", "parent_id": None},
        headers=_headers(),
    )
    assert duplicate_root.status_code == 409

    # Same name under a DIFFERENT parent is legal — the point of folders.
    other = _folder(client, "Shafts")
    _folder(client, "Housings", parent=other["id"])


def test_folders_are_owner_scoped(client: TestClient) -> None:
    folder = _folder(client, "Gearbox")
    assert (
        client.get("/api/v1/folders?kind=part", headers=_headers(OTHER)).json()[
            "folders"
        ]
        == []
    )
    foreign = client.patch(
        f"/api/v1/folders/{folder['id']}",
        json={"name": "Theirs"},
        headers=_headers(OTHER),
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "folder_not_found"


# --- moving ----------------------------------------------------------------------


def test_folder_cannot_be_moved_into_itself_or_a_descendant(
    client: TestClient,
) -> None:
    root = _folder(client, "Gearbox")
    child = _folder(client, "Housings", parent=root["id"])
    grandchild = _folder(client, "Covers", parent=child["id"])

    into_self = client.post(
        f"/api/v1/folders/{root['id']}/move",
        json={"parent_id": root["id"]},
        headers=_headers(),
    )
    assert into_self.status_code == 422
    assert into_self.json()["error"]["code"] == "folder_cycle"

    into_descendant = client.post(
        f"/api/v1/folders/{root['id']}/move",
        json={"parent_id": grandchild["id"]},
        headers=_headers(),
    )
    assert into_descendant.status_code == 422
    assert into_descendant.json()["error"]["code"] == "folder_cycle"

    # The subtree is untouched by the refusals — nothing was half-moved.
    listed = client.get("/api/v1/folders?kind=part", headers=_headers()).json()
    parents = {f["name"]: f["parent_id"] for f in listed["folders"]}
    assert parents["Gearbox"] is None
    assert parents["Housings"] == root["id"]
    assert parents["Covers"] == child["id"]


def test_folder_moves_to_the_root_with_an_explicit_null(client: TestClient) -> None:
    root = _folder(client, "Gearbox")
    child = _folder(client, "Housings", parent=root["id"])
    moved = client.post(
        f"/api/v1/folders/{child['id']}/move",
        json={"parent_id": None},
        headers=_headers(),
    )
    assert moved.status_code == 200
    assert moved.json()["parent_id"] is None


def test_nesting_is_bounded(client: TestClient) -> None:
    parent: str | None = None
    for level in range(MAX_FOLDER_DEPTH):
        parent = _folder(client, f"Level {level}", parent=parent)["id"]
    too_deep = client.post(
        "/api/v1/folders",
        json={"name": "One too many", "kind": "part", "parent_id": parent},
        headers=_headers(),
    )
    assert too_deep.status_code == 422
    assert too_deep.json()["error"]["code"] == "folder_too_deep"


# --- deleting: decision 4, refuse and NAME the contents ---------------------------


def test_deleting_a_folder_holding_documents_is_refused_and_names_them(
    client: TestClient,
) -> None:
    folder = _folder(client, "Gearbox")
    part = _part(client, "Bracket")
    assert _move_part(client, part["id"], folder["id"]).status_code == 200

    refused = client.delete(f"/api/v1/folders/{folder['id']}", headers=_headers())
    assert refused.status_code == 409
    error = refused.json()["error"]
    assert error["code"] == "folder_not_empty"
    # A LIST, by name — the caller's next action is to move these out.
    assert error["details"]["contents"] == [
        {"id": part["id"], "name": "Bracket", "kind": "part"}
    ]

    # NOT a cascade and NOT an orphan: the part is exactly where it was.
    assert (
        client.get(f"/api/v1/parts/{part['id']}", headers=_headers()).json()[
            "folder_id"
        ]
        == folder["id"]
    )

    # Emptying it makes the delete go through.
    assert _move_part(client, part["id"], None).status_code == 200
    assert (
        client.delete(f"/api/v1/folders/{folder['id']}", headers=_headers()).status_code
        == 204
    )


def test_deleting_a_folder_holding_a_subfolder_names_the_subfolder(
    client: TestClient,
) -> None:
    root = _folder(client, "Gearbox")
    child = _folder(client, "Housings", parent=root["id"])
    refused = client.delete(f"/api/v1/folders/{root['id']}", headers=_headers())
    assert refused.status_code == 409
    assert refused.json()["error"]["details"]["contents"] == [
        {"id": child["id"], "name": "Housings", "kind": "folder"}
    ]


# --- filing a document -----------------------------------------------------------


def test_move_reports_where_the_document_ACTUALLY_is(client: TestClient) -> None:
    folder = _folder(client, "Gearbox")
    part = _part(client, "Bracket")

    moved = _move_part(client, part["id"], folder["id"])
    assert moved.status_code == 200
    assert moved.json()["folder_id"] == folder["id"]
    # ...and re-reading it agrees, so the response was not an optimistic echo.
    assert (
        client.get(f"/api/v1/parts/{part['id']}", headers=_headers()).json()[
            "folder_id"
        ]
        == folder["id"]
    )

    unfiled = _move_part(client, part["id"], None)
    assert unfiled.status_code == 200
    assert unfiled.json()["folder_id"] is None


def test_filing_is_not_an_edit(client: TestClient) -> None:
    """It moves neither ``tree_version`` nor ``updated_at``.

    Both matter to a surface: a version bump would mark a recorded evaluate
    stale (a part would "need rebuilding" because someone tidied the drawer),
    and an ``updated_at`` bump would make LAST WORKED say "just now" for a
    document nobody worked on.
    """
    folder = _folder(client, "Gearbox")
    part = _part(client, "Bracket")
    before = client.get(f"/api/v1/parts/{part['id']}", headers=_headers()).json()

    _move_part(client, part["id"], folder["id"])
    after = client.get(f"/api/v1/parts/{part['id']}", headers=_headers()).json()
    assert after["tree_version"] == before["tree_version"]
    assert after["updated_at"] == before["updated_at"]
    assert after["folder_id"] == folder["id"]


def test_documents_of_the_wrong_kind_cannot_be_filed(client: TestClient) -> None:
    drawing_folder = _folder(client, "Sheets", kind="drawing")
    part = _part(client, "Bracket")
    refused = _move_part(client, part["id"], drawing_folder["id"])
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "folder_kind_mismatch"


def test_document_names_are_unique_per_folder(client: TestClient) -> None:
    left = _folder(client, "Left")
    right = _folder(client, "Right")
    a = _part(client, "Bracket")
    b = _part(client, "Bracket 2")
    assert _move_part(client, a["id"], left["id"]).status_code == 200
    assert _move_part(client, b["id"], right["id"]).status_code == 200

    # Two folders may each hold a "Bracket" — this is the point of #WS2.
    renamed = client.patch(
        f"/api/v1/parts/{b['id']}",
        json={"name": "Bracket", "expected_tree_version": b["tree_version"]},
        headers=_headers(),
    )
    assert renamed.status_code == 200

    # ...but ONE folder may not hold two, so filing the second into Left fails.
    collision = _move_part(client, b["id"], left["id"])
    assert collision.status_code == 409
    assert collision.json()["error"]["code"] == "part_name_taken"
    # Refused cleanly: it is still in Right.
    assert (
        client.get(f"/api/v1/parts/{b['id']}", headers=_headers()).json()["folder_id"]
        == right["id"]
    )


def test_two_unfiled_documents_may_not_share_a_name(client: TestClient) -> None:
    """The partial-index half a plain composite UNIQUE would have missed."""
    _part(client, "Bracket")
    duplicate = client.post(
        "/api/v1/parts", json={"name": "Bracket"}, headers=_headers()
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "part_name_taken"


def test_moving_to_an_unknown_folder_is_a_uniform_404(client: TestClient) -> None:
    part = _part(client, "Bracket")
    missing = _move_part(client, part["id"], str(uuid.uuid4()))
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "folder_not_found"


def test_a_duplicate_lands_in_its_sources_folder(client: TestClient) -> None:
    folder = _folder(client, "Gearbox")
    part = _part(client, "Bracket")
    _move_part(client, part["id"], folder["id"])
    copy = client.post(
        f"/api/v1/parts/{part['id']}/duplicate", headers=_headers()
    ).json()
    assert copy["folder_id"] == folder["id"]
    assert copy["name"] == "Bracket copy"
