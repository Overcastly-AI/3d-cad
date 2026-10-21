"""FLOOR-FRAME acceptance: B5's framed floor from one ``loft.floor`` feature,
its 12 in o.c. edit, and B2's walls standing on it, on STEP.

``goldens/b5-floor-2x8-16oc`` and ``-12oc`` are the floor's expansion and
``b5-shed-walls-on-floor`` adds B2's four walls at base elevation 8.75 (the
joists' top); each is pinned to the plugins by
``packages/loft-plugins/tests/test_floor.py``. buildings.md asks three
things, each checked here against numbers typed from the spec by hand:

1. counts and cut lengths: the cut list measured from the bodies is the
   spec's floor list (Joist 2x8 10 @ 117, Rim 2x8 2 @ 144, Sill PT 2x6 2 @
   144 and 2 @ 109; 13 joists at 12 in o.c.);
2. the exported STEP's solids are, box for box, an independent build123d
   script of the spec's members, summing to 20 030.25 in^3 (23 847.375 at
   12 in o.c.) to 1e-4;
3. interference none, on the goldens and on a kernel sweep of turned, odd
   and touching floors (``fixtures/floor-sweep.json.gz``, pinned to the
   plugin): one solid per member and no two sharing any volume.
"""

import gzip
import itertools
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from build123d import (
    Box,
    Pos,
    Solid,
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from fastapi.testclient import TestClient
from geometry.harness import build_model_solid
from geometry.kernel import measure_shape
from geometry.kernel.interference import probe_overlap
from geometry.main import app
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMember,
    cut_list_response,
    part_pieces,
)
from loft_wire.features import EvaluateTreeRequest, ExportTreeRequest

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
SWEEP = Path(__file__).resolve().parent / "fixtures" / "floor-sweep.json.gz"
IN = 25.4
SPF, PT = "spf_lumber", "southern_pine_pt"

Row = tuple[str, str, str, int, float, int]

#: buildings.md B5's floor cut list: member, profile, material, qty, length
#: (in), stock (ft), in tree order.
FLOOR_16: list[Row] = [
    ("Joist", "2x8", SPF, 10, 117.0, 10),
    ("Rim", "2x8", SPF, 2, 144.0, 12),
    ("Sill", "2x6", PT, 2, 144.0, 12),
    ("Sill", "2x6", PT, 2, 109.0, 10),
]
TABLES: dict[str, list[Row]] = {
    "b5-floor-2x8-16oc": FLOOR_16,
    # "joist spacing 16 -> 12. That gives 13 joists".
    "b5-floor-2x8-12oc": [("Joist", "2x8", SPF, 13, 117.0, 10), *FLOOR_16[1:]],
    # The floor, then B2's wall list without openings (test_walls_b2).
    "b5-shed-walls-on-floor": [
        *FLOOR_16,
        ("Stud", "2x4", SPF, 36, 92.625, 8),
        ("Top plate", "2x4", SPF, 4, 144.0, 12),
        ("Bottom plate", "2x4", PT, 2, 144.0, 12),
        ("Top plate", "2x4", SPF, 4, 113.0, 10),
        ("Bottom plate", "2x4", PT, 2, 113.0, 10),
    ],
}
#: The spec's volumes (in^3): the floor's, and B2's walls' 25 601.625 on it.
VOLUMES = {
    "b5-floor-2x8-16oc": 20030.25,
    "b5-floor-2x8-12oc": 23847.375,
    "b5-shed-walls-on-floor": 20030.25 + 25601.625,
}
#: Pressure-treated volume (in^3): the sills (and B2's bottom plates).
PT_VOLUME = {
    "b5-floor-2x8-16oc": 4174.5,
    "b5-floor-2x8-12oc": 4174.5,
    "b5-shed-walls-on-floor": 4174.5 + (2 * 144 + 2 * 113) * 5.25,
}

each_golden = pytest.mark.parametrize("name", sorted(TABLES))

Bounds = tuple[float, float, float, float, float, float]  # x0, x1, y0, y1, z0, z1 (in)


def _request(name: str) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )


def _members(name: str) -> list[CutListMember]:
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / name / "members.json").read_text()
    )
    return [CutListMember.model_validate(item) for item in raw]


