"""Twisted prism 1.0.0: the expansion, placed exactly (kernel-free).

``services/geometry/goldens/plugin-twisted-prism-v1-square20-hole-r3-h30-30deg``
is the expansion of one stored twisted prism over the profile of the legacy
twisted-extrude golden. :func:`golden_request` rebuilds it from the plugin and
the first test asserts the committed ``model.json`` is exactly that; the
geometry half (the same solid as the legacy twisted extrude) is
``services/geometry/tests/test_plugin_twisted_prism.py``. Regenerate after a
deliberate change with ``python test_twisted_prism.py > model.json``.
"""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, PluginError, canonical_inputs, expand
from loft_wire.features import (
    AUTHORED_FEATURES,
    AuthoredEnvelope,
    DatumFeature,
    DatumMidplaneParams,
    DatumOffsetFromParams,
    DatumOffsetParams,
    DatumPlaneRef,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    FeatureEnvelope,
    FeatureRef,
    SketchFeature,
    SketchParamsV1,
    SweepFeature,
)
from loft_wire.sketch import SketchLine

PLUGIN = REGISTRY.get("loft.twisted_prism", "1.0.0")

GOLDENS = Path(__file__).resolve().parents[3] / "services" / "geometry" / "goldens"
LEGACY_GOLDEN = GOLDENS / "sweep-twist-square20-hole-r3-h30-30deg"
GOLDEN = GOLDENS / "plugin-twisted-prism-v1-square20-hole-r3-h30-30deg"

PART_ID = uuid.UUID("00000000-0000-0000-0000-00000000071d")
PROFILE_ID = uuid.UUID("00000000-0000-0000-0000-0000000007d1")
PRISM_ID = uuid.UUID("00000000-0000-0000-0000-0000000007d2")

#: The stored inputs: the legacy golden's numbers (30 mm, 30 deg, axis at the
#: sketch origin, along the normal, joined).
INPUTS: dict[str, Any] = {
    "profile": {"kind": "feature", "feature_id": str(PROFILE_ID)},
    "distance_mm": 30.0,
    "twist_angle_deg": 30.0,
}


def profile_sketch() -> FeatureEnvelope:
    """The legacy golden's profile: a 20 mm square with an r3 hole at (4, 0)."""
    legacy: dict[str, Any] = json.loads((LEGACY_GOLDEN / "model.json").read_text())
    envelope = AUTHORED_FEATURES.load(
        "sketch", 1, legacy["features"][0]["feature"]["params"]
    )
    assert envelope.type == "sketch"
    return envelope


def golden_request() -> EvaluateTreeRequest:
    """The base features documents would send geometry for this part."""
    plugin = REGISTRY.get("loft.twisted_prism", "1.0.0")
    profile = profile_sketch()
    custom = AUTHORED_FEATURES.load(
        "custom",
        1,
        {
            "plugin_id": "loft.twisted_prism",
            "plugin_version": "1.0.0",
            "inputs": INPUTS,
        },
    )
    assert custom.type == "custom"
    inputs = canonical_inputs(plugin.manifest, custom.params.inputs)
    members = expand(plugin, PRISM_ID, inputs, {PROFILE_ID: profile})
    return EvaluateTreeRequest(
        part_id=PART_ID,
        tree_version=1,
        features=[
            EvaluatedFeatureInput(id=PROFILE_ID, feature=profile),
            *(EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in members),
        ],
        linear_deflection=0.1,
    )


def test_the_golden_is_the_plugins_expansion() -> None:
    """``model.json`` of the geometry golden is exactly what v1 expands to: a
    change to v1's expansion fails here, before it can reach a stored part."""
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDEN / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == golden_request().model_dump(mode="json")


def _sketch(plane: Any) -> SketchFeature:
    return SketchFeature(
        type="sketch",
        version=1,
        params=SketchParamsV1(plane=plane, entities=[], constraints=[]),
    )


def _datum(params: Any) -> DatumFeature:
    return DatumFeature(type="datum", version=1, params=params)


def _expand(
    earlier: dict[uuid.UUID, AuthoredEnvelope], **inputs: Any
) -> list[ExpandedMember]:
    raw: dict[str, Any] = {"profile": FeatureRef(kind="feature", feature_id=PROFILE_ID)}
    raw.update(inputs)
    return expand(PLUGIN, PRISM_ID, canonical_inputs(PLUGIN.manifest, raw), earlier)


def _path(members: list[ExpandedMember]) -> tuple[Any, tuple[float, ...]]:
    path = next(m for m in members if m.role == "path").feature
    assert isinstance(path, SketchFeature)
    (line,) = path.params.entities
    assert isinstance(line, SketchLine)
    return path.params.plane, (line.start.x, line.start.y, line.end.x, line.end.y)


