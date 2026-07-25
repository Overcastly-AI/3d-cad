"""Per-request work bounds over HTTP — typed 422s, never 500s (audit G2).

The parse-level bounds themselves are unit-tested in
``packages/py-kit/tests/test_work_bounds.py``; this suite proves the SERVICE
behaviour: an over-bound compute request answers the py-kit 422 error envelope
(the scrubbed ``RequestValidationError`` rendering, or the route's typed
``ValidationApiError`` for the cross-field interference cap) — never a 500 and
never a started kernel computation. Plus the kernel-level defense-in-depth
twin of the pattern-count ceiling for direct kernel callers.
"""

import uuid
from typing import Any

import pytest
from build123d import Solid
from fastapi.testclient import TestClient
from geometry.kernel.pattern import PatternCountError, linear_pattern
from geometry.main import app
from py_kit.schemas.assemblies import MAX_INTERFERENCE_INSTANCES
from py_kit.schemas.features import MAX_PATTERN_COUNT
from py_kit.schemas.geometry import MIN_LINEAR_DEFLECTION

client = TestClient(app)

BOX_REQUEST: dict[str, Any] = {
    "shape": "box",
    "params": {"x": 10.0, "y": 10.0, "z": 10.0},
}


def _assert_envelope_422(response: Any) -> None:
    """A work-bound rejection is the standard 422 envelope, never a 500."""
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"


def test_tessellate_rejects_sub_floor_linear_deflection() -> None:
    response = client.post(
        "/api/v1/tessellate",
        json={**BOX_REQUEST, "linear_deflection": MIN_LINEAR_DEFLECTION / 1000.0},
    )
    _assert_envelope_422(response)


def test_export_rejects_sub_floor_angular_deflection() -> None:
    response = client.post(
        "/api/v1/export",
        json={**BOX_REQUEST, "format": "stl", "angular_deflection": 1e-9},
    )
    _assert_envelope_422(response)


def test_evaluate_rejects_pattern_count_over_ceiling() -> None:
    feature = {
        "id": str(uuid.uuid4()),
        "feature": {
            "type": "pattern",
            "version": 1,
            "params": {
                "pattern": {
                    "kind": "linear",
                    "direction": {"x": 1.0, "y": 0.0, "z": 0.0},
                    "spacing_mm": 10.0,
                    "count": MAX_PATTERN_COUNT + 1,
                }
            },
        },
    }
    response = client.post(
        "/api/v1/evaluate",
        json={
            "part_id": str(uuid.uuid4()),
            "tree_version": 1,
            "features": [feature],
        },
    )
    _assert_envelope_422(response)


def test_interference_rejects_over_instance_cap_with_typed_code() -> None:
    """The route-level N^2 cap: a typed 422 BEFORE any solve/boolean starts.

    Instances carry empty feature prefixes on purpose — if the handler check
    were missing/after the solve, this request would still be cheap, so the
    assertion is on the TYPED rejection, not on latency.
    """
    instances: list[dict[str, Any]] = [
        {
            "instance_id": str(uuid.uuid4()),
            "part_key": f"part-{index}@tip",
            "features": [],
        }
        for index in range(MAX_INTERFERENCE_INSTANCES + 1)
    ]
    response = client.post(
        "/api/v1/assembly/interference",
        json={
            "assembly_id": str(uuid.uuid4()),
            "version": 1,
            "instances": instances,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "interference_too_many_instances"


def test_interference_cap_allows_at_cap_requests_past_the_guard() -> None:
    """Exactly AT the cap the guard admits the request (the solve then answers
    a 200 with per-instance no-body outcomes — bodyless parts, empty clash
    list), proving the ceiling is exclusive of legitimate work."""
    instances: list[dict[str, Any]] = [
        {
            "instance_id": str(uuid.uuid4()),
            "part_key": f"part-{index}@tip",
            "features": [],
        }
        for index in range(MAX_INTERFERENCE_INSTANCES)
    ]
    response = client.post(
        "/api/v1/assembly/interference",
        json={
            "assembly_id": str(uuid.uuid4()),
            "version": 1,
            "instances": instances,
        },
    )
    assert response.status_code == 200
    assert response.json()["clashes"] == []


def test_assembly_evaluate_rejects_over_instance_parse_cap() -> None:
    from py_kit.schemas.assemblies import MAX_ASSEMBLY_INSTANCES

    instances: list[dict[str, Any]] = [
        {
            "instance_id": str(uuid.uuid4()),
            "part_key": f"part-{index}@tip",
            "features": [],
        }
        for index in range(MAX_ASSEMBLY_INSTANCES + 1)
    ]
    response = client.post(
        "/api/v1/assembly/evaluate",
        json={
            "assembly_id": str(uuid.uuid4()),
            "version": 1,
            "instances": instances,
        },
    )
    _assert_envelope_422(response)


def test_kernel_pattern_count_ceiling_defense_in_depth() -> None:
    """Direct kernel callers hit the same MAX_PATTERN_COUNT wall as the DTO
    parse — a typed PatternCountError before any copy/boolean loop."""
    body = Solid.make_box(10.0, 10.0, 10.0)
    with pytest.raises(PatternCountError, match="at most"):
        linear_pattern(body, (1.0, 0.0, 0.0), 20.0, MAX_PATTERN_COUNT + 1)
