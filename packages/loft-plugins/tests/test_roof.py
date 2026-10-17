"""``loft.roof`` 1.0.0: B2's gable from one custom feature (ROOF).

Layouts are checked against ``docs/reference-parts/buildings.md`` B2's roof
and its 8/12 edit, typed from the spec by hand. The geometry goldens
``b2-roof-6-12`` and ``b2-roof-8-12`` are this plugin's expansion
(``model.json``, with the member materials documents sends) and their
members' metadata (``members.json``); the first test asserts the files are
exactly that, so the geometry acceptance
(``services/geometry/tests/test_roof_b2.py``) reads files that cannot drift.
Regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_roof.py``.
"""

import itertools
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
    DatumPlaneRef,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    SketchFeature,
)
from loft_wire.materials import with_member_materials
from loft_wire.plugins import PLUGIN_INPUT_UNSUPPORTED
from loft_wire.sketch import SketchLine

IN = 25.4
ROOF = REGISTRY.get("loft.roof", "1.0.0")
GOLDENS = Path(__file__).resolve().parents[3] / "services" / "geometry" / "goldens"
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
ROOF_ID = uuid.UUID("00000000-0000-0000-0000-0000000000f1")

#: golden name -> raw inputs (what the form sends; the rest are B2 defaults).
GOLDEN_INPUTS: dict[str, dict[str, Any]] = {
    "b2-roof-6-12": {"pitch": "rise_6"},
    "b2-roof-8-12": {"pitch": "rise_8"},
}

#: buildings.md B2: rafter centres X 0.75, 24, 48, ..., 120, 143.25.
CENTRES = [0.75, 24, 48, 72, 96, 120, 143.25]


def members(raw: dict[str, Any] | None = None) -> list[ExpandedMember]:
    inputs = canonical_inputs(ROOF.manifest, raw or {})
    return expand(ROOF, ROOF_ID, inputs, {})


def golden(name: str) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """A golden's evaluation request (member materials applied, as documents
    sends them) and its members' cut-list metadata."""
    expansion = members(GOLDEN_INPUTS[name])
    titles = {role.role: role.title for role in ROOF.manifest.members}
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
            feature_id=m.id, role=m.role, title=titles[m.role], metadata=m.metadata
        )
        for m in expansion
        if m.metadata is not None
    ]
    return request, metadata


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


Outline = list[tuple[float, float]]


def bodies(
    expansion: list[ExpandedMember],
) -> dict[tuple[str, int], tuple[float, float, Outline]]:
    """Each body as (x0, x1, its (Y, Z) outline), in inches: from its YZ
    plane, its section sketch and its extrude (no kernel)."""
    by_id = {m.id: m for m in expansion}
    out: dict[tuple[str, int], tuple[float, float, Outline]] = {}
    for m in expansion:
        if not isinstance(m.feature, ExtrudeFeature):
            continue
        sketch = by_id[m.feature.params.profile.feature_id].feature
        assert isinstance(sketch, SketchFeature)
        plane = sketch.params.plane
        if isinstance(plane, DatumPlaneRef):
            assert plane.plane == "YZ"
            x0 = 0.0
        else:
            datum = by_id[plane.feature_id].feature
            assert isinstance(datum, DatumFeature)
            assert isinstance(datum.params, DatumOffsetParams)
            assert datum.params.base == "YZ" and not datum.params.flip
            x0 = datum.params.offset_mm
        lines = [e for e in sketch.params.entities if isinstance(e, SketchLine)]
        assert len(lines) == len(sketch.params.entities)
        for a, b in zip(lines, lines[1:] + lines[:1], strict=True):
            assert a.end == b.start  # one closed loop, in order
        outline = [(e.start.x / IN, e.start.y / IN) for e in lines]
        x1 = x0 + m.feature.params.distance_mm
        out[(m.role, m.index)] = (round(x0 / IN, 9), round(x1 / IN, 9), outline)
    return out


def area(outline: Outline) -> float:
    """Signed area (shoelace): positive counter-clockwise."""
    n = len(outline)
    return (
        sum(
            outline[i][0] * outline[(i + 1) % n][1]
            - outline[(i + 1) % n][0] * outline[i][1]
            for i in range(n)
        )
        / 2
    )


