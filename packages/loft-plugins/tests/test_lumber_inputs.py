"""A plugin reads lumber profiles and materials from the shared library."""

import uuid

import pytest
from loft_plugins import ExpandInputs, PluginError, canonical_inputs, lumber_options
from loft_wire.lumber import LUMBER_PROFILES
from loft_wire.plugins import (
    ChoiceInput,
    MaterialInput,
    PluginManifest,
    PluginMemberRole,
)

MANIFEST = PluginManifest(
    id="test.joists",
    version="1.0.0",
    title="Joists",
    description="Lumber-profile input fixture.",
    inputs=[
        ChoiceInput(
            kind="choice",
            name="joist_profile",
            label="Joist",
            options=lumber_options(["us_2x8", "us_2x10", "us_2x12"]),
            default="us_2x10",
        ),
        MaterialInput(
            kind="material", name="material", label="Material", default="spf_lumber"
        ),
    ],
    members=[PluginMemberRole(role="joist", title="Joists")],
)


def test_options_cover_the_library_labelled_by_nominal_size() -> None:
    options = lumber_options()
    assert [o.value for o in options] == [p.key for p in LUMBER_PROFILES]
    assert options[0].label == "1x2"
    assert [o.label for o in lumber_options(["us_2x12", "us_2x8"])] == [
        "2x8",
        "2x12",
    ]


def test_a_choice_input_reads_back_as_the_actual_size() -> None:
    values = canonical_inputs(MANIFEST, {"joist_profile": "us_2x12"})
    inputs = ExpandInputs(feature_id=uuid.uuid4(), values=values)

    profile = inputs.lumber("joist_profile")

    assert (profile.name, profile.thickness_in, profile.width_in) == (
        "2x12",
        1.5,
        11.25,
    )
    assert inputs.material("material") == "spf_lumber"


def test_a_non_profile_value_is_a_typed_refusal() -> None:
    inputs = ExpandInputs(feature_id=uuid.uuid4(), values={"joist_profile": "2x10"})
    with pytest.raises(PluginError) as caught:
        inputs.lumber("joist_profile")
    assert caught.value.code == "plugin_input_invalid"
