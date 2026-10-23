"""BUILDING-OUTLINE acceptance: B7 from one outline sketch, on STEP.

``goldens/b7-outline`` is B7 (docs/reference-parts/buildings.md) built the way
BACKLOG BUILDING-OUTLINE asks: one 288 x 192 sketch, a ``loft.floor`` 1.2.0 on
it, ``loft.wall`` 1.3.0 on it standing on the floor, the five openings
(``loft.door``/``loft.window`` 1.1.0) and a ``loft.roof`` 1.4.0 whose front and
back walls define the slope. ``model.json`` and ``members.json`` are pinned
to the plugins by ``packages/loft-plugins/tests/test_building_outline.py``;
``fixtures/outline-cases.json.gz`` holds the edits. Geometry never learns
plugins exist, so this module imports nothing from them.

Checked here against an INDEPENDENT build123d script (:func:`script`, typed
from buildings.md B7 and the QA-B7-HOUSE round's numbers, sharing no code
with the plugins):

1. the STEP's 217 solids are the script's, solid for solid; the volume is
   the round's 264 895.4795 in^3 less the 26 rafter tails' notches in the
   front and back walls' OSB (43.1005859375 in^3): 264 852.3788656 in^3;
2. interference none: the round's build shared that 43.1 in^3 between the
   tails and the OSB, and the outline roof notches the OSB round them;
3. the cut list is the round's 23 lines (the eave OSB's net area less the
   notches, the same 17 sheets) and its price to the last line, $2,868.87,
   the members over 20 ft spliced (CUT-LIST-LONG-STOCK);
4. edit 1 (the 288 dimension set to 336) is the round's 28 ft house: 234
   solids, the script's at 336, with no interference;
5. ``b7-front-wall-from-end`` (OPENING-FROM-END) and ``b7-units``
   (OPENING-UNITS: every opening picked by call size and its unit drawn, 229
   solids, each unit one priced cut-list line).

Regenerate expected.json's derivation numbers with
``uv run python services/geometry/tests/test_outline_b7.py``.
"""

import gzip
import itertools
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from build123d import (
    Box,
    Face,
    Pos,
    Solid,
    Vector,
    Wire,
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
    cut_list_csv,
    cut_list_response,
    part_pieces,
)
from loft_wire.features import EvaluateTreeRequest, ExportTreeRequest
from loft_wire.price_book import PriceBookResponse

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
NAME = "b7-outline"
CASES = Path(__file__).resolve().parent / "fixtures" / "outline-cases.json.gz"
IN = 25.4

# --- B7, typed from buildings.md and the round (inches) ----------------------------

W = 192.0  # the house's depth (Y)
T = 1.5  # every member's thickness
SILL_W, SILL_T = 5.5, 1.5  # PT 2x6 sills, flat
JOIST = 9.25  # 2x10
FRAMING_TOP = SILL_T + JOIST  # 10.75
PLY = 23 / 32
BASE = FRAMING_TOP + PLY  # the walls stand on the subfloor: 11.46875
H = 97.125  # plate to plate
D = 5.5  # 2x6 walls
STUD_TOP = T + 92.625  # 94.125 above the wall's base
OSB = 7 / 16
PLATE = BASE + H  # 108.59375
SIDE = W - 2 * D  # 181: the side walls fit between the front and back

SPF, PT, OSB_M, PLY_M = "spf_lumber", "southern_pine_pt", "osb", "plywood"
PVC, GLASS = "pvc", "glass"
DENSITY = {
    SPF: 450.0,
    PT: 582.0,
    OSB_M: 641.0,
    PLY_M: 577.0,
    PVC: 1400.0,
    GLASS: 2500.0,
}  # kg/m^3

Bounds = tuple[float, float, float, float, float, float]


@dataclass(frozen=True)
class Opening:
    """A rough opening in a wall's frame: centre along the wall from its
    start, width, sill and head above its base."""

    centre: float
    width: float
    sill: float
    head: float

    @property
    def door(self) -> bool:
        return self.sill == 0.0


def door(centre: float) -> Opening:
    return Opening(centre, 36 + 2, 0.0, 80 + 2.5)  # 38 x 82.5


def window(centre: float, w: float, h: float) -> Opening:
    return Opening(centre, w + 0.5, 82.5 - (h + 0.5), 82.5)


def layout(length: float, spacing: float) -> list[float]:
    """Centres from 0.75, every *spacing*, the far one flush, a layout one
    that would pass the far one's face dropped (buildings.md B2)."""
    inner: list[float] = []
    k = 1
    while spacing * k + 0.75 <= length - T:
        inner.append(spacing * k)
        k += 1
    return [0.75, *inner, length - 0.75]


#: A member in its wall's frame: u along, v in from the outer face, z up.
Local = tuple[str, str, float, float, float, float, float, float]


