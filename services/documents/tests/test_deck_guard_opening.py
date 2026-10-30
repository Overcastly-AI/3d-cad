"""DECK-GUARD-OPENING through documents: B1's guard opens at its stair.

A ``loft.stair`` offers its inputs to the ``loft.deck`` it picks, as a
window is hosted in its wall: writing, moving, suppressing or deleting the
stair re-expands the deck in the same write, and ``loft.deck`` 1.3.0 breaks
its guard between the stair's outer stringer faces (X 78..114 on B1's rim).
The deck reads the stair's inputs and the stair the deck's, never each
other's members, so the two never cycle. A 1.2.0 deck is untouched and its
stair warns ``stair_deck_guard``; its update to 1.3.0 re-lays the front
guard, so it is offered on its own and Update all leaves it.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.parts import PRINCIPAL_HEADER

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000007bb"}
IN = 25.4
GUARD = {"guard": "open_sides"}


def _custom(plugin: str, version: str, **inputs: Any) -> dict[str, Any]:
    return {
        "type": "custom",
        "version": 1,
        "params": {"plugin_id": plugin, "plugin_version": version, "inputs": inputs},
    }


def _ref(feature_id: str) -> dict[str, str]:
    return {"kind": "feature", "feature_id": feature_id}


class _Part:
    """A part through the API: features added, the tree read, Update run."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        response = client.post(
            "/api/v1/parts",
            json={"name": f"B1 guard {uuid.uuid4()}", "length_unit": "in"},
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
            f"/api/v1/parts/{self.id}/features/plugin-updates",
            json=body,
            headers=HEADERS,
        )
        if response.status_code == 200:
            self.version = int(response.json()["tree_version"])
        return response


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _expansion(part: _Part, name: str = "Deck") -> list[dict[str, Any]]:
    return part.rows()[name]["feature"]["params"]["expansion"]


def _front_posts(part: _Part) -> list[str]:
    return sorted(
        m["name"]
        for m in _expansion(part)
        if m["role"] == "guard_post" and m["name"].startswith("front/")
    )


OPEN = [
    "front/end",
    "front/run/0/1",
    "front/run/0/end",
    "front/run/1/0",
    "front/run/1/1",
]
CLOSED = ["front/1", "front/2", "front/end"]
#: At X 60: runs 0..42 (one bay) and 78..192 (two).
MOVED = ["front/end", "front/run/0/end", "front/run/1/0", "front/run/1/1"]


def _write(client: TestClient, part: _Part, method: str, url: str, body: Any) -> Any:
    response = client.request(
        method,
        f"/api/v1/parts/{part.id}/features{url}",
        json={**body, "expected_tree_version": part.version},
        headers=HEADERS,
    )
    if response.status_code in (200, 201):
        part.version = int(response.json()["tree_version"])
    return response


def test_a_stair_opens_the_guard_and_stops_warning(client: TestClient) -> None:
    part = _Part(client)
    deck = part.add("Deck", _custom("loft.deck", "1.3.0", **GUARD))
    assert _front_posts(part) == CLOSED
    stair = part.add("Stair", _custom("loft.stair", "1.0.0", deck=_ref(deck)))
    # The stair's write re-laid the deck: a post each side of X 78..114.
    assert _front_posts(part) == OPEN
    rows = part.rows()
    assert rows["Stair"].get("plugin_warnings") is None
    assert rows["Deck"].get("plugin_update") is None
    roles = [m["role"] for m in _expansion(part)]
    assert (roles.count("guard_post"), roles.count("baluster")) == (10, 72)

    # Moved to X 60 (X 42..78): the deck follows in the same write.
    moved = _write(
        client,
        part,
        "PATCH",
        f"/{stair}",
        {
            "feature": _custom(
                "loft.stair", "1.0.0", deck=_ref(deck), position_mm=60 * IN
            )
        },
    )
    assert moved.status_code == 200, moved.text
    # Runs 0..42 (one bay) and 78..192 (two): posts at 1.75, 40.25 and
    # 79.75, 135, 190.25.
    assert _front_posts(part) == MOVED

    # Suppressed, the guard closes; restored, it opens again.
    for suppressed, want in ((True, CLOSED), (False, MOVED)):
        response = _write(
            client, part, "PATCH", f"/{stair}/suppress", {"suppressed": suppressed}
        )
        assert response.status_code == 200, response.text
        assert _front_posts(part) == want

    # Deleted, the deck is 1.2.0's B1 again, member for member.
    response = client.request(
        "DELETE",
        f"/api/v1/parts/{part.id}/features/{stair}",
        params={"expected_tree_version": part.version},
        headers=HEADERS,
    )
    assert response.status_code in (200, 204), response.text
    part.version = int(part.tree()["tree_version"])
    assert _front_posts(part) == CLOSED


