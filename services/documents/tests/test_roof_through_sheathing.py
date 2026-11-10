"""ROOF-THROUGH-SHEATHING-UPDATE through documents: a stored roof whose tails
pass through wall sheathing carries a warning, and the fix is an opt-in,
undoable update of its pin.

B3's hip (``loft.roof`` 1.3.0) on B2's four walls (``loft.wall`` 1.2.0 with
7/16 OSB) shares 33.2551 in^3 with the OSB over 30 (member, panel) pairs:
22 tails x 1.22021484375 and 4 hip corners x 1.602597506 (the hand figures,
packages/loft-plugins/tests/test_roof_sheathing.py). The roof picks its
walls, so the warning offers the latest Roof, 1.7.0, which notches them
(a hip frames no ceiling joists or gable ends, so 1.7.0 builds it as 1.5.0).
Re-pinning is an
ordinary feature edit with the same inputs: the warning goes and Undo brings
the 1.3.0 roof, and its warning, back. Nothing is re-pinned on read. A roof on
its typed bearing picks no walls: it is warned with no update.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.parts import PRINCIPAL_HEADER

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000e7"}
IN = 25.4
NOTCHES = 33.25511658666087

#: B2's four walls, clockwise, framing in: start x, start y, direction, length.
B2_WALLS = [
    (144, 0, 180, 144),
    (0, 3.5, 90, 113),
    (0, 120, 0, 144),
    (144, 116.5, 270, 113),
]


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _custom(plugin_id: str, version: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "custom",
        "version": 1,
        "params": {"plugin_id": plugin_id, "plugin_version": version, "inputs": inputs},
    }


def _wall(x: float, y: float, direction: float, length: float) -> dict[str, Any]:
    return _custom(
        "loft.wall",
        "1.2.0",
        {
            "start_x_mm": x * IN,
            "start_y_mm": y * IN,
            "direction_deg": float(direction),
            "length_mm": length * IN,
            "sheathing": "osb_7_16",
        },
    )


class Part:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        response = client.post(
            "/api/v1/parts",
            json={"name": f"B3 on B2 {uuid.uuid4()}", "length_unit": "in"},
            headers=HEADERS,
        )
        assert response.status_code == 201, response.text
        self.id = str(response.json()["id"])
        self.version = int(response.json()["tree_version"])

    def added(self, feature: dict[str, Any], name: str) -> dict[str, Any]:
        response = self.client.post(
            f"/api/v1/parts/{self.id}/features",
            json={
                "name": name,
                "feature": feature,
                "expected_tree_version": self.version,
            },
            headers=HEADERS,
        )
        assert response.status_code == 201, response.text
        self.version = int(response.json()["tree_version"])
        return response.json()["feature"]

    def patch(self, feature_id: str, feature: dict[str, Any]) -> dict[str, Any]:
        response = self.client.patch(
            f"/api/v1/parts/{self.id}/features/{feature_id}",
            json={"feature": feature, "expected_tree_version": self.version},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        self.version = int(response.json()["tree_version"])
        return response.json()["feature"]

    def update(self, feature_id: str) -> dict[str, Any]:
        """The roof's declared update (``POST .../features/plugin-updates``),
        what the editor's "Update to" runs: its inputs carried by the map."""
        response = self.client.post(
            f"/api/v1/parts/{self.id}/features/plugin-updates",
            json={"expected_tree_version": self.version, "feature_ids": [feature_id]},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        self.version = int(response.json()["tree_version"])
        return next(f for f in response.json()["features"] if f["id"] == feature_id)

    def tree(self) -> dict[str, dict[str, Any]]:
        response = self.client.get(f"/api/v1/parts/{self.id}/features", headers=HEADERS)
        assert response.status_code == 200, response.text
        return {f["id"]: f for f in response.json()["features"]}

    def undo(self) -> None:
        response = self.client.post(
            f"/api/v1/parts/{self.id}/undo",
            json={"expected_tree_version": self.version},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        self.version = int(response.json()["tree_version"])


def _house(client: TestClient, roof: dict[str, Any]) -> tuple[Part, dict[str, Any]]:
    part = Part(client)
    walls = [part.added(_wall(*row), f"Wall {i + 1}") for i, row in enumerate(B2_WALLS)]
    picks = [{"kind": "feature", "feature_id": w["id"]} for w in walls]
    inputs = {k: (picks if v == "WALLS" else v) for k, v in roof.items()}
    return part, part.added(_custom("loft.roof", "1.3.0", inputs), "Roof")


def test_a_hip_on_sheathed_walls_warns_and_offers_the_update(
    client: TestClient,
) -> None:
    part, roof = _house(client, {"style": "hip", "walls": "WALLS"})
    # The write's own response and the tree say the same.
    for shown in (roof, part.tree()[roof["id"]]):
        (warning,) = shown["plugin_warnings"]
        assert warning["code"] == "roof_through_sheathing"
        assert warning["pairs"] == 30
        assert warning["overlap_in3"] == pytest.approx(NOTCHES, abs=1e-9)
        assert warning["update_to"] == "1.9.0"
        assert "33.2551 in³" in warning["message"]
        assert "Update to 1.9.0" in warning["message"]
        assert "says what else it adds" in warning["message"]
    # A hip frames no ceiling joists: its update adds none (PLUGIN-UPDATE-ALL).
    offer = part.tree()[roof["id"]]["plugin_update"]
    assert (offer["to_version"], offer["adds"], offer["quiet"]) == ("1.9.0", [], False)
    # Reading never re-pins.
    assert part.tree()[roof["id"]]["feature"]["params"]["plugin_version"] == "1.3.0"
    for wall in (f for f in part.tree().values() if f["id"] != roof["id"]):
        assert "plugin_warnings" not in wall

    updated = part.update(roof["id"])
    assert updated["feature"]["params"]["plugin_version"] == "1.9.0"
    # Ceiling joists takes its default; a hip frames none.
    inputs = updated["feature"]["params"]["inputs"]
    assert inputs["ceiling_joists"] == "beside_common"
    assert not any(
        m["role"] == "ceiling_joist" for m in updated["feature"]["params"]["expansion"]
    )
    assert "plugin_warnings" not in updated
    assert "plugin_warnings" not in part.tree()[roof["id"]]
    notches = [
        m
        for m in updated["feature"]["params"]["expansion"]
        if str(m.get("name", "")).startswith("tail/")
    ]
    assert len(notches) == 26

    part.undo()
    back = part.tree()[roof["id"]]
    assert back["feature"]["params"]["plugin_version"] == "1.3.0"
    assert back["plugin_warnings"][0]["update_to"] == "1.9.0"


def test_a_typed_roof_is_warned_with_no_update(client: TestClient) -> None:
    """B3 typed on B2's bearing (no walls picked) over the same walls."""
    part, roof = _house(client, {"style": "hip"})
    (warning,) = part.tree()[roof["id"]]["plugin_warnings"]
    assert warning["pairs"] == 30
    assert warning["overlap_in3"] == pytest.approx(NOTCHES, abs=1e-9)
    assert warning["update_to"] is None
    assert "typed bearing" in warning["message"]


def test_unsheathed_walls_raise_no_warning(client: TestClient) -> None:
    part = Part(client)
    for i, row in enumerate(B2_WALLS):
        wall = _wall(*row)
        wall["params"]["inputs"].pop("sheathing")
        part.added(wall, f"Wall {i + 1}")
    roof = part.added(_custom("loft.roof", "1.3.0", {"style": "hip"}), "Roof")
    assert "plugin_warnings" not in roof