def wall_frame(length: float, openings: Sequence[Opening]) -> list[Local]:
    """buildings.md B2's framing rules on a 2x6 wall: layout studs, and per
    opening kings, jacks, two header plies (2x6 on edge at each face), top
    cripples, a window's flat sill and bottom cripples; double top plate; a
    PT bottom plate cut out of a door."""
    out: list[Local] = []
    studs = layout(length, 16.0)
    for c in studs:
        if any(
            o.centre - o.width / 2 - 3 < c + 0.75
            and c - 0.75 < o.centre + o.width / 2 + 3
            for o in openings
        ):
            continue
        out.append(("Stud", SPF, c - 0.75, c + 0.75, 0, D, T, STUD_TOP))
    for o in sorted(openings, key=lambda o: o.centre):
        u0, u1 = o.centre - o.width / 2, o.centre + o.width / 2
        out += [
            ("Stud", SPF, u0 - 3, u0 - 1.5, 0, D, T, STUD_TOP),
            ("Stud", SPF, u1 + 1.5, u1 + 3, 0, D, T, STUD_TOP),
            ("Jack", SPF, u0 - 1.5, u0, 0, D, T, o.head),
            ("Jack", SPF, u1, u1 + 1.5, 0, D, T, o.head),
            ("Header", SPF, u0 - 1.5, u1 + 1.5, 0, T, o.head, o.head + 5.5),
            ("Header", SPF, u0 - 1.5, u1 + 1.5, D - T, D, o.head, o.head + 5.5),
        ]
        for c in studs:
            if u0 - 1.5 <= c - 0.75 and c + 0.75 <= u1 + 1.5:
                out.append(
                    ("Cripple", SPF, c - 0.75, c + 0.75, 0, D, o.head + 5.5, STUD_TOP)
                )
        if not o.door:
            out.append(("Sill", SPF, u0, u1, 0, D, o.sill - T, o.sill))
            for c in studs:
                if u0 <= c - 0.75 and c + 0.75 <= u1:
                    out.append(
                        ("Cripple", SPF, c - 0.75, c + 0.75, 0, D, T, o.sill - T)
                    )
    out += [
        ("Top plate", SPF, 0, length, 0, D, STUD_TOP, STUD_TOP + T),
        ("Top plate", SPF, 0, length, 0, D, STUD_TOP + T, STUD_TOP + 2 * T),
    ]
    start = 0.0
    for o in sorted((o for o in openings if o.door), key=lambda o: o.centre):
        out.append(("Bottom plate", PT, start, o.centre - o.width / 2, 0, D, 0, T))
        start = o.centre + o.width / 2
    out.append(("Bottom plate", PT, start, length, 0, D, 0, T))
    return out


@dataclass(frozen=True)
class Wall:
    """A wall's start, unit direction and inward normal in plan."""

    x: float
    y: float
    along: tuple[int, int]
    inward: tuple[int, int]
    length: float
    openings: tuple[Opening, ...]

    def box(
        self, u0: float, u1: float, v0: float, v1: float, z0: float, z1: float
    ) -> Bounds:
        xs = [
            self.x + u * self.along[0] + v * self.inward[0]
            for u in (u0, u1)
            for v in (v0, v1)
        ]
        ys = [
            self.y + u * self.along[1] + v * self.inward[1]
            for u in (u0, u1)
            for v in (v0, v1)
        ]
        return (min(xs), max(xs), min(ys), max(ys), BASE + z0, BASE + z1)


def walls(length: float, left: float = 60.0) -> list[Wall]:
    """Clockwise from the front: the front and back run the full length, the
    sides fit between them (181); B7's openings at X *left* (60), 144, 228
    (front), X 144 (back) and centred on each side."""
    big = (36.0, 48.0)
    return [
        Wall(
            length,
            0,
            (-1, 0),
            (0, 1),
            length,
            (
                door(length - 144),
                window(length - left, *big),
                window(length - 228, *big),
            ),
        ),
        Wall(0, D, (0, 1), (1, 0), SIDE, (window(SIDE / 2, 24, 36),)),
        Wall(0, W, (1, 0), (0, -1), length, (window(144, *big),)),
        Wall(length, W - D, (0, -1), (-1, 0), SIDE, (window(SIDE / 2, 24, 36),)),
    ]


# --- The roof (buildings.md B2's rules at B7's size) -------------------------------

SLOPE = 6 / 12
RAFTER_D = 7.25  # 2x8
RIDGE_D = 9.25  # 2x10
SEAT = min(D, RAFTER_D / 3 / SLOPE)  # the heel limited to 1/3: 29/6
HEEL = SEAT * SLOPE
PLUMB = RAFTER_D * math.sqrt(1 + SLOPE * SLOPE)
RIDGE_FACE = W / 2 - T / 2  # 95.25
OVERHANG = 12.0


def bottom(y: float) -> float:
    """The front rafter's underside above Y *y* (its local frame)."""
    return PLATE + (y - SEAT) * SLOPE


