"""GYPSUM-SHEETS: ``loft.ceiling`` 1.0.0 hangs gypsum board under a gable's
ceiling joists (Revit's Ceiling, Chief Architect's ceiling surface).

Checked against ``docs/reference-parts/buildings.md`` B7 and B10, typed by
hand:

* B7 (``loft.roof`` 1.8.0, every default: 11 ceiling joists 2x8 at X c +
  0.75 .. c + 2.25 for c = 24, ..., 264, plates topped at Z 108.59375):
  the ceiling X 5.5..282.5 by Y 5.5..186.5 (inside the walls' framing),
  Z 108.09375..108.59375, in courses from the front wall, Y 5.5..53.5,
  ..101.5, ..149.5 and a 37 in rip ..186.5; each course 140 + 137, the
  joint on the joist at X 145.5 (144.75..146.25), the farthest a 4x12 from
  X 5.5 reaches (149.5): 8 panels, 50 137 in^2 (348.17 ft^2);
* every panel names its 4x12 and is 1/2 ceiling gypsum;
* 28 ft: 325 is 140 + 144 + 41, the joints at X 145.5 and 289.5; 4x8
  sheets: 96 reaches X 97.5 (joist at 97.5), so 92 + 96 + 89;
* B10: the partitions reach the board, so P1 (with its gypsum, X 177.75 ..
  182.25) and P2 (Y 129.75..134.25 from P1 to the right wall) are cut out;
  with the walls' inside gypsum the room is X 6..282 by Y 6..186;
* along Y (the ridge along Y), the courses run along X from the left wall;
* refused: a hip, Ceiling joists None, a roof before 1.6.0;
* no ceiling box meets another body's but face to face (the geometry test
  probes every pair exactly).

The geometry golden ``b7-ceiling`` and the kernel fixture
``ceiling-cases.json.gz`` are written from here and pinned by this module
(``services/geometry/tests/test_ceiling_b7.py`` checks them exactly).
Regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_ceiling.py``.
"""

import gzip
import json
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, ExpandInputs, Hosted, PluginError, canonical_inputs
from loft_plugins.builtin.ceiling import sheet_runs
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    AuthoredEnvelope,
    EvaluateTreeRequest,
    ExpandedMember,
    SketchFeature,
)

sys.path.insert(0, str(Path(__file__).parent))
from test_building_outline import (
    B7_FLOOR,
    B7_ROOF,
    B7_STUDS,
    GOLDENS,
    IN,
    ROOF_ID,
    WALLS_ID,
    boxes,
    envelope,
    expand,
    house,
    members_json,
    members_of,
    rectangle,
    ref,
    request_of,
)
from test_ceiling_joists import B7_GABLE, Rows, b7_roofed, roofed
from test_interior_walls import INTERIOR, INTERIOR_ID, WALL_1_4, b10, titles

CEILING = REGISTRY.get("loft.ceiling", "1.0.0")
ROOF_1_5 = REGISTRY.get("loft.roof", "1.5.0")
ROOF_1_8 = REGISTRY.get("loft.roof", "1.8.0")
CEILING_ID = uuid.UUID("00000000-0000-0000-0000-00000000b7c1")
GOLDEN = "b7-ceiling"
CASES = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "geometry"
    / "tests"
    / "fixtures"
    / "ceiling-cases.json.gz"
)
PART_ID = uuid.UUID("00000000-0000-0000-0000-0000000ce111")

PLATE = 1.5 + 9.25 + 23 / 32 + 97.125  # 108.59375
#: B7's ceiling joists' centres: beside each inner common, X c + 1.5.
JOISTS = [c + 1.5 for c in range(24, 265, 24)]


def hung(rows: Rows, raw: dict[str, Any] | None = None) -> Rows:
    """*rows* with a ceiling on their roof appended, as documents builds it."""
    earlier: dict[uuid.UUID, AuthoredEnvelope] = {}
    for fid, env, members in rows:
        earlier[fid] = env
        for m in members:
            earlier[m.id] = m.feature
    full = {"roof": ref(ROOF_ID), **(raw or {})}
    members = expand(CEILING, CEILING_ID, full, earlier)
    return [*rows, (CEILING_ID, envelope(CEILING, full), members)]


def b7(length: float = 288.0, raw: dict[str, Any] | None = None) -> Rows:
    return hung(b7_roofed(length, None, ROOF_1_8), raw)


