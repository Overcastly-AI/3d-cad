"""``loft.deck`` 1.2.0: B1 on pier footings (DECK-FOOTINGS).

buildings.md B1 "Footings": each post stands on a round pier footing, Ø16,
Z -12..0, centred under it, with a post base; 3 at 16 ft, 4 at 20 ft. The
geometry goldens ``plugin-deck-v1.2-b1-footings-16ft`` and ``-20ft`` are this
version's expansion (``model.json``, with the member materials documents
sends) and its members' metadata (``members.json``); the first test pins
them, so ``services/geometry/tests/test_deck_footings_b1.py`` reads files
that cannot drift. Regenerate after a deliberate change (a NEW plugin
version) with ``uv run python packages/loft-plugins/tests/test_deck_footings.py``.

1.0.0 and 1.1.0 are frozen: their goldens (``test_deck.py``,
``test_member_names.py``) still pin them byte for byte, and the last test
here re-expands both and finds no footing.
"""

import json
import math
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, PluginError, canonical_inputs, expand
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    DatumFeature,
    DatumOffsetParams,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    FeatureRef,
    SketchFeature,
)
from loft_wire.materials import with_member_materials
from loft_wire.plugins import PLUGIN_INPUT_UNSUPPORTED
from loft_wire.sketch import SketchCircle

IN = 25.4
DECK = REGISTRY.get("loft.deck", "1.2.0")
GOLDENS = Path(__file__).resolve().parents[3] / "services" / "geometry" / "goldens"
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
DECK_ID = uuid.UUID("00000000-0000-0000-0000-00000000dec1")

#: golden name -> raw inputs (inches x 25.4: what the form sends).
GOLDEN_INPUTS: dict[str, dict[str, Any]] = {
    "plugin-deck-v1.2-b1-footings-16ft": {"width_mm": 192 * IN, "depth_mm": 144 * IN},
    "plugin-deck-v1.2-b1-footings-20ft": {"width_mm": 240 * IN, "depth_mm": 144 * IN},
}


def members(
    raw: dict[str, Any] | None = None, version: str = "1.2.0"
) -> list[ExpandedMember]:
    plugin = REGISTRY.get("loft.deck", version)
    inputs = canonical_inputs(plugin.manifest, raw or {})
    return expand(plugin, DECK_ID, inputs, {})


def golden(name: str) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """A golden's evaluation request (member materials applied, as documents
    sends them) and its members' cut-list metadata."""
    expansion = members(GOLDEN_INPUTS[name])
    titles = {role.role: role.title for role in DECK.manifest.members}
    request = EvaluateTreeRequest(
        part_id=PART_ID,
        tree_version=1,
        features=[EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in expansion],
        materials=with_member_materials(
            None,
            {m.id: m.metadata.material for m in expansion if m.metadata is not None},
        ),
        linear_deflection=0.1,
    )
    metadata = [
        CutListMember(
            feature_id=m.id,
            role=m.role,
            title=titles[m.role],
            plugin_id="loft.deck",
            metadata=m.metadata,
        )
        for m in expansion
        if m.metadata is not None
    ]
    return request, metadata


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


def piers(
    expansion: list[ExpandedMember],
) -> list[tuple[float, float, float, float, float]]:
    """Each footing as (centre x, centre y, radius, z0, z1) in inches, from
    its circle, its level and its extrude (no kernel)."""
    by_id = {m.id: m for m in expansion}
    out: list[tuple[float, float, float, float, float]] = []
    for m in expansion:
        if m.role != "footing":
            continue
        assert isinstance(m.feature, ExtrudeFeature)
        sketch = by_id[m.feature.params.profile.feature_id].feature
        assert isinstance(sketch, SketchFeature)
        (circle,) = sketch.params.entities
        assert isinstance(circle, SketchCircle)
        plane = sketch.params.plane
        assert isinstance(plane, FeatureRef)
        level = by_id[plane.feature_id].feature
        assert isinstance(level, DatumFeature)
        assert isinstance(level.params, DatumOffsetParams)
        assert level.params.base == "XY"
        z0 = level.params.offset_mm
        z1 = z0 + m.feature.params.distance_mm
        out.append(
            tuple(  # pyright: ignore[reportArgumentType]
                round(v / IN, 9)
                for v in (circle.center.x, circle.center.y, circle.radius, z0, z1)
            )
        )
    return out


@pytest.mark.parametrize("name", sorted(GOLDEN_INPUTS))
def test_the_goldens_are_the_plugins_expansion(name: str) -> None:
    request, metadata = golden(name)
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / name / "members.json").read_text() == _members_json(metadata)