def rafter_profile() -> list[tuple[float, float]]:
    return [
        (-OVERHANG, bottom(-OVERHANG)),
        (0.0, PLATE - HEEL),
        (0.0, PLATE),
        (SEAT, PLATE),
        (RIDGE_FACE, bottom(RIDGE_FACE)),
        (RIDGE_FACE, bottom(RIDGE_FACE) + PLUMB),
        (-OVERHANG, bottom(-OVERHANG) + PLUMB),
    ]


# --- The members as solids ----------------------------------------------------------


@dataclass(frozen=True)
class Member:
    member: str
    material: str
    solid: Solid


def box(b: Bounds) -> Solid:
    x0, x1, y0, y1, z0, z1 = b
    return (
        Pos((x0 + x1) / 2 * IN, (y0 + y1) / 2 * IN, (z0 + z1) / 2 * IN)
        * Box((x1 - x0) * IN, (y1 - y0) * IN, (z1 - z0) * IN)
    ).solid()


def prism_x(points: Sequence[tuple[float, float]], x0: float, x1: float) -> Solid:
    """A (Y, Z) polygon at X *x0* extruded to *x1*."""
    wire = Wire.make_polygon(
        [Vector(x0 * IN, y * IN, z * IN) for y, z in points], close=True
    )
    return Solid.extrude(Face(wire), Vector((x1 - x0) * IN, 0, 0))


def floor_boxes(length: float) -> list[tuple[str, str, Bounds]]:
    out: list[tuple[str, str, Bounds]] = [
        ("Sill", PT, (0, length, 0, SILL_W, 0, SILL_T)),
        ("Sill", PT, (0, length, W - SILL_W, W, 0, SILL_T)),
        ("Sill", PT, (0, SILL_W, SILL_W, W - SILL_W, 0, SILL_T)),
        ("Sill", PT, (length - SILL_W, length, SILL_W, W - SILL_W, 0, SILL_T)),
        ("Rim", SPF, (0, length, 0, T, SILL_T, FRAMING_TOP)),
        ("Rim", SPF, (0, length, W - T, W, SILL_T, FRAMING_TOP)),
    ]
    out += [
        ("Joist", SPF, (c - 0.75, c + 0.75, T, W - T, SILL_T, FRAMING_TOP))
        for c in layout(length, 16.0)
    ]
    for row, y0 in enumerate(range(0, int(W), 48)):
        edges = (
            [0.0]
            + [x for x in range(48 if row % 2 else 96, int(length), 96)]
            + [length]
        )
        for x0, x1 in itertools.pairwise(edges):
            out.append(("Subfloor", PLY_M, (x0, x1, y0, y0 + 48, FRAMING_TOP, BASE)))
    return out


def framing_boxes(length: float, left: float = 60.0) -> list[tuple[str, str, Bounds]]:
    return [
        (member, material, wall.box(*local))
        for wall in walls(length, left)
        for member, material, *local in wall_frame(wall.length, wall.openings)  # type: ignore[misc]
    ]


def panel_boxes(length: float, left: float = 60.0) -> list[tuple[Bounds, list[Bounds]]]:
    """Each OSB panel's box and the rough openings to cut from it: 48 in
    from each wall's start, outside its face, full height; the side walls'
    four corner rips 5.5 + 7/16 wide past their ends."""
    out: list[tuple[Bounds, list[Bounds]]] = []
    for wall in walls(length, left):
        holes = [
            wall.box(
                o.centre - o.width / 2,
                o.centre + o.width / 2,
                -1 - OSB,
                1,
                o.sill,
                o.head,
            )
            for o in wall.openings
        ]
        cuts = [*range(0, math.ceil(wall.length), 48), wall.length]
        for u0, u1 in itertools.pairwise(cuts):
            out.append((wall.box(u0, u1, -OSB, 0, 0, H), holes))
        if wall.length == SIDE:
            out.append((wall.box(-D - OSB, 0, -OSB, 0, 0, H), []))
            out.append((wall.box(SIDE, SIDE + D + OSB, -OSB, 0, 0, H), []))
    return out


def rafters(length: float) -> list[Solid]:
    front = rafter_profile()
    back = [(W - y, z) for y, z in reversed(front)]
    return [
        prism_x(profile, c - 0.75, c + 0.75)
        for c in layout(length, 24.0)
        for profile in (front, back)
    ]


def ridge(length: float) -> Bounds:
    top = bottom(RIDGE_FACE) + PLUMB
    return (0, length, W / 2 - T / 2, W / 2 + T / 2, top - RIDGE_D, top)


# --- Window and door units (OPENING-UNITS) ------------------------------------------

#: How a unit is drawn (in), typed from RESEARCH §23's OPENING-UNITS entry: a
#: window's frame 2 in wide and 3.25 deep from the framing's face round a
#: 1/4 in pane centred in it, the unit 1/2 in under its rough opening each
#: way and centred in it; a door's frame 3/4 in jambs and head and a 1.25 in
#: threshold, the wall's depth deep, round a 1.75 in slab at the face, the
#: unit 1/2 in under the opening, centred across it and on the subfloor.
WIN_FACE, WIN_DEPTH, PANE = 2.0, 3.25, 0.25
JAMB, THRESHOLD, SLAB = 0.75, 1.25, 1.75


