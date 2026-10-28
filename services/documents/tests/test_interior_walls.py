"""INTERIOR-WALLS through documents: B10's partitions, their backing in the
walls they meet and a door in one (packages/loft-plugins/tests/
test_interior_walls.py checks the members against buildings.md B10).

B7's 288 x 192 outline plus two lines (X 180 and Y 132), a Floor and Walls
1.4.0 on it, one Interior wall on the walls and a 2868 door in P2. The
Interior wall names the walls as its host, so writing it re-expands the
walls with their backing, and deleting it takes the backing away; the door
names the Interior wall, so writing it re-frames P2. One dimension edit,
288 -> 336, re-lays it all with the partitions where they were.
"""

import uuid
from collections import Counter
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.parts import PRINCIPAL_HEADER

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-000000010b10"}
IN = 25.4


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _line(lid: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": lid,
        "kind": "line",
        "start": {"x": a[0] * IN, "y": a[1] * IN},
        "end": {"x": b[0] * IN, "y": b[1] * IN},
    }


def _at(entity: str, point: str) -> dict[str, str]:
    return {"entity": entity, "point": point}


def _plan(length: float) -> dict[str, Any]:
    """The Rectangle tool from the origin, dimensioned *length* x 192, and
    P1 (e5) and P2 (e6) drawn at 288, dimensioned from the left and front
    lines."""
    corners = [(0.0, 0.0), (288.0, 0.0), (288.0, 192.0), (0.0, 192.0)]
    constraints: list[dict[str, Any]] = [
        {"kind": "fixed", "point": _at("origin", "position")},
        {"kind": "coincident", "a": _at("e1", "start"), "b": _at("origin", "position")},
    ]
    for k in range(4):
        lid = f"e{k + 1}"
        constraints.append(
            {"kind": "vertical" if k % 2 else "horizontal", "entity": lid}
        )
        constraints.append(
            {
                "kind": "coincident",
                "a": _at(lid, "end"),
                "b": _at(f"e{(k + 1) % 4 + 1}", "start"),
            }
        )
    constraints += [
        {"kind": "distance", "entity": "e1", "value_mm": length * IN, "name": "length"},
        {"kind": "distance", "entity": "e2", "value_mm": 192 * IN, "name": "width"},
        {"kind": "vertical", "entity": "e5"},
        {"kind": "horizontal", "entity": "e6"},
        {
            "kind": "point_line_distance",
            "point": _at("e5", "start"),
            "line": "e4",
            "value_mm": 180 * IN,
        },
        {
            "kind": "point_line_distance",
            "point": _at("e6", "start"),
            "line": "e1",
            "value_mm": 132 * IN,
        },
    ]
    return {
        "type": "sketch",
        "version": 1,
        "params": {
            "plane": {"kind": "datum_plane", "plane": "XY"},
            "entities": [
                {
                    "id": "origin",
                    "kind": "point",
                    "construction": True,
                    "position": {"x": 0.0, "y": 0.0},
                },
                *(
                    _line(f"e{k + 1}", corners[k], corners[(k + 1) % 4])
                    for k in range(4)
                ),
                _line("e5", (180, 192), (180, 0)),
                _line("e6", (288, 132), (180, 132)),
            ],
            "constraints": constraints,
        },
    }


def _custom(plugin: str, version: str, **inputs: Any) -> dict[str, Any]:
    return {
        "type": "custom",
        "version": 1,
        "params": {"plugin_id": plugin, "plugin_version": version, "inputs": inputs},
    }


def _ref(feature_id: str) -> dict[str, str]:
    return {"kind": "feature", "feature_id": feature_id}


