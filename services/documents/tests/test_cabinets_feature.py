"""The shipped ``loft.cabinets`` plugin through documents (CASEWORK).

C1's B24 as one Cabinets feature in an inch part, with the server's own
registry: its 15 panel bodies with their materials ride the evaluation
request and its members, plugin and metadata (banding, hardware, grain) the
cut-list request; a part parameter drives one box's width through a formula
on its row (``/inputs/boxes/0/width_mm``), 24 -> 27 in keeping every
member's id; a row out of its sizes is a typed refusal naming the box.
"""

import uuid
from collections import Counter
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.cut_list import CutListPartRequest
from loft_wire.features import EvaluateTreeRequest
from loft_wire.parts import PRINCIPAL_HEADER

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000c1"}
IN = 25.4


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _cabinets(boxes: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    feature: dict[str, Any] = {
        "type": "custom",
        "version": 1,
        "params": {
            "plugin_id": "loft.cabinets",
            "plugin_version": "1.0.0",
            "inputs": {"boxes": boxes},
        },
    }
    feature.update(extra)
    return feature


def _part(client: TestClient) -> tuple[str, int]:
    response = client.post(
        "/api/v1/parts",
        json={"name": f"C1 {uuid.uuid4()}", "length_unit": "in"},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"]), int(response.json()["tree_version"])


def _post(client: TestClient, part_id: str, version: int, feature: Any) -> Any:
    return client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": "Cabinets", "feature": feature, "expected_tree_version": version},
        headers=HEADERS,
    )


def _request(client: TestClient, part_id: str) -> EvaluateTreeRequest:
    response = client.get(
        f"/api/v1/parts/{part_id}/evaluation-request", headers=HEADERS
    )
    assert response.status_code == 200, response.text
    return EvaluateTreeRequest.model_validate_json(response.content)


def _cut_request(client: TestClient, part_id: str) -> CutListPartRequest:
    response = client.get(f"/api/v1/parts/{part_id}/cut-list-request", headers=HEADERS)
    assert response.status_code == 200, response.text
    return CutListPartRequest.model_validate_json(response.content)


def _bodies(request: EvaluateTreeRequest) -> list[uuid.UUID]:
    return [e.id for e in request.features if e.feature.type == "extrude"]


def test_c1_carries_its_panels_banding_and_hardware(client: TestClient) -> None:
    part_id, version = _part(client)
    response = _post(
        client, part_id, version, _cabinets([{"type": "base", "width_mm": 24 * IN}])
    )
    assert response.status_code == 201, response.text
    # The stored row is canonical: every field, defaults filled in.
    tree = client.get(f"/api/v1/parts/{part_id}/features", headers=HEADERS).json()
    stored = tree["features"][0]["feature"]["params"]["inputs"]["boxes"]
    assert stored == [
        {
            "type": "base",
            "width_mm": 24 * IN,
            "height": "standard",
            "fronts": "standard",
            "doors": "auto",
            "drawers": 3,
            "drawer_height_mm": 6 * IN,
            "shelves": 1,
        }
    ]
    request = _request(client, part_id)
    assert len(_bodies(request)) == 15
    assert request.materials is not None
    assert Counter(e.material for e in request.materials.bodies) == {"plywood": 15}
    members = _cut_request(client, part_id).members
    assert {m.plugin_id for m in members} == {"loft.cabinets"}
    banding = sum(
        m.metadata.banding.length_mm for m in members if m.metadata.banding is not None
    )
    assert banding / IN == pytest.approx(282.4375)
    hardware = Counter(
        h.key
        for m in members
        for h in m.metadata.hardware or []
        for _ in range(h.quantity)
    )
    assert hardware == {"hinge": 2, "slide_22": 1}
    assert all(m.metadata.grain is not None for m in members)


def test_a_parameter_drives_a_row_and_ids_hold(client: TestClient) -> None:
    part_id, version = _part(client)
    width = str(uuid.uuid4())

    def parameters(expr: str) -> list[dict[str, Any]]:
        return [{"id": width, "name": "w", "expression": expr, "unit": "length"}]

    response = client.put(
        f"/api/v1/parts/{part_id}/parameters",
        json={"expected_tree_version": version, "parameters": parameters("24 in")},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    version = int(response.json()["tree_version"])
    feature = _cabinets(
        [{"type": "base", "width_mm": 24 * IN}],
        expressions={"/inputs/boxes/0/width_mm": "w"},
    )
    response = _post(client, part_id, version, feature)
    assert response.status_code == 201, response.text
    version = int(response.json()["tree_version"])
    before = _request(client, part_id)
    response = client.put(
        f"/api/v1/parts/{part_id}/parameters",
        json={"expected_tree_version": version, "parameters": parameters("27 in")},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    after = _request(client, part_id)
    assert _bodies(after) == _bodies(before)
    tree = client.get(f"/api/v1/parts/{part_id}/features", headers=HEADERS).json()
    row = tree["features"][0]["feature"]["params"]["inputs"]["boxes"][0]
    assert row["width_mm"] == pytest.approx(27 * IN)


def test_a_box_out_of_its_sizes_is_a_typed_refusal(client: TestClient) -> None:
    part_id, version = _part(client)
    response = _post(
        client,
        part_id,
        version,
        _cabinets(
            [
                {"type": "base", "width_mm": 24 * IN},
                {"type": "base", "width_mm": 25 * IN},
            ]
        ),
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "plugin_input_invalid"
    assert "Box 2" in error["message"]
    assert error["details"]["input"] == "boxes"