def ring(wall: Wall, outer: Bounds, hole: Bounds) -> Solid:
    solid = box(wall.box(*outer))
    return solid.cut(box(wall.box(*hole))).solids()[0]  # pyright: ignore[reportUnknownMemberType]


def unit_members(length: float = 288.0, left: float = 60.0) -> list[Member]:
    """Every opening's unit: a window's frame (PVC) and pane (glass), a
    door's frame and slab (SPF)."""
    out: list[Member] = []
    for wall in walls(length, left):
        for o in wall.openings:
            u0, u1 = o.centre - o.width / 2 + 0.25, o.centre + o.width / 2 - 0.25
            if o.door:
                z1 = o.head - 0.5
                slab = (u0 + JAMB, u1 - JAMB, 0.0, SLAB, THRESHOLD, z1 - JAMB)
                outer = (u0, u1, 0.0, D, 0.0, z1)
                hole = (slab[0], slab[1], -1.0, D + 1, slab[4], slab[5])
                out.append(Member("Door", SPF, ring(wall, outer, hole)))
                out.append(Member("Slab", SPF, box(wall.box(*slab))))
                continue
            z0, z1 = o.sill + 0.25, o.head - 0.25
            g = (u0 + WIN_FACE, u1 - WIN_FACE, z0 + WIN_FACE, z1 - WIN_FACE)
            mid = (WIN_DEPTH - PANE) / 2
            outer = (u0, u1, 0.0, WIN_DEPTH, z0, z1)
            hole = (g[0], g[1], -1.0, WIN_DEPTH + 1, g[2], g[3])
            out.append(Member("Window", PVC, ring(wall, outer, hole)))
            out.append(
                Member(
                    "Glazing",
                    GLASS,
                    box(wall.box(g[0], g[1], mid, mid + PANE, g[2], g[3])),
                )
            )
    return out


def units_volume(length: float = 288.0, left: float = 60.0) -> Fraction:
    """The units' volume (in^3), exactly: a ring is its outer box less its
    hole, times its depth."""
    exact = Fraction(0)
    for wall in walls(length, left):
        for o in wall.openings:
            w, h = (
                Fraction(o.width) - Fraction(1, 2),
                Fraction(o.head - o.sill) - Fraction(1, 2),
            )
            if o.door:
                sw, sh = (
                    w - 2 * Fraction(JAMB),
                    h - Fraction(JAMB) - Fraction(THRESHOLD),
                )
                exact += (w * h - sw * sh) * Fraction(D) + sw * sh * Fraction(SLAB)
            else:
                gw, gh = w - 2 * Fraction(WIN_FACE), h - 2 * Fraction(WIN_FACE)
                exact += (w * h - gw * gh) * Fraction(WIN_DEPTH) + gw * gh * Fraction(
                    PANE
                )
    return exact


def script(
    length: float = 288.0, left: float = 60.0, units: bool = False
) -> list[Member]:
    """B7 at *length*, its left front window at X *left*: every member a
    build123d solid, each panel a box less its openings and the rafter tails
    that pass through it; with *units*, each opening's unit drawn."""
    out = [
        Member(m, mat, box(b))
        for m, mat, b in floor_boxes(length) + framing_boxes(length, left)
    ]
    tails = rafters(length)
    for panel, holes in panel_boxes(length, left):
        solid = box(panel)
        for hole in holes:
            solid = solid.cut(box(hole)).solids()[0]  # pyright: ignore[reportUnknownMemberType]
        for tail in tails:
            if solid.bounding_box().overlaps(tail.bounding_box()):  # pyright: ignore[reportUnknownMemberType]
                solid = solid.cut(tail).solids()[0]  # pyright: ignore[reportUnknownMemberType]
        out.append(Member("Sheathing", OSB_M, solid))
    out += [Member("Rafter", SPF, s) for s in tails]
    out.append(Member("Ridge", SPF, box(ridge(length))))
    if units:
        out += unit_members(length, left)
    return out


# --- The volume, analytically -------------------------------------------------------


def _shoelace(points: Sequence[tuple[float, float]]) -> float:
    return (
        abs(
            sum(
                a[0] * b[1] - b[0] * a[1]
                for a, b in zip(points, [*points[1:], points[0]], strict=True)
            )
        )
        / 2
    )


def notch_per_rafter() -> Fraction:
    """One tail's notch in the OSB (in^3): over the 7/16 thickness the panel
    above the tail's underside, z = P + (y - seat) / 2, across 1.5:
    t x slope x (seat x s + s^2 / 2), seat 29/6."""
    s, seat = Fraction(7, 16), Fraction(29, 6)
    return Fraction(3, 2) * Fraction(1, 2) * (seat * s + s * s / 2)


