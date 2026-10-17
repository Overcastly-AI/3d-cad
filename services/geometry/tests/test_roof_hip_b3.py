"""ROOF-HIP acceptance: B3's hip roof from one ``loft.roof`` 1.1.0 feature.

``goldens/b3-hip-6-12`` and ``b3-hip-8-12`` are the plugin's expansion
(``model.json``, member materials applied as documents sends them) and each
member's metadata (``members.json``), pinned to the plugin by
``packages/loft-plugins/tests/test_roof_hip.py``. Geometry never learns
plugins exist, so this module reads JSON only. Checked against
``docs/reference-parts/buildings.md`` B3 and an INDEPENDENT build123d script
(:func:`script_hip_roof`), which models every member another way: its plan
outline as a vertical prism, cut to the slab between its bottom and top
planes, less the seat (all below the plate inside the walls' faces):

1. the cut list, measured from the bodies, is buildings.md B3's;
2. line lengths measured on the exported STEP's faces: commons 79.660, jacks
   52.480 and 25.647 (26.833 apart), hips 106.875 on the centreline, the
   hip's top 0.265 below the ridge's (dropped) and its heel 3.556;
3. the STEP's solids are the script's to 1e-4 (each pair's symmetric
   difference), and none interferes with another or with B2's walls;
4. the overlap sweep: other spans, lengths, pitches, spacings, overhangs and
   sizes (``tests/fixtures/roof-hip-sweep.json.gz``, pinned to the plugin the
   same way) build one solid per member, none overlapping (touching only),
   the float-coincidence class the DECK review found;
5. the STEP round trip's drift is OCCT's: the script's own solids drift the
   same through build123d's STEP (ROOF-TWIN-DRIFT-TEST, both roofs).
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
SWEEP = Path(__file__).resolve().parent / "fixtures" / "roof-hip-sweep.json.gz"
IN = 25.4
R2 = math.sqrt(2)
#: Golden -> rise per 12.
RISES = {"b3-hip-6-12": 6, "b3-hip-8-12": 8}
#: buildings.md B3 and its 8/12 edit: common, long jack, short jack, hip line
#: lengths (in), the jacks' difference, the hip's drop, and the roof's volume.
SPEC: dict[str, dict[str, float]] = {
    "b3-hip-6-12": {
        "common": 79.660,
        "jack_long": 52.480,
        "jack_short": 25.647,
        "decrement": 26.833,
        "hip": 106.875,
        "drop": 0.265,
        "volume": 13790.758,
    },
    "b3-hip-8-12": {
        "common": 85.632,
        "jack_long": 56.414,
        "jack_short": 27.570,
        "decrement": 28.844,
        "hip": 111.397,
        "drop": 0.354,
        "volume": 14711.255,
    },
}

each_roof = pytest.mark.parametrize("name", sorted(RISES))


# --- The independent script ------------------------------------------------------


def script_hip_roof(rise: int) -> list[Solid]:
    """B3's roof from buildings.md alone. Walls' outer faces X 0..144, Y
    0..120, plates at Z 97.125 and 3.5 deep; 2x6 commons and jacks, 2x8
    ridge and hips, 12 in level overhang. Each member: its plan outline as
    a prism, cut to the slab between its bottom and top planes, less every
    point below the plate inside the walls' outer faces."""
    length, span, plate, plate_w, overhang = 144.0, 120.0, 97.125, 3.5, 12.0
    k = rise / 12
    seat = min(plate_w, 5.5 / 3 / k)
    plumb = 5.5 * math.hypot(12, rise) / 12
    top0 = plate + plumb - seat * k  # the planes' height at the walls' faces
    face = span / 2 - 0.75  # the ridge's face, and its ends' inside corners
    half_hip = 0.75 * R2  # a hip's half thickness, along a wall

    def prism(points: Sequence[tuple[float, float]]) -> Solid:
        polygon = Polygon(*[(x * IN, y * IN) for x, y in points], align=None)
        return extrude(polygon, 400 * IN, dir=(0, 0, 1)).solid()

    def slab(
        origin: tuple[float, float, float], gx: float, gy: float, h: float
    ) -> Solid:
        """Between z = f and z = f - h, f the plane through *origin* rising
        gx per X and gy per Y."""
        normal = Vector(-gx, -gy, 1).normalized()
        top = Plane(origin=tuple(c * IN for c in origin), z_dir=normal)
        thick = h * normal.Z * IN
        return (top.location * Pos(0, 0, -thick / 2) * Box(1e4, 1e4, thick)).solid()

    def below_plate(x0: float, x1: float, y0: float, y1: float) -> Solid:
        box = Box((x1 - x0) * IN, (y1 - y0) * IN, plate * IN)
        return (
            Pos((x0 + x1) / 2 * IN, (y0 + y1) / 2 * IN, plate / 2 * IN) * box
        ).solid()

    def member(
        plan: Sequence[tuple[float, float]],
        plane: tuple[tuple[float, float, float], float, float, float],
        seat_box: tuple[float, float, float, float],
    ) -> Solid:
        origin, gx, gy, h = plane
        common = prism(plan) & slab(origin, gx, gy, h)
        assert common is not None
        body = common - below_plate(*seat_box)
        solids = list(body.solids())
        assert len(solids) == 1
        return solids[0]

    front = ((0.0, 0.0, top0), 0.0, k, plumb)
    back = ((0.0, span, top0), 0.0, -k, plumb)
    left = ((0.0, 0.0, top0), k, 0.0, plumb)
    right = ((length, 0.0, top0), -k, 0.0, plumb)
    inside_front = (-1.0, length + 1, 0.0, span / 2)
    inside_back = (-1.0, length + 1, span / 2, span)
    inside_left = (0.0, length / 2, -1.0, span + 1)
    inside_right = (length / 2, length, -1.0, span + 1)

    solids: list[Solid] = []
    # Commons at X 60 and 84, front and back; kings on Y 60 at each end.
    for x in (60.0, 84.0):
        plan = [
            (x - 0.75, -overhang),
            (x + 0.75, -overhang),
            (x + 0.75, face),
            (x - 0.75, face),
        ]
        solids.append(member(plan, front, inside_front))
        solids.append(member([(a, span - b) for a, b in plan], back, inside_back))
    king = [(-overhang, 59.25), (face, 59.25), (face, 60.75), (-overhang, 60.75)]
    solids.append(member(king, left, inside_left))
    solids.append(member([(length - a, b) for a, b in king], right, inside_right))
    # Jacks 12 and 36 from each corner on each wall, cut at the hip's face.
    for c in (36.0, 12.0):
        local = [
            (c - 0.75, -overhang),
            (c + 0.75, -overhang),
            (c + 0.75, c + 0.75 - half_hip),
            (c - 0.75, c - 0.75 - half_hip),
        ]
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            cx, cy = (0.0 if sx == 1 else length), (0.0 if sy == 1 else span)
            along_x = [(cx + sx * a, cy + sy * d) for a, d in local]
            along_y = [(cx + sx * d, cy + sy * a) for a, d in local]
            solids.append(
                member(
                    along_x,
                    front if sy == 1 else back,
                    inside_front if sy == 1 else inside_back,
                )
            )
            solids.append(
                member(
                    along_y,
                    left if sx == 1 else right,
                    inside_left if sx == 1 else inside_right,
                )
            )
    # Hips: the strip 0.75 either side of the 45 deg line from each corner,
    # boxed by the fascia corner and the ridge's inside corner; top edges in
    # the planes (the centreline 0.265 below at 6/12), 7.25 deep square to it.
    drop = 0.75 * k / R2
    hip_plumb = 7.25 * math.hypot(12 * R2, rise) / (12 * R2)
    hexagon = [
        (-overhang, -overhang),
        (-overhang + half_hip, -overhang),
        (face, face - half_hip),
        (face, face),
        (face - half_hip, face),
        (-overhang, -overhang + half_hip),
    ]
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        cx, cy = (0.0 if sx == 1 else length), (0.0 if sy == 1 else span)
        plan = [(cx + sx * a, cy + sy * b) for a, b in hexagon]
        xs = sorted((cx, cx + sx * 70))
        ys = sorted((cy, cy + sy * 70))
        plane = ((cx, cy, top0 - drop), sx * k / 2, sy * k / 2, hip_plumb)
        solids.append(member(plan, plane, (xs[0], xs[1], ys[0], ys[1])))
    ridge_top = top0 + k * face
    ridge = Pos(72 * IN, 60 * IN, (ridge_top - 3.625) * IN) * Box(
        25.5 * IN, 1.5 * IN, 7.25 * IN
    )
    solids.append(ridge.solid())
    return solids


