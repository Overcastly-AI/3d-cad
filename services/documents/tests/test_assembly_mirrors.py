"""Component mirrors, documents side (ASM-MIRROR-COMPONENT).

- A mirror is ONE entry of the assembly: create, replace and delete it, each a
  version bump and an undo step; the graph and the evaluation request carry
  it; an assembly without mirrors reads exactly as before.
- Seeds must be instances of the assembly, an opposite hand a part seed, and
  a plane face a part of the assembly (nested parts by occurrence id).
- The BOM: a mirrored copy counts on its seed's line (the crank arms are 2), an
  opposite hand is a line of its own (1 + 1 opposite hand), at every level and
  on a drawing's parts list.
- The instance bound counts twins, for the assembly and every one above it.
- Deleting a seed or the plane's instance cascades; duplicate re-maps ids.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.assemblies import EvaluateAssemblyRequest, nested_occurrence_id
from loft_wire.parts import PRINCIPAL_HEADER

OWNER = "6f3f6b64-0000-4000-8000-0000000000c8"
HEADERS = {PRINCIPAL_HEADER: OWNER}

#: A planar face signature (the geometry is not evaluated here).
FACE = {
    "normal": {"x": 1.0, "y": 0.0, "z": 0.0},
    "centroid": {"x": 60.0, "y": 5.0, "z": 5.0},
    "area_mm2": 100.0,
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


def _graph(client: TestClient, assembly: str) -> Any:
    return client.get(f"/api/v1/assemblies/{assembly}", headers=HEADERS).json()


def _version(client: TestClient, assembly: str) -> int:
    return int(_graph(client, assembly)["doc_version"])


def _part(client: TestClient, name: str) -> str:
    return str(_post(client, "/api/v1/parts", {"name": name})["id"])


def _assembly(client: TestClient, name: str) -> str:
    return str(_post(client, "/api/v1/assemblies", {"name": name})["id"])


def _instance(
    client: TestClient, assembly: str, ref: str, name: str, kind: str = "part"
) -> str:
    body = {
        "expected_version": _version(client, assembly),
        "ref_document_id": ref,
        "ref_document_kind": kind,
        "name": name,
    }
    path = f"/api/v1/assemblies/{assembly}/instances"
    return str(_post(client, path, body)["instance"]["id"])


def _mirror(
    seeds: list[str],
    opposite: list[str] | None = None,
    face_on: str | None = None,
) -> dict[str, Any]:
    plane: dict[str, Any] = (
        {"kind": "origin_plane", "plane": "yz"}
        if face_on is None
        else {"kind": "face", "instance_id": face_on, "signature": FACE}
    )
    return {
        "seed_instance_ids": seeds,
        "plane": plane,
        "opposite_hand_instance_ids": opposite or [],
    }


def _create(client: TestClient, assembly: str, mirror: dict[str, Any]) -> Any:
    return client.post(
        f"/api/v1/assemblies/{assembly}/mirrors",
        json={"expected_version": _version(client, assembly), "mirror": mirror},
        headers=HEADERS,
    )


def _add(client: TestClient, assembly: str, mirror: dict[str, Any]) -> str:
    response = _create(client, assembly, mirror)
    assert response.status_code == 201, response.text
    return str(response.json()["mirror"]["id"])


def _bom(client: TestClient, assembly: str) -> Any:
    response = client.get(f"/api/v1/assemblies/{assembly}/bom", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def _lines(lines: list[dict[str, Any]]) -> list[tuple[str, int, bool]]:
    return [
        (line["name"], line["quantity"], line.get("opposite_hand", False))
        for line in lines
    ]


def test_a_mirror_is_one_entry_and_one_undo_step(client: TestClient) -> None:
    arm = _part(client, "Crank arm")
    bike = _assembly(client, "Crankset")
    right = _instance(client, bike, arm, "Crank arm <1>")
    assert "mirrors" not in _graph(client, bike)  # reads exactly as before
    before = _version(client, bike)
    mirror_id = _add(client, bike, _mirror([right]))
    graph = _graph(client, bike)
    assert graph["doc_version"] == before + 1
    (stored,) = graph["mirrors"]
    assert stored["id"] == mirror_id
    assert stored["mirror"]["plane"] == {
        "kind": "origin_plane",
        "plane": "yz",
        "offset_mm": 0.0,
    }

    request = EvaluateAssemblyRequest.model_validate(
        client.get(
            f"/api/v1/assemblies/{bike}/evaluation-request", headers=HEADERS
        ).json()
    )
    assert [str(m.mirror_id) for m in request.mirrors] == [mirror_id]

    # Switch the arm to an opposite hand (same id), undo and redo it.
    response = client.patch(
        f"/api/v1/assemblies/{bike}/mirrors/{mirror_id}",
        json={
            "expected_version": _version(client, bike),
            "mirror": _mirror([right], opposite=[right]),
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    undo = client.post(
        f"/api/v1/assemblies/{bike}/undo",
        json={"expected_version": _version(client, bike)},
        headers=HEADERS,
    )
    assert undo.status_code == 200, undo.text
    assert undo.json()["mirrors"][0]["mirror"]["opposite_hand_instance_ids"] == []
    redo = client.post(
        f"/api/v1/assemblies/{bike}/redo",
        json={"expected_version": _version(client, bike)},
        headers=HEADERS,
    )
    assert redo.json()["mirrors"][0]["mirror"]["opposite_hand_instance_ids"] == [right]

    deleted = client.delete(
        f"/api/v1/assemblies/{bike}/mirrors/{mirror_id}",
        params={"expected_version": _version(client, bike)},
        headers=HEADERS,
    )
    assert deleted.status_code == 200, deleted.text
    assert "mirrors" not in deleted.json()
    assert [i["id"] for i in deleted.json()["instances"]] == [right]
    missing = client.delete(
        f"/api/v1/assemblies/{bike}/mirrors/{mirror_id}",
        params={"expected_version": _version(client, bike)},
        headers=HEADERS,
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "mirror_not_found"


def test_seeds_opposite_hands_and_planes_must_belong(client: TestClient) -> None:
    arm = _part(client, "Crank arm")
    pedal = _part(client, "Pedal")
    bike = _assembly(client, "Bike")
    crankset = _assembly(client, "Crankset")
    _instance(client, crankset, arm, "Crank arm <1>")
    right = _instance(client, bike, arm, "Crank arm <1>")
    pedal_r = _instance(client, bike, pedal, "Pedal <1>")
    sub = _instance(client, bike, crankset, "Crankset <1>", kind="assembly")
    stranger = str(uuid.uuid4())

    def code(mirror: dict[str, Any]) -> str:
        response = _create(client, bike, mirror)
        assert response.status_code == 422, response.text
        return str(response.json()["error"]["code"])

    assert code(_mirror([stranger])) == "mirror_seed_unknown"
    assert code(_mirror([sub], opposite=[sub])) == "mirror_opposite_hand_needs_part"
    assert code(_mirror([right], face_on=stranger)) == "mirror_reference_unknown"
    assert code(_mirror([right], face_on=sub)) == "mirror_needs_part"
    assert code(_mirror([right], opposite=[pedal_r])) == "validation_error"
    # A seed may be a sub-assembly (a copy); the plane may be a face of a part
    # inside one, and of a seed itself.
    inner = _graph(client, crankset)["instances"][0]["id"]
    nested = str(nested_occurrence_id(uuid.UUID(sub), uuid.UUID(inner)))
    _add(client, bike, _mirror([sub, pedal_r], opposite=[pedal_r], face_on=nested))
    _add(client, bike, _mirror([right], face_on=right))


def test_the_crank_arms_bill_as_two_or_one_plus_one_opposite_hand(
    client: TestClient,
) -> None:
    """The backlog's acceptance on the BOM: the left arm is a mirrored copy of
    the right (Crank arm x 2), or its opposite hand (1 + 1)."""
    arm = _part(client, "Crank arm")
    spindle = _part(client, "Spindle")
    crankset = _assembly(client, "Crankset")
    _instance(client, crankset, spindle, "Spindle <1>")
    right = _instance(client, crankset, arm, "Crank arm <1>")
    mirror_id = _add(client, crankset, _mirror([right]))
    bom = _bom(client, crankset)
    assert _lines(bom["lines"]) == [("Crank arm", 2, False), ("Spindle", 1, False)]
    assert bom["total_instances"] == 3
    assert "opposite_hand" not in bom["lines"][0]  # omitted when false

    response = client.patch(
        f"/api/v1/assemblies/{crankset}/mirrors/{mirror_id}",
        json={
            "expected_version": _version(client, crankset),
            "mirror": _mirror([right], opposite=[right]),
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    bom = _bom(client, crankset)
    expected = [
        ("Crank arm", 1, False),
        ("Crank arm (opposite hand)", 1, True),
        ("Spindle", 1, False),
    ]
    assert _lines(bom["lines"]) == expected
    assert _lines(bom["parts_only"]) == expected
    assert bom["total_parts"] == 3
    hand = bom["lines"][1]
    assert hand["ref_document_id"] == arm and hand["ref_document_kind"] == "part"

    # One level up, a bike with the crankset mirrored as a whole (a copy):
    # two cranksets, and every part doubled, opposite hands included.
    bike = _assembly(client, "Bike")
    sub = _instance(client, bike, crankset, "Crankset <1>", kind="assembly")
    _add(client, bike, _mirror([sub]))
    bom = _bom(client, bike)
    assert _lines(bom["lines"]) == [("Crankset", 2, False)]
    assert _lines(bom["parts_only"]) == [
        ("Crank arm", 2, False),
        ("Crank arm (opposite hand)", 2, True),
        ("Spindle", 2, False),
    ]
    indented = [
        (row["item"], row["name"], row["total_quantity"]) for row in bom["indented"]
    ]
    assert indented == [
        ("1", "Crankset", 2),
        ("1.1", "Crank arm", 2),
        ("1.2", "Crank arm (opposite hand)", 2),
        ("1.3", "Spindle", 2),
    ]

    # A drawing's parts list numbers the opposite hand as its own item.
    drawing = _post(client, "/api/v1/drawings", {"name": "Crankset sheet"})["id"]
    sheet = client.post(
        f"/api/v1/drawings/{drawing}/sheets",
        json={"expected_version": 0, "name": "Sheet 1"},
        headers=HEADERS,
    ).json()
    view = client.post(
        f"/api/v1/drawings/{drawing}/sheets/{sheet['sheet']['id']}/views",
        json={
            "expected_version": sheet["doc_version"],
            "ref_document_id": crankset,
            "ref_document_kind": "assembly",
            "projection": "front",
            "position": {"x_mm": 50.0, "y_mm": 50.0},
        },
        headers=HEADERS,
    )
    assert view.status_code == 201, view.text
    parts_list = client.get(f"/api/v1/drawings/{drawing}/bom", headers=HEADERS).json()
    assert [
        (line["item_number"], line["name"], line["quantity"])
        for line in parts_list["lines"]
    ] == [(1, "Spindle", 1), (2, "Crank arm", 1), (3, "Crank arm (opposite hand)", 1)]
    assert parts_list["total_instances"] == 3


def test_the_instance_bound_counts_twins_at_every_ancestor(client: TestClient) -> None:
    """W holds 10 parts, X ten W, Y three X: Y places 3 x 111 = 333. Twins of
    W's parts would take Y to 3 x (1 + 10 x 21) = 633; twins of two X in Y to
    333 + 222 = 555. Both are refused and rolled back; one X is fine."""
    plate = _part(client, "Plate")
    w = _assembly(client, "W")
    parts = [_instance(client, w, plate, f"Plate <{n}>") for n in range(1, 11)]
    x = _assembly(client, "X")
    for n in range(1, 11):
        _instance(client, x, w, f"W <{n}>", kind="assembly")
    y = _assembly(client, "Y")
    xs = [_instance(client, y, x, f"X <{n}>", kind="assembly") for n in (1, 2, 3)]

    response = _create(client, w, _mirror(parts))
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "assembly_too_large"
    assert "mirrors" not in _graph(client, w)  # rolled back
    response = _create(client, y, _mirror(xs[:2]))
    assert response.json()["error"]["code"] == "assembly_too_large"
    _add(client, y, _mirror(xs[:1]))


def test_deleting_a_seed_or_the_plane_cascades(client: TestClient) -> None:
    arm = _part(client, "Crank arm")
    bike = _assembly(client, "Bike")
    a = _instance(client, bike, arm, "Crank arm <1>")
    b = _instance(client, bike, arm, "Crank arm <2>")
    frame = _instance(client, bike, arm, "Crank arm <3>")
    two_seeds = _add(client, bike, _mirror([a, b], opposite=[b]))
    on_face = _add(client, bike, _mirror([a], face_on=frame))

    def delete(instance: str) -> Any:
        response = client.delete(
            f"/api/v1/assemblies/{bike}/instances/{instance}",
            params={"expected_version": _version(client, bike)},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        return response.json()

    graph = delete(frame)  # the plane's face is gone: that mirror goes
    assert [m["id"] for m in graph["mirrors"]] == [two_seeds]
    graph = delete(b)  # one seed left, and its opposite hand with it
    (mirror,) = graph["mirrors"]
    assert mirror["mirror"]["seed_instance_ids"] == [a]
    assert mirror["mirror"]["opposite_hand_instance_ids"] == []
    assert mirror["order_index"] == 0
    graph = delete(a)  # no seeds left
    assert "mirrors" not in graph
    del on_face


def test_duplicate_remaps_the_mirror(client: TestClient) -> None:
    arm = _part(client, "Crank arm")
    bike = _assembly(client, "Bike")
    a = _instance(client, bike, arm, "Crank arm <1>")
    frame = _instance(client, bike, arm, "Crank arm <2>")
    _add(client, bike, _mirror([a], opposite=[a], face_on=frame))
    copy = _post(client, f"/api/v1/assemblies/{bike}/duplicate", {})["id"]
    graph = _graph(client, copy)
    new_a, new_frame = (i["id"] for i in graph["instances"])
    (mirror,) = graph["mirrors"]
    assert mirror["mirror"]["seed_instance_ids"] == [new_a]
    assert mirror["mirror"]["opposite_hand_instance_ids"] == [new_a]
    assert mirror["mirror"]["plane"]["instance_id"] == new_frame