def test_b1_stands_on_three_piers() -> None:
    """buildings.md B1 "Footings": Ø16, Z -12..0, centred under each post at
    X 2.75, 96, 189.25 on the beam line Y 126; 3π x 64 x 12 in³."""
    got = piers(members())
    assert got == [(x, 126, 8, -12, 0) for x in (2.75, 96, 189.25)]
    volume = sum(math.pi * r**2 * (z1 - z0) for _, _, r, z0, z1 in got)
    assert volume == pytest.approx(7238.229473870882, abs=1e-9)


def test_the_20ft_edit_gives_four() -> None:
    got = piers(members(GOLDEN_INPUTS["plugin-deck-v1.2-b1-footings-20ft"]))
    assert [p[0] for p in got] == pytest.approx(
        [2.75 + 234.5 * n / 3 for n in range(4)], abs=1e-9
    )
    assert {p[1:] for p in got} == {(126, 8, -12, 0)}


def test_every_footing_lists_its_concrete_and_post_base() -> None:
    footings = [m for m in members() if m.role == "footing"]
    assert len(footings) == 3
    for m in footings:
        assert m.metadata is not None and m.metadata.concrete is not None
        assert m.metadata.profile == "Concrete, 80 lb bag"
        assert m.metadata.material == "concrete"
        assert m.metadata.concrete.item == "concrete_bag_80"
        assert m.metadata.concrete.waste_percent == 5
        assert m.metadata.concrete.one_delivery  # the piers fill from one truck
        assert m.metadata.concrete.post_base == "post_base_6x6"


def test_footings_are_named_as_their_posts() -> None:
    """A footing takes its post's name, so the end one keeps its id when the
    deck is widened; they emit right after the posts."""
    expansion = members()
    named = [(m.role, m.name) for m in expansion if m.role in ("post", "footing")]
    ends = ["outer/0", "outer/1", "outer/end"]
    assert named == [("post", n) for n in ends] + [("footing", n) for n in ends]
    wide = members(GOLDEN_INPUTS["plugin-deck-v1.2-b1-footings-20ft"])
    end = {m.id for m in expansion if m.role == "footing" and m.name == "outer/end"}
    assert end <= {m.id for m in wide if m.role == "footing"}
    roles = [m.role for m in expansion if isinstance(m.feature, ExtrudeFeature)]
    assert list(dict.fromkeys(roles)) == [
        "ledger",
        "rim",
        "beam",
        "joist",
        "post",
        "footing",
        "deck",
    ]


def test_ready_mix_and_no_post_bases_are_choices() -> None:
    (first, *_) = [
        m
        for m in members({"footing_concrete": "ready_mix", "post_bases": "no"})
        if m.role == "footing"
    ]
    assert first.metadata is not None and first.metadata.concrete is not None
    assert first.metadata.profile == "Ready-mix concrete"
    assert first.metadata.concrete.item == "ready_mix"
    assert first.metadata.concrete.post_base is None


def test_post_bases_follow_the_post_size() -> None:
    for profile, base in (("us_4x4", "post_base_4x4"), ("us_4x6", "post_base_4x6")):
        footing = next(
            m for m in members({"post_profile": profile}) if m.role == "footing"
        )
        assert footing.metadata is not None and footing.metadata.concrete is not None
        assert footing.metadata.concrete.post_base == base


def test_footing_inputs_drive_the_piers() -> None:
    got = piers(members({"footing_diameter_mm": 12 * IN, "footing_depth_mm": 42 * IN}))
    assert {p[2:] for p in got} == {(6, -42, 0)}


def test_a_freestanding_deck_footings_both_beam_lines() -> None:
    got = piers(members({"attachment": "freestanding"}))
    assert len(got) == 6
    assert sorted({p[1] for p in got}) == [18, 126]


def test_no_footings_is_the_1_1_deck() -> None:
    """Footings off, 1.2.0 emits 1.1.0's members exactly."""
    assert members({"footings": "none"}) == members(version="1.1.0")


def test_older_versions_have_no_footings() -> None:
    for version in ("1.0.0", "1.1.0"):
        roles = Counter(m.role for m in members(version=version))
        assert "footing" not in roles and roles["post"] == 3


def test_overlapping_piers_are_refused() -> None:
    with pytest.raises(PluginError) as caught:
        members({"post_spacing_mm": 24 * IN, "footing_diameter_mm": 30 * IN})
    assert caught.value.code == PLUGIN_INPUT_UNSUPPORTED
    assert caught.value.input == "footing_diameter_mm"


if __name__ == "__main__":
    for name in sorted(GOLDEN_INPUTS):
        request, metadata = golden(name)
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(_members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
