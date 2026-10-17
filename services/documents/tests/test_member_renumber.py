"""WALL-MEMBER-RENUMBER through documents: a feature on a generated member
keeps that member through an edit, or the edit is refused.

The hole is what a multi-body user makes (Fusion's Combine > Cut): a 1 in
circle extruded as a new body and a Boolean subtract whose TARGET is the
member, by id. Under ``loft.wall`` / ``loft.deck`` 1.1.0 the member's id is
its place (``stud/slot/8``, ``joist/end``), so moving B2's door 24 in or
widening B1 16 -> 20 ft keeps the Boolean on its stud or end joist. Under
1.0.0 the same edits would hand the id to another member (the end stud at
143.25, the layout joist at 192); documents refuses them with 409
``feature_has_dependents`` naming the hole, as it refuses an edit that drops
a referenced member, whether the edit is to the wall, to its door, or to a
parameter. An edit that does not move the member (a taller wall) is fine.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.features import (
    BooleanFeature,
    DatumFeature,
    DatumOffsetParams,
    EvaluateTreeRequest,
)
from loft_wire.parts import PRINCIPAL_HEADER
from loft_wire.plugins import member_id

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000e3"}
IN = 25.4

#: B2's front wall: from (144, 0) along -X, 144 long, framing to +Y.
FRONT = {"start_x_mm": 144 * IN, "direction_deg": 180.0, "length_mm": 144 * IN}


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _custom(
    plugin_id: str, version: str, inputs: dict[str, Any], **extra: Any
) -> dict[str, Any]:
    feature: dict[str, Any] = {
        "type": "custom",
        "version": 1,
        "params": {"plugin_id": plugin_id, "plugin_version": version, "inputs": inputs},
    }
    feature.update(extra)
    return feature


def _door(wall: str, offset: float, **extra: Any) -> dict[str, Any]:
    inputs = {
        "host_wall": {"kind": "feature", "feature_id": wall},
        "offset_mm": offset * IN,
    }
    return _custom("loft.door", "1.0.0", inputs, **extra)


class Part:
    def __init__(self, client: TestClient, name: str) -> None:
        self.client = client
        response = client.post(
            "/api/v1/parts",
            json={"name": f"{name} {uuid.uuid4()}", "length_unit": "in"},
            headers=HEADERS,
        )
        assert response.status_code == 201, response.text
        self.id = str(response.json()["id"])
        self.version = int(response.json()["tree_version"])

    def _track(self, response: Any) -> Any:
        if response.status_code in (200, 201):
            self.version = int(response.json()["tree_version"])
        return response

    def added(self, feature: dict[str, Any], name: str) -> str:
        response = self._track(
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
        assert response.status_code == 201, response.text
        return str(response.json()["feature"]["id"])

    def feature(self, feature_id: str) -> dict[str, Any]:
        response = self.client.get(
            f"/api/v1/parts/{self.id}/features/{feature_id}", headers=HEADERS
        )
        assert response.status_code == 200, response.text
        return response.json()["feature"]

    def patch(self, feature_id: str, feature: dict[str, Any]) -> Any:
        return self._track(
            self.client.patch(
                f"/api/v1/parts/{self.id}/features/{feature_id}",
                json={"feature": feature, "expected_tree_version": self.version},
                headers=HEADERS,
            )
        )

    def delete(self, feature_id: str) -> Any:
        return self._track(
            self.client.delete(
                f"/api/v1/parts/{self.id}/features/{feature_id}",
                params={"expected_tree_version": self.version},
                headers=HEADERS,
            )
        )

    def parameters(self, parameters: list[dict[str, Any]]) -> Any:
        return self._track(
            self.client.put(
                f"/api/v1/parts/{self.id}/parameters",
                json={"expected_tree_version": self.version, "parameters": parameters},
                headers=HEADERS,
            )
        )

    def request(self) -> EvaluateTreeRequest:
        response = self.client.get(
            f"/api/v1/parts/{self.id}/evaluation-request", headers=HEADERS
        )
        assert response.status_code == 200, response.text
        return EvaluateTreeRequest.model_validate_json(response.content)

    def drill(
        self,
        target: uuid.UUID,
        plane: dict[str, Any],
        centre: tuple[float, float],
        through: float,
        **sketch_extra: Any,
    ) -> str:
        """A 1 in hole through *target*: a circle on *plane*, extruded
        symmetric *through* in as a new body, subtracted from the target.
        Returns the Boolean's id (the feature named "Hole")."""
        sketch = self.added(
            {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": plane,
                    "entities": [
                        {
                            "id": "c1",
                            "kind": "circle",
                            "center": {"x": centre[0] * IN, "y": centre[1] * IN},
                            "radius": 0.5 * IN,
                        }
                    ],
                    "constraints": [],
                },
                **sketch_extra,
            },
            "Hole sketch",
        )
        tool = self.added(
            {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": sketch},
                    "distance_mm": through * IN,
                    "operation": "add",
                    "merge": False,
                    "extent": "symmetric",
                },
            },
            "Hole tool",
        )
        return self.added(
            {
                "type": "boolean",
                "version": 1,
                "params": {
                    "operation": "subtract",
                    "target": {"kind": "feature", "feature_id": str(target)},
                    "tool": {"kind": "feature", "feature_id": tool},
                },
            },
            "Hole",
        )

    def target_of(self, boolean: str) -> uuid.UUID:
        return uuid.UUID(self.feature(boolean)["params"]["target"]["feature_id"])

    def members(self, feature_id: str) -> dict[uuid.UUID, dict[str, Any]]:
        params = self.feature(feature_id)["params"]
        return {uuid.UUID(m["id"]): m for m in params["expansion"]}


