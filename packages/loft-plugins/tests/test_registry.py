"""The registry: pinned versions, input checks, caps and member validation."""

import json
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import (
    REGISTRY,
    ExpandInputs,
    Member,
    Plugin,
    PluginError,
    PluginRegistry,
    canonical_inputs,
    expand,
)
from loft_plugins.testing import BLOCKS_V1, BLOCKS_V2, expand_v1
from loft_wire.features import (
    DatumFeature,
    DatumOffsetParams,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureRef,
)
from loft_wire.plugins import (
    MAX_PLUGIN_EXPANSION,
    PluginCatalog,
    PluginMemberRole,
    member_id,
    member_key,
    semver_key,
)

GOLDEN_V1 = (
    Path(__file__).resolve().parent / "goldens" / "test-blocks-v1.0.0-count3.json"
)
FEATURE_ID = uuid.UUID("00000000-0000-0000-0000-00000000b10c")
INPUTS: dict[str, Any] = {"width_mm": 12.0, "depth_mm": 4.0, "count": 3}


def _expansion_bytes(registry: PluginRegistry, version: str) -> bytes:
    plugin = registry.get("test.blocks", version)
    members = expand(plugin, FEATURE_ID, canonical_inputs(plugin.manifest, INPUTS), {})
    dumped = [member.model_dump(mode="json") for member in members]
    return (json.dumps(dumped, indent=2) + "\n").encode()


def test_a_v2_release_leaves_a_v1_feature_byte_identical() -> None:
    """Acceptance: the v1-pinned expansion is its golden, byte for byte, with
    v1 alone and after v2 is released; v2 really is a different expansion."""
    v1_only = PluginRegistry([BLOCKS_V1])
    both = PluginRegistry([BLOCKS_V1, BLOCKS_V2])
    golden = GOLDEN_V1.read_bytes()
    assert _expansion_bytes(v1_only, "1.0.0") == golden
    assert _expansion_bytes(both, "1.0.0") == golden
    assert _expansion_bytes(both, "2.0.0") != golden
    assert both.latest("test.blocks").manifest.version == "2.0.0"


def test_member_ids_are_stable_names() -> None:
    assert member_key(FEATURE_ID, "block", 2) == f"{FEATURE_ID}/block/2"
    assert member_id(FEATURE_ID, "block", 2) == uuid.uuid5(
        uuid.UUID("6c0f7e52-3b1d-5f0e-9a4c-1d2e3f405162"), f"{FEATURE_ID}/block/2"
    )
    golden: list[dict[str, Any]] = json.loads(GOLDEN_V1.read_text())
    assert [(m["role"], m["index"]) for m in golden] == [
        ("profile", 0),
        ("block", 0),
        ("profile", 1),
        ("block", 1),
        ("profile", 2),
        ("block", 2),
    ]
    assert all(
        m["id"] == str(member_id(FEATURE_ID, m["role"], m["index"])) for m in golden
    )


def test_the_catalog_lists_every_version_newest_first() -> None:
    catalog = PluginRegistry([BLOCKS_V2, BLOCKS_V1]).catalog()
    assert [(m.id, m.version, m.latest) for m in catalog.plugins] == [
        ("test.blocks", "2.0.0", True),
        ("test.blocks", "1.0.0", False),
    ]
    served = PluginCatalog.model_validate(REGISTRY.catalog().model_dump(mode="json"))
    assert [(m.id, m.version, m.latest) for m in served.plugins] == [
        ("loft.deck", "1.0.0", True),
        ("loft.twisted_prism", "1.0.0", True),
        ("loft.wall", "1.0.0", True),
    ]


def test_a_release_cannot_be_registered_twice() -> None:
    with pytest.raises(ValueError, match="registered twice"):
        PluginRegistry([BLOCKS_V1, BLOCKS_V1])


def test_unknown_plugins_and_versions_are_typed() -> None:
    with pytest.raises(PluginError) as missing:
        REGISTRY.get("acme.deck", "1.0.0")
    assert missing.value.code == "plugin_not_found"
    with pytest.raises(PluginError) as version:
        REGISTRY.get("loft.twisted_prism", "9.0.0")
    assert version.value.code == "plugin_version_not_found"
    assert semver_key("1.10.0") > semver_key("1.9.3")


