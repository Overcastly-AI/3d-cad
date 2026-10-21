"""ROOF-L-DOUBLED-COMMON: ``loft.roof`` 1.2.0 frames ONE common where an L's
wing jacks reach the flush ridge-end common's place an ulp off it.

Before the fix, 1.2.0 deduplicated layout positions exactly, so on 25 of 64
constructed L footprints it framed two coincident commons (an overlap, and a
common counted twice in the priced cut list). 1.2.0 now lays the twin out and
numbers it as before, then drops its own features (its section and body), so
every other member keeps its ``(role, index)`` and its id; a feature that
named the twin finds its member gone (``reference_unresolved``), never
another member. The line that survives is 1.3.0's (ROOF-MEMBER-RENUMBER):
the first of the king, the ridge layout and the jacks to reach the place.

The geometry golden ``l-hip-16oc-v1.2-one-common`` is such an L at 1.2.0
(walls picked, 16 in o.c.), and the fixture
``services/geometry/tests/fixtures/l-hip-16oc-v1.2-doubled.json.gz`` is the
expansion 1.2.0 gave before the fix, which
``services/geometry/tests/test_roof_l_doubled_common.py`` builds against it.
Regenerate after a deliberate change with
``uv run python packages/loft-plugins/tests/test_roof_l_doubled_common.py``.
"""

import gzip
import itertools
import json
import sys
import uuid
from collections import Counter
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from loft_plugins import REGISTRY, canonical_inputs, expand
from loft_plugins.builtin import roof_valley
from loft_wire.cut_list import CutListMember
from loft_wire.features import (
    CustomFeature,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExpandedMember,
    FeatureRef,
)
from loft_wire.materials import with_member_materials
from loft_wire.plugins import member_id

IN = 25.4
ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "services" / "geometry" / "goldens" / "l-hip-16oc-v1.2-one-common"
FIXTURE = (
    ROOT
    / "services"
    / "geometry"
    / "tests"
    / "fixtures"
    / "l-hip-16oc-v1.2-doubled.json.gz"
)
ROOF_V1_2 = REGISTRY.get("loft.roof", "1.2.0")
ROOF_V1_3 = REGISTRY.get("loft.roof", "1.3.0")
WALL = REGISTRY.get("loft.wall", "1.1.0")
PART = uuid.UUID("00000000-0000-0000-0000-0000000001c2")
ROOF_ID = uuid.UUID("00000000-0000-0000-0000-0000000000f1")

WallRow = tuple[float, float, float, float]


def l_walls(w: float, h: float, xa: float, yb: float) -> list[WallRow]:
    """Six 2x4 walls (start x, start y on the outer face, direction, length;
    framing on the right, clockwise, butted as B4's) round the L whose outer
    faces are (0, yb) (0, h) (w, h) (w, 0) (xa, 0) (xa, yb)."""
    return [
        (0, h, 0, w),
        (w, h - 3.5, 270, h - 3.5),
        (w - 3.5, 0, 180, w - 3.5 - xa),
        (xa, 3.5, 90, yb - 3.5),
        (xa + 3.5, yb, 180, xa + 3.5),
        (0, yb + 3.5, 90, h - yb - 7),
    ]


def l_cases() -> Iterator[tuple[float, list[WallRow]]]:
    """test_roof_member_names' 64 constructed L's (arms two spacings apart,
    so the wing's jacks run onto the flush ridge-end common), as walls."""
    for spacing, w2, b, a in itertools.product(
        (16.0, 19.2, 12.7, 17.1), (48.0, 50.3, 61.7, 72.9), (37.3, 51.1), (24.0, 33.3)
    ):
        w1 = w2 + 2 * spacing
        big_a, big_b = a + w2, b + w1
        if big_a - w1 < 1.5:
            big_a = w1 + 30 + a
            a = big_a - w2
        yield spacing, l_walls(big_a, big_b, a, b)


#: The golden's L: 157 x 144.8, the notch to (95.3, 51.1), 16 in o.c. (one of
#: the 25; its arms, 61.7 and 93.7, are two spacings apart).
GOLDEN_WALLS = l_walls(157.0, 144.8, 95.3, 51.1)
GOLDEN_SPACING = 16.0


def roof(version: str, spacing: float, rows: list[WallRow]) -> list[ExpandedMember]:
    plugin = REGISTRY.get("loft.roof", version)
    refs: list[FeatureRef] = []
    earlier: dict[uuid.UUID, Any] = {}
    for index, (x, y, direction, length) in enumerate(rows):
        feature_id = uuid.UUID(int=0xB4A11 * 256 + index)
        inputs = canonical_inputs(
            WALL.manifest,
            {
                "start_x_mm": x * IN,
                "start_y_mm": y * IN,
                "direction_deg": float(direction),
                "length_mm": length * IN,
            },
        )
        earlier[feature_id] = CustomFeature.model_validate(
            {
                "type": "custom",
                "version": 1,
                "params": {
                    "plugin_id": "loft.wall",
                    "plugin_version": "1.1.0",
                    "inputs": inputs,
                },
            }
        )
        refs.append(FeatureRef(kind="feature", feature_id=feature_id))
    inputs = canonical_inputs(
        plugin.manifest,
        {"style": "hip", "spacing_mm": spacing * IN, "walls": refs},
    )
    return expand(plugin, ROOF_ID, inputs, earlier)


@contextmanager
def before_the_fix() -> Generator[None]:
    """1.2.0 as it expanded before ROOF-L-DOUBLED-COMMON: the twin kept."""
    real = roof_valley._drop_twins  # pyright: ignore[reportPrivateUsage]
    roof_valley._drop_twins = lambda _inputs, members, _dropped: members  # pyright: ignore[reportPrivateUsage]
    try:
        yield
    finally:
        roof_valley._drop_twins = real  # pyright: ignore[reportPrivateUsage]