class _Part:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        response = client.post(
            "/api/v1/parts",
            json={"name": f"B10 {uuid.uuid4()}", "length_unit": "in"},
            headers=HEADERS,
        )
        assert response.status_code == 201, response.text
        self.id = str(response.json()["id"])
        self.version = int(response.json()["tree_version"])

    def add(self, name: str, feature: dict[str, Any]) -> str:
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
        return str(response.json()["feature"]["id"])

    def edit(self, feature_id: str, feature: dict[str, Any]) -> None:
        response = self.client.patch(
            f"/api/v1/parts/{self.id}/features/{feature_id}",
            json={"feature": feature, "expected_tree_version": self.version},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        self.version = int(response.json()["tree_version"])

    def delete(self, feature_id: str) -> None:
        response = self.client.delete(
            f"/api/v1/parts/{self.id}/features/{feature_id}",
            params={"expected_tree_version": self.version},
            headers=HEADERS,
        )
        assert response.status_code in (200, 204), response.text
        self.version += 1
        listed = self.client.get(f"/api/v1/parts/{self.id}/features", headers=HEADERS)
        self.version = int(listed.json()["tree_version"])

    def stored(self) -> dict[str, Any]:
        response = self.client.get(f"/api/v1/parts/{self.id}/features", headers=HEADERS)
        assert response.status_code == 200, response.text
        return {f["name"]: f["feature"] for f in response.json()["features"]}


def _roles(stored: dict[str, Any], name: str) -> Counter[str]:
    return Counter(m["role"] for m in stored[name]["params"]["expansion"])


def _b10(client: TestClient) -> tuple[_Part, dict[str, str]]:
    part = _Part(client)
    ids: dict[str, str] = {}
    ids["sketch"] = part.add("Plan", _plan(288))
    ids["floor"] = part.add(
        "Floor",
        _custom(
            "loft.floor", "1.3.0", outline=_ref(ids["sketch"]), joist_profile="us_2x10"
        ),
    )
    ids["walls"] = part.add(
        "Walls",
        _custom(
            "loft.wall",
            "1.4.0",
            outline=_ref(ids["sketch"]),
            floor=_ref(ids["floor"]),
            stud_profile="us_2x6",
            sheathing="osb_7_16",
        ),
    )
    ids["interior"] = part.add(
        "Interior walls",
        _custom("loft.interior_wall", "1.0.0", host_wall=_ref(ids["walls"])),
    )
    ids["door"] = part.add(
        "Door",
        _custom(
            "loft.door",
            "1.4.0",
            host_wall=_ref(ids["interior"]),
            wall_segment=["e6"],
            size="door_2868",
            measure_from="end",
            offset_mm=50.25 * IN,
        ),
    )
    return part, ids


def _x_extent(stored: dict[str, Any], name: str, member: str) -> tuple[float, float]:
    """The X extent (in) of the section sketch of the member named *member*."""
    expansion = stored[name]["params"]["expansion"]
    section = next(
        m for m in expansion if m["role"] == "section" and m.get("name") == member
    )
    xs = [
        e[p]["x"] / IN
        for e in section["feature"]["params"]["entities"]
        for p in ("start", "end")
    ]
    return round(min(xs), 6), round(max(xs), 6)


def test_b10_frames_its_partitions_backing_and_door(client: TestClient) -> None:
    part, _ = _b10(client)
    stored = part.stored()
    assert _roles(stored, "Walls")["block"] == 9
    interior = _roles(stored, "Interior walls")
    assert interior["block"] == 3
    assert interior["finish"] == 20
    assert interior["bottom_plate"] == 3  # P2's cut at the door
    assert interior["king"] == 2 and interior["jack"] == 2
    assert _roles(stored, "Door")["frame"] == 1
    assert stored["Door"]["params"]["inputs"]["measure_from"] == "end"
    assert _x_extent(stored, "Interior walls", "e6/top_plate/course/1") == (
        181.75,
        282.5,
    )


def test_28_ft_keeps_the_partitions_and_grows_p2(client: TestClient) -> None:
    part, ids = _b10(client)
    part.edit(ids["sketch"], _plan(336))
    stored = part.stored()
    assert _x_extent(stored, "Interior walls", "e5/top_plate/course/1") == (
        178.25,
        181.75,
    )
    assert _x_extent(stored, "Interior walls", "e6/top_plate/course/1") == (
        181.75,
        330.5,
    )
    assert _roles(stored, "Walls")["block"] == 9


def test_deleting_the_partitions_takes_their_backing_away(client: TestClient) -> None:
    part, ids = _b10(client)
    part.delete(ids["door"])
    part.delete(ids["interior"])
    stored = part.stored()
    assert _roles(stored, "Walls")["block"] == 0


def test_partitions_need_1_4_0_walls(client: TestClient) -> None:
    part = _Part(client)
    sketch = part.add("Plan", _plan(288))
    walls = part.add(
        "Walls",
        _custom("loft.wall", "1.3.0", outline=_ref(sketch), stud_profile="us_2x6"),
    )
    response = client.post(
        f"/api/v1/parts/{part.id}/features",
        json={
            "name": "Interior walls",
            "feature": _custom("loft.interior_wall", "1.0.0", host_wall=_ref(walls)),
            "expected_tree_version": part.version,
        },
        headers=HEADERS,
    )
    assert response.status_code == 422, response.text
    assert "update the walls to 1.4.0" in response.json()["error"]["message"]
