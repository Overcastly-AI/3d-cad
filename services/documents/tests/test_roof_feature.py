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


# --- 1.1.0: Style Hip (ROOF-HIP) ---------------------------------------------------


def _roof_1_1(**inputs: Any) -> dict[str, Any]:
    feature = _roof(**inputs)
    feature["params"]["plugin_version"] = "1.1.0"
    return feature


def _shapes(request: EvaluateTreeRequest) -> list[tuple[str, Any]]:
    """Each member's type and, for a sketch, its outline: the expansion
    with its ids (derived from the feature's own id) left out."""
    return [
        (
            e.feature.type,
            e.feature.params.model_dump(mode="json")["entities"]
            if e.feature.type == "sketch"
            else None,
        )
        for e in request.features
    ]


def test_a_hip_roof_is_b3s_members_and_the_edit_back_is_b2s_gable(
    client: TestClient,
) -> None:
    """B3: Style Hip gives 27 bodies (6 commons, 16 jacks, 4 hips, a ridge),
    each weighed as spruce-pine-fir; the jacks and hips are trimmed by
    cutters their booleans consume, so no cutter is left a body. The edit
    back to Gable is B2's roof exactly as a stored 1.0.0 roof expands."""
    part_id, version = _part(client)
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": "Roof",
            "feature": _roof_1_1(style="hip"),
            "expected_tree_version": version,
        },
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    feature_id = response.json()["feature"]["id"]
    stored = response.json()["feature"]["feature"]["params"]
    assert stored["inputs"]["style"] == "hip"
    assert stored["inputs"]["hip_profile"] == "us_2x8"
    roles = [m["role"] for m in stored["expansion"]]
    assert {r: roles.count(r) for r in ("common", "jack", "hip", "ridge")} == {
        "common": 6,
        "jack": 16,
        "hip": 4,
        "ridge": 1,
    }
    hip = _request(client, part_id)
    assert hip.materials is not None
    assigned = {e.base_feature_id: e.material for e in hip.materials.bodies}
    assert len(assigned) == 27 and set(assigned.values()) == {"spf_lumber"}
    assert sum(e.feature.type == "boolean" for e in hip.features) == 24

    response = client.patch(
        f"/api/v1/parts/{part_id}/features/{feature_id}",
        json={
            "expected_tree_version": hip.tree_version,
            "feature": _roof_1_1(style="gable"),
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    gable = _request(client, part_id)
    assert len(_bodies(gable)) == 15
    other, version = _part(client)
    response = client.post(
        f"/api/v1/parts/{other}/features",
        json={"name": "Roof", "feature": _roof(), "expected_tree_version": version},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    assert _shapes(gable) == _shapes(_request(client, other))


@pytest.mark.parametrize(
    ("inputs", "at"),
    [
        ({"style": "hip", "hip_profile": "us_2x6"}, "hip_profile"),
        ({"style": "hip", "overhang_mm": 2.54e-8}, "overhang_mm"),
        ({"style": "gable", "overhang_mm": 2.54e-8}, "overhang_mm"),
    ],
)
def test_a_shallow_hip_and_a_sliver_of_overhang_are_typed_refusals(
    client: TestClient, inputs: dict[str, Any], at: str
) -> None:
    part_id, version = _part(client)
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": "Roof",
            "feature": _roof_1_1(**inputs),
            "expected_tree_version": version,
        },
        headers=HEADERS,
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "plugin_input_unsupported"
    assert error["details"]["input"] == at
