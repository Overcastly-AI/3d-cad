"""``GET /parts/{id}/cut-list-request`` (CUT-LIST): the evaluation request
plus each plugin member's metadata, from the expansion geometry builds.

The B1 deck fixture plugin (``loft_plugins.testing_deck``) stands in for the
DECK plugin: one custom feature, 46 members with metadata, titled from its
manifest; without the plugin (a read-only part) the role names them.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents import custom_features
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_plugins import PluginRegistry
from loft_plugins.testing_deck import DECK_B1
from loft_wire.cut_list import CutListPartRequest
from loft_wire.parts import PRINCIPAL_HEADER

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000c7"}

DECK: dict[str, Any] = {
    "type": "custom",
    "version": 1,
    "params": {"plugin_id": "test.deck_b1", "plugin_version": "1.0.0", "inputs": {}},
}


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[PluginRegistry]]:
    holder = [PluginRegistry([DECK_B1])]

    class Proxy(PluginRegistry):
        def __getattribute__(self, name: str) -> Any:
            return getattr(holder[0], name)

    monkeypatch.setattr(custom_features, "PLUGINS", Proxy())
    yield holder


def _deck_part(client: TestClient) -> str:
    response = client.post(
        "/api/v1/parts",
        json={"name": f"Deck {uuid.uuid4()}", "length_unit": "in"},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    part_id = str(response.json()["id"])
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": "Deck", "feature": DECK, "expected_tree_version": 0},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return part_id


def _read(client: TestClient, part_id: str) -> CutListPartRequest:
    response = client.get(f"/api/v1/parts/{part_id}/cut-list-request", headers=HEADERS)
    assert response.status_code == 200, response.text
    return CutListPartRequest.model_validate_json(response.content)


def test_members_carry_titles_and_metadata_of_the_sent_expansion(
    client: TestClient, registry: list[PluginRegistry]
) -> None:
    del registry
    part_id = _deck_part(client)
    request = _read(client, part_id)
    assert request.length_unit == "in"
    titles = [m.title for m in request.members]
    roles = ("Ledger", "Rim", "Beam", "Joist", "Post", "Deck")
    assert [titles.count(t) for t in roles] == [1, 1, 2, 13, 3, 26]
    sent = {entry.id for entry in request.evaluation.features}
    assert {m.feature_id for m in request.members} <= sent
    evaluation = client.get(
        f"/api/v1/parts/{part_id}/evaluation-request", headers=HEADERS
    ).json()
    assert request.evaluation.model_dump(mode="json") == evaluation
    assert {m.metadata.profile for m in request.members} == {"2x10", "6x6", "5/4x6"}


def test_a_read_only_part_titles_members_by_role(
    client: TestClient, registry: list[PluginRegistry]
) -> None:
    part_id = _deck_part(client)
    registry[0] = PluginRegistry()  # the plugin is gone: stored expansion rebuilds
    request = _read(client, part_id)
    assert {m.title for m in request.members} == {
        "Ledger",
        "Rim",
        "Beam",
        "Joist",
        "Post",
        "Deck",
    }
    assert len(request.members) == 46


def test_a_foreign_part_is_a_404(
    client: TestClient, registry: list[PluginRegistry]
) -> None:
    del registry
    part_id = _deck_part(client)
    other = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000c8"}
    response = client.get(f"/api/v1/parts/{part_id}/cut-list-request", headers=other)
    assert response.status_code == 404