def analytic_volume(
    length: float, notched: bool = True, left: float = 60.0, units: bool = False
) -> float:
    """Boxes and panels in exact rationals, the rafters by the shoelace."""
    exact = units_volume(length, left) if units else Fraction(0)
    boxes = floor_boxes(length) + framing_boxes(length, left)
    for _, _, (x0, x1, y0, y1, z0, z1) in boxes:
        exact += (
            (Fraction(x1) - Fraction(x0))
            * (Fraction(y1) - Fraction(y0))
            * (Fraction(z1) - Fraction(z0))
        )
    for wall in walls(length, left):
        area = Fraction(wall.length) * Fraction(H)
        area -= sum(
            Fraction(o.width) * (Fraction(o.head) - Fraction(o.sill))
            for o in wall.openings
        )
        if wall.length == SIDE:
            area += 2 * (Fraction(D) + Fraction(7, 16)) * Fraction(H)
        exact += area * Fraction(7, 16)
    x0, x1, y0, y1, z0, z1 = ridge(length)
    pairs = len(layout(length, 24.0))
    if notched:
        exact -= 2 * pairs * notch_per_rafter()
    volume = float(exact)
    volume += (x1 - x0) * (y1 - y0) * (z1 - z0)
    volume += 2 * pairs * T * _shoelace(rafter_profile())
    return volume


# --- Reading the golden --------------------------------------------------------------


def _request(name: str = NAME) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )


def _members() -> list[CutListMember]:
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / NAME / "members.json").read_text()
    )
    return [CutListMember.model_validate(item) for item in raw]


def _extents(request: EvaluateTreeRequest) -> BodyExtentsResult:
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    return BodyExtentsResult.model_validate_json(response.content)


