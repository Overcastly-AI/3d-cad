"""CASEWORK acceptance: ``loft.cabinets`` 1.0.0's C1-C3 on the kernel and STEP.

The goldens ``c1-*``, ``c2-*`` and ``c3-*`` are the plugin's expansions,
pinned to it by ``packages/loft-plugins/tests/test_cabinets.py``. Checked here
against panels typed from ``docs/reference-parts/casework.md`` (C1's table)
and this module's independent script of its conventions (:func:`spec`),
never from the plugin:

1. each golden's exported STEP is the spec solid for solid (volume and
   bounds), its volume the spec's to 1e-4 in^3, and no two solids overlap;
2. the cut list lists C1's panels by sheet (with kerf, grain and no panel
   gap), 23.54 ft of banding, 2 hinges and a pair of 22 in slides, under
   Casework;
3. C3 prices to the last line, its total the lines summed by hand;
4. C2's runs on B7's left wall touch nothing of the house;
5. a run turned 30 degrees is C1's volume (the turned-plane sides).

``expected.json`` of each golden is written from :func:`spec` by
``uv run python services/geometry/tests/test_casework.py`` (exact rational
sums, ``x 25.4`` = mm exactly); the tolerances are measured.
"""

import itertools
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from build123d import Solid, import_step  # pyright: ignore[reportUnknownVariableType]
from fastapi.testclient import TestClient
from geometry.kernel import measure_shape
from geometry.kernel.interference import probe_overlap
from geometry.main import app
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMember,
    CutListResponse,
    cut_list_response,
    part_pieces,
)
from loft_wire.features import EvaluateTreeRequest, ExportTreeRequest
from loft_wire.price_book import EMPTY_PRICE_BOOK, PriceBookEntry, PriceBookResponse

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
IN = 25.4
IN_F = Fraction(254, 10)

Bounds = tuple[float, float, float, float, float, float]  # x0, x1, y0, y1, z0, z1

#: Library densities (kg/m^3), loft_wire.materials: plywood 36 pcf, melamine
#: particleboard 45 pcf, white oak G 0.73 at 12 %.
DENSITY = {"plywood": 577, "melamine": 721, "white_oak": 759}


# --- The independent script --------------------------------------------------------


@dataclass(frozen=True)
class Spec:
    """One panel (in): its box, its material, and a notched side's toe notch
    (a box through the side's thickness at its front bottom corner, taken
    out of it)."""

    role: str
    box: Bounds
    material: str
    notch: Bounds | None = None

    def boxes(self) -> list[tuple[Bounds, int]]:
        """The panel as signed boxes: itself, less its notch."""
        if self.notch is None:
            return [(self.box, 1)]
        return [(self.box, 1), (self.notch, -1)]


def _carcass(
    W: float, D: float, H: float, toe: float, z: float, top: str, band: str, m: str
) -> list[Spec]:
    """Sides, back, bottom, top or stretchers, toe kick (casework.md)."""
    t = 0.75
    out = [
        Spec(
            "side",
            (x0, x0 + t, 0, D, z, z + H),
            m,
            (x0, x0 + t, D - 3, D, 0, toe) if toe else None,
        )
        for x0 in (0, W - t)
    ]
    out += [
        Spec("back", (t, W - t, 0, t, z + toe, z + H), m),
        Spec("bottom", (t, W - t, t, D, z + toe, z + toe + t), m),
    ]
    if top == "stretchers":
        out += [
            Spec("stretcher", (t, W - t, D - 4, D, z + H - t, z + H), m),
            Spec("stretcher", (t, W - t, t, t + 4, z + H - t, z + H), m),
        ]
    else:
        out.append(Spec("top", (t, W - t, t, D, z + H - t, z + H), m))
    if toe:
        out.append(Spec("toe_kick", (t, W - t, D - 3 - t, D - 3, 0, toe), m))
    del band
    return out


