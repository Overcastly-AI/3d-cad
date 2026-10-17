"""``loft.roof`` 1.1.0: the Style choice, and B3's hip roof (ROOF-HIP).

Numbers are typed from ``docs/reference-parts/buildings.md`` ("Hip and valley
conventions" and B3), never read back from the plugin. The geometry goldens
``b3-hip-6-12`` and ``b3-hip-8-12`` are this plugin's expansion
(``model.json``, member materials applied as documents sends them) and their
members' metadata (``members.json``); the first test pins the files to it,
so ``services/geometry/tests/test_roof_hip_b3.py`` reads files that cannot
drift. Regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_roof_hip.py``.
"""

import gzip
import json
import math
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, PluginError, canonical_inputs, expand
from loft_plugins.builtin.roof import Hip, jack_centres
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    BooleanFeature,
    DatumFeature,
    DatumMidplaneParams,
    DatumOffsetParams,
    DatumPlaneRef,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    ExtrudeFeature,
    FeatureRef,
    SketchFeature,
)
from loft_wire.materials import with_member_materials
from loft_wire.plugins import PLUGIN_INPUT_UNSUPPORTED
from loft_wire.sketch import SketchLine

IN = 25.4
ROOF_1_0 = REGISTRY.get("loft.roof", "1.0.0")
ROOF = REGISTRY.get("loft.roof", "1.1.0")
GEOMETRY = Path(__file__).resolve().parents[3] / "services" / "geometry"
GOLDENS = GEOMETRY / "goldens"
#: The kernel overlap sweep's requests (services/geometry/tests/test_roof_hip_b3.py).
SWEEP_FIXTURE = GEOMETRY / "tests" / "fixtures" / "roof-hip-sweep.json.gz"
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b3")
ROOF_ID = uuid.UUID("00000000-0000-0000-0000-0000000000f1")
HIP = {"style": "hip"}

#: golden name -> raw inputs (what the form sends; the rest are B3 defaults).
GOLDEN_INPUTS: dict[str, dict[str, Any]] = {
    "b3-hip-6-12": {**HIP, "pitch": "rise_6"},
    "b3-hip-8-12": {**HIP, "pitch": "rise_8"},
}


#: The overlap sweep: name -> (span, length, rise, spacing, overhang) in
#: inches, and the rafter, ridge and hip sizes. Ridge-end commons touching
#: (length = span + 1.5), 1/12 to 18/12, 16 / 19.2 / 24 o.c., overhangs 0,
#: 1/16 and 36, a wide roof of many jacks, and 2x8 commons.
SweepCase = tuple[tuple[float, float, int, float, float], tuple[str, str, str]]
SWEEP: dict[str, SweepCase] = {
    "span48-len49.5-3-12-oc16-oh0": (
        (48, 49.5, 3, 16, 0),
        ("us_2x6", "us_2x8", "us_2x8"),
    ),
    "span96-len200-12-12-oc24-oh6": (
        (96, 200, 12, 24, 6),
        ("us_2x6", "us_2x10", "us_2x10"),
    ),
    "span200-len216-4-12-oc24-oh24": (
        (200, 216, 4, 24, 24),
        ("us_2x6", "us_2x8", "us_2x8"),
    ),
    "span120-len144-1-12-oc24-oh12": (
        (120, 144, 1, 24, 12),
        ("us_2x6", "us_2x8", "us_2x8"),
    ),
    "span130-len157-9-12-oc19.2-oh1_16": (
        (130, 157, 9, 19.2, 1 / 16),
        ("us_2x6", "us_2x8", "us_2x8"),
    ),
    "span120-len144-18-12-oc24-oh12": (
        (120, 144, 18, 24, 12),
        ("us_2x6", "us_2x12", "us_2x12"),
    ),
    "span120-len168-6-12-2x8-oh36": (
        (120, 168, 6, 24, 36),
        ("us_2x8", "us_2x10", "us_2x10"),
    ),
}


def sweep_raw(name: str) -> dict[str, Any]:
    (span, length, rise, spacing, overhang), (rafter, ridge, hip) = SWEEP[name]
    return {
        "style": "hip",
        "span_mm": span * IN,
        "length_mm": length * IN,
        "pitch": f"rise_{rise}",
        "spacing_mm": spacing * IN,
        "overhang_mm": overhang * IN,
        "rafter_profile": rafter,
        "ridge_profile": ridge,
        "hip_profile": hip,
    }


