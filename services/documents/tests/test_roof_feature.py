"""The shipped ``loft.roof`` plugin through documents (ROOF).

One Roof custom feature in an inch part, with the server's own registry: B2's
gable expands to 14 rafters and a ridge, each weighed by its member material
(spruce-pine-fir) with no part material; the pitch edit 6/12 -> 8/12
regenerates every member under the same ids (B2's named edit); and a ridge
shallower than the rafters' plumb cut is a typed refusal.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.features import EvaluateTreeRequest
from loft_wire.parts import PRINCIPAL_HEADER

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000f1"}


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _roof(**inputs: Any) -> dict[str, Any]:
    return {
        "type": "custom",
        "version": 1,
        "params": {
            "plugin_id": "loft.roof",
            "plugin_version": "1.0.0",
            "inputs": inputs,
        },
    }


def _part(client: TestClient) -> tuple[str, int]:
    response = client.post(
        "/api/v1/parts",
        json={"name": f"B2 roof {uuid.uuid4()}", "length_unit": "in"},
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


def test_the_pitch_edit_regenerates_every_member_under_its_id(
    client: TestClient,
) -> None:
    part_id, version = _part(client)
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": "Roof", "feature": _roof(), "expected_tree_version": version},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    feature_id = response.json()["feature"]["id"]
    stored = response.json()["feature"]["feature"]["params"]["inputs"]
    assert stored["pitch"] == "rise_6"
    before = _request(client, part_id)
    bodies = _bodies(before)
    assert len(bodies) == 15  # 14 rafters and the ridge
    assert before.materials is not None
    assert before.materials.default_material is None
    assigned = {e.base_feature_id: e.material for e in before.materials.bodies}
    assert assigned == dict.fromkeys(bodies, "spf_lumber")

    response = client.patch(
        f"/api/v1/parts/{part_id}/features/{feature_id}",
        json={
            "expected_tree_version": before.tree_version,
            "feature": _roof(pitch="rise_8"),
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    after = _request(client, part_id)
    assert _bodies(after) == bodies
    changed = {
        e.id
        for e, f in zip(before.features, after.features, strict=True)
        if e.feature != f.feature
    }
    # Only the side profiles (and the ridge's section) move with the pitch.
    sketches = {e.id for e in after.features if e.feature.type == "sketch"}
    assert len(sketches) == 15
    assert changed == sketches


def test_a_shallow_ridge_is_a_typed_refusal(client: TestClient) -> None:
    part_id, version = _part(client)
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": "Roof",
            "feature": _roof(ridge_profile="us_2x6"),
            "expected_tree_version": version,
        },
        headers=HEADERS,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "plugin_input_unsupported"