def _shelves(W: float, D: float, z0: float, z1: float, n: int, m: str) -> list[Spec]:
    """n shelves, equal clear gaps from z0 to z1, 1/32 off each side, 1 in
    back from the front."""
    gap = (z1 - z0 - n * 0.75) / (n + 1)
    return [
        Spec(
            "shelf",
            (
                0.78125,
                W - 0.78125,
                0.75,
                D - 1,
                z0 + gap * (k + 1) + 0.75 * k,
                z0 + gap * (k + 1) + 0.75 * (k + 1),
            ),
            m,
        )
        for k in range(n)
    ]


def _drawer(
    x0: float, x1: float, y1: float, length: float, z0: float, z1: float
) -> list[Spec]:
    """A 1/2 plywood box, sides z0..z1, on a 1/4 bottom under them."""
    y0 = y1 - length
    return [
        Spec("drawer_side", (x0, x0 + 0.5, y0, y1, z0, z1), "plywood"),
        Spec("drawer_side", (x1 - 0.5, x1, y0, y1, z0, z1), "plywood"),
        Spec("drawer_end", (x0 + 0.5, x1 - 0.5, y1 - 0.5, y1, z0, z1), "plywood"),
        Spec("drawer_end", (x0 + 0.5, x1 - 0.5, y0, y0 + 0.5, z0, z1), "plywood"),
        Spec("drawer_bottom", (x0, x1, y0, y1, z0 - 0.25, z0), "plywood"),
    ]


def _front(
    role: str, x0: float, x1: float, y: float, z0: float, z1: float, m: str
) -> Spec:
    return Spec(role, (x0, x1, y, y + 0.75, z0, z1), m)


def _two(W: float, edge: float) -> list[tuple[float, float]]:
    """Two doors meeting 1/8 apart at the middle."""
    return [(edge, W / 2 - 1 / 16), (W / 2 + 1 / 16, W - edge)]


def b24(W: float = 24, m: str = "plywood") -> list[Spec]:
    """C1 frameless at width W: casework.md's table."""
    out = _carcass(W, 24, 34.5, 4.5, 0, "stretchers", "", m)
    out += _shelves(W, 24, 5.25, 28.5, 1, m)
    out += [
        _front("drawer_front", 1 / 16, W - 1 / 16, 24, 28.4375, 34.4375, m),
        _front("door", 1 / 16, W - 1 / 16, 24, 4.5625, 28.3125, m),
    ]
    return out + _drawer(1.25, W - 1.25, 24, 22, 29, 33)


def b24_face_frame() -> list[Spec]:
    """C1 with a 1x2 frame: openings 5 (drawer) and 20.5 (door) between
    1-1/2 rails, fronts 1/2 over them."""
    m, oak = "plywood", "white_oak"
    out = _carcass(24, 24, 34.5, 4.5, 0, "stretchers", "", m)
    out += _shelves(24, 24, 5.25, 26.5, 1, m)
    out += [
        Spec("stile", (0, 1.5, 24, 24.75, 4.5, 34.5), oak),
        Spec("stile", (22.5, 24, 24, 24.75, 4.5, 34.5), oak),
        Spec("rail", (1.5, 22.5, 24, 24.75, 33, 34.5), oak),
        Spec("rail", (1.5, 22.5, 24, 24.75, 26.5, 28), oak),
        Spec("rail", (1.5, 22.5, 24, 24.75, 4.5, 6), oak),
        _front("drawer_front", 1, 23, 24.75, 27.5, 33.5, m),
        _front("door", 1, 23, 24.75, 5.5, 27, m),
    ]
    return out + _drawer(2, 22, 24, 22, 28.75, 32.5)