def _extents(request: EvaluateTreeRequest) -> BodyExtentsResult:
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    return BodyExtentsResult.model_validate_json(response.content)


def _step_solids(name: str, tmp_path: Path) -> list[Solid]:
    request = ExportTreeRequest.model_validate(
        {**_request(name).model_dump(mode="json"), "format": "step"}
    )
    response = client.post("/api/v1/export/tree", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    path = tmp_path / f"{name}.step"
    path.write_bytes(response.content)
    return list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


# --- The spec's members, typed by hand ----------------------------------------------


def spec_floor(spacing: float) -> list[Bounds]:
    """buildings.md B5's floor: sills Z 0..1.5 (front and back 144, sides 109
    between them), rims Y 0..1.5 and 118.5..120, joists Y 1.5..118.5 at
    0.75, then every *spacing*, and 143.25; all framing Z 1.5..8.75."""
    centres = [0.75, *(spacing * n for n in range(1, 13) if spacing * n <= 141.75)]
    centres.append(143.25)
    return [
        (0, 144, 0, 5.5, 0, 1.5),
        (0, 144, 114.5, 120, 0, 1.5),
        (0, 5.5, 5.5, 114.5, 0, 1.5),
        (138.5, 144, 5.5, 114.5, 0, 1.5),
        (0, 144, 0, 1.5, 1.5, 8.75),
        (0, 144, 118.5, 120, 1.5, 8.75),
        *((c - 0.75, c + 0.75, 1.5, 118.5, 1.5, 8.75) for c in centres),
    ]


def spec_walls(base: float) -> list[Bounds]:
    """B2's four walls without openings (test_walls_b2's typing) on *base*."""
    long = [0.75, *(16.0 * n for n in range(1, 9)), 143.25]
    left = [3.5 + u for u in (0.75, *(16.0 * n for n in range(1, 7)), 112.25)]
    right = [116.5 - u for u in (0.75, *(16.0 * n for n in range(1, 7)), 112.25)]
    studs, plates = (1.5, 94.125), [(0.0, 1.5), (94.125, 95.625), (95.625, 97.125)]
    out: list[Bounds] = []
    for y0, y1 in ((0.0, 3.5), (116.5, 120.0)):
        out += [(x - 0.75, x + 0.75, y0, y1, *studs) for x in long]
        out += [(0, 144, y0, y1, *z) for z in plates]
    for (x0, x1), along in (((0.0, 3.5), left), ((140.5, 144.0), right)):
        out += [(x0, x1, y - 0.75, y + 0.75, *studs) for y in along]
        out += [(x0, x1, 3.5, 116.5, *z) for z in plates]
    return [(*b[:4], b[4] + base, b[5] + base) for b in out]


SPEC: dict[str, list[Bounds]] = {
    "b5-floor-2x8-16oc": spec_floor(16),
    "b5-floor-2x8-12oc": spec_floor(12),
    "b5-shed-walls-on-floor": spec_floor(16) + spec_walls(8.75),
}


def _script(boxes: Sequence[Bounds]) -> list[Solid]:
    """The independent script: each member a build123d Box, no Loft code."""
    return [
        (
            Pos((x0 + x1) / 2 * IN, (y0 + y1) / 2 * IN, (z0 + z1) / 2 * IN)
            * Box((x1 - x0) * IN, (y1 - y0) * IN, (z1 - z0) * IN)
        ).solid()
        for x0, x1, y0, y1, z0, z1 in boxes
    ]


def _signature(solid: Solid) -> tuple[float, ...]:
    """Volume (in^3, to 1e-6) and the box (in, to 1e-6) of a solid."""
    box = solid.bounding_box()
    values = (box.min.X, box.max.X, box.min.Y, box.max.Y, box.min.Z, box.max.Z)
    volume = float(measure_shape(solid).volume) / IN**3
    return (round(volume, 6), *(round(v / IN, 6) + 0.0 for v in values))


# --- 1. The cut list ----------------------------------------------------------------


@each_golden
def test_the_cut_list_is_the_specs(name: str) -> None:
    request = _request(name)
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B5",
        length_unit="in",
        pieces=part_pieces(_extents(request), _members(name), request.materials),
    )
    rows = [
        (
            line.member,
            line.profile,
            line.material,
            line.quantity,
            round(line.length_mm / IN, 6),
            line.stock_length_ft,
        )
        for line in cut_list.lines
    ]
    assert rows == TABLES[name]
    assert cut_list.unclassified == 0


