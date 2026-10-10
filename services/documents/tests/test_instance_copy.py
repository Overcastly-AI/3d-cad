"""documents ``POST /assemblies/{id}/instances/{instance_id}/copy`` (Fusion Copy).

Runs against SQLite (always) and the real migrated scratch PostgreSQL (see
conftest.py). Helpers are self-contained: test modules cannot import each
other under ``--import-mode=importlib``.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from documents import instance_copy
from documents.instance_copy import copy_instance_name
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.parts import PRINCIPAL_HEADER

OWNER = "6f3f6b64-0000-4000-8000-0000000000c1"
INTRUDER = "6f3f6b64-0000-4000-8000-0000000000c2"

#: Graph fields that legitimately change across undo/redo.
VOLATILE_GRAPH_FIELDS = frozenset({"doc_version", "can_undo", "can_redo"})
VOLATILE_HEADER_FIELDS = frozenset({"doc_version", "updated_at"})

TILTED: dict[str, Any] = {
    "position": {"x": 5.0, "y": -3.0, "z": 7.5},
    "orientation": {
        "x": 0.0,
        "y": 0.0,
        "z": 0.7071067811865476,
        "w": 0.7071067811865476,
    },
}


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=any_db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


def _create_part(client: TestClient, name: str, owner: str = OWNER) -> str:
    response = client.post(
        "/api/v1/parts", json={"name": name}, headers=_headers(owner)
    )
    assert response.status_code == 201, response.text
    part_id: str = response.json()["id"]
    return part_id


def _create_assembly(client: TestClient, name: str, owner: str = OWNER) -> str:
    response = client.post(
        "/api/v1/assemblies", json={"name": name}, headers=_headers(owner)
    )
    assert response.status_code == 201, response.text
    assembly_id: str = response.json()["id"]
    return assembly_id


def _graph(client: TestClient, assembly_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/assemblies/{assembly_id}", headers=_headers())
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _version(client: TestClient, assembly_id: str) -> int:
    version: int = _graph(client, assembly_id)["doc_version"]
    return version


def _add_instance(
    client: TestClient,
    assembly_id: str,
    part_id: str,
    name: str,
    *,
    grounded: bool = False,
    placement: dict[str, Any] | None = None,
    owner: str = OWNER,
) -> str:
    payload: dict[str, Any] = {
        "expected_version": _version(client, assembly_id) if owner == OWNER else 0,
        "ref_document_id": part_id,
        "ref_document_kind": "part",
        "name": name,
        "grounded": grounded,
    }
    if placement is not None:
        payload["placement"] = placement
    response = client.post(
        f"/api/v1/assemblies/{assembly_id}/instances",
        json=payload,
        headers=_headers(owner),
    )
    assert response.status_code == 201, response.text
    instance_id: str = response.json()["instance"]["id"]
    return instance_id


def _copy(
    client: TestClient,
    assembly_id: str,
    instance_id: str,
    *,
    expected_version: int | None = None,
    offset: Any = None,
    owner: str = OWNER,
) -> Any:
    body: dict[str, Any] = {
        "expected_version": (
            _version(client, assembly_id)
            if expected_version is None
            else expected_version
        )
    }
    if offset is not None:
        body["offset"] = offset
    return client.post(
        f"/api/v1/assemblies/{assembly_id}/instances/{instance_id}/copy",
        json=body,
        headers=_headers(owner),
    )


def _comparable(graph: dict[str, Any]) -> dict[str, Any]:
    stripped = {k: v for k, v in graph.items() if k not in VOLATILE_GRAPH_FIELDS}
    stripped["assembly"] = {
        k: v for k, v in graph["assembly"].items() if k not in VOLATILE_HEADER_FIELDS
    }
    return stripped


def _plate_assembly(client: TestClient) -> tuple[str, str, str, str]:
    """A grounded "Hole plate <1>" locked to a "Bracket <1>"."""
    part = _create_part(client, "Hole plate")
    bracket_part = _create_part(client, "Bracket")
    assembly = _create_assembly(client, "Copy rig")
    plate = _add_instance(
        client, assembly, part, "Hole plate <1>", grounded=True, placement=TILTED
    )
    bracket = _add_instance(client, assembly, bracket_part, "Bracket <1>")
    response = client.post(
        f"/api/v1/assemblies/{assembly}/mates",
        json={
            "expected_version": _version(client, assembly),
            "mate": {"type": "lock", "a_instance_id": plate, "b_instance_id": bracket},
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    return assembly, part, plate, bracket


# --- create -----------------------------------------------------------------------


def test_copy_creates_a_free_offset_instance_of_the_same_part(
    client: TestClient,
) -> None:
    assembly, part, plate, _ = _plate_assembly(client)
    before = _graph(client, assembly)

    response = _copy(client, assembly, plate)

    assert response.status_code == 201, response.text
    body = response.json()
    copy = body["instance"]
    assert body["doc_version"] == before["doc_version"] + 1
    assert copy["id"] != plate
    assert copy["assembly_id"] == assembly
    assert copy["ref_document_id"] == part
    assert copy["ref_document_kind"] == "part"
    assert copy["ref_pinned_version"] is None
    assert copy["name"] == "Hole plate <2>"
    # The source is grounded; a copy never is.
    assert copy["grounded"] is False
    # +20 mm along X by default; orientation kept verbatim.
    assert copy["placement"] == {
        "position": {"x": 25.0, "y": -3.0, "z": 7.5},
        "orientation": TILTED["orientation"],
    }
    assert copy["order_index"] == 2

    after = _graph(client, assembly)
    assert after["doc_version"] == body["doc_version"]
    assert [row["id"] for row in after["instances"]] == [
        *(row["id"] for row in before["instances"]),
        copy["id"],
    ]
    # Mates are NOT copied: the source's lock is the only mate, untouched.
    assert after["mates"] == before["mates"]
    # The source is untouched.
    assert after["instances"][:2] == before["instances"]


def test_copy_applies_an_explicit_offset(client: TestClient) -> None:
    assembly, _, plate, _ = _plate_assembly(client)

    response = _copy(client, assembly, plate, offset=[-10.0, 0.5, 100.0])

    assert response.status_code == 201, response.text
    position = response.json()["instance"]["placement"]["position"]
    assert position == {"x": -5.0, "y": -2.5, "z": 107.5}


@pytest.mark.parametrize(
    "offset",
    [
        [1.0, 2.0],
        [1.0, 2.0, 3.0, 4.0],
        [1e9, 0.0, 0.0],
        [0.0, -100_000.5, 0.0],
        {"x": 1.0, "y": 0.0, "z": 0.0},
        "20,0,0",
    ],
)
def test_bad_offset_is_422_and_writes_nothing(client: TestClient, offset: Any) -> None:
    assembly, _, plate, _ = _plate_assembly(client)
    before = _graph(client, assembly)

    response = _copy(client, assembly, plate, offset=offset)

    assert response.status_code == 422, response.text
    assert _graph(client, assembly) == before


def test_non_finite_offset_is_422(client: TestClient) -> None:
    assembly, _, plate, _ = _plate_assembly(client)
    version = _version(client, assembly)
    response = client.post(
        f"/api/v1/assemblies/{assembly}/instances/{plate}/copy",
        content=f'{{"expected_version": {version}, "offset": [NaN, 0, 0]}}',
        headers={**_headers(), "content-type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert _version(client, assembly) == version


def test_copy_of_a_sub_assembly_instance(client: TestClient) -> None:
    child = _create_assembly(client, "Hinge")
    parent = _create_assembly(client, "Door")
    response = client.post(
        f"/api/v1/assemblies/{parent}/instances",
        json={
            "expected_version": 0,
            "ref_document_id": child,
            "ref_document_kind": "assembly",
            "name": "Hinge <1>",
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    source = response.json()["instance"]["id"]

    copied = _copy(client, parent, source)

    assert copied.status_code == 201, copied.text
    copy = copied.json()["instance"]
    assert (copy["ref_document_id"], copy["ref_document_kind"]) == (child, "assembly")
    assert copy["name"] == "Hinge <2>"


def test_instance_limit_is_enforced(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assembly, _, plate, _ = _plate_assembly(client)
    monkeypatch.setattr(instance_copy, "MAX_ASSEMBLY_INSTANCES", 2)
    before = _graph(client, assembly)

    response = _copy(client, assembly, plate)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "instance_limit_exceeded"
    assert _graph(client, assembly) == before


# --- naming -----------------------------------------------------------------------


def test_names_stay_unique_across_several_copies(client: TestClient) -> None:
    assembly, _, plate, bracket = _plate_assembly(client)

    names = [
        _copy(client, assembly, plate).json()["instance"]["name"] for _ in range(3)
    ]
    assert names == ["Hole plate <2>", "Hole plate <3>", "Hole plate <4>"]

    # Copying a copy continues the same sequence, not the copy's own number.
    third = _graph(client, assembly)["instances"][3]
    assert third["name"] == "Hole plate <3>"
    assert _copy(client, assembly, third["id"]).json()["instance"]["name"] == (
        "Hole plate <5>"
    )
    # A different base keeps its own sequence.
    assert _copy(client, assembly, bracket).json()["instance"]["name"] == "Bracket <2>"

    all_names = [row["name"] for row in _graph(client, assembly)["instances"]]
    assert len(all_names) == len(set(all_names)) == 7


def test_copy_numbers_after_a_gap_and_after_deletes(client: TestClient) -> None:
    part = _create_part(client, "Bolt")
    assembly = _create_assembly(client, "Bolted")
    first = _add_instance(client, assembly, part, "Bolt <1>")
    _add_instance(client, assembly, part, "Bolt <7>")

    assert _copy(client, assembly, first).json()["instance"]["name"] == "Bolt <8>"


@pytest.mark.parametrize(
    ("source", "taken", "expected"),
    [
        ("Hole plate <1>", ["Hole plate <1>"], "Hole plate <2>"),
        ("Hole plate <2>", ["Hole plate <1>", "Hole plate <2>"], "Hole plate <3>"),
        # A renamed, unnumbered instance counts as <1>.
        ("Left rail", ["Left rail"], "Left rail <2>"),
        # Only an exact "<base> <n>" counts toward the sequence.
        ("Nut <1>", ["Nut <1>", "Nut <x>", "Nut<4>", "Nuts <9>"], "Nut <2>"),
        ("Pin <01>", ["Pin <01>"], "Pin <01> <2>"),
        # A base that itself ends in a number keeps it.
        ("M6 <3>", ["M6 <3>", "M6 <10>"], "M6 <11>"),
        ("<1> <1>", ["<1> <1>"], "<1> <2>"),
    ],
)
def test_copy_instance_name(source: str, taken: list[str], expected: str) -> None:
    assert copy_instance_name(source, taken) == expected


def test_copy_instance_name_stays_within_the_length_bound() -> None:
    source = "x" * 196 + " <9>"
    taken = [source, "x" * 195 + " <10>"]

    name = copy_instance_name(source, taken, max_length=200)

    # The base is shortened to fit " <10>", which is taken, so the number climbs.
    assert name == "x" * 195 + " <11>"


# --- undo / redo --------------------------------------------------------------------


def test_copy_is_one_undo_step_restored_verbatim(client: TestClient) -> None:
    assembly, _, plate, _ = _plate_assembly(client)
    before = _graph(client, assembly)

    copied = _copy(client, assembly, plate)
    assert copied.status_code == 201, copied.text
    after_copy = _graph(client, assembly)
    assert after_copy["can_undo"] is True

    undo = client.post(
        f"/api/v1/assemblies/{assembly}/undo",
        json={"expected_version": after_copy["doc_version"]},
        headers=_headers(),
    )
    assert undo.status_code == 200, undo.text
    undone = undo.json()
    assert _comparable(undone) == _comparable(before)
    assert undone["can_redo"] is True

    redo = client.post(
        f"/api/v1/assemblies/{assembly}/redo",
        json={"expected_version": undone["doc_version"]},
        headers=_headers(),
    )
    assert redo.status_code == 200, redo.text
    # Redo restores the copy with its id, name, placement and timestamps.
    assert _comparable(redo.json()) == _comparable(after_copy)


# --- concurrency + authz ------------------------------------------------------------


def test_stale_version_is_refused_and_writes_nothing(client: TestClient) -> None:
    assembly, _, plate, _ = _plate_assembly(client)
    before = _graph(client, assembly)

    response = _copy(
        client, assembly, plate, expected_version=before["doc_version"] - 1
    )

    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "stale_assembly_version"
    assert error["details"] == {
        "provided": before["doc_version"] - 1,
        "current": before["doc_version"],
    }
    assert _graph(client, assembly) == before


def test_another_users_assembly_is_404(client: TestClient) -> None:
    assembly, _, plate, _ = _plate_assembly(client)
    before = _graph(client, assembly)

    response = _copy(
        client,
        assembly,
        plate,
        expected_version=before["doc_version"],
        owner=INTRUDER,
    )

    assert response.status_code == 404, response.text
    assert _graph(client, assembly) == before


def test_instance_of_another_assembly_is_404(client: TestClient) -> None:
    assembly, part, _, _ = _plate_assembly(client)
    other = _create_assembly(client, "Elsewhere")
    foreign = _add_instance(client, other, part, "Hole plate <1>")
    before = _graph(client, assembly)
    other_before = _graph(client, other)

    response = _copy(client, assembly, foreign)

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "instance_not_found"
    assert _graph(client, assembly) == before
    assert _graph(client, other) == other_before


def test_unknown_instance_is_404(client: TestClient) -> None:
    assembly, _, _, _ = _plate_assembly(client)

    response = _copy(client, assembly, "00000000-0000-4000-8000-000000000000")

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "instance_not_found"


def test_another_users_instance_in_their_assembly_is_404(client: TestClient) -> None:
    """The intruder addresses the owner's instance through their OWN assembly."""
    _, _, plate, _ = _plate_assembly(client)
    theirs = _create_assembly(client, "Intruder rig", owner=INTRUDER)

    response = _copy(client, theirs, plate, expected_version=0, owner=INTRUDER)

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "instance_not_found"
