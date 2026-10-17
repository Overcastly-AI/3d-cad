"""The shipped ``loft.wall`` plugin through documents (STUD-WALL).

B2's four walls as four Wall custom features in an inch part, with the
server's own registry: 48 member bodies whose materials (PT bottom plates,
SPF studs and top plates) ride the evaluation request; a parameter drives the
stud spacing, 16 -> 24 in, regenerating 26 studs with the kept ids; and an
input past its bound is a typed refusal.
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

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000e2"}
IN = 25.4

#: B2's walls, clockwise: start x, start y (in), direction (deg), length (in).
B2_WALLS = [
    (144.0, 0.0, 180.0, 144.0),
    (0.0, 3.5, 90.0, 113.0),
    (0.0, 120.0, 0.0, 144.0),
    (144.0, 116.5, 270.0, 113.0),
]


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _wall(
    x: float, y: float, direction: float, length: float, **extra: Any
) -> dict[str, Any]:
    feature: dict[str, Any] = {
        "type": "custom",
        "version": 1,
        "params": {
            "plugin_id": "loft.wall",
            "plugin_version": "1.0.0",
            "inputs": {
                "start_x_mm": x * IN,
                "start_y_mm": y * IN,
                "direction_deg": direction,
                "length_mm": length * IN,
                "stud_spacing_mm": 16 * IN,
            },
        },
    }
    feature.update(extra)
    return feature


def _part(client: TestClient) -> tuple[str, int]:
    response = client.post(
        "/api/v1/parts",
        json={"name": f"B2 walls {uuid.uuid4()}", "length_unit": "in"},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"]), int(response.json()["tree_version"])


def _add(client: TestClient, part_id: str, version: int, feature: Any) -> int:
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": "Wall", "feature": feature, "expected_tree_version": version},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return int(response.json()["tree_version"])


def _request(client: TestClient, part_id: str) -> EvaluateTreeRequest:
    response = client.get(
        f"/api/v1/parts/{part_id}/evaluation-request", headers=HEADERS
    )
    assert response.status_code == 200, response.text
    return EvaluateTreeRequest.model_validate_json(response.content)


def _bodies(request: EvaluateTreeRequest) -> list[uuid.UUID]:
    return [e.id for e in request.features if e.feature.type == "extrude"]


def test_b2s_walls_carry_their_member_materials(client: TestClient) -> None:
    part_id, version = _part(client)
    for wall in B2_WALLS:
        version = _add(client, part_id, version, _wall(*wall))
    request = _request(client, part_id)
    bodies = _bodies(request)
    assert len(bodies) == 48  # 36 studs, 8 top plates, 4 bottom plates
    assert request.materials is not None
    assert request.materials.default_material is None
    assigned = Counter(e.material for e in request.materials.bodies)
    assert assigned == {"spf_lumber": 44, "southern_pine_pt": 4}


def test_a_parameter_drives_the_spacing_and_ids_hold(client: TestClient) -> None:
    part_id, version = _part(client)
    response = client.put(
        f"/api/v1/parts/{part_id}/parameters",
        json={
            "expected_tree_version": version,
            "parameters": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "stud_oc",
                    "expression": "16 in",
                    "unit": "length",
                }
            ],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    version = response.json()["tree_version"]
    for wall in B2_WALLS:
        feature = _wall(*wall, expressions={"/inputs/stud_spacing_mm": "stud_oc"})
        version = _add(client, part_id, version, feature)
    before = _request(client, part_id)
    assert len(_bodies(before)) == 48

    rows = client.get(f"/api/v1/parts/{part_id}/parameters", headers=HEADERS).json()
    row = {k: v for k, v in rows["parameters"][0].items() if k != "value"}
    response = client.put(
        f"/api/v1/parts/{part_id}/parameters",
        json={
            "expected_tree_version": before.tree_version,
            "parameters": [{**row, "expression": "24 in"}],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    after = _request(client, part_id)
    assert len(_bodies(after)) == 38  # 26 studs and the 12 plates
    assert set(_bodies(after)) < set(_bodies(before))  # every kept id kept


def test_an_input_past_its_bound_is_a_typed_refusal(client: TestClient) -> None:
    part_id, version = _part(client)
    feature = _wall(*B2_WALLS[0])
    feature["params"]["inputs"]["stud_spacing_mm"] = 48 * IN
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": "Wall", "feature": feature, "expected_tree_version": version},
        headers=HEADERS,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "plugin_input_invalid"
