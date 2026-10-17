"""Doors and windows hosted in walls, through documents (WINDOW-DOOR).

B2's four walls with its door and window as six custom features in an inch
part, with the server's own registry. A write to an opening re-expands its
host wall (stored, and in the evaluation request): adding, moving,
suppressing, deleting the door and a parameter that drives its offset each
reframe the front wall; an undo restores it. A host that is missing, later,
or not a wall is refused, and so is an opening the wall cannot frame.
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

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000d2"}
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


def _custom(plugin_id: str, inputs: dict[str, Any], **extra: Any) -> dict[str, Any]:
    feature: dict[str, Any] = {
        "type": "custom",
        "version": 1,
        "params": {"plugin_id": plugin_id, "plugin_version": "1.0.0", "inputs": inputs},
    }
    feature.update(extra)
    return feature


def _wall(x: float, y: float, direction: float, length: float) -> dict[str, Any]:
    return _custom(
        "loft.wall",
        {
            "start_x_mm": x * IN,
            "start_y_mm": y * IN,
            "direction_deg": direction,
            "length_mm": length * IN,
        },
    )


def _opening(kind: str, host: str, offset: float, **extra: Any) -> dict[str, Any]:
    inputs: dict[str, Any] = {
        "host_wall": {"kind": "feature", "feature_id": host},
        "offset_mm": offset * IN,
    }
    inputs.update(extra.pop("inputs", {}))
    return _custom(f"loft.{kind}", inputs, **extra)


class Part:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        response = client.post(
            "/api/v1/parts",
            json={"name": f"B2 {uuid.uuid4()}", "length_unit": "in"},
            headers=HEADERS,
        )
        assert response.status_code == 201, response.text
        self.id = str(response.json()["id"])
        self.version = int(response.json()["tree_version"])

    def _track(self, response: Any) -> Any:
        if response.status_code in (200, 201):
            self.version = int(response.json()["tree_version"])
        return response

    def add(self, feature: dict[str, Any], name: str) -> Any:
        return self._track(
            self.client.post(
                f"/api/v1/parts/{self.id}/features",
                json={
                    "name": name,
                    "feature": feature,
                    "expected_tree_version": self.version,
                },
                headers=HEADERS,
            )
        )

    def added(self, feature: dict[str, Any], name: str) -> str:
        response = self.add(feature, name)
        assert response.status_code == 201, response.text
        return str(response.json()["feature"]["id"])

    def patch(self, feature_id: str, feature: dict[str, Any]) -> Any:
        return self._track(
            self.client.patch(
                f"/api/v1/parts/{self.id}/features/{feature_id}",
                json={"feature": feature, "expected_tree_version": self.version},
                headers=HEADERS,
            )
        )

    def suppress(self, feature_id: str, suppressed: bool) -> None:
        response = self._track(
            self.client.patch(
                f"/api/v1/parts/{self.id}/features/{feature_id}/suppress",
                json={"suppressed": suppressed, "expected_tree_version": self.version},
                headers=HEADERS,
            )
        )
        assert response.status_code == 200, response.text

    def delete(self, feature_id: str) -> Any:
        return self._track(
            self.client.delete(
                f"/api/v1/parts/{self.id}/features/{feature_id}",
                params={"expected_tree_version": self.version},
                headers=HEADERS,
            )
        )

    def undo(self) -> None:
        response = self._track(
            self.client.post(
                f"/api/v1/parts/{self.id}/undo",
                json={"expected_tree_version": self.version},
                headers=HEADERS,
            )
        )
        assert response.status_code == 200, response.text

    def stored_roles(self, feature_id: str) -> Counter[str]:
        """The roles of a feature's STORED expansion."""
        response = self.client.get(
            f"/api/v1/parts/{self.id}/features/{feature_id}", headers=HEADERS
        )
        assert response.status_code == 200, response.text
        params: dict[str, Any] = response.json()["feature"]["params"]
        expansion: list[dict[str, Any]] = params["expansion"] or []
        return Counter(
            str(m["role"]) for m in expansion if m["feature"]["type"] == "extrude"
        )

    def request(self) -> EvaluateTreeRequest:
        response = self.client.get(
            f"/api/v1/parts/{self.id}/evaluation-request", headers=HEADERS
        )
        assert response.status_code == 200, response.text
        return EvaluateTreeRequest.model_validate_json(response.content)

    def bodies(self) -> int:
        return sum(1 for e in self.request().features if e.feature.type == "extrude")


def _b2(client: TestClient) -> tuple[Part, list[str]]:
    part = Part(client)
    walls = [part.added(_wall(*w), f"Wall {i + 1}") for i, w in enumerate(B2_WALLS)]
    return part, walls


DOOR_FRAMED = {
    "stud": 8,
    "king": 2,
    "jack": 2,
    "header": 2,
    "cripple": 2,
    "top_plate": 2,
    "bottom_plate": 2,
}
PLAIN_144 = {"stud": 10, "top_plate": 2, "bottom_plate": 1}


def test_b2s_door_and_window_frame_their_walls(client: TestClient) -> None:
    part, walls = _b2(client)
    assert part.bodies() == 48
    door = part.added(_opening("door", walls[0], 72), "Door 1")
    part.added(_opening("window", walls[3], 56.5), "Window 1")
    # The openings expand to nothing; their walls hold the framing.
    assert part.stored_roles(door) == {}
    assert part.stored_roles(walls[0]) == DOOR_FRAMED
    assert part.stored_roles(walls[3]) == {
        "stud": 6,
        "king": 2,
        "jack": 2,
        "header": 2,
        "cripple": 2,
        "sill": 1,
        "sill_cripple": 2,
        "top_plate": 2,
        "bottom_plate": 1,
    }
    assert part.bodies() == 64  # buildings.md's wall cut list
    request = part.request()
    assert request.materials is not None
    assert Counter(e.material for e in request.materials.bodies) == {
        "spf_lumber": 59,
        "southern_pine_pt": 5,
    }