def sweep_fixture() -> str:
    """The sweep's requests as geometry reads them (compact JSON)."""
    cases: list[dict[str, Any]] = []
    for name, ((span, length, *_), _) in SWEEP.items():
        request, metadata = golden(sweep_raw(name))
        cases.append(
            {
                "name": name,
                "bearing_in": {
                    "span": span,
                    "length": length,
                    "plate_height": 97.125,
                    "plate_width": 3.5,
                },
                "bodies": len(metadata),
                "request": request.model_dump(mode="json"),
            }
        )
    return json.dumps(cases, separators=(",", ":")) + "\n"


def members(
    raw: dict[str, Any] | None = None, version: str = "1.1.0"
) -> list[ExpandedMember]:
    plugin = ROOF if version == "1.1.0" else ROOF_1_0
    return expand(plugin, ROOF_ID, canonical_inputs(plugin.manifest, raw or {}), {})


def golden(
    raw: dict[str, Any], part_id: uuid.UUID = PART_ID
) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """A golden's evaluation request and its members' cut-list metadata."""
    expansion = members(raw)
    titles = {role.role: role.title for role in ROOF.manifest.members}
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


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


def _refusal(raw: dict[str, Any]) -> PluginError:
    with pytest.raises(PluginError) as caught:
        members(raw)
    return caught.value


Plane = tuple[str, float]  # ("YZ", x) or ("XZ", y) of the member's datum face


def placed(expansion: list[ExpandedMember]) -> dict[tuple[str, int], Plane]:
    """Each common, jack and ridge body by the datum it is sketched on: a
    YZ plane at X (extruded +X), or an XZ plane at Y (extruded -Y)."""
    by_id = {m.id: m for m in expansion}
    out: dict[tuple[str, int], Plane] = {}
    for m in expansion:
        if not isinstance(m.feature, ExtrudeFeature) or m.role not in (
            "common",
            "jack",
            "ridge",
        ):
            continue
        sketch = by_id[m.feature.params.profile.feature_id].feature
        assert isinstance(sketch, SketchFeature)
        plane = sketch.params.plane
        if isinstance(plane, DatumPlaneRef):
            out[(m.role, m.index)] = (plane.plane, 0.0)
            continue
        datum = by_id[plane.feature_id].feature
        assert isinstance(datum, DatumFeature)
        assert isinstance(datum.params, DatumOffsetParams)
        assert not datum.params.flip
        sign = 1 if datum.params.base == "YZ" else -1  # XZ's normal is -Y
        out[(m.role, m.index)] = (
            datum.params.base,
            round(sign * datum.params.offset_mm / IN, 9),
        )
    return out


def outline(
    expansion: list[ExpandedMember], ref: FeatureRef
) -> list[tuple[float, float]]:
    """A section sketch's closed polygon, in inches."""
    sketch = next(m for m in expansion if m.id == ref.feature_id).feature
    assert isinstance(sketch, SketchFeature)
    lines = [e for e in sketch.params.entities if isinstance(e, SketchLine)]
    for a, b in zip(lines, lines[1:] + lines[:1], strict=True):
        assert a.end == b.start
    return [(e.start.x / IN, e.start.y / IN) for e in lines]


# --- Goldens and 1.0.0 -------------------------------------------------------------


def test_the_sweep_fixture_is_the_plugins_expansion() -> None:
    assert gzip.decompress(SWEEP_FIXTURE.read_bytes()).decode() == sweep_fixture()


@pytest.mark.parametrize("name", sorted(GOLDEN_INPUTS))
def test_the_goldens_are_the_plugins_expansion(name: str) -> None:
    request, metadata = golden(GOLDEN_INPUTS[name])
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDENS / name / "members.json").read_text() == _members_json(metadata)


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"pitch": "rise_8"},
        {"spacing_mm": 16 * IN, "overhang_mm": 0.0},
        {"pitch": "rise_12", "ridge_profile": "us_2x10", "span_mm": 200 * IN},
    ],
)
def test_gable_at_1_1_is_1_0_member_for_member(raw: dict[str, Any]) -> None:
    """Style Gable is 1.0.0's expansion: the same members under the same ids,
    so an edit from Hip back to Gable gives B2's roof exactly."""
    old = [m.model_dump(mode="json") for m in members(raw, "1.0.0")]
    new = [m.model_dump(mode="json") for m in members({**raw, "style": "gable"})]
    assert new == old


