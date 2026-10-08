"""documents named part versions (LOFT-VERSIONS, :mod:`documents.versions`).

Pinned here:

* save / list / restore, and seq that only grows;
* restore is ONE undoable edit through the history ring, and never deletes a
  version;
* every route is owner-scoped (another owner's part is a 404);
* the caps (count and bytes) refuse, never prune;
* a ``.loft`` round trip with versions is byte-stable, keeps each seq, and
  re-mints a version's ids with the rest of the file when they collide.

Same SQLite file-per-test posture as the sibling suites, plus one run on the
migrated Postgres schema.
"""

import asyncio
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from documents import versions as versions_module
from documents.db import Base
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.loft_file import (
    LoftTree,
    LoftVersionList,
    pack_part,
    read_loft,
)
from loft_wire.parts import PRINCIPAL_HEADER
from loft_wire.versions import MAX_PART_VERSIONS_TOTAL_BYTES
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000017a"
OTHER = "6f3f6b64-0000-4000-8000-00000000017b"


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[Callable[[str], TestClient]]:
    """A documents app per named database: two installs in one test."""
    opened: list[Any] = []

    def make(name: str) -> TestClient:
        url = f"sqlite:///{tmp_path}/{name}.db"
        asyncio.run(_create_schema(url))
        manager = TestClient(build_app(DocumentsSettings(postgres_url=url)))
        client = manager.__enter__()
        opened.append(manager)
        return client

    yield make
    for manager in opened:
        manager.__exit__(None, None, None)


@pytest.fixture
def client(make_client: Callable[[str], TestClient]) -> TestClient:
    return make_client("install-a")


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


def _sketch(width: float) -> dict[str, Any]:
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
                    "end": {"x": width, "y": 0.0},
                }
            ],
            "constraints": [],
        },
    }