def test_every_write_to_the_door_reframes_its_wall(client: TestClient) -> None:
    part, walls = _b2(client)
    door = part.added(_opening("door", walls[0], 72), "Door 1")
    # Moved 24 in: 7 layout studs and 3 top cripples.
    moved = part.patch(door, _opening("door", walls[0], 48))
    assert moved.status_code == 200, moved.text
    assert part.stored_roles(walls[0])["stud"] == 7
    assert part.stored_roles(walls[0])["cripple"] == 3
    # Suppressed: no effect, as any suppressed feature; then back.
    part.suppress(door, True)
    assert part.stored_roles(walls[0]) == PLAIN_144
    assert part.bodies() == 48
    part.suppress(door, False)
    assert part.stored_roles(walls[0])["cripple"] == 3
    # Re-hosted in the back wall: both walls reframe.
    rehosted = part.patch(door, _opening("door", walls[2], 72))
    assert rehosted.status_code == 200, rehosted.text
    assert part.stored_roles(walls[0]) == PLAIN_144
    assert part.stored_roles(walls[2]) == DOOR_FRAMED
    # Deleted: 10 full studs and one 144 bottom plate; undo brings it back.
    assert part.delete(door).status_code == 200
    assert part.stored_roles(walls[2]) == PLAIN_144
    assert part.bodies() == 48
    part.undo()
    assert part.stored_roles(walls[2]) == DOOR_FRAMED


def test_a_parameter_drives_the_door_and_its_wall_follows(client: TestClient) -> None:
    part, walls = _b2(client)
    response = client.put(
        f"/api/v1/parts/{part.id}/parameters",
        json={
            "expected_tree_version": part.version,
            "parameters": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "door_at",
                    "expression": "72 in",
                    "unit": "length",
                }
            ],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    part.version = response.json()["tree_version"]
    part.added(
        _opening("door", walls[0], 0, expressions={"/inputs/offset_mm": "door_at"}),
        "Door 1",
    )
    assert part.stored_roles(walls[0])["cripple"] == 2
    rows = client.get(f"/api/v1/parts/{part.id}/parameters", headers=HEADERS).json()
    row = {k: v for k, v in rows["parameters"][0].items() if k != "value"}
    response = client.put(
        f"/api/v1/parts/{part.id}/parameters",
        json={
            "expected_tree_version": part.version,
            "parameters": [{**row, "name": "door_x", "expression": "48 in"}],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    # The wall reads no parameter itself, yet re-frames for its door (stored
    # and evaluated), through the parameter's rename.
    assert part.stored_roles(walls[0])["cripple"] == 3
    # 48, less 3 studs, plus 2 kings, 2 jacks, 2 plies, 3 cripples, 1 plate.
    assert part.bodies() == 55


def test_hosts_that_are_missing_later_or_not_walls_are_refused(
    client: TestClient,
) -> None:
    part, walls = _b2(client)
    missing = part.add(_opening("door", str(uuid.uuid4()), 72), "Door")
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "reference_not_found"
    door = part.added(_opening("door", walls[0], 72), "Door 1")
    on_a_door = part.add(_opening("window", door, 72), "Window")
    assert on_a_door.status_code == 422, on_a_door.text
    assert on_a_door.json()["error"]["code"] == "plugin_input_invalid"
    assert "not a loft.wall" in on_a_door.json()["error"]["message"]
    # Hosting cannot run backwards: the door may not move before its wall,
    # and the wall may not be deleted under it.
    tree = client.get(f"/api/v1/parts/{part.id}/features", headers=HEADERS).json()
    order = [row["id"] for row in tree["features"]]
    reordered = client.put(
        f"/api/v1/parts/{part.id}/features/order",
        json={
            "order": [door, *[i for i in order if i != door]],
            "expected_tree_version": part.version,
        },
        headers=HEADERS,
    )
    assert reordered.status_code == 422
    assert reordered.json()["error"]["code"] == "reference_not_earlier"
    assert part.delete(walls[0]).status_code == 409


def test_an_opening_the_wall_cannot_frame_is_refused(client: TestClient) -> None:
    part, walls = _b2(client)
    door = part.added(_opening("door", walls[0], 72), "Door 1")
    version = part.version
    # Past the wall's end: refused on the door's own field.
    far = part.add(_opening("door", walls[0], 130), "Door 2")
    assert far.status_code == 422
    assert far.json()["error"]["details"]["input"] == "offset_mm"
    # Overlapping the first door: refused by the wall, naming both.
    over = part.add(_opening("window", walls[0], 100), "Window 1")
    assert over.status_code == 422
    message = over.json()["error"]["message"]
    assert "Window 1" in message and "Door 1" in message
    # A wall shortened under its door is refused too, and nothing changed.
    short = part.patch(walls[0], _wall(144.0, 0.0, 180.0, 80.0))
    assert short.status_code == 422, short.text
    assert "Door 1" in short.json()["error"]["message"]
    assert part.version == version
    assert part.stored_roles(walls[0]) == DOOR_FRAMED
    assert part.stored_roles(door) == {}