def b10_hung(walls: dict[str, Any] | None = None) -> Rows:
    return hung(roofed(b10(walls=walls, roof=False), B7_GABLE, ROOF_1_8))


def ceiling_of(rows: Rows) -> list[ExpandedMember]:
    return next(ms for fid, _, ms in rows if fid == CEILING_ID)


def panels(rows: Rows) -> list[tuple[float, ...]]:
    return sorted(
        tuple(round(v, 6) for v in b) for b in boxes(ceiling_of(rows), ("ceiling",))
    )


# --- The layout -----------------------------------------------------------------------


def test_a_sheet_ends_on_the_farthest_joist_it_reaches() -> None:
    assert sheet_runs(5.5, 282.5, JOISTS, 144) == [(5.5, 145.5), (145.5, 282.5)]
    assert sheet_runs(5.5, 100.0, JOISTS, 144) == [(5.5, 100.0)]
    with pytest.raises(ValueError):
        sheet_runs(0.0, 200.0, [150.0], 144)


def test_b7s_ceiling_is_8_panels_140_and_137_on_the_joist_at_145_5() -> None:
    got = panels(b7())
    z = (round(PLATE - 0.5, 6), round(PLATE, 6))
    want = sorted(
        (a0, a1, b0, b1, *z)
        for b0, b1 in ((5.5, 53.5), (53.5, 101.5), (101.5, 149.5), (149.5, 186.5))
        for a0, a1 in ((5.5, 145.5), (145.5, 282.5))
    )
    assert got == want
    area = sum((b[1] - b[0]) * (b[3] - b[2]) for b in got)
    assert area == 277 * 181 == 50137
    assert round(area / 144, 2) == 348.17
    assert 144.75 < 145.5 < 146.25  # on the joist beside the common at 144


def test_every_panel_is_ceiling_board_hung_from_a_4x12() -> None:
    meta = [m.metadata for m in ceiling_of(b7()) if m.role == "ceiling"]
    assert len(meta) == 8
    assert {(m.profile, m.material, m.sheet) for m in meta if m} == {
        ("1/2 ceiling gypsum", "gypsum", "4x12")
    }


def test_28_ft_and_4x8_sheets_land_every_joint_on_a_joist() -> None:
    long = {(b[0], b[1]) for b in panels(b7(336))}
    assert long == {(5.5, 145.5), (145.5, 289.5), (289.5, 330.5)}
    short = {(b[0], b[1]) for b in panels(b7(raw={"finish_sheet": "sheet_4x8"}))}
    assert short == {(5.5, 97.5), (97.5, 193.5), (193.5, 282.5)}
    meta = [m.metadata for m in ceiling_of(b7(raw={"finish": "gypsum_5_8"}))]
    assert {m.profile for m in meta if m} == {"5/8 gypsum"}
    z0 = min(b[4] for b in panels(b7(raw={"finish": "gypsum_5_8"})))
    assert z0 == round(PLATE - 0.625, 6)


def test_b10s_partitions_are_cut_out_with_their_gypsum() -> None:
    got = panels(b10_hung())
    # P1 with its boards: nothing of the ceiling between X 177.75 and 182.25.
    assert all(b[1] <= 177.75 or b[0] >= 182.25 for b in got)
    # P2 with its boards, east of P1: nothing between Y 129.75 and 134.25.
    east = [b for b in got if b[0] >= 182.25]
    assert all(b[3] <= 129.75 or b[2] >= 134.25 for b in east)
    area = sum((b[1] - b[0]) * (b[3] - b[2]) for b in got)
    assert area == pytest.approx(277 * 181 - 4.5 * 181 - 4.5 * 100.25, abs=1e-9)


def test_inside_gypsum_shrinks_the_room_to_the_boards() -> None:
    got = panels(b10_hung({"finish": "gypsum_1_2"}))
    assert min(b[0] for b in got) == 6.0 and max(b[1] for b in got) == 282.0
    assert min(b[2] for b in got) == 6.0 and max(b[3] for b in got) == 186.0


def along_y() -> Rows:
    moved = rectangle(192, 288).model_dump(mode="json")
    for e in moved["params"]["entities"]:
        if e["id"] == "origin":
            e["position"] = {"x": 24 * IN, "y": 36 * IN}
    rows = house(SketchFeature.model_validate(moved), [], B7_STUDS, B7_FLOOR, None)
    return hung(roofed(rows, {"slope_walls": ["e2", "e4"], **B7_ROOF}, ROOF_1_8))


