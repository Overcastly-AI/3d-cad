"""``loft.timber_frame``: B6's frame and its pegged mortise and tenon joints
(TIMBER-FRAME).

Numbers are typed from ``docs/reference-parts/buildings.md`` B6, never read
back from the plugin. The geometry goldens ``timber-mt-8x8`` (one joint),
``b6-frame-12x16`` and ``b6-frame-14x16`` (the width edit) are this plugin's
expansion (``model.json``, member materials applied as documents sends them)
and their members' metadata (``members.json``); the first tests pin the files
to it, so ``services/geometry/tests/test_timber_frame_b6.py`` reads files
that cannot drift. Regenerate after a deliberate change (a NEW plugin
version) with ``uv run python packages/loft-plugins/tests/test_timber_frame.py``.
"""

import gzip
import json
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, PluginError, canonical_inputs, expand
from loft_plugins.api import ExpandInputs
from loft_plugins.builtin.timber_frame import (
    Box,
    Frame,
    Joint,
    Peg,
    emit_frame,
    frame_layout,
)
from loft_plugins.registry import validate_members
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    BooleanFeature,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
)
from loft_wire.lumber import lumber_profile
from loft_wire.materials import with_member_materials
from loft_wire.plugins import (
    MAX_PLUGIN_EXPANSION,
    PLUGIN_INPUT_INVALID,
    PLUGIN_INPUT_UNSUPPORTED,
    member_id,
)

IN = 25.4
FRAME = REGISTRY.get("loft.timber_frame", "1.0.0")
GEOMETRY = Path(__file__).resolve().parents[3] / "services" / "geometry"
GOLDENS = GEOMETRY / "goldens"
#: The kernel overlap sweep (services/geometry/tests/test_timber_frame_b6.py).
SWEEP_FIXTURE = GEOMETRY / "tests" / "fixtures" / "timber-frame-sweep.json.gz"
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b6")
FRAME_ID = uuid.UUID("00000000-0000-0000-0000-0000000000f6")
EIGHT = lumber_profile("us_8x8")

#: golden name -> raw inputs (what the form sends; the rest are B6 defaults).
GOLDEN_INPUTS: dict[str, dict[str, Any]] = {
    "b6-frame-12x16": {},
    "b6-frame-14x16": {"width_mm": 168 * IN},
}
JOINT_GOLDEN = "timber-mt-8x8"

#: The overlap sweep: name -> raw inputs. Inner bents (shortened opposed
#: tenons), beams narrower than the posts (flush outside, inner tie beams
#: centred), the girts at their lowest and highest, large sections, and the
#: most bents.
SWEEP: dict[str, dict[str, Any]] = {
    "3-bents-8x8": {"bent_count": 3},
    "4-bents-6x8-beams-girt-low": {
        "bent_count": 4,
        "beam_profile": "us_6x8",
        "length_mm": 300 * IN,
        "girt_height_mm": 7.5 * IN,
    },
    "2-bents-12x12-8x12-girt-high": {
        "post_profile": "us_12x12",
        "beam_profile": "us_8x12",
        "post_height_mm": 120 * IN,
        "girt_height_mm": 108.5 * IN,
    },
    "3-bents-10x10-6x6-wide": {
        "bent_count": 3,
        "post_profile": "us_10x10",
        "beam_profile": "us_6x6",
        "width_mm": 300 * IN,
        "length_mm": 240 * IN,
    },
    "8-bents-max": {
        "bent_count": 8,
        "width_mm": 480 * IN,
        "length_mm": 960 * IN,
        "post_height_mm": 288 * IN,
        "girt_height_mm": 140 * IN,
    },
}


def members(
    raw: dict[str, Any] | None = None, feature_id: uuid.UUID = FRAME_ID
) -> list[ExpandedMember]:
    return expand(FRAME, feature_id, canonical_inputs(FRAME.manifest, raw or {}), {})


