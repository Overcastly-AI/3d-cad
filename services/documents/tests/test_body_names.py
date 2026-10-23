"""Body names (BODY-NAMES): a member body is named after its feature and
member, a user's rename is stored on the part and wins, and both reach
``GET /parts/{id}/body-names`` (what a STEP export names its solids by).

The B1 deck fixture plugin (``loft_plugins.testing_deck``) stands in for the
building plugins: one custom feature, 46 members, titled from its manifest.
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
from loft_wire.body_names import BODY_NAME_MAX_LENGTH, MAX_BODY_NAMES, PartBodyNames
from loft_wire.parts import PRINCIPAL_HEADER, PartResponse

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000d7"}
OTHER = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000d8"}

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
        json={"name": "Back deck", "feature": DECK, "expected_tree_version": 0},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return part_id


def _names(client: TestClient, part_id: str) -> dict[str, str]:
    response = client.get(f"/api/v1/parts/{part_id}/body-names", headers=HEADERS)
    assert response.status_code == 200, response.text
    bodies = PartBodyNames.model_validate_json(response.content).bodies
    return {str(body.base_feature_id): body.name for body in bodies}


def _part(client: TestClient, part_id: str) -> PartResponse:
    response = client.get(f"/api/v1/parts/{part_id}", headers=HEADERS)
    assert response.status_code == 200, response.text
    return PartResponse.model_validate_json(response.content)


def _rename(
    client: TestClient, part_id: str, names: list[dict[str, str]]
) -> PartResponse:
    version = _part(client, part_id).tree_version
    response = client.patch(
        f"/api/v1/parts/{part_id}",
        json={"expected_tree_version": version, "body_names": names},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    return PartResponse.model_validate_json(response.content)


def _member_ids(client: TestClient, part_id: str) -> list[tuple[str, str, int]]:
    """(id, role, index) of every stored member, in expansion order."""
    tree = client.get(f"/api/v1/parts/{part_id}/features", headers=HEADERS).json()
    return [
        (m["id"], m["role"], m["index"])
        for m in tree["features"][0]["feature"]["params"]["expansion"]
    ]


def test_every_member_is_named_after_its_feature_and_member(
    client: TestClient, registry: list[PluginRegistry]
) -> None:
    del registry
    part_id = _deck_part(client)
    names = _names(client, part_id)
    members = _member_ids(client, part_id)
    # Every member is named; geometry names the bodies among them.
    assert set(names) == {member_id for member_id, _, _ in members}
    by_role: dict[str, list[str]] = {}
    for member_id, role, _ in members:
        by_role.setdefault(role, []).append(names[member_id])
    # A role of one member has no number; the others count from 1 in order.
    assert by_role["ledger"] == ["Back deck · Ledger"]
    assert by_role["joist"][:3] == [
        "Back deck · Joist 1",
        "Back deck · Joist 2",
        "Back deck · Joist 3",
    ]
    assert by_role["joist"][-1] == "Back deck · Joist 13"
    assert "Body" not in " ".join(names.values())


def test_a_rename_wins_persists_and_leaves_the_evaluate_current(
    client: TestClient, registry: list[PluginRegistry]
) -> None:
    del registry
    part_id = _deck_part(client)
    stud = _member_ids(client, part_id)[5][0]
    record = client.put(
        f"/api/v1/parts/{part_id}/last-evaluation",
        json={"tree_version": _part(client, part_id).tree_version, "status": "ok"},
        headers=HEADERS,
    )
    assert record.status_code in (200, 204), record.text
    renamed = _rename(
        client, part_id, [{"base_feature_id": stud, "name": "  Corner joist "}]
    )
    assert [(str(b.base_feature_id), b.name) for b in renamed.body_names] == [
        (stud, "Corner joist")
    ]
    # Display metadata: the recorded evaluate follows the version bump.
    assert renamed.eval_state == "ok"
    assert _part(client, part_id).body_names == renamed.body_names
    assert _names(client, part_id)[stud] == "Corner joist"
    # An empty list clears every rename, back to the member's own name.
    cleared = _rename(client, part_id, [])
    assert cleared.body_names == []
    assert _names(client, part_id)[stud].startswith("Back deck · ")


def test_a_rename_of_a_body_the_tree_no_longer_makes_is_inert(
    client: TestClient, registry: list[PluginRegistry]
) -> None:
    del registry
    part_id = _deck_part(client)
    gone = str(uuid.uuid4())
    _rename(client, part_id, [{"base_feature_id": gone, "name": "Old post"}])
    assert gone not in _names(client, part_id)
    assert len(_names(client, part_id)) == len(_member_ids(client, part_id))


@pytest.mark.parametrize(
    "names",
    [
        [{"base_feature_id": "6f3f6b64-0000-4000-8000-0000000000e1", "name": "a"}] * 2,
        [{"base_feature_id": "6f3f6b64-0000-4000-8000-0000000000e1", "name": " "}],
        [
            {
                "base_feature_id": "6f3f6b64-0000-4000-8000-0000000000e1",
                "name": "x" * (BODY_NAME_MAX_LENGTH + 1),
            }
        ],
        [
            {"base_feature_id": str(uuid.UUID(int=n)), "name": "a"}
            for n in range(MAX_BODY_NAMES + 1)
        ],
    ],
    ids=["duplicate", "blank", "too-long", "too-many"],
)
def test_a_bad_rename_is_refused(
    client: TestClient, registry: list[PluginRegistry], names: list[dict[str, str]]
) -> None:
    del registry
    part_id = _deck_part(client)
    response = client.patch(
        f"/api/v1/parts/{part_id}",
        json={"expected_tree_version": 1, "body_names": names},
        headers=HEADERS,
    )
    assert response.status_code == 422, response.text
    assert _part(client, part_id).body_names == []


def test_another_owners_part_is_a_404(
    client: TestClient, registry: list[PluginRegistry]
) -> None:
    del registry
    part_id = _deck_part(client)
    assert (
        client.get(f"/api/v1/parts/{part_id}/body-names", headers=OTHER).status_code
        == 404
    )
    response = client.patch(
        f"/api/v1/parts/{part_id}",
        json={
            "expected_tree_version": 1,
            "body_names": [{"base_feature_id": str(uuid.uuid4()), "name": "x"}],
        },
        headers=OTHER,
    )
    assert response.status_code == 404


def test_a_duplicate_and_a_loft_round_trip_keep_the_renames(
    client: TestClient, registry: list[PluginRegistry]
) -> None:
    del registry
    part_id = _deck_part(client)
    stud = _member_ids(client, part_id)[5][0]
    _rename(client, part_id, [{"base_feature_id": stud, "name": "Corner joist"}])

    copy = client.post(f"/api/v1/parts/{part_id}/duplicate", headers=HEADERS)
    assert copy.status_code == 201, copy.text
    copy_id = copy.json()["id"]
    copied = _part(client, copy_id).body_names
    assert [body.name for body in copied] == ["Corner joist"]
    # Keyed by the COPY's member, which is the copy's sixth member.
    assert str(copied[0].base_feature_id) == _member_ids(client, copy_id)[5][0]
    assert str(copied[0].base_feature_id) != stud

    tree = client.get(f"/api/v1/parts/{part_id}/loft-tree", headers=HEADERS)
    assert tree.status_code == 200, tree.text
    assert tree.json()["body_names"] == [
        {"base_feature_id": stud, "name": "Corner joist"}
    ]