# --- 2. The STEP against the spec and an independent script -------------------------


def test_the_spec_volumes_are_buildings_mds() -> None:
    """The hand-typed members sum to the spec's figures, part by part."""
    for name, boxes in SPEC.items():
        volume = sum((b[1] - b[0]) * (b[3] - b[2]) * (b[5] - b[4]) for b in boxes)
        assert volume == pytest.approx(VOLUMES[name], abs=1e-9), name
    floor = SPEC["b5-floor-2x8-16oc"]
    assert sum(1 for b in floor if b[4] == 1.5 and b[3] - b[2] == 117) == 10


@each_golden
def test_the_step_is_the_independent_scripts(name: str, tmp_path: Path) -> None:
    solids = _step_solids(name, tmp_path)
    script = _script(SPEC[name])
    assert len(solids) == len(script) == sum(row[3] for row in TABLES[name])
    assert Counter(_signature(s) for s in solids) == Counter(
        _signature(s) for s in script
    )
    ours = sum(float(measure_shape(s).volume) for s in solids) / IN**3
    theirs = sum(float(measure_shape(s).volume) for s in script) / IN**3
    assert ours == pytest.approx(VOLUMES[name], abs=1e-4)
    assert ours == pytest.approx(theirs, abs=1e-4)


# --- 3. Interference none -----------------------------------------------------------


def _overlapping(solids: Sequence[Solid]) -> tuple[int, list[tuple[int, int, float]]]:
    """Pairs whose bounding boxes overlap on all three axes by ANY amount
    (no slack, so a 1e-9 in float overlap is probed too): how many were
    probed exactly, and those sharing any volume."""
    boxes = [s.bounding_box() for s in solids]
    probed = 0
    bad: list[tuple[int, int, float]] = []
    for i, j in itertools.combinations(range(len(solids)), 2):
        a, b = boxes[i], boxes[j]
        if all(
            min(getattr(a.max, k), getattr(b.max, k))
            > max(getattr(a.min, k), getattr(b.min, k))
            for k in ("X", "Y", "Z")
        ):
            probed += 1
            probe = probe_overlap(solids[i], solids[j])
            if probe.unresolved or probe.volume_mm3 != 0.0:
                bad.append((i, j, probe.volume_mm3))
    return probed, bad


@each_golden
def test_nothing_interferes(name: str, tmp_path: Path) -> None:
    _, bad = _overlapping(_step_solids(name, tmp_path))
    assert bad == []


def _sweep() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(gzip.decompress(SWEEP.read_bytes()))
    return cases


@pytest.mark.parametrize("case", _sweep(), ids=[c["name"] for c in _sweep()])
def test_the_overlap_sweep_builds_every_member_touching_only(
    case: dict[str, Any],
) -> None:
    """Turned floors, joists along the width, odd sizes and spacings, a layout
    joist touching the end joist, no sill: one valid solid per member, no two
    sharing any volume. The turned floors' members all have overlapping
    boxes with their neighbours, so those pairs are probed exactly."""
    request = EvaluateTreeRequest.model_validate(case["request"])
    shape = build_model_solid(request)
    solids: list[Solid] = list(shape.solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    assert len(solids) == case["bodies"]
    assert all(s.is_valid for s in solids)
    probed, bad = _overlapping(solids)
    assert bad == [], bad
    if "turned" in case["name"]:
        assert probed >= case["bodies"]


# --- Mass ---------------------------------------------------------------------------


@each_golden
def test_every_body_weighs_by_its_member_material(name: str) -> None:
    """PT sills (and B2's bottom plates), SPF joists, rims, studs and top
    plates, with no part default."""
    request = _request(name)
    assert request.materials is not None
    assert request.materials.default_material is None
    response = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    pt = PT_VOLUME[name]
    want = (pt * 582.0 + (VOLUMES[name] - pt) * 450.0) * 1e-6 * IN**3
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)
