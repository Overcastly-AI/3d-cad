"""A wall 1.5.0 with an Exterior finish but no sheathing warns (SIDING-TRIM).

The finish goes over the exterior sheathing, so a bare-stud wall takes none.
A finish picked on such a wall is not dropped silently: the stored wall
carries ``wall_finish_no_sheathing``, which says to turn sheathing on, and
still builds (advice, never a refusal). A sheathed wall, a wall at the
default None, and a 1.4.0 wall (no finish input) carry no warning.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.parts import PRINCIPAL_HEADER

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000f5"}
IN = 25.4


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _wall(version: str, **inputs: Any) -> dict[str, Any]:
    return {
        "type": "custom",
        "version": 1,
        "params": {
            "plugin_id": "loft.wall",
            "plugin_version": version,
            "inputs": {
                "start_x_mm": 0.0,
                "start_y_mm": 0.0,
                "direction_deg": 0.0,
                "length_mm": 144 * IN,
                "stud_spacing_mm": 16 * IN,
                **inputs,
            },
        },
    }


def _row(client: TestClient, feature: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/parts",
        json={"name": f"Finish {uuid.uuid4()}", "length_unit": "in"},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    part_id = str(response.json()["id"])
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": "Wall",
            "feature": feature,
            "expected_tree_version": response.json()["tree_version"],
        },
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    response = client.get(f"/api/v1/parts/{part_id}/features", headers=HEADERS)
    assert response.status_code == 200, response.text
    (row,) = [f for f in response.json()["features"] if f["name"] == "Wall"]
    return row


def test_a_finish_with_no_sheathing_warns_and_builds(client: TestClient) -> None:
    row = _row(client, _wall("1.5.0", exterior_finish="fibre_cement_lap_8_25"))
    (warning,) = row["plugin_warnings"]
    assert warning["code"] == "wall_finish_no_sheathing"
    assert "no siding without sheathing; turn sheathing on" in warning["message"]
    assert "Lap" in warning["message"]
    assert warning["update_to"] is None
    assert (warning["overlap_in3"], warning["pairs"]) == (0.0, 0)
    roles = {m["role"] for m in row["feature"]["params"]["expansion"]}
    assert "stud" in roles and "siding" not in roles


@pytest.mark.parametrize(
    ("version", "inputs"),
    [
        ("1.5.0", {"sheathing": "osb_7_16", "exterior_finish": "vinyl_d4"}),
        ("1.5.0", {}),  # the default: None
        ("1.5.0", {"exterior_finish": "none"}),
        ("1.4.0", {}),
    ],
)
def test_no_warning_when_sided_or_unasked(
    client: TestClient, version: str, inputs: dict[str, Any]
) -> None:
    row = _row(client, _wall(version, **inputs))
    assert row.get("plugin_warnings") is None
