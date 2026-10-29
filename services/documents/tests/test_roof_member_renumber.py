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


def test_a_new_roof_is_inserted_at_1_6(client: TestClient) -> None:
    """1.4.0 (BUILDING-OUTLINE) is 1.3.0 with Defines Slope on outline walls;
    without one it expands as 1.3.0, names and all. 1.5.0
    (ROOF-HIP-SHEATHING-NOTCH) notches the walls' sheathing round its tails;
    1.6.0 (CEILING-JOISTS) ties a gable on its walls with ceiling joists."""
    catalog = client.get("/api/v1/plugins", headers=HEADERS).json()["plugins"]
    latest = [p["version"] for p in catalog if p["id"] == "loft.roof" and p["latest"]]
    assert latest == ["1.6.0"]


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


# --- A parameter-table change that moves a picked wall --------------------------------


def _table(part: Part, rows: list[dict[str, Any]]) -> Any:
    return part._track(  # pyright: ignore[reportPrivateUsage]
        part.client.put(
            f"/api/v1/parts/{part.id}/parameters",
            json={"expected_tree_version": part.version, "parameters": rows},
            headers=HEADERS,
        )
    )


def _roof_on_a_driven_wall(
    client: TestClient, version: str, role: str, key: Any
) -> tuple[Part, dict[str, Any], str, str, uuid.UUID]:
    """B3 on B2's walls, the right wall's start X on the parameter
    ``right_x`` (144 in); a hole through member (role, key). The roof reads
    no parameter: only the wall it picks does."""
    part = Part(client, f"Roof on a driven wall {version}")
    row = {
        "id": str(uuid.uuid4()),
        "name": "right_x",
        "expression": "144 in",
        "unit": "length",
    }
    assert _table(part, [row]).status_code == 200
    walls = [part.added(_wall(*r), f"Wall {i + 1}") for i, r in enumerate(B2_WALLS[:3])]
    driven = {**_wall(*B2_WALLS[3]), "expressions": {"/inputs/start_x_mm": "right_x"}}
    walls.append(part.added(driven, "Wall 4"))
    picks = [{"kind": "feature", "feature_id": w} for w in walls]
    roof = part.added(_custom("loft.roof", version, {**HIP, "walls": picks}), "Roof")
    target = (
        member_id(uuid.UUID(roof), role, 0, key)
        if isinstance(key, str)
        else member_id(uuid.UUID(roof), role, key)
    )
    assert target in part.members(roof)
    return part, row, roof, part.drill(target), target


def test_1_2_a_table_change_that_moves_the_member_is_refused(
    client: TestClient,
) -> None:
    """``right_x`` 144 -> 146 in moves the right wall, so the roof that picks
    it re-lays and its right king common (1.2.0's common/5) moves 2 in: the
    table PUT is refused naming the hole, and nothing is stored."""
    part, row, roof, hole, _ = _roof_on_a_driven_wall(client, "1.2.0", "common", 5)
    stored = part.members(roof)
    _refused_naming_the_hole(
        _table(part, [{**row, "expression": "146 in"}]), hole, "1.2.0"
    )
    assert part.members(roof) == stored
    table = client.get(f"/api/v1/parts/{part.id}/parameters", headers=HEADERS).json()
    assert table["parameters"][0]["expression"] == "144 in"


def test_1_3_a_table_change_keeps_the_hole_and_stores_the_roof(
    client: TestClient,
) -> None:
    part, row, roof, hole, target = _roof_on_a_driven_wall(
        client, "1.3.0", "common", "right/king"
    )
    section = member_id(uuid.UUID(roof), "section", 0, "common/right/king")
    before = part.members(roof)
    response = _table(part, [{**row, "expression": "146 in"}])
    assert response.status_code == 200, response.text
    after = part.members(roof)
    assert part.target_of(hole) == target
    # The roof was re-laid with the table and stored: its king's section moved.
    assert after[section]["feature"] != before[section]["feature"]


# --- A feature on a 1.2.0 roof's dropped twin (ROOF-L-DOUBLED-COMMON) -----------------

#: An L (157 x 144.8, the notch to (95.3, 51.1)) where 1.2.0 framed two
#: coincident commons at 16 in o.c. (common/16 and its twin common/17).
L_WALLS = [
    (0, 144.8, 0, 157.0),
    (157.0, 141.3, 270, 141.3),
    (153.5, 0, 180, 58.2),
    (95.3, 3.5, 90, 47.6),
    (98.8, 51.1, 180, 98.8),
    (0, 54.6, 90, 144.8 - 51.1 - 7),
]


def test_a_feature_on_the_dropped_twin_is_named_as_such(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A part saved before the fix stores the twin, and a hole on it. The
    rebuild already drops the twin, so any write that re-expands the roof (to
    the roof, to a wall it picks) is refused with a message that says what
    happened, not that the change removes geometry."""
    from loft_plugins.api import ExpandInputs, Member
    from loft_plugins.builtin import roof_valley

    def keep_twins(
        _inputs: ExpandInputs, members: list[Member], _dropped: set[int]
    ) -> list[Member]:
        return members

    part = Part(client, "L roof saved before the fix")
    walls = [part.added(_wall(*r), f"Wall {i + 1}") for i, r in enumerate(L_WALLS)]
    picks = [{"kind": "feature", "feature_id": w} for w in walls]
    inputs = {**HIP, "spacing_mm": 16 * IN, "walls": picks}
    with monkeypatch.context() as before_the_fix:
        before_the_fix.setattr(roof_valley, "_drop_twins", keep_twins)
        roof = part.added(_custom("loft.roof", "1.2.0", inputs), "Roof")
    twin = member_id(uuid.UUID(roof), "common", 17)
    assert twin in part.members(roof)
    hole = part.drill(twin)

    for response in (
        part.patch(
            roof,
            _custom("loft.roof", "1.2.0", {**inputs, "rafter_material": "dfl_lumber"}),
        ),
        part.patch(walls[0], _wall(*L_WALLS[0])),
    ):
        assert response.status_code == 409, response.text
        error = response.json()["error"]
        assert error["code"] == "feature_has_dependents"
        assert [d["id"] for d in error["details"]["dependents"]] == [hole]
        assert error["message"] == (
            "'Hole' refer(s) to a duplicate rafter that was removed from 'Roof' "
            "(it was framed twice in the same place); delete or re-pick it."
        )
        assert "removes geometry" not in error["message"]
