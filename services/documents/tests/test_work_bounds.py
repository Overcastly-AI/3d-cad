"""documents write-side twins of the per-request work bounds (audit G2).

The evaluation/compose DTOs now carry parse-time ceilings
(``MAX_TREE_FEATURES``, ``MAX_ASSEMBLY_INSTANCES``/``MAX_ASSEMBLY_MATES``,
``MAX_DRAWING_VIEWS``/``MAX_DRAWING_DIMENSIONS``/``MAX_DRAWING_ANNOTATIONS``),
so documents must refuse to PERSIST a document that would exceed them — else a
part/assembly/drawing could accumulate rows one CRUD call at a time until every
later evaluation-request read fails constructing the bounded DTO (a persistent
500, the exact never-500 violation the bounds exist to prevent).

Each guard reads its module-global constant at call time, so the tests
monkeypatch the ceiling down to a tiny value instead of creating hundreds of
rows — the GUARD LOGIC (typed 422, correct code, at-cap accept / over-cap
reject) is what is under test, not the production constant's magnitude (the
constants themselves are asserted in py-kit's test_work_bounds).
"""

from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from py_kit.schemas.parts import PRINCIPAL_HEADER

OWNER = "6f3f6b64-0000-4000-8000-00000000000c"

SKETCH_ENVELOPE: dict[str, Any] = {
    "type": "sketch",
    "version": 1,
    "params": {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": [
            {
                "id": "e1",
                "kind": "line",
                "start": {"x": 0.0, "y": 0.0},
                "end": {"x": 40.0, "y": 0.0},
            }
        ],
        "constraints": [],
    },
}


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=any_db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _headers() -> dict[str, str]:
    return {PRINCIPAL_HEADER: OWNER}


def _error_code(response: Any) -> str:
    assert response.status_code == 422, response.text
    code: str = response.json()["error"]["code"]
    return code


def _create_part(client: TestClient, name: str = "bounded-part") -> str:
    response = client.post("/api/v1/parts", json={"name": name}, headers=_headers())
    assert response.status_code == 201, response.text
    part_id: str = response.json()["id"]
    return part_id


def _add_feature(client: TestClient, part_id: str, version: int) -> Any:
    return client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": f"Sketch{version + 1}",
            "feature": SKETCH_ENVELOPE,
            "expected_tree_version": version,
        },
        headers=_headers(),
    )