def cuts(outline: Outline) -> dict[str, float]:
    """A rafter outline's plumb cuts and birdsmouth, measured from its
    corners: the two vertical edges at the extreme Y (the plumb cuts), the
    vertical heel and the level seat between them."""
    n = len(outline)
    edges = [(outline[i], outline[(i + 1) % n]) for i in range(n)]
    plumb = [(a, b) for a, b in edges if abs(a[0] - b[0]) < 1e-9]
    level = [(a, b) for a, b in edges if abs(a[1] - b[1]) < 1e-9]
    ys = [p[0] for p in outline]
    lo, hi = min(ys), max(ys)
    ends = [e for e in plumb if abs(e[0][0] - lo) < 1e-9 or abs(e[0][0] - hi) < 1e-9]
    heels = [e for e in plumb if e not in ends]
    assert len(ends) == 2 and len(heels) == 1 and len(level) == 1
    # The line length: along the top edge, from plumb cut to plumb cut.
    tops = [max(a[1], b[1]) for a, b in ends]
    (a, b), (c, d) = ends
    top_a = (a[0], max(a[1], b[1]))
    top_b = (c[0], max(c[1], d[1]))
    return {
        "line_length": math.dist(top_a, top_b),
        "plumb_cut": abs(ends[0][0][1] - ends[0][1][1]),
        "heel": abs(heels[0][0][1] - heels[0][1][1]),
        "seat": abs(level[0][0][0] - level[0][1][0]),
        "seat_z": level[0][0][1],
        "heel_y": heels[0][0][0],
        "top_at_ridge": max(tops),
    }


# --- Goldens -----------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(GOLDEN_INPUTS))
def test_the_goldens_are_the_plugins_expansion(name: str) -> None:
    request, metadata = golden(name)
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / name / "members.json").read_text() == _members_json(metadata)


# --- B2, member by member ----------------------------------------------------------


def test_b2_is_the_default_roof() -> None:
    assert members() == members(GOLDEN_INPUTS["b2-roof-6-12"])


def test_b2_rafters_and_ridge_are_the_specs() -> None:
    """buildings.md B2 roof: 14 2x6 rafters at 24 in o.c. bearing on the front
    and back walls, a 2x8 ridge 144 long centred on Y 60."""
    got = bodies(members())
    assert Counter(role for role, _ in got) == {"rafter": 14, "ridge": 1}
    for i, centre in enumerate(CENTRES):
        for side in (0, 1):
            x0, x1, _ = got[("rafter", 2 * i + side)]
            assert (x0, x1) == (centre - 0.75, centre + 0.75)
    x0, x1, ridge = got[("ridge", 0)]
    assert (x0, x1) == (0, 144)
    ys = sorted({round(y, 9) for y, _ in ridge})
    zs = sorted({round(z, 9) for _, z in ridge})
    assert ys == [59.25, 60.75]
    assert zs[1] - zs[0] == pytest.approx(7.25, abs=1e-9)


@pytest.mark.parametrize(
    ("raw", "line_length", "seat", "heel"),
    [
        # "line length between plumb cuts is 79.660 ... seats the full 3.5
        # plate with a 1.75 heel"
        ({}, 79.660, 3.5, 1.75),
        # "Pitch 6/12 -> 8/12: line length 85.632 ... the seat shortens to
        # 2.75 with a 1.833 heel"
        ({"pitch": "rise_8"}, 85.632, 2.75, 1.833),
    ],
)
def test_every_rafter_cuts_to_the_spec(
    raw: dict[str, Any], line_length: float, seat: float, heel: float
) -> None:
    got = bodies(members(raw))
    rise = 8 if raw else 6
    for i in range(14):
        _, _, outline = got[("rafter", i)]
        assert area(outline) > 0  # counter-clockwise, one loop
        cut = cuts(outline)
        assert cut["line_length"] == pytest.approx(line_length, abs=5e-4)
        assert cut["seat"] == pytest.approx(seat, abs=5e-4)
        assert cut["heel"] == pytest.approx(heel, abs=5e-4)
        assert cut["heel"] <= 5.5 / 3 + 1e-9  # the 1/3-depth limit
        # The seat bears on the plate top; the heel is on the wall's face.
        assert cut["seat_z"] == pytest.approx(97.125, abs=1e-9)
        assert cut["heel_y"] == pytest.approx(0 if i % 2 == 0 else 120, abs=1e-9)
        # Plumb cuts are the 2x6's depth measured plumb.
        assert cut["plumb_cut"] == pytest.approx(
            5.5 * math.hypot(12, rise) / 12, abs=1e-9
        )
    # The ridge's top is flush with the rafters' top at its face.
    _, _, ridge = got[("ridge", 0)]
    assert max(z for _, z in ridge) == pytest.approx(
        cuts(got[("rafter", 0)][2])["top_at_ridge"], abs=1e-9
    )