def v3021(face_frame: bool) -> list[Spec]:
    """C3: 30 x 21 x 34.5, a 6 in false front over two doors, no shelf."""
    m = "melamine"
    out = _carcass(30, 21, 34.5, 4.5, 0, "stretchers", "", m)
    if not face_frame:
        out.append(_front("false_front", 1 / 16, 30 - 1 / 16, 21, 28.4375, 34.4375, m))
        out += [
            _front("door", a, b, 21, 4.5625, 28.3125, m) for a, b in _two(30, 1 / 16)
        ]
        return out
    oak = "white_oak"
    out += [
        Spec("stile", (0, 1.5, 21, 21.75, 4.5, 34.5), oak),
        Spec("stile", (28.5, 30, 21, 21.75, 4.5, 34.5), oak),
        Spec("rail", (1.5, 28.5, 21, 21.75, 33, 34.5), oak),
        Spec("rail", (1.5, 28.5, 21, 21.75, 26.5, 28), oak),
        Spec("rail", (1.5, 28.5, 21, 21.75, 4.5, 6), oak),
        _front("false_front", 1, 29, 21.75, 27.5, 33.5, m),
    ]
    return out + [_front("door", a, b, 21.75, 5.5, 27, m) for a, b in _two(30, 1)]


def c2_base() -> list[Spec]:
    """C2's base run from its start (the back wall's face), boxes side by
    side: a 3.5 filler, T1884, DB24, B27, SB36, B24."""
    m = "plywood"
    out: list[Spec] = [_front("filler", 0, 3.5, 24, 4.5, 84, m)]
    # T1884: a full top, one shelf in its 5.25..83.25 bay, stacked doors
    # split in line with a base box's door top (28.3125).
    tall = _carcass(18, 24, 84, 4.5, 0, "top", "", m) + _shelves(
        18, 24, 5.25, 83.25, 1, m
    )
    tall += [
        _front("door", 1 / 16, 18 - 1 / 16, 24, 28.4375, 83.9375, m),
        _front("door", 1 / 16, 18 - 1 / 16, 24, 4.5625, 28.3125, m),
    ]
    # DB24: three drawers, 6 on top and two of 11.8125; each box's top 3/4
    # under its opening's (the stretchers' underside for the top drawer).
    db = _carcass(24, 24, 34.5, 4.5, 0, "stretchers", "", m)
    db += [
        _front("drawer_front", 1 / 16, 24 - 1 / 16, 24, 28.4375, 34.4375, m),
        _front("drawer_front", 1 / 16, 24 - 1 / 16, 24, 16.5, 28.3125, m),
        _front("drawer_front", 1 / 16, 24 - 1 / 16, 24, 4.5625, 16.375, m),
    ]
    db += _drawer(1.25, 22.75, 24, 22, 29, 33)
    db += _drawer(1.25, 22.75, 24, 22, 17.8125, 27.625)
    db += _drawer(1.25, 22.75, 24, 22, 5.875, 15.6875)
    # SB36: a false front over two doors, no shelf.
    sb = _carcass(36, 24, 34.5, 4.5, 0, "stretchers", "", m)
    sb.append(_front("false_front", 1 / 16, 36 - 1 / 16, 24, 28.4375, 34.4375, m))
    sb += [_front("door", a, b, 24, 4.5625, 28.3125, m) for a, b in _two(36, 1 / 16)]
    x = 3.5
    for box, width in ((tall, 18), (db, 24), (b24(27), 27), (sb, 36), (b24(24), 24)):
        out += [_moved(s, x) for s in box]
        x += width
    return out


def c2_wall() -> list[Spec]:
    """W2430 and W2730 from 21.5 in along: 12 deep, 30 high, bottom 54,
    two shelves each (9 in clear gaps), one full-height door each."""
    m = "plywood"
    out: list[Spec] = []
    x = 21.5
    for width in (24, 27):
        box = _carcass(width, 12, 30, 0, 54, "top", "", m)
        box += _shelves(width, 12, 54.75, 83.25, 2, m)
        box.append(_front("door", 1 / 16, width - 1 / 16, 12, 54.0625, 83.9375, m))
        out += [_moved(s, x) for s in box]
        x += width
    return out