def test_along_y_the_courses_run_along_x() -> None:
    got = panels(along_y())
    assert len(got) == 8
    # The house is 192 x 288 at (24, 36): the room X 29.5..210.5, Y 41.5..318.5.
    assert min(b[0] for b in got) == 29.5 and max(b[1] for b in got) == 210.5
    assert min(b[2] for b in got) == 41.5 and max(b[3] for b in got) == 318.5
    assert {(b[0], b[1]) for b in got} == {
        (29.5, 77.5),
        (77.5, 125.5),
        (125.5, 173.5),
        (173.5, 210.5),
    }


# --- Tree order (CEILING-ORDER) -------------------------------------------------------

CEILING_OVER = (
    "A ceiling earlier in the tree hangs over this wall; move the wall above "
    "the ceiling in the tree."
)


def _earlier(rows: Rows) -> dict[uuid.UUID, AuthoredEnvelope]:
    out: dict[uuid.UUID, AuthoredEnvelope] = {}
    for fid, env, members in rows:
        out[fid] = env
        for m in members:
            out[m.id] = m.feature
    return out


def _ceiling_first() -> Rows:
    """B10's sketch, floor and walls, the roof and a ceiling, no partitions."""
    return hung(roofed(b10(roof=False, partitions=False), B7_GABLE, ROOF_1_8))


def test_partitions_after_the_ceiling_are_refused_naming_why() -> None:
    """A ceiling laid out before the partitions runs through their plates:
    the Interior wall after it is refused on its Exterior walls pick."""
    with pytest.raises(PluginError) as caught:
        expand(
            INTERIOR,
            INTERIOR_ID,
            {"host_wall": ref(WALLS_ID)},
            _earlier(_ceiling_first()),
        )
    assert caught.value.message == CEILING_OVER
    assert caught.value.input == "host_wall"
    assert caught.value.code == "plugin_input_unsupported"


def test_walls_hosting_partitions_after_a_ceiling_are_refused() -> None:
    """The framed-wall path: walls re-expanded after a ceiling on them (a
    reorder) with a partition hosted refuse too, naming the partition."""
    rows = _ceiling_first()
    walls = next(env for fid, env, _ in rows if fid == WALLS_ID)
    raw = dict(walls.params.inputs)  # type: ignore[union-attr]
    interior = canonical_inputs(INTERIOR.manifest, {"host_wall": ref(WALLS_ID)})
    hosted = Hosted(
        INTERIOR_ID,
        INTERIOR.manifest.id,
        INTERIOR.manifest.version,
        "Interior walls",
        ExpandInputs(INTERIOR_ID, interior),
    )
    with pytest.raises(PluginError) as caught:
        expand(WALL_1_4, WALLS_ID, raw, _earlier(rows), (hosted,))
    assert caught.value.message == f"Interior walls: {CEILING_OVER}"
    assert caught.value.input == "host_wall"


def test_partitions_before_the_ceiling_are_fine() -> None:
    rows = b10_hung()
    assert any(
        m.role == "stud" for fid, _, ms in rows if fid == INTERIOR_ID for m in ms
    )
    assert panels(rows)


# --- Refusals -------------------------------------------------------------------------


def _refused(rows: Rows) -> str:
    with pytest.raises(PluginError) as caught:
        hung(rows)
    return caught.value.message


def test_a_hip_none_and_an_old_roof_are_refused() -> None:
    walls = house(rectangle(288, 192), [], B7_STUDS, B7_FLOOR, None)
    assert "gable" in _refused(
        roofed(walls, {**B7_ROOF, "style": "hip", "hip_profile": "us_2x10"}, ROOF_1_8)
    )
    none = {**B7_GABLE, "ceiling_joists": "none"}
    assert "Beside each common" in _refused(roofed(walls, none, ROOF_1_8))
    assert "1.6.0" in _refused(roofed(walls, B7_GABLE, ROOF_1_5))


def test_the_manifest() -> None:
    m = CEILING.manifest
    values = canonical_inputs(m, {"roof": ref(ROOF_ID)})
    assert values["finish"] == "gypsum_ceiling_1_2"
    assert values["finish_sheet"] == "sheet_4x12"
    assert [r.role for r in m.members] == [
        "ceiling_level",
        "ceiling_section",
        "ceiling",
    ]