def _extrude(sketch_id: str, distance: float) -> dict[str, Any]:
    return {
        "type": "extrude",
        "version": 1,
        "params": {
            "profile": {"kind": "feature", "feature_id": sketch_id},
            "distance_mm": distance,
            "operation": "add",
            "direction": "normal",
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

    def add(self, name: str, feature: dict[str, Any]) -> str:
        response = self.client.post(
            f"/api/v1/parts/{self.id}/features",
            json={
                "name": name,
                "feature": feature,
                "expected_tree_version": self.version,
            },
            headers=_headers(),
        )
        assert response.status_code == 201, response.text
        self.version = response.json()["tree_version"]
        feature_id: str = response.json()["feature"]["id"]
        return feature_id

    def delete(self, feature_id: str) -> None:
        response = self.client.delete(
            f"/api/v1/parts/{self.id}/features/{feature_id}",
            params={"expected_tree_version": self.version},
            headers=_headers(),
        )
        assert response.status_code == 200, response.text
        self.version = response.json()["tree_version"]

    def save(self, name: str, **extra: Any) -> Any:
        return self.client.post(
            f"/api/v1/parts/{self.id}/versions",
            json={"name": name, **extra},
            headers=_headers(),
        )

    def restore(self, seq: int) -> Any:
        response = self.client.post(
            f"/api/v1/parts/{self.id}/versions/{seq}/restore",
            json={"expected_tree_version": self.version},
            headers=_headers(),
        )
        if response.status_code == 200:
            self.version = response.json()["tree_version"]
        return response

    def history(self, direction: str) -> dict[str, Any]:
        response = self.client.post(
            f"/api/v1/parts/{self.id}/{direction}",
            json={"expected_tree_version": self.version},
            headers=_headers(),
        )
        assert response.status_code == 200, response.text
        self.version = response.json()["tree_version"]
        body: dict[str, Any] = response.json()
        return body

    def tree(self) -> dict[str, Any]:
        response = self.client.get(
            f"/api/v1/parts/{self.id}/features", headers=_headers()
        )
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def feature_ids(self) -> list[str]:
        return [feature["id"] for feature in self.tree()["features"]]

    def versions(self) -> list[dict[str, Any]]:
        response = self.client.get(
            f"/api/v1/parts/{self.id}/versions", headers=_headers()
        )
        assert response.status_code == 200, response.text
        listed: list[dict[str, Any]] = response.json()["versions"]
        return listed


def _two_versions(client: TestClient) -> tuple[Part, dict[str, str]]:
    """v1 = Sketch1 + Extrude1 (10 mm); v2 adds Sketch2; the live tree then
    loses Extrude1 and gains Extrude2 (25 mm) on Sketch2."""
    part = Part(client)
    sketch = part.add("Sketch1", _sketch(40.0))
    extrude = part.add("Extrude1", _extrude(sketch, 10.0))
    assert part.save("Rev A", message="First article", author="Ada").status_code == 201
    sketch2 = part.add("Sketch2", _sketch(20.0))
    assert part.save("Rev B").status_code == 201
    part.delete(extrude)
    extrude2 = part.add("Extrude2", _extrude(sketch2, 25.0))
    return part, {
        "sketch": sketch,
        "extrude": extrude,
        "sketch2": sketch2,
        "extrude2": extrude2,
    }


# --- save / list ------------------------------------------------------------------


def test_save_and_list_newest_first(client: TestClient) -> None:
    part, ids = _two_versions(client)
    listed = part.versions()
    assert [v["seq"] for v in listed] == [2, 1]
    rev_a = listed[1]
    assert rev_a["name"] == "Rev A"
    assert rev_a["message"] == "First article"
    assert rev_a["author"] == "Ada"
    assert rev_a["feature_count"] == 2
    assert listed[0]["author"] is None
    assert listed[0]["feature_count"] == 3
    # A display name and nothing else: no account id, no email, no tree.
    assert set(rev_a) == {
        "seq",
        "name",
        "message",
        "author",
        "created_at",
        "tree_sha256",
        "feature_count",
    }
    assert OWNER not in str(listed)
    assert ids["extrude"] not in str(listed)


def test_saving_is_not_a_tree_edit(client: TestClient) -> None:
    part = Part(client)
    part.add("Sketch1", _sketch(40.0))
    before = part.tree()
    response = part.save("Rev A", expected_tree_version=part.version)
    assert response.status_code == 201, response.text
    after = part.tree()
    assert after["tree_version"] == before["tree_version"]
    assert after["can_undo"] == before["can_undo"]


def test_save_refuses_a_stale_tree_version(client: TestClient) -> None:
    part = Part(client)
    part.add("Sketch1", _sketch(40.0))
    response = part.save("Rev A", expected_tree_version=0)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "stale_tree_version"


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "x" * 121},
        {"name": "Rev A", "author": "x" * 81},
        {"name": "Rev A", "message": "x" * 2001},
        {"name": "Rev A", "owner_id": OWNER},
    ],
    ids=["empty-name", "long-name", "long-author", "long-message", "extra-key"],
)
def test_save_input_limits(client: TestClient, body: dict[str, Any]) -> None:
    part = Part(client)
    response = client.post(
        f"/api/v1/parts/{part.id}/versions", json=body, headers=_headers()
    )
    assert response.status_code == 422


def test_seq_only_grows(client: TestClient) -> None:
    part = Part(client)
    seqs = [part.save(f"v{n}").json()["seq"] for n in range(3)]
    assert seqs == [1, 2, 3]


# --- restore --------------------------------------------------------------------


def test_restore_brings_back_the_tree_and_keeps_every_version(
    client: TestClient,
) -> None:
    part, ids = _two_versions(client)
    version_before = part.version
    response = part.restore(1)
    assert response.status_code == 200, response.text
    tree = response.json()
    assert [f["id"] for f in tree["features"]] == [ids["sketch"], ids["extrude"]]
    assert tree["features"][1]["feature"]["params"]["distance_mm"] == 10.0
    assert tree["tree_version"] == version_before + 1
    # Later versions are kept; restoring never deletes one.
    assert [v["seq"] for v in part.versions()] == [2, 1]
    # And restoring the later version works too.
    assert part.restore(2).status_code == 200
    assert part.feature_ids() == [ids["sketch"], ids["extrude"], ids["sketch2"]]