@pytest.mark.parametrize(
    ("inputs", "name"),
    [
        ({"width_mm": 0.0}, "width_mm"),  # exclusive minimum
        ({"count": 51}, "count"),
        ({"count": 2.5}, "count"),
        ({"width_mm": "wide"}, "width_mm"),
        ({"colour": 1}, "colour"),
    ],
)
def test_inputs_are_checked_against_the_manifest(
    inputs: dict[str, Any], name: str
) -> None:
    with pytest.raises(PluginError) as refused:
        canonical_inputs(BLOCKS_V1.manifest, inputs)
    assert refused.value.code == "plugin_input_invalid"
    assert refused.value.input == name


def test_inputs_get_defaults_and_their_unit_type() -> None:
    """A length given as ``30`` is stored ``30.0`` (so a formula can drive it as
    a length), a count ``2.0`` as ``2``; missing inputs take their defaults."""
    out = canonical_inputs(BLOCKS_V1.manifest, {"width_mm": 30, "count": 2.0})
    assert out == {"width_mm": 30.0, "depth_mm": 5.0, "count": 2}
    assert isinstance(out["width_mm"], float) and isinstance(out["count"], int)
    # kinds only, before formulas resolve: an out-of-range number is kept
    assert (
        canonical_inputs(BLOCKS_V1.manifest, {"count": 99}, bounds=False)["count"] == 99
    )


def _plugin(expander: Any) -> Plugin:
    manifest = BLOCKS_V1.manifest.model_copy(
        update={
            "id": "test.bad",
            "members": [PluginMemberRole(role="block", title="Block")],
        }
    )
    return Plugin(manifest, expander)


def _block(inputs: ExpandInputs, index: int, profile: FeatureRef) -> Member:
    return Member(
        "block",
        index,
        ExtrudeFeature(
            type="extrude",
            version=1,
            params=ExtrudeParamsV1(profile=profile, distance_mm=1.0, operation="add"),
        ),
    )


def test_over_5000_members_is_a_typed_error() -> None:
    def endless(inputs: ExpandInputs) -> Iterator[Member]:
        n = 0
        while True:
            yield Member(
                "block",
                n,
                DatumFeature(
                    type="datum",
                    version=1,
                    params=DatumOffsetParams(kind="offset", base="XY", offset_mm=n),
                ),
            )
            n += 1

    with pytest.raises(PluginError) as refused:
        expand(_plugin(endless), FEATURE_ID, {}, {})
    assert refused.value.code == "plugin_expansion_too_large"
    assert str(MAX_PLUGIN_EXPANSION) in refused.value.message


def test_over_the_time_limit_is_a_typed_error() -> None:
    def slow(inputs: ExpandInputs) -> list[Member]:
        time.sleep(0.05)
        return []

    with pytest.raises(PluginError) as refused:
        expand(_plugin(slow), FEATURE_ID, {}, {}, time_limit_s=0.01)
    assert refused.value.code == "plugin_expansion_timeout"


def test_members_get_the_authoring_checks() -> None:
    """Undeclared role, a repeated (role, index), a reference to nothing, a
    reference to a feature of the wrong type, and a plugin bug are all
    ``plugin_expansion_invalid`` (never a 500)."""
    sketch_id = uuid.uuid4()
    ref = FeatureRef(kind="feature", feature_id=sketch_id)
    datum = DatumFeature(
        type="datum",
        version=1,
        params=DatumOffsetParams(kind="offset", base="XY", offset_mm=0.0),
    )

    def undeclared(i: ExpandInputs) -> list[Member]:
        return [Member("joist", 0, datum)]

    def repeated(i: ExpandInputs) -> list[Member]:
        return [Member("block", 0, datum), Member("block", 0, datum)]

    def dangling(i: ExpandInputs) -> list[Member]:
        return [_block(i, 0, ref)]

    def forward(i: ExpandInputs) -> list[Member]:
        return [_block(i, 0, i.ref("block", 1))]

    def buggy(i: ExpandInputs) -> list[Member]:
        raise ZeroDivisionError("a plugin bug")

    for expander in (undeclared, repeated, dangling, forward, buggy):
        with pytest.raises(PluginError) as refused:
            expand(_plugin(expander), FEATURE_ID, {}, {})
        assert refused.value.code == "plugin_expansion_invalid", refused.value.message

    # the extrude may name the sketch when it is earlier and a sketch...
    sketch = expand_v1(
        ExpandInputs(FEATURE_ID, {"width_mm": 1.0, "depth_mm": 1.0, "count": 1})
    )[0].feature
    assert expand(_plugin(dangling), FEATURE_ID, {}, {sketch_id: sketch})
    # ...but not when it is a datum
    with pytest.raises(PluginError, match="cannot name a 'datum'"):
        expand(_plugin(dangling), FEATURE_ID, {}, {sketch_id: datum})
