"""The shipped ``loft.floor`` plugin through documents (FLOOR-FRAME).

B5's floor as one Floor custom feature in an inch part, with the server's own
registry: 16 member bodies whose materials (PT sills, SPF joists and rims)
ride the evaluation request; a parameter drives the joist spacing 16 -> 12 in
(13 joists) and the width 144 -> 192 in, every kept member keeping its id;
and an input past its bound is a typed refusal.
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

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000f5"}
IN = 25.4


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _floor(**extra: Any) -> dict[str, Any]:
    feature: dict[str, Any] = {
        "type": "custom",
        "version": 1,
        "params": {
            "plugin_id": "loft.floor",
            "plugin_version": "1.0.0",
            "inputs": {
                "width_mm": 144 * IN,
                "depth_mm": 120 * IN,
                "joist_spacing_mm": 16 * IN,
            },
        },
    }
    feature.update(extra)
    return feature


def _part(client: TestClient) -> tuple[str, int]:
    response = client.post(
        "/api/v1/parts",
        json={"name": f"B5 floor {uuid.uuid4()}", "length_unit": "in"},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"]), int(response.json()["tree_version"])


def _add(client: TestClient, part_id: str, version: int, feature: Any) -> int:
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": "Floor", "feature": feature, "expected_tree_version": version},
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


def _set_parameters(
    client: TestClient, part_id: str, version: int, parameters: list[dict[str, Any]]
) -> int:
    response = client.put(
        f"/api/v1/parts/{part_id}/parameters",
        json={"expected_tree_version": version, "parameters": parameters},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    return int(response.json()["tree_version"])


def test_b5s_floor_carries_its_member_materials(client: TestClient) -> None:
    part_id, version = _part(client)
    _add(client, part_id, version, _floor())
    request = _request(client, part_id)
    assert len(_bodies(request)) == 16  # 10 joists, 2 rims, 4 sills
    assert request.materials is not None
    assert request.materials.default_material is None
    assigned = Counter(e.material for e in request.materials.bodies)
    assert assigned == {"spf_lumber": 12, "southern_pine_pt": 4}


def test_parameters_drive_spacing_and_width_and_ids_hold(client: TestClient) -> None:
    part_id, version = _part(client)
    oc, width = str(uuid.uuid4()), str(uuid.uuid4())

    def parameters(oc_expr: str, width_expr: str) -> list[dict[str, Any]]:
        return [
            {"id": oc, "name": "joist_oc", "expression": oc_expr, "unit": "length"},
            {"id": width, "name": "w", "expression": width_expr, "unit": "length"},
        ]

    version = _set_parameters(client, part_id, version, parameters("16 in", "144 in"))
    feature = _floor(
        expressions={"/inputs/joist_spacing_mm": "joist_oc", "/inputs/width_mm": "w"}
    )
    version = _add(client, part_id, version, feature)
    before = _request(client, part_id)
    assert len(_bodies(before)) == 16

    # The spec's edit: spacing 16 -> 12 gives 13 joists.
    version = _set_parameters(client, part_id, version, parameters("12 in", "144 in"))
    twelve = _request(client, part_id)
    assert len(_bodies(twelve)) == 19
    assert set(_bodies(before)) < set(_bodies(twelve))

    # Widening adds joists after the ones it had: every id is kept.
    _set_parameters(client, part_id, version, parameters("16 in", "192 in"))
    wide = _request(client, part_id)
    assert len(_bodies(wide)) == 19  # 13 joists at 16 o.c. on 192
    assert set(_bodies(before)) < set(_bodies(wide))


def test_an_input_past_its_bound_is_a_typed_refusal(client: TestClient) -> None:
    part_id, version = _part(client)
    feature = _floor()
    feature["params"]["inputs"]["joist_spacing_mm"] = 48 * IN
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": "Floor", "feature": feature, "expected_tree_version": version},
        headers=HEADERS,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "plugin_input_invalid"