def _map(s: Spec, f: Callable[[Bounds], Bounds]) -> Spec:
    """*s* with its box and notch mapped by *f* (a box to a box)."""
    return Spec(s.role, f(s.box), s.material, None if s.notch is None else f(s.notch))


def _moved(s: Spec, dx: float) -> Spec:
    return _map(s, lambda b: (b[0] + dx, b[1] + dx, b[2], b[3], b[4], b[5]))


#: B7's left wall: its inside face at X 5.5, a 1/2 in gypsum gap, the run
#: from the back wall's face (Y 186.5) toward the front, on the subfloor.
SUBFLOOR = 1.5 + 9.25 + 23 / 32


def _on_b7(s: Spec) -> Spec:
    """Run frame -> world: X = 6 + y, Y = 186.5 - x, Z on the subfloor."""
    return _map(
        s,
        lambda b: (
            6 + b[2],
            6 + b[3],
            186.5 - b[1],
            186.5 - b[0],
            SUBFLOOR + b[4],
            SUBFLOOR + b[5],
        ),
    )


def _shifted(specs: list[Spec], dx: float, dy: float) -> list[Spec]:
    return [
        _map(s, lambda b: (b[0] + dx, b[1] + dx, b[2] + dy, b[3] + dy, b[4], b[5]))
        for s in specs
    ]


def spec(name: str) -> list[Spec]:
    """The independent script's panels for each golden, in the world (in)."""
    if name == "c1-b24-frameless-casework":
        return b24()
    if name == "c1-b27-frameless-casework":
        return b24(27)
    if name == "c1-b24-face-frame-casework":
        return b24_face_frame()
    if name == "c2-kitchen-b7-left-wall":
        return [_on_b7(s) for s in c2_base() + c2_wall()]
    if name == "c3-v3021-melamine-frameless":
        return _shifted(v3021(False), 12, 24)
    if name == "c3-v3021-melamine-face-frame":
        return _shifted(v3021(True), 12, 24)
    raise KeyError(name)


#: C1 turned 30 degrees about (12, 24).
TURNED = "c1-b24-turned-30-casework"
TURN_DEG, TURN_AT = 30.0, (12.0, 24.0)

NAMES = (
    "c1-b24-frameless-casework",
    "c1-b27-frameless-casework",
    "c1-b24-face-frame-casework",
    "c2-kitchen-b7-left-wall",
    "c3-v3021-melamine-frameless",
    "c3-v3021-melamine-face-frame",
)


def _fr(v: float) -> Fraction:
    return Fraction(v)


def volume_in3(specs: list[Spec]) -> Fraction:
    total = Fraction(0)
    for s in specs:
        for (x0, x1, y0, y1, z0, z1), sign in s.boxes():
            total += (
                sign * (_fr(x1) - _fr(x0)) * (_fr(y1) - _fr(y0)) * (_fr(z1) - _fr(z0))
            )
    return total


@dataclass(frozen=True)
class Derived:
    volume: Fraction
    area: Fraction
    centroid: tuple[Fraction, Fraction, Fraction]
    mass_g: Fraction
    com: tuple[Fraction, Fraction, Fraction]
    bounds: Bounds
    faces: int
    edges: int
    shells: int
    vertices: int
    triangles: int


