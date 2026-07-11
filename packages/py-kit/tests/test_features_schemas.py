"""py_kit.schemas.features — envelopes, refs, registry/upcast totality.

The worked example asserted here is docs/design/feature-tree.md §6 verbatim
(40 x 25 mm rectangle on XY, extruded 10 mm) — the same rows the documents
service round-trips in its own suite.
"""

import uuid
from typing import Any, Literal

import pytest
from py_kit.schemas.features import (
    FEATURE_REGISTRY,
    DatumPlaneRef,
    ExtrudeFeature,
    Feature,
    FeatureCreate,
    FeatureRef,
    FeatureSchemaError,
    FeatureTypeRegistry,
    FeatureUpdate,
    SketchFeature,
    SketchParamsV1,
    UnknownFeatureVersionError,
    feature_references,
    iter_feature_refs,
)
from pydantic import BaseModel, TypeAdapter, ValidationError

SKETCH_ID = uuid.UUID("6f3f6b64-0000-4000-8000-0000000000aa")

#: §6 worked example — sketch params, verbatim.
SKETCH_PARAMS: dict[str, Any] = {
    "plane": {"kind": "datum_plane", "plane": "XY"},
    "entities": [
        {
            "id": "e1",
            "kind": "line",
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 40.0, "y": 0.0},
        },
        {
            "id": "e2",
            "kind": "line",
            "start": {"x": 40.0, "y": 0.0},
            "end": {"x": 40.0, "y": 25.0},
        },
        {
            "id": "e3",
            "kind": "line",
            "start": {"x": 40.0, "y": 25.0},
            "end": {"x": 0.0, "y": 25.0},
        },
        {
            "id": "e4",
            "kind": "line",
            "start": {"x": 0.0, "y": 25.0},
            "end": {"x": 0.0, "y": 0.0},
        },
    ],
    "constraints": [
        {
            "kind": "coincident",
            "a": {"entity": "e1", "point": "end"},
            "b": {"entity": "e2", "point": "start"},
        },
        {"kind": "horizontal", "entity": "e1"},
        {"kind": "vertical", "entity": "e2"},
        {"kind": "distance", "entity": "e1", "value_mm": 40.0},
        {"kind": "distance", "entity": "e2", "value_mm": 25.0},
    ],
}

#: §6 worked example — extrude params, verbatim (feature id substituted).
EXTRUDE_PARAMS: dict[str, Any] = {
    "profile": {"kind": "feature", "feature_id": str(SKETCH_ID)},
    "distance_mm": 10.0,
    "operation": "add",
    "direction": "normal",
}

FEATURE_ADAPTER: TypeAdapter[SketchFeature | ExtrudeFeature] = TypeAdapter(Feature)


# --- envelopes (§1.3) -------------------------------------------------------------


def test_worked_example_sketch_round_trips_verbatim() -> None:
    envelope = FEATURE_ADAPTER.validate_python(
        {"type": "sketch", "version": 1, "params": SKETCH_PARAMS}
    )
    assert isinstance(envelope, SketchFeature)
    assert envelope.model_dump(mode="json") == {
        "type": "sketch",
        "version": 1,
        "params": SKETCH_PARAMS,
    }


def test_worked_example_extrude_round_trips_verbatim() -> None:
    envelope = FEATURE_ADAPTER.validate_python(
        {"type": "extrude", "version": 1, "params": EXTRUDE_PARAMS}
    )
    assert isinstance(envelope, ExtrudeFeature)
    assert envelope.params.profile.feature_id == SKETCH_ID
    assert envelope.model_dump(mode="json") == {
        "type": "extrude",
        "version": 1,
        "params": EXTRUDE_PARAMS,
    }


def test_unknown_feature_type_rejected() -> None:
    with pytest.raises(ValidationError):
        FEATURE_ADAPTER.validate_python({"type": "fillet", "version": 1, "params": {}})


def test_extrude_requires_positive_distance() -> None:
    bad = {**EXTRUDE_PARAMS, "distance_mm": 0.0}
    with pytest.raises(ValidationError):
        FEATURE_ADAPTER.validate_python(
            {"type": "extrude", "version": 1, "params": bad}
        )


def test_extrude_direction_defaults_to_normal() -> None:
    params = {k: v for k, v in EXTRUDE_PARAMS.items() if k != "direction"}
    envelope = FEATURE_ADAPTER.validate_python(
        {"type": "extrude", "version": 1, "params": params}
    )
    assert isinstance(envelope, ExtrudeFeature)
    assert envelope.params.direction == "normal"


def test_geom_ref_discriminates_on_kind() -> None:
    params = SketchParamsV1.model_validate(
        {
            "plane": {"kind": "datum_plane", "plane": "XZ"},
            "entities": [],
            "constraints": [],
        }
    )
    assert isinstance(params.plane, DatumPlaneRef)
    with pytest.raises(ValidationError):
        SketchParamsV1.model_validate(
            {"plane": {"kind": "subshape"}, "entities": [], "constraints": []}
        )


def test_feature_update_requires_something_to_update() -> None:
    with pytest.raises(ValidationError):
        FeatureUpdate.model_validate({"expected_tree_version": 0})
    FeatureUpdate.model_validate({"expected_tree_version": 0, "name": "Sketch2"})


def test_feature_create_rejects_negative_expected_version() -> None:
    with pytest.raises(ValidationError):
        FeatureCreate.model_validate(
            {
                "name": "Sketch1",
                "feature": {"type": "sketch", "version": 1, "params": SKETCH_PARAMS},
                "expected_tree_version": -1,
            }
        )


# --- reference helpers (§2.2/§2.3) --------------------------------------------------


def _extrude() -> ExtrudeFeature:
    return ExtrudeFeature.model_validate(
        {"type": "extrude", "version": 1, "params": EXTRUDE_PARAMS}
    )