def test_a_stair_that_leaves_no_room_for_a_post_is_refused(client: TestClient) -> None:
    part = _Part(client)
    deck = part.add("Deck", _custom("loft.deck", "1.3.0", **GUARD))
    before = part.rows()["Deck"]["feature"]
    response = _write(
        client,
        part,
        "POST",
        "",
        {
            "name": "Stair",
            "feature": _custom(
                "loft.stair", "1.0.0", deck=_ref(deck), position_mm=20 * IN
            ),
        },
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "plugin_input_unsupported"
    assert error["message"].startswith(
        "Stair: only 2 in of the front guard is left to the deck's corner"
    )
    assert part.rows()["Deck"]["feature"] == before


def test_a_1_2_deck_keeps_its_guard_and_its_update_is_separate(
    client: TestClient,
) -> None:
    part = _Part(client)
    deck = part.add("Deck", _custom("loft.deck", "1.2.0", **GUARD))
    before = part.rows()["Deck"]["feature"]
    part.add("Stair", _custom("loft.stair", "1.0.0", deck=_ref(deck)))
    rows = part.rows()
    assert rows["Deck"]["feature"] == before  # frozen, byte for byte
    (warning,) = rows["Stair"]["plugin_warnings"]
    assert warning["code"] == "stair_deck_guard"
    offer = rows["Deck"]["plugin_update"]
    assert offer is not None and offer["to_version"] == "1.3.0" and offer["separate"]
    assert offer["adds"] == ["2 guard posts", "2 rails"]
    assert offer["relays"] == ["2 guard posts", "6 rails", "33 balusters"]
    assert offer["summary"].startswith(
        "Re-lays 2 guard posts, 6 rails and 33 balusters to open the guard at "
        "the stair. Adds 2 guard posts and 2 rails."
    )
    # Update all leaves it; on its own it opens the guard and the warning goes.
    response = part.update()
    assert response.status_code == 200, response.text
    (skipped,) = response.json()["skipped_updates"]
    assert (skipped["name"], skipped["reason"]) == ("Deck", "separate")
    alone = part.update([deck])
    assert alone.status_code == 200, alone.text
    assert _front_posts(part) == OPEN
    assert part.rows()["Stair"].get("plugin_warnings") is None


def test_an_unguarded_1_2_deck_updates_quietly(client: TestClient) -> None:
    part = _Part(client)
    deck = part.add("Deck", _custom("loft.deck", "1.2.0"))
    part.add("Stair", _custom("loft.stair", "1.0.0", deck=_ref(deck)))
    before = _expansion(part)
    offer = part.rows()["Deck"]["plugin_update"]
    assert offer is not None and offer["quiet"] and not offer["separate"]
    response = part.update()
    assert response.status_code == 200, response.text
    assert part.rows()["Deck"]["feature"]["params"]["plugin_version"] == "1.3.0"
    assert [{**m, "index": 0} for m in _expansion(part)] == [
        {**m, "index": 0} for m in before
    ]


def test_b1_keeps_its_inch_numbers(client: TestClient) -> None:
    """The opening's posts by hand: X 74.5..78 and 114..117.5 (mm on the
    wire, 25.4 an inch)."""
    part = _Part(client)
    deck = part.add("Deck", _custom("loft.deck", "1.3.0", **GUARD))
    part.add("Stair", _custom("loft.stair", "1.0.0", deck=_ref(deck)))
    by_id = {m["id"]: m for m in _expansion(part)}
    xs: dict[str, tuple[float, float]] = {}
    for m in by_id.values():
        if m["role"] != "guard_post" or m["name"] not in (
            "front/run/0/end",
            "front/run/1/0",
        ):
            continue
        sketch = by_id[m["feature"]["params"]["profile"]["feature_id"]]
        points = [e["start"]["x"] / IN for e in sketch["feature"]["params"]["entities"]]
        xs[m["name"]] = (round(min(points), 6), round(max(points), 6))
    assert xs == {"front/run/0/end": (74.5, 78.0), "front/run/1/0": (114.0, 117.5)}
