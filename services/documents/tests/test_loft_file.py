"""documents ``.loft`` routes: the tree an export writes, and what an import creates.

The import contract (docs/FILE-FORMAT.md, :mod:`documents.loft_file`):

* ids are KEPT when none exists here, and ALL re-minted when any does — so
  importing the same file twice gives a detached copy, named "<name> copy";
* the POST /features validation runs on every feature, a newer
  ``param_version`` or an unknown type is refused naming the feature;
* dependency edges are DERIVED again (the file carries none);
* a re-mint rewrites the uuid inside each ``topo_name`` and drops hashed names.

Same SQLite file-per-test posture as the sibling suites.
"""

import asyncio
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from documents.db import Base
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.parts import PRINCIPAL_HEADER
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine

OWNER = "6f3f6b64-0000-4000-8000-00000000000a"
OTHER = "6f3f6b64-0000-4000-8000-00000000000b"


async def _create_schema(url: str) -> None:
    engine = create_async_engine(async_dsn(url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[Callable[[str], TestClient]]:
    """A documents app per named database — two installs in one test."""
    opened: list[Any] = []

    def make(name: str) -> TestClient:
        url = f"sqlite:///{tmp_path}/{name}.db"
        asyncio.run(_create_schema(url))
        manager = TestClient(build_app(DocumentsSettings(postgres_url=url)))
        client = manager.__enter__()
        opened.append(manager)
        return client

    yield make
    for manager in opened:
        manager.__exit__(None, None, None)


@pytest.fixture
def client(make_client: Callable[[str], TestClient]) -> TestClient:
    return make_client("install-a")


def _headers(owner: str = OWNER) -> dict[str, str]:
    return {PRINCIPAL_HEADER: owner}


SKETCH_PARAMS: dict[str, Any] = {
    "plane": {"kind": "datum_plane", "plane": "XY"},
    "entities": [
        {
            "construction": False,
            "id": "e1",
            "kind": "line",
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 40.0, "y": 0.0},
        }
    ],
    "constraints": [],
}


def _add(
    client: TestClient, part_id: str, name: str, feature: dict[str, Any], version: int
) -> str:
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": name, "feature": feature, "expected_tree_version": version},
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    feature_id: str = response.json()["feature"]["id"]
    return feature_id


def _on_face_datum(target_id: str, topo_name: str) -> dict[str, Any]:
    return {
        "type": "datum",
        "version": 1,
        "params": {
            "kind": "on_face",
            "offset_mm": 0.0,
            "face": {
                "kind": "subshape",
                "feature_id": target_id,
                "subshape_type": "face",
                "selector": {
                    "selector_version": 1,
                    "signature": {
                        "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
                        "centroid": {"x": 20.0, "y": 12.5, "z": 10.0},
                        "area_mm2": 1000.0,
                        "topo_name": topo_name,
                    },
                },
            },
        },
    }


def _seeded(client: TestClient) -> dict[str, str]:
    """Sketch1 <- Extrude1 <- Plane1 (on a named face), a material, a travel stop."""
    part_id = client.post(
        "/api/v1/parts",
        json={"name": "Bracket", "length_unit": "in"},
        headers=_headers(),
    ).json()["id"]
    sketch = _add(
        client,
        part_id,
        "Sketch1",
        {"type": "sketch", "version": 1, "params": SKETCH_PARAMS},
        0,
    )
    extrude = _add(
        client,
        part_id,
        "Extrude1",
        {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": sketch},
                "distance_mm": 10.0,
                "operation": "add",
                "direction": "normal",
            },
        },
        1,
    )
    plane = _add(
        client, part_id, "Plane1", _on_face_datum(extrude, f"{extrude}:cap_end"), 2
    )
    hashed = _add(
        client, part_id, "Plane2", _on_face_datum(extrude, f"{extrude}:#{'a' * 32}"), 3
    )
    patched = client.patch(
        f"/api/v1/parts/{part_id}",
        json={
            "expected_tree_version": 4,
            "materials": {
                "default_material": "aluminium_6061",
                "bodies": [{"base_feature_id": extrude, "material": "steel_1018"}],
            },
        },
        headers=_headers(),
    )
    assert patched.status_code == 200, patched.text
    moved = client.put(
        f"/api/v1/parts/{part_id}/rollback",
        json={"expected_tree_version": 5, "rollback_feature_id": plane},
        headers=_headers(),
    )
    assert moved.status_code == 200, moved.text
    return {
        "part": part_id,
        "sketch": sketch,
        "extrude": extrude,
        "plane": plane,
        "hashed": hashed,
    }


