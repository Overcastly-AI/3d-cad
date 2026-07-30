"""documents material assignment — persistence + handover (docs/design/materials.md).

Mass is derived from a material, and the material is the ONE thing on the
evaluation request that is not pure geometry intent. What matters here:

* a part starts with NO material, and says so as an empty assignment rather
  than null-vs-empty ambiguity;
* the assignment (document default + per-body overrides) round-trips through
  the PATCH and rides the evaluation request geometry receives — an assembly
  instance carries the same one its part does, so an instance never evaluates
  to a different mass than the part it references;
* a material change invalidates the recorded evaluate (mass depends on it),
  while a rename or a unit change still does not.

Same SQLite dialect posture as tests/test_parts.py.
"""

import asyncio
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from documents.db import Base
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from py_kit.db import async_dsn
from py_kit.schemas.assemblies import EvaluateAssemblyRequest
from py_kit.schemas.features import EvaluateTreeRequest
from py_kit.schemas.materials import MATERIALS, MaterialLibraryResponse
from py_kit.schemas.parts import PRINCIPAL_HEADER
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000000a"

#: A minimal valid sketch — this suite tests handover, not solving.
SKETCH_PARAMS: dict[str, Any] = {
    "plane": {"kind": "datum_plane", "plane": "XY"},
    "entities": [
        {
            "id": "e1",
            "kind": "line",
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 40.0, "y": 0.0},
        }
    ],
    "constraints": [{"kind": "fixed", "point": {"entity": "e1", "point": "start"}}],
}


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path}/documents.db"
    asyncio.run(_create_schema(url))
    return url


@pytest.fixture
def client(db_url: str) -> Iterator[TestClient]:
    settings = DocumentsSettings(postgres_url=db_url)
    with TestClient(build_app(settings)) as test_client:
        yield test_client


def _headers() -> dict[str, str]:
    return {PRINCIPAL_HEADER: OWNER}


def _create_part(client: TestClient, name: str = "bracket") -> dict[str, Any]:
    response = client.post("/api/v1/parts", json={"name": name}, headers=_headers())
    assert response.status_code == 201, response.text
    part: dict[str, Any] = response.json()
    return part


def _patch(client: TestClient, part_id: str, body: dict[str, Any]) -> Any:
    return client.patch(f"/api/v1/parts/{part_id}", json=body, headers=_headers())


class TestTheEmptyState:
    """A part nobody has assigned a material to says exactly that."""

    def test_a_new_part_has_no_material(self, client: TestClient) -> None:
        part = _create_part(client)

        assert part["materials"] == {"default_material": None, "bodies": []}

    def test_an_unset_assignment_reads_back_as_empty_not_null(
        self, client: TestClient
    ) -> None:
        """One shape on the wire: never null-vs-empty for the same state."""
        part = _create_part(client)

        listed = client.get("/api/v1/parts", headers=_headers()).json()["parts"]

        assert listed[0]["materials"] is not None
        assert listed[0]["materials"] == part["materials"]


