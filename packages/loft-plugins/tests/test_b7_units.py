"""B7 with its window and door units (OPENING-UNITS, RESEARCH §23).

B7's openings at ``loft.window``/``loft.door`` 1.3.0, each picked by call
size: with the units left out it frames ``b7-from-end`` body for body, and
each unit sits clear of every member inside its rough opening. The geometry
golden ``b7-units`` is written from here and pinned by this module.
Regenerate after a deliberate change (a NEW plugin version) with
``uv run python packages/loft-plugins/tests/test_b7_units.py``.
"""

import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from loft_plugins import REGISTRY
from loft_wire.cut_list import CutListMember
from loft_wire.features import AuthoredEnvelope, EvaluateTreeRequest, ExpandedMember

# The B7 builders and body probes are test_building_outline's. pytest runs in
# importlib mode, which puts no test directory on sys.path, so add this one.
sys.path.insert(0, str(Path(__file__).parent))
from test_building_outline import (
    B7_FLOOR,
    B7_ROOF,
    B7_STUDS,
    GOLDENS,
    IN,
    TITLES,
    b7_from_end,
    bodies,
    boxes,
    house,
    members_json,
    members_of,
    overlaps,
    rectangle,
    request_of,
)

WINDOW_1_3 = REGISTRY.get("loft.window", "1.3.0")
DOOR_1_3 = REGISTRY.get("loft.door", "1.3.0")
UNITS_GOLDEN = "b7-units"
UNIT_ROLES = ("frame", "glazing", "slab")


def b7_unit_openings(
    draw: str = "draw",
) -> list[tuple[Any, str, str, dict[str, Any]]]:
    """B7's openings at 1.3.0, placed as b7_from_end_openings places them,
    each picked by call size and no size field typed: the door and the three
    big windows take the defaults (3068, 3040), the side windows pick 2030."""
    unit = {"draw_unit": draw}
    small = {"size": "window_2030", **unit}
    return [
        (DOOR_1_3, "Door", "e1", {"offset_mm": 144 * IN, **unit}),
        (WINDOW_1_3, "Window 1", "e1", {"offset_mm": 60 * IN, **unit}),
        (WINDOW_1_3, "Window 2", "e1", {"offset_mm": 228 * IN, **unit}),
        (WINDOW_1_3, "Window 3", "e3", {"offset_mm": 144 * IN, **unit}),
        (WINDOW_1_3, "Window 4", "e4", {"offset_mm": 90.5 * IN, **small}),
        (WINDOW_1_3, "Window 5", "e2", {"offset_mm": 90.5 * IN, **small}),
    ]


def b7_units(
    draw: str = "draw",
) -> list[tuple[uuid.UUID, AuthoredEnvelope, list[ExpandedMember]]]:
    return house(
        rectangle(288, 192),
        b7_unit_openings(draw),
        B7_STUDS,
        B7_FLOOR,
        {"slope_walls": ["e1", "e3"], **B7_ROOF},
    )


def unit_members(members: list[ExpandedMember]) -> list[ExpandedMember]:
    return [m for m in members if m.role in UNIT_ROLES]


def test_picked_sizes_frame_the_typed_rough_openings_member_for_member() -> None:
    """3068, 3040 and 2030 frame 38 x 82.5, 36.5 x 48.5 and 24.5 x 36.5: with
    the units left out, B7 at 1.3.0 is B7 typed at 1.2.0, body for body."""
    typed = bodies(members_of(b7_from_end()))
    assert bodies(members_of(b7_units("none"))) == typed
    drawn = members_of(b7_units())
    framing = [m for m in drawn if m.role not in UNIT_ROLES]
    assert bodies(framing) == typed
    assert len(unit_members(drawn)) == 12


