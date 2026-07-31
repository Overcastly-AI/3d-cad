"""documents duplicate — what a copy carries, and what it deliberately does not.

The assertions here are the contract from :mod:`documents.duplicate` stated as
tests, because "Duplicate" is a verb a user can be silently wrong about: a copy
that carries less than advertised looks correct right up until the original is
edited. Two things are therefore checked in every kind:

1. the copied children EXIST, in order, with their payloads; and
2. the copy is DETACHED — no id inside it points back at the source document,
   and editing one does not move the other.

Same dialect posture as the sibling suites (SQLite file-per-test; see
conftest.py for what that does and does not cover).
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
    url = f"sqlite:///{tmp_path}/documents.db"
    asyncio.run(_create_schema(url))
    return url


@pytest.fixture
def client(db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


SKETCH_PARAMS: dict[str, Any] = {
    "plane": {"kind": "datum_plane", "plane": "XY"},
    "entities": [
        {
            "construction": False,
            "id": "e1",
            "kind": "line",
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 40.0, "y": 0.0},
        }
    ],
    "constraints": [],
}


def _create_part(client: TestClient, name: str, owner: str = OWNER) -> str:
    response = client.post(
        "/api/v1/parts", json={"name": name}, headers=_headers(owner)
    )
    assert response.status_code == 201, response.text
    part_id: str = response.json()["id"]
    return part_id


def _add_feature(
    client: TestClient,
    part_id: str,
    name: str,
    feature: dict[str, Any],
    expected_tree_version: int,
) -> str:
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": name,
            "feature": feature,
            "expected_tree_version": expected_tree_version,
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    feature_id: str = response.json()["feature"]["id"]
    return feature_id


def _tree(client: TestClient, part_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/parts/{part_id}/features", headers=_headers())
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _seeded_part(client: TestClient, name: str = "bracket") -> tuple[str, str, str]:
    """A part whose tree has a REFERENCE in it: Sketch1 ← Extrude1.

    The reference is the whole point: a duplicate that copied the rows but not
    the ref would produce a tree whose extrude still profiles the ORIGINAL
    part's sketch — valid-looking, cross-document, and wrong.
    """
    part_id = _create_part(client, name)
    sketch_id = _add_feature(
        client,
        part_id,
        "Sketch1",
        {"type": "sketch", "version": 1, "params": SKETCH_PARAMS},
        0,
    )
    extrude_id = _add_feature(
        client,
        part_id,
        "Extrude1",
        {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": sketch_id},
                "distance_mm": 10.0,
                "operation": "add",
                "direction": "normal",
            },
        },
        1,
    )
    return part_id, sketch_id, extrude_id


# --- parts ------------------------------------------------------------------------


def test_duplicate_part_copies_the_tree_and_rewrites_its_references(
    client: TestClient,
) -> None:
    part_id, sketch_id, extrude_id = _seeded_part(client)

    response = client.post(f"/api/v1/parts/{part_id}/duplicate", headers=_headers())
    assert response.status_code == 201, response.text
    copy = response.json()
    assert copy["name"] == "bracket copy"
    assert copy["id"] != part_id

    tree = _tree(client, copy["id"])["features"]
    assert [f["name"] for f in tree] == ["Sketch1", "Extrude1"]
    assert [f["order_index"] for f in tree] == [0, 1]
    assert [f["feature"]["type"] for f in tree] == ["sketch", "extrude"]

    # Detached: new feature ids, and the extrude profiles the COPY's sketch.
    copied_ids = {f["id"] for f in tree}
    assert copied_ids.isdisjoint({sketch_id, extrude_id})
    assert tree[1]["feature"]["params"]["profile"]["feature_id"] == tree[0]["id"]
    # ...and the params it did NOT need to rewrite came through verbatim.
    assert tree[1]["feature"]["params"]["distance_mm"] == 10.0
    assert tree[0]["feature"]["params"]["entities"] == SKETCH_PARAMS["entities"]


def test_duplicate_part_carries_dependency_edges_so_the_copy_guards_deletes(
    client: TestClient,
) -> None:
    """The copy's own 409-with-dependents works — edges were copied, not dropped.

    Asserted through BEHAVIOUR rather than by reading the edge table: what a
    dropped edge would actually cost the user is a delete that silently breaks
    the extrude above it.
    """
    part_id, _, _ = _seeded_part(client)
    copy_id = client.post(
        f"/api/v1/parts/{part_id}/duplicate", headers=_headers()
    ).json()["id"]
    tree = _tree(client, copy_id)
    copied_sketch = tree["features"][0]["id"]

    refused = client.delete(
        f"/api/v1/parts/{copy_id}/features/{copied_sketch}",
        params={"expected_tree_version": tree["tree_version"]},
        headers=_headers(),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "feature_has_dependents"
    dependents = refused.json()["error"]["details"]["dependents"]
    assert [d["name"] for d in dependents] == ["Extrude1"]


def test_duplicate_part_carries_header_metadata_but_not_the_evaluate_record(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/parts",
        json={"name": "inch-part", "length_unit": "in"},
        headers=_headers(),
    )
    part_id = response.json()["id"]
    client.patch(
        f"/api/v1/parts/{part_id}",
        json={
            "expected_tree_version": 0,
            "materials": {"default_material": "steel_1018", "overrides": {}},
        },
        headers=_headers(),
    )
    client.put(
        f"/api/v1/parts/{part_id}/last-evaluation",
        json={"tree_version": 1, "status": "ok"},
        headers=_headers(),
    )
    assert (
        client.get(f"/api/v1/parts/{part_id}", headers=_headers()).json()["eval_state"]
        == "ok"
    )

    copy = client.post(f"/api/v1/parts/{part_id}/duplicate", headers=_headers()).json()
    assert copy["length_unit"] == "in"
    assert copy["materials"]["default_material"] == "steel_1018"
    # The copy has never been built, and says so rather than inheriting a
    # verdict about a document that did not exist when it was recorded.
    assert copy["eval_state"] == "never"
    assert copy["last_eval_status"] is None
    assert copy["last_eval_at"] is None
    assert copy["tree_version"] == 0


def test_duplicate_part_carries_the_travel_stop(client: TestClient) -> None:
    part_id, sketch_id, _ = _seeded_part(client)
    rollback = client.put(
        f"/api/v1/parts/{part_id}/rollback",
        json={"expected_tree_version": 2, "rollback_feature_id": sketch_id},
        headers=_headers(),
    )
    assert rollback.status_code == 200, rollback.text

    copy_id = client.post(
        f"/api/v1/parts/{part_id}/duplicate", headers=_headers()
    ).json()["id"]
    tree = _tree(client, copy_id)
    # Remapped onto the COPY's sketch, never left pointing at the source's.
    assert tree["rollback_feature_id"] == tree["features"][0]["id"]
    assert tree["rollback_feature_id"] != sketch_id


def test_editing_a_copy_does_not_touch_the_original(client: TestClient) -> None:
    part_id, _, _ = _seeded_part(client)
    copy_id = client.post(
        f"/api/v1/parts/{part_id}/duplicate", headers=_headers()
    ).json()["id"]
    copy_tree = _tree(client, copy_id)

    deleted = client.delete(
        f"/api/v1/parts/{copy_id}/features/{copy_tree['features'][1]['id']}",
        params={"expected_tree_version": copy_tree["tree_version"]},
        headers=_headers(),
    )
    assert deleted.status_code == 200, deleted.text
    assert len(_tree(client, copy_id)["features"]) == 1
    assert len(_tree(client, part_id)["features"]) == 2


def test_duplicate_names_avoid_collisions_and_stay_predictable(
    client: TestClient,
) -> None:
    part_id = _create_part(client, "plate")
    first = client.post(f"/api/v1/parts/{part_id}/duplicate", headers=_headers()).json()
    second = client.post(
        f"/api/v1/parts/{part_id}/duplicate", headers=_headers()
    ).json()
    third = client.post(f"/api/v1/parts/{part_id}/duplicate", headers=_headers()).json()
    assert [first["name"], second["name"], third["name"]] == [
        "plate copy",
        "plate copy 2",
        "plate copy 3",
    ]


def test_duplicate_is_owner_scoped(client: TestClient) -> None:
    part_id = _create_part(client, "private")
    response = client.post(
        f"/api/v1/parts/{part_id}/duplicate", headers=_headers(OTHER)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "part_not_found"
    assert client.get("/api/v1/parts", headers=_headers(OTHER)).json()["parts"] == []


def test_duplicate_unknown_part_is_404(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/parts/{uuid.uuid4()}/duplicate", headers=_headers()
    )
    assert response.status_code == 404


# --- assemblies -------------------------------------------------------------------


def _seeded_assembly(client: TestClient) -> tuple[str, str, str, str]:
    """An assembly of two instances joined by a lock mate."""
    assembly_id = client.post(
        "/api/v1/assemblies", json={"name": "gearbox"}, headers=_headers()
    ).json()["id"]
    part_a = _create_part(client, "plate-a")
    part_b = _create_part(client, "plate-b")
    instance_a = client.post(
        f"/api/v1/assemblies/{assembly_id}/instances",
        json={
            "expected_version": 0,
            "ref_document_id": part_a,
            "ref_document_kind": "part",
            "name": "Plate <1>",
            "grounded": True,
        },
        headers=_headers(),
    ).json()["instance"]["id"]
    instance_b = client.post(
        f"/api/v1/assemblies/{assembly_id}/instances",
        json={
            "expected_version": 1,
            "ref_document_id": part_b,
            "ref_document_kind": "part",
            "name": "Plate <2>",
            "placement": {
                "position": {"x": 10.0, "y": 0.0, "z": 5.0},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            },
        },
        headers=_headers(),
    ).json()["instance"]["id"]
    mate = client.post(
        f"/api/v1/assemblies/{assembly_id}/mates",
        json={
            "expected_version": 2,
            "mate": {
                "type": "lock",
                "a_instance_id": instance_a,
                "b_instance_id": instance_b,
            },
        },
        headers=_headers(),
    )
    assert mate.status_code == 201, mate.text
    return assembly_id, part_a, instance_a, instance_b


def test_duplicate_assembly_copies_instances_and_rewires_mates(
    client: TestClient,
) -> None:
    assembly_id, _part_a, instance_a, instance_b = _seeded_assembly(client)

    response = client.post(
        f"/api/v1/assemblies/{assembly_id}/duplicate", headers=_headers()
    )
    assert response.status_code == 201, response.text
    copy_id = response.json()["id"]
    assert response.json()["name"] == "gearbox copy"

    graph = client.get(f"/api/v1/assemblies/{copy_id}", headers=_headers()).json()
    instances = graph["instances"]
    assert [i["name"] for i in instances] == ["Plate <1>", "Plate <2>"]
    assert [i["grounded"] for i in instances] == [True, False]
    assert instances[1]["placement"]["position"] == {"x": 10.0, "y": 0.0, "z": 5.0}
    # The instances are NEW rows...
    assert {i["id"] for i in instances}.isdisjoint({instance_a, instance_b})
    # ...and the mate names the COPY's instances, not the source's.
    mate = graph["mates"][0]["mate"]
    assert mate["a_instance_id"] == instances[0]["id"]
    assert mate["b_instance_id"] == instances[1]["id"]


def test_duplicate_assembly_references_the_same_parts(client: TestClient) -> None:
    """Instances are REFERENCES: a copy points at the same parts, and the part
    count does not grow. That is the stated contract, so it is asserted."""
    assembly_id, part_a, _, _ = _seeded_assembly(client)
    before = len(client.get("/api/v1/parts", headers=_headers()).json()["parts"])

    copy_id = client.post(
        f"/api/v1/assemblies/{assembly_id}/duplicate", headers=_headers()
    ).json()["id"]

    after = client.get("/api/v1/parts", headers=_headers()).json()["parts"]
    assert len(after) == before
    graph = client.get(f"/api/v1/assemblies/{copy_id}", headers=_headers()).json()
    assert graph["instances"][0]["ref_document_id"] == part_a


def test_duplicating_an_assembly_makes_its_parts_undeletable_by_both(
    client: TestClient,
) -> None:
    """Both assemblies are real dependents — the 409 names them both."""
    assembly_id, part_a, _, _ = _seeded_assembly(client)
    client.post(f"/api/v1/assemblies/{assembly_id}/duplicate", headers=_headers())

    refused = client.delete(f"/api/v1/parts/{part_a}", headers=_headers())
    assert refused.status_code == 409, refused.text
    dependents = refused.json()["error"]["details"]["dependents"]
    assert sorted(d["name"] for d in dependents) == ["gearbox", "gearbox copy"]
    assert {d["kind"] for d in dependents} == {"assembly"}


# --- drawings ---------------------------------------------------------------------


def test_duplicate_drawing_copies_the_layout_and_keeps_its_references(
    client: TestClient,
) -> None:
    part_id = _create_part(client, "bracket")
    drawing_id = client.post(
        "/api/v1/drawings", json={"name": "bracket-detail"}, headers=_headers()
    ).json()["id"]
    sheet = client.post(
        f"/api/v1/drawings/{drawing_id}/sheets",
        json={"expected_version": 0, "name": "Sheet 1", "size": "A3"},
        headers=_headers(),
    )
    assert sheet.status_code == 201, sheet.text
    sheet_id = sheet.json()["sheet"]["id"]
    view = client.post(
        f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/views",
        json={
            "expected_version": 1,
            "ref_document_id": part_id,
            "ref_document_kind": "part",
            "projection": "front",
            "position": {"x_mm": 50.0, "y_mm": 50.0},
        },
        headers=_headers(),
    )
    assert view.status_code == 201, view.text
    view_id = view.json()["view"]["id"]

    response = client.post(
        f"/api/v1/drawings/{drawing_id}/duplicate", headers=_headers()
    )
    assert response.status_code == 201, response.text
    copy_id = response.json()["id"]
    assert response.json()["name"] == "bracket-detail copy"

    layout = client.get(f"/api/v1/drawings/{copy_id}", headers=_headers()).json()
    sheets = layout["sheets"]
    assert [s["sheet"]["name"] for s in sheets] == ["Sheet 1"]
    assert sheets[0]["sheet"]["size"] == "A3"
    assert sheets[0]["sheet"]["id"] != sheet_id
    views = sheets[0]["views"]
    assert [v["projection"] for v in views] == ["front"]
    assert views[0]["id"] != view_id
    # The view still projects the SAME part — a view is a reference.
    assert views[0]["ref_document_id"] == part_id

    # ...which makes the part undeletable while either drawing exists.
    refused = client.delete(f"/api/v1/parts/{part_id}", headers=_headers())
    assert refused.status_code == 409
    dependents = refused.json()["error"]["details"]["dependents"]
    assert sorted(d["name"] for d in dependents) == [
        "bracket-detail",
        "bracket-detail copy",
    ]
    assert {d["kind"] for d in dependents} == {"drawing"}


def test_duplicate_drawing_with_no_sheets_is_an_empty_copy(
    client: TestClient,
) -> None:
    drawing_id = client.post(
        "/api/v1/drawings", json={"name": "blank"}, headers=_headers()
    ).json()["id"]
    response = client.post(
        f"/api/v1/drawings/{drawing_id}/duplicate", headers=_headers()
    )
    assert response.status_code == 201, response.text
    layout = client.get(
        f"/api/v1/drawings/{response.json()['id']}", headers=_headers()
    ).json()
    assert layout["sheets"] == []