# --- No overlaps ----------------------------------------------------------------------


@pytest.mark.parametrize("case", ["b7", "b7-336", "b10", "b10-inside-gypsum"])
def test_no_panel_box_meets_another_body(case: str) -> None:
    rows = {
        "b7": b7,
        "b7-336": lambda: b7(336),
        "b10": b10_hung,
        "b10-inside-gypsum": lambda: b10_hung({"finish": "gypsum_1_2"}),
    }[case]()
    members = members_of(rows)
    mine = boxes(members, ("ceiling",))
    roles = tuple({m.role for m in members} - {"ceiling"} - {"rafter"})
    others = boxes(members, roles) + mine
    assert mine
    assert [
        (a, b)
        for a in mine
        for b in others
        if a is not b
        and all(min(a[k + 1], b[k + 1]) - max(a[k], b[k]) > 1e-6 for k in (0, 2, 4))
    ] == []


# --- The golden and the kernel's cases ------------------------------------------------


def metadata_of(rows: Rows) -> list[CutListMember]:
    names = {
        **titles(),
        **{("loft.roof", r.role): r.title for r in ROOF_1_8.manifest.members},
        **{("loft.ceiling", r.role): r.title for r in CEILING.manifest.members},
    }
    out: list[CutListMember] = []
    for _, env, members in rows:
        plugin_id = getattr(getattr(env, "params", None), "plugin_id", None)
        for m in members:
            if m.metadata is not None:
                out.append(
                    CutListMember(
                        feature_id=m.id,
                        role=m.role,
                        title=names[(str(plugin_id), m.role)],
                        plugin_id=plugin_id,
                        metadata=m.metadata,
                    )
                )
    return out


def golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """b7-gable-ends' tree with its roof at 1.8.0 (the same members: B7's
    walls carry no finish) and a ceiling, every default kept."""
    rows = b7()
    request = request_of(rows).model_copy(update={"part_id": PART_ID})
    return request, metadata_of(rows)


def _count(rows: Rows, role: str) -> int:
    return sum(1 for m in members_of(rows) if m.role == role)


def cases() -> str:
    """B10 under its ceiling (with and without its walls' inside gypsum), B7
    at 28 ft and at 8/12, and B7 turned off the origin; each with its counts."""
    built = {
        "b10": b10_hung(),
        "b10-inside-gypsum": b10_hung({"finish": "gypsum_1_2"}),
        "b7-336": b7(336),
        "b7-8-12": hung(
            b7_roofed(raw={**B7_GABLE, "pitch": "rise_8"}, plugin=ROOF_1_8)
        ),
        "along-y-moved": along_y(),
    }
    out = [
        {
            "name": name,
            "bodies": sum(1 for m in members_of(rows) if m.metadata is not None),
            "panels": _count(rows, "ceiling"),
            "request": request_of(rows).model_dump(mode="json"),
        }
        for name, rows in built.items()
    ]
    return json.dumps(out, separators=(",", ":"), sort_keys=True)


def test_the_golden_is_the_plugins_expansion() -> None:
    request, metadata = golden()
    folder = GOLDENS / GOLDEN
    assert (folder / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (folder / "members.json").read_text() == members_json(metadata)


def test_the_golden_is_b7_gable_ends_and_8_panels() -> None:
    _, metadata = golden()
    assert len(metadata) == 262 + 8 == 270
    assert Counter(m.title for m in metadata)["Ceiling"] == 8


def test_the_kernel_cases_are_the_plugins_expansion() -> None:
    assert gzip.decompress(CASES.read_bytes()).decode() == cases()


if __name__ == "__main__":
    request, metadata = golden()
    (GOLDENS / GOLDEN).mkdir(parents=True, exist_ok=True)
    (GOLDENS / GOLDEN / "model.json").write_text(
        request.model_dump_json(indent=2) + "\n"
    )
    (GOLDENS / GOLDEN / "members.json").write_text(members_json(metadata))
    sys.stdout.write(f"{GOLDEN}: {len(request.features)} features\n")
    CASES.write_bytes(gzip.compress(cases().encode(), mtime=0))
    sys.stdout.write(f"{CASES.name}\n")
