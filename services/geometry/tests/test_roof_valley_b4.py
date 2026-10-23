"""ROOF-VALLEY acceptance: B4's L-shaped hip roof from one ``loft.roof`` 1.2.0
feature, its footprint picked from B4's six walls, and the 48 in wing edit.

``goldens/b4-l-hip-valley`` and ``b4-wing-48`` are the plugin's expansion
(``model.json``, member materials applied as documents sends them) and each
member's metadata (``members.json``), pinned to the plugin by
``packages/loft-plugins/tests/test_roof_valley.py``, as are the fixtures
``roof-valley-sweep.json.gz`` and ``b4-walls.json.gz``. Geometry never learns
plugins exist, so this module reads JSON only. Checked against
``docs/reference-parts/buildings.md`` B4 and an INDEPENDENT build123d script
(:func:`script_roof`), which models every member another way: its plan
outline as a vertical prism, cut to the slab between its bottom and top
planes, less everything below the plate inside the walls' outer faces, and
(ROOF-HIP-TAIL) a hip's or valley's tail less everything below its rip plane
outside the walls:

1. the cut list, measured from the bodies, is buildings.md B4's;
2. line lengths on the exported STEP's faces: commons 79.660 (the cut ones
   78.474), jacks 52.480 and 25.647, valley jacks 51.641 and 24.808, hips
   and the valley 106.875 on the centreline, the wing's cripple 24.461;
3. every solid is the script's to 1e-4, and the script without the rips is
   the product manager's hand total, 30 054.875 in^3;
4. none interferes with another or with the walls; the walls themselves are
   the wall rules (studs on 16 from each wall's start, plates) and a script;
5. the overlap sweep: other L's (equal and unequal arms, the smallest arms,
   every orientation), pitches 1/12 .. 24/12, overhangs 0, 1/16, 24, 36,
   16, 19.2 and 24 o.c., 2x4 and 2x8 commons and a rectangle on walls build
   one solid per member, touching only (DECK's float class).
"""

