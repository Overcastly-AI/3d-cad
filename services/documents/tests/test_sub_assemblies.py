"""Nested sub-assemblies, documents side (ASM-A3 step 1).

A wheel (two parts) is inserted twice into a bike next to a frame part:

- the evaluation request nests to any depth, each sub-assembly built once;
- inserting an assembly into itself, directly or through a chain, is refused
  with a message naming the chain;
- the BOM reads top level 2 lines / 3 instances, indented with per-parent and
  all-levels quantities, and parts only 3 lines / 5 parts;
- a joint may attach to a part inside a sub-assembly by its occurrence id, but
  not to two parts of one rigid sub-assembly, nor by geometry to the
  sub-assembly itself; it survives a re-read, is removed with its sub-assembly
  instance, and follows the copy when the assembly is duplicated.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.assemblies import (
    EvaluateAssemblyRequest,
    nested_occurrence_id,
    occurrence_id,
)
from loft_wire.parts import PRINCIPAL_HEADER

OWNER = "6f3f6b64-0000-4000-8000-0000000000a3"
HEADERS = {PRINCIPAL_HEADER: OWNER}


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=any_db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _post(client: TestClient, path: str, body: dict[str, Any]) -> Any:
    response = client.post(path, json=body, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()


def _version(client: TestClient, assembly: str) -> int:
    body = client.get(f"/api/v1/assemblies/{assembly}", headers=HEADERS).json()
    return int(body["doc_version"])


def _insert(client: TestClient, assembly: str, ref: str, kind: str, name: str) -> Any:
    return client.post(
        f"/api/v1/assemblies/{assembly}/instances",
        json={
            "expected_version": _version(client, assembly),
            "ref_document_id": ref,
            "ref_document_kind": kind,
            "name": name,
        },
        headers=HEADERS,
    )


def _instance(client: TestClient, assembly: str, ref: str, kind: str, name: str) -> str:
    response = _insert(client, assembly, ref, kind, name)
    assert response.status_code == 201, response.text
    return str(response.json()["instance"]["id"])


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


def _joint(a: str, b: str) -> dict[str, Any]:
    return {"type": "joint", "motion": "rigid", "a": _origin(a), "b": _origin(b)}


def _add_mate(client: TestClient, assembly: str, mate: dict[str, Any]) -> Any:
    return client.post(
        f"/api/v1/assemblies/{assembly}/mates",
        json={"expected_version": _version(client, assembly), "mate": mate},
        headers=HEADERS,
    )


class Bike:
    def __init__(self, client: TestClient) -> None:
        self.rim = _post(client, "/api/v1/parts", {"name": "Rim"})["id"]
        self.hub = _post(client, "/api/v1/parts", {"name": "Hub"})["id"]
        self.frame = _post(client, "/api/v1/parts", {"name": "Frame"})["id"]
        self.wheel = _post(client, "/api/v1/assemblies", {"name": "Wheel"})["id"]
        self.rim_in_wheel = _instance(client, self.wheel, self.rim, "part", "Rim <1>")
        self.hub_in_wheel = _instance(client, self.wheel, self.hub, "part", "Hub <1>")
        self.bike = _post(client, "/api/v1/assemblies", {"name": "Bike"})["id"]
        self.front = _instance(client, self.bike, self.wheel, "assembly", "Wheel <1>")
        self.rear = _instance(client, self.bike, self.wheel, "assembly", "Wheel <2>")
        self.frame_in_bike = _instance(
            client, self.bike, self.frame, "part", "Frame <1>"
        )

    def occurrence(self, sub: str, part: str) -> str:
        return str(nested_occurrence_id(uuid.UUID(sub), uuid.UUID(part)))


def test_evaluation_request_nests_every_level(client: TestClient) -> None:
    bike = Bike(client)
    # A third level: the bike inside a rack.
    rack = _post(client, "/api/v1/assemblies", {"name": "Rack"})["id"]
    on_rack = _instance(client, rack, bike.bike, "assembly", "Bike <1>")
    body = client.get(f"/api/v1/assemblies/{rack}/evaluation-request", headers=HEADERS)
    assert body.status_code == 200, body.text
    request = EvaluateAssemblyRequest.model_validate(body.json())
    (bike_instance,) = request.instances
    assert str(bike_instance.instance_id) == on_rack
    assert bike_instance.sub_assembly is not None
    front, rear, frame = bike_instance.sub_assembly.instances
    assert frame.sub_assembly is None
    for wheel in (front, rear):
        assert wheel.sub_assembly is not None
        assert [str(i.instance_id) for i in wheel.sub_assembly.instances] == [
            bike.rim_in_wheel,
            bike.hub_in_wheel,
        ]
    # Built once, shared: both wheel instances carry the same request.
    assert front.sub_assembly == rear.sub_assembly


def test_inserting_an_assembly_into_itself_is_refused(client: TestClient) -> None:
    bike = Bike(client)
    direct = _insert(client, bike.wheel, bike.wheel, "assembly", "Self <1>")
    assert direct.status_code == 422
    assert direct.json()["error"]["code"] == "assembly_cycle"
    assert direct.json()["error"]["message"] == (
        "An assembly cannot be inserted into itself."
    )
    chain = _insert(client, bike.wheel, bike.bike, "assembly", "Bike <1>")
    assert chain.status_code == 422
    error = chain.json()["error"]
    assert error["code"] == "assembly_cycle"
    assert error["message"] == (
        "Bike already contains Wheel, so inserting it here would make the "
        "assembly contain itself."
    )


def test_bom_top_level_indented_and_parts_only(client: TestClient) -> None:
    bike = Bike(client)
    body = client.get(f"/api/v1/assemblies/{bike.bike}/bom", headers=HEADERS).json()
    assert [(line["name"], line["quantity"]) for line in body["lines"]] == [
        ("Frame", 1),
        ("Wheel", 2),
    ]
    assert body["total_instances"] == 3
    assert [
        (row["item"], row["level"], row["name"], row["quantity"], row["total_quantity"])
        for row in body["indented"]
    ] == [
        ("1", 0, "Frame", 1, 1),
        ("2", 0, "Wheel", 2, 2),
        ("2.1", 1, "Hub", 1, 2),
        ("2.2", 1, "Rim", 1, 2),
    ]
    assert [(line["name"], line["quantity"]) for line in body["parts_only"]] == [
        ("Frame", 1),
        ("Hub", 2),
        ("Rim", 2),
    ]
    assert body["total_parts"] == 5
    assert all(line["ref_document_kind"] == "part" for line in body["parts_only"])


def test_a_joint_to_a_nested_part_is_stored_and_reread(client: TestClient) -> None:
    bike = Bike(client)
    rim = bike.occurrence(bike.front, bike.rim_in_wheel)
    response = _add_mate(client, bike.bike, _joint(bike.frame_in_bike, rim))
    assert response.status_code == 201, response.text
    graph = client.get(f"/api/v1/assemblies/{bike.bike}", headers=HEADERS).json()
    (mate,) = graph["mates"]
    assert mate["mate"]["b"]["instance_id"] == rim
    # The same id geometry derives from the instance path.
    assert rim == str(
        occurrence_id([uuid.UUID(bike.front), uuid.UUID(bike.rim_in_wheel)])
    )


def test_a_joint_inside_one_rigid_sub_assembly_is_refused(client: TestClient) -> None:
    bike = Bike(client)
    rim = bike.occurrence(bike.front, bike.rim_in_wheel)
    hub = bike.occurrence(bike.front, bike.hub_in_wheel)
    response = _add_mate(client, bike.bike, _joint(rim, hub))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mate_within_sub_assembly"
    # Across two wheel instances is fine: they move independently.
    other = bike.occurrence(bike.rear, bike.hub_in_wheel)
    assert _add_mate(client, bike.bike, _joint(rim, other)).status_code == 201


def test_a_joint_needs_a_part_not_the_sub_assembly(client: TestClient) -> None:
    bike = Bike(client)
    response = _add_mate(client, bike.bike, _joint(bike.frame_in_bike, bike.front))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mate_needs_part"
    lock = {
        "type": "lock",
        "a_instance_id": bike.frame_in_bike,
        "b_instance_id": bike.front,
    }
    assert _add_mate(client, bike.bike, lock).status_code == 201


def test_an_unknown_occurrence_is_refused(client: TestClient) -> None:
    bike = Bike(client)
    stray = str(nested_occurrence_id(uuid.UUID(bike.front), uuid.uuid4()))
    response = _add_mate(client, bike.bike, _joint(bike.frame_in_bike, stray))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mate_instance_unknown"


def test_deleting_the_sub_assembly_instance_removes_joints_to_its_parts(
    client: TestClient,
) -> None:
    bike = Bike(client)
    rim = bike.occurrence(bike.front, bike.rim_in_wheel)
    assert (
        _add_mate(client, bike.bike, _joint(bike.frame_in_bike, rim)).status_code == 201
    )
    response = client.delete(
        f"/api/v1/assemblies/{bike.bike}/instances/{bike.front}",
        params={"expected_version": _version(client, bike.bike)},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["mates"] == []


def test_duplicating_moves_joints_to_nested_parts_with_the_copy(
    client: TestClient,
) -> None:
    bike = Bike(client)
    rim = bike.occurrence(bike.front, bike.rim_in_wheel)
    assert (
        _add_mate(client, bike.bike, _joint(bike.frame_in_bike, rim)).status_code == 201
    )
    copy = _post(client, f"/api/v1/assemblies/{bike.bike}/duplicate", {})["id"]
    graph = client.get(f"/api/v1/assemblies/{copy}", headers=HEADERS).json()
    front_copy = graph["instances"][0]["id"]
    (mate,) = graph["mates"]
    assert mate["mate"]["b"]["instance_id"] == bike.occurrence(
        front_copy, bike.rim_in_wheel
    )
    assert mate["mate"]["a"]["instance_id"] == graph["instances"][2]["id"]
