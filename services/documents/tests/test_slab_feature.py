"""SLAB through documents: a Slab on the outline, walls standing on it.

B8 (docs/reference-parts/buildings.md): B7's 288 x 192 outline, a
``loft.slab`` 1.0.0 on it and ``loft.wall`` 1.4.0 on the outline with On
floor set to the slab. The walls are stored standing on the slab's top, the
cut-list request carries the pour (its waste allowance and two #4 loops) on
the slab's body and anchor bolts on every bottom plate, and the 288
dimension set to 336 re-lays the slab and walls in one write. A 1.3.0 wall
cannot pick a slab (its On floor names floors only).
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.cut_list import CutListMember, CutListPartRequest
from loft_wire.features import EvaluateTreeRequest
from loft_wire.parts import PRINCIPAL_HEADER

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000008b8"}
IN = 25.4


# --- B7's outline and a part to build on it (test_building_outline.py's) ----------


def _line(lid: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": lid,
        "kind": "line",
        "start": {"x": a[0] * IN, "y": a[1] * IN},
        "end": {"x": b[0] * IN, "y": b[1] * IN},
    }


def _at(entity: str, point: str) -> dict[str, str]:
    return {"entity": entity, "point": point}


def _outline(length: float) -> dict[str, Any]:
    """The Rectangle tool from the origin, drawn 288 x 192 and dimensioned
    *length* x 192 (a dimension edit leaves the drawing as it was)."""
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
            json={"name": f"B7 outline {uuid.uuid4()}", "length_unit": "in"},
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

    def stored(self) -> dict[str, Any]:
        response = self.client.get(f"/api/v1/parts/{self.id}/features", headers=HEADERS)
        assert response.status_code == 200, response.text
        return {f["name"]: f["feature"] for f in response.json()["features"]}

    def request(self) -> EvaluateTreeRequest:
        response = self.client.get(
            f"/api/v1/parts/{self.id}/evaluation-request", headers=HEADERS
        )
        assert response.status_code == 200, response.text
        return EvaluateTreeRequest.model_validate_json(response.content)


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _b8(client: TestClient) -> tuple[_Part, str, str, str]:
    part = _Part(client)
    sketch = part.add("Outline", _outline(288))
    slab = part.add("Slab", _custom("loft.slab", "1.0.0", outline=_ref(sketch)))
    walls = part.add(
        "Walls",
        _custom(
            "loft.wall",
            "1.4.0",
            outline=_ref(sketch),
            floor=_ref(slab),
            stud_profile="us_2x6",
        ),
    )
    return part, sketch, slab, walls


def _cut_list_request(client: TestClient, part: _Part) -> CutListPartRequest:
    response = client.get(f"/api/v1/parts/{part.id}/cut-list-request", headers=HEADERS)
    assert response.status_code == 200, response.text
    return CutListPartRequest.model_validate_json(response.content)


def _slab_meta(request: CutListPartRequest) -> CutListMember:
    (slab,) = [m for m in request.members if m.plugin_id == "loft.slab"]
    return slab


def test_walls_stand_on_the_slab_and_list_their_bolts(client: TestClient) -> None:
    part, _, _, _ = _b8(client)
    stored = part.stored()
    assert stored["Slab"]["params"]["inputs"]["waste_percent"] == 5
    request = _cut_list_request(client, part)
    slab = _slab_meta(request)
    assert (slab.role, slab.title) == ("slab", "Slab")
    assert slab.metadata.concrete is not None
    assert slab.metadata.concrete.waste_percent == 5
    assert [round(r.length_mm / IN, 6) for r in slab.metadata.rebar or []] == [
        912.0,
        912.0,
    ]
    plates = [m for m in request.members if m.role == "bottom_plate"]
    assert len(plates) == 4  # no door: one piece per wall
    assert all(m.metadata.anchor_bolts is not None for m in plates)
    assert not any(
        m.metadata.anchor_bolts for m in request.members if m.role != "bottom_plate"
    )
    # The walls' bottom plates sit on the slab's top, Z 0: their level is XY.
    extrudes = {
        e.id: e.feature
        for e in request.evaluation.features
        if e.feature.type == "extrude"
    }
    sketches = {
        e.id: e.feature
        for e in request.evaluation.features
        if e.feature.type == "sketch"
    }
    for plate in plates:
        profile = extrudes[plate.feature_id].params.profile.feature_id  # type: ignore[union-attr]
        plane = sketches[profile].params.plane  # type: ignore[union-attr]
        assert plane.model_dump() == {"kind": "datum_plane", "plane": "XY"}


def test_one_dimension_edit_re_lays_the_slab_and_walls(client: TestClient) -> None:
    part, sketch, _, _ = _b8(client)
    part.edit(sketch, _outline(336))
    slab = _slab_meta(_cut_list_request(client, part))
    assert [round(r.length_mm / IN, 6) for r in slab.metadata.rebar or []] == [
        1008.0,
        1008.0,
    ]
    assert all(e.input_error is None for e in part.request().features)


def test_a_1_3_0_wall_cannot_stand_on_a_slab(client: TestClient) -> None:
    part, sketch, slab, _ = _b8(client)
    response = client.post(
        f"/api/v1/parts/{part.id}/features",
        json={
            "name": "Old walls",
            "feature": _custom(
                "loft.wall", "1.3.0", outline=_ref(sketch), floor=_ref(slab)
            ),
            "expected_tree_version": part.version,
        },
        headers=HEADERS,
    )
    assert response.status_code == 422, response.text
    assert "loft.floor" in response.json()["error"]["message"]