def _loft_tree(client: TestClient, part_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/parts/{part_id}/loft-tree", headers=_headers())
    assert response.status_code == 200, response.text
    tree: dict[str, Any] = response.json()
    return tree


def _import(client: TestClient, document_id: str, tree: dict[str, Any]) -> Any:
    return client.post(
        "/api/v1/parts/import-loft",
        json={"document_id": document_id, "tree": tree},
        headers=_headers(),
    )


def _features(client: TestClient, part_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/parts/{part_id}/features", headers=_headers())
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --- export -----------------------------------------------------------------------


def test_loft_tree_is_the_whole_definition_and_nothing_derived(
    client: TestClient,
) -> None:
    ids = _seeded(client)
    tree = _loft_tree(client, ids["part"])
    assert tree["name"] == "Bracket"
    assert tree["length_unit"] == "in"
    assert tree["rollback_feature_id"] == ids["plane"]
    assert tree["materials"]["bodies"][0]["base_feature_id"] == ids["extrude"]
    assert [f["name"] for f in tree["features"]] == [
        "Sketch1",
        "Extrude1",
        "Plane1",
        "Plane2",
    ]
    assert set(tree["features"][0]) == {
        "id",
        "name",
        "type",
        "param_version",
        "suppressed",
        "params",
    }
    # Params come out through the registry: the current version, defaults filled.
    assert tree["features"][1]["param_version"] == 1
    assert tree["features"][1]["params"]["distance_mm"] == 10.0


def test_loft_tree_is_owner_scoped(client: TestClient) -> None:
    ids = _seeded(client)
    response = client.get(
        f"/api/v1/parts/{ids['part']}/loft-tree", headers=_headers(OTHER)
    )
    assert response.status_code == 404


# --- import -----------------------------------------------------------------------


def test_import_into_another_install_keeps_every_id(
    client: TestClient, make_client: Callable[[str], TestClient]
) -> None:
    ids = _seeded(client)
    tree = _loft_tree(client, ids["part"])
    other = make_client("install-b")

    response = _import(other, ids["part"], tree)
    assert response.status_code == 201, response.text
    part = response.json()
    assert part["id"] == ids["part"]
    assert part["name"] == "Bracket"
    assert part["length_unit"] == "in"
    assert part["tree_version"] == 1
    assert part["eval_state"] == "never"
    # The tree reads back identical: same ids, same params, same travel stop.
    reread = _loft_tree(other, part["id"])
    for got, want in zip(reread["features"], tree["features"], strict=True):
        assert got == want, (got, want)
    assert reread == tree
    # ...including the topo names, untouched when nothing was re-minted.
    plane = _features(other, part["id"])["features"][2]
    signature = plane["feature"]["params"]["face"]["selector"]["signature"]
    assert signature["topo_name"] == f"{ids['extrude']}:cap_end"


def test_import_twice_gives_a_detached_copy(client: TestClient) -> None:
    ids = _seeded(client)
    tree = _loft_tree(client, ids["part"])

    response = _import(client, ids["part"], tree)
    assert response.status_code == 201, response.text
    copy = response.json()
    assert copy["name"] == "Bracket copy"
    assert copy["id"] != ids["part"]
    again = _import(client, ids["part"], tree)
    assert again.status_code == 201, again.text
    assert again.json()["name"] == "Bracket copy 2"

    copied = _loft_tree(client, copy["id"])
    new_ids = [f["id"] for f in copied["features"]]
    assert set(new_ids).isdisjoint(ids.values())
    sketch, extrude, plane, hashed = copied["features"]
    # Every reference, the travel stop and the per-body material follow the copy.
    assert extrude["params"]["profile"]["feature_id"] == sketch["id"]
    assert plane["params"]["face"]["feature_id"] == extrude["id"]
    assert copied["rollback_feature_id"] == plane["id"]
    assert copied["materials"]["bodies"][0]["base_feature_id"] == extrude["id"]
    # The named tier survives the re-mint; a hashed name cannot, so it is dropped.
    signature = plane["params"]["face"]["selector"]["signature"]
    assert signature["topo_name"] == f"{extrude['id']}:cap_end"
    assert hashed["params"]["face"]["selector"]["signature"]["topo_name"] is None
    # The original is untouched.
    assert _loft_tree(client, ids["part"]) == tree


def test_import_derives_the_dependency_edges_again(client: TestClient) -> None:
    ids = _seeded(client)
    copy_id = _import(client, ids["part"], _loft_tree(client, ids["part"])).json()["id"]
    tree = _features(client, copy_id)
    refused = client.delete(
        f"/api/v1/parts/{copy_id}/features/{tree['features'][0]['id']}",
        params={"expected_tree_version": tree["tree_version"]},
        headers=_headers(),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "feature_has_dependents"
    dependents = refused.json()["error"]["details"]["dependents"]
    assert [d["name"] for d in dependents] == ["Extrude1"]


def test_newer_param_version_is_refused_naming_the_feature(
    client: TestClient,
) -> None:
    ids = _seeded(client)
    tree = _loft_tree(client, ids["part"])
    tree["features"][1]["param_version"] = 99
    response = _import(client, str(uuid.uuid4()), tree)
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "loft_feature_too_new"
    assert error["details"]["feature_name"] == "Extrude1"
    assert "Upgrade Loft" in error["message"]
    assert len(client.get("/api/v1/parts", headers=_headers()).json()["parts"]) == 1


def test_unknown_feature_type_is_refused_naming_the_feature(
    client: TestClient,
) -> None:
    ids = _seeded(client)
    tree = _loft_tree(client, ids["part"])
    tree["features"][2]["type"] = "warp_drive"
    response = _import(client, str(uuid.uuid4()), tree)
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "loft_feature_unknown_type"
    assert error["details"]["feature_name"] == "Plane1"


def test_the_post_features_rules_apply(client: TestClient) -> None:
    """A forward reference is refused exactly as POST /features refuses it."""
    ids = _seeded(client)
    tree = _loft_tree(client, ids["part"])
    tree["features"][0], tree["features"][1] = tree["features"][1], tree["features"][0]
    response = _import(client, str(uuid.uuid4()), tree)
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "reference_not_found"
    assert error["details"]["feature_name"] == "Extrude1"


def test_invalid_params_are_refused(client: TestClient) -> None:
    ids = _seeded(client)
    tree = _loft_tree(client, ids["part"])
    tree["features"][1]["params"]["distance_mm"] = "far"
    response = _import(client, str(uuid.uuid4()), tree)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "loft_feature_invalid"


def test_duplicate_feature_ids_and_a_dangling_travel_stop_are_refused(
    client: TestClient,
) -> None:
    ids = _seeded(client)
    tree = _loft_tree(client, ids["part"])
    dangling = {**tree, "rollback_feature_id": str(uuid.uuid4())}
    response = _import(client, str(uuid.uuid4()), dangling)
    assert response.json()["error"]["code"] == "loft_rollback_invalid"
    twice = {**tree, "features": [tree["features"][0], tree["features"][0]]}
    response = _import(client, str(uuid.uuid4()), twice)
    assert response.json()["error"]["code"] == "loft_feature_id_duplicate"


def test_an_empty_tree_imports(client: TestClient) -> None:
    response = _import(client, str(uuid.uuid4()), {"name": "Empty", "features": []})
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Empty"


def test_import_on_postgres_with_the_migrated_constraints(pg_url: str) -> None:
    """The real schema: composite same-part FKs (the travel stop, the edges) and
    the deferrable order unique exist only in the migrations, not in SQLite."""
    with TestClient(build_app(DocumentsSettings(postgres_url=pg_url))) as client:
        ids = _seeded(client)
        tree = _loft_tree(client, ids["part"])
        response = _import(client, ids["part"], tree)
        assert response.status_code == 201, response.text
        copied = _loft_tree(client, response.json()["id"])
        assert copied["rollback_feature_id"] == copied["features"][2]["id"]
        assert [f["name"] for f in copied["features"]] == [
            f["name"] for f in tree["features"]
        ]
