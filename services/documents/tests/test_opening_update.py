"""OPENING-UPDATE through documents: out-of-date custom features say so, and
"Update all" re-pins them in ONE undoable edit.

B7 as saved before HEADER-PLIES (b7-outline: walls 1.3.0, the door and five
windows 1.1.0, the roof 1.4.0, the floor 1.2.0). Each feature with a declared
update carries ``plugin_update`` (Onshape marks a custom feature whose Feature
Studio is newer; Fusion badges stale content), naming what it adds, read by
a dry run (PLUGIN-UPDATE-ALL): the roof "11 ceiling joists", each opening "2
header spacers" and "1 header ply" (its wall's); the floor and the walls
change no member, so their offers are ``quiet``. ``POST
.../features/plugin-updates`` with no ids updates every one of them: the
floor to 1.4.0 (Joists bear on Long walls, its members byte for byte), the
walls to 1.4.0, the openings to 1.5.0 (their inputs carried by
``loft_plugins.updates``: Measured from the wall start, Custom size, Rough
opening only, Header build Fill the wall) and the roof to 1.7.0 with its
ceiling joists and gable ends. The walls then frame 18 header plies (was 12) and the
openings draw 12 spacers; one Undo restores every row byte for byte, and Redo
brings the update back. A feature with no update is refused, and a refusal on
the last feature rolls back the first: nothing is written. B1's deck at
1.1.0 gains its 3 pier footings and post bases; B9's foundation at 1.0.0
lists its 5 vents and access door.
"""

import dataclasses
import uuid
from collections import Counter
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_plugins.updates import UPDATES as UPDATE_TABLE
from loft_wire.parts import PRINCIPAL_HEADER

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000007ba"}
IN = 25.4
UPDATES = "plugin-updates"


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


#: B7's 288 x 192 outline as the Rectangle tool draws it from the origin.
B7_CORNERS = [(0.0, 0.0), (288.0, 0.0), (288.0, 192.0), (0.0, 192.0)]