def test_gable_at_1_1_is_b2s_golden() -> None:
    request, _ = golden({}, uuid.UUID("00000000-0000-0000-0000-0000000000b2"))
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDENS / "b2-roof-6-12" / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")


def test_1_1_is_additive_and_the_latest() -> None:
    """1.1.0 keeps every 1.0.0 input (a stored roof's inputs are a 1.1.0
    roof's), adds Style (Gable by default) and the hip size, and is what a
    new Roof is inserted with; 1.0.0 stays installed for stored roofs."""
    assert REGISTRY.latest("loft.roof").manifest.version == "1.1.0"
    old = {i.name for i in ROOF_1_0.manifest.inputs}
    new = [i.name for i in ROOF.manifest.inputs]
    assert old <= set(new) and set(new) - old == {"style", "hip_profile"}
    style = next(i for i in ROOF.manifest.inputs if i.name == "style")
    assert style.kind == "choice" and style.default == "gable"
    assert [o.label for o in style.options] == ["Gable", "Hip"]
    hip = next(i for i in ROOF.manifest.inputs if i.name == "hip_profile")
    assert hip.kind == "choice" and hip.default == "us_2x8"
    stored = canonical_inputs(ROOF_1_0.manifest, {"pitch": "rise_8"})
    assert canonical_inputs(ROOF.manifest, stored)["style"] == "gable"


# --- buildings.md's hip conventions, by hand --------------------------------------


@pytest.mark.parametrize(
    ("rise", "unit", "line", "drop", "heel", "plumb"),
    [
        # "unit length 18.00 ... (59.25 + 12) x 18/12 = 106.875 ... drop 0.265
        # ... heel 3.556 on the centreline, plumb depth 7.690"
        (6, 18.00, 106.875, 0.265, 3.556, 7.690),
        # "hips 111.397 (unit 18.76, drop 0.354)"
        (8, 18.76, 111.397, 0.354, None, None),
    ],
)
def test_the_hip_is_the_specs(
    rise: int,
    unit: float,
    line: float,
    drop: float,
    heel: float | None,
    plumb: float | None,
) -> None:
    slope = rise / 12
    seat = min(3.5, 5.5 / 3 / slope)
    hap = 5.5 * math.hypot(12, rise) / 12 - seat * slope
    hip = Hip(rise, 7.25, 1.5, 97.125, hap, 59.25, 12.0)
    assert hip.unit_length == pytest.approx(unit, abs=5e-3)
    assert hip.line_length == pytest.approx(line, abs=5e-4)
    assert hip.drop == pytest.approx(drop, abs=5e-4)
    if heel is not None and plumb is not None:
        assert hip.heel == pytest.approx(heel, abs=5e-4)
        assert hip.plumb_depth == pytest.approx(plumb, abs=5e-4)


@pytest.mark.parametrize(
    ("rise", "long", "short", "decrement"),
    [(6, 52.480, 25.647, 26.833), (8, 56.414, 27.570, 28.844)],
)
def test_the_jacks_shorten_by_the_common_difference(
    rise: int, long: float, short: float, decrement: float
) -> None:
    """Jacks 12 and 36 in from each corner (buildings.md B3), centre runs
    34.939 and 10.939 (the hip's 45 deg half thickness, 0.75 x sqrt 2 =
    1.061, off the layout point), one spacing apart: 24 x unit / 12."""
    centres = jack_centres(60.0, 24.0, 1.5, 1.5, min(3.5, 5.5 / 3 / (rise / 12)))
    assert centres == [36.0, 12.0]
    unit = math.hypot(12, rise)
    lines = [(12.0 + c - 0.75 * math.sqrt(2)) * unit / 12 for c in centres]
    assert lines == [pytest.approx(long, abs=5e-4), pytest.approx(short, abs=5e-4)]
    assert lines[0] - lines[1] == pytest.approx(decrement, abs=5e-4)


def test_no_tail_jack_and_the_layout_on_16() -> None:
    # B3: "No tail jack: the next layout point is the fascia corner."
    assert jack_centres(60.0, 24.0, 1.5, 1.5, 3.5) == [36.0, 12.0]
    # On 16: 44, 28, 12; -4 would be a tail jack (ROOF-TAIL-JACKS).
    assert jack_centres(60.0, 16.0, 1.5, 1.5, 3.5) == [44.0, 28.0, 12.0]
    # A layout point whose cheek would cut into the seat is not framed.
    assert jack_centres(50.0, 24.0, 1.5, 1.5, 3.5) == [26.0]