def derive(specs: list[Spec]) -> Derived:
    """Exact sums over the spec's panels (in, then x 25.4 = mm): each panel
    a box, a notched side its box less the notch. A side's area is its
    box's less the notch's two faces in the side's plane (its perimeter, the
    notch at a corner, is the box's): the notch's volume over the side's
    thickness, twice. A
    box is 6 faces, 12 edges, 24 mesh vertices and 12 triangles; an L prism
    8 faces, 18 edges, 36 vertices (two hexagons, six quads) and 20
    triangles (4 per hexagon, 2 per quad)."""
    vol = area = mass = Fraction(0)
    moment = [Fraction(0)] * 3
    mass_moment = [Fraction(0)] * 3
    faces = edges = verts = tris = 0
    for s in specs:
        x0, x1, y0, y1, z0, z1 = (_fr(v) for v in s.box)
        a, b, c = x1 - x0, y1 - y0, z1 - z0
        if s.notch is None:
            area += 2 * (a * b + b * c + c * a)
            faces, edges, verts, tris = faces + 6, edges + 12, verts + 24, tris + 12
        else:
            n = [_fr(v) for v in s.notch]
            notch = (n[1] - n[0]) * (n[3] - n[2]) * (n[5] - n[4]) / min(a, b, c)
            area += 2 * (a * b + b * c + c * a) - 2 * notch
            faces, edges, verts, tris = faces + 8, edges + 18, verts + 36, tris + 20
        rho = Fraction(DENSITY[s.material])
        for (bx0, bx1, by0, by1, bz0, bz1), sign in s.boxes():
            p = [_fr(v) for v in (bx0, bx1, by0, by1, bz0, bz1)]
            v = sign * (p[1] - p[0]) * (p[3] - p[2]) * (p[5] - p[4])
            centre = ((p[0] + p[1]) / 2, (p[2] + p[3]) / 2, (p[4] + p[5]) / 2)
            vol += v
            mass += v * rho
            for k in range(3):
                moment[k] += v * centre[k]
                mass_moment[k] += v * rho * centre[k]
    mm3 = IN_F**3
    xs = [v for s in specs for v in s.box[0:2]]
    ys = [v for s in specs for v in s.box[2:4]]
    zs = [v for s in specs for v in s.box[4:6]]
    return Derived(
        volume=vol * mm3,
        area=area * IN_F**2,
        centroid=(
            moment[0] / vol * IN_F,
            moment[1] / vol * IN_F,
            moment[2] / vol * IN_F,
        ),
        # kg/m^3 x mm^3 = 1e-9 kg = 1e-6 g.
        mass_g=mass * mm3 / 10**6,
        com=tuple(mass_moment[k] / mass * IN_F for k in range(3)),  # type: ignore[arg-type]
        bounds=(
            min(xs) * IN,
            max(xs) * IN,
            min(ys) * IN,
            max(ys) * IN,
            min(zs) * IN,
            max(zs) * IN,
        ),
        faces=faces,
        edges=edges,
        shells=len(specs),
        vertices=verts,
        triangles=tris,
    )


# --- 1. The STEP against the script ------------------------------------------------


def _request(name: str) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )


def _members(name: str) -> list[CutListMember]:
    raw: list[dict[str, Any]] = json.loads(
        (GOLDENS / name / "members.json").read_text()
    )
    return [CutListMember.model_validate(item) for item in raw]