def _step_solids(tmp_path_factory: pytest.TempPathFactory, name: str) -> list[Solid]:
    request = ExportTreeRequest.model_validate(
        {**_request(name).model_dump(mode="json"), "format": "step"}
    )
    response = client.post("/api/v1/export/tree", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    path = tmp_path_factory.mktemp("step") / f"{name}.step"
    path.write_bytes(response.content)
    return list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return _step_solids(tmp_path_factory, NAME)


def _signature(solid: Solid) -> tuple[float, ...]:
    """A solid's volume (in^3) and bounds (in)."""
    bb = solid.bounding_box()
    values = (bb.min.X, bb.max.X, bb.min.Y, bb.max.Y, bb.min.Z, bb.max.Z)
    volume = float(measure_shape(solid).volume) / IN**3
    return (volume, *(v / IN for v in values))


def _unmatched(
    ours: Sequence[Solid], theirs: Sequence[Solid]
) -> list[tuple[float, ...]]:
    """Each of *ours* paired with one of *theirs* of the same volume (to 1e-4
    in^3) and bounds (to 1e-5 in), solid for solid; what finds no partner.
    Tolerances, not rounding: a rounded key splits on the 1e-10 noise of a
    value at a rounding edge (a cripple's 50.53125 in^3)."""
    left = [_signature(s) for s in theirs]
    missing: list[tuple[float, ...]] = []
    for sig in (_signature(s) for s in ours):
        k = next(
            (
                k
                for k, other in enumerate(left)
                if abs(sig[0] - other[0]) <= 1e-4
                and all(
                    abs(a - b) <= 1e-5 for a, b in zip(sig[1:], other[1:], strict=True)
                )
            ),
            None,
        )
        if k is None:
            missing.append(sig)
        else:
            left.pop(k)
    return missing + left


def _overlapping(solids: Sequence[Solid]) -> list[tuple[int, int, float]]:
    """Pairs whose boxes overlap on all three axes by any amount, probed
    exactly; those sharing any volume."""
    boxes = [s.bounding_box() for s in solids]
    bad: list[tuple[int, int, float]] = []
    for i, j in itertools.combinations(range(len(solids)), 2):
        a, b = boxes[i], boxes[j]
        if all(
            min(getattr(a.max, k), getattr(b.max, k))
            > max(getattr(a.min, k), getattr(b.min, k))
            for k in ("X", "Y", "Z")
        ):
            probe = probe_overlap(solids[i], solids[j])
            if probe.unresolved or probe.volume_mm3 != 0.0:
                bad.append((i, j, probe.volume_mm3))
    return bad


# --- 1. The STEP against the script ------------------------------------------------


def test_the_volume_is_the_rounds_less_the_tail_notches() -> None:
    """The round's script summed the members' prisms less each birdsmouth:
    264 895.4795 in^3 (house-b7.spec.ts), counting the tails' overlap with
    the OSB twice. Notching 26 tails: 26 x 1.5 x 1/2 x (29/6 x 7/16 + (7/16)^2
    / 2) = 43.1005859375 in^3 less."""
    assert analytic_volume(288, notched=False) == pytest.approx(264895.4795, abs=1e-4)
    assert 26 * notch_per_rafter() == Fraction(44135, 1024)
    assert float(26 * notch_per_rafter()) == 43.10058593750
    assert analytic_volume(288) == pytest.approx(264852.3788656, abs=1e-6)


def test_the_step_is_the_independent_scripts(step_solids: list[Solid]) -> None:
    mine = script()
    assert len(step_solids) == len(mine) == 217
    assert _unmatched(step_solids, [m.solid for m in mine]) == []
    volume = sum(float(measure_shape(s).volume) for s in step_solids) / IN**3
    assert volume == pytest.approx(analytic_volume(288), abs=1e-4)


# --- 2. Interference none ----------------------------------------------------------


def test_nothing_interferes(step_solids: list[Solid]) -> None:
    assert _overlapping(step_solids) == []


# --- 3. The cut list and its price -------------------------------------------------

#: The round's 23 lines (house-b7.spec.ts HOUSE_PRICED): member, quantity,
#: length (in) or net area (in^2), stock; the members over 20 ft spliced from
#: the cheapest pieces the book prices (CUT-LIST-LONG-STOCK). The eave walls'
#: OSB is the round's 83 175.71875 in^2 less the notches (43.1005859375 /
#: (7/16) = 98.515625 in^2). In the list's order (CUT-LIST-PANEL): the golden's
#: members.json names no plugins, so the lumber is one Other group after the
#: sheet goods' Sheathing, by member as it first appears in the tree, then
#: profile and material (the floor's PT sills before the windows' SPF), then
#: length. The app's list, with its plugins, is grouped Floor, Walls, Roof,
#: Sheathing (house-b7.spec.ts).
HOUSE: list[tuple[str, int, float, str]] = [
    ("Subfloor", 14, 55296, "12 x 4x8"),
    ("Sheathing", 24, 83175.71875 - 98.515625, "17 x 4x9"),
    ("Joist", 19, 189, "16 ft"),
    ("Rim", 2, 288, "16 ft + 8 ft"),
    ("Sill", 2, 181, "16 ft"),
    ("Sill", 2, 288, "2 x 12 ft"),
    ("Sill", 2, 24.5, "8 ft"),
    ("Sill", 3, 36.5, "8 ft"),
    ("Stud", 60, 92.625, "8 ft"),
    ("Jack", 12, 81, "8 ft"),
    ("Header", 4, 27.5, "8 ft"),
    ("Header", 6, 39.5, "8 ft"),
    ("Header", 2, 41, "8 ft"),
    ("Cripple", 14, 6.125, "8 ft"),
    ("Cripple", 7, 31, "8 ft"),
    ("Cripple", 4, 43, "8 ft"),
    ("Top plate", 4, 181, "16 ft"),
    ("Top plate", 4, 288, "16 ft + 8 ft"),
    ("Bottom plate", 2, 125, "12 ft"),
    ("Bottom plate", 2, 181, "16 ft"),
    ("Bottom plate", 1, 288, "2 x 12 ft"),
    ("Rafter", 26, 123.5341, "12 ft"),
    ("Ridge", 1, 288, "16 ft + 8 ft"),
]

#: The round's eight blanks and an 8 ft SPF 2x10 (loft-wire's
#: test_price_book.py B7 book): (material, profile, stock ft or sheet, cents).
BOOK = PriceBookResponse.model_validate(
    {
        "currency": "USD",
        "entries": [
            {"material": m, "profile": p, "unit": "each", **stock, "price_cents": c}
            for m, p, stock, c in [
                (SPF, "us_2x10", {"stock_length_ft": 16}, 2297),
                (PT, "us_2x6", {"stock_length_ft": 16}, 1698),
                (PLY_M, "plywood_23_32", {"sheet": "4x8"}, 4250),
                (SPF, "us_2x6", {"stock_length_ft": 8}, 648),
                (PT, "us_2x6", {"stock_length_ft": 12}, 1248),
                (OSB_M, "osb_7_16", {"sheet": "4x9"}, 2498),
                (SPF, "us_2x6", {"stock_length_ft": 16}, 1398),
                (SPF, "us_2x8", {"stock_length_ft": 12}, 1347),
                (SPF, "us_2x10", {"stock_length_ft": 8}, 1147),
            ]
        ],
    }
)


def _cut_list() -> Any:
    request = _request()
    return cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B7",
        length_unit="in",
        pieces=part_pieces(_extents(request), _members(), request.materials),
        price_book=BOOK,
    )


def _stock(line: Any) -> str:
    """The stock cell as house-b7.spec.ts reads it."""
    if line.sheet:
        return f"{line.stock_quantity} x {line.sheet}"
    pieces = list(line.stock_pieces_ft or [])
    if len(pieces) > 1 and len(set(pieces)) == 1:
        return f"{len(pieces)} x {pieces[0]} ft"
    if pieces:
        return " + ".join(f"{p} ft" for p in pieces)
    return "-"