XZ = {"kind": "datum_plane", "plane": "XZ"}


def _refused_naming_the_hole(response: Any, hole: str) -> None:
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "feature_has_dependents"
    assert [d["id"] for d in error["details"]["dependents"]] == [hole]
    assert "'Hole'" in error["message"]


def _wall_with_door_and_hole(
    client: TestClient, version: str
) -> tuple[Part, str, str, str, uuid.UUID]:
    """B2's front wall at *version*, its door at 72, and a hole through the
    stud at 128 along the wall (world X 16, Z 48): stud/6 under 1.0.0,
    stud/slot/8 under 1.1.0."""
    part = Part(client, f"B2 front wall {version}")
    wall = part.added(_custom("loft.wall", version, FRONT), "Front wall")
    door = part.added(_door(wall, 72), "Door 1")
    stud = (
        member_id(uuid.UUID(wall), "stud", 6)
        if version == "1.0.0"
        else member_id(uuid.UUID(wall), "stud", 0, "slot/8")
    )
    assert stud in part.members(wall)
    hole = part.drill(stud, XZ, (16, 48), 7)
    return part, wall, door, hole, stud


def test_1_1_moving_the_door_keeps_the_hole_in_its_stud(client: TestClient) -> None:
    part, wall, door, hole, stud = _wall_with_door_and_hole(client, "1.1.0")
    before = part.members(wall)[stud]
    response = part.patch(door, _door(wall, 48))
    assert response.status_code == 200, response.text
    after = part.members(wall)
    assert part.target_of(hole) == stud
    assert after[stud]["name"] == "slot/8"
    # Same stud, same place: its section did not move.
    section = before["feature"]["params"]["profile"]["feature_id"]
    assert after[stud]["feature"] == before["feature"]
    assert uuid.UUID(section) in after
    request = part.request()
    cut = next(e.feature for e in request.features if e.feature.type == "boolean")
    assert isinstance(cut, BooleanFeature) and cut.params.target.feature_id == stud


def test_1_0_moving_the_door_is_refused_naming_the_hole(client: TestClient) -> None:
    part, wall, door, hole, _ = _wall_with_door_and_hole(client, "1.0.0")
    stored = part.members(wall)
    _refused_naming_the_hole(part.patch(door, _door(wall, 48)), hole)
    assert part.members(wall) == stored  # nothing written
    assert part.feature(door)["params"]["inputs"]["offset_mm"] == 72 * IN


def test_1_0_deleting_the_door_is_refused_naming_the_hole(client: TestClient) -> None:
    """With the door gone the layout studs return, and stud/6 would be the
    one at 96."""
    part, _, door, hole, _ = _wall_with_door_and_hole(client, "1.0.0")
    _refused_naming_the_hole(part.delete(door), hole)


def test_1_0_a_taller_wall_keeps_its_hole(client: TestClient) -> None:
    """Not every edit of a 1.0.0 wall is refused: a taller wall lengthens
    its studs in place, so stud/6 is still the stud at 128."""
    part, wall, _, hole, stud = _wall_with_door_and_hole(client, "1.0.0")
    taller = _custom("loft.wall", "1.0.0", {**FRONT, "height_mm": 109.125 * IN})
    response = part.patch(wall, taller)
    assert response.status_code == 200, response.text
    assert part.target_of(hole) == stud


def test_1_0_a_parameter_that_moves_the_door_is_refused(client: TestClient) -> None:
    part = Part(client, "B2 front wall, door on a parameter")
    response = part.parameters(
        [
            {
                "id": str(uuid.uuid4()),
                "name": "door_x",
                "expression": "72 in",
                "unit": "length",
            }
        ]
    )
    assert response.status_code == 200, response.text
    wall = part.added(_custom("loft.wall", "1.0.0", FRONT), "Front wall")
    part.added(_door(wall, 72, expressions={"/inputs/offset_mm": "door_x"}), "Door 1")
    hole = part.drill(member_id(uuid.UUID(wall), "stud", 6), XZ, (16, 48), 7)
    rows = client.get(f"/api/v1/parts/{part.id}/parameters", headers=HEADERS).json()
    row = {k: v for k, v in rows["parameters"][0].items() if k != "value"}
    _refused_naming_the_hole(part.parameters([{**row, "expression": "48 in"}]), hole)


# --- B1: the end joist, 16 -> 20 ft ------------------------------------------------


