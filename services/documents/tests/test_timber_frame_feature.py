"""The shipped ``loft.timber_frame`` plugin through documents (TIMBER-FRAME).

One Timber frame custom feature in an inch part, with the server's own
registry: B6's frame expands to 4 posts, 2 tie beams, 2 girts and 8 pegs,
each weighed by its member material (Douglas fir-larch, the pegs white oak)
with no part material, and every tenon, mortise cutter and bore consumed by
its boolean; the cut-list request names those 16 members; the width edit
12 -> 14 ft regenerates every member under the same ids (B6's named edit);
and a beam wider than its posts is a typed refusal.
"""

import uuid
from collections import Counter
from collections.abc import Iterator
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.cut_list import CutListPartRequest
from loft_wire.features import EvaluateTreeRequest
from loft_wire.parts import PRINCIPAL_HEADER

HEADERS = {PRINCIPAL_HEADER: "6f3f6b64-0000-4000-8000-0000000000f6"}
IN = 25.4


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _frame(**inputs: Any) -> dict[str, Any]:
    return {
        "type": "custom",
        "version": 1,
        "params": {
            "plugin_id": "loft.timber_frame",
            "plugin_version": "1.0.0",
            "inputs": inputs,
        },
    }


def _part(client: TestClient) -> tuple[str, int]:
    response = client.post(
        "/api/v1/parts",
        json={"name": f"B6 frame {uuid.uuid4()}", "length_unit": "in"},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"]), int(response.json()["tree_version"])


def _request(client: TestClient, part_id: str) -> EvaluateTreeRequest:
    response = client.get(
        f"/api/v1/parts/{part_id}/evaluation-request", headers=HEADERS
    )
    assert response.status_code == 200, response.text
    return EvaluateTreeRequest.model_validate_json(response.content)


def test_b6_expands_and_the_width_edit_keeps_every_id(client: TestClient) -> None:
    part_id, version = _part(client)
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={"name": "Frame", "feature": _frame(), "expected_tree_version": version},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    feature_id = response.json()["feature"]["id"]
    stored = response.json()["feature"]["feature"]["params"]
    assert stored["inputs"]["bent_count"] == 2
    assert stored["inputs"]["width_mm"] == pytest.approx(144 * IN)
    roles = Counter(m["role"] for m in stored["expansion"])
    assert {r: roles[r] for r in ("post", "tie_beam", "girt", "peg")} == {
        "post": 4,
        "tie_beam": 2,
        "girt": 2,
        "peg": 8,
    }

    before = _request(client, part_id)
    assert before.materials is not None
    assert before.materials.default_material is None
    assigned = Counter(e.material for e in before.materials.bodies)
    assert assigned == {"dfl_lumber": 8, "white_oak": 8}
    assert sum(e.feature.type == "boolean" for e in before.features) == 32

    cut = client.get(f"/api/v1/parts/{part_id}/cut-list-request", headers=HEADERS)
    assert cut.status_code == 200, cut.text
    members = CutListPartRequest.model_validate_json(cut.content).members
    assert Counter(m.title for m in members) == {
        "Post": 4,
        "Tie beam": 2,
        "Girt": 2,
        "Peg": 8,
    }
    assert {m.metadata.profile for m in members if m.role == "peg"} == {"Ø1"}

    response = client.patch(
        f"/api/v1/parts/{part_id}/features/{feature_id}",
        json={
            "expected_tree_version": before.tree_version,
            "feature": _frame(width_mm=168 * IN),
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    after = _request(client, part_id)
    assert [e.id for e in after.features] == [e.id for e in before.features]
    changed = {
        e.id
        for e, f in zip(before.features, after.features, strict=True)
        if e.feature != f.feature
    }
    # The right posts, the tie beams, and the right joints' sketches move.
    assert changed
    assert all(
        e.feature.type in ("sketch", "datum", "extrude")
        for e in after.features
        if e.id in changed
    )


def test_a_beam_wider_than_its_posts_is_a_typed_refusal(client: TestClient) -> None:
    part_id, version = _part(client)
    response = client.post(
        f"/api/v1/parts/{part_id}/features",
        json={
            "name": "Frame",
            "feature": _frame(post_profile="us_6x6", beam_profile="us_8x8"),
            "expected_tree_version": version,
        },
        headers=HEADERS,
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "plugin_input_unsupported"
    assert "wider than" in error["message"]
