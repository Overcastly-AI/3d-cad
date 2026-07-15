"""documents assemblies — CRUD, acyclicity, OCC, auth, 409-with-dependents.

Runs the SAME application code against SQLite (always) and a real scratch
PostgreSQL with the actual migrations applied (0001+0002+0003) — see conftest.py
for the dialect split. Exercises docs/design/assemblies.md §1: the instance +
mate CRUD round-trip, write-time acyclicity (self + transitive cycle),
optimistic concurrency (stale ``expected_version`` → 422), owner-scoped auth
(non-owner → uniform 404), and the cross-document 409-with-dependents on
deleting a still-instanced part / sub-assembly.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from py_kit.schemas.parts import PRINCIPAL_HEADER

OWNER = "6f3f6b64-0000-4000-8000-00000000000a"
OTHER = "6f3f6b64-0000-4000-8000-00000000000b"


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=any_db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


def _error(body: dict[str, Any]) -> dict[str, Any]:
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    return error


def _create_part(client: TestClient, name: str, owner: str = OWNER) -> str:
    response = client.post(
        "/api/v1/parts", json={"name": name}, headers=_headers(owner)
    )
    assert response.status_code == 201, response.text
    part_id: str = response.json()["id"]
    return part_id


def _create_assembly(client: TestClient, name: str, owner: str = OWNER) -> str:
    response = client.post(
        "/api/v1/assemblies", json={"name": name}, headers=_headers(owner)
    )
    assert response.status_code == 201, response.text
    assembly_id: str = response.json()["id"]
    return assembly_id


def _add_instance(
    client: TestClient,
    assembly_id: str,
    ref_document_id: str,
    expected_version: int,
    *,
    ref_document_kind: str = "part",
    name: str = "Part <1>",
    grounded: bool = False,
    placement: dict[str, Any] | None = None,
    owner: str = OWNER,
) -> Any:
    payload: dict[str, Any] = {
        "expected_version": expected_version,
        "ref_document_id": ref_document_id,
        "ref_document_kind": ref_document_kind,
        "name": name,
        "grounded": grounded,
    }
    if placement is not None:
        payload["placement"] = placement
    return client.post(
        f"/api/v1/assemblies/{assembly_id}/instances",
        json=payload,
        headers=_headers(owner),
    )


# --- CRUD round-trip --------------------------------------------------------------


def test_assembly_crud_round_trip(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "gearbox")
    part_a = _create_part(client, "plate-a")
    part_b = _create_part(client, "plate-b")

    r1 = _add_instance(client, assembly_id, part_a, 0, name="Plate <1>", grounded=True)
    assert r1.status_code == 201, r1.text
    assert r1.json()["doc_version"] == 1
    instance_a = r1.json()["instance"]["id"]

    r2 = _add_instance(
        client,
        assembly_id,
        part_b,
        1,
        name="Plate <2>",
        placement={
            "position": {"x": 10.0, "y": 0.0, "z": 5.0},
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        },
    )
    assert r2.status_code == 201, r2.text
    instance_b = r2.json()["instance"]["id"]

    rm = client.post(
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
    assert rm.status_code == 201, rm.text
    assert rm.json()["doc_version"] == 3

    graph = client.get(f"/api/v1/assemblies/{assembly_id}", headers=_headers()).json()
    assert graph["doc_version"] == 3
    assert graph["assembly"]["name"] == "gearbox"
    assert graph["assembly"]["owner_id"] == OWNER

    instances = graph["instances"]
    assert [i["order_index"] for i in instances] == [0, 1]
    assert instances[0]["ref_document_id"] == part_a
    assert instances[0]["grounded"] is True
    assert instances[0]["ref_pinned_version"] is None
    assert instances[0]["placement"]["orientation"] == {
        "x": 0.0,
        "y": 0.0,
        "z": 0.0,
        "w": 1.0,
    }
    assert instances[1]["ref_document_id"] == part_b
    assert instances[1]["placement"]["position"] == {"x": 10.0, "y": 0.0, "z": 5.0}

    mates = graph["mates"]
    assert len(mates) == 1
    assert mates[0]["mate"]["type"] == "lock"
    assert mates[0]["mate"]["a_instance_id"] == instance_a
    assert mates[0]["mate"]["b_instance_id"] == instance_b


def test_list_assemblies_owner_scoped(client: TestClient) -> None:
    _create_assembly(client, "mine-1")
    _create_assembly(client, "mine-2")
    _create_assembly(client, "theirs", owner=OTHER)

    body = client.get("/api/v1/assemblies", headers=_headers()).json()
    assert [a["name"] for a in body["assemblies"]] == ["mine-1", "mine-2"]


def test_duplicate_assembly_name_is_409(client: TestClient) -> None:
    _create_assembly(client, "dup")
    response = client.post(
        "/api/v1/assemblies", json={"name": "dup"}, headers=_headers()
    )
    assert response.status_code == 409
    assert _error(response.json())["code"] == "assembly_name_taken"


# --- acyclicity -------------------------------------------------------------------


def test_direct_self_reference_is_rejected(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "self")
    response = _add_instance(
        client, assembly_id, assembly_id, 0, ref_document_kind="assembly"
    )
    assert response.status_code == 422
    assert _error(response.json())["code"] == "assembly_cycle"


def test_transitive_cycle_is_rejected(client: TestClient) -> None:
    a = _create_assembly(client, "outer")
    b = _create_assembly(client, "inner")
    # A instances B as a sub-assembly (A -> B).
    r1 = _add_instance(client, a, b, 0, ref_document_kind="assembly", name="B in A")
    assert r1.status_code == 201, r1.text
    # B instancing A (B -> A) would close the cycle A -> B -> A.
    r2 = _add_instance(client, b, a, 0, ref_document_kind="assembly", name="A in B")
    assert r2.status_code == 422
    assert _error(r2.json())["code"] == "assembly_cycle"


def test_reference_to_missing_document_is_422(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "dangle")
    missing = "6f3f6b64-0000-4000-8000-0000000000ff"
    response = _add_instance(client, assembly_id, missing, 0)
    assert response.status_code == 422
    assert _error(response.json())["code"] == "ref_document_not_found"


def test_cannot_instance_another_owners_part(client: TestClient) -> None:
    #: Owner-scoped references (§1.2): a foreign part is treated as missing.
    assembly_id = _create_assembly(client, "borrow")
    foreign_part = _create_part(client, "foreign", owner=OTHER)
    response = _add_instance(client, assembly_id, foreign_part, 0)
    assert response.status_code == 422
    assert _error(response.json())["code"] == "ref_document_not_found"


# --- optimistic concurrency -------------------------------------------------------


def test_stale_expected_version_is_422(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "occ")
    part = _create_part(client, "occ-part")
    _add_instance(client, assembly_id, part, 0)  # bumps to doc_version 1
    # Re-using the stale version 0 must be rejected.
    stale = _add_instance(client, assembly_id, part, 0, name="again")
    assert stale.status_code == 422
    assert _error(stale.json())["code"] == "stale_assembly_version"


# --- auth -------------------------------------------------------------------------


def test_non_owner_gets_uniform_404(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "private")
    response = client.get(f"/api/v1/assemblies/{assembly_id}", headers=_headers(OTHER))
    assert response.status_code == 404
    assert _error(response.json())["code"] == "assembly_not_found"


def test_missing_principal_is_401(client: TestClient) -> None:
    response = client.get("/api/v1/assemblies")
    assert response.status_code == 401


# --- 409-with-dependents ----------------------------------------------------------


def test_delete_instanced_part_is_409(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "uses-part")
    part = _create_part(client, "shared-part")
    _add_instance(client, assembly_id, part, 0)

    response = client.delete(f"/api/v1/parts/{part}", headers=_headers())
    assert response.status_code == 409
    error = _error(response.json())
    assert error["code"] == "part_has_dependents"
    assert error["details"]["dependents"][0]["name"] == "uses-part"


def test_delete_instanced_sub_assembly_is_409(client: TestClient) -> None:
    parent = _create_assembly(client, "parent")
    child = _create_assembly(client, "child")
    _add_instance(client, parent, child, 0, ref_document_kind="assembly", name="child")

    response = client.delete(f"/api/v1/assemblies/{child}", headers=_headers())
    assert response.status_code == 409
    assert _error(response.json())["code"] == "assembly_has_dependents"


def test_delete_unreferenced_part_still_succeeds(client: TestClient) -> None:
    part = _create_part(client, "lonely")
    response = client.delete(f"/api/v1/parts/{part}", headers=_headers())
    assert response.status_code == 204


# --- instance / mate mutation -----------------------------------------------------


def test_update_instance_replaces_placement(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "move")
    part = _create_part(client, "movable")
    r = _add_instance(client, assembly_id, part, 0)
    instance_id = r.json()["instance"]["id"]

    response = client.patch(
        f"/api/v1/assemblies/{assembly_id}/instances/{instance_id}",
        json={
            "expected_version": 1,
            "placement": {
                "position": {"x": 3.0, "y": 4.0, "z": 0.0},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            },
            "grounded": True,
        },
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    instance = response.json()["instance"]
    assert instance["placement"]["position"] == {"x": 3.0, "y": 4.0, "z": 0.0}
    assert instance["grounded"] is True


def test_reorder_instances(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "reorder")
    p1 = _create_part(client, "r1")
    p2 = _create_part(client, "r2")
    p3 = _create_part(client, "r3")
    i1 = _add_instance(client, assembly_id, p1, 0, name="first").json()["instance"][
        "id"
    ]
    _add_instance(client, assembly_id, p2, 1, name="second")
    _add_instance(client, assembly_id, p3, 2, name="third")

    # Move the first instance to the end (order_index 2).
    response = client.patch(
        f"/api/v1/assemblies/{assembly_id}/instances/{i1}",
        json={"expected_version": 3, "order_index": 2},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    assert _graph_names(client, assembly_id) == ["second", "third", "first"]


def _graph_names(client: TestClient, assembly_id: str) -> list[str]:
    graph = client.get(f"/api/v1/assemblies/{assembly_id}", headers=_headers()).json()
    return [i["name"] for i in graph["instances"]]


def test_mate_rejects_unknown_instance(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "badmate")
    part = _create_part(client, "bm")
    i1 = _add_instance(client, assembly_id, part, 0).json()["instance"]["id"]
    stranger = "6f3f6b64-0000-4000-8000-0000000000ee"

    response = client.post(
        f"/api/v1/assemblies/{assembly_id}/mates",
        json={
            "expected_version": 1,
            "mate": {"type": "lock", "a_instance_id": i1, "b_instance_id": stranger},
        },
        headers=_headers(),
    )
    assert response.status_code == 422
    assert _error(response.json())["code"] == "mate_instance_unknown"


def test_delete_instance_cascades_dependent_mate(client: TestClient) -> None:
    assembly_id = _create_assembly(client, "cascade")
    p1 = _create_part(client, "c1")
    p2 = _create_part(client, "c2")
    i1 = _add_instance(client, assembly_id, p1, 0).json()["instance"]["id"]
    i2 = _add_instance(client, assembly_id, p2, 1, name="c2").json()["instance"]["id"]
    client.post(
        f"/api/v1/assemblies/{assembly_id}/mates",
        json={
            "expected_version": 2,
            "mate": {"type": "lock", "a_instance_id": i1, "b_instance_id": i2},
        },
        headers=_headers(),
    )

    response = client.delete(
        f"/api/v1/assemblies/{assembly_id}/instances/{i1}?expected_version=3",
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    graph = response.json()
    assert len(graph["instances"]) == 1
    assert graph["mates"] == []  # the lock mate went with its endpoint