def walls(span: float, length: float, plate: float, width: float) -> list[Solid]:
    """Four walls as solid envelopes, Z 0..plate (stricter than their
    members: nothing may enter a wall's volume at all)."""

    def box(x0: float, x1: float, y0: float, y1: float) -> Solid:
        return (
            Location(((x0 + x1) / 2 * IN, (y0 + y1) / 2 * IN, plate / 2 * IN))
            * Box((x1 - x0) * IN, (y1 - y0) * IN, plate * IN)
        ).solid()

    return [
        box(0, length, 0, width),
        box(0, length, span - width, span),
        box(0, width, width, span - width),
        box(length - width, length, width, span - width),
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


def _step_solids(name: str, tmp_path: Path) -> list[Solid]:
    request = ExportTreeRequest.model_validate(
        {**_request(name).model_dump(mode="json"), "format": "step"}
    )
    response = client.post("/api/v1/export/tree", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    path = tmp_path / f"{name}.step"
    path.write_bytes(response.content)
    return list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


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


def _by_role(name: str, solids: list[Solid]) -> dict[str, list[Solid]]:
    """The STEP's solids by member, told apart by size alone: a hip is the
    only body 7.25 deep and longer than the ridge; jacks are the 2x6 bodies
    shorter than a common."""
    out: dict[str, list[Solid]] = {"common": [], "jack": [], "hip": [], "ridge": []}
    for solid in solids:
        volume = _volume(solid) / IN**3
        if abs(volume - 277.3125) < 1e-3:
            out["ridge"].append(solid)
        elif volume > 1000:
            out["hip"].append(solid)
        elif volume > (640 if RISES[name] == 6 else 690):
            out["common"].append(solid)
        else:
            out["jack"].append(solid)
    return out


# --- Tests -------------------------------------------------------------------------


@each_roof
def test_the_cut_list_is_buildings_md_b3(name: str) -> None:
    request = _request(name)
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B3 roof",
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
    # Overall lengths, long point to long point: line + depth x rise/12, and
    # a cheek's long point 0.75 x unit/12 more (buildings.md B3's table).
    rise = RISES[name]
    spec = SPEC[name]
    k = rise / 12
    cheek = 0.75 * math.hypot(12, rise) / 12
    hip_overall = spec["hip"] + 7.25 * k / R2
    want = [
        ("Common", "2x6", 6, spec["common"] + 5.5 * k, 8),
        ("Jack", "2x6", 8, spec["jack_long"] + 5.5 * k + cheek, 8),
        ("Jack", "2x6", 8, spec["jack_short"] + 5.5 * k + cheek, 8),
        ("Hip", "2x8", 4, hip_overall, 10),
        ("Ridge", "2x8", 1, 25.5, 8),
    ]
    assert len(rows) == len(want)
    for got, expected in zip(rows, want, strict=True):
        assert got[:3] == expected[:3] and got[4] == expected[4]
        assert got[3] == pytest.approx(expected[3], abs=1.5e-3), got
    if name == "b3-hip-6-12":  # buildings.md's table, as printed
        assert [r[3] for r in rows] == [82.410, 56.068, 29.235, 109.438, 25.5]
    assert {line.material for line in cut_list.lines} == {"spf_lumber"}
    assert cut_list.unclassified == 0


@each_roof
def test_the_lengths_measured_on_the_step_are_the_specs(
    name: str, tmp_path: Path
) -> None:
    spec = SPEC[name]
    roles = _by_role(name, _step_solids(name, tmp_path))
    assert {r: len(s) for r, s in roles.items()} == {
        "common": 6,
        "jack": 16,
        "hip": 4,
        "ridge": 1,
    }

    def top_face_length(solid: Solid) -> float:
        """A common's or jack's top face (the largest face neither a side
        nor level) over its 1.5 width: its centreline length."""
        rest = [
            f
            for f in solid.faces()
            if abs(f.normal_at().X) < 1 - 1e-9
            and abs(f.normal_at().Y) < 1 - 1e-9
            and f.normal_at().Z > 1e-9
        ]
        return max(f.area for f in rest) / (1.5 * IN) / IN

    for common in roles["common"]:
        assert top_face_length(common) == pytest.approx(spec["common"], abs=5e-4)
    jacks = sorted(top_face_length(j) for j in roles["jack"])
    assert jacks[:8] == [pytest.approx(spec["jack_short"], abs=5e-4)] * 8
    assert jacks[8:] == [pytest.approx(spec["jack_long"], abs=5e-4)] * 8
    assert jacks[8] - jacks[0] == pytest.approx(spec["decrement"], abs=5e-4)

    ridge_top = roles["ridge"][0].bounding_box().max.Z / IN
    for hip in roles["hip"]:
        # Dropped: its highest point (the ridge end's long point) is the drop
        # below the ridge's top, which is flush with the planes.
        top = hip.bounding_box().max.Z / IN
        assert ridge_top - top == pytest.approx(spec["drop"], abs=5e-4)
    for hip in roles["hip"]:
        assert _hip_centre_length(hip) == pytest.approx(spec["hip"], abs=5e-4)
    if name == "b3-hip-6-12":
        for hip in roles["hip"]:
            # The double heel on the corner: the hip's lowest point inside
            # both walls is 3.556 below the plate, on the corner's plumb line.
            assert _heel(hip) == pytest.approx(3.556, abs=5e-4)


def _midplane_vertices(hip: Solid) -> list[Vector]:
    """The hip's vertices on its centreline's vertical plane (the long
    points of its double cheeks), in inches."""
    sides = [
        f for f in hip.faces() if abs(f.normal_at().Z) < 1e-9 and f.area > 300 * IN * IN
    ]
    a, b = sides[0], sides[1]
    normal = a.normal_at()
    centre = (a.center() + b.center()) * 0.5
    return [
        Vector(v) / IN
        for v in hip.vertices()
        if abs((Vector(v) - centre).dot(normal)) < 1e-6
    ]


def _hip_centre_length(hip: Solid) -> float:
    """Along the top's centreline, long point to long point."""
    points = _midplane_vertices(hip)
    tail = min(points, key=lambda p: p.Z)
    tail_top = max(
        (p for p in points if math.hypot(p.X - tail.X, p.Y - tail.Y) < 1e-6),
        key=lambda p: p.Z,
    )
    ridge_top = max(points, key=lambda p: p.Z)
    return (ridge_top - tail_top).length


def _heel(hip: Solid) -> float:
    """Plate height less the lowest midplane vertex on the corner's plumb
    line (a corner of the walls' outer faces)."""
    on_corner = [
        p
        for p in _midplane_vertices(hip)
        if min(abs(p.X), abs(p.X - 144)) < 1e-6 and min(abs(p.Y), abs(p.Y - 120)) < 1e-6
    ]
    return 97.125 - min(p.Z for p in on_corner)


@each_roof
def test_the_bodies_are_the_independent_scripts(name: str, tmp_path: Path) -> None:
    """The kernel's bodies are the script's to 1e-4 mm^3 each (volume and
    symmetric difference). The exported STEP's are too, within the golden's
    reviewed round-trip bound: OCCT's writer moves a hip by ~1.1e-4 mm^3
    (6e-12 of it; test_the_roofs_step_drift_is_occts), so the STEP is not
    held to 1e-4 per body, but its solids still match the script one to one."""
    want = sorted(script_hip_roof(RISES[name]), key=_key)
    built: list[Solid] = list(build_model_solid(_request(name)).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    got = sorted(built, key=_key)
    assert len(got) == len(want) == 27
    total = 0.0
    for a, b in zip(got, want, strict=True):
        assert _volume(a) == pytest.approx(_volume(b), abs=1e-4)
        difference = _volume(a.cut(b)) + _volume(b.cut(a))  # pyright: ignore[reportUnknownMemberType]
        assert difference < 1e-4, (_key(a), difference)
        total += _volume(a)
    # buildings.md's "to 1e-4" is in inches: the summed volume, in^3; and
    # the hand total, printed to 3 decimals.
    script = sum(_volume(s) for s in want)
    assert total / IN**3 == pytest.approx(script / IN**3, abs=1e-4)
    assert script / IN**3 == pytest.approx(SPEC[name]["volume"], abs=5e-4)
    bound = json.loads((GOLDENS / name / "expected.json").read_text())[
        "roundtrip_tolerance"
    ]
    step = sorted(_step_solids(name, tmp_path), key=_key)
    assert [_key(s) for s in step] == [_key(s) for s in want]
    for a, b in zip(step, want, strict=True):
        assert _volume(a) == pytest.approx(_volume(b), abs=bound)
        difference = _volume(a.cut(b)) + _volume(b.cut(a))  # pyright: ignore[reportUnknownMemberType]
        assert difference < bound, (_key(a), difference)


@each_roof
def test_nothing_interferes_with_the_walls_or_each_other(
    name: str, tmp_path: Path
) -> None:
    roof = _step_solids(name, tmp_path)
    probed, bad = _overlapping(roof, walls(120, 144, 97.125, 3.5))
    assert bad == []
    # Every jack touches its hip and every common or jack its wall: those
    # boxes overlap, so the pairs are probed exactly.
    assert probed >= 16 + 22


def _sweep() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(gzip.decompress(SWEEP.read_bytes()))
    return cases


@pytest.mark.parametrize("case", _sweep(), ids=[c["name"] for c in _sweep()])
def test_the_overlap_sweep_builds_every_member_touching_only(
    case: dict[str, Any],
) -> None:
    """Other spans, lengths, pitches, spacings, overhangs (0, 1/16, 36) and
    sizes: one solid per member, the members at most touching each other
    and the walls."""
    request = EvaluateTreeRequest.model_validate(case["request"])
    shape = build_model_solid(request)
    solids: list[Solid] = list(shape.solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    assert len(solids) == case["bodies"]
    assert all(s.is_valid for s in solids)
    bearing = case["bearing_in"]
    probed, bad = _overlapping(
        solids,
        walls(
            bearing["span"],
            bearing["length"],
            bearing["plate_height"],
            bearing["plate_width"],
        ),
    )
    assert bad == [], bad
    assert probed > case["bodies"] // 2


def _drift(solids: Sequence[Solid], tmp_path: Path, name: str) -> float:
    """Volume after build123d's STEP export and re-import, less before."""
    before = sum(_volume(s) for s in solids)
    path = tmp_path / f"{name}.step"
    export_step(Compound(list(solids)), str(path))
    back = list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportUnknownVariableType]
    return sum(_volume(s) for s in back) - before  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]


@pytest.mark.parametrize("name", ["b2-roof-6-12", "b3-hip-6-12", "b3-hip-8-12"])
def test_the_roofs_step_drift_is_occts(name: str, tmp_path: Path) -> None:
    """ROOF-TWIN-DRIFT-TEST: the roof goldens' 1e-3 mm^3 round-trip bound
    holds for the plugin's bodies, and the independent script's own solids
    (no Loft code at all) drift through build123d's STEP too, while their
    one axis-aligned body, the ridge, does not: the drift is OCCT's writer
    rounding sloped coordinates, not Loft's export.

    Measured 2026-10-17 (mm^3): B2 plugin -3.47e-4, twin -3.47e-4 (built the
    same way, the same drift); B3 6/12 plugin +1.18e-4, twin -3.10e-3; 8/12
    plugin +2.26e-4, twin -1.01e-3. The hip twin cuts each member from
    sloped slabs (more irrational vertices than the plugin's sketched
    profiles), so it drifts more: the bound is the plugin's, not the twin's."""
    bound = json.loads((GOLDENS / name / "expected.json").read_text())[
        "roundtrip_tolerance"
    ]
    built: list[Solid] = list(build_model_solid(_request(name)).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    ours = abs(_drift(built, tmp_path, "ours"))
    twin_solids = _b2_twin() if name.startswith("b2") else script_hip_roof(RISES[name])
    twin = abs(_drift(twin_solids, tmp_path, "twin"))
    ridge = abs(_drift(twin_solids[-1:], tmp_path, "ridge"))
    assert ours < bound, ours
    assert 1e-5 < twin < 1e-2, twin  # ~1e-11 of the roof, from OCCT alone
    assert ridge < 1e-7, ridge


def _b2_twin() -> list[Solid]:
    """B2's gable from buildings.md, as test_roof_b2's script builds it
    (typed again here: test modules do not import each other)."""
    seat, heel, plumb = 3.5, 1.75, 5.5 * math.sqrt(1.25)

    def z(y: float) -> float:
        return 97.125 + (y - seat) * 0.5

    front = [
        (-12.0, z(-12.0)),
        (0.0, 97.125 - heel),
        (0.0, 97.125),
        (seat, 97.125),
        (59.25, z(59.25)),
        (59.25, z(59.25) + plumb),
        (-12.0, z(-12.0) + plumb),
    ]
    back = [(120.0 - y, h) for y, h in front]
    solids: list[Solid] = []
    for centre in (0.75, 24, 48, 72, 96, 120, 143.25):
        for outline in (front, back):
            plane = Plane.YZ.offset((centre - 0.75) * IN)
            face = plane * Polygon(*[(y * IN, h * IN) for y, h in outline], align=None)
            solids.append(extrude(face, 1.5 * IN, dir=(1, 0, 0)).solid())
    top = z(59.25) + plumb
    ridge = Pos(72 * IN, 60 * IN, (top - 3.625) * IN) * Box(
        144 * IN, 1.5 * IN, 7.25 * IN
    )
    solids.append(ridge.solid())
    return solids