class TestAssignment:
    """Default + per-body override, replaced wholesale (design §2)."""

    def test_patch_sets_the_document_default(self, client: TestClient) -> None:
        part = _create_part(client)

        response = _patch(
            client,
            part["id"],
            {
                "expected_tree_version": 0,
                "materials": {"default_material": "aluminium_6061"},
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["materials"]["default_material"] == "aluminium_6061"
        assert response.json()["tree_version"] == 1

    def test_patch_sets_a_per_body_override(self, client: TestClient) -> None:
        part = _create_part(client)
        body_id = str(uuid.uuid4())

        response = _patch(
            client,
            part["id"],
            {
                "expected_tree_version": 0,
                "materials": {
                    "default_material": "aluminium_6061",
                    "bodies": [{"base_feature_id": body_id, "material": "steel_1018"}],
                },
            },
        )

        assert response.status_code == 200, response.text
        materials = response.json()["materials"]
        assert materials["bodies"] == [
            {"base_feature_id": body_id, "material": "steel_1018"}
        ]

    def test_an_empty_assignment_clears_it_back_to_unknown(
        self, client: TestClient
    ) -> None:
        """Clearing is expressible — a material is not a one-way door."""
        part = _create_part(client)
        _patch(
            client,
            part["id"],
            {
                "expected_tree_version": 0,
                "materials": {"default_material": "steel_1018"},
            },
        )

        response = _patch(
            client,
            part["id"],
            {"expected_tree_version": 1, "materials": {"default_material": None}},
        )

        assert response.status_code == 200, response.text
        assert response.json()["materials"] == {"default_material": None, "bodies": []}

    def test_duplicate_body_overrides_are_rejected(self, client: TestClient) -> None:
        """Order must never decide which material a body gets (RESEARCH §9)."""
        part = _create_part(client)
        body_id = str(uuid.uuid4())

        response = _patch(
            client,
            part["id"],
            {
                "expected_tree_version": 0,
                "materials": {
                    "bodies": [
                        {"base_feature_id": body_id, "material": "steel_1018"},
                        {"base_feature_id": body_id, "material": "abs"},
                    ]
                },
            },
        )

        assert response.status_code == 422, response.text

    def test_an_unknown_material_is_rejected(self, client: TestClient) -> None:
        part = _create_part(client)

        response = _patch(
            client,
            part["id"],
            {
                "expected_tree_version": 0,
                "materials": {"default_material": "unobtainium"},
            },
        )

        assert response.status_code == 422, response.text

    def test_a_patch_with_nothing_at_all_is_still_rejected(
        self, client: TestClient
    ) -> None:
        part = _create_part(client)

        response = _patch(client, part["id"], {"expected_tree_version": 0})

        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "empty_part_update"


class TestHandover:
    """What geometry receives (design §2/§3)."""

    def test_the_evaluation_request_carries_the_assignment(
        self, client: TestClient
    ) -> None:
        part = _create_part(client)
        _patch(
            client,
            part["id"],
            {
                "expected_tree_version": 0,
                "materials": {"default_material": "brass_c360"},
            },
        )

        response = client.get(
            f"/api/v1/parts/{part['id']}/evaluation-request", headers=_headers()
        )

        assert response.status_code == 200, response.text
        request = EvaluateTreeRequest.model_validate(response.json())
        assert request.materials is not None
        assert request.materials.default_material == "brass_c360"

    def test_no_material_hands_over_null_not_an_empty_object(
        self, client: TestClient
    ) -> None:
        """Geometry's ``None`` and an empty assignment mean the same thing; the
        handover picks ONE of them so the kernel has a single case to read."""
        part = _create_part(client)

        response = client.get(
            f"/api/v1/parts/{part['id']}/evaluation-request", headers=_headers()
        )

        assert EvaluateTreeRequest.model_validate(response.json()).materials is None

    def test_an_assembly_instance_carries_its_parts_materials(
        self, client: TestClient
    ) -> None:
        """An instance must evaluate to the same mass as opening the part."""
        part = _create_part(client, "instanced")
        _patch(
            client,
            part["id"],
            {
                "expected_tree_version": 0,
                "materials": {"default_material": "pla"},
            },
        )
        created = client.post(
            f"/api/v1/parts/{part['id']}/features",
            json={
                "name": "Sketch1",
                "feature": {"type": "sketch", "version": 1, "params": SKETCH_PARAMS},
                "expected_tree_version": 1,
            },
            headers=_headers(),
        )
        assert created.status_code == 201, created.text

        assembly = client.post(
            "/api/v1/assemblies", json={"name": "rig"}, headers=_headers()
        )
        assert assembly.status_code == 201, assembly.text
        assembly_id = assembly.json()["id"]
        instance = client.post(
            f"/api/v1/assemblies/{assembly_id}/instances",
            json={
                "expected_version": assembly.json()["doc_version"],
                "ref_document_kind": "part",
                "ref_document_id": part["id"],
                "name": "Instanced <1>",
                "grounded": True,
            },
            headers=_headers(),
        )
        assert instance.status_code == 201, instance.text

        response = client.get(
            f"/api/v1/assemblies/{assembly_id}/evaluation-request", headers=_headers()
        )

        assert response.status_code == 200, response.text
        request = EvaluateAssemblyRequest.model_validate(response.json())
        assert len(request.instances) == 1
        assert request.instances[0].materials is not None
        assert request.instances[0].materials.default_material == "pla"


class TestEvaluateRecordInvalidation:
    """A material change really does invalidate the recorded answer (§2)."""

    @staticmethod
    def _record(client: TestClient, part_id: str, tree_version: int) -> None:
        response = client.put(
            f"/api/v1/parts/{part_id}/last-evaluation",
            json={"tree_version": tree_version, "status": "ok"},
            headers=_headers(),
        )
        assert response.status_code == 200, response.text

    def test_changing_material_makes_the_last_evaluate_stale(
        self, client: TestClient
    ) -> None:
        part = _create_part(client)
        self._record(client, part["id"], 0)

        response = _patch(
            client,
            part["id"],
            {
                "expected_tree_version": 0,
                "materials": {"default_material": "steel_1018"},
            },
        )

        assert response.json()["eval_state"] == "stale", (
            "mass is derived from the material, so the recorded result describes "
            "a state that no longer holds"
        )

    def test_renaming_still_does_not(self, client: TestClient) -> None:
        """The §4.4a carry-forward survives — only material breaks it."""
        part = _create_part(client)
        self._record(client, part["id"], 0)

        response = _patch(
            client, part["id"], {"expected_tree_version": 0, "name": "renamed"}
        )

        assert response.json()["eval_state"] == "ok"


def test_the_material_library_is_served_not_hardcoded(client: TestClient) -> None:
    """One table of densities; clients read it rather than copying it."""
    response = client.get("/api/v1/materials")

    assert response.status_code == 200, response.text
    library = MaterialLibraryResponse.model_validate(response.json())
    assert [m.key for m in library.materials] == [m.key for m in MATERIALS]
    assert [m.density_kg_m3 for m in library.materials] == [
        m.density_kg_m3 for m in MATERIALS
    ]
