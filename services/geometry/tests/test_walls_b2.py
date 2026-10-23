"""STUD-WALL and WINDOW-DOOR acceptance: B2's walls from four ``loft.wall``
features, with the door and window they host, on STEP.

``goldens/b2-walls-no-openings-16oc`` and ``-24oc`` are four walls'
expansions at 16 and 24 in o.c. (``model.json``, with the member materials
documents applies) and each member's metadata (``members.json``), pinned to
the plugin by ``packages/loft-plugins/tests/test_wall.py``. buildings.md asks
three things, each checked here against numbers typed from the spec by hand:

1. counts and cut lengths: the cut list, measured from the bodies, equals the
   spec's wall list without openings (and the 24 in o.c. edit's);
2. the exported STEP holds that many solids summing to 25 601.625 in^3
   (20 738.8125 at 24 in o.c.) to 1e-4, each a member of the list's sizes;
3. interference none: no two solids of the STEP overlap.

And ``plugin-wall-v1-144-30deg``, one wall turned 30 degrees, matches an
independent build123d script body for body, and its cut list reads the turned
members at their true lengths.

WINDOW-DOOR: ``b2-walls-door-window`` is B2 with its hosted door and window
(the spec's wall cut list, 28 942.125 in^3), and ``b2-walls-door-moved-24``,
``-window-30`` and ``-door-deleted`` are the spec's three edits. Each one's
STEP solids are, box for box, the members typed below from buildings.md's
coordinates (:func:`spec_boxes`), and no solid enters a rough opening.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from build123d import (
    Box,
    Compound,
    Location,
    Pos,
    Rot,
    Solid,
    export_step,  # pyright: ignore[reportUnknownVariableType]
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from fastapi.testclient import TestClient
from geometry.kernel import measure_shape
from geometry.kernel.extents import body_extents
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
IN = 25.4
SPF, PT = "spf_lumber", "southern_pine_pt"

#: B2 with its door and window: buildings.md's wall cut list in the list's
#: order (CUT-LIST-PANEL): by member as it first appears in the tree (front
#: wall first; kings are studs as the spec lists them), then length.
DOOR_WINDOW: list[tuple[str, str, str, int, float, int]] = [
    ("Stud", "2x4", SPF, 36, 92.625, 8),
    ("Jack", "2x4", SPF, 4, 81.0, 8),
    ("Header", "2x6", SPF, 2, 27.5, 8),
    ("Header", "2x6", SPF, 2, 41.0, 8),
    ("Cripple", "2x4", SPF, 4, 6.125, 8),
    ("Cripple", "2x4", SPF, 2, 43.0, 8),
    ("Top plate", "2x4", SPF, 4, 113.0, 10),
    ("Top plate", "2x4", SPF, 4, 144.0, 12),
    ("Bottom plate", "2x4", PT, 2, 53.0, 8),
    ("Bottom plate", "2x4", PT, 2, 113.0, 10),
    ("Bottom plate", "2x4", PT, 1, 144.0, 12),
    ("Sill", "2x4", SPF, 1, 24.5, 8),
]

#: buildings.md B2's wall cut list with no openings: member, profile,
#: material, qty, length (in), stock (ft), by member as it first appears in
#: the tree (front wall first), then length.
TABLES: dict[str, list[tuple[str, str, str, int, float, int]]] = {
    "b2-walls-no-openings-16oc": [
        ("Stud", "2x4", SPF, 36, 92.625, 8),
        ("Top plate", "2x4", SPF, 4, 113.0, 10),
        ("Top plate", "2x4", SPF, 4, 144.0, 12),
        ("Bottom plate", "2x4", PT, 2, 113.0, 10),
        ("Bottom plate", "2x4", PT, 2, 144.0, 12),
    ],
    # "spacing 16 -> 24 gives 26 studs".
    "b2-walls-no-openings-24oc": [
        ("Stud", "2x4", SPF, 26, 92.625, 8),
        ("Top plate", "2x4", SPF, 4, 113.0, 10),
        ("Top plate", "2x4", SPF, 4, 144.0, 12),
        ("Bottom plate", "2x4", PT, 2, 113.0, 10),
        ("Bottom plate", "2x4", PT, 2, 144.0, 12),
    ],
    # The default 144 wall turned 30 degrees: the same list as one B2 front
    # wall, read from turned bodies.
    "plugin-wall-v1-144-30deg": [
        ("Stud", "2x4", SPF, 10, 92.625, 8),
        ("Top plate", "2x4", SPF, 2, 144.0, 12),
        ("Bottom plate", "2x4", PT, 1, 144.0, 12),
    ],
    "b2-walls-door-window": DOOR_WINDOW,
    # "Door moved 24 in: 7 layout studs and 3 top cripples, still 2 kings
    # and 2 jacks": 35 studs, 5 top cripples in all; the plate cut moves.
    "b2-walls-door-moved-24": [
        ("Stud", "2x4", SPF, 35, 92.625, 8),
        ("Jack", "2x4", SPF, 4, 81.0, 8),
        ("Header", "2x6", SPF, 2, 27.5, 8),
        ("Header", "2x6", SPF, 2, 41.0, 8),
        ("Cripple", "2x4", SPF, 5, 6.125, 8),
        ("Cripple", "2x4", SPF, 2, 43.0, 8),
        ("Top plate", "2x4", SPF, 4, 113.0, 10),
        ("Top plate", "2x4", SPF, 4, 144.0, 12),
        ("Bottom plate", "2x4", PT, 1, 29.0, 8),
        ("Bottom plate", "2x4", PT, 1, 77.0, 8),
        ("Bottom plate", "2x4", PT, 2, 113.0, 10),
        ("Bottom plate", "2x4", PT, 1, 144.0, 12),
        ("Sill", "2x4", SPF, 1, 24.5, 8),
    ],
    # "Window 24 -> 30 in wide: header 33.5, sill 30.5, still 2 top and 2
    # bottom cripples."
    "b2-walls-window-30": [
        *DOOR_WINDOW[:2],
        ("Header", "2x6", SPF, 2, 33.5, 8),
        *DOOR_WINDOW[3:11],
        ("Sill", "2x4", SPF, 1, 30.5, 8),
    ],
    # "Door deleted: the front wall has 10 full studs and one 144 bottom plate."
    "b2-walls-door-deleted": [
        ("Stud", "2x4", SPF, 36, 92.625, 8),
        ("Top plate", "2x4", SPF, 4, 113.0, 10),
        ("Top plate", "2x4", SPF, 4, 144.0, 12),
        ("Bottom plate", "2x4", PT, 2, 113.0, 10),
        ("Bottom plate", "2x4", PT, 2, 144.0, 12),
        ("Jack", "2x4", SPF, 2, 81.0, 8),
        ("Header", "2x6", SPF, 2, 27.5, 8),
        ("Cripple", "2x4", SPF, 2, 6.125, 8),
        ("Cripple", "2x4", SPF, 2, 43.0, 8),
        ("Sill", "2x4", SPF, 1, 24.5, 8),
    ],
}
#: The spec's volumes (in^3); the 30 degree wall is 10 studs and 3 plates.
VOLUMES = {
    "b2-walls-no-openings-16oc": 25601.625,
    "b2-walls-no-openings-24oc": 20738.8125,
    "plugin-wall-v1-144-30deg": 7130.8125,
    # Summed from the spec's wall cut list: studs 36 x 92.625, jacks 4 x 81,
    # cripples 4 x 6.125 + 2 x 43, sill 24.5 and plates 4 x 144 + 4 x 113
    # + 144 + 2 x 113 + 2 x 53, all at 5.25 in^2; headers 2 x 41 + 2 x 27.5
    # at 8.25 in^2 (1.5 x 5.5; the 1/2 in spacer is not a member).
    "b2-walls-door-window": 28942.125,
    # Door moved: 35 studs, 5 top cripples, plates 77 + 29 for 53 + 53.
    "b2-walls-door-moved-24": 28942.125 - 92.625 * 5.25 + 6.125 * 5.25,
    # Window 30: header 2 x 6 in longer (8.25), sill 6 in longer (5.25).
    "b2-walls-window-30": 28942.125 + 12 * 8.25 + 6 * 5.25,
    # Door deleted: 2 layout studs back, the kings, jacks, header, 2 top
    # cripples gone; one 144 plate for 2 x 53.
    "b2-walls-door-deleted": 28942.125
    - (2 * 81 + 2 * 6.125 + 2 * 53 - 144) * 5.25
    - 2 * 41 * 8.25,
}
B2 = [
    "b2-walls-no-openings-16oc",
    "b2-walls-no-openings-24oc",
    "b2-walls-door-window",
    "b2-walls-door-moved-24",
    "b2-walls-window-30",
    "b2-walls-door-deleted",
]
#: Pressure-treated bottom plate length (in) per golden: the rest is SPF.
PT_LENGTH = {
    "b2-walls-no-openings-16oc": 2 * 144 + 2 * 113,
    "b2-walls-no-openings-24oc": 2 * 144 + 2 * 113,
    "b2-walls-door-window": 144 + 2 * 113 + 2 * 53,
    "b2-walls-door-moved-24": 144 + 2 * 113 + 77 + 29,
    "b2-walls-window-30": 144 + 2 * 113 + 2 * 53,
    "b2-walls-door-deleted": 2 * 144 + 2 * 113,
}
#: Each profile's section (in), smaller first.
SECTIONS = {"2x4": (1.5, 3.5), "2x6": (1.5, 5.5)}

each_golden = pytest.mark.parametrize("name", sorted(TABLES))


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


@each_golden
def test_the_cut_list_is_the_specs(name: str) -> None:
    request = _request(name)
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B2 walls",
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


@each_golden
def test_the_step_is_the_specs_and_nothing_interferes(
    name: str, tmp_path: Path
) -> None:
    solids = _step_solids(name, tmp_path)
    table = TABLES[name]
    assert len(solids) == sum(row[3] for row in table)
    volume_in3 = sum(float(measure_shape(s).volume) for s in solids) / IN**3
    assert volume_in3 == pytest.approx(VOLUMES[name], abs=1e-4)
    # Every solid is a member of the list: its length and its 1.5 x 3.5.
    want: Counter[tuple[float, ...]] = Counter()
    for row in table:
        want[(row[4], *SECTIONS[row[1]])] += row[3]
    got = Counter(
        tuple(round(v / IN, 6) for v in body_extents(s)[:1])
        + tuple(sorted(round(v / IN, 6) for v in body_extents(s)[1:]))
        for s in solids
    )
    assert got == want
    # Interference none: probe every pair whose bounding boxes overlap in
    # volume (disjoint or merely touching boxes cannot interpenetrate).
    boxes = [s.bounding_box() for s in solids]
    for i in range(len(solids)):
        for j in range(i + 1, len(solids)):
            a, b = boxes[i], boxes[j]
            if all(
                min(getattr(a.max, k), getattr(b.max, k))
                - max(getattr(a.min, k), getattr(b.min, k))
                > 1e-6
                for k in ("X", "Y", "Z")
            ):
                probe = probe_overlap(solids[i], solids[j])
                assert not probe.unresolved and probe.volume_mm3 == 0.0, (i, j)


@pytest.mark.parametrize("name", B2)
def test_every_body_weighs_by_its_member_material(name: str) -> None:
    """PT bottom plates, SPF studs and top plates, with no part default."""
    request = _request(name)
    assert request.materials is not None
    assert request.materials.default_material is None
    response = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    bottom_in3 = PT_LENGTH[name] * 1.5 * 3.5
    want = (bottom_in3 * 582.0 + (VOLUMES[name] - bottom_in3) * 450.0) * 1e-6 * IN**3
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


# --- The 30 degree wall against an independent script ------------------------------


def _script_wall() -> list[Solid]:
    """The 30 degree wall typed from buildings.md B2's rules, in build123d with
    no Loft code: boxes in the wall's frame (u along, v to the right, z up),
    turned 30 degrees about Z at the start (10, 20)."""
    t = 1.5
    layout = [0.75, *(16.0 * n for n in range(1, 9)), 143.25]
    local = [(c - t / 2, c + t / 2, 1.5, 94.125) for c in layout]
    local += [(0.0, 144.0, z, z + 1.5) for z in (94.125, 95.625, 0.0)]
    solids: list[Solid] = []
    for u0, u1, z0, z1 in local:
        box = Box((u1 - u0) * IN, 3.5 * IN, (z1 - z0) * IN)
        placed = (
            Location((10 * IN, 20 * IN, 0))
            * Rot(0, 0, 30)
            * Pos((u0 + u1) / 2 * IN, -1.75 * IN, (z0 + z1) / 2 * IN)
            * box
        )
        solids.append(placed.solid())
    return solids


def _signature(solid: Solid) -> tuple[float, ...]:
    """Volume, centroid and box of a solid, to 1e-6 mm."""
    props = measure_shape(solid)
    box = solid.bounding_box()
    values = [
        float(props.volume),
        props.centroid.x,
        props.centroid.y,
        props.centroid.z,
        box.min.X,
        box.min.Y,
        box.min.Z,
        box.max.X,
        box.max.Y,
        box.max.Z,
    ]
    return tuple(round(v, 6) for v in values)


def _by_position(signature: tuple[float, ...]) -> tuple[float, ...]:
    """Order solids by centroid (their volumes differ by the STEP drift)."""
    return signature[1:4]


def test_the_30_degree_wall_matches_a_script(tmp_path: Path) -> None:
    ours = sorted(
        (_signature(s) for s in _step_solids("plugin-wall-v1-144-30deg", tmp_path)),
        key=_by_position,
    )
    script = sorted((_signature(s) for s in _script_wall()), key=_by_position)
    assert len(ours) == len(script) == 13
    for got, want in zip(ours, script, strict=True):
        # Volume and area move by OCCT's STEP drift on turned planes (the
        # golden's round-trip rationale); positions stay at 1e-6 mm.
        assert got[0] == pytest.approx(want[0], abs=1e-3)
        assert got[1:] == pytest.approx(want[1:], abs=1e-6)


def test_the_turned_step_drift_is_occts(tmp_path: Path) -> None:
    """The 30 degree wall's STEP volume drift (expected.json) is OCCT's: the
    script's own boxes drift the same way through build123d's STEP, and the
    unturned wall does not."""

    def drift(degrees: float) -> float:
        solids = [Rot(0, 0, degrees - 30) * s for s in _script_wall()]
        before = sum(float(measure_shape(s).volume) for s in solids)
        path = tmp_path / f"twin-{degrees:g}.step"
        export_step(Compound(solids), str(path))
        back = list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportUnknownVariableType]
        return sum(float(measure_shape(s).volume) for s in back) - before  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]

    turned = abs(drift(30.0))
    assert 1e-4 < turned < 2e-3
    assert abs(drift(0.0)) < 1e-5  # 50x below the turned drift


# --- WINDOW-DOOR: every member typed from buildings.md ------------------------------

Bounds = tuple[float, float, float, float, float, float]  # x0, x1, y0, y1, z0, z1 (in)

#: Layout stud centres along X on the front and back walls (both read the
#: same: 144 is a multiple of 16, so the layout from X 144 mirrors onto it).
LONG = [0.75, 16, 32, 48, 64, 80, 96, 112, 128, 143.25]
#: Left side wall, from Y 3.5 upward: 3.5 + (0.75, 16, ..., 96, 112.25).
LEFT = [4.25, 19.5, 35.5, 51.5, 67.5, 83.5, 99.5, 115.75]
#: Right side wall, from Y 116.5 downward: 116.5 - (0.75, 16, ..., 112.25).
RIGHT = [115.75, 100.5, 84.5, 68.5, 52.5, 36.5, 20.5, 4.25]

STUD_Z = (1.5, 94.125)
PLATES_Z = [(0.0, 1.5), (94.125, 95.625), (95.625, 97.125)]


def _x_wall(y0: float, y1: float, studs: list[float]) -> list[Bounds]:
    """A wall along X (front Y 0..3.5, back 116.5..120): studs and plates."""
    out: list[Bounds] = [(x - 0.75, x + 0.75, y0, y1, *STUD_Z) for x in studs]
    return out + [(0, 144, y0, y1, *z) for z in PLATES_Z[1:]]


def _y_wall(x0: float, x1: float, studs: list[float]) -> list[Bounds]:
    """A side wall along Y (3.5..116.5): studs and top plates."""
    out: list[Bounds] = [(x0, x1, y - 0.75, y + 0.75, *STUD_Z) for y in studs]
    return out + [(x0, x1, 3.5, 116.5, *z) for z in PLATES_Z[1:]]


def _front_door(cx: float, cripples: list[float]) -> list[Bounds]:
    """The front wall's door (buildings.md: rough opening 38 x 82.5 centred on
    X *cx*): kings and jacks either side, two 2x6 plies at Y 0..1.5 and
    2..3.5 over the jacks, top cripples at *cripples*, the bottom plate cut
    out of the opening; layout studs only clear of the kings."""
    a, b, c, d, e, f = cx - 22, cx - 20.5, cx - 19, cx + 19, cx + 20.5, cx + 22
    studs = [x for x in LONG if x + 0.75 <= a or x - 0.75 >= f]
    out = _x_wall(0, 3.5, studs)
    out += [(a, b, 0, 3.5, *STUD_Z), (e, f, 0, 3.5, *STUD_Z)]  # kings
    out += [(b, c, 0, 3.5, 1.5, 82.5), (d, e, 0, 3.5, 1.5, 82.5)]  # jacks
    out += [(b, e, 0, 1.5, 82.5, 88), (b, e, 2, 3.5, 82.5, 88)]  # header
    out += [(x - 0.75, x + 0.75, 0, 3.5, 88, 94.125) for x in cripples]
    return [*out, (0, c, 0, 3.5, 0, 1.5), (d, 144, 0, 3.5, 0, 1.5)]


def _right_window(width: float) -> list[Bounds]:
    """The right side wall's window: rough opening *width* x 36.5 centred on
    Y 60, sill at Z 46, head 82.5; cripples at the replaced layout studs
    (Y 52.5 and 68.5: wall-local 64 and 48)."""
    lo, hi = 60 - width / 2, 60 + width / 2
    out = _y_wall(140.5, 144, [y for y in RIGHT if y not in (52.5, 68.5)])
    out += [
        (140.5, 144, lo - 3, lo - 1.5, *STUD_Z),  # kings
        (140.5, 144, hi + 1.5, hi + 3, *STUD_Z),
        (140.5, 144, lo - 1.5, lo, 1.5, 82.5),  # jacks
        (140.5, 144, hi, hi + 1.5, 1.5, 82.5),
        (142.5, 144, lo - 1.5, hi + 1.5, 82.5, 88),  # header, exterior ply
        (140.5, 142, lo - 1.5, hi + 1.5, 82.5, 88),
        (140.5, 144, lo, hi, 44.5, 46),  # flat sill
    ]
    for y in (52.5, 68.5):
        out += [
            (140.5, 144, y - 0.75, y + 0.75, 88, 94.125),
            (140.5, 144, y - 0.75, y + 0.75, 1.5, 44.5),
        ]
    return [*out, (140.5, 144, 3.5, 116.5, 0, 1.5)]


def spec_boxes(name: str) -> list[Bounds]:
    """Every member of golden *name*, typed from buildings.md B2 and its edits."""
    front = {
        "b2-walls-door-window": _front_door(72, [64, 80]),
        "b2-walls-door-moved-24": _front_door(96, [80, 96, 112]),
        "b2-walls-window-30": _front_door(72, [64, 80]),
        "b2-walls-door-deleted": [*_x_wall(0, 3.5, LONG), (0, 144, 0, 3.5, 0, 1.5)],
    }[name]
    left = [*_y_wall(0, 3.5, LEFT), (0, 3.5, 3.5, 116.5, 0, 1.5)]
    back = [*_x_wall(116.5, 120, LONG), (0, 144, 116.5, 120, 0, 1.5)]
    right = _right_window(30.5 if name == "b2-walls-window-30" else 24.5)
    return front + left + back + right


#: Each golden's rough openings (in): nothing may enter them.
OPENINGS: dict[str, list[Bounds]] = {
    "b2-walls-door-window": [
        (53, 91, 0, 3.5, 0, 82.5),
        (140.5, 144, 47.75, 72.25, 46, 82.5),
    ],
    "b2-walls-door-moved-24": [
        (77, 115, 0, 3.5, 0, 82.5),
        (140.5, 144, 47.75, 72.25, 46, 82.5),
    ],
    "b2-walls-window-30": [
        (53, 91, 0, 3.5, 0, 82.5),
        (140.5, 144, 44.75, 75.25, 46, 82.5),
    ],
    "b2-walls-door-deleted": [(140.5, 144, 47.75, 72.25, 46, 82.5)],
}


def _box_in(solid: Solid) -> Bounds:
    box = solid.bounding_box()
    values = (box.min.X, box.max.X, box.min.Y, box.max.Y, box.min.Z, box.max.Z)
    return tuple(round(v / IN, 6) + 0.0 for v in values)  # type: ignore[return-value]


@pytest.mark.parametrize("name", sorted(OPENINGS))
def test_every_solid_is_a_spec_member_and_none_enters_an_opening(
    name: str, tmp_path: Path
) -> None:
    """The STEP's solids are buildings.md's members box for box, the volumes
    sum to the spec's (VOLUMES, from its cut list), and no solid crosses a
    rough opening: the door's runs to the slab, the bottom plate cut out."""
    solids = _step_solids(name, tmp_path)
    got = Counter(_box_in(s) for s in solids)
    want = Counter(tuple(float(v) + 0.0 for v in b) for b in spec_boxes(name))
    assert got == want
    spec_volume = sum(
        (b[1] - b[0]) * (b[3] - b[2]) * (b[5] - b[4]) for b in spec_boxes(name)
    )
    assert spec_volume == pytest.approx(VOLUMES[name], abs=1e-9)
    for box in got:
        for hole in OPENINGS[name]:
            inside = all(
                min(box[k + 1], hole[k + 1]) - max(box[k], hole[k]) > 1e-9
                for k in (0, 2, 4)
            )
            assert not inside, (box, hole)