def test_restore_is_one_undoable_edit(client: TestClient) -> None:
    part, ids = _two_versions(client)
    live = [ids["sketch"], ids["sketch2"], ids["extrude2"]]
    assert part.feature_ids() == live
    assert part.restore(1).status_code == 200
    assert part.feature_ids() == [ids["sketch"], ids["extrude"]]

    undone = part.history("undo")
    assert [f["id"] for f in undone["features"]] == live
    assert undone["can_redo"] is True
    redone = part.history("redo")
    assert [f["id"] for f in redone["features"]] == [ids["sketch"], ids["extrude"]]


def test_restore_rederives_the_dependency_edges(client: TestClient) -> None:
    """Sketch1 is referenced again after restoring v1, so deleting it is refused."""
    part, ids = _two_versions(client)
    assert part.restore(1).status_code == 200
    response = client.delete(
        f"/api/v1/parts/{part.id}/features/{ids['sketch']}",
        params={"expected_tree_version": part.version},
        headers=_headers(),
    )
    assert response.status_code == 409


def test_restore_refuses_a_stale_tree_version_and_an_unknown_seq(
    client: TestClient,
) -> None:
    part, _ = _two_versions(client)
    stale = client.post(
        f"/api/v1/parts/{part.id}/versions/1/restore",
        json={"expected_tree_version": part.version - 1},
        headers=_headers(),
    )
    assert stale.status_code == 422
    assert stale.json()["error"]["code"] == "stale_tree_version"
    missing = part.restore(9)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "part_version_not_found"


# --- owner scoping --------------------------------------------------------------


def test_every_route_is_a_404_for_another_owner(client: TestClient) -> None:
    part, _ = _two_versions(client)
    base = f"/api/v1/parts/{part.id}"
    other = _headers(OTHER)
    responses = [
        client.post(f"{base}/versions", json={"name": "Mine"}, headers=other),
        client.get(f"{base}/versions", headers=other),
        client.get(f"{base}/loft-versions", headers=other),
        client.post(
            f"{base}/versions/1/restore",
            json={"expected_tree_version": part.version},
            headers=other,
        ),
    ]
    for response in responses:
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "part_not_found"
    # Nothing moved for the owner.
    assert [v["seq"] for v in part.versions()] == [2, 1]


def test_routes_need_a_principal(client: TestClient) -> None:
    part = Part(client)
    response = client.get(f"/api/v1/parts/{part.id}/versions")
    assert response.status_code in (401, 422)


# --- caps -----------------------------------------------------------------------


def test_the_count_cap_refuses_and_never_prunes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(versions_module, "MAX_PART_VERSIONS", 2)
    part = Part(client)
    assert part.save("v1").status_code == 201
    assert part.save("v2").status_code == 201
    refused = part.save("v3")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "part_version_limit"
    assert [v["name"] for v in part.versions()] == ["v2", "v1"]


