"""Custom features in documents (PLUGIN-REGISTRY, RESEARCH §23).

A custom feature is stored as one row pinning its plugin version, with its
inputs and last expansion. Documents expands it on write and in the
evaluation request, so geometry is sent base features only; a server without
the plugin rebuilds the stored expansion, read-only; a newer release never
changes a feature pinned to an older one.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from documents import custom_features
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_plugins import REGISTRY, PluginRegistry
from loft_plugins.testing import BLOCKS_V1, BLOCKS_V2
from loft_wire.parts import PRINCIPAL_HEADER
from loft_wire.plugins import member_id

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000c5"}

SQUARE = {
    "plane": {"kind": "datum_plane", "plane": "XY"},
    "entities": [
        {
            "id": f"e{i}",
            "kind": "line",
            "start": {"x": a[0], "y": a[1]},
            "end": {"x": b[0], "y": b[1]},
        }
        for i, (a, b) in enumerate(
            [
                ((-10, -10), (10, -10)),
                ((10, -10), (10, 10)),
                ((10, 10), (-10, 10)),
                ((-10, 10), (-10, -10)),
            ]
        )
    ],
    "constraints": [],
}


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


@pytest.fixture
def plugins(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[PluginRegistry]]:
    """Swap the server's registry: ``plugins[0] = ...`` installs another."""
    holder = [REGISTRY]

    class Proxy(PluginRegistry):
        def __getattribute__(self, name: str) -> Any:
            return getattr(holder[0], name)

    monkeypatch.setattr(custom_features, "PLUGINS", Proxy())
    yield holder


class Part:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        response = client.post(
            "/api/v1/parts", json={"name": f"P {uuid.uuid4()}"}, headers=HEADERS
        )
        assert response.status_code == 201, response.text
        self.id = str(response.json()["id"])
        self.version = 0

    def post(self, feature: dict[str, Any], name: str = "F") -> Any:
        response = self.client.post(
            f"/api/v1/parts/{self.id}/features",
            json={
                "name": name,
                "feature": feature,
                "expected_tree_version": self.version,
            },
            headers=HEADERS,
        )
        if response.status_code == 201:
            self.version = response.json()["tree_version"]
        return response

    def patch(self, feature_id: str, **body: Any) -> Any:
        response = self.client.patch(
            f"/api/v1/parts/{self.id}/features/{feature_id}",
            json={"expected_tree_version": self.version, **body},
            headers=HEADERS,
        )
        if response.status_code == 200:
            self.version = response.json()["tree_version"]
        return response

    def request(self) -> Any:
        response = self.client.get(
            f"/api/v1/parts/{self.id}/evaluation-request", headers=HEADERS
        )
        assert response.status_code == 200, response.text
        return response

    def sketch(self) -> str:
        response = self.post({"type": "sketch", "version": 1, "params": SQUARE})
        assert response.status_code == 201, response.text
        return str(response.json()["feature"]["id"])


def _prism(sketch_id: str, **inputs: Any) -> dict[str, Any]:
    expressions = inputs.pop("expressions", None)
    feature: dict[str, Any] = {
        "type": "custom",
        "version": 1,
        "params": {
            "plugin_id": "loft.twisted_prism",
            "plugin_version": "1.0.0",
            "inputs": {
                "profile": {"kind": "feature", "feature_id": sketch_id},
                **inputs,
            },
        },
    }
    if expressions is not None:
        feature["expressions"] = expressions
    return feature


def _blocks(version: str = "1.0.0", **inputs: Any) -> dict[str, Any]:
    return {
        "type": "custom",
        "version": 1,
        "params": {
            "plugin_id": "test.blocks",
            "plugin_version": version,
            "inputs": inputs,
        },
    }