def _sketch() -> SketchFeature:
    return SketchFeature.model_validate(
        {"type": "sketch", "version": 1, "params": SKETCH_PARAMS}
    )


def test_extrude_profile_slot_accepts_sketches_only() -> None:
    (reference,) = feature_references(_extrude())
    assert reference.slot == "profile"
    assert reference.ref.feature_id == SKETCH_ID
    assert reference.allowed_types == frozenset({"sketch"})


def test_sketch_on_datum_plane_has_no_feature_refs() -> None:
    assert feature_references(_sketch()) == ()
    assert list(iter_feature_refs(_sketch())) == []


def test_sketch_plane_feature_ref_accepts_no_type_in_v1() -> None:
    sketch = SketchFeature.model_validate(
        {
            "type": "sketch",
            "version": 1,
            "params": {
                "plane": {"kind": "feature", "feature_id": str(SKETCH_ID)},
                "entities": [],
                "constraints": [],
            },
        }
    )
    (reference,) = feature_references(sketch)
    assert reference.slot == "plane"
    assert reference.allowed_types == frozenset()


def test_slot_map_drift_fails_loudly() -> None:
    """A ref the generic walk finds but the slot map misses must raise, never
    silently drop a dependency edge (self-check in feature_references)."""
    smuggled = SketchParamsV1.model_construct(
        plane=DatumPlaneRef(kind="datum_plane", plane="XY"),
        entities=[FeatureRef(kind="feature", feature_id=SKETCH_ID)],  # pyright: ignore[reportArgumentType]
        constraints=[],
    )
    sketch = SketchFeature.model_construct(type="sketch", version=1, params=smuggled)
    with pytest.raises(FeatureSchemaError, match="out of sync"):
        feature_references(sketch)


# --- registry + upcasts (§1.4) ------------------------------------------------------


class _WidgetParamsV2(BaseModel):
    size: int
    color: str


class _WidgetV2(BaseModel):
    type: Literal["widget"]
    version: Literal[2]
    params: _WidgetParamsV2


def test_module_registry_serves_current_versions() -> None:
    assert FEATURE_REGISTRY.current_version("sketch") == 1
    assert FEATURE_REGISTRY.current_version("extrude") == 1
    loaded = FEATURE_REGISTRY.load("extrude", 1, EXTRUDE_PARAMS)
    assert isinstance(loaded, ExtrudeFeature)
    with pytest.raises(UnknownFeatureVersionError):
        FEATURE_REGISTRY.current_version("fillet")


def test_upcast_chain_reaches_current_version() -> None:
    """The documented path (design §1.4): a v1 row lazily upcast on read,
    the new required field filled from the old version's implicit behavior."""
    registry: FeatureTypeRegistry[_WidgetV2] = FeatureTypeRegistry()
    registry.register(_WidgetV2)
    registry.register_upcast("widget", 1, lambda params: {**params, "color": "gray"})
    registry.validate_chains()

    loaded = registry.load("widget", 1, {"size": 3})
    assert loaded.version == 2
    assert loaded.params == _WidgetParamsV2(size=3, color="gray")
    # Current-version rows pass through untouched.
    assert registry.load("widget", 2, {"size": 1, "color": "red"}).params.color == "red"


def test_chain_gaps_are_rejected_at_validate_time() -> None:
    """Totality enforcement: a registered chain with a hole cannot import."""

    class _GadgetV3(BaseModel):
        type: Literal["gadget"]
        version: Literal[3]
        params: _WidgetParamsV2

    registry: FeatureTypeRegistry[_GadgetV3] = FeatureTypeRegistry()
    registry.register(_GadgetV3)
    registry.register_upcast(
        "gadget", 1, lambda params: params
    )  # 1→2 only; 2→3 missing
    with pytest.raises(FeatureSchemaError, match="gaps"):
        registry.validate_chains()


def test_upcast_beyond_current_version_rejected() -> None:
    registry: FeatureTypeRegistry[_WidgetV2] = FeatureTypeRegistry()
    registry.register(_WidgetV2)
    registry.register_upcast("widget", 2, lambda params: params)
    with pytest.raises(FeatureSchemaError, match="beyond"):
        registry.validate_chains()


def test_upcast_for_unregistered_type_rejected() -> None:
    registry: FeatureTypeRegistry[_WidgetV2] = FeatureTypeRegistry()
    registry.register_upcast("widget", 1, lambda params: params)
    with pytest.raises(FeatureSchemaError, match="unregistered"):
        registry.validate_chains()


def test_missing_upcast_link_fails_at_load() -> None:
    """A stored version with no registered path to current raises — the row
    is unloadable and must fail loudly, never guess."""
    registry: FeatureTypeRegistry[_WidgetV2] = FeatureTypeRegistry()
    registry.register(_WidgetV2)
    registry.validate_chains()
    with pytest.raises(UnknownFeatureVersionError, match="no upcast"):
        registry.load("widget", 1, {"size": 3})


def test_params_newer_than_current_fail_at_load() -> None:
    registry: FeatureTypeRegistry[_WidgetV2] = FeatureTypeRegistry()
    registry.register(_WidgetV2)
    with pytest.raises(UnknownFeatureVersionError, match="NEWER"):
        registry.load("widget", 3, {"size": 3})


def test_duplicate_registrations_rejected() -> None:
    registry: FeatureTypeRegistry[_WidgetV2] = FeatureTypeRegistry()
    registry.register(_WidgetV2)
    with pytest.raises(FeatureSchemaError, match="twice"):
        registry.register(_WidgetV2)
    registry.register_upcast("widget", 1, lambda params: params)
    with pytest.raises(FeatureSchemaError, match="twice"):
        registry.register_upcast("widget", 1, lambda params: params)