def spec_joint() -> Frame:
    """buildings.md B6 "One joint", typed from the spec: a post X 0..7.5,
    Y 0..7.5, Z 0..96 and a beam X 7.5..67.5, Z 88.5..96; the tenon X
    3.5..7.5, Y 3..4.5, Z 89.25..95.25; the peg along Y at X 5.5, Z 92.25."""
    return Frame(
        posts=[Box(0.0, 7.5, 0.0, 7.5, 0.0, 96.0)],
        tie_beams=[Box(7.5, 67.5, 0.0, 7.5, 88.5, 96.0)],
        girts=[],
        joints=[
            Joint(
                post=0,
                beam_role="tie_beam",
                beam=0,
                tenon=Box(3.5, 7.5, 3.0, 4.5, 89.25, 95.25),
                peg=Peg("y", 5.5, 92.25, 0.0, 7.5),
            )
        ],
    )


def joint_members() -> list[ExpandedMember]:
    """The one-joint golden: :func:`emit_frame` (the plugin's own code) on
    :func:`spec_joint`, as the registry would store it."""
    inputs = ExpandInputs(FRAME_ID, {})
    out = [
        ExpandedMember(
            role=m.role,
            index=m.index,
            id=member_id(FRAME_ID, m.role, m.index),
            feature=m.feature,
            metadata=m.metadata,
        )
        for m in emit_frame(
            inputs, spec_joint(), EIGHT, EIGHT, "dfl_lumber", "white_oak"
        )
    ]
    validate_members(FRAME_ID, out, {})
    return out


def as_golden(
    expansion: list[ExpandedMember], part_id: uuid.UUID = PART_ID
) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """A golden's evaluation request and its members' cut-list metadata."""
    titles = {role.role: role.title for role in FRAME.manifest.members}
    request = EvaluateTreeRequest(
        part_id=part_id,
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
            feature_id=m.id, role=m.role, title=titles[m.role], metadata=m.metadata
        )
        for m in expansion
        if m.metadata is not None
    ]
    return request, metadata


def goldens() -> dict[str, tuple[EvaluateTreeRequest, list[CutListMember]]]:
    out = {name: as_golden(members(raw)) for name, raw in GOLDEN_INPUTS.items()}
    out[JOINT_GOLDEN] = as_golden(joint_members())
    return out


def sweep_fixture() -> str:
    """The sweep's requests as geometry reads them (compact JSON)."""
    cases: list[dict[str, Any]] = []
    for name, raw in SWEEP.items():
        request, metadata = as_golden(members(raw))
        cases.append(
            {
                "name": name,
                "bodies": len(metadata),
                "request": request.model_dump(mode="json"),
            }
        )
    return json.dumps(cases, separators=(",", ":")) + "\n"


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


def _refusal(raw: dict[str, Any]) -> PluginError:
    with pytest.raises(PluginError) as caught:
        members(raw)
    return caught.value


def _layout(**kw: Any) -> Frame:
    args: dict[str, Any] = {
        "width": 144.0,
        "length": 192.0,
        "bents": 2,
        "height": 96.0,
        "girt_top": 60.0,
        "post": EIGHT,
        "beam": EIGHT,
    }
    args.update(kw)
    return frame_layout(**args)


def _volume(box: Box) -> float:
    return (box.x1 - box.x0) * (box.y1 - box.y0) * (box.z1 - box.z0)


# --- Goldens -----------------------------------------------------------------------


@pytest.mark.parametrize("name", [*sorted(GOLDEN_INPUTS), JOINT_GOLDEN])
def test_the_goldens_are_the_plugins_expansion(name: str) -> None:
    request, metadata = goldens()[name]
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / name / "members.json").read_text() == _members_json(metadata)


def test_the_sweep_fixture_is_the_plugins_expansion() -> None:
    assert gzip.decompress(SWEEP_FIXTURE.read_bytes()).decode() == sweep_fixture()


# --- B6, member by member ----------------------------------------------------------