import gzip
import itertools
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from build123d import (
    Box,
    Compound,
    Location,
    Plane,
    Polygon,
    Pos,
    Solid,
    Vector,
    export_step,  # pyright: ignore[reportUnknownVariableType]
    extrude,
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
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SWEEP = FIXTURES / "roof-valley-sweep.json.gz"
WALLS = FIXTURES / "b4-walls.json.gz"
IN = 25.4
R2 = math.sqrt(2)
NAMES = ("b4-l-hip-valley", "b4-wing-48")
#: Golden -> the wing's outer face X (buildings.md B4: 120; the edit: 192).
WING = {"b4-l-hip-valley": 120.0, "b4-wing-48": 192.0}
each_roof = pytest.mark.parametrize("name", NAMES)

# 6/12, 2x6 commons, 2x8 ridges, hips and valleys, 12 in overhang, plates at
# 97.125, 3.5 deep (buildings.md "Hip and valley conventions").
K = 0.5
PLATE = 97.125
OH = 12.0
SEAT = 3.5
PLUMB = 5.5 * math.hypot(12, 6) / 12  # 6.149
TOP0 = PLATE + PLUMB - SEAT * K  # the planes at the walls' outer faces
HS = 0.75 * R2  # a hip's or valley's half thickness, along a wall
DROP = 0.75 * K / R2  # 0.265
HIP_PLUMB = 7.25 * math.hypot(12 * R2, 6) / (12 * R2)  # 7.690
M = K / R2  # rise per plan inch along a hip or valley

#: buildings.md B4 (and its edit, from the independent script): members by
#: cut-list row, the roof's volume, and the volume without ROOF-HIP-TAIL.
TOTALS = {
    "b4-l-hip-valley": {"members": 52, "untrimmed": 30054.875},
    "b4-wing-48": {"members": 48},
}


# --- The independent script --------------------------------------------------------

PlaneSpec = tuple[tuple[float, float, float], float, float, float]


def _prism(points: Sequence[tuple[float, float]], z0: float, h: float) -> Solid:
    polygon = Polygon(*[(x * IN, y * IN) for x, y in points], align=None)
    return Pos(0, 0, z0 * IN) * extrude(polygon, h * IN, dir=(0, 0, 1)).solid()


def _slab(origin: tuple[float, float, float], gx: float, gy: float, h: float) -> Solid:
    """Between z = f and z = f - h (plumb), f the plane through *origin*
    rising gx per X and gy per Y."""
    normal = Vector(-gx, -gy, 1).normalized()
    top = Plane(origin=tuple(c * IN for c in origin), z_dir=normal)
    thick = h * normal.Z * IN
    return (top.location * Pos(0, 0, -thick / 2) * Box(2e5, 2e5, thick)).solid()


def footprint(wing: float) -> list[tuple[float, float]]:
    """The walls' outer faces round the L."""
    return [(0, 120), (wing, 120), (wing, 0), (240, 0), (240, 240), (0, 240)]


def script_roof(wing: float, rip: bool = True) -> list[Solid]:
    """B4's roof (wing 120) or its edit (wing 192, 48 wide) from buildings.md
    and RESEARCH §23's framing rules alone; every coordinate typed here."""
    inside = _prism(footprint(wing), -200, 400)
    below_plate = _prism(footprint(wing), -200, PLATE + 200)
    outside = _prism([(-100, -100), (400, -100), (400, 400), (-100, 400)], -200, 600)
    outside = outside - inside  # pyright: ignore[reportOperatorIssue]

    def member(
        plan: Sequence[tuple[float, float]],
        plane: PlaneSpec,
        rip_at: tuple[float, float, float] | None = None,
    ) -> Solid:
        origin, gx, gy, h = plane
        common = _prism(plan, -200, 600) & _slab(origin, gx, gy, h)
        assert common is not None
        body = common - below_plate
        if rip and rip_at is not None:
            below_rip = _slab(rip_at, gx, gy, 1000)
            body = body - (below_rip & outside)  # pyright: ignore[reportOperatorIssue]
        solids = list(body.solids())
        assert len(solids) == 1
        return solids[0]

    back: PlaneSpec = ((0, 240, TOP0), 0, -K, PLUMB)
    right: PlaneSpec = ((240, 0, TOP0), -K, 0, PLUMB)
    wing_front: PlaneSpec = ((0, 0, TOP0), 0, K, PLUMB)
    wing_left: PlaneSpec = ((wing, 0, TOP0), K, 0, PLUMB)
    main_front: PlaneSpec = ((0, 120, TOP0), 0, K, PLUMB)
    left: PlaneSpec = ((0, 0, TOP0), K, 0, PLUMB)

    def along_y(x: float, y0: float, y1: float) -> list[tuple[float, float]]:
        return [(x - 0.75, y0), (x + 0.75, y0), (x + 0.75, y1), (x - 0.75, y1)]

    def along_x(y: float, x0: float, x1: float) -> list[tuple[float, float]]:
        return [(x0, y - 0.75), (x0, y + 0.75), (x1, y + 0.75), (x1, y - 0.75)]

    def mirror(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(y, x) for x, y in points]

    w2 = 240 - wing  # the wing's width
    ridge_v = 240 - w2 / 2  # the wing ridge's X
    gap = wing - 120  # the valley line: Y = X - gap
    solids: list[Solid] = []
    # Commons: back X 60..180 and the left king on Y 180 (the main hipped
    # rectangle), main front X 60.. on the main ridge's layout, the right
    # wall's on the wing ridge's (Y w2/2 .. its far end), its king on Y 180.
    for x in range(60, 181, 24):
        solids.append(member(along_y(x, 252, 180.75), back))
    solids.append(member(along_x(180, -12, 59.25), left))
    # The valley's face on the main front: Y >= X - gap + HS.
    for x in range(60, 181, 24):
        if x + 0.75 - gap + HS <= 108:  # its tail clear of the valley
            solids.append(member(along_y(x, 108, 179.25), main_front))
        elif x + 0.75 - gap + HS <= 120:  # tail cut at the valley's face
            cut = [
                (x - 0.75, x - 0.75 - gap + HS),
                (x + 0.75, x + 0.75 - gap + HS),
                (x + 0.75, 179.25),
                (x - 0.75, 179.25),
            ]
            solids.append(member(cut, main_front))
    if wing == 120:
        # B4: the wing mirrors the main front about the valley.
        for y in (60, 84):
            solids.append(member(along_x(y, 108, 179.25), wing_left))
        cut = [
            (107.25, 107.25 + HS),
            (108.75, 108.75 + HS),
            (108.75, 179.25),
            (107.25, 179.25),
        ]
        solids.append(member(mirror(cut), wing_left))
        for y in range(60, 181, 24):
            solids.append(member(along_x(y, 252, 180.75), right))
        solids.append(member(along_y(180, -12, 59.25), wing_front))
    else:
        # The 48 wing: commons on Y 24..96 (120 would cut its seat at the
        # valley), the right wall's on Y 24..144 to the wing ridge's face
        # (216.75) and its king on Y 180; the wing front's king on X 216.
        for y in (24, 48, 72, 96):
            solids.append(member(along_x(y, 180, ridge_v - 0.75), wing_left))
        for y in range(24, 145, 24):
            solids.append(member(along_x(y, 252, ridge_v + 0.75), right))
        solids.append(member(along_x(180, 252, 180.75), right))
        solids.append(member(along_y(ridge_v, -12, w2 / 2 - 0.75), wing_front))

    # Hip jacks: 12 and 36 from each hip's corner along both its walls, cut at
    # the hip's side face (HS off its line along a wall).
    corners: list[tuple[tuple[float, float], tuple[int, int], PlaneSpec, PlaneSpec]] = [
        ((0, 120), (1, 1), main_front, left),
        ((0, 240), (1, -1), back, left),
        ((240, 240), (-1, -1), back, right),
    ]
    if wing == 120:
        corners += [
            ((240, 0), (-1, 1), wing_front, right),
            ((120, 0), (1, 1), wing_front, wing_left),
        ]
    for (cx, cy), (sx, sy), plane_x, plane_y in corners:
        for c in (36.0, 12.0):
            local = [
                (c - 0.75, -OH),
                (c + 0.75, -OH),
                (c + 0.75, c + 0.75 - HS),
                (c - 0.75, c - 0.75 - HS),
            ]
            solids.append(
                member([(cx + sx * a, cy + sy * d) for a, d in local], plane_x)
            )
            solids.append(
                member([(cx + sx * d, cy + sy * a) for a, d in local], plane_y)
            )
    if wing == 120:
        # Valley jacks: main front X 132, 156 and wing left Y 132, 156, from
        # the valley's face to the ridges' faces.
        for x in (132, 156):
            plan = [
                (x - 0.75, x - 0.75 + HS),
                (x + 0.75, x + 0.75 + HS),
                (x + 0.75, 179.25),
                (x - 0.75, 179.25),
            ]
            solids.append(member(plan, main_front))
            solids.append(member(mirror(plan), wing_left))
    else:
        # The hip from N1 (216, 144) to the main ridge's end runs X + Y = 360;
        # the right wall's jack on Y 156 ends at its side face, and the main
        # front's cripple on X 204 runs from the valley's face to it.
        plan = [
            (252, 155.25),
            (252, 156.75),
            (360 + HS - 156.75, 156.75),
            (360 + HS - 155.25, 155.25),
        ]
        solids.append(member(plan, right))
        cripple = [
            (203.25, 203.25 - gap + HS),
            (204.75, 204.75 - gap + HS),
            (204.75, 360 - HS - 204.75),
            (203.25, 360 - HS - 203.25),
        ]
        solids.append(member(cripple, main_front))

    # Hips: dropped; from the fascia corner to the inside corner of the
    # ridge-end and king commons; tails ripped to the commons' depth.
    def hip(corner: tuple[float, float], signs: tuple[int, int], run: float) -> Solid:
        (cx, cy), (sx, sy) = corner, signs
        hexagon = [
            (-OH, -OH),
            (-OH + HS, -OH),
            (run, run - HS),
            (run, run),
            (run - HS, run),
            (-OH, -OH + HS),
        ]
        plan = [(cx + sx * a, cy + sy * b) for a, b in hexagon]
        plane: PlaneSpec = ((cx, cy, TOP0 - DROP), sx * K / 2, sy * K / 2, HIP_PLUMB)
        return member(plan, plane, (cx, cy, TOP0 - PLUMB))

    solids += [
        hip((0, 120), (1, 1), 59.25),
        hip((0, 240), (1, -1), 59.25),
        hip((240, 240), (-1, -1), 59.25),
        hip((240, 0), (-1, 1), w2 / 2 - 0.75),
        hip((wing, 0), (1, 1), w2 / 2 - 0.75),
    ]
    if wing != 120:
        # The hip N1 -> N2: its top end a double cheek in the inside corner of
        # the main front's ridge-end common (X 180.75) and the right wall's
        # king (Y 179.25); its foot on the wing ridge's end (Y 144.75),
        # wrapped round that ridge's corner (X 215.25).
        plan = [
            (180.75, 179.25),
            (180.75 + HS, 179.25),
            (215.25 + HS, 144.75),
            (215.25, 144.75),
            (215.25, 144.75 - HS),
            (180.75, 179.25 - HS),
        ]
        n1 = (216.0, 144.0, TOP0 + K * w2 / 2 - DROP)
        solids.append(member(plan, (n1, -K / 2, K / 2, HIP_PLUMB)))

    # The valley: not dropped; a V notch on the fascias' inside corner
    # (wing - 12, 108), the top a cheek on each member it meets.
    if wing == 120:
        valley = [
            (108, 108),
            (108, 108 - HS),
            (179.25, 179.25 - HS),
            (179.25, 179.25),
            (179.25 - HS, 179.25),
            (108 - HS, 108),
        ]
    else:
        valley = [
            (180, 108),
            (180, 108 - HS),
            (215.25, 215.25 - gap - HS),
            (215.25, 360 - HS - 215.25),
            (216 - HS, 144),
            (180 - HS, 108),
        ]
    solids.append(
        member(
            valley,
            ((wing, 120, TOP0), K / 2, K / 2, HIP_PLUMB),
            (wing, 120, TOP0 - PLUMB + M * 0.75),
        )
    )

    # Ridges: tops flush with the commons' at the ridges' faces.
    main_top = TOP0 + K * 59.25
    solids.append(
        (
            Pos(120 * IN, 180 * IN, (main_top - 3.625) * IN)
            * Box(121.5 * IN, 1.5 * IN, 7.25 * IN)
        ).solid()
    )
    wing_top = TOP0 + K * (w2 / 2 - 0.75)
    y0 = w2 / 2 - 0.75
    y1 = 179.25 if wing == 120 else 144.0 + 0.75
    solids.append(
        (
            Pos(ridge_v * IN, (y0 + y1) / 2 * IN, (wing_top - 3.625) * IN)
            * Box(1.5 * IN, (y1 - y0) * IN, 7.25 * IN)
        ).solid()
    )
    return solids


def wall_envelopes(wing: float) -> list[Solid]:
    """B4's six walls as solid envelopes Z 0..97.125 (buildings.md):
    nothing may enter a wall's volume at all."""

    def box(x0: float, x1: float, y0: float, y1: float) -> Solid:
        return (
            Location(((x0 + x1) / 2 * IN, (y0 + y1) / 2 * IN, PLATE / 2 * IN))
            * Box((x1 - x0) * IN, (y1 - y0) * IN, PLATE * IN)
        ).solid()

    return [
        box(0, 240, 236.5, 240),
        box(236.5, 240, 0, 236.5),
        box(wing, 236.5, 0, 3.5),
        box(wing, wing + 3.5, 3.5, 120),
        box(0, wing + 3.5, 120, 123.5),
        box(0, 3.5, 123.5, 236.5),
    ]


# --- Helpers -----------------------------------------------------------------------


def _request(name: str) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )


