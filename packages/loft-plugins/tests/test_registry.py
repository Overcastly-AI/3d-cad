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
    registry,
)
from loft_plugins.testing import BLOCKS_V1, BLOCKS_V2, expand_v1
from loft_wire.features import (
    CustomFeature,
    CustomParamsV1,
    DatumFeature,
    DatumOffsetParams,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureRef,
)
from loft_wire.plugins import (
    MAX_FEATURE_LIST,
    MAX_PLUGIN_EXPANSION,
    FeatureListInput,
    PluginCatalog,
    PluginManifest,
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
        ("loft.deck", "1.1.0", True),
        ("loft.deck", "1.0.0", False),
        ("loft.door", "1.3.0", True),
        ("loft.door", "1.2.0", False),
        ("loft.door", "1.1.0", False),
        ("loft.door", "1.0.0", False),
        ("loft.floor", "1.3.0", True),
        ("loft.floor", "1.2.0", False),
        ("loft.floor", "1.1.0", False),
        ("loft.floor", "1.0.0", False),
        ("loft.roof", "1.5.0", True),
        ("loft.roof", "1.4.0", False),
        ("loft.roof", "1.3.0", False),
        ("loft.roof", "1.2.0", False),
        ("loft.roof", "1.1.0", False),
        ("loft.roof", "1.0.0", False),
        ("loft.timber_frame", "1.0.0", True),
        ("loft.twisted_prism", "1.0.0", True),
        ("loft.wall", "1.3.0", True),
        ("loft.wall", "1.2.0", False),
        ("loft.wall", "1.1.0", False),
        ("loft.wall", "1.0.0", False),
        ("loft.window", "1.3.0", True),
        ("loft.window", "1.2.0", False),
        ("loft.window", "1.1.0", False),
        ("loft.window", "1.0.0", False),
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


class _FakeClock:
    """A clock that reads *now*; a test's plugin advances it."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _datum(n: int) -> Member:
    return Member(
        role="block",
        index=n,
        feature=DatumFeature(
            type="datum",
            version=1,
            params=DatumOffsetParams(kind="offset", base="XY", offset_mm=float(n)),
        ),
    )


@pytest.fixture
def clocks(monkeypatch: pytest.MonkeyPatch) -> tuple[_FakeClock, _FakeClock]:
    """Faked (cpu, wall) clocks, so the budget tests never depend on load."""
    cpu, wall = _FakeClock(), _FakeClock()
    monkeypatch.setattr(registry, "_cpu_clock", cpu)
    monkeypatch.setattr(registry, "_wall_clock", wall)
    return cpu, wall


def test_a_cpu_burning_plugin_trips_the_cpu_budget(
    clocks: tuple[_FakeClock, _FakeClock],
) -> None:
    """Each member costs 0.5 s of CPU: past the 2 s budget it is refused, and
    the message names the CPU limit, not the wall-clock one."""
    cpu, wall = clocks

    def burn(inputs: ExpandInputs) -> Iterator[Member]:
        for n in range(100):
            cpu.now += 0.5
            wall.now += 0.5
            yield _datum(n)

    with pytest.raises(PluginError) as refused:
        expand(_plugin(burn), FEATURE_ID, {}, {})
    assert refused.value.code == "plugin_expansion_timeout"
    assert "2 s of CPU time" in refused.value.message
    assert cpu.now == pytest.approx(2.5)  # stopped at the first member over


def test_a_loaded_machine_does_not_trip_the_cpu_budget(
    clocks: tuple[_FakeClock, _FakeClock],
) -> None:
    """The regression: 0.1 s of CPU that takes 5 s of wall-clock (a loaded
    machine) expands, where a 2 s wall-clock budget refused it."""
    cpu, wall = clocks

    def cheap_but_starved(inputs: ExpandInputs) -> Iterator[Member]:
        for n in range(5):
            cpu.now += 0.02
            wall.now += 1.0
            yield _datum(n)

    members = expand(_plugin(cheap_but_starved), FEATURE_ID, {}, {})
    assert len(members) == 5


def test_a_sleeping_plugin_trips_the_wall_clock_backstop(
    clocks: tuple[_FakeClock, _FakeClock],
) -> None:
    """A plugin that sleeps or blocks spends no CPU, but past the 10 s
    wall-clock backstop it is refused, and the message names that limit."""
    _cpu, wall = clocks

    def sleeper(inputs: ExpandInputs) -> Iterator[Member]:
        for n in range(100):
            wall.now += 3.0
            yield _datum(n)

    with pytest.raises(PluginError) as refused:
        expand(_plugin(sleeper), FEATURE_ID, {}, {})
    assert refused.value.code == "plugin_expansion_timeout"
    assert "10 s (wall-clock)" in refused.value.message
    assert wall.now == pytest.approx(12.0)


def test_the_budget_is_checked_after_the_last_member(
    clocks: tuple[_FakeClock, _FakeClock],
) -> None:
    """A plugin that does all its work before returning still meets both
    limits (the final check)."""
    cpu, wall = clocks

    def burn_then_return(inputs: ExpandInputs) -> list[Member]:
        cpu.now += 3.0
        return []

    def sleep_then_return(inputs: ExpandInputs) -> list[Member]:
        wall.now += 11.0
        return []

    for expander, limit in ((burn_then_return, "CPU"), (sleep_then_return, "wall")):
        with pytest.raises(PluginError) as refused:
            expand(_plugin(expander), FEATURE_ID, {}, {})
        assert refused.value.code == "plugin_expansion_timeout"
        assert limit in refused.value.message


def test_the_real_clocks_tell_cpu_from_sleep() -> None:
    """On the real clocks: a real sleep trips the wall-clock backstop and not
    the CPU budget, and a real busy loop trips the CPU budget. Both hold under
    any load (load only lengthens wall-clock, which the CPU test allows 60 s)."""

    def sleeper(inputs: ExpandInputs) -> list[Member]:
        time.sleep(0.05)
        return []

    with pytest.raises(PluginError) as slept:
        expand(_plugin(sleeper), FEATURE_ID, {}, {}, wall_limit_s=0.01)
    assert "wall-clock" in slept.value.message

    def busy(inputs: ExpandInputs) -> Iterator[Member]:
        for n in range(MAX_PLUGIN_EXPANSION):
            stop = time.thread_time() + 0.01
            while time.thread_time() < stop:
                pass
            yield _datum(n)

    with pytest.raises(PluginError) as burned:
        expand(_plugin(busy), FEATURE_ID, {}, {}, cpu_limit_s=0.05, wall_limit_s=60)
    assert "CPU time" in burned.value.message


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


# --- Feature lists (ROOF-VALLEY: a roof's picked walls) ----------------------------


def _picks(minimum: int = 0, maximum: int = 3) -> PluginManifest:
    return PluginManifest(
        id="test.picks",
        version="1.0.0",
        title="Picks",
        description="Takes several walls.",
        inputs=[
            FeatureListInput(
                kind="features",
                name="walls",
                label="Walls",
                feature_types=["custom"],
                plugin_ids=["loft.wall"],
                min_items=minimum,
                max_items=maximum,
            )
        ],
        members=[PluginMemberRole(role="block", title="Block")],
    )


def _ref(n: int) -> FeatureRef:
    return FeatureRef(kind="feature", feature_id=uuid.UUID(int=n))


def test_a_feature_list_keeps_its_picks_in_order() -> None:
    assert canonical_inputs(_picks(), {}) == {}  # optional: left empty
    picks = [_ref(3), _ref(1), _ref(2)]
    assert canonical_inputs(_picks(), {"walls": picks}) == {"walls": picks}


@pytest.mark.parametrize(
    ("value", "minimum", "why"),
    [
        (None, 1, "pick at least 1"),
        ([_ref(1)], 2, "pick at least 2"),
        ([_ref(1), _ref(2), _ref(3), _ref(4)], 0, "pick at most 3"),
        ([_ref(1), _ref(1)], 0, "twice"),
        ("walls", 0, "must name features"),
    ],
)
def test_a_feature_list_is_checked(value: Any, minimum: int, why: str) -> None:
    raw = {} if value is None else {"walls": value}
    with pytest.raises(PluginError, match=why) as refused:
        canonical_inputs(_picks(minimum), raw)
    assert refused.value.code == "plugin_input_invalid"
    assert refused.value.input == "walls"


def test_a_feature_lists_picks_are_earlier_features_of_its_plugins() -> None:
    plugin = Plugin(_picks(), lambda inputs: iter(()))
    wall = CustomFeature.model_validate(
        {
            "type": "custom",
            "version": 1,
            "params": {
                "plugin_id": "loft.wall",
                "plugin_version": "1.0.0",
                "inputs": {},
            },
        }
    )
    deck = wall.model_copy(
        update={"params": wall.params.model_copy(update={"plugin_id": "loft.deck"})}
    )
    one, two = _ref(1).feature_id, _ref(2).feature_id
    inputs = canonical_inputs(plugin.manifest, {"walls": [_ref(1), _ref(2)]})
    assert expand(plugin, FEATURE_ID, inputs, {one: wall, two: wall}) == []
    with pytest.raises(PluginError, match="names no earlier feature"):
        expand(plugin, FEATURE_ID, inputs, {one: wall})
    with pytest.raises(PluginError, match=r"names a loft\.deck"):
        expand(plugin, FEATURE_ID, inputs, {one: wall, two: deck})


def test_a_feature_list_input_is_bounded() -> None:
    with pytest.raises(ValueError, match="min_items is above max_items"):
        FeatureListInput(
            kind="features",
            name="w",
            label="W",
            feature_types=["custom"],
            min_items=3,
            max_items=2,
        )
    with pytest.raises(ValueError, match="plugin_ids needs"):
        FeatureListInput(
            kind="features",
            name="w",
            label="W",
            feature_types=["datum"],
            plugin_ids=["loft.wall"],
        )
    with pytest.raises(ValueError, match="less than or equal"):
        FeatureListInput(
            kind="features",
            name="w",
            label="W",
            feature_types=["custom"],
            max_items=MAX_FEATURE_LIST + 1,
        )


def test_a_custom_feature_stores_a_list_of_picks() -> None:
    params = CustomParamsV1.model_validate(
        {
            "plugin_id": "test.picks",
            "plugin_version": "1.0.0",
            "inputs": {"walls": [_ref(1).model_dump(mode="json")]},
        }
    )
    assert params.inputs["walls"] == [_ref(1)]
    with pytest.raises(ValueError):  # an empty pick is no value, not []
        CustomParamsV1.model_validate(
            {
                "plugin_id": "test.picks",
                "plugin_version": "1.0.0",
                "inputs": {"walls": []},
            }
        )