def test_the_size_cap_refuses(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    part = Part(client)
    part.add("Sketch1", _sketch(40.0))
    assert part.save("v1").status_code == 201
    stored = MAX_PART_VERSIONS_TOTAL_BYTES
    monkeypatch.setattr(versions_module, "MAX_PART_VERSIONS_TOTAL_BYTES", 1000)
    refused = part.save("v2")
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "part_version_limit"
    monkeypatch.setattr(versions_module, "MAX_PART_VERSIONS_TOTAL_BYTES", stored)
    assert part.save("v2").status_code == 201


# --- .loft ----------------------------------------------------------------------


def _export(client: TestClient, part_id: str) -> bytes:
    """What the gateway's export does, minus the cached body."""
    tree = client.get(f"/api/v1/parts/{part_id}/loft-tree", headers=_headers())
    listed = client.get(f"/api/v1/parts/{part_id}/loft-versions", headers=_headers())
    assert tree.status_code == 200 and listed.status_code == 200
    return pack_part(
        document_id=uuid.UUID(part_id),
        tree=LoftTree.model_validate(tree.json()),
        loft_version="test",
        versions=LoftVersionList.model_validate(listed.json()).versions,
    )


def _import(client: TestClient, data: bytes) -> Any:
    archive = read_loft(data)
    return client.post(
        "/api/v1/parts/import-loft",
        json={
            "document_id": str(archive.manifest.document_id),
            "tree": archive.tree.model_dump(mode="json"),
            "versions": [v.model_dump(mode="json") for v in archive.versions],
        },
        headers=_headers(),
    )


def test_a_loft_round_trip_with_versions_is_byte_stable(
    make_client: Callable[[str], TestClient],
) -> None:
    first = make_client("install-a")
    part, ids = _two_versions(first)
    exported = _export(first, part.id)
    assert len(read_loft(exported).versions) == 2

    second = make_client("install-b")
    created = _import(second, exported)
    assert created.status_code == 201, created.text
    assert created.json()["id"] == part.id  # ids kept: nothing collides here
    assert _export(second, part.id) == exported

    copy = Part.__new__(Part)
    copy.client, copy.id, copy.version = second, part.id, created.json()["tree_version"]
    listed = copy.versions()
    assert [(v["seq"], v["name"], v["author"]) for v in listed] == [
        (2, "Rev B", None),
        (1, "Rev A", "Ada"),
    ]
    assert listed == part.versions()
    # Rev A's Extrude1 exists only in the version, and it restores there.
    assert copy.restore(1).status_code == 200
    assert copy.feature_ids() == [ids["sketch"], ids["extrude"]]


def test_a_reminted_import_remaps_ids_inside_versions(client: TestClient) -> None:
    part, ids = _two_versions(client)
    created = _import(client, _export(client, part.id))
    assert created.status_code == 201, created.text
    copy = Part.__new__(Part)
    copy.client, copy.id, copy.version = client, created.json()["id"], 1
    assert copy.id != part.id
    assert [v["seq"] for v in copy.versions()] == [2, 1]
    assert copy.restore(1).status_code == 200, "version ids must be re-minted too"
    restored = copy.tree()["features"]
    assert {f["id"] for f in restored}.isdisjoint(ids.values())
    # The copy's extrude points at the copy's sketch, not the original's.
    assert (
        restored[1]["feature"]["params"]["profile"]["feature_id"] == restored[0]["id"]
    )
    # The original is untouched.
    assert part.feature_ids() == [ids["sketch"], ids["sketch2"], ids["extrude2"]]


def test_an_import_without_versions_has_none(client: TestClient) -> None:
    part = Part(client)
    part.add("Sketch1", _sketch(40.0))
    tree = client.get(f"/api/v1/parts/{part.id}/loft-tree", headers=_headers())
    response = client.post(
        "/api/v1/parts/import-loft",
        json={"document_id": str(uuid.uuid4()), "tree": tree.json()},
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    listed = client.get(
        f"/api/v1/parts/{response.json()['id']}/versions", headers=_headers()
    )
    assert listed.json() == {"versions": []}


def test_an_imported_version_that_would_not_restore_is_refused_naming_it(
    client: TestClient,
) -> None:
    part, _ = _two_versions(client)
    archive = read_loft(_export(client, part.id))
    versions = [v.model_dump(mode="json") for v in archive.versions]
    versions[0]["tree"]["features"][1]["type"] = "warp_drive"
    response = client.post(
        "/api/v1/parts/import-loft",
        json={
            "document_id": str(uuid.uuid4()),
            "tree": archive.tree.model_dump(mode="json"),
            "versions": versions,
        },
        headers=_headers(),
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "loft_feature_unknown_type"
    assert error["details"]["version_seq"] == 1


def test_versions_on_postgres_with_the_migrated_schema(pg_url: str) -> None:
    """Save, restore, undo and a re-minted import on the real schema (the
    composite same-part FKs exist only in the migrations)."""
    with TestClient(build_app(DocumentsSettings(postgres_url=pg_url))) as client:
        part, ids = _two_versions(client)
        assert [v["seq"] for v in part.versions()] == [2, 1]
        assert part.restore(1).status_code == 200
        assert part.feature_ids() == [ids["sketch"], ids["extrude"]]
        undone = part.history("undo")
        assert [f["id"] for f in undone["features"]] == [
            ids["sketch"],
            ids["sketch2"],
            ids["extrude2"],
        ]
        exported = _export(client, part.id)
        created = _import(client, exported)
        assert created.status_code == 201, created.text
        listed = client.get(
            f"/api/v1/parts/{created.json()['id']}/versions", headers=_headers()
        )
        assert [v["seq"] for v in listed.json()["versions"]] == [2, 1]
        assert (
            listed.json()["versions"][1]["created_at"]
            == (part.versions()[1]["created_at"])
        )