def test_each_unit_sits_in_its_rough_opening_clear_of_every_member() -> None:
    """Frame and glass (a door: frame and slab) 1/4 in inside the rough
    opening on each side (a door on the subfloor, 1/2 in under its header),
    touching no framing member, panel or rafter."""
    members = members_of(b7_units())
    units = unit_members(members)
    # Every box but the OSB's (a panel's box spans its holes) and the
    # rafters' (sloped; the kernel test probes them exactly). A frame's box
    # spans its own glass or slab, so units are checked against the rest.
    skip = ("sheathing", "rafter", *UNIT_ROLES)
    rest = boxes(members, tuple({m.role for m in members} - set(skip)))
    for unit in boxes(members, UNIT_ROLES):
        assert [p for p in overlaps([unit, *rest]) if p[0] == 0] == []
    assert len(units) == 12
    frames = sorted(boxes(members, ("frame",)))
    # Front wall (Y 0..5.5): the 3040s at X 60 and 228 and the door at 144;
    # the windows' frames 3.25 deep from the framing's face, the door's 5.5.
    sill = BASE_Z + 82.5 - 48.5
    want_front = [
        (42.0, 78.0, 0.0, 3.25, sill + 0.25, sill + 48.25),
        (125.25, 162.75, 0.0, 5.5, BASE_Z, BASE_Z + 82.0),
        (210.0, 246.0, 0.0, 3.25, sill + 0.25, sill + 48.25),
    ]
    front = [b for b in frames if b[3] <= 5.5 + 1e-9]
    assert [tuple(round(v, 6) for v in b) for b in front] == [
        tuple(round(v, 6) for v in b) for b in want_front
    ]


BASE_Z = 1.5 + 9.25 + 23 / 32  # the walls' base: the subfloor's top


def test_each_unit_carries_its_size_and_is_counted_once() -> None:
    units = unit_members(members_of(b7_units()))
    seen: Counter[tuple[str, str | None, str | None, bool]] = Counter()
    for m in units:
        assert m.metadata is not None and m.metadata.unit is not None
        seen[
            (m.role, m.metadata.profile, m.metadata.material, m.metadata.unit.counted)
        ] += 1
    assert seen == Counter(
        {
            ("frame", "3040", "pvc", True): 3,
            ("glazing", "3040", "glass", False): 3,
            ("frame", "2030", "pvc", True): 2,
            ("glazing", "2030", "glass", False): 2,
            ("frame", "3068", "spf_lumber", True): 1,
            ("slab", "3068", "spf_lumber", False): 1,
        }
    )
    keys = {m.metadata.unit.key for m in units if m.metadata and m.metadata.unit}
    assert keys == {"window_3040", "window_2030", "door_3068"}


UNIT_TITLES = {
    **TITLES,
    **{
        role.role: role.title
        for plugin in (WINDOW_1_3, DOOR_1_3)
        for role in plugin.manifest.members
    },
}


def units_golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    """B7 at 288 with every opening picked by size and its unit drawn."""
    rows = b7_units()
    metadata = [
        CutListMember(
            feature_id=m.id, role=m.role, title=UNIT_TITLES[m.role], metadata=m.metadata
        )
        for m in members_of(rows)
        if m.metadata is not None
    ]
    return request_of(rows), metadata


def test_the_units_golden_is_the_plugins_expansion() -> None:
    request, metadata = units_golden()
    folder = GOLDENS / UNITS_GOLDEN
    assert (folder / "model.json").read_text() == request.model_dump_json(
        indent=2
    ) + "\n"
    assert (folder / "members.json").read_text() == members_json(metadata)


if __name__ == "__main__":
    request, metadata = units_golden()
    (GOLDENS / UNITS_GOLDEN).mkdir(parents=True, exist_ok=True)
    (GOLDENS / UNITS_GOLDEN / "model.json").write_text(
        request.model_dump_json(indent=2) + "\n"
    )
    (GOLDENS / UNITS_GOLDEN / "members.json").write_text(members_json(metadata))
    sys.stdout.write(f"{UNITS_GOLDEN}: {len(request.features)} features\n")