def _doubled(members: list[ExpandedMember]) -> int:
    """How many rafters share their (resolved) feature with an earlier one."""
    table = {m.id: m for m in members}

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            fields: dict[str, Any] = node  # pyright: ignore[reportUnknownVariableType]
            target = fields.get("feature_id")
            if fields.get("kind") == "feature" and target is not None:
                ref = uuid.UUID(str(target))
                if ref in table:
                    return walk(table[ref].feature.model_dump(mode="json"))
            return {k: walk(v) for k, v in fields.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]  # pyright: ignore[reportUnknownVariableType]
        return node

    rafters = ("common", "jack", "valley_jack", "cripple")
    seen = Counter(
        json.dumps(walk(m.feature.model_dump(mode="json")), sort_keys=True)
        for m in members
        if m.role in rafters
    )
    return sum(n - 1 for n in seen.values())


def test_1_2_frames_one_common_where_it_framed_two() -> None:
    """Over the 64 L's: before the fix 1.2.0 doubled a common in 25 and 1.3.0
    in none; now 1.2.0 doubles none, and where it dropped a twin it dropped
    exactly the twin's section and body, every other member unchanged."""
    fixed_cases = 0
    for spacing, rows in l_cases():
        with before_the_fix():
            old = roof("1.2.0", spacing, rows)
        new = roof("1.2.0", spacing, rows)
        assert _doubled(roof("1.3.0", spacing, rows)) == 0
        assert _doubled(new) == 0
        if _doubled(old) == 0:
            assert new == old
            continue
        fixed_cases += 1
        assert _doubled(old) == 1
        kept = {m.id for m in new}
        gone = [m for m in old if m.id not in kept]
        assert sorted(m.role for m in gone) == ["common", "section"]
        # Every other member as it was: same id, role, index and feature.
        assert new == [m for m in old if m.id in kept]
        assert Counter(m.role for m in new) == Counter(
            m.role for m in roof("1.3.0", spacing, rows)
        )
    assert fixed_cases == 25


def test_the_twin_is_lost_never_rebound() -> None:
    """The golden's twin, ``common/17``, is gone from the expansion, and no
    member took its id: a Boolean that named it now names nothing."""
    with before_the_fix():
        old = roof("1.2.0", GOLDEN_SPACING, GOLDEN_WALLS)
    new = roof("1.2.0", GOLDEN_SPACING, GOLDEN_WALLS)
    twin = member_id(ROOF_ID, "common", 17)
    survivor = member_id(ROOF_ID, "common", 16)
    assert twin in {m.id for m in old}
    assert twin not in {m.id for m in new}
    assert survivor in {m.id for m in new}
    commons = sorted(m.index for m in new if m.role == "common")
    assert commons == [*range(17), 18]


def _request(
    members: list[ExpandedMember],
) -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    titles = {r.role: r.title for r in ROOF_V1_2.manifest.members}
    request = EvaluateTreeRequest(
        part_id=PART,
        tree_version=1,
        features=[EvaluatedFeatureInput(id=m.id, feature=m.feature) for m in members],
        materials=with_member_materials(
            None,
            {m.id: m.metadata.material for m in members if m.metadata is not None},
        ),
        linear_deflection=0.1,
    )
    metadata = [
        CutListMember(
            feature_id=m.id, role=m.role, title=titles[m.role], metadata=m.metadata
        )
        for m in members
        if m.metadata is not None
    ]
    return request, metadata


def golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    return _request(roof("1.2.0", GOLDEN_SPACING, GOLDEN_WALLS))


def fixture() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    with before_the_fix():
        return _request(roof("1.2.0", GOLDEN_SPACING, GOLDEN_WALLS))


def _members_json(items: list[CutListMember]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in items], indent=2) + "\n"


def _fixture_json() -> bytes:
    request, metadata = fixture()
    return json.dumps(
        {
            "request": request.model_dump(mode="json"),
            "members": [m.model_dump(mode="json") for m in metadata],
        },
        sort_keys=True,
    ).encode()


def test_the_golden_is_the_plugins_expansion() -> None:
    request, metadata = golden()
    committed = EvaluateTreeRequest.model_validate_json(
        (GOLDEN / "model.json").read_text()
    )
    assert committed.model_dump(mode="json") == request.model_dump(mode="json")
    assert (GOLDEN / "members.json").read_text() == _members_json(metadata)


def test_the_fixture_is_1_2_before_the_fix() -> None:
    assert json.loads(gzip.decompress(FIXTURE.read_bytes())) == json.loads(
        _fixture_json()
    )


@pytest.mark.parametrize("version", ["1.2.0", "1.3.0"])
def test_b4_is_untouched(version: str) -> None:
    """B4 and its 48 in wing never met the twin: the fix changes nothing."""
    b4 = l_walls(240.0, 240.0, 120.0, 120.0)
    wing = l_walls(240.0, 240.0, 192.0, 120.0)
    for rows in (b4, wing):
        with before_the_fix():
            old = roof(version, 24.0, rows)
        assert roof(version, 24.0, rows) == old


if __name__ == "__main__":
    request, metadata = golden()
    GOLDEN.mkdir(parents=True, exist_ok=True)
    (GOLDEN / "model.json").write_text(request.model_dump_json(indent=2) + "\n")
    (GOLDEN / "members.json").write_text(_members_json(metadata))
    FIXTURE.write_bytes(gzip.compress(_fixture_json(), mtime=0))
    sys.stdout.write(f"{GOLDEN.name}: {len(request.features)} features\n")