def _step(request: EvaluateTreeRequest, path: Path) -> list[Solid]:
    export = ExportTreeRequest.model_validate(
        {**request.model_dump(mode="json"), "format": "step"}
    )
    response = client.post("/api/v1/export/tree", json=export.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    path.write_bytes(response.content)
    return list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def _signature(solid: Solid) -> tuple[float, ...]:
    bb = solid.bounding_box()
    values = (bb.min.X, bb.max.X, bb.min.Y, bb.max.Y, bb.min.Z, bb.max.Z)
    return (float(measure_shape(solid).volume) / IN**3, *(v / IN for v in values))


def _spec_signature(s: Spec) -> tuple[float, ...]:
    return (float(volume_in3([s])), *s.box)


def _unmatched(
    got: list[tuple[float, ...]], want: list[tuple[float, ...]]
) -> list[Any]:
    left = list(want)
    missing: list[Any] = []
    for sig in got:
        k = next(
            (
                k
                for k, other in enumerate(left)
                if abs(sig[0] - other[0]) <= 1e-6
                and all(
                    abs(a - b) <= 1e-6 for a, b in zip(sig[1:], other[1:], strict=True)
                )
            ),
            None,
        )
        if k is None:
            missing.append(sig)
        else:
            left.pop(k)
    return missing + left


def _overlapping(
    solids: list[Solid], only: set[int] | None = None
) -> list[tuple[int, int]]:
    boxes = [s.bounding_box() for s in solids]
    bad: list[tuple[int, int]] = []
    for i, j in itertools.combinations(range(len(solids)), 2):
        if only is not None and i not in only and j not in only:
            continue
        a, b = boxes[i], boxes[j]
        if all(
            min(getattr(a.max, k), getattr(b.max, k))
            - max(getattr(a.min, k), getattr(b.min, k))
            > 1e-6
            for k in ("X", "Y", "Z")
        ):
            probe = probe_overlap(solids[i], solids[j])
            if probe.unresolved or probe.volume_mm3 != 0.0:
                bad.append((i, j))
    return bad


def test_the_script_is_casework_md() -> None:
    """C1 3 526.66796875 in^3 (widened 3 820.10546875), as casework.md
    states; the face frame and C3 are the sums worked in test_cabinets."""
    assert volume_in3(b24()) == Fraction(3526_66796875, 10**8)
    assert volume_in3(b24(27)) == Fraction(3820_10546875, 10**8)
    assert float(volume_in3(b24_face_frame())) == 3561.58203125
    assert float(volume_in3(v3021(False))) == 3072.140625
    assert len(c2_base()) == 1 + 9 + 25 + 15 + 10 + 15
    assert len(c2_wall()) == 2 * 8


@pytest.mark.parametrize("name", NAMES)
def test_the_step_is_the_script_and_nothing_overlaps(name: str, tmp_path: Path) -> None:
    solids = _step(_request(name), tmp_path / f"{name}.step")
    specs = spec(name)
    assert len(solids) == len(specs)
    assert (
        _unmatched([_signature(s) for s in solids], [_spec_signature(s) for s in specs])
        == []
    )
    total = sum(float(measure_shape(s).volume) for s in solids) / IN**3
    assert total == pytest.approx(float(volume_in3(specs)), abs=1e-4)
    assert _overlapping(solids) == []


# --- 2. The cut list -----------------------------------------------------------------


def _cut_list(name: str, book: PriceBookResponse = EMPTY_PRICE_BOOK) -> CutListResponse:
    request = _request(name)
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    extents = BodyExtentsResult.model_validate_json(response.content)
    return cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name=name,
        length_unit="in",
        pieces=part_pieces(extents, _members(name), request.materials),
        price_book=book,
    )


def test_c1_lists_panels_by_sheet_banding_and_hardware_under_casework() -> None:
    """3/4 plywood on two 4x8 sheets: grain along each sheet's 96 in, a 1/8
    kerf a cut and no panel gap, the sides (34.5 x 24), the door
    (23.75 x 23.875) and the back (30 x 22.5) leave no room on one sheet's
    96 x 48 for the bottom, shelf, stretchers, toe kick and drawer front
    (worked: sides + door along one 24 in strip use 93 in; the other strip,
    23.875 wide, takes the back, bottom, shelf and drawer front, 81.31 in,
    and the 22.5 in stretchers and toe kick do not fit its 14.56 in left);
    1/2 and 1/4 on one sheet each. Banding 282.4375 in, 24 ft bought."""
    cut = _cut_list("c1-b24-frameless-casework")
    assert {line.system for line in cut.lines} == {"casework"}
    rows = {
        (line.profile, line.sheet, line.quantity, line.stock_quantity)
        for line in cut.lines
        if line.sheet is not None
    }
    assert rows == {
        ("3/4 plywood", "4x8", 10, 2),
        ("1/2 plywood", "4x8", 4, 1),
        ("1/4 plywood", "4x8", 1, 1),
    }
    areas = {
        line.profile: (line.area_mm2 or 0) / IN**2 for line in cut.lines if line.sheet
    }
    assert areas == {
        "3/4 plywood": pytest.approx(4317.890625),
        "1/2 plywood": pytest.approx(340),
        "1/4 plywood": pytest.approx(473),
    }
    items = {
        (line.casework, line.material): line
        for line in cut.lines
        if line.casework is not None
    }
    band = items[("edge_banding", "plywood")]
    assert band.total_length_mm / IN == pytest.approx(282.4375)
    assert round(band.total_length_mm / IN / 12, 2) == 23.54
    assert band.stock_quantity == 24
    assert band.quantity == 7  # 2 sides, bottom, stretcher, shelf, door, drawer front
    assert (
        items[("hinge", "steel_1018")].quantity,
        items[("slide_22", "steel_1018")].quantity,
    ) == (2, 1)
    assert cut.unclassified == 0


