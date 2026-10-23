"""BUILDING-OUTLINE through documents: one sketch drives the walls and the
floor, the roof picks the walls, and one dimension edit re-lays them all.

B7's 288 x 192 outline (packages/loft-plugins/tests/test_building_outline.py
checks the members against the QA-B7-HOUSE round's typed build): a Floor and
Walls on the outline, the walls on the floor, a window in the back wall and
a gable whose front and back walls define the slope. Setting the sketch's 288
dimension to 336 is one write; it stores the walls', floor's and roof's new
expansions (the roof picks the walls, which pick the sketch), and the next
evaluation sends the 28 ft house. The sketch cannot be deleted under them.
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

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000007b7"}
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


def _house(client: TestClient) -> tuple[_Part, str]:
    part = _Part(client)
    sketch = part.add("Outline", _outline(288))
    floor = part.add(
        "Floor",
        _custom("loft.floor", "1.2.0", outline=_ref(sketch), joist_profile="us_2x10"),
    )
    walls = part.add(
        "Walls",
        _custom(
            "loft.wall",
            "1.3.0",
            outline=_ref(sketch),
            floor=_ref(floor),
            stud_profile="us_2x6",
            sheathing="osb_7_16",
        ),
    )
    part.add(
        "Window",
        _custom(
            "loft.window",
            "1.1.0",
            host_wall=_ref(walls),
            wall_segment=["e3"],
            offset_mm=144 * IN,
            width_mm=36 * IN,
            height_mm=48 * IN,
        ),
    )
    part.add(
        "Roof",
        _custom(
            "loft.roof",
            "1.4.0",
            walls=[_ref(walls)],
            slope_walls=["e1", "e3"],
            rafter_profile="us_2x8",
            ridge_profile="us_2x10",
        ),
    )
    return part, sketch


def _roles(stored: dict[str, Any], name: str) -> Counter[str]:
    return Counter(m["role"] for m in stored[name]["params"]["expansion"])


def test_one_dimension_edit_re_lays_the_walls_floor_and_roof(
    client: TestClient,
) -> None:
    part, sketch = _house(client)
    before = part.stored()
    assert before["Window"]["params"]["inputs"]["wall_segment"] == ["e3"]
    assert _roles(before, "Floor")["joist"] == 19
    assert _roles(before, "Roof")["rafter"] == 26
    request = part.request()
    extrudes = [
        e.feature.params.model_dump()
        for e in request.features
        if e.feature.type == "extrude"
    ]
    bodies = sum(1 for p in extrudes if p["operation"] == "add")
    # Every member that is a body (it carries metadata) is sent: the floor
    # 39, the walls with the back window and their OSB, the roof 27; and the
    # 26 tails' notches in the front and back OSB, cuts of no body.
    assert sum(1 for p in extrudes if p["operation"] == "cut") == 26
    members = [
        m
        for name in ("Floor", "Walls", "Roof")
        for m in before[name]["params"]["expansion"]
        if m.get("metadata") is not None
    ]
    assert bodies == len(members)
    assert sum(1 for m in members if m["role"] in ("rafter", "ridge")) == 27
    assert all(e.input_error is None for e in request.features)

    part.edit(sketch, _outline(336))
    after = part.stored()
    assert _roles(after, "Floor")["joist"] == 22
    assert _roles(after, "Roof")["rafter"] == 30
    assert _roles(after, "Walls")["sheathing"] > _roles(before, "Walls")["sheathing"]
    request = part.request()
    assert all(e.input_error is None for e in request.features)
    ridge = next(
        e
        for e in request.features
        if e.feature.type == "extrude"
        and e.feature.params.model_dump()["distance_mm"] == pytest.approx(336 * IN)
    )
    assert ridge is not None


def test_the_outline_cannot_be_deleted_under_its_walls(client: TestClient) -> None:
    part, sketch = _house(client)
    response = client.delete(
        f"/api/v1/parts/{part.id}/features/{sketch}",
        params={"expected_tree_version": part.version},
        headers=HEADERS,
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "feature_has_dependents"


def test_an_outline_that_is_not_fully_defined_is_a_typed_refusal(
    client: TestClient,
) -> None:
    part = _Part(client)
    loose = _outline(288)
    loose["params"]["constraints"] = [
        c for c in loose["params"]["constraints"] if c.get("name") != "width"
    ]
    sketch = part.add("Outline", loose)
    response = client.post(
        f"/api/v1/parts/{part.id}/features",
        json={
            "name": "Walls",
            "feature": _custom("loft.wall", "1.3.0", outline=_ref(sketch)),
            "expected_tree_version": part.version,
        },
        headers=HEADERS,
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "plugin_input_unsupported"
    assert error["details"]["input"] == "outline"
    assert "not fully defined" in error["message"]


# --- Dimensions driven by formulas (the walls follow the sketch as it solves) ------


def _driven(expression: str) -> dict[str, Any]:
    """The outline with its length dimension driven by *expression*; its
    stored value still 288, as a client that saves the formula leaves it."""
    sketch = _outline(288)
    for c in sketch["params"]["constraints"]:
        if c.get("name") == "length":
            c["expression"] = expression
    return sketch


def _extrude_lengths(part: _Part) -> list[float]:
    request = part.request()
    assert all(e.input_error is None for e in request.features)
    return [
        float(e.feature.params.model_dump()["distance_mm"])
        for e in request.features
        if e.feature.type == "extrude"
    ]


def _is_house(part: _Part, length: float, joists: int, rafters: int) -> None:
    """The walls, floor and roof, stored and sent, are the *length* house."""
    stored = part.stored()
    assert _roles(stored, "Floor")["joist"] == joists
    assert _roles(stored, "Roof")["rafter"] == rafters
    lengths = _extrude_lengths(part)
    other = 336.0 if length == 288.0 else 288.0
    assert any(d == pytest.approx(length * IN) for d in lengths)  # the ridge
    assert not any(d == pytest.approx(other * IN) for d in lengths)


def test_the_outline_follows_a_dimension_typed_with_its_unit(
    client: TestClient,
) -> None:
    part, sketch = _house(client)
    part.edit(sketch, _driven("336 in"))
    _is_house(part, 336.0, 22, 30)


def test_a_bare_number_in_an_inch_part_is_inches_and_the_walls_follow(
    client: TestClient,
) -> None:
    """FORMULA-BARE-UNIT: the length typed as a bare ``336`` in this inch
    part is stored as ``336 in``, and the house is 28 ft, not 336 mm."""
    part, sketch = _house(client)
    part.edit(sketch, _driven("336"))
    stored = part.stored()["Outline"]["params"]["constraints"]
    length = next(c for c in stored if c.get("name") == "length")
    assert length["expression"] == "336 in"
    _is_house(part, 336.0, 22, 30)


def test_a_dimension_that_does_not_evaluate_flags_the_walls(
    client: TestClient,
) -> None:
    """``1 in / 0`` on the outline's length: the walls, floor and roof are
    sent with an error naming the dimension, never built at the old 288."""
    part, sketch = _house(client)
    part.edit(sketch, _driven("1 in / 0"))
    request = part.request()
    flagged = {
        str(e.input_error.message)
        for e in request.features
        if e.input_error is not None and e.feature.type != "sketch"
    }
    assert flagged
    assert all("dimension 'length'" in message for message in flagged)


def test_the_outline_follows_a_part_parameter_and_its_edit(
    client: TestClient,
) -> None:
    """Length driven by ``L``: the house follows L = 336 in, and a parameter
    edit to 288 in re-expands the walls, floor and roof in the same PUT."""
    part, sketch = _house(client)
    row = {"id": str(uuid.uuid4()), "name": "L", "unit": "length"}

    def put(expression: str) -> None:
        response = client.put(
            f"/api/v1/parts/{part.id}/parameters",
            json={
                "expected_tree_version": part.version,
                "parameters": [{**row, "expression": expression}],
            },
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        part.version = int(response.json()["tree_version"])

    put("336 in")
    part.edit(sketch, _driven("L"))
    _is_house(part, 336.0, 22, 30)
    before = part.stored()["Walls"]["params"]["expansion"]
    put("288 in")
    _is_house(part, 288.0, 19, 26)
    after = part.stored()["Walls"]["params"]["expansion"]
    assert len(after) < len(before)  # the walls were re-laid by the PUT


# --- Openings measured from the end nearer the origin (OPENING-FROM-END) ----------


def _walls_only(client: TestClient) -> tuple[_Part, str, str]:
    part = _Part(client)
    sketch = part.add("Outline", _outline(288))
    walls = part.add(
        "Walls",
        _custom("loft.wall", "1.3.0", outline=_ref(sketch), stud_profile="us_2x6"),
    )
    return part, sketch, walls


def _window(version: str, walls: str, **inputs: Any) -> dict[str, Any]:
    return _custom(
        "loft.window",
        version,
        host_wall=_ref(walls),
        wall_segment=["e1"],
        width_mm=36 * IN,
        height_mm=48 * IN,
        **inputs,
    )


def _framing(part: _Part) -> list[tuple[float, ...]]:
    """The walls' members as geometry alone: every sketch member's line ends
    (mm, to 1e-6), sorted, so two parts compare without their feature ids."""
    out: list[tuple[float, ...]] = []
    for member in part.stored()["Walls"]["params"]["expansion"]:
        feature = member["feature"]
        if feature["type"] != "sketch":
            continue
        for e in feature["params"]["entities"]:
            if e["kind"] == "line":
                ends = (e["start"]["x"], e["start"]["y"], e["end"]["x"], e["end"]["y"])
                out.append(tuple(round(v, 6) + 0.0 for v in ends))
    return sorted(out)


def test_a_new_window_measures_from_the_end_nearer_the_origin(
    client: TestClient,
) -> None:
    """B7's front wall runs X 288 -> 0, so a new 1.2.0 window left at its
    default stores Measured from = end, and 60 is X 60: 1.1.0's 228 from the
    start. Moving it 24 in is one field (60 -> 84); the house growing to 336
    leaves it at X 84, where 1.1.0 needs its offset re-typed (252)."""
    part, sketch, walls = _walls_only(client)
    window = part.add("Window", _window("1.2.0", walls, offset_mm=60 * IN))
    stored = part.stored()["Window"]["params"]["inputs"]
    assert stored["measure_from"] == "end"
    assert stored["offset_mm"] == pytest.approx(60 * IN)

    typed, _, typed_walls = _walls_only(client)
    old = typed.add("Window", _window("1.1.0", typed_walls, offset_mm=228 * IN))
    assert _framing(part) == _framing(typed)

    part.edit(window, _window("1.2.0", walls, measure_from="end", offset_mm=84 * IN))
    typed.edit(old, _window("1.1.0", typed_walls, offset_mm=204 * IN))
    assert _framing(part) == _framing(typed)

    part.edit(sketch, _outline(336))
    typed.edit(_sketch_of(typed), _outline(336))
    assert _framing(part) != _framing(typed)  # 1.1.0's window moved with the start
    typed.edit(old, _window("1.1.0", typed_walls, offset_mm=252 * IN))
    assert _framing(part) == _framing(typed)
    assert part.stored()["Window"]["params"]["inputs"]["offset_mm"] == pytest.approx(
        84 * IN
    )


def _sketch_of(part: _Part) -> str:
    response = part.client.get(f"/api/v1/parts/{part.id}/features", headers=HEADERS)
    return next(
        str(f["id"]) for f in response.json()["features"] if f["name"] == "Outline"
    )


def test_an_explicit_reference_is_stored_as_typed(client: TestClient) -> None:
    """Start, End and Centre are kept; Centre's distance is signed."""
    part, _, walls = _walls_only(client)
    window = part.add(
        "Window", _window("1.2.0", walls, measure_from="start", offset_mm=100 * IN)
    )
    start = _framing(part)
    assert part.stored()["Window"]["params"]["inputs"]["measure_from"] == "start"
    part.edit(
        window, _window("1.2.0", walls, measure_from="centre", offset_mm=-44 * IN)
    )
    assert part.stored()["Window"]["params"]["inputs"]["measure_from"] == "centre"
    assert _framing(part) == start


def test_older_windows_keep_measuring_from_the_start(client: TestClient) -> None:
    part, _, walls = _walls_only(client)
    part.add("Window", _window("1.1.0", walls, offset_mm=228 * IN))
    assert "measure_from" not in part.stored()["Window"]["params"]["inputs"]