def test_feature_create_refuses_over_tree_ceiling(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import documents.features as features_module

    monkeypatch.setattr(features_module, "MAX_TREE_FEATURES", 2)
    part_id = _create_part(client)
    assert _add_feature(client, part_id, 0).status_code == 201  # 1st: under cap
    assert _add_feature(client, part_id, 1).status_code == 201  # 2nd: reaches cap
    response = _add_feature(client, part_id, 2)  # 3rd: would exceed
    assert _error_code(response) == "feature_limit_exceeded"


def _create_assembly(client: TestClient) -> str:
    response = client.post(
        "/api/v1/assemblies", json={"name": "bounded-assembly"}, headers=_headers()
    )
    assert response.status_code == 201, response.text
    assembly_id: str = response.json()["id"]
    return assembly_id


def _add_instance(
    client: TestClient, assembly_id: str, part_id: str, version: int, name: str
) -> Any:
    return client.post(
        f"/api/v1/assemblies/{assembly_id}/instances",
        json={
            "expected_version": version,
            "ref_document_id": part_id,
            "ref_document_kind": "part",
            "name": name,
        },
        headers=_headers(),
    )


def test_instance_create_refuses_over_instance_ceiling(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import documents.assemblies as assemblies_module

    monkeypatch.setattr(assemblies_module, "MAX_ASSEMBLY_INSTANCES", 1)
    assembly_id = _create_assembly(client)
    part_id = _create_part(client)
    assert _add_instance(client, assembly_id, part_id, 0, "P <1>").status_code == 201
    response = _add_instance(client, assembly_id, part_id, 1, "P <2>")
    assert _error_code(response) == "instance_limit_exceeded"


def test_mate_create_refuses_over_mate_ceiling(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import documents.assemblies as assemblies_module

    assembly_id = _create_assembly(client)
    part_id = _create_part(client)
    r1 = _add_instance(client, assembly_id, part_id, 0, "P <1>")
    r2 = _add_instance(client, assembly_id, part_id, 1, "P <2>")
    instance_a = r1.json()["instance"]["id"]
    instance_b = r2.json()["instance"]["id"]

    monkeypatch.setattr(assemblies_module, "MAX_ASSEMBLY_MATES", 0)
    response = client.post(
        f"/api/v1/assemblies/{assembly_id}/mates",
        json={
            "expected_version": 2,
            "mate": {
                "type": "lock",
                "a_instance_id": instance_a,
                "b_instance_id": instance_b,
            },
        },
        headers=_headers(),
    )
    assert _error_code(response) == "mate_limit_exceeded"


def _drawing_with_sheet(client: TestClient) -> tuple[str, str]:
    response = client.post(
        "/api/v1/drawings", json={"name": "bounded-drawing"}, headers=_headers()
    )
    assert response.status_code == 201, response.text
    drawing_id: str = response.json()["id"]
    sheet = client.post(
        f"/api/v1/drawings/{drawing_id}/sheets",
        json={"expected_version": 0, "name": "Sheet 1"},
        headers=_headers(),
    )
    assert sheet.status_code == 201, sheet.text
    sheet_id: str = sheet.json()["sheet"]["id"]
    return drawing_id, sheet_id


def _add_view(
    client: TestClient, drawing_id: str, sheet_id: str, part_id: str, version: int
) -> Any:
    return client.post(
        f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/views",
        json={
            "expected_version": version,
            "ref_document_id": part_id,
            "ref_document_kind": "part",
            "projection": "front",
            "position": {"x_mm": 50.0, "y_mm": 50.0},
        },
        headers=_headers(),
    )


def test_sheet_create_refuses_over_sheet_ceiling(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """audit H5 — the bound G2 missed. Every read of a drawing serializes its whole
    sheet tree, and `DrawingTreeResponse.sheets` now carries the matching
    `max_length`, so persisting past the ceiling would make the drawing
    unreadable."""
    import documents.drawings as drawings_module

    monkeypatch.setattr(drawings_module, "MAX_DRAWING_SHEETS", 1)
    drawing_id, _sheet_id = _drawing_with_sheet(client)  # sheet 1 of 1
    response = client.post(
        f"/api/v1/drawings/{drawing_id}/sheets",
        json={"expected_version": 1, "name": "Sheet 2"},
        headers=_headers(),
    )
    assert _error_code(response) == "sheet_limit_exceeded"
    assert response.json()["error"]["details"]["max_sheets"] == 1

    # The drawing is still readable, and still holds exactly the one sheet.
    tree = client.get(f"/api/v1/drawings/{drawing_id}", headers=_headers())
    assert tree.status_code == 200, tree.text
    assert len(tree.json()["sheets"]) == 1


def test_view_create_refuses_over_view_ceiling(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import documents.drawings as drawings_module

    monkeypatch.setattr(drawings_module, "MAX_DRAWING_VIEWS", 1)
    drawing_id, sheet_id = _drawing_with_sheet(client)
    part_id = _create_part(client)
    assert _add_view(client, drawing_id, sheet_id, part_id, 1).status_code == 201
    response = _add_view(client, drawing_id, sheet_id, part_id, 2)
    assert _error_code(response) == "view_limit_exceeded"


def test_dimension_create_refuses_over_dimension_ceiling(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import documents.drawings as drawings_module

    drawing_id, sheet_id = _drawing_with_sheet(client)
    part_id = _create_part(client)
    view = _add_view(client, drawing_id, sheet_id, part_id, 1)
    view_id = view.json()["view"]["id"]

    monkeypatch.setattr(drawings_module, "MAX_DRAWING_DIMENSIONS", 0)
    response = client.post(
        f"/api/v1/drawings/{drawing_id}/views/{view_id}/dimensions",
        json={
            "expected_version": 2,
            "dimension": {
                "type": "linear",
                "measurement": {
                    "mode": "edge_length",
                    "edge": {
                        "curve": "line",
                        "end_a": {"x": 0.0, "y": 0.0, "z": 0.0},
                        "end_b": {"x": 40.0, "y": 0.0, "z": 0.0},
                        "midpoint": {"x": 20.0, "y": 0.0, "z": 0.0},
                        "length_mm": 40.0,
                    },
                },
            },
        },
        headers=_headers(),
    )
    assert _error_code(response) == "dimension_limit_exceeded"


def test_annotation_create_refuses_over_annotation_ceiling(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import documents.drawings as drawings_module

    drawing_id, sheet_id = _drawing_with_sheet(client)

    monkeypatch.setattr(drawings_module, "MAX_DRAWING_ANNOTATIONS", 0)
    response = client.post(
        f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/annotations",
        json={
            "expected_version": 1,
            "annotation": {
                "type": "note",
                "text": "Break all sharp edges",
                "position": {"x_mm": 10.0, "y_mm": 20.0},
            },
        },
        headers=_headers(),
    )
    assert _error_code(response) == "annotation_limit_exceeded"
