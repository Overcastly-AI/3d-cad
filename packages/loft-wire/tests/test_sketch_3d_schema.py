"""The 3D sketch's wire shape (SKETCH-3D): ids, relations and references."""

from typing import Any

import pytest
from loft_wire.features import (
    BODY_AFFECTING_FEATURE_TYPES,
    FEATURE_REGISTRY,
    FeatureResult,
    Sketch3DFeature,
    feature_references,
)
from pydantic import ValidationError

SKETCH = "00000000-0000-0000-0000-000000000001"
BODY = "00000000-0000-0000-0000-000000000002"


def _point(eid: str, snap: dict[str, Any] | None = None) -> dict[str, Any]:
    point: dict[str, Any] = {
        "id": eid,
        "kind": "point",
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
    }
    if snap is not None:
        point["snap"] = snap
    return point


def _line(eid: str, a: str, b: str) -> dict[str, Any]:
    return {"id": eid, "kind": "line", "start": a, "end": b}


def _load(entities: list[Any], constraints: list[Any] | None = None) -> Any:
    return FEATURE_REGISTRY.load(
        "sketch_3d", 1, {"entities": entities, "constraints": constraints or []}
    )


def test_a_skeleton_loads_and_dumps_without_absent_snaps() -> None:
    feature = _load(
        [_point("a", {"kind": "origin"}), _point("b"), _line("l", "a", "b")],
        [
            {"kind": "along", "line": "l", "axis": "z"},
            {"kind": "length", "line": "l", "value_mm": 10.0},
            {"kind": "distance", "a": "a", "b": "b", "value_mm": 10.0},
            {"kind": "coincident", "a": "a", "b": "b"},
            {"kind": "fixed", "point": "b"},
        ],
    )
    assert isinstance(feature, Sketch3DFeature)
    dumped = feature.params.model_dump(mode="json")
    assert "snap" not in dumped["entities"][1]
    assert dumped["entities"][0]["snap"] == {"kind": "origin"}


@pytest.mark.parametrize(
    ("entities", "constraints"),
    [
        ([_point("a"), _point("a")], []),
        ([_point("a"), _line("l", "a", "missing")], []),
        ([_point("a"), _line("l", "a", "a")], []),
        ([_point("a")], [{"kind": "fixed", "point": "zz"}]),
        ([_point("a"), _point("b")], [{"kind": "coincident", "a": "a", "b": "a"}]),
        ([_point("a")], [{"kind": "length", "line": "a", "value_mm": 1.0}]),
        (
            [_point("a"), _point("b"), _line("l", "a", "b")],
            [{"kind": "length", "line": "l", "value_mm": 0.0}],
        ),
    ],
)
def test_malformed_sketches_are_refused(
    entities: list[Any], constraints: list[Any]
) -> None:
    with pytest.raises(ValidationError):
        _load(entities, constraints)


def test_snaps_are_dependencies_with_their_slot_rules() -> None:
    edge = {
        "kind": "subshape",
        "feature_id": BODY,
        "subshape_type": "edge",
        "selector": {
            "selector_version": 1,
            "signature": {
                "curve": "line",
                "end_a": {"x": 0.0, "y": 0.0, "z": 0.0},
                "end_b": {"x": 0.0, "y": 0.0, "z": 10.0},
                "midpoint": {"x": 0.0, "y": 0.0, "z": 5.0},
                "length_mm": 10.0,
            },
        },
    }
    feature = _load(
        [
            _point("o", {"kind": "origin"}),
            _point(
                "s",
                {
                    "kind": "sketch_point",
                    "sketch": {"kind": "feature", "feature_id": SKETCH},
                    "entity": "e1",
                    "point": "end",
                },
            ),
            _point("v", {"kind": "vertex", "edge": edge, "end": "b"}),
        ]
    )
    refs = feature_references(feature)
    assert [r.slot for r in refs] == ["snap:s", "snap:v"]
    assert [str(r.ref.feature_id) for r in refs] == [SKETCH, BODY]
    assert refs[0].allowed_types == frozenset({"sketch", "sketch_3d"})
    assert refs[1].allowed_types == BODY_AFFECTING_FEATURE_TYPES
    assert "sketch_3d" not in BODY_AFFECTING_FEATURE_TYPES


def test_the_result_payload_is_discriminated_by_kind() -> None:
    result = FeatureResult.model_validate(
        {
            "feature_id": SKETCH,
            "status": "ok",
            "data": {
                "kind": "solved_sketch_3d",
                "points": [{"id": "a", "position": {"x": 1.0, "y": 2.0, "z": 3.0}}],
                "dof": 3,
            },
        }
    )
    assert result.data is not None and result.data.kind == "solved_sketch_3d"