def test_the_cut_list_is_the_rounds_and_prices_to_the_same_total() -> None:
    cut_list = _cut_list()
    rows = [
        (
            line.member,
            line.quantity,
            round((line.area_mm2 or 0) / IN**2, 6)
            if line.sheet
            else round(line.length_mm / IN, 4),
            _stock(line),
        )
        for line in cut_list.lines
    ]
    assert rows == [
        (m, q, round(v, 6) if m in ("Subfloor", "Sheathing") else v, s)
        for m, q, v, s in HOUSE
    ]
    assert (
        sum(line.quantity for line in cut_list.lines if line.sheet is None)
        == 217 - 14 - 24
    )
    # The 18 short lines: 19 x 22.97 + 4 x 16.98 + 12 x 42.50 + 114 x 6.48 +
    # 2 x 12.48 + 17 x 24.98 + 4 x 13.98 + 26 x 13.47 = 2 608.83; the splices:
    # rims 2 x (22.97 + 11.47), sills 2 x 2 x 12.48, top plates 4 x (13.98 +
    # 6.48), bottom plate 2 x 12.48, ridge 22.97 + 11.47 = 260.04. The
    # round's $2,868.87 to the last line (house-b7.spec.ts PRICE).
    short = (
        19 * 2297
        + 4 * 1698
        + 12 * 4250
        + 114 * 648
        + 2 * 1248
        + 17 * 2498
        + 4 * 1398
        + 26 * 1347
    )
    splices = 2 * 3444 + 2 * 2496 + 4 * 2046 + 2496 + 3444
    assert (short, splices) == (260883, 26004)
    assert cut_list.total_price_cents == short + splices == 286887
    assert cut_list.unpriced_lines == 0
    assert cut_list.unclassified == 0
    total = cut_list_csv(cut_list).split("\r\n")
    assert ",Total,,,,,,,,,,,,,,2868.87" in total


# --- Mass ---------------------------------------------------------------------------


def test_every_body_weighs_by_its_member_material() -> None:
    request = _request()
    assert request.materials is not None and request.materials.default_material is None
    response = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    want = sum(
        float(measure_shape(m.solid).volume) * DENSITY[m.material] * 1e-6
        for m in script()
    )
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


# --- 4. The edits and the other outlines --------------------------------------------


def _cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(gzip.decompress(CASES.read_bytes()))
    return cases


@pytest.mark.parametrize("case", _cases(), ids=[c["name"] for c in _cases()])
def test_each_outline_case_builds_valid_with_no_interference(
    case: dict[str, Any],
) -> None:
    """B7 at 336 (234 solids, the script's), B2 on an outline (its gable),
    an L on 2x4 outline walls with a hip, and a gable along Y off the origin
    whose tails are notched out of the side walls' OSB and corner rips."""
    request = EvaluateTreeRequest.model_validate(case["request"])
    solids: list[Solid] = list(build_model_solid(request).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    assert len(solids) == case["bodies"]
    assert all(s.is_valid for s in solids)
    assert _overlapping(solids) == []
    if case["name"] == "b7-336":
        assert len(solids) == 234
        mine = script(336)
        assert _unmatched(solids, [m.solid for m in mine]) == []
        volume = sum(float(measure_shape(s).volume) for s in solids) / IN**3
        assert volume == pytest.approx(analytic_volume(336), abs=1e-4)


# --- 5. Openings measured from the X 0 end (OPENING-FROM-END) -----------------------

FROM_END = "b7-front-wall-from-end"


@pytest.fixture(scope="module")
def from_end_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return _step_solids(tmp_path_factory, FROM_END)


def test_from_the_end_the_grown_house_with_the_window_moved_is_the_scripts(
    from_end_solids: list[Solid],
) -> None:
    """``b7-front-wall-from-end``: B7's 288 dimension set to 336 and the left
    front window's distance from the X 0 end set 60 -> 84, each one field.
    The script types the openings at X 84, 144 and 228 from the X 0 end."""
    mine = script(336, left=84)
    assert len(from_end_solids) == len(mine) == 234
    assert _unmatched(from_end_solids, [m.solid for m in mine]) == []
    volume = sum(float(measure_shape(s).volume) for s in from_end_solids) / IN**3
    assert volume == pytest.approx(analytic_volume(336, left=84), abs=1e-4)
    assert _overlapping(from_end_solids) == []


# --- 6. Window and door units (OPENING-UNITS) -------------------------------------

UNITS = "b7-units"


@pytest.fixture(scope="module")
def units_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return _step_solids(tmp_path_factory, UNITS)


def test_with_its_units_the_house_is_the_scripts_and_nothing_interferes(
    units_solids: list[Solid],
) -> None:
    """``b7-units``: every opening picked by size and its unit drawn. The
    STEP's 229 solids are the script's (b7-outline's 217 and 12 unit
    bodies), the volume b7-outline's plus 12 064.5 in^3, and no unit body
    touches a framing member, panel or rafter."""
    mine = script(units=True)
    assert len(units_solids) == len(mine) == 229
    assert _unmatched(units_solids, [m.solid for m in mine]) == []
    assert units_volume() == Fraction(24129, 2)
    volume = sum(float(measure_shape(s).volume) for s in units_solids) / IN**3
    assert volume == pytest.approx(analytic_volume(288, units=True), abs=1e-4)
    assert _overlapping(units_solids) == []


#: B7's book and its units: a vinyl 3040 $289.00, a vinyl 2030 $189.00 and a
#: 3068 prehung door $449.00 (wood frame).
UNIT_BOOK = PriceBookResponse.model_validate(
    {
        "currency": "USD",
        "entries": [
            *(e.model_dump(mode="json") for e in BOOK.entries),
            *(
                {"material": m, "profile": k, "unit": "each", "price_cents": c}
                for m, k, c in [
                    (PVC, "window_3040", 28900),
                    (PVC, "window_2030", 18900),
                    (SPF, "door_3068", 44900),
                ]
            ),
        ],
    }
)


def test_each_unit_is_one_priced_line_and_the_lumber_is_unchanged() -> None:
    request = _request(UNITS)
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / UNITS / "members.json").read_text()
    )
    members = [CutListMember.model_validate(item) for item in raw]
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B7",
        length_unit="in",
        pieces=part_pieces(_extents(request), members, request.materials),
        price_book=UNIT_BOOK,
    )
    units = [line for line in cut_list.lines if line.unit is not None]
    assert [
        (u.member, u.profile, u.quantity, u.unit_key, u.extended_price_cents)
        for u in units
    ] == [
        ("Door", "3068", 1, "door_3068", 44900),
        ("Window", "3040", 3, "window_3040", 3 * 28900),
        ("Window", "2030", 2, "window_2030", 2 * 18900),
    ]
    lumber = [line for line in cut_list.lines if line.unit is None]
    assert [(line.member, line.quantity) for line in lumber] == [
        (m, q) for m, q, _, _ in HOUSE
    ]
    # The round's $2,868.87 plus the units: 449 + 3 x 289 + 2 x 189.
    assert cut_list.total_price_cents == 286887 + 44900 + 86700 + 37800 == 456287
    assert cut_list.unpriced_lines == 0
    assert ",Total,,,,,,,,,,,,,4562.87" in cut_list_csv(cut_list).split("\r\n")


