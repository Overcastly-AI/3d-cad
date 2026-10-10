"""A feature sent with ``input_error`` is not built (PART-PARAMETERS step 2).

Documents sets ``EvaluatedFeatureInput.input_error`` when a parameter value
fails the feature's field or a name has no value (docs/RESEARCH.md §19).
Geometry builds nothing for that feature, reports it failed with that exact
error, and the features after it build against the body before it, as they do
after a suppressed feature.

Hand-checked numbers: the sketch is a 40 x 25 mm rectangle on XY. Extrude A
is 10 mm (z 0..10). Extrude B would add 10 mm on a datum at z=10 (to z=20) but
carries the input error. Extrude C adds 5 mm on the same datum (z 10..15). So
the body is 40 x 25 x 15 = 15000 mm^3 with max z 15. Had B built it would be
20000 mm^3 to z=20, and a strict-prefix stop at B would leave 10000 mm^3.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.main import app
from geometry.rebuild_cache import prefix_keys
from loft_wire.features import (
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    EvaluateTreeResult,
)
from pydantic import ValidationError

client = TestClient(app)

PART_ID = uuid.UUID("00000000-0000-0000-0000-00000000f1fa")
SKETCH_ID = uuid.UUID("00000000-0000-0000-0000-00000000f101")
EXTRUDE_A_ID = uuid.UUID("00000000-0000-0000-0000-00000000f102")
DATUM_ID = uuid.UUID("00000000-0000-0000-0000-00000000f103")
SKETCH_B_ID = uuid.UUID("00000000-0000-0000-0000-00000000f104")
EXTRUDE_B_ID = uuid.UUID("00000000-0000-0000-0000-00000000f105")
EXTRUDE_C_ID = uuid.UUID("00000000-0000-0000-0000-00000000f106")

#: OCCT volume of an analytic box is exact to round-off; 1e-6 mm^3 is far
#: below any modelling change and far above double round-off at 1e4.
VOLUME_TOLERANCE_MM3 = 1e-6

INPUT_ERROR: dict[str, Any] = {
    "code": "parameter_value_invalid",
    "message": "distance_mm = H - 30 resolves to -10 mm; it must be positive.",
}


def _rectangle(plane: dict[str, Any]) -> dict[str, Any]:
    corners = [(0.0, 0.0), (40.0, 0.0), (40.0, 25.0), (0.0, 25.0)]
    entities = [
        {
            "id": f"e{i + 1}",
            "kind": "line",
            "start": {"x": corners[i][0], "y": corners[i][1]},
            "end": {"x": corners[(i + 1) % 4][0], "y": corners[(i + 1) % 4][1]},
        }
        for i in range(4)
    ]
    constraints = [
        {
            "kind": "coincident",
            "a": {"entity": f"e{i + 1}", "point": "end"},
            "b": {"entity": f"e{(i + 1) % 4 + 1}", "point": "start"},
        }
        for i in range(4)
    ]
    return {"plane": plane, "entities": entities, "constraints": constraints}


def _feature(
    feature_id: uuid.UUID, feature: dict[str, Any], input_error: Any = None
) -> dict[str, Any]:
    item: dict[str, Any] = {"id": str(feature_id), "feature": feature}
    if input_error is not None:
        item["input_error"] = input_error
    return item


def _extrude(
    feature_id: uuid.UUID,
    profile_id: uuid.UUID,
    distance_mm: float,
    input_error: Any = None,
) -> dict[str, Any]:
    params = {
        "profile": {"kind": "feature", "feature_id": str(profile_id)},
        "distance_mm": distance_mm,
        "operation": "add",
        "direction": "normal",
    }
    return _feature(
        feature_id,
        {"type": "extrude", "version": 1, "params": params},
        input_error,
    )


def _request(input_error: Any) -> dict[str, Any]:
    datum_plane = {"kind": "feature", "feature_id": str(DATUM_ID)}
    datum = {"base": "XY", "offset_mm": 10.0, "flip": False}
    return {
        "part_id": str(PART_ID),
        "tree_version": 1,
        "features": [
            _feature(
                SKETCH_ID,
                {
                    "type": "sketch",
                    "version": 1,
                    "params": _rectangle({"kind": "datum_plane", "plane": "XY"}),
                },
            ),
            _extrude(EXTRUDE_A_ID, SKETCH_ID, 10.0),
            _feature(DATUM_ID, {"type": "datum", "version": 1, "params": datum}),
            _feature(
                SKETCH_B_ID,
                {"type": "sketch", "version": 1, "params": _rectangle(datum_plane)},
            ),
            _extrude(EXTRUDE_B_ID, SKETCH_B_ID, 10.0, input_error),
            _extrude(EXTRUDE_C_ID, SKETCH_B_ID, 5.0),
        ],
    }


def _post(payload: dict[str, Any]) -> EvaluateTreeResult:
    response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 200, response.text
    return EvaluateTreeResult.model_validate(response.json())


@pytest.mark.parametrize("code", ["parameter_value_invalid", "parameter_unresolved"])
def test_input_error_fails_the_feature_and_the_next_feature_builds(code: str) -> None:
    error = {**INPUT_ERROR, "code": code}
    result = _post(_request(error))

    assert [r.status for r in result.features] == [
        "ok",  # sketch
        "ok",  # extrude A
        "ok",  # datum
        "ok",  # sketch B
        "error",  # extrude B: not built, carries the input error verbatim
        "ok",  # extrude C builds on the body before B
    ]
    failed = result.features[4]
    assert failed.error is not None
    assert failed.error.code == code
    assert failed.error.message == INPUT_ERROR["message"]
    assert failed.data is None
    props = result.properties
    assert props is not None
    assert props.volume == pytest.approx(40.0 * 25.0 * 15.0, abs=VOLUME_TOLERANCE_MM3)
    assert props.bounding_box.max.z == pytest.approx(15.0, abs=1e-9)
    assert result.mesh_glb_id is not None


def test_without_input_error_the_same_tree_builds_every_feature() -> None:
    """The control: B builds, so the stack reaches z=20 (20000 mm^3)."""
    result = _post(_request(None))

    assert [r.status for r in result.features] == ["ok"] * 6
    props = result.properties
    assert props is not None
    assert props.volume == pytest.approx(40.0 * 25.0 * 20.0, abs=VOLUME_TOLERANCE_MM3)
    assert props.bounding_box.max.z == pytest.approx(20.0, abs=1e-9)


def test_a_feature_that_uses_the_unbuilt_output_fails_as_reference_unresolved() -> None:
    """Sketch B is sick, so extrude B has no profile: the existing
    ``reference_unresolved``, pinned upstream, and the strict prefix from there."""
    payload = _request(None)
    payload["features"][3]["input_error"] = INPUT_ERROR
    result = _post(payload)

    assert [r.status for r in result.features] == [
        "ok",
        "ok",
        "ok",
        "error",  # sketch B: the input error
        "error",  # extrude B: its profile was never solved
        "skipped",
    ]
    assert result.features[3].error is not None
    assert result.features[3].error.code == "parameter_value_invalid"
    downstream = result.features[4].error
    assert downstream is not None
    assert downstream.code == "reference_unresolved"
    assert downstream.upstream_feature_id == SKETCH_B_ID
    props = result.properties
    assert props is not None
    assert props.volume == pytest.approx(40.0 * 25.0 * 10.0, abs=VOLUME_TOLERANCE_MM3)


def test_input_error_is_deterministic() -> None:
    first = client.post("/api/v1/evaluate", json=_request(INPUT_ERROR))
    second = client.post("/api/v1/evaluate", json=_request(INPUT_ERROR))
    assert first.status_code == second.status_code == 200
    assert first.content == second.content


def test_input_error_is_absent_from_a_dump_when_none() -> None:
    item = EvaluatedFeatureInput.model_validate(
        _extrude(EXTRUDE_B_ID, SKETCH_B_ID, 10.0)
    )
    assert item.input_error is None
    assert "input_error" not in item.model_dump(mode="json")
    assert "input_error" not in item.model_dump_json()


def test_input_error_changes_the_rebuild_cache_key() -> None:
    """A sick feature must never be served the cached body of its healthy twin."""
    healthy = EvaluateTreeRequest.model_validate(_request(None))
    sick = EvaluateTreeRequest.model_validate(_request(INPUT_ERROR))
    healthy_keys = prefix_keys(healthy, capture_scope=())
    sick_keys = prefix_keys(sick, capture_scope=())
    assert healthy_keys[:5] == sick_keys[:5]
    assert healthy_keys[5] != sick_keys[5]


def test_input_error_refuses_a_code_that_is_not_an_input_code() -> None:
    with pytest.raises(ValidationError, match=r"input_error\.code must be one of"):
        EvaluatedFeatureInput.model_validate(
            _extrude(
                EXTRUDE_B_ID,
                SKETCH_B_ID,
                10.0,
                {"code": "boolean_failed", "message": "not an input error"},
            )
        )
    response = client.post(
        "/api/v1/evaluate",
        json=_request({"code": "profile_not_closed", "message": "x"}),
    )
    assert response.status_code == 422
