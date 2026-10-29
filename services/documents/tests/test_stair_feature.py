"""STAIRS through documents: a Stair on B1's rim, and a free stair.

B1 (docs/reference-parts/buildings.md) is one ``loft.deck`` 1.2.0; a
``loft.stair`` 1.0.0 picks it and hangs from its rim. The deck is stored and
built exactly as before (the stair reads its inputs and never changes it);
editing the deck's height re-lays the stair in the same write; the cut-list
request lists the stair's members under its plugin; a layout that breaks IRC
R311.7 is refused on write with the section named; advice comes back as the
stair's ``plugin_warnings``.
"""

import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.cut_list import CutListPartRequest

sys.path.insert(0, str(Path(__file__).parent))
from test_slab_feature import (  # pyright: ignore[reportPrivateUsage]
    HEADERS,
    IN,
    _custom,  # pyright: ignore[reportPrivateUsage]
    _Part,  # pyright: ignore[reportPrivateUsage]
    _ref,  # pyright: ignore[reportPrivateUsage]
)


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _b1(client: TestClient, **stair: Any) -> tuple[_Part, str, str]:
    part = _Part(client)
    deck = part.add("Deck", _custom("loft.deck", "1.2.0"))
    stair_id = part.add(
        "Stair", _custom("loft.stair", "1.0.0", deck=_ref(deck), **stair)
    )
    return part, deck, stair_id


def _cut_list_request(client: TestClient, part: _Part) -> CutListPartRequest:
    response = client.get(f"/api/v1/parts/{part.id}/cut-list-request", headers=HEADERS)
    assert response.status_code == 200, response.text
    return CutListPartRequest.model_validate_json(response.content)


def _rows(client: TestClient, part: _Part) -> dict[str, Any]:
    response = client.get(f"/api/v1/parts/{part.id}/features", headers=HEADERS)
    assert response.status_code == 200, response.text
    return {f["name"]: f for f in response.json()["features"]}


def _roles(request: CutListPartRequest) -> Counter[str]:
    return Counter(m.role for m in request.members if m.plugin_id == "loft.stair")


def test_a_stair_hangs_on_b1s_rim_and_leaves_the_deck_alone(
    client: TestClient,
) -> None:
    part = _Part(client)
    deck = part.add("Deck", _custom("loft.deck", "1.2.0"))
    before = part.stored()["Deck"]
    part.add("Stair", _custom("loft.stair", "1.0.0", deck=_ref(deck)))
    # The deck's stored feature, its expansion included, is byte-identical.
    assert part.stored()["Deck"] == before
    request = _cut_list_request(client, part)
    assert _roles(request) == Counter(
        {"tread": 6, "stringer": 3, "handrail_post": 2, "handrail": 1}
    )
    titles = {m.role: m.title for m in request.members if m.plugin_id == "loft.stair"}
    assert titles["stringer"] == "Stringer"
    assert all(e.input_error is None for e in part.request().features)
    assert _rows(client, part)["Stair"].get("plugin_warnings") is None


def test_raising_the_deck_re_lays_its_stair(client: TestClient) -> None:
    part, deck, _ = _b1(client)
    part.edit(deck, _custom("loft.deck", "1.2.0", height_mm=36 * IN))
    roles = _roles(_cut_list_request(client, part))
    # 5 risers of 7.2: 4 treads of two boards.
    assert roles["tread"] == 8 and roles["stringer"] == 3


def test_a_layout_that_breaks_r311_7_is_refused_on_write(client: TestClient) -> None:
    part = _Part(client)
    deck = part.add("Deck", _custom("loft.deck", "1.2.0"))
    response = client.post(
        f"/api/v1/parts/{part.id}/features",
        json={
            "name": "Stair",
            "feature": _custom("loft.stair", "1.0.0", deck=_ref(deck), handrail="none"),
            "expected_tree_version": part.version,
        },
        headers=HEADERS,
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "plugin_input_unsupported"
    assert error["message"].startswith("IRC R311.7.8:")


def test_a_free_stair_warns_of_its_throat_and_open_sides(client: TestClient) -> None:
    part = _Part(client)
    part.add(
        "Stair",
        _custom("loft.stair", "1.0.0", rise_mm=107.09375 * IN, risers="closed"),
    )
    warnings = _rows(client, part)["Stair"]["plugin_warnings"]
    assert [w["code"] for w in warnings] == [
        "stair_throat_thin",
        "stair_stringer_span",
        "stair_guard_required",
    ]
    assert "4.9697 in" in warnings[0]["message"]
    assert "6'-0\"" in warnings[1]["message"]
    assert "R312.1.1" in warnings[2]["message"]
    assert all(w["update_to"] is None for w in warnings)
    assert _roles(_cut_list_request(client, part))["riser"] == 13


def test_a_guarded_deck_warns_at_its_stair(client: TestClient) -> None:
    part = _Part(client)
    deck = part.add("Deck", _custom("loft.deck", "1.2.0", guard="open_sides"))
    part.add("Stair", _custom("loft.stair", "1.0.0", deck=_ref(deck)))
    (warning,) = _rows(client, part)["Stair"]["plugin_warnings"]
    assert warning["code"] == "stair_deck_guard"
