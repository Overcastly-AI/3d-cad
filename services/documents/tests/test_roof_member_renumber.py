"""ROOF-MEMBER-RENUMBER through documents: a feature on a roof's member keeps
that member through an edit, or the edit is refused.

The hole is a Boolean subtract whose TARGET is the member, by id (as in
test_member_renumber.py for walls). Under ``loft.roof`` 1.3.0 the id is the
member's place (``common/front/ridge/start``), so lengthening, re-pitching or
moving a picked wall keeps the Boolean on its rafter. Under 1.0.0 to 1.2.0
the same edits can hand the id to another member; documents refuses an edit
that moves a referenced member of a renumbered role with 409
``feature_has_dependents`` naming the hole, whether the edit is to the roof
or to a wall it picks. An edit that leaves the member where it is (a new
material) is fine. The check compares placements, so it also refuses a
pitch change on an old roof: its rafters' profiles change.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.parts import PRINCIPAL_HEADER
from loft_wire.plugins import member_id

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000e4"}
IN = 25.4
XZ = {"kind": "datum_plane", "plane": "XZ"}
HIP = {"style": "hip"}

#: B2's four walls (B3's bearing), clockwise, framing in: start x, start y,
#: direction, length (in).
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
        "1.1.0",
        {
            "start_x_mm": x * IN,
            "start_y_mm": y * IN,
            "direction_deg": float(direction),
            "length_mm": length * IN,
        },
    )


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

    def members(self, feature_id: str) -> dict[uuid.UUID, dict[str, Any]]:
        params = self.feature(feature_id)["params"]
        return {uuid.UUID(m["id"]): m for m in params["expansion"]}

    def drill(self, target: uuid.UUID) -> str:
        """A 1 in hole: a circle on XZ extruded symmetric 200 in as a new
        body, subtracted from *target*. Returns the Boolean's id ("Hole")."""
        sketch = self.added(
            {
                "type": "sketch",
                "version": 1,
                "params": {
                    "plane": XZ,
                    "entities": [
                        {
                            "id": "c1",
                            "kind": "circle",
                            "center": {"x": 60 * IN, "y": 108 * IN},
                            "radius": 0.5 * IN,
                        }
                    ],
                    "constraints": [],
                },
            },
            "Hole sketch",
        )
        tool = self.added(
            {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": sketch},
                    "distance_mm": 200 * IN,
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


def _refused_naming_the_hole(response: Any, hole: str, version: str) -> None:
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "feature_has_dependents"
    assert [d["id"] for d in error["details"]["dependents"]] == [hole]
    assert "'Hole'" in error["message"]
    assert f"loft.roof {version}" in error["message"]


def _roof(
    client: TestClient, version: str, inputs: dict[str, Any], role: str, key: Any
) -> tuple[Part, str, str, uuid.UUID]:
    """A Roof at *version* with a hole through member (role, key): an index
    under an ordinal pin, a name under 1.3.0."""
    part = Part(client, f"Roof {version}")
    roof = part.added(_custom("loft.roof", version, inputs), "Roof")
    target = (
        member_id(uuid.UUID(roof), role, 0, key)
        if isinstance(key, str)
        else member_id(uuid.UUID(roof), role, key)
    )
    assert target in part.members(roof)
    return part, roof, part.drill(target), target


def test_a_new_roof_is_inserted_at_1_3(client: TestClient) -> None:
    catalog = client.get("/api/v1/plugins", headers=HEADERS).json()["plugins"]
    latest = [p["version"] for p in catalog if p["id"] == "loft.roof" and p["latest"]]
    assert latest == ["1.3.0"]


def test_1_3_lengthening_keeps_the_hole_in_its_common(client: TestClient) -> None:
    part, roof, hole, target = _roof(
        client, "1.3.0", HIP, "common", "front/ridge/start"
    )
    before = part.members(roof)[target]
    response = part.patch(
        roof, _custom("loft.roof", "1.3.0", {**HIP, "length_mm": 168 * IN})
    )
    assert response.status_code == 200, response.text
    after = part.members(roof)
    assert part.target_of(hole) == target
    assert after[target]["name"] == "front/ridge/start"
    assert after[target]["feature"] == before["feature"]  # same section, same place


def test_1_3_a_pitch_change_keeps_the_hole_in_its_jack(client: TestClient) -> None:
    part, roof, hole, target = _roof(client, "1.3.0", HIP, "jack", "front/left/1")
    response = part.patch(
        roof, _custom("loft.roof", "1.3.0", {**HIP, "pitch": "rise_8"})
    )
    assert response.status_code == 200, response.text
    assert part.target_of(hole) == target
    assert part.members(roof)[target]["name"] == "front/left/1"


@pytest.mark.parametrize(
    ("version", "inputs", "role", "index", "edit"),
    [
        # 1.2.0's common/3 is the front ridge-end common at 144 and the left
        # king at 168.
        ("1.2.0", HIP, "common", 3, {**HIP, "length_mm": 168 * IN}),
        ("1.1.0", HIP, "common", 3, {**HIP, "length_mm": 168 * IN}),
        # The gable's rafter/12 is the front end rafter, then a layout one.
        ("1.0.0", {}, "rafter", 12, {"length_mm": 168 * IN}),
        # Conservative: a re-pitched jack is in the same place in plan, but
        # its profile changed, and an ordinal cannot tell that from a move.
        ("1.2.0", HIP, "jack", 0, {**HIP, "pitch": "rise_8"}),
    ],
)
def test_an_old_roof_edit_that_moves_a_referenced_member_is_refused(
    client: TestClient,
    version: str,
    inputs: dict[str, Any],
    role: str,
    index: int,
    edit: dict[str, Any],
) -> None:
    part, roof, hole, _ = _roof(client, version, inputs, role, index)
    stored = part.members(roof)
    response = part.patch(roof, _custom("loft.roof", version, edit))
    _refused_naming_the_hole(response, hole, version)
    assert part.members(roof) == stored  # nothing written


def test_an_old_roof_edit_that_keeps_the_member_is_allowed(client: TestClient) -> None:
    part, roof, hole, target = _roof(client, "1.2.0", HIP, "common", 3)
    response = part.patch(
        roof, _custom("loft.roof", "1.2.0", {**HIP, "rafter_material": "dfl_lumber"})
    )
    assert response.status_code == 200, response.text
    assert part.target_of(hole) == target


def _roof_on_walls(
    client: TestClient, version: str, role: str, key: Any
) -> tuple[Part, list[str], str, str, uuid.UUID]:
    part = Part(client, f"Roof on walls {version}")
    walls = [part.added(_wall(*row), f"Wall {i + 1}") for i, row in enumerate(B2_WALLS)]
    picks = [{"kind": "feature", "feature_id": w} for w in walls]
    roof = part.added(_custom("loft.roof", version, {**HIP, "walls": picks}), "Roof")
    target = (
        member_id(uuid.UUID(roof), role, 0, key)
        if isinstance(key, str)
        else member_id(uuid.UUID(roof), role, key)
    )
    assert target in part.members(roof)
    return part, walls, roof, part.drill(target), target


def test_1_2_moving_a_picked_wall_that_moves_the_member_is_refused(
    client: TestClient,
) -> None:
    """The right wall 2 in further out: B3's footprint is 146 long, so the
    right king common (1.2.0's common/5) moves 2 in. The edit is to the
    wall; the roof re-lays with it, so the wall's write is refused."""
    part, walls, roof, hole, _ = _roof_on_walls(client, "1.2.0", "common", 5)
    stored = part.members(roof)
    response = part.patch(walls[3], _wall(146, 116.5, 270, 113))
    _refused_naming_the_hole(response, hole, "1.2.0")
    assert part.members(roof) == stored


def test_1_3_moving_a_picked_wall_keeps_the_hole_and_stores_the_roof(
    client: TestClient,
) -> None:
    part, walls, roof, hole, target = _roof_on_walls(
        client, "1.3.0", "common", "right/king"
    )
    section = member_id(uuid.UUID(roof), "section", 0, "common/right/king")
    before = part.members(roof)
    response = part.patch(walls[3], _wall(146, 116.5, 270, 113))
    assert response.status_code == 200, response.text
    after = part.members(roof)
    assert part.target_of(hole) == target
    assert after[target]["name"] == "right/king"
    # The king's body names its section by place; the section moved with the
    # wall (stored on the roof at the wall's write).
    assert after[target]["feature"] == before[target]["feature"]
    assert after[section]["feature"] != before[section]["feature"]


def test_a_wall_edit_the_roof_cannot_frame_is_still_allowed(
    client: TestClient,
) -> None:
    """A wall drawn in steps passes through outlines no roof frames: the
    write is allowed and the roof keeps its stored members (it reports the
    error at rebuild, as before)."""
    part, walls, roof, _, _ = _roof_on_walls(client, "1.2.0", "common", 5)
    stored = part.members(roof)
    response = part.patch(walls[3], _wall(160, 116.5, 270, 113))
    assert response.status_code == 200, response.text
    assert part.members(roof) == stored