def test_b6_has_the_specs_members() -> None:
    """buildings.md B6: 4 posts, 2 tie beams, 2 girts and 8 pegs; each joint
    a tenon fused on, a mortise and two bores cut, from two sketches."""
    expansion = members()
    bodies = Counter(m.role for m in expansion if isinstance(m.feature, ExtrudeFeature))
    assert bodies == {
        "post": 4,
        "tie_beam": 2,
        "girt": 2,
        "peg": 8,
        "tenon": 8,
        "mortise": 8,
        "bore": 16,
    }
    booleans = [m.feature for m in expansion if isinstance(m.feature, BooleanFeature)]
    roles = {m.id: m.role for m in expansion}
    unions = Counter(
        (roles[b.params.target.feature_id], roles[b.params.tool.feature_id])
        for b in booleans
        if b.params.operation == "union"
    )
    assert unions == {("tie_beam", "tenon"): 4, ("girt", "tenon"): 4}
    cuts = Counter(
        (roles[b.params.target.feature_id], roles[b.params.tool.feature_id])
        for b in booleans
        if b.params.operation == "subtract"
    )
    assert cuts == {
        ("post", "mortise"): 8,
        ("post", "bore"): 8,
        ("tie_beam", "bore"): 4,
        ("girt", "bore"): 4,
    }
    metadata = Counter(
        (m.role, m.metadata.profile, m.metadata.material)
        for m in expansion
        if m.metadata is not None
    )
    assert metadata == {
        ("post", "8x8", "dfl_lumber"): 4,
        ("tie_beam", "8x8", "dfl_lumber"): 2,
        ("girt", "8x8", "dfl_lumber"): 2,
        ("peg", "Ø1", "white_oak"): 8,
    }


def test_one_joint_placement_cuts_both_members() -> None:
    """The mortise and the tenon are extrudes of ONE sketch, and the peg and
    both its holes of ONE circle: the holes are coaxial by construction."""
    expansion = members()
    by_id = {m.id: m for m in expansion}
    profiles: dict[str, Counter[str]] = {}
    for m in expansion:
        if isinstance(m.feature, ExtrudeFeature):
            sketch = m.feature.params.profile.feature_id
            profiles.setdefault(str(sketch), Counter())[m.role] += 1
    shared = Counter(frozenset(c.items()) for c in profiles.values())
    assert shared == {
        frozenset({("tenon", 1), ("mortise", 1)}): 8,
        frozenset({("bore", 2), ("peg", 1)}): 8,
        frozenset({("post", 1)}): 4,
        frozenset({("tie_beam", 1)}): 2,
        frozenset({("girt", 1)}): 2,
    }
    assert all(by_id[uuid.UUID(s)].role == "section" for s in profiles)


def test_b6_layout_is_the_specs() -> None:
    frame = _layout()
    assert frame.posts == [
        Box(0, 7.5, 0, 7.5, 0, 96),
        Box(136.5, 144, 0, 7.5, 0, 96),
        Box(0, 7.5, 184.5, 192, 0, 96),
        Box(136.5, 144, 184.5, 192, 0, 96),
    ]
    # Tie beams flush with the post tops and the outside; shoulder 129.
    assert frame.tie_beams == [
        Box(7.5, 136.5, 0, 7.5, 88.5, 96),
        Box(7.5, 136.5, 184.5, 192, 88.5, 96),
    ]
    # Girts between the bents, tops at Z 60; shoulder 177.
    assert frame.girts == [
        Box(0, 7.5, 7.5, 184.5, 52.5, 60),
        Box(136.5, 144, 7.5, 184.5, 52.5, 60),
    ]
    # The first joint is buildings.md's "One joint" exactly.
    assert frame.joints[0] == spec_joint().joints[0]
    for joint in frame.joints:
        t = joint.tenon
        assert sorted((t.x1 - t.x0, t.y1 - t.y0)) == [1.5, 4.0]
        assert t.z1 - t.z0 == 6.0
        post = frame.posts[joint.post]
        # The peg runs through the post's full depth, 2 in from the shoulder,
        # at the tenon's mid-height, through the tenon's thickness.
        assert joint.peg.end - joint.peg.start == 7.5
        assert joint.peg.z == (t.z0 + t.z1) / 2
        if joint.peg.axis == "y":
            assert (joint.peg.start, joint.peg.end) == (post.y0, post.y1)
            assert t.x0 + 0.5 <= joint.peg.across <= t.x1 - 0.5
            shoulder = t.x1 if t.x1 == post.x1 else t.x0
            assert abs(joint.peg.across - shoulder) == 2.0
        else:
            assert (joint.peg.start, joint.peg.end) == (post.x0, post.x1)
            assert t.y0 + 0.5 <= joint.peg.across <= t.y1 - 0.5
            shoulder = t.y1 if t.y1 == post.y1 else t.y0
            assert abs(joint.peg.across - shoulder) == 2.0
    # 56 025 in³: every member's shoulder box (tenon fills mortise, peg hole).
    boxes = frame.posts + frame.tie_beams + frame.girts
    assert sum(_volume(b) for b in boxes) == 56025.0