def test_a_twisted_prism_is_stored_pinned_and_sent_as_base_features(
    client: TestClient,
) -> None:
    part = Part(client)
    sketch_id = part.sketch()
    created = part.post(_prism(sketch_id, distance_mm=30, twist_angle_deg=30))
    assert created.status_code == 201, created.text
    stored = created.json()["feature"]["feature"]
    prism_id = uuid.UUID(created.json()["feature"]["id"])
    assert stored["params"]["plugin_version"] == "1.0.0"
    # canonical inputs: defaults filled, a length typed as a length
    assert stored["params"]["inputs"]["distance_mm"] == 30.0
    assert stored["params"]["inputs"]["direction"] == "normal"
    roles = [(m["role"], m["index"]) for m in stored["params"]["expansion"]]
    assert roles == [("path", 0), ("sweep", 0)]

    features = part.request().json()["features"]
    assert [f["feature"]["type"] for f in features] == ["sketch", "sketch", "sweep"]
    assert [f["id"] for f in features[1:]] == [
        str(member_id(prism_id, "path", 0)),
        str(member_id(prism_id, "sweep", 0)),
    ]
    assert features[2]["feature"]["params"]["twist_angle_deg"] == 30.0


def test_refusals_are_typed(client: TestClient) -> None:
    part = Part(client)
    sketch_id = part.sketch()
    for feature, code in [
        (_prism(sketch_id, distance_mm=0), "plugin_input_invalid"),
        (_prism(sketch_id, colour="red"), "plugin_input_invalid"),
        (_prism(str(uuid.uuid4())), "reference_not_found"),
        (
            {
                **_prism(sketch_id),
                "params": {**_prism(sketch_id)["params"], "plugin_id": "acme.deck"},
            },
            "plugin_not_found",
        ),
        (
            {
                **_prism(sketch_id),
                "params": {**_prism(sketch_id)["params"], "plugin_version": "9.9.9"},
            },
            "plugin_version_not_found",
        ),
    ]:
        response = part.post(feature)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == code, response.text