def test_with_its_units_every_body_weighs_by_its_material() -> None:
    request = _request(UNITS)
    response = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    want = sum(
        float(measure_shape(m.solid).volume) * DENSITY[m.material] * 1e-6
        for m in script(units=True)
    )
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


# --- expected.json's numbers ---------------------------------------------------------


def expected_numbers(
    length: float = 288.0, left: float = 60.0, units: bool = False
) -> dict[str, Any]:
    """A golden's mass properties, topology and mesh counts from the script
    (B7 at *length*, the left front window at X *left*): volume analytic,
    the rest measured on the script's solids; a planar face of n vertices on
    h holes meshes as n + 2h - 2 triangles."""
    mine = script(length, left, units)
    volume = analytic_volume(length, left=left, units=units) * IN**3
    area = sum(float(measure_shape(m.solid).surface_area) for m in mine)
    moments = [0.0, 0.0, 0.0]
    mass = 0.0
    mass_moments = [0.0, 0.0, 0.0]
    vertices = triangles = faces = edges = 0
    for m in mine:
        props = measure_shape(m.solid)
        v = float(props.volume)
        c = props.centroid
        for k, value in enumerate((c.x, c.y, c.z)):
            moments[k] += v * value
            mass_moments[k] += v * DENSITY[m.material] * 1e-6 * value
        mass += v * DENSITY[m.material] * 1e-6
        faces += len(m.solid.faces())
        edges += len(m.solid.edges())
        for face in m.solid.faces():
            loops = face.wires()
            n = sum(len(w.edges()) for w in loops)
            vertices += n
            triangles += n + 2 * (len(loops) - 1) - 2
    total = sum(float(measure_shape(m.solid).volume) for m in mine)
    bb = [m.solid.bounding_box() for m in mine]
    return {
        "volume": volume,
        "surface_area": area,
        "centroid": [x / total for x in moments],
        "mass_g": mass,
        "center_of_mass": [x / mass for x in mass_moments],
        "bbox": [
            min(b.min.X for b in bb),
            min(b.min.Y for b in bb),
            min(b.min.Z for b in bb),
            max(b.max.X for b in bb),
            max(b.max.Y for b in bb),
            max(b.max.Z for b in bb),
        ],
        "topology": {"faces": faces, "edges": edges, "shells": len(mine)},
        "mesh": {"vertices": vertices, "triangles": triangles},
    }


if __name__ == "__main__":
    # ``b7-outline``: no arguments; ``b7-front-wall-from-end``: ``336 84``;
    # ``b7-units``: ``288 60 units``.
    args = [float(a) for a in sys.argv[1:3]]
    with_units = sys.argv[3:4] == ["units"]
    json.dump(expected_numbers(*args, units=with_units), sys.stdout, indent=2)
    sys.stdout.write("\n")