def _outline(
    corners: list[tuple[float, float]] = B7_CORNERS,
) -> dict[str, Any]:
    """A rectangle outline drawn through *corners* from the origin (B7's by
    default), its first two sides dimensioned."""
    first = abs(corners[1][0] - corners[0][0]) + abs(corners[1][1] - corners[0][1])
    second = abs(corners[2][0] - corners[1][0]) + abs(corners[2][1] - corners[1][1])
    constraints: list[dict[str, Any]] = [
        {"kind": "fixed", "point": _at("origin", "position")},
        {"kind": "coincident", "a": _at("e1", "start"), "b": _at("origin", "position")},
    ]
    for k in range(4):
        lid = f"e{k + 1}"
        a, b = corners[k], corners[(k + 1) % 4]
        constraints.append(
            {"kind": "horizontal" if a[1] == b[1] else "vertical", "entity": lid}
        )
        constraints.append(
            {
                "kind": "coincident",
                "a": _at(lid, "end"),
                "b": _at(f"e{(k + 1) % 4 + 1}", "start"),
            }
        )
    constraints += [
        {"kind": "distance", "entity": "e1", "value_mm": first * IN, "name": "length"},
        {"kind": "distance", "entity": "e2", "value_mm": second * IN, "name": "width"},
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
            json={"name": f"B7 update {uuid.uuid4()}", "length_unit": "in"},
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

    def tree(self) -> dict[str, Any]:
        response = self.client.get(f"/api/v1/parts/{self.id}/features", headers=HEADERS)
        assert response.status_code == 200, response.text
        return response.json()

    def rows(self) -> dict[str, dict[str, Any]]:
        return {f["name"]: f for f in self.tree()["features"]}

    def update(self, feature_ids: list[str] | None = None) -> Any:
        body: dict[str, Any] = {"expected_tree_version": self.version}
        if feature_ids is not None:
            body["feature_ids"] = feature_ids
        response = self.client.post(
            f"/api/v1/parts/{self.id}/features/{UPDATES}", json=body, headers=HEADERS
        )
        if response.status_code == 200:
            self.version = int(response.json()["tree_version"])
        return response

    def step(self, direction: str) -> None:
        response = self.client.post(
            f"/api/v1/parts/{self.id}/{direction}",
            json={"expected_tree_version": self.version},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        self.version = int(response.json()["tree_version"])


#: B7's openings on its outline walls (buildings.md B7): the front wall runs
#: from X 288 to X 0, so its door at X 144 and windows at X 60 and 228 sit
#: 288 - X from its start; the back window at X 144; each side's centred.
OPENINGS: list[tuple[str, str, str, dict[str, float]]] = [
    ("Door", "loft.door", "e1", {"offset_mm": 144 * IN}),
    ("Window 1", "loft.window", "e1", {"offset_mm": 228 * IN}),
    ("Window 2", "loft.window", "e1", {"offset_mm": 60 * IN}),
    ("Window 3", "loft.window", "e3", {"offset_mm": 144 * IN}),
    ("Window 4", "loft.window", "e4", {"offset_mm": 90.5 * IN}),
    ("Window 5", "loft.window", "e2", {"offset_mm": 90.5 * IN}),
]
BIG = {"width_mm": 36 * IN, "height_mm": 48 * IN}


def _b7(client: TestClient) -> _Part:
    part = _Part(client)
    sketch = part.add("Outline", _outline())
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
    for name, plugin, segment, raw in OPENINGS:
        size = BIG if name in ("Window 1", "Window 2", "Window 3") else {}
        part.add(
            name,
            _custom(
                plugin,
                "1.1.0",
                host_wall=_ref(walls),
                wall_segment=[segment],
                **raw,
                **size,
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
    return part


def _pins(rows: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        name: row["feature"]["params"]["plugin_version"]
        for name, row in rows.items()
        if row["feature"]["type"] == "custom"
    }


def _roles(rows: dict[str, dict[str, Any]]) -> Counter[str]:
    return Counter(
        m["role"]
        for row in rows.values()
        if row["feature"]["type"] == "custom"
        for m in row["feature"]["params"]["expansion"]
    )


OPENING_NAMES = [name for name, *_ in OPENINGS]
STORED = {
    "Floor": "1.2.0",
    "Walls": "1.3.0",
    **{name: "1.1.0" for name in OPENING_NAMES},
    "Roof": "1.4.0",
}
UPDATED = {
    "Floor": "1.4.0",
    "Walls": "1.5.0",
    **{name: "1.5.0" for name in OPENING_NAMES},
    "Roof": "1.8.0",
}


def test_each_out_of_date_feature_offers_its_update(client: TestClient) -> None:
    rows = _b7(client).rows()
    assert _pins(rows) == STORED
    offers = {name: row.get("plugin_update") for name, row in rows.items()}
    assert offers["Outline"] is None
    # The floor and the walls change no member: no badge, but Update all.
    # The walls' update leaves Exterior finish at None (SIDING-TRIM).
    for name, version in (("Floor", "1.4.0"), ("Walls", "1.5.0")):
        offer = offers[name]
        assert offer is not None and offer["to_version"] == version
        assert (offer["adds"], offer["quiet"]) == ([], True)
        assert (offer["relays"], offer["separate"]) == ([], False)
    roof = offers["Roof"]
    assert roof is not None and roof["to_version"] == "1.8.0"
    adds = ["11 ceiling joists", "22 gable studs", "12 gable sheathing panels"]
    assert (roof["adds"], roof["quiet"]) == (adds, False)
    assert roof["summary"].startswith(
        "Adds 11 ceiling joists, 22 gable studs and 12 gable sheathing panels. "
    )
    for name in OPENING_NAMES:
        offer = offers[name]
        assert offer is not None and offer["to_version"] == "1.5.0"
        assert offer["adds"] == ["2 header spacers", "1 header ply"]
        assert offer["summary"].startswith("Adds 2 header spacers and 1 header ply.")
        assert not offer["quiet"]
    # Reading never re-pins, and the stored headers are two plies.
    assert _pins(rows) == STORED
    assert _roles(rows)["header"] == 12


def test_update_all_is_one_edit_and_one_undo_step(client: TestClient) -> None:
    part = _b7(client)
    before = part.rows()
    version = part.version
    response = part.update()
    assert response.status_code == 200, response.text
    assert part.version == version + 1
    rows = {f["name"]: f for f in response.json()["features"]}
    assert _pins(rows) == UPDATED
    assert all(row.get("plugin_update") is None for row in rows.values())
    roles = _roles(rows)
    # 18 plies (was 12) and 12 spacers: 2 per opening, B7's 2x6 headers; and
    # the gable's 11 ceiling joists and gable ends (the new defaults).
    assert (roles["header"], roles["spacer"], roles["foam"]) == (18, 12, 0)
    assert roles["ceiling_joist"] == 11
    assert (roles["gable_stud"], roles["gable_sheathing"]) == (22, 12)
    # The openings' inputs, carried by the map: what 1.1.0 built, filled.
    door = rows["Door"]["feature"]["params"]["inputs"]
    assert {k: door[k] for k in ("measure_from", "size", "draw_unit")} == {
        "measure_from": "start",
        "size": "custom",
        "draw_unit": "none",
    }
    assert door["header_build"] == "fill"
    assert (
        door["offset_mm"] == before["Door"]["feature"]["params"]["inputs"]["offset_mm"]
    )
    # The floor expands to exactly what it did, on Long walls; the roof to
    # what it did, then its joists.
    floor = rows["Floor"]["feature"]["params"]
    assert floor["expansion"] == before["Floor"]["feature"]["params"]["expansion"]
    assert floor["inputs"]["joists_bear_on"] == "long_walls"
    roof = rows["Roof"]["feature"]["params"]["expansion"]
    stored_roof = before["Roof"]["feature"]["params"]["expansion"]
    assert roof[: len(stored_roof)] == stored_roof
    # One Undo restores every row as it was stored, byte for byte.
    part.step("undo")
    restored = part.rows()
    assert {n: r["feature"] for n, r in restored.items()} == {
        n: r["feature"] for n, r in before.items()
    }
    assert restored["Walls"].get("plugin_update") is not None
    part.step("redo")
    assert _pins(part.rows()) == UPDATED


def test_one_feature_updates_alone_and_its_wall_reframes(client: TestClient) -> None:
    part = _b7(client)
    rows = part.rows()
    response = part.update([rows["Door"]["id"]])
    assert response.status_code == 200, response.text
    after = {f["name"]: f for f in response.json()["features"]}
    assert _pins(after) == {**STORED, "Door": "1.5.0"}
    # The walls (still 1.3.0) frame the door's header in three plies.
    assert _roles(after)["header"] == 13
    assert _roles(after)["spacer"] == 2


def test_a_feature_with_no_update_is_refused_and_nothing_is_written(
    client: TestClient,
) -> None:
    part = _b7(client)
    rows = part.rows()
    version = part.version
    refused = part.update([rows["Door"]["id"], rows["Outline"]["id"]])
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "plugin_update_unavailable"
    assert part.tree()["tree_version"] == version
    assert _pins(part.rows()) == STORED
    missing = part.update([str(uuid.uuid4())])
    assert missing.status_code == 404, missing.text
    # Updated, nothing is left to update.
    assert part.update().status_code == 200
    again = part.update()
    assert again.status_code == 422
    assert again.json()["error"]["code"] == "plugin_update_unavailable"


def test_a_stale_update_is_refused(client: TestClient) -> None:
    part = _b7(client)
    part.version -= 1
    response = part.update()
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "stale_tree_version"


def test_the_evaluation_sends_the_spacers_with_their_material(
    client: TestClient,
) -> None:
    part = _b7(client)
    assert part.update().status_code == 200
    response = client.get(
        f"/api/v1/parts/{part.id}/evaluation-request", headers=HEADERS
    )
    assert response.status_code == 200, response.text
    request = response.json()
    rows = part.rows()
    spacer_ids = {
        m["id"]
        for name in OPENING_NAMES
        for m in rows[name]["feature"]["params"]["expansion"]
        if m["role"] == "spacer"
    }
    sent = {f["id"] for f in request["features"]}
    assert len(spacer_ids) == 12 and spacer_ids <= sent
    bodies = {
        b["base_feature_id"]: b["material"] for b in request["materials"]["bodies"]
    }
    assert {bodies[i] for i in spacer_ids} == {"plywood"}


def _bad_roof_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """The roof's update refused: its map gives a pitch 1.8.0 has not."""

    def bad_pitch(inputs: Any, _context: Any) -> dict[str, Any]:
        return {**inputs, "pitch": "rise_99"}

    roof = UPDATE_TABLE[("loft.roof", "1.4.0")]
    monkeypatch.setitem(
        UPDATE_TABLE,  # type: ignore[arg-type]
        ("loft.roof", "1.4.0"),
        dataclasses.replace(roof, map_inputs=bad_pitch),
    )


def test_update_all_skips_a_refused_feature_and_updates_the_rest(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Update all omits and warns (VISION, 2026-10-29): the roof, the last
    feature, is refused after the floor, the walls and the six openings
    were re-pinned; it alone is restored as stored and listed with its
    reason, the rest update in one step, and one Undo restores them."""
    part = _b7(client)
    before = part.rows()
    version = part.version
    _bad_roof_map(monkeypatch)
    response = part.update()
    assert response.status_code == 200, response.text
    body = response.json()
    assert part.version == version + 1
    (skipped,) = body["skipped_updates"]
    assert (skipped["name"], skipped["reason"], skipped["code"]) == (
        "Roof",
        "refused",
        "plugin_input_invalid",
    )
    assert skipped["message"]
    rows = {f["name"]: f for f in body["features"]}
    assert _pins(rows) == {**UPDATED, "Roof": "1.4.0"}
    assert rows["Roof"]["feature"] == before["Roof"]["feature"]
    # The roof's dependency edges are as stored: the walls still cannot go.
    blocked = client.delete(
        f"/api/v1/parts/{part.id}/features/{rows['Walls']['id']}",
        params={"expected_tree_version": part.version},
        headers=HEADERS,
    )
    assert blocked.status_code == 409, blocked.text
    # One Undo: every row as stored, byte for byte.
    monkeypatch.undo()
    part.step("undo")
    assert {n: r["feature"] for n, r in part.rows().items()} == {
        n: r["feature"] for n, r in before.items()
    }


def test_named_features_are_all_or_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Updating named features, a refusal on the last (the roof) rolls back
    the first (the door): nothing is written, the tree version and the
    history do not move."""
    part = _b7(client)
    before = part.rows()
    version = part.version
    _bad_roof_map(monkeypatch)
    refused = part.update([before["Door"]["id"], before["Roof"]["id"]])
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "plugin_input_invalid"
    tree = part.tree()
    assert tree["tree_version"] == version
    after = {f["name"]: f for f in tree["features"]}
    assert {n: r["feature"] for n, r in after.items()} == {
        n: r["feature"] for n, r in before.items()
    }
    # Undo steps back over the roof's own add, not over a half update.
    monkeypatch.undo()
    part.step("undo")
    assert "Roof" not in part.rows()
    assert _pins(part.rows()) == {k: v for k, v in STORED.items() if k != "Roof"}


#: A 290 x 197 outline drawn clockwise from the origin, up first: 1.2.0 laid
#: its floor from another corner than 1.3.0's lowest one, and 16 in o.c.
#: divides neither side, so the update re-lays the floor.
CLOCKWISE = [(0.0, 0.0), (0.0, 197.0), (290.0, 197.0), (290.0, 0.0)]


def test_an_update_that_re_lays_a_floor_is_left_for_its_own_decision(
    client: TestClient,
) -> None:
    part = _Part(client)
    sketch = part.add("Outline", _outline(CLOCKWISE))
    part.add(
        "Floor",
        _custom("loft.floor", "1.2.0", outline=_ref(sketch), joist_profile="us_2x10"),
    )
    part.add("Deck", _custom("loft.deck", "1.1.0", width_mm=192 * IN))
    rows = part.rows()
    offer = rows["Floor"]["plugin_update"]
    assert offer is not None and offer["separate"]
    assert offer["relays"] and offer["relays"][0].endswith(" joists")
    assert offer["summary"].startswith("Re-lays ")
    assert " from the outline's lowest corner." in offer["summary"]
    # Update all takes the deck and leaves the floor, listed.
    response = part.update()
    assert response.status_code == 200, response.text
    body = response.json()
    (skipped,) = body["skipped_updates"]
    assert (skipped["name"], skipped["reason"]) == ("Floor", "separate")
    assert skipped["message"].endswith("Update it on its own.")
    assert _pins({f["name"]: f for f in body["features"]}) == {
        "Floor": "1.2.0",
        "Deck": "1.3.0",
    }
    # On its own it updates, re-laid as it said.
    alone = part.update([rows["Floor"]["id"]])
    assert alone.status_code == 200, alone.text
    assert "skipped_updates" not in alone.json()
    floor = {f["name"]: f for f in alone.json()["features"]}["Floor"]
    assert floor["feature"]["params"]["plugin_version"] == "1.4.0"
    assert floor.get("plugin_update") is None
    # Only the floor was left: Update all now has nothing to do.
    assert part.update().status_code == 422


def _deck(client: TestClient, version: str) -> _Part:
    part = _Part(client)
    part.add("Deck", _custom("loft.deck", version, width_mm=192 * IN))
    return part


def test_b1_at_deck_1_1_0_gains_its_footings_and_post_bases(
    client: TestClient,
) -> None:
    part = _deck(client, "1.1.0")
    offer = part.rows()["Deck"]["plugin_update"]
    assert offer is not None and offer["to_version"] == "1.3.0"
    assert offer["adds"] == ["3 pier footings", "3 post bases"]
    assert offer["summary"].startswith("Adds 3 pier footings and 3 post bases. ")
    before = part.rows()["Deck"]["feature"]["params"]["expansion"]
    response = part.update()
    assert response.status_code == 200, response.text
    deck = {f["name"]: f for f in response.json()["features"]}["Deck"]
    assert deck.get("plugin_update") is None
    expansion = deck["feature"]["params"]["expansion"]
    footings = [m for m in expansion if m["role"] == "footing"]
    assert len(footings) == 3
    assert {m["metadata"]["concrete"]["post_base"] for m in footings} == {
        "post_base_6x6"
    }
    # Every 1.1.0 member is kept under its id (its running index aside).
    by_id = {m["id"]: m for m in expansion}
    assert all({**by_id[m["id"]], "index": m["index"]} == m for m in before)
    assert part.update().status_code == 422  # nothing left to update


def test_b9_at_foundation_1_0_0_lists_its_vents_and_access_door(
    client: TestClient,
) -> None:
    part = _b7(client)
    rows = part.rows()
    part.add(
        "Foundation",
        _custom(
            "loft.foundation",
            "1.0.0",
            outline=_ref(rows["Outline"]["id"]),
            floor=_ref(rows["Floor"]["id"]),
        ),
    )
    offer = part.rows()["Foundation"]["plugin_update"]
    assert offer is not None and offer["to_version"] == "1.1.0"
    assert offer["adds"] == ["5 foundation vents", "1 access door"]
    response = part.update([part.rows()["Foundation"]["id"]])
    assert response.status_code == 200, response.text
    stem = next(
        m
        for f in response.json()["features"]
        if f["name"] == "Foundation"
        for m in f["feature"]["params"]["expansion"]
        if m["role"] == "stem"
    )
    assert [
        (o["item"], o["quantity"]) for o in stem["metadata"]["foundation_openings"]
    ] == [("foundation_vent", 5), ("crawl_access_door", 1)]


def test_an_update_it_cannot_preview_is_left_for_its_own_decision(
    client: TestClient,
) -> None:
    """A suppressed floor drawn clockwise (its update would re-lay it, but a
    suppressed row's dry run is not run): its offer cannot say what it moves,
    so it is separate, says so, and Update all leaves and lists it."""
    part = _Part(client)
    sketch = part.add("Outline", _outline(CLOCKWISE))
    floor = part.add(
        "Floor",
        _custom("loft.floor", "1.2.0", outline=_ref(sketch), joist_profile="us_2x10"),
    )
    part.add("Deck", _custom("loft.deck", "1.1.0", width_mm=192 * IN))
    suppressed = client.patch(
        f"/api/v1/parts/{part.id}/features/{floor}/suppress",
        json={"suppressed": True, "expected_tree_version": part.version},
        headers=HEADERS,
    )
    assert suppressed.status_code == 200, suppressed.text
    part.version = int(suppressed.json()["tree_version"])
    offer = part.rows()["Floor"]["plugin_update"]
    assert offer is not None and offer["separate"]
    assert offer["summary"].startswith(
        "Can't preview this update (suppressed or refused); update it on its own."
    )
    response = part.update()
    assert response.status_code == 200, response.text
    body = response.json()
    (skipped,) = body["skipped_updates"]
    assert (skipped["name"], skipped["reason"]) == ("Floor", "separate")
    assert _pins({f["name"]: f for f in body["features"]}) == {
        "Floor": "1.2.0",
        "Deck": "1.3.0",
    }