def _members(name: str) -> list[CutListMember]:
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / name / "members.json").read_text()
    )
    return [CutListMember.model_validate(item) for item in raw]


def _step_solids(request: EvaluateTreeRequest, path: Path) -> list[Solid]:
    export = ExportTreeRequest.model_validate(
        {**request.model_dump(mode="json"), "format": "step"}
    )
    response = client.post("/api/v1/export/tree", json=export.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    path.write_bytes(response.content)
    return list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def _built(request: EvaluateTreeRequest) -> list[Solid]:
    return list(build_model_solid(request).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def _key(solid: Solid) -> tuple[float, float, float]:
    c = solid.center()
    return (round(c.X, 3), round(c.Y, 3), round(c.Z, 3))


def _volume(shape: Any) -> float:
    return float(measure_shape(shape).volume) if shape else 0.0


def _overlapping(
    solids: Sequence[Solid], others: Sequence[Solid] = ()
) -> tuple[int, list[tuple[int, int, float]]]:
    """Pairs among *solids*, and of *solids* with *others*, whose boxes
    overlap: how many were probed exactly, and those sharing any volume."""
    everything = [*solids, *others]
    boxes = [s.bounding_box() for s in everything]
    probed = 0
    bad: list[tuple[int, int, float]] = []
    for i, j in itertools.combinations(range(len(everything)), 2):
        if i >= len(solids):
            break
        a, b = boxes[i], boxes[j]
        if all(
            min(getattr(a.max, k), getattr(b.max, k))
            - max(getattr(a.min, k), getattr(b.min, k))
            > 1e-6
            for k in ("X", "Y", "Z")
        ):
            probed += 1
            probe = probe_overlap(everything[i], everything[j])
            if probe.unresolved or probe.volume_mm3 != 0.0:
                bad.append((i, j, probe.volume_mm3))
    return probed, bad


def _top_face_length(solid: Solid) -> float:
    """A rafter's top face (the largest face neither a side nor level nor
    facing down) over its 1.5 width: its centreline length."""
    rest = [
        f
        for f in solid.faces()
        if abs(f.normal_at().X) < 1 - 1e-9
        and abs(f.normal_at().Y) < 1 - 1e-9
        and 1e-9 < f.normal_at().Z < 1 - 1e-9
    ]
    return max(f.area for f in rest) / (1.5 * IN) / IN


def _midplane_vertices(member: Solid) -> list[Vector]:
    """A hip's or valley's vertices on its centreline's vertical plane (the
    points of its double cheeks and V notch), in inches."""
    sides = [
        f
        for f in member.faces()
        if abs(f.normal_at().Z) < 1e-9 and f.area > 100 * IN * IN
    ]
    a, b = sides[0], sides[1]
    normal = a.normal_at()
    centre = (a.center() + b.center()) * 0.5
    return [
        Vector(v) / IN
        for v in member.vertices()
        if abs((Vector(v) - centre).dot(normal)) < 1e-6
    ]


def _centre_length(member: Solid) -> float:
    """Along the top's centreline, the tail's point to the top end's."""
    points = _midplane_vertices(member)
    tail = min(points, key=lambda p: p.Z)
    tail_top = max(
        (p for p in points if math.hypot(p.X - tail.X, p.Y - tail.Y) < 1e-6),
        key=lambda p: p.Z,
    )
    top = max(points, key=lambda p: p.Z)
    return (top - tail_top).length


def _labelled(name: str, solids: list[Solid]) -> dict[str, list[Solid]]:
    """The kernel's solids by member, matched to the script's by centroid:
    the script says which is which."""
    want = script_roof(WING[name])
    labels = _script_labels(WING[name])
    by_key = {_key(s): label for s, label in zip(want, labels, strict=True)}
    out: dict[str, list[Solid]] = {}
    for solid in solids:
        out.setdefault(by_key[_key(solid)], []).append(solid)
    return out


def _script_labels(wing: float) -> list[str]:
    """The script's members in its own order (script_roof's comments)."""
    if wing == 120:
        return (
            ["common"] * 7
            + ["common"] * 2
            + ["cut common"]
            + ["common"] * 2
            + ["cut common"]
            + ["common"] * 7
            + ["jack"] * 20
            + ["valley jack"] * 4
            + ["hip"] * 5
            + ["valley"]
            + ["ridge"] * 2
        )
    return (
        ["common"] * 7
        + ["common"] * 5
        + ["cut common"]
        + ["common"] * 4
        + ["common"] * 6
        + ["common"]
        + ["common"]
        + ["jack"] * 12
        + ["jack"]
        + ["cripple"]
        + ["hip"] * 6
        + ["valley"]
        + ["ridge"] * 2
    )


# --- Tests -------------------------------------------------------------------------

#: buildings.md B4's roof table, and its 48 in wing edit: member, profile,
#: quantity, overall length (in), stock. A cheek adds its long point, 0.75 x
#: 13.416/12 = 0.839; a ripped hip's or valley's tail adds its plumb depth
#: (the commons' 6.149 less the drop 0.265) x 6/18 past its top's point.
CUT_LISTS: dict[str, list[tuple[str, str, int, float, int]]] = {
    "b4-l-hip-valley": [
        ("Common", "2x6", 2, 82.063, 8),
        ("Common", "2x6", 18, 82.410, 8),
        ("Jack", "2x6", 10, 29.235, 8),
        ("Jack", "2x6", 10, 56.068, 8),
        ("Valley jack", "2x6", 2, 28.397, 8),
        ("Valley jack", "2x6", 2, 55.230, 8),
        ("Hip", "2x8", 5, 108.836, 10),
        ("Valley", "2x8", 1, 109.632, 10),
        ("Ridge", "2x8", 1, 120, 10),
        ("Ridge", "2x8", 1, 121.5, 12),
    ],
    "b4-wing-48": [
        ("Common", "2x6", 11, 42.161, 8),
        ("Common", "2x6", 1, 82.063, 8),
        ("Common", "2x6", 13, 82.410, 8),
        ("Jack", "2x6", 6, 29.235, 8),
        ("Jack", "2x6", 7, 56.068, 8),
        ("Cripple", "2x6", 1, 28.888, 8),
        ("Hip", "2x8", 2, 54.836, 8),
        ("Hip", "2x8", 1, 55.109, 8),
        ("Hip", "2x8", 3, 108.836, 10),
        ("Valley", "2x8", 1, 55.961, 8),
        ("Ridge", "2x8", 2, 121.5, 12),
    ],
}


@each_roof
def test_the_cut_list_is_buildings_md_b4(name: str) -> None:
    request = _request(name)
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B4 roof",
        length_unit="in",
        pieces=part_pieces(
            BodyExtentsResult.model_validate_json(response.content),
            _members(name),
            request.materials,
        ),
    )
    rows = [
        (
            line.member,
            line.profile,
            line.quantity,
            round(line.length_mm / IN, 3),
            line.stock_length_ft,
        )
        for line in cut_list.lines
    ]
    assert rows == CUT_LISTS[name]
    # The rows by hand: a common's overall is its line + 5.5 x 6/12; a hip's
    # line (59.25 + 12) x 18/12 = 106.875 plus its ripped tail's plumb depth
    # x 6/18; the valley's 0.75 x 18/16.971 more for its V notch's edges.
    ripped = PLUMB - DROP
    assert pytest.approx(82.410, abs=5e-4) == 79.660 + 2.75
    assert pytest.approx(82.063, abs=1e-3) == 78.474 + 2.75 + 0.839
    assert 106.875 + ripped / 3 == pytest.approx(108.836, abs=5e-4)
    assert 106.875 + 0.75 * 18 / (12 * R2) + ripped / 3 == pytest.approx(
        109.632, abs=5e-4
    )
    assert {line.material for line in cut_list.lines} == {"spf_lumber"}
    assert cut_list.unclassified == 0
    assert sum(line.quantity for line in cut_list.lines) == TOTALS[name]["members"]


@each_roof
def test_the_lengths_measured_on_the_step_are_the_specs(
    name: str, tmp_path: Path
) -> None:
    roles = _labelled(name, _step_solids(_request(name), tmp_path / "roof.step"))
    unit = math.hypot(12, 6) / 12
    for common in roles["common"]:
        length = _top_face_length(common)
        # B4's commons are B2's rafter (79.660); the 48 wing's run 23.25.
        assert length in (
            pytest.approx(79.660, abs=5e-4),
            pytest.approx((23.25 + 12) * unit, abs=5e-4),
        )
    for cut in roles["cut common"]:
        assert _top_face_length(cut) == pytest.approx(78.474, abs=5e-4)
    jacks = sorted({round(_top_face_length(j), 3) for j in roles["jack"]})
    assert jacks == [25.647, 52.480]
    if name == "b4-l-hip-valley":
        valley_jacks = sorted(_top_face_length(j) for j in roles["valley jack"])
        assert valley_jacks[0] == pytest.approx(24.808, abs=5e-4)
        assert valley_jacks[-1] == pytest.approx(51.641, abs=5e-4)
        assert valley_jacks[-1] - valley_jacks[0] == pytest.approx(26.833, abs=5e-4)
        assert _centre_length(roles["valley"][0]) == pytest.approx(106.875, abs=5e-4)
    else:
        assert _top_face_length(roles["cripple"][0]) == pytest.approx(24.461, abs=5e-4)
    ridge_top = max(r.bounding_box().max.Z for r in roles["ridge"]) / IN
    for hip in roles["hip"][:3]:
        # The main roof's hips: B3's, 106.875 on the centreline, dropped.
        assert _centre_length(hip) == pytest.approx(106.875, abs=5e-4)
        assert ridge_top - hip.bounding_box().max.Z / IN == pytest.approx(
            DROP, abs=5e-4
        )
    # The valley is not dropped: its top's highest point is on the valley
    # line where it meets the ridges' (or the hip's) faces.
    # B4: (179.25, 179.25), 59.25 along both walls from (120, 120); the 48
    # wing: on the hip's face X + Y = 360 - 1.061, 46.939 along both.
    valley = roles["valley"][0]
    along = 2 * 59.25 if name == "b4-l-hip-valley" else 360 - HS - 192 - 120
    top_end = valley.bounding_box().max.Z / IN
    assert top_end == pytest.approx(TOP0 + K * along / 2, abs=5e-4)


def test_the_tails_are_ripped_to_the_commons_depth(tmp_path: Path) -> None:
    """ROOF-HIP-TAIL on the STEP: each hip's and the valley's tail point,
    where the fascias meet, has its bottom at the commons' tails' bottoms,
    so the fascia line is straight; at the wall corner, the heel on the
    centreline is the commons' 1.75 (hips) and 1.75 - 0.265 (the valley)."""
    roles = _labelled(
        "b4-l-hip-valley",
        _step_solids(_request("b4-l-hip-valley"), tmp_path / "roof.step"),
    )
    tail_bottom = PLATE - SEAT * K - OH * K  # a common's tail: 89.375
    valley = roles["valley"][0]
    for member, heel in [*((h, 1.75) for h in roles["hip"]), (valley, 1.75 - DROP)]:
        points = _midplane_vertices(member)
        tail = min(points, key=lambda p: p.Z)
        # A hip's tail point is at the fascia corner, on the commons' tails'
        # bottom line; the valley's notch point is the drop above it, so the
        # notch's edges, on the fascias, are on it.
        lift = DROP if member is valley else 0.0
        assert pytest.approx(tail_bottom + lift, abs=5e-4) == tail.Z
        corner_points = [
            p
            for p in points
            if any(math.hypot(p.X - cx, p.Y - cy) < 1e-6 for cx, cy in footprint(120))
        ]
        assert PLATE - min(p.Z for p in corner_points) == pytest.approx(heel, abs=5e-4)


@each_roof
def test_the_bodies_are_the_independent_scripts(name: str, tmp_path: Path) -> None:
    """The kernel's bodies are the script's to 1e-4 mm^3 each (volume and
    symmetric difference); the STEP's within the golden's reviewed round-trip
    bound. Without the rips, the script is the hand total."""
    want = sorted(script_roof(WING[name]), key=_key)
    got = sorted(_built(_request(name)), key=_key)
    assert len(got) == len(want) == TOTALS[name]["members"]
    total = 0.0
    for a, b in zip(got, want, strict=True):
        assert _volume(a) == pytest.approx(_volume(b), abs=1e-4)
        difference = _volume(a.cut(b)) + _volume(b.cut(a))  # pyright: ignore[reportUnknownMemberType]
        assert difference < 1e-4, (_key(a), difference)
        total += _volume(a)
    script = sum(_volume(s) for s in want)
    assert total / IN**3 == pytest.approx(script / IN**3, abs=1e-4)
    expected = json.loads((GOLDENS / name / "expected.json").read_text())
    assert total == pytest.approx(expected["properties"]["volume"], abs=1e-3)
    if "untrimmed" in TOTALS[name]:
        untrimmed = sum(_volume(s) for s in script_roof(WING[name], rip=False))
        assert untrimmed / IN**3 == pytest.approx(TOTALS[name]["untrimmed"], abs=5e-4)
    bound = expected["roundtrip_tolerance"]
    step = sorted(_step_solids(_request(name), tmp_path / "roof.step"), key=_key)
    assert [_key(s) for s in step] == [_key(s) for s in want]
    for a, b in zip(step, want, strict=True):
        assert _volume(a) == pytest.approx(_volume(b), abs=bound)
        difference = _volume(a.cut(b)) + _volume(b.cut(a))  # pyright: ignore[reportUnknownMemberType]
        assert difference < bound, (_key(a), difference)


@each_roof
def test_nothing_interferes_with_the_walls_or_each_other(
    name: str, tmp_path: Path
) -> None:
    roof = _step_solids(_request(name), tmp_path / "roof.step")
    probed, bad = _overlapping(roof, wall_envelopes(WING[name]))
    assert bad == []
    # Every jack and valley-side member touches its hip or valley, and every
    # bearing member its wall: those pairs are probed exactly.
    assert probed >= TOTALS[name]["members"]


WallFrame = tuple[float, float, int, int, tuple[int, int]]


def _piece(frame: WallFrame, u0: float, u1: float, z0: float, z1: float) -> Solid:
    """A wall member from u0 to u1 along the wall, across its 3.5 depth."""
    x, y, c, s, across = frame
    corners = [
        (x + c * u + across[0] * v, y + s * u + across[1] * v)
        for u, v in ((u0, 0), (u1, 0), (u1, 3.5), (u0, 3.5))
    ]
    xs = sorted(p[0] for p in corners)
    ys = sorted(p[1] for p in corners)
    centre = ((xs[0] + xs[-1]) / 2 * IN, (ys[0] + ys[-1]) / 2 * IN, (z0 + z1) / 2 * IN)
    size = ((xs[-1] - xs[0]) * IN, (ys[-1] - ys[0]) * IN, (z1 - z0) * IN)
    return (Location(centre) * Box(*size)).solid()


def test_b4s_walls_are_the_wall_rules() -> None:
    """B4's six walls from loft.wall (the fixture pinned to the plugin):
    each is plates and studs by the wall rules, typed here (studs 0.75 from
    the start, then every 16 from it, an end stud flush, one that would
    overlap it dropped; a double top plate; 92.625 studs), and no member of
    one wall overlaps another's."""
    data: dict[str, Any] = json.loads(gzip.decompress(WALLS.read_bytes()))
    solids = _built(EvaluateTreeRequest.model_validate(data["request"]))
    want: list[Solid] = []
    for x, y, direction, length in data["walls"]:
        c = round(math.cos(math.radians(direction)))
        s = round(math.sin(math.radians(direction)))
        across = (s, -c)  # framing on the right

        centres = [0.75]
        n = 1
        while 16 * n <= length - 0.75 - 1.5 + 1e-9:
            centres.append(16.0 * n)
            n += 1
        centres.append(length - 0.75)
        frame = (x, y, c, s, across)
        want += [_piece(frame, u - 0.75, u + 0.75, 1.5, 94.125) for u in centres]
        want += [
            _piece(frame, 0, length, 94.125, 95.625),
            _piece(frame, 0, length, 95.625, 97.125),
            _piece(frame, 0, length, 0, 1.5),
        ]
    assert len(solids) == len(want)
    for a, b in zip(sorted(solids, key=_key), sorted(want, key=_key), strict=True):
        difference = _volume(a.cut(b)) + _volume(b.cut(a))  # pyright: ignore[reportUnknownMemberType]
        assert difference < 1e-4, (_key(a), difference)
    _, bad = _overlapping(solids)
    assert bad == []


def _sweep() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(gzip.decompress(SWEEP.read_bytes()))
    return cases


@pytest.mark.parametrize("case", _sweep(), ids=[c["name"] for c in _sweep()])
def test_the_overlap_sweep_builds_every_member_touching_only(
    case: dict[str, Any],
) -> None:
    request = EvaluateTreeRequest.model_validate(case["request"])
    solids = _built(request)
    assert len(solids) == case["bodies"]
    assert all(s.is_valid for s in solids)
    plate = case["plate_height"]
    walls = [
        (
            Location(((x0 + x1) / 2 * IN, (y0 + y1) / 2 * IN, plate / 2 * IN))
            * Box((x1 - x0) * IN, (y1 - y0) * IN, plate * IN)
        ).solid()
        for x0, x1, y0, y1 in case["walls"]
    ]
    probed, bad = _overlapping(solids, walls)
    assert bad == [], bad
    assert probed > case["bodies"] // 2


def _drift(solids: Sequence[Solid], tmp_path: Path, name: str) -> float:
    before = sum(_volume(s) for s in solids)
    path = tmp_path / f"{name}.step"
    export_step(Compound(list(solids)), str(path))
    back = list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportUnknownVariableType]
    return sum(_volume(s) for s in back) - before  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]


@each_roof
def test_the_roofs_step_drift_is_occts(name: str, tmp_path: Path) -> None:
    """The golden's round-trip bound holds for the plugin's bodies, and the
    script's own solids drift through build123d's STEP too while its
    axis-aligned ridges do not: OCCT's writer rounding sloped coordinates."""
    bound = json.loads((GOLDENS / name / "expected.json").read_text())[
        "roundtrip_tolerance"
    ]
    ours = abs(_drift(_built(_request(name)), tmp_path, "ours"))
    twin = script_roof(WING[name])
    assert ours < bound, ours
    # The twin drifts (OCCT alone, ~1e-11 of the roof); its two axis-aligned
    # ridges only by summation order (2e-7 of 3.4e7 mm^3).
    assert 1e-4 < abs(_drift(twin, tmp_path, "twin")) < 1e-2
    assert abs(_drift(twin[-2:], tmp_path, "ridges")) < 1e-6
