"""PIPE-ALONG-PATH wire: the Pipe feature and the along-path datum."""

import uuid
from typing import Any

import pytest
from loft_wire.features import (
    BASE_BODY_AFFECTING_FEATURE_TYPES,
    BODY_AFFECTING_FEATURE_TYPES,
    FEATURE_REGISTRY,
    DatumAlongPathParams,
    DatumFeature,
    PipeFeature,
    feature_references,
)
from pydantic import ValidationError

SKETCH = "00000000-0000-0000-0000-00000000b001"
BODY = "00000000-0000-0000-0000-00000000b002"


def _curve(entity: str, sketch: str = SKETCH) -> dict[str, Any]:
    return {
        "kind": "sketch_curve",
        "sketch": {"kind": "feature", "feature_id": sketch},
        "entity": entity,
    }


def _edge() -> dict[str, Any]:
    point = {"x": 0.0, "y": 0.0, "z": 0.0}
    return {
        "kind": "subshape",
        "feature_id": BODY,
        "subshape_type": "edge",
        "selector": {
            "selector_version": 1,
            "signature": {
                "curve": "line",
                "end_a": point,
                "end_b": {"x": 10.0, "y": 0.0, "z": 0.0},
                "midpoint": {"x": 5.0, "y": 0.0, "z": 0.0},
                "length_mm": 10.0,
            },
        },
    }


def _pipe(**params: Any) -> PipeFeature:
    body = {"path": [_curve("e1")], "outer_diameter_mm": 20.0, "operation": "add"}
    body.update(params)
    loaded = FEATURE_REGISTRY.load("pipe", 1, body)
    assert isinstance(loaded, PipeFeature)
    return loaded


def test_a_pipe_is_a_body_creating_feature() -> None:
    assert "pipe" in BODY_AFFECTING_FEATURE_TYPES
    assert "pipe" in BASE_BODY_AFFECTING_FEATURE_TYPES
    pipe = _pipe()
    assert pipe.params.wall_thickness_mm is None
    assert pipe.params.merge is True


def test_a_wall_must_leave_a_bore() -> None:
    assert _pipe(wall_thickness_mm=9.99).params.wall_thickness_mm == 9.99
    with pytest.raises(ValidationError, match="leaves no bore"):
        _pipe(wall_thickness_mm=10.0)
    with pytest.raises(ValidationError):
        _pipe(wall_thickness_mm=0.0)
    with pytest.raises(ValidationError):
        _pipe(outer_diameter_mm=0.0)


def test_an_empty_path_is_refused() -> None:
    with pytest.raises(ValidationError):
        _pipe(path=[])


def test_each_picked_curve_is_a_dependency_with_its_slot_rule() -> None:
    other = str(uuid.UUID(int=7))
    pipe = _pipe(path=[_curve("e1"), _curve("e2", other), _edge()])
    refs = feature_references(pipe)
    assert [r.slot for r in refs] == ["path[0]", "path[1]", "path[2]"]
    assert [str(r.ref.feature_id) for r in refs] == [SKETCH, other, BODY]
    assert refs[0].allowed_types == frozenset({"sketch", "sketch_3d"})
    assert refs[2].allowed_types == BODY_AFFECTING_FEATURE_TYPES


def test_the_along_path_datum_names_its_curve() -> None:
    datum = DatumFeature.model_validate(
        {
            "type": "datum",
            "version": 1,
            "params": {"kind": "along_path", "path": _curve("e3"), "ratio": 0.25},
        }
    )
    assert isinstance(datum.params, DatumAlongPathParams)
    assert datum.params.measure == "ratio"
    (ref,) = feature_references(datum)
    assert ref.allowed_types == frozenset({"sketch", "sketch_3d"})
    with pytest.raises(ValidationError):
        DatumAlongPathParams.model_validate(
            {"kind": "along_path", "path": _curve("e3"), "ratio": 1.5}
        )
    with pytest.raises(ValidationError):
        DatumAlongPathParams.model_validate(
            {"kind": "along_path", "path": _curve("e3"), "distance_mm": -1.0}
        )