def _book(entries: list[tuple[str, str, str, str | None, int]]) -> PriceBookResponse:
    return PriceBookResponse(
        currency="USD",
        entries=[
            PriceBookEntry(material=m, profile=p, unit=u, sheet=s, price_cents=c)  # type: ignore[arg-type]
            for m, p, u, s, c in entries
        ],
    )


C3_BOOK: list[tuple[str, str, str, str | None, int]] = [
    ("melamine", "melamine_3_4", "each", "4x8", 4298),
    ("pvc", "edge_banding", "linear_foot", None, 35),
    ("steel_1018", "hinge", "each", None, 450),
    ("white_oak", "us_1x2", "linear_foot", None, 189),
]


@pytest.mark.parametrize(
    ("name", "sheets", "banding_in", "frame"),
    [
        # 343.25 in of PVC banding: sides 2 x 30, bottom and stretcher 28.5,
        # the false front 2 x 35.875, the doors 4 x 38.625.
        ("c3-v3021-melamine-frameless", 2, 343.25, None),
        # The frame covers the carcass's edges: the false front 2 x 34, the
        # doors 4 x 35.4375; 2 stiles 30 and 3 rails 27, 141 in of 1x2
        # (each piece its own 8 ft stock, priced on the foot bought).
        ("c3-v3021-melamine-face-frame", 2, 209.75, (2, 3)),
    ],
)
def test_c3_prices_to_the_last_line(
    name: str, sheets: int, banding_in: float, frame: tuple[int, int] | None
) -> None:
    cut = _cut_list(name, _book(C3_BOOK))
    assert cut.unpriced_lines == 0
    by = {(line.casework or line.profile): line for line in cut.lines}
    sheet = by["3/4 melamine"]
    assert (sheet.sheet, sheet.stock_quantity) == ("4x8", sheets)
    band = by["edge_banding"]
    assert band.total_length_mm / IN == pytest.approx(banding_in)
    feet = math.ceil(banding_in / 12)
    assert band.stock_quantity == feet
    assert by["hinge"].quantity == 4
    hand = sheets * 4298 + feet * 35 + 4 * 450
    if frame is not None:
        stiles, rails = frame
        lumber = [line for line in cut.lines if line.profile == "1x2"]
        assert sum(line.quantity for line in lumber) == stiles + rails
        # Each 1x2 is one 8 ft piece of stock, priced 8 ft x $1.89.
        hand += (stiles + rails) * 8 * 189
    assert cut.total_price_cents == hand
    assert sum(line.extended_price_cents or 0 for line in cut.lines) == hand


# --- 4. C2 on B7 ---------------------------------------------------------------------