def _deck_with_hole(client: TestClient, version: str) -> tuple[Part, str, str, str]:
    """B1 at *version* with its width on the parameter ``deck_width`` and a
    hole through the end joist whose datum follows the width, as a user
    drives a sketch from the same parameter."""
    part = Part(client, f"B1 deck {version}")
    response = part.parameters(
        [
            {
                "id": str(uuid.uuid4()),
                "name": "deck_width",
                "expression": "16 ft",
                "unit": "length",
            }
        ]
    )
    assert response.status_code == 200, response.text
    deck = part.added(
        _custom(
            "loft.deck",
            version,
            {"width_mm": 192 * IN, "depth_mm": 144 * IN},
            expressions={"/inputs/width_mm": "deck_width"},
        ),
        "Deck",
    )
    end = (
        member_id(uuid.UUID(deck), "joist", 12)
        if version == "1.0.0"
        else member_id(uuid.UUID(deck), "joist", 0, "end")
    )
    datum = part.added(
        {
            "type": "datum",
            "version": 1,
            "params": {"kind": "offset", "base": "YZ", "offset_mm": 191.25 * IN},
            "expressions": {"/offset_mm": "deck_width - 0.75 in"},
        },
        "End joist plane",
    )
    hole = part.drill(end, {"kind": "feature", "feature_id": datum}, (72, 24.375), 3)
    rows = client.get(f"/api/v1/parts/{part.id}/parameters", headers=HEADERS).json()
    row = {k: v for k, v in rows["parameters"][0].items() if k != "value"}
    return part, deck, hole, row["id"]


def _widen(part: Part, row_id: str) -> Any:
    return part.parameters(
        [
            {
                "id": row_id,
                "name": "deck_width",
                "expression": "20 ft",
                "unit": "length",
            }
        ]
    )


def test_1_1_widening_the_deck_keeps_the_hole_on_the_end_joist(
    client: TestClient,
) -> None:
    part, deck, hole, row = _deck_with_hole(client, "1.1.0")
    end = part.target_of(hole)
    response = _widen(part, row)
    assert response.status_code == 200, response.text
    members = part.members(deck)
    assert members[end]["name"] == "end"
    assert part.target_of(hole) == end
    # The end joist moved to the new side (X 238.5..240), and so did the hole.
    section = members[
        uuid.UUID(members[end]["feature"]["params"]["profile"]["feature_id"])
    ]
    xs = {
        round(point["x"] / IN, 9)
        for line in section["feature"]["params"]["entities"]
        for point in (line["start"], line["end"])
    }
    assert xs == {238.5, 240.0}
    datum = next(
        e.feature
        for e in part.request().features
        if isinstance(e.feature, DatumFeature) and e.id not in members
    )
    assert isinstance(datum.params, DatumOffsetParams)
    assert datum.params.offset_mm == pytest.approx(239.25 * IN)


def test_1_0_widening_the_deck_is_refused_naming_the_hole(client: TestClient) -> None:
    part, deck, hole, row = _deck_with_hole(client, "1.0.0")
    stored = part.members(deck)
    _refused_naming_the_hole(_widen(part, row), hole)
    assert part.members(deck) == stored


def test_1_0_widening_the_deck_by_its_input_is_refused(client: TestClient) -> None:
    part, deck, hole, _ = _deck_with_hole(client, "1.0.0")
    wider = _custom("loft.deck", "1.0.0", {"width_mm": 240 * IN, "depth_mm": 144 * IN})
    _refused_naming_the_hole(part.patch(deck, wider), hole)


def test_a_copy_and_an_import_carry_the_hole_to_the_copied_stud(
    client: TestClient,
) -> None:
    """Duplicate and ``.loft`` import re-mint the wall's id; a named member's
    id follows it by name (``member_id_mapping``), so the copied Boolean
    names the copy's stud at slot 8."""
    part, _, _, _, _ = _wall_with_door_and_hole(client, "1.1.0")

    def follows(part_id: str) -> None:
        rows = client.get(f"/api/v1/parts/{part_id}/features", headers=HEADERS)
        features = rows.json()["features"]
        wall, cut = features[0], features[-1]
        stud = member_id(uuid.UUID(wall["id"]), "stud", 0, "slot/8")
        assert cut["feature"]["params"]["target"]["feature_id"] == str(stud)
        ids = {m["id"] for m in wall["feature"]["params"]["expansion"]}
        assert str(stud) in ids

    copy = client.post(f"/api/v1/parts/{part.id}/duplicate", headers=HEADERS)
    assert copy.status_code == 201, copy.text
    follows(str(copy.json()["id"]))
    tree = client.get(f"/api/v1/parts/{part.id}/loft-tree", headers=HEADERS).json()
    imported = client.post(
        "/api/v1/parts/import-loft",
        json={"document_id": part.id, "tree": tree},  # ids taken: re-minted
        headers=HEADERS,
    )
    assert imported.status_code == 201, imported.text
    follows(str(imported.json()["id"]))