def test_formulas_drive_inputs_and_the_table(client: TestClient) -> None:
    """An input takes a §20 expression; a table change re-expands."""
    part = Part(client)
    response = client.put(
        f"/api/v1/parts/{part.id}/parameters",
        json={
            "expected_tree_version": part.version,
            "parameters": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "twist",
                    "expression": "20 deg",
                    "unit": "angle",
                }
            ],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    part.version = response.json()["tree_version"]
    sketch_id = part.sketch()
    created = part.post(
        _prism(
            sketch_id,
            twist_angle_deg=0,
            expressions={"/inputs/twist_angle_deg": "twist * 2"},
        )
    )
    assert created.status_code == 201, created.text
    sweep = part.request().json()["features"][-1]["feature"]
    assert sweep["params"]["twist_angle_deg"] == pytest.approx(40.0)

    rows = client.get(f"/api/v1/parts/{part.id}/parameters", headers=HEADERS).json()
    row = {k: v for k, v in rows["parameters"][0].items() if k != "value"}
    response = client.put(
        f"/api/v1/parts/{part.id}/parameters",
        json={
            "expected_tree_version": part.version,
            "parameters": [{**row, "expression": "25 deg"}],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    sweep = part.request().json()["features"][-1]["feature"]
    assert sweep["params"]["twist_angle_deg"] == pytest.approx(50.0)
    tree = client.get(f"/api/v1/parts/{part.id}/features", headers=HEADERS).json()
    stored = tree["features"][-1]["feature"]["params"]
    assert stored["inputs"]["twist_angle_deg"] == pytest.approx(50.0)
    assert stored["expansion"][-1]["feature"]["params"]["twist_angle_deg"] == (
        pytest.approx(50.0)
    )


def test_a_v2_release_leaves_a_v1_feature_byte_identical(
    client: TestClient, plugins: list[PluginRegistry]
) -> None:
    """Acceptance: releasing v2 changes neither the stored v1 feature nor the
    request geometry rebuilds it from, byte for byte; v2 is listed as latest
    and is what a new feature pinned to it builds."""
    plugins[0] = PluginRegistry([BLOCKS_V1])
    part = Part(client)
    assert part.post(_blocks(count=2)).status_code == 201
    before = part.request().content
    plugins[0] = PluginRegistry([BLOCKS_V1, BLOCKS_V2])
    assert part.request().content == before

    catalog = client.get("/api/v1/plugins", headers=HEADERS).json()["plugins"]
    assert [(p["version"], p["latest"]) for p in catalog] == [
        ("2.0.0", True),
        ("1.0.0", False),
    ]
    assert part.post(_blocks("2.0.0", count=2)).status_code == 201
    directions = [
        f["feature"]["params"]["direction"]
        for f in part.request().json()["features"]
        if f["feature"]["type"] == "extrude"
    ]
    assert directions == ["normal", "normal", "reverse", "reverse"]


def test_without_its_plugin_a_feature_rebuilds_read_only(
    client: TestClient, plugins: list[PluginRegistry]
) -> None:
    part = Part(client)
    sketch_id = part.sketch()
    created = part.post(_prism(sketch_id, distance_mm=30))
    prism = created.json()["feature"]
    before = part.request().json()

    plugins[0] = PluginRegistry()
    assert part.request().json() == before  # the stored expansion rebuilds
    changed = _prism(sketch_id, distance_mm=31)
    response = part.patch(prism["id"], feature=changed)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "plugin_read_only"
    # a rename, or saving it back unchanged, is fine
    assert part.patch(prism["id"], name="Kept").status_code == 200
    assert part.patch(prism["id"], feature=prism["feature"]).status_code == 200
    assert client.get("/api/v1/plugins", headers=HEADERS).json() == {"plugins": []}


def test_a_pick_on_a_member_is_an_edge_to_the_custom_feature(
    client: TestClient,
) -> None:
    """A later feature may reference a generated member; its dependency is the
    custom feature's row (so deleting it is a 409), and duplicate and .loft
    import move the member ids with the custom feature's id."""
    part = Part(client)
    sketch_id = part.sketch()
    created = part.post(_prism(sketch_id, distance_mm=30))
    prism_id = created.json()["feature"]["id"]
    path_id = str(member_id(uuid.UUID(prism_id), "path", 0))
    later = part.post(
        {
            "type": "extrude",
            "version": 1,
            "params": {
                "profile": {"kind": "feature", "feature_id": path_id},
                "distance_mm": 5.0,
                "operation": "add",
            },
        }
    )
    assert later.status_code == 201, later.text
    deleted = client.delete(
        f"/api/v1/parts/{part.id}/features/{prism_id}",
        params={"expected_tree_version": part.version},
        headers=HEADERS,
    )
    assert deleted.status_code == 409
    assert deleted.json()["error"]["code"] == "feature_has_dependents"

    copy = client.post(f"/api/v1/parts/{part.id}/duplicate", headers=HEADERS)
    assert copy.status_code == 201, copy.text
    _assert_members_follow(client, str(copy.json()["id"]))

    tree = client.get(f"/api/v1/parts/{part.id}/loft-tree", headers=HEADERS).json()
    imported = client.post(
        "/api/v1/parts/import-loft",
        json={"document_id": part.id, "tree": tree},  # ids taken: re-minted
        headers=HEADERS,
    )
    assert imported.status_code == 201, imported.text
    _assert_members_follow(client, str(imported.json()["id"]))


def _assert_members_follow(client: TestClient, part_id: str) -> None:
    rows = client.get(f"/api/v1/parts/{part_id}/features", headers=HEADERS).json()
    _, prism, later = rows["features"]
    new_path = str(member_id(uuid.UUID(prism["id"]), "path", 0))
    assert prism["feature"]["params"]["expansion"][0]["id"] == new_path
    assert later["feature"]["params"]["profile"]["feature_id"] == new_path
    request = client.get(
        f"/api/v1/parts/{part_id}/evaluation-request", headers=HEADERS
    ).json()
    assert new_path in [f["id"] for f in request["features"]]


def test_an_import_with_a_forged_member_id_is_refused(client: TestClient) -> None:
    part = Part(client)
    sketch_id = part.sketch()
    assert part.post(_prism(sketch_id)).status_code == 201
    tree = client.get(f"/api/v1/parts/{part.id}/loft-tree", headers=HEADERS).json()
    tree["features"][1]["params"]["expansion"][0]["id"] = sketch_id
    imported = client.post(
        "/api/v1/parts/import-loft",
        json={"document_id": str(uuid.uuid4()), "tree": tree},
        headers=HEADERS,
    )
    assert imported.status_code == 422, imported.text
    assert imported.json()["error"]["code"] == "plugin_expansion_invalid"


def test_the_catalog_needs_a_principal(client: TestClient) -> None:
    assert client.get("/api/v1/plugins").status_code in (401, 403, 422)
    served = client.get("/api/v1/plugins", headers=HEADERS)
    assert served.status_code == 200
    assert [p["id"] for p in served.json()["plugins"]] == ["loft.twisted_prism"]