def test_c2_touches_nothing_of_b7(tmp_path: Path) -> None:
    """B7 with its units (b7-units) and C2's two runs as one part: no
    cabinet solid shares volume with another or with any of the house's."""
    house = _request("b7-units")
    runs = _request("c2-kitchen-b7-left-wall")
    assert house.materials is not None and runs.materials is not None
    request = house.model_copy(
        update={
            "features": [*house.features, *runs.features],
            "materials": house.materials.model_copy(
                update={"bodies": [*house.materials.bodies, *runs.materials.bodies]}
            ),
        }
    )
    solids = _step(request, tmp_path / "c2-on-b7.step")
    cabinets = {
        i
        for i, s in enumerate(solids)
        if s.bounding_box().min.X >= 6 * IN - 1e-6
        and s.bounding_box().max.X <= 30.75 * IN + 1e-6
    }
    assert len(cabinets) >= len(spec("c2-kitchen-b7-left-wall"))
    assert _overlapping(solids, cabinets) == []


# --- 5. A run turned 30 degrees ------------------------------------------------------


def test_a_turned_run_is_c1_turned(tmp_path: Path) -> None:
    """C1 on a run turned 30 degrees about (12, 24) (golden
    ``c1-b24-turned-30-casework``): its notched sides on a plane turned
    about Z, every other panel a turned plan rectangle. The STEP is C1's 15
    solids, each of C1's volumes, summing to 3 526.66796875 in^3, and no two
    overlap."""
    solids = _step(_request(TURNED), tmp_path / "turned.step")
    got = sorted(float(measure_shape(s).volume) / IN**3 for s in solids)
    want = sorted(float(volume_in3([p])) for p in b24())
    assert got == pytest.approx(want, abs=1e-6)
    assert sum(got) == pytest.approx(3526.66796875, abs=1e-4)
    assert _overlapping(solids) == []


# --- The goldens' expected.json ----------------------------------------------------


def _turned(point: tuple[float, float]) -> tuple[float, float]:
    """A C1 plan point (in) turned TURN_DEG about the origin, moved to
    TURN_AT."""
    c, s = math.cos(math.radians(TURN_DEG)), math.sin(math.radians(TURN_DEG))
    x, y = point
    return (TURN_AT[0] + x * c - y * s, TURN_AT[1] + x * s + y * c)


def expected(name: str) -> dict[str, Any]:
    if name == TURNED:
        # C1's numbers, its centroids turned and its plan box the extremes
        # of every panel's turned corners (a notched side's plan corners
        # stand above its notch).
        out = expected("c1-b24-frameless-casework")
        for key in ("centroid", "center_of_mass"):
            x, y = _turned((out[key]["x"] / IN, out[key]["y"] / IN))
            out[key] = {**out[key], "x": x * IN, "y": y * IN}
        corners = [
            _turned((p.box[i], p.box[j])) for p in b24() for i in (0, 1) for j in (2, 3)
        ]
        box = out["bounding_box"]
        box["min"] = {
            **box["min"],
            "x": min(c[0] for c in corners) * IN,
            "y": min(c[1] for c in corners) * IN,
        }
        box["max"] = {
            **box["max"],
            "x": max(c[0] for c in corners) * IN,
            "y": max(c[1] for c in corners) * IN,
        }
        return out
    d = derive(spec(name))

    def point(c: tuple[Fraction, Fraction, Fraction]) -> dict[str, float]:
        return {"x": float(c[0]), "y": float(c[1]), "z": float(c[2])}

    return {
        "volume": float(d.volume),
        "surface_area": float(d.area),
        "centroid": point(d.centroid),
        "mass_g": float(d.mass_g),
        "center_of_mass": point(d.com),
        "bounding_box": {
            "min": {"x": d.bounds[0], "y": d.bounds[2], "z": d.bounds[4]},
            "max": {"x": d.bounds[1], "y": d.bounds[3], "z": d.bounds[5]},
        },
        "topology": {"faces": d.faces, "edges": d.edges, "shells": d.shells},
        "mesh": {"vertices": d.vertices, "triangles": d.triangles},
    }


if __name__ == "__main__":
    print(json.dumps({name: expected(name) for name in (*NAMES, TURNED)}, indent=1))