def test_a_pair_is_mirrored_about_the_ridge() -> None:
    got = bodies(members())
    front, back = got[("rafter", 0)][2], got[("rafter", 1)][2]
    mirrored = sorted((round(120 - y, 9), round(z, 9)) for y, z in front)
    assert sorted((round(y, 9), round(z, 9)) for y, z in back) == mirrored


def test_metadata_is_plain_library_names() -> None:
    expansion = members()
    built = [m for m in expansion if isinstance(m.feature, ExtrudeFeature)]
    profiles = {m.role: m.metadata.profile for m in built if m.metadata}
    assert profiles == {"rafter": "2x6", "ridge": "2x8"}
    assert {m.metadata.material for m in built if m.metadata} == {"spf_lumber"}
    helpers = [m for m in expansion if not isinstance(m.feature, ExtrudeFeature)]
    assert all(m.metadata is None for m in helpers)


def test_roles_emit_in_the_cut_list_order() -> None:
    order = [m.role for m in members() if isinstance(m.feature, ExtrudeFeature)]
    assert list(dict.fromkeys(order)) == ["rafter", "ridge"]


# --- Determinism and stable ids ----------------------------------------------------


def test_the_expansion_is_deterministic() -> None:
    a = [m.model_dump(mode="json") for m in members()]
    b = [m.model_dump(mode="json") for m in members()]
    assert a == b


def test_member_ids_survive_the_pitch_edit() -> None:
    before = [(m.role, m.index, m.id) for m in members()]
    after = [(m.role, m.index, m.id) for m in members({"pitch": "rise_8"})]
    assert before == after


# --- Inputs ------------------------------------------------------------------------


def test_the_pitch_is_typed_per_12() -> None:
    pitch = next(i for i in ROOF.manifest.inputs if i.name == "pitch")
    assert pitch.kind == "choice"
    labels = [o.label for o in pitch.options]
    assert labels[0] == "1/12" and "6/12" in labels and labels[-1] == "24/12"
    assert pitch.default == "rise_6"


def test_spacing_drives_the_count() -> None:
    got = Counter(m.role for m in members({"spacing_mm": 16 * IN}))
    assert got["rafter"] == 2 * 10  # 0.75, 16, ..., 128, 143.25


def test_no_overhang_cuts_the_rafter_at_the_wall() -> None:
    got = bodies(members({"overhang_mm": 0.0}))
    outline = got[("rafter", 0)][2]
    assert len(outline) == 5 and min(y for y, _ in outline) == 0
    # Seat and heel are the full plate's; the wall face is the tail.
    assert (0.0, 97.125) in [(round(y, 9), round(z, 9)) for y, z in outline]


def test_material_inputs_reach_the_members() -> None:
    expansion = members({"ridge_material": "lvl", "rafter_material": "dfl_lumber"})
    by_role = {m.role: m.metadata for m in expansion if m.metadata}
    assert by_role["ridge"].material == "lvl"
    assert by_role["rafter"].material == "dfl_lumber"


def test_rafters_never_overlap_each_other_or_the_ridge() -> None:
    """Front and back rafters stop at the ridge's faces; neighbours sit a
    spacing apart (exact, on the plan and the sketch)."""
    for raw in [{}, {"pitch": "rise_12", "ridge_profile": "us_2x10"}]:
        got = bodies(members(raw))
        _, _, ridge = got[("ridge", 0)]
        ridge_y = sorted({y for y, _ in ridge})
        for (role, _), (_, _, outline) in got.items():
            if role != "rafter":
                continue
            ys = [y for y, _ in outline]
            assert max(ys) <= ridge_y[0] + 1e-9 or min(ys) >= ridge_y[1] - 1e-9
        xs = sorted(
            {(x0, x1) for (role, _), (x0, x1, _) in got.items() if role == "rafter"}
        )
        assert all(b[0] >= a[1] for a, b in itertools.pairwise(xs))


# --- Refusals ----------------------------------------------------------------------


def _refusal(raw: dict[str, Any]) -> PluginError:
    with pytest.raises(PluginError) as caught:
        members(raw)
    return caught.value


def test_a_ridge_shallower_than_the_plumb_cut_is_refused() -> None:
    error = _refusal({"ridge_profile": "us_2x6"})  # 5.5 < 6.149
    assert error.code == PLUGIN_INPUT_UNSUPPORTED and error.input == "ridge_profile"


if __name__ == "__main__":
    for name in sorted(GOLDEN_INPUTS):
        request, metadata = golden(name)
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(_members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