def test_an_off_axis_twist_puts_the_path_on_an_offset_plane() -> None:
    """XY profile, axis at (3, 5), reversed: the path plane is XZ slid to y = 5
    (XZ's normal is -Y, so offset -5), and the line runs from (3, 0) down 12."""
    members = _expand(
        {PROFILE_ID: _sketch(DatumPlaneRef(kind="datum_plane", plane="XY"))},
        distance_mm=12.0,
        axis_x_mm=3.0,
        axis_y_mm=5.0,
        direction="reverse",
        operation="cut",
        body="new_body",
    )
    assert [(m.role, m.index) for m in members] == [
        ("axis_plane", 0),
        ("path", 0),
        ("sweep", 0),
    ]
    datum = members[0].feature
    assert isinstance(datum, DatumFeature)
    assert datum.params == DatumOffsetParams(kind="offset", base="XZ", offset_mm=-5.0)
    plane, line = _path(members)
    assert plane == FeatureRef(kind="feature", feature_id=members[0].id)
    assert line == (3.0, 0.0, 3.0, -12.0)
    sweep = members[2].feature
    assert isinstance(sweep, SweepFeature)
    assert sweep.params.operation == "cut" and sweep.params.merge is False
    assert sweep.params.path == FeatureRef(kind="feature", feature_id=members[1].id)


def test_a_yz_profile_on_a_chained_flipped_offset() -> None:
    """YZ slid 10, then slid 4 more and flipped (the kernel's order: offset,
    then flip): the profile plane is x = 14 with normal -X and sketch +v = -Z.
    The axis at sketch (2, 1) is world (14, 2, -1); the path runs on XZ slid
    to y = 2 (offset -2) from (14, -1) to (14 - 7, -1)."""
    plane_a, plane_b = uuid.uuid4(), uuid.uuid4()
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {
        plane_a: _datum(DatumOffsetParams(kind="offset", base="YZ", offset_mm=10.0)),
        plane_b: _datum(
            DatumOffsetFromParams(
                kind="offset_from",
                base=FeatureRef(kind="feature", feature_id=plane_a),
                offset_mm=4.0,
                flip=True,
            )
        ),
        PROFILE_ID: _sketch(FeatureRef(kind="feature", feature_id=plane_b)),
    }
    members = _expand(earlier, distance_mm=7.0, axis_x_mm=2.0, axis_y_mm=1.0)
    datum = members[0].feature
    assert isinstance(datum, DatumFeature)
    assert datum.params == DatumOffsetParams(kind="offset", base="XZ", offset_mm=-2.0)
    assert _path(members)[1] == (14.0, -1.0, 7.0, -1.0)


def test_a_profile_on_the_origin_xz_plane_paths_on_yz() -> None:
    members = _expand(
        {PROFILE_ID: _sketch(DatumPlaneRef(kind="datum_plane", plane="XZ"))},
        distance_mm=5.0,
    )
    assert [m.role for m in members] == ["path", "sweep"]
    plane, line = _path(members)
    assert plane == DatumPlaneRef(kind="datum_plane", plane="YZ")
    assert line == (0.0, 0.0, -5.0, 0.0)


def test_unsupported_planes_and_profiles_are_typed() -> None:
    face_plane = uuid.uuid4()
    midplane = _datum(
        DatumMidplaneParams(
            kind="midplane",
            a=DatumPlaneRef(kind="datum_plane", plane="XY"),
            b=DatumPlaneRef(kind="datum_plane", plane="XY"),
        )
    )
    with pytest.raises(PluginError) as unsupported:
        _expand(
            {
                face_plane: midplane,
                PROFILE_ID: _sketch(FeatureRef(kind="feature", feature_id=face_plane)),
            }
        )
    assert unsupported.value.code == "plugin_input_unsupported"
    with pytest.raises(PluginError) as not_a_sketch:
        _expand({PROFILE_ID: midplane})
    assert not_a_sketch.value.code == "plugin_input_invalid"


def test_the_manifest_carries_what_the_form_needs() -> None:
    manifest = PLUGIN.manifest
    assert (manifest.title, manifest.group) == ("Twisted prism", "build")
    kinds = {item.name: item.kind for item in manifest.inputs}
    assert kinds == {
        "profile": "profile",
        "distance_mm": "length",
        "twist_angle_deg": "angle",
        "axis_x_mm": "length",
        "axis_y_mm": "length",
        "direction": "choice",
        "operation": "choice",
        "body": "choice",
    }


if __name__ == "__main__":
    print(golden_request().model_dump_json(indent=2, exclude_defaults=True))