def test_the_width_edit_is_the_specs() -> None:
    """Width 12 -> 14 ft: tie beams 153 between shoulders (161 overall),
    58 725 in³."""
    frame = _layout(width=168.0)
    assert [b.x1 - b.x0 for b in frame.tie_beams] == [153.0, 153.0]
    boxes = frame.posts + frame.tie_beams + frame.girts
    assert sum(_volume(b) for b in boxes) == 58725.0


def test_inner_bents_shorten_the_opposed_girt_tenons() -> None:
    """Three bents: the middle posts take a girt tenon from each side, each
    3.5 long with 1/2 in between their ends; the inner tie beam is centred."""
    frame = _layout(bents=3)
    assert len(frame.posts) == 6 and len(frame.girts) == 4
    assert len(frame.joints) == 3 * 2 + 4 * 2
    inner = [j for j in frame.joints if j.beam_role == "girt" and j.post in (2, 3)]
    assert len(inner) == 4
    for joint in inner:
        assert joint.tenon.y1 - joint.tenon.y0 == 3.5
    left = sorted((j.tenon.y0, j.tenon.y1) for j in inner if j.post == 2)
    assert left[1][0] - left[0][1] == 0.5
    narrow = _layout(bents=3, beam=lumber_profile("us_6x8"))
    assert narrow.tie_beams[1].y0 - narrow.posts[2].y0 == 1.0  # centred
    assert narrow.tie_beams[0].y0 == 0.0  # flush outside
    assert narrow.tie_beams[2].y1 == 192.0


@pytest.mark.parametrize(
    ("raw", "code", "field"),
    [
        ({"post_profile": "us_6x6", "beam_profile": "us_8x8"}, "u", "beam_profile"),
        (
            {"bent_count": 3, "post_profile": "us_6x6", "beam_profile": "us_6x6"},
            "u",
            "post_profile",
        ),
        ({"girt_height_mm": 89 * IN}, "u", "girt_height_mm"),
        ({"girt_height_mm": 7 * IN}, "u", "girt_height_mm"),
        ({"bent_count": 8, "length_mm": 200 * IN}, "u", "length_mm"),
        ({"bent_count": 9}, "i", "bent_count"),
        ({"bent_count": 1}, "i", "bent_count"),
    ],
)
def test_refusals_are_typed(raw: dict[str, Any], code: str, field: str) -> None:
    error = _refusal(raw)
    assert error.code == (
        PLUGIN_INPUT_UNSUPPORTED if code == "u" else PLUGIN_INPUT_INVALID
    )
    assert error.input == field


def test_a_short_tie_beam_is_refused() -> None:
    """The width's 72 in floor keeps every tie beam over 24 in; the layout
    refuses one anyway (a guard for a later, narrower bound)."""
    with pytest.raises(PluginError) as caught:
        _layout(width=40.0, post=lumber_profile("us_12x12"))
    assert caught.value.input == "width_mm"


def test_the_largest_frame_is_bounded() -> None:
    """Eight bents at the largest size: 44 joints in under 600 features, far
    below the tree's 1 000 and the 5 000 expansion cap."""
    expansion = members(SWEEP["8-bents-max"])
    assert len(expansion) < 600 < MAX_PLUGIN_EXPANSION
    assert Counter(m.role for m in expansion)["peg"] == 44


if __name__ == "__main__":
    for name, (request, metadata) in sorted(goldens().items()):
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(_members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
    SWEEP_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    SWEEP_FIXTURE.write_bytes(gzip.compress(sweep_fixture().encode(), mtime=0))
    sys.stdout.write(f"{SWEEP_FIXTURE.name}: {len(SWEEP)} cases\n")