# --- B3, member by member ----------------------------------------------------------


def test_b3_has_the_specs_members() -> None:
    """buildings.md B3: 6 commons, 16 hip jacks, 4 hips, 1 ridge (27)."""
    expansion = members(HIP)
    bodies = Counter(m.role for m in expansion if isinstance(m.feature, ExtrudeFeature))
    assert bodies == {"common": 6, "jack": 16, "hip": 4, "ridge": 1, "cutter": 24}
    trims = [m.feature for m in expansion if isinstance(m.feature, BooleanFeature)]
    # Each jack is intersected with its plan; each hip too, then its seat cut.
    assert Counter(t.params.operation for t in trims) == {
        "intersect": 20,
        "subtract": 4,
    }
    targets = {m.id: m.role for m in expansion}
    assert Counter(targets[t.params.target.feature_id] for t in trims) == {
        "jack": 16,
        "hip": 8,
    }
    assert {targets[t.params.tool.feature_id] for t in trims} == {"cutter"}


def test_b3_layout_is_the_specs() -> None:
    """Commons at X 60 and 84 (front, back) and the kings on Y 60; jacks
    front and back at X 12, 36, 108, 132 and on the ends at Y 12, 36, 84,
    108; the ridge X 59.25..84.75 (25.5) on Y 59.25..60.75."""
    expansion = members(HIP)
    got = placed(expansion)
    commons = Counter(p for (role, _), p in got.items() if role == "common")
    assert commons == {("YZ", 59.25): 2, ("YZ", 83.25): 2, ("XZ", 60.75): 2}
    jacks = Counter(p for (role, _), p in got.items() if role == "jack")
    want = {("YZ", x - 0.75): 2 for x in (12, 36, 108, 132)}
    want |= {("XZ", y + 0.75): 2 for y in (12, 36, 84, 108)}
    assert jacks == want
    assert got[("ridge", 0)] == ("YZ", 59.25)
    ridge = next(m for m in expansion if m.role == "ridge").feature
    assert isinstance(ridge, ExtrudeFeature)
    assert ridge.params.distance_mm / IN == pytest.approx(25.5, abs=1e-12)
    ys = {round(y, 9) for y, _ in outline(expansion, ridge.params.profile)}
    assert ys == {59.25, 60.75}


def _hip_line(corner: tuple[float, float], point: tuple[float, float]) -> float:
    """Signed plan distance of *point* from the hip's centreline at *corner*."""
    (cx, cy), (x, y) = corner, point
    dx, dy = (1 if cx == 0 else -1), (1 if cy == 0 else -1)
    return ((x - cx) * dy - (y - cy) * dx) / math.sqrt(2)


def test_every_jack_cheek_is_on_its_hips_side_face() -> None:
    """Each jack's cutter has one edge off the axes, the cheek: it lies on
    the side face of the hip from the nearest corner, 0.75 off the hip's
    centreline, and is 45 deg in plan."""
    expansion = members(HIP)
    by_id = {m.id: m for m in expansion}
    corners = [(0.0, 0.0), (144.0, 0.0), (0.0, 120.0), (144.0, 120.0)]
    cheeks = 0
    for m in expansion:
        if not isinstance(m.feature, BooleanFeature):
            continue
        if by_id[m.feature.params.target.feature_id].role != "jack":
            continue
        cutter = by_id[m.feature.params.tool.feature_id].feature
        assert isinstance(cutter, ExtrudeFeature)
        points = outline(expansion, cutter.params.profile)
        edges = list(zip(points, points[1:] + points[:1], strict=True))
        slanted = [
            (a, b)
            for a, b in edges
            if abs(a[0] - b[0]) > 1e-9 and abs(a[1] - b[1]) > 1e-9
        ]
        assert len(slanted) == 1
        (a, b) = slanted[0]
        assert abs(a[0] - b[0]) == pytest.approx(abs(a[1] - b[1]), abs=1e-9)
        corner = min(corners, key=lambda c: math.dist(c, a))
        assert abs(_hip_line(corner, a)) == pytest.approx(0.75, abs=1e-9)
        assert abs(_hip_line(corner, b)) == pytest.approx(0.75, abs=1e-9)
        cheeks += 1
    assert cheeks == 16


