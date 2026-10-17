"""The shipped ``loft.deck`` plugin through documents (DECK).

One Deck custom feature in an inch part, with the server's own registry (no
fixture): its members' materials ride the evaluation request as per-body
assignments, so the part has a mass with no part material (the CUT-LIST note:
the Material panel said "No material"); the user's own body override still
wins; and a parameter drives the width, 16 -> 20 ft, regenerating the members
with stable ids.
"""

import uuid
from collections import Counter
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.features import EvaluateTreeRequest
from loft_wire.parts import PRINCIPAL_HEADER

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000d7"}
IN = 25.4


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _deck(**extra: Any) -> dict[str, Any]:
    feature: dict[str, Any] = {
        "type": "custom",
        "version": 1,
        "params": {
            "plugin_id": "loft.deck",
            "plugin_version": "1.0.0",
            "inputs": {"width_mm": 192 * IN, "depth_mm": 144 * IN},
        },
    }
    feature.update(extra)
    return feature


def _part(client: TestClient) -> tuple[str, int]:
    response = client.post(
        "/api/v1/parts",
        json={"name": f"B1 deck {uuid.uuid4()}", "length_unit": "in"},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"]), int(response.json()["tree_version"])


def _request(client: TestClient, part_id: str) -> EvaluateTreeRequest:
    response = client.get(
        f"/api/v1/parts/{part_id}/evaluation-request", headers=HEADERS
    )
    assert response.status_code == 200, response.text
    return EvaluateTreeRequest.model_validate_json(response.content)


def _bodies(request: EvaluateTreeRequest) -> list[uuid.UUID]:
    return [e.id for e in request.features if e.feature.type == "extrude"]


def test_member_materials_ride_the_evaluation_request(client: TestClient) -> None:
    part_id, version = _part(client)
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": "Deck", "feature": _deck(), "expected_tree_version": version},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    request = _request(client, part_id)
    bodies = _bodies(request)
    assert len(bodies) == 46
    assert request.materials is not None
    assert request.materials.default_material is None
    assigned = {e.base_feature_id: e.material for e in request.materials.bodies}
    assert assigned == dict.fromkeys(bodies, "southern_pine_pt")

    # The user's own override on one joist wins; a part default changes no
    # member (each has its own material); the stored assignment is the user's.
    joist = bodies[4]
    tree_version = request.tree_version
    response = client.patch(
        f"/api/v1/parts/{part_id}",
        json={
            "expected_tree_version": tree_version,
            "materials": {
                "default_material": "spf_lumber",
                "bodies": [{"base_feature_id": str(joist), "material": "lvl"}],
            },
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    request = _request(client, part_id)
    assert request.materials is not None
    assert request.materials.default_material == "spf_lumber"
    assigned = {e.base_feature_id: e.material for e in request.materials.bodies}
    assert assigned[joist] == "lvl"
    assert Counter(assigned.values()) == {"southern_pine_pt": 45, "lvl": 1}
    stored = client.get(f"/api/v1/parts/{part_id}", headers=HEADERS).json()
    assert len(stored["materials"]["bodies"]) == 1

    # The cut list reads the same materials geometry weighs.
    cut = client.get(f"/api/v1/parts/{part_id}/cut-list-request", headers=HEADERS)
    assert cut.status_code == 200, cut.text
    assert cut.json()["evaluation"] == request.model_dump(mode="json")


def test_a_parameter_drives_the_width_and_ids_hold(client: TestClient) -> None:
    part_id, version = _part(client)
    response = client.put(
        f"/api/v1/parts/{part_id}/parameters",
        json={
            "expected_tree_version": version,
            "parameters": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "deck_width",
                    "expression": "16 ft",
                    "unit": "length",
                }
            ],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    version = response.json()["tree_version"]
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": "Deck",
            "feature": _deck(expressions={"/inputs/width_mm": "deck_width"}),
            "expected_tree_version": version,
        },
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    before = _request(client, part_id)
    assert len(_bodies(before)) == 46

    rows = client.get(f"/api/v1/parts/{part_id}/parameters", headers=HEADERS).json()
    row = {k: v for k, v in rows["parameters"][0].items() if k != "value"}
    response = client.put(
        f"/api/v1/parts/{part_id}/parameters",
        json={
            "expected_tree_version": before.tree_version,
            "parameters": [{**row, "expression": "20 ft"}],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    after = _request(client, part_id)
    assert len(_bodies(after)) == 50  # 16 joists and 4 posts
    assert set(_bodies(before)) < set(_bodies(after))  # every old id kept
    assert after.materials is not None and len(after.materials.bodies) == 50


def test_an_unsupported_combination_is_a_typed_refusal(client: TestClient) -> None:
    part_id, version = _part(client)
    feature = _deck()
    feature["params"]["inputs"]["joist_direction"] = "along"
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": "Deck", "feature": feature, "expected_tree_version": version},
        headers=HEADERS,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "plugin_input_unsupported"
