"""In-context links, documents side (ASM-A3-IN-CONTEXT).

A carriage (plate and block) is inserted into a stage next to a rail; the
plate's sketch projects the rail's hole in context:

- a valid link is stored and survives a re-read, and existing sketches load
  unchanged;
- a link naming a foreign or unknown assembly, a host occurrence that does not
  place this part, or a component that places another part is refused;
- a link back to the part itself, or one closing a loop through another part's
  link, is refused with ``in_context_cycle`` naming the chain;
- the write-back stores the resolved value without an undo step or a
  ``tree_version`` bump, skips a link that changed, and a stale save keeps the
  stored value;
- deleting the referenced component leaves the link stored, and the sketch can
  still be saved (geometry reports the error).
"""

import copy
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.assemblies import nested_occurrence_id
from loft_wire.in_context import InContextLink
from loft_wire.parts import PRINCIPAL_HEADER

OWNER = "6f3f6b64-0000-4000-8000-0000000000c7"
HEADERS = {PRINCIPAL_HEADER: OWNER}
OTHER = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000c8"}

EDGE = {
    "curve": "circle",
    "end_a": {"x": 189.25, "y": 0.0, "z": 8.0},
    "end_b": {"x": 189.25, "y": 0.0, "z": 8.0},
    "midpoint": {"x": 185.75, "y": 0.0, "z": 8.0},
    "length_mm": 10.995574287564276,
}


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=any_db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _post(client: TestClient, path: str, body: dict[str, Any]) -> Any:
    response = client.post(path, json=body, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()


def _version(client: TestClient, assembly: str) -> int:
    body = client.get(f"/api/v1/assemblies/{assembly}", headers=HEADERS).json()
    return int(body["doc_version"])


def _instance(client: TestClient, assembly: str, ref: str, kind: str) -> str:
    body = _post(
        client,
        f"/api/v1/assemblies/{assembly}/instances",
        {
            "expected_version": _version(client, assembly),
            "ref_document_id": ref,
            "ref_document_kind": kind,
            "name": "x",
        },
    )
    return str(body["instance"]["id"])


def _tree_version(client: TestClient, part: str) -> int:
    body = client.get(f"/api/v1/parts/{part}/features", headers=HEADERS).json()
    return int(body["tree_version"])


def _link(
    assembly: str, host: str, occurrence: str, part: str, resolved_y: float | None
) -> dict[str, Any]:
    link: dict[str, Any] = {
        "assembly_id": assembly,
        "host_occurrence_id": host,
        "occurrence_id": occurrence,
        "part_id": part,
        "edge": EDGE,
    }
    if resolved_y is not None:
        link["resolved"] = {
            "kind": "circle",
            "center": {"x": 12.5, "y": resolved_y, "z": -8.0},
            "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
            "radius": 1.75,
        }
    return link


def _sketch(entities: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "sketch",
        "version": 1,
        "params": {
            "plane": {"kind": "datum_plane", "plane": "XY"},
            "entities": entities,
            "constraints": [],
        },
    }


def _hole(link: dict[str, Any], entity_id: str = "p1") -> dict[str, Any]:
    return {
        "id": entity_id,
        "kind": "circle",
        "center": {"x": 12.5, "y": 40.0},
        "radius": 1.75,
        "projection": {"in_context": link},
    }


class Stage:
    def __init__(self, client: TestClient) -> None:
        self.rail = _post(client, "/api/v1/parts", {"name": "Rail"})["id"]
        self.plate = _post(client, "/api/v1/parts", {"name": "Plate"})["id"]
        self.block = _post(client, "/api/v1/parts", {"name": "Block"})["id"]
        self.carriage = _post(client, "/api/v1/assemblies", {"name": "Carriage"})["id"]
        self.plate_in_carriage = _instance(client, self.carriage, self.plate, "part")
        self.block_in_carriage = _instance(client, self.carriage, self.block, "part")
        self.stage = _post(client, "/api/v1/assemblies", {"name": "Stage"})["id"]
        self.rail_in_stage = _instance(client, self.stage, self.rail, "part")
        self.carriage_in_stage = _instance(
            client, self.stage, self.carriage, "assembly"
        )
        self.plate_occ = str(
            nested_occurrence_id(
                uuid.UUID(self.carriage_in_stage), uuid.UUID(self.plate_in_carriage)
            )
        )
        self.block_occ = str(
            nested_occurrence_id(
                uuid.UUID(self.carriage_in_stage), uuid.UUID(self.block_in_carriage)
            )
        )

    def link(self, resolved_y: float | None = 40.0) -> dict[str, Any]:
        return _link(
            self.stage, self.plate_occ, self.rail_in_stage, self.rail, resolved_y
        )


def _create(
    client: TestClient, part: str, feature: dict[str, Any], headers: Any = None
) -> Any:
    return client.post(
        f"/api/v1/parts/{part}/features",
        json={
            "name": "Sketch",
            "feature": feature,
            "expected_tree_version": _tree_version(client, part),
        },
        headers=headers or HEADERS,
    )


def _entities(client: TestClient, part: str, feature: str) -> list[dict[str, Any]]:
    body = client.get(
        f"/api/v1/parts/{part}/features/{feature}", headers=HEADERS
    ).json()
    return body["feature"]["params"]["entities"]


def test_a_link_is_stored_and_survives_a_reread(client: TestClient) -> None:
    stage = Stage(client)
    response = _create(client, stage.plate, _sketch([_hole(stage.link())]))
    assert response.status_code == 201, response.text
    feature = response.json()["feature"]["id"]
    (entity,) = _entities(client, stage.plate, feature)
    want = InContextLink.model_validate(stage.link()).model_dump(mode="json")
    assert entity["projection"] == {"in_context": want}
    # Its evaluation request carries it verbatim; no feature dependency.
    request = client.get(
        f"/api/v1/parts/{stage.plate}/evaluation-request", headers=HEADERS
    ).json()
    assert request["features"][0]["feature"]["params"]["entities"][0] == entity
    deps = client.get(
        f"/api/v1/parts/{stage.plate}/features/{feature}/dependents", headers=HEADERS
    )
    assert deps.status_code == 200, deps.text


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"assembly_id": str(uuid.uuid4())}, "in_context_assembly_unknown"),
        ({"host_occurrence_id": str(uuid.uuid4())}, "in_context_host_mismatch"),
        ({"occurrence_id": str(uuid.uuid4())}, "in_context_occurrence_unknown"),
        ({"part_id": str(uuid.uuid4())}, "in_context_part_mismatch"),
    ],
)
def test_a_bad_link_is_refused(
    client: TestClient, change: dict[str, str], code: str
) -> None:
    stage = Stage(client)
    response = _create(client, stage.plate, _sketch([_hole(stage.link() | change)]))
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == code


