"""documents joint mates: create through POST /mates, edit through PATCH.

A joint's persisted truth is its value, so PATCH edits the mate row in place:
same id, same order, a ``doc_version`` bump and exactly one undo step (undo
and redo restore the row verbatim). A value outside the joint's limits is a
422 ``joint_value_out_of_limits`` whose message names the joint and the limit,
on create as on PATCH; a joint may only name instances of its own assembly;
another owner's assembly is a uniform 404.

Runs against SQLite (always) and the real migrated scratch PostgreSQL (see
conftest.py). Helpers are self-contained: test modules cannot import each
other under ``--import-mode=importlib``.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.parts import PRINCIPAL_HEADER

OWNER = "6f3f6b64-0000-4000-8000-00000000000a"
STRANGER = "6f3f6b64-0000-4000-8000-00000000000b"


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=any_db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


def _post(client: TestClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=body, headers=_headers())
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _assembly_with_two_instances(
    client: TestClient, name: str = "hinge"
) -> tuple[str, str, str]:
    part = _post(client, "/api/v1/parts", {"name": f"{name}-leaf"})["id"]
    assembly = _post(client, "/api/v1/assemblies", {"name": name})["id"]
    instances: list[str] = []
    for index in range(2):
        body = _post(
            client,
            f"/api/v1/assemblies/{assembly}/instances",
            {
                "expected_version": index,
                "ref_document_id": part,
                "ref_document_kind": "part",
                "name": f"Leaf <{index + 1}>",
                "grounded": index == 0,
            },
        )
        instances.append(body["instance"]["id"])
    return assembly, instances[0], instances[1]


def _origin(instance_id: str) -> dict[str, Any]:
    return {
        "instance_id": instance_id,
        "kind": "circle_centre",
        "signature": {
            "curve": "circle",
            "end_a": {"x": 5.0, "y": 0.0, "z": 0.0},
            "end_b": {"x": 5.0, "y": 0.0, "z": 0.0},
            "midpoint": {"x": -5.0, "y": 0.0, "z": 0.0},
            "length_mm": 31.415926,
        },
    }


def _revolute(a: str, b: str, rot_deg: float = 30.0) -> dict[str, Any]:
    return {
        "type": "joint",
        "motion": "revolute",
        "a": _origin(a),
        "b": _origin(b),
        "limits": {"rot_min_deg": -90.0, "rot_max_deg": 180.0},
        "value": {"rot_deg": rot_deg},
    }


def _add_mate(
    client: TestClient, assembly: str, mate: dict[str, Any], version: int
) -> tuple[str, int]:
    body = _post(
        client,
        f"/api/v1/assemblies/{assembly}/mates",
        {"expected_version": version, "mate": mate},
    )
    return body["mate"]["id"], body["doc_version"]


def _patch(
    client: TestClient,
    assembly: str,
    mate_id: str,
    body: dict[str, Any],
    owner: str = OWNER,
) -> Any:
    return client.patch(
        f"/api/v1/assemblies/{assembly}/mates/{mate_id}",
        json=body,
        headers=_headers(owner),
    )


def _graph(client: TestClient, assembly: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/assemblies/{assembly}", headers=_headers())
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _history(client: TestClient, assembly: str, op: str, version: int) -> Any:
    response = client.post(
        f"/api/v1/assemblies/{assembly}/{op}",
        json={"expected_version": version},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_create_patch_undo_redo_a_joint(client: TestClient) -> None:
    assembly, a, b = _assembly_with_two_instances(client)
    mate_id, version = _add_mate(client, assembly, _revolute(a, b), 2)
    created = _graph(client, assembly)["mates"]
    assert [row["id"] for row in created] == [mate_id]
    assert created[0]["mate"]["value"] == {"rot_deg": 30.0, "lin_mm": None}

    response = _patch(
        client,
        assembly,
        mate_id,
        {"expected_version": version, "value": {"rot_deg": 120.0}, "flip": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["doc_version"] == version + 1
    assert body["mate"]["id"] == mate_id
    assert body["mate"]["order_index"] == 0
    assert body["mate"]["mate"]["value"]["rot_deg"] == 120.0
    assert body["mate"]["mate"]["b"]["flip"] is True
    assert body["mate"]["mate"]["limits"] == created[0]["mate"]["limits"]
    patched = _graph(client, assembly)
    assert patched["mates"] == [body["mate"]]
    assert patched["can_undo"] is True

    undone = _history(client, assembly, "undo", version + 1)
    assert undone["doc_version"] == version + 2
    assert undone["mates"] == created  # verbatim: same id, value and params
    redone = _history(client, assembly, "redo", version + 2)
    assert redone["mates"] == patched["mates"]


def test_value_out_of_limits_is_refused_naming_the_limit(client: TestClient) -> None:
    assembly, a, b = _assembly_with_two_instances(client)
    _, version = _add_mate(client, assembly, _revolute(a, b), 2)
    second, version = _add_mate(client, assembly, _revolute(a, b), version)

    response = _patch(
        client,
        assembly,
        second,
        {"expected_version": version, "value": {"rot_deg": 200.0}},
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "joint_value_out_of_limits"
    assert error["message"] == "Revolute 2: 200° exceeds max 180°"
    assert error["details"]["joint"] == "Revolute 2"
    assert _graph(client, assembly)["doc_version"] == version  # nothing written

    tightened = _patch(
        client,
        assembly,
        second,
        {"expected_version": version, "limits": {"rot_min_deg": 45.0}},
    )
    assert tightened.status_code == 422
    assert tightened.json()["error"]["message"] == "Revolute 2: 30° is below min 45°"

    on_create = client.post(
        f"/api/v1/assemblies/{assembly}/mates",
        json={"expected_version": version, "mate": _revolute(a, b, rot_deg=-100.0)},
        headers=_headers(),
    )
    assert on_create.status_code == 422
    error = on_create.json()["error"]
    assert error["code"] == "joint_value_out_of_limits"
    assert error["message"] == "Revolute 3: -100° is below min -90°"


def test_explicit_null_limits_removes_them(client: TestClient) -> None:
    assembly, a, b = _assembly_with_two_instances(client)
    mate_id, version = _add_mate(client, assembly, _revolute(a, b), 2)
    response = _patch(
        client,
        assembly,
        mate_id,
        {"expected_version": version, "limits": None, "value": {"rot_deg": 200.0}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["mate"]["mate"]["limits"] is None


def test_joint_naming_a_foreign_instance_is_refused(client: TestClient) -> None:
    assembly, a, _ = _assembly_with_two_instances(client, "hinge-a")
    _, _, foreign = _assembly_with_two_instances(client, "hinge-b")
    response = client.post(
        f"/api/v1/assemblies/{assembly}/mates",
        json={"expected_version": 2, "mate": _revolute(a, foreign)},
        headers=_headers(),
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "mate_instance_unknown"
    assert error["details"] == {"instance_id": foreign}


def test_another_owners_assembly_is_404(client: TestClient) -> None:
    assembly, a, b = _assembly_with_two_instances(client)
    mate_id, version = _add_mate(client, assembly, _revolute(a, b), 2)
    response = _patch(
        client,
        assembly,
        mate_id,
        {"expected_version": version, "value": {"rot_deg": 1.0}},
        owner=STRANGER,
    )
    assert response.status_code == 404
    unknown = _patch(
        client,
        assembly,
        "6f3f6b64-0000-4000-8000-0000000000ff",
        {"expected_version": version, "value": {"rot_deg": 1.0}},
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "mate_not_found"


@pytest.mark.parametrize(
    ("body", "stale", "code"),
    [
        ({}, False, "empty_mate_update"),
        ({"value": {"lin_mm": 3.0}}, False, "invalid_joint_update"),
        ({"value": {"rot_deg": 1.0}}, True, "stale_assembly_version"),
    ],
)
def test_bad_patches_are_422(
    client: TestClient, body: dict[str, Any], stale: bool, code: str
) -> None:
    assembly, a, b = _assembly_with_two_instances(client)
    mate_id, version = _add_mate(client, assembly, _revolute(a, b), 2)
    expected = version - 1 if stale else version
    response = _patch(client, assembly, mate_id, {"expected_version": expected, **body})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == code
    assert _graph(client, assembly)["doc_version"] == version


def test_legacy_mate_is_not_patchable(client: TestClient) -> None:
    assembly, a, b = _assembly_with_two_instances(client)
    lock = {"type": "lock", "a_instance_id": a, "b_instance_id": b}
    mate_id, version = _add_mate(client, assembly, lock, 2)
    response = _patch(
        client, assembly, mate_id, {"expected_version": version, "offset_mm": 1.0}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mate_not_joint"


def test_evaluation_request_carries_the_joint(client: TestClient) -> None:
    assembly, a, b = _assembly_with_two_instances(client)
    mate_id, _ = _add_mate(client, assembly, _revolute(a, b), 2)
    response = client.get(
        f"/api/v1/assemblies/{assembly}/evaluation-request", headers=_headers()
    )
    assert response.status_code == 200, response.text
    [mate] = response.json()["mates"]
    assert mate["mate_id"] == mate_id
    assert mate["mate"]["type"] == "joint"
