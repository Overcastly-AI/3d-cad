"""In-context links on the wire (ASM-A3-IN-CONTEXT).

- a projection names exactly one source: a body edge or an in-context edge;
- an in-context link round-trips, adds no feature dependency, and a sketch
  without one dumps exactly as before;
- ``carry_resolved`` keeps the stored value for an unchanged link only;
- ``apply_resolved`` writes only where the link still names the same
  assembly and occurrence.
"""

import copy
import uuid
from typing import Any

import pytest
from loft_wire.features import FEATURE_REGISTRY, feature_references
from loft_wire.in_context import (
    InContextResolvedItem,
    apply_resolved,
    carry_resolved,
    linked_parts,
)
from loft_wire.sketch import SketchDefinition
from pydantic import ValidationError

ASM = str(uuid.UUID(int=1))
HOST = str(uuid.UUID(int=2))
OCC = str(uuid.UUID(int=3))
PART = str(uuid.UUID(int=4))
EDGE = {
    "subshape_type": "edge",
    "curve": "circle",
    "end_a": {"x": 1.75, "y": 0.0, "z": 8.0},
    "end_b": {"x": 1.75, "y": 0.0, "z": 8.0},
    "midpoint": {"x": -1.75, "y": 0.0, "z": 8.0},
    "length_mm": 10.995574287564276,
    "adjacent_faces": None,
    "topo_name": None,
    "end_a_topo_name": None,
}


def _resolved(y: float) -> dict[str, Any]:
    return {
        "kind": "circle",
        "center": {"x": 12.5, "y": y, "z": -8.0},
        "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
        "radius": 1.75,
    }


def _sketch(y: float | None = 40.0, occurrence: str = OCC) -> dict[str, Any]:
    link: dict[str, Any] = {
        "assembly_id": ASM,
        "host_occurrence_id": HOST,
        "occurrence_id": occurrence,
        "part_id": PART,
        "edge": EDGE,
    }
    if y is not None:
        link["resolved"] = _resolved(y)
    return {
        "plane": {"kind": "datum_plane", "plane": "XY"},
        "entities": [
            {
                "id": "p1",
                "construction": False,
                "projection": {"in_context": link},
                "kind": "circle",
                "center": {"x": 12.5, "y": 40.0},
                "radius": 1.75,
            }
        ],
        "constraints": [],
    }


def test_a_link_round_trips_and_adds_no_dependency() -> None:
    raw = _sketch()
    params = {k: v for k, v in raw.items() if k != "plane"}
    assert SketchDefinition.model_validate(params).model_dump(mode="json") == params
    feature = FEATURE_REGISTRY.load("sketch", 1, raw)
    assert feature_references(feature) == ()
    assert linked_parts(raw) == {uuid.UUID(PART)}


def test_a_projection_names_exactly_one_source() -> None:
    both = _sketch()
    both["entities"][0]["projection"]["edge"] = {
        "kind": "subshape",
        "feature_id": str(uuid.uuid4()),
        "subshape_type": "edge",
        "selector": {"selector_version": 1, "signature": EDGE},
    }
    with pytest.raises(ValidationError, match="either a body edge"):
        FEATURE_REGISTRY.load("sketch", 1, both)
    neither = _sketch()
    neither["entities"][0]["projection"] = {}
    with pytest.raises(ValidationError, match="either a body edge"):
        FEATURE_REGISTRY.load("sketch", 1, neither)


def test_carry_keeps_the_stored_value_for_an_unchanged_link() -> None:
    stored = _sketch(45.0)
    incoming = carry_resolved(stored, _sketch(40.0))
    link = incoming["entities"][0]["projection"]["in_context"]
    assert link["resolved"] == _resolved(45.0)
    # A link to another component keeps its own.
    other = carry_resolved(stored, _sketch(40.0, occurrence=str(uuid.uuid4())))
    assert other["entities"][0]["projection"]["in_context"]["resolved"] == _resolved(
        40.0
    )
    # Nothing stored, nothing carried.
    assert carry_resolved(_sketch(None), _sketch(40.0)) == _sketch(40.0)


def test_apply_writes_only_to_the_same_link() -> None:
    params = copy.deepcopy(_sketch(40.0))
    item = InContextResolvedItem.model_validate(
        {
            "feature_id": str(uuid.uuid4()),
            "entity_id": "p1",
            "assembly_id": ASM,
            "occurrence_id": OCC,
            "resolved": _resolved(45.0),
        }
    )
    assert apply_resolved(params, item) is True
    assert params["entities"][0]["projection"]["in_context"]["resolved"] == (
        _resolved(45.0)
    )
    assert apply_resolved(params, item) is False  # already there
    moved = item.model_copy(update={"occurrence_id": uuid.uuid4()})
    assert apply_resolved(params, moved) is False
    gone = item.model_copy(update={"entity_id": "p9"})
    assert apply_resolved(params, gone) is False