def test_a_foreign_assembly_is_unknown(client: TestClient) -> None:
    stage = Stage(client)
    theirs = client.post("/api/v1/assemblies", json={"name": "T"}, headers=OTHER)
    assert theirs.status_code == 201
    link = stage.link() | {"assembly_id": theirs.json()["id"]}
    response = _create(client, stage.plate, _sketch([_hole(link)]))
    assert response.json()["error"]["code"] == "in_context_assembly_unknown"


def test_a_host_must_place_this_part(client: TestClient) -> None:
    """The plate's link, written into the block (which is not at the plate's
    occurrence), is refused."""
    stage = Stage(client)
    response = _create(client, stage.block, _sketch([_hole(stage.link())]))
    assert response.json()["error"]["code"] == "in_context_host_mismatch"


def test_a_link_to_itself_or_through_a_loop_is_refused(client: TestClient) -> None:
    stage = Stage(client)
    to_self = _link(stage.stage, stage.plate_occ, stage.plate_occ, stage.plate, None)
    response = _create(client, stage.plate, _sketch([_hole(to_self)]))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "in_context_cycle"

    # Plate -> rail stored; then rail -> block -> plate closes the loop.
    assert _create(client, stage.plate, _sketch([_hole(stage.link())])).status_code
    block_to_plate = _link(
        stage.stage, stage.block_occ, stage.plate_occ, stage.plate, None
    )
    assert (
        _create(client, stage.block, _sketch([_hole(block_to_plate)])).status_code
        == 201
    )
    rail_to_block = _link(
        stage.stage, stage.rail_in_stage, stage.block_occ, stage.block, None
    )
    response = _create(client, stage.rail, _sketch([_hole(rail_to_block)]))
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "in_context_cycle"
    assert "Rail -> Block -> Plate -> Rail" in error["message"]
    assert error["details"]["chain"] == [
        stage.rail,
        stage.block,
        stage.plate,
        stage.rail,
    ]