def test_each_hip_is_sketched_on_a_midplane_at_its_corner() -> None:
    expansion = members(HIP)
    by_id = {m.id: m for m in expansion}
    hips = [m for m in expansion if m.role == "hip"]
    assert len(hips) == 4
    for hip in hips:
        assert isinstance(hip.feature, ExtrudeFeature)
        assert hip.feature.params.extent == "symmetric"
        assert hip.feature.params.distance_mm == pytest.approx(1.5 * IN)
        sketch = by_id[hip.feature.params.profile.feature_id].feature
        assert isinstance(sketch, SketchFeature)
        plane = sketch.params.plane
        assert isinstance(plane, FeatureRef)
        datum = by_id[plane.feature_id].feature
        assert isinstance(datum, DatumFeature)
        assert isinstance(datum.params, DatumMidplaneParams)
    assert all(m.metadata is not None for m in hips)
    assert {(m.metadata.profile, m.metadata.material) for m in hips if m.metadata} == {
        ("2x8", "spf_lumber")
    }


def test_roles_emit_in_the_cut_list_order() -> None:
    """Commons, the long jacks first, hips, ridge (buildings.md B3's table)."""
    order = [
        m.role
        for m in members(HIP)
        if isinstance(m.feature, ExtrudeFeature) and m.metadata is not None
    ]
    assert list(dict.fromkeys(order)) == ["common", "jack", "hip", "ridge"]
    jacks = [p for (role, _), p in placed(members(HIP)).items() if role == "jack"]
    assert jacks[0] == ("YZ", 35.25)  # the first jack is a long one (X 36)


def test_spacing_drives_the_counts() -> None:
    got = Counter(m.role for m in members({**HIP, "spacing_mm": 16 * IN}))
    # Side commons at X 60, 75.25, 84 per side + 2 kings; jacks 44, 28, 12.
    assert got["common"] == 8 and got["jack"] == 24 and got["hip"] == 4


def test_the_expansion_is_deterministic_and_ids_survive_the_pitch_edit() -> None:
    a = [m.model_dump(mode="json") for m in members(HIP)]
    assert a == [m.model_dump(mode="json") for m in members(HIP)]
    before = [(m.role, m.index, m.id) for m in members(HIP)]
    after = [(m.role, m.index, m.id) for m in members({**HIP, "pitch": "rise_8"})]
    assert before == after


def test_no_overhang_frames_a_hip_without_tails() -> None:
    expansion = members({**HIP, "overhang_mm": 0.0})
    assert Counter(m.role for m in expansion)["hip"] == 4


# --- Refusals ----------------------------------------------------------------------


def test_a_hip_shallower_than_the_commons_plumb_cut_is_refused() -> None:
    error = _refusal({**HIP, "hip_profile": "us_2x6"})  # 5.5 < 6.149
    assert error.code == PLUGIN_INPUT_UNSUPPORTED and error.input == "hip_profile"


def test_a_hip_roof_shorter_than_its_span_is_refused() -> None:
    error = _refusal({**HIP, "length_mm": 121 * IN})  # < 120 + 1.5
    assert error.code == PLUGIN_INPUT_UNSUPPORTED and error.input == "length_mm"
    assert members({**HIP, "length_mm": 121.5 * IN})  # ridge-end commons touch


@pytest.mark.parametrize("style", ["gable", "hip"])
def test_a_sliver_of_overhang_is_refused(style: str) -> None:
    """ROOF-OVERHANG-MIN: 0 or at least 1/16 in; 2.54e-8 mm broke the kernel."""
    error = _refusal({"style": style, "overhang_mm": 2.54e-8})
    assert error.code == PLUGIN_INPUT_UNSUPPORTED and error.input == "overhang_mm"
    assert members({"style": style, "overhang_mm": IN / 16})
    assert members({"style": style, "overhang_mm": 0.0})


if __name__ == "__main__":
    for name, raw in sorted(GOLDEN_INPUTS.items()):
        request, metadata = golden(raw)
        (GOLDENS / name).mkdir(parents=True, exist_ok=True)
        (GOLDENS / name / "model.json").write_text(
            request.model_dump_json(indent=2) + "\n"
        )
        (GOLDENS / name / "members.json").write_text(_members_json(metadata))
        sys.stdout.write(f"{name}: {len(request.features)} features\n")
    SWEEP_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    SWEEP_FIXTURE.write_bytes(gzip.compress(sweep_fixture().encode(), mtime=0))
    sys.stdout.write(f"{SWEEP_FIXTURE.name}: {len(SWEEP)} cases\n")