def test_write_back_is_metadata_and_a_stale_save_keeps_it(
    client: TestClient,
) -> None:
    stage = Stage(client)
    created = _create(client, stage.plate, _sketch([_hole(stage.link())])).json()
    feature = created["feature"]["id"]
    version = _tree_version(client, stage.plate)
    item = {
        "feature_id": feature,
        "entity_id": "p1",
        "assembly_id": stage.stage,
        "host_occurrence_id": stage.plate_occ,
        "occurrence_id": stage.rail_in_stage,
        "part_id": stage.rail,
        "edge": EDGE,
        "resolved": stage.link(45.0)["resolved"],
    }
    response = client.post(
        f"/api/v1/parts/{stage.plate}/in-context/resolved",
        json={"items": [item, item | {"entity_id": "nope"}]},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"written": 1, "skipped": 1}
    assert _tree_version(client, stage.plate) == version
    (entity,) = _entities(client, stage.plate, feature)
    assert entity["projection"]["in_context"]["resolved"]["center"]["y"] == 45.0
    # Undo goes back past the sketch, not to the +-40 value.
    undo = client.post(
        f"/api/v1/parts/{stage.plate}/undo",
        json={"expected_tree_version": version},
        headers=HEADERS,
    )
    assert undo.status_code == 200, undo.text
    assert (
        client.get(f"/api/v1/parts/{stage.plate}/features", headers=HEADERS).json()[
            "features"
        ]
        == []
    )
    redo = client.post(
        f"/api/v1/parts/{stage.plate}/redo",
        json={"expected_tree_version": version + 1},
        headers=HEADERS,
    )
    assert redo.status_code == 200, redo.text
    (entity,) = _entities(client, stage.plate, feature)
    assert entity["projection"]["in_context"]["resolved"]["center"]["y"] == 45.0

    # A save from the tree read before the write-back (+-40) keeps +-45.
    stale = _hole(stage.link(40.0))
    stale["construction"] = True
    response = client.patch(
        f"/api/v1/parts/{stage.plate}/features/{feature}",
        json={
            "feature": _sketch([stale]),
            "expected_tree_version": _tree_version(client, stage.plate),
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    (entity,) = _entities(client, stage.plate, feature)
    assert entity["construction"] is True
    assert entity["projection"]["in_context"]["resolved"]["center"]["y"] == 45.0

    # A link that changed (another component) is not written.
    moved = copy.deepcopy(item) | {"occurrence_id": str(uuid.uuid4())}
    response = client.post(
        f"/api/v1/parts/{stage.plate}/in-context/resolved",
        json={"items": [moved]},
        headers=HEADERS,
    )
    assert response.json() == {"written": 0, "skipped": 1}
    # Nor one resolved for ANOTHER edge of the same component (the entity was
    # re-projected while an older evaluation was in flight).
    other_edge = EDGE | {
        "end_a": {"x": 26.75, "y": 0.0, "z": 8.0},
        "end_b": {"x": 26.75, "y": 0.0, "z": 8.0},
        "midpoint": {"x": 23.25, "y": 0.0, "z": 8.0},
    }
    stale = copy.deepcopy(item) | {
        "edge": other_edge,
        "resolved": stage.link(99.0)["resolved"],
    }
    response = client.post(
        f"/api/v1/parts/{stage.plate}/in-context/resolved",
        json={"items": [stale]},
        headers=HEADERS,
    )
    assert response.json() == {"written": 0, "skipped": 1}
    (entity,) = _entities(client, stage.plate, feature)
    assert entity["projection"]["in_context"]["resolved"]["center"]["y"] == 45.0
    # Someone else's part is a 404.
    response = client.post(
        f"/api/v1/parts/{stage.plate}/in-context/resolved",
        json={"items": [item]},
        headers=OTHER,
    )
    assert response.status_code == 404


def test_deleting_the_component_keeps_the_link_and_the_sketch_editable(
    client: TestClient,
) -> None:
    stage = Stage(client)
    created = _create(client, stage.plate, _sketch([_hole(stage.link())])).json()
    feature = created["feature"]["id"]
    deleted = client.delete(
        f"/api/v1/assemblies/{stage.stage}/instances/{stage.rail_in_stage}",
        params={"expected_version": _version(client, stage.stage)},
        headers=HEADERS,
    )
    assert deleted.status_code in (200, 204), deleted.text
    (entity,) = _entities(client, stage.plate, feature)
    assert entity["projection"]["in_context"]["occurrence_id"] == stage.rail_in_stage
    # The unchanged link is not re-checked: the sketch still saves.
    renamed = _hole(stage.link())
    renamed["construction"] = True
    response = client.patch(
        f"/api/v1/parts/{stage.plate}/features/{feature}",
        json={
            "feature": _sketch([renamed]),
            "expected_tree_version": _tree_version(client, stage.plate),
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    # Break link (the projection dropped) saves too, keeping the circle.
    broken = {k: v for k, v in renamed.items() if k != "projection"}
    response = client.patch(
        f"/api/v1/parts/{stage.plate}/features/{feature}",
        json={
            "feature": _sketch([broken]),
            "expected_tree_version": _tree_version(client, stage.plate),
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    (entity,) = _entities(client, stage.plate, feature)
    assert "projection" not in entity
    assert entity["center"] == {"x": 12.5, "y": 40.0}
