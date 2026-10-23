"""ROOF-HIP-SHEATHING-NOTCH acceptance: B3's hip on B2's sheathed outline.

``goldens/b3-outline-hip-sheathed`` is B2's four walls drawn as one 144 x 120
outline (``loft.wall`` 1.3.0, 2x4 at 16 in o.c., 7/16 OSB) and B3's hip roof
on them (``loft.roof`` 1.5.0, 6/12, 2x6 at 24 in o.c., 2x8 ridge and hips,
12 in overhang), each tail notched out of the OSB it passes through.
``model.json`` and ``members.json`` are pinned to the plugins by
``packages/loft-plugins/tests/test_roof_sheathing.py``. Geometry never learns
plugins exist, so this module reads JSON only.

Checked here against an INDEPENDENT build123d script (:func:`script`, typed
from buildings.md B2 and B3, sharing no code with the plugins):

1. the volume is analytic: B2's framing 25 601.625, its OSB 22 510.236328125
   (two 144 walls, two 113 walls and four corner rips 3.5 + 7/16 wide, all
   97.125 x 7/16), B3's roof at 1.3.0 (b3-hip-6-12's 13 790.757636 less
   four ripped hip tails, test_roof_member_renumber.Roof.rip), less the
   notches: 22 tails x 1.5 x 1/2 x (3.5 x 7/16 + (7/16)^2 / 2) and four hip
   corners 2 sqrt 2 a s heel - k s a^2 + sqrt 2 k a s^2 (a 0.75, s 7/16,
   heel 1.75, k 1/2);
2. the STEP's 91 solids are the script's solid for solid, the script's
   panels being each OSB box LESS the roof members that meet it: so each
   notch removes exactly the overlap, no more;
3. nothing interferes.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_roof_hip_sheathing.py``.
"""

import importlib.util
import itertools
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from build123d import (
    Box,
    Plane,
    Pos,
    Rot,
    Solid,
    Vector,
    import_step,  # pyright: ignore[reportUnknownVariableType]
)
from fastapi.testclient import TestClient
from geometry.kernel import measure_shape
from geometry.kernel.interference import probe_overlap
from geometry.main import app
from loft_wire.features import EvaluateTreeRequest, ExportTreeRequest

client = TestClient(app)


def _sibling(name: str) -> Any:
    """Another test module here (the suite imports by path, importlib)."""
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: B3's independent roof script (1.1.0) and the 1.3.0 rip's closed form.
script_hip_roof = _sibling("test_roof_hip_b3").script_hip_roof
Roof = _sibling("test_roof_member_renumber").Roof

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
NAME = "b3-outline-hip-sheathed"
IN = 25.4
R2 = math.sqrt(2)

# --- B2 and B3, typed from buildings.md (inches) -----------------------------------

LENGTH, SPAN = 144.0, 120.0
D = 3.5  # 2x4 walls
T = 1.5
H = 97.125  # the plate's top
STUD_TOP = 94.125
OSB = 7 / 16
K = 0.5  # 6/12
SEAT = 3.5
HEEL = SEAT * K
SPF, PT, OSB_M = "spf_lumber", "southern_pine_pt", "osb"
DENSITY = {SPF: 450.0, PT: 582.0, OSB_M: 641.0}

Bounds = tuple[float, float, float, float, float, float]

FRAMING = 25601.625  # b2-walls-no-openings-16oc's analytic volume
OSB_VOLUME = (2 * 144 + 2 * 113 + 4 * (D + OSB)) * H * OSB
TAIL = T * K * (SEAT * OSB + OSB * OSB / 2)
CORNER = (
    2 * R2 * (T / 2) * OSB * HEEL
    - K * OSB * (T / 2) ** 2
    + R2 * K * (T / 2) * OSB * OSB
)
NOTCHES = 22 * TAIL + 4 * CORNER


def roof_volume() -> float:
    """B3 at 1.3.0: b3-hip-6-12 (1.1.0, buildings.md's 13 790.757636) less
    ROOF-HIP-TAIL's four rips (the renumber goldens' closed form)."""
    rip: float = Roof(6).rip()[0]
    base = json.loads((GOLDENS / "b3-hip-6-12" / "expected.json").read_text())
    return base["properties"]["volume"] / IN**3 - 4 * rip


def analytic_volume() -> float:
    return FRAMING + OSB_VOLUME + roof_volume() - NOTCHES


@dataclass(frozen=True)
class Member:
    material: str
    solid: Solid


def box(b: Bounds) -> Solid:
    x0, x1, y0, y1, z0, z1 = b
    return (
        Pos((x0 + x1) / 2 * IN, (y0 + y1) / 2 * IN, (z0 + z1) / 2 * IN)
        * Box((x1 - x0) * IN, (y1 - y0) * IN, (z1 - z0) * IN)
    ).solid()


def layout(length: float) -> list[float]:
    """Stud centres from a wall's start: 0.75, every 16, the far one flush."""
    inner = [16.0 * k for k in range(1, 20) if 16.0 * k + 0.75 <= length - T]
    return [0.75, *inner, length - 0.75]


def framing() -> list[Member]:
    """B2's walls (buildings.md): front and back X 0..144 run through, the
    sides fit between (Y 3.5..116.5); a PT bottom plate, studs to 94.125 and
    a double top plate. The outline walks clockwise: the front from X 144,
    the left from Y 3.5, the back from X 0, the right from Y 116.5."""
    out: list[Member] = []
    walls: list[tuple[float, float, int, int, int, int, float]] = [
        (LENGTH, 0.0, -1, 0, 0, 1, LENGTH),
        (0.0, D, 0, 1, 1, 0, SPAN - 2 * D),
        (0.0, SPAN, 1, 0, 0, -1, LENGTH),
        (LENGTH, SPAN - D, 0, -1, -1, 0, SPAN - 2 * D),
    ]
    for x, y, ax, ay, nx, ny, length in walls:

        def at(u0: float, u1: float, z0: float, z1: float) -> Bounds:
            xs = [x + u * ax + v * nx for u in (u0, u1) for v in (0.0, D)]  # noqa: B023
            ys = [y + u * ay + v * ny for u in (u0, u1) for v in (0.0, D)]  # noqa: B023
            return (min(xs), max(xs), min(ys), max(ys), z0, z1)

        out.append(Member(PT, box(at(0, length, 0, T))))
        out.append(Member(SPF, box(at(0, length, STUD_TOP, STUD_TOP + T))))
        out.append(Member(SPF, box(at(0, length, STUD_TOP + T, H))))
        for c in layout(length):
            out.append(Member(SPF, box(at(c - 0.75, c + 0.75, T, STUD_TOP))))
    return out


def panels() -> list[Bounds]:
    """The OSB outside the framing's faces, full height, 48 in from each
    wall's start, and the side walls' corner rips 3.5 + 7/16 wide."""
    out: list[Bounds] = []
    for x0 in (96.0, 48.0, 0.0):  # front, from X 144
        out.append((x0, x0 + 48, -OSB, 0.0, 0.0, H))
    for y0, y1 in ((3.5, 51.5), (51.5, 99.5), (99.5, 116.5)):  # left, from 3.5
        out.append((-OSB, 0.0, y0, y1, 0.0, H))
    for x0 in (0.0, 48.0, 96.0):  # back, from X 0
        out.append((x0, x0 + 48, SPAN, SPAN + OSB, 0.0, H))
    for y0, y1 in ((68.5, 116.5), (20.5, 68.5), (3.5, 20.5)):  # right, from 116.5
        out.append((LENGTH, LENGTH + OSB, y0, y1, 0.0, H))
    for x0, x1 in ((-OSB, 0.0), (LENGTH, LENGTH + OSB)):
        out.append((x0, x1, -OSB, D, 0.0, H))
        out.append((x0, x1, SPAN - D, SPAN + OSB, 0.0, H))
    return out


def ripped_roof() -> list[Solid]:
    """B3's roof (test_roof_hip_b3's script, 1.1.0) with each hip's tail
    ripped as ROOF-HIP-TAIL rips it: below the line where the two commons'
    undersides meet (Z plate - heel at the corner, rising k / sqrt 2 along
    the hip), back to where that line reaches the plate (heel / (k / sqrt 2)
    along the hip; inside both walls below the plate is the seat's)."""
    solids: list[Solid] = list(script_hip_roof(6))
    reach = HEEL / (K / R2)
    out: list[Solid] = []
    for solid in solids:
        # The hips are the only bodies over 1 000 in^3 (b3-hip-6-12: 1 128.7).
        if float(measure_shape(solid).volume) / IN**3 < 1000:
            out.append(solid)
            continue
        bb = solid.bounding_box()
        left, front = bb.min.X / IN < LENGTH / 2, bb.min.Y / IN < SPAN / 2
        cx, dx = (0.0, 1) if left else (LENGTH, -1)
        cy, dy = (0.0, 1) if front else (SPAN, -1)
        normal = Vector(-dx * K / 2, -dy * K / 2, 1).normalized()
        under = Plane(origin=(cx * IN, cy * IN, (H - HEEL) * IN), z_dir=normal)
        below = (
            under.location * Pos(0, 0, -100 * IN) * Box(1e4, 1e4, 200 * IN)
        ).solid()
        angle = math.degrees(math.atan2(dy, dx))
        mid = reach - 50.0
        tail = (
            Pos((cx + dx * mid / R2) * IN, (cy + dy * mid / R2) * IN, 0)
            * Rot(0, 0, angle)
            * Box(100 * IN, 100 * IN, 1000 * IN)
        ).solid()
        cutter = below & tail
        ripped = list((solid - cutter).solids())
        assert len(ripped) == 1
        out.append(ripped[0])
    return out


def script() -> list[Member]:
    """Every body: the framing, each OSB panel less the roof members that
    meet it, and the roof."""
    roof = ripped_roof()
    out = framing()
    for b in panels():
        panel = box(b)
        for member in roof:
            if probe_overlap(panel, member).volume_mm3 > 0.0:
                panel = next(iter((panel - member).solids()))
        out.append(Member(OSB_M, panel))
    out += [Member(SPF, s) for s in roof]
    return out


# --- The golden's STEP -------------------------------------------------------------


def _request() -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / NAME / "model.json").read_text()
    )


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    request = ExportTreeRequest.model_validate(
        {**_request().model_dump(mode="json"), "format": "step"}
    )
    response = client.post("/api/v1/export/tree", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    path = tmp_path_factory.mktemp("step") / f"{NAME}.step"
    path.write_bytes(response.content)
    return list(import_step(path).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def _signature(solid: Solid) -> tuple[float, ...]:
    bb = solid.bounding_box()
    values = (bb.min.X, bb.max.X, bb.min.Y, bb.max.Y, bb.min.Z, bb.max.Z)
    volume = float(measure_shape(solid).volume) / IN**3
    return (volume, *(v / IN for v in values))


def _unmatched(
    ours: Sequence[Solid], theirs: Sequence[Solid]
) -> list[tuple[float, ...]]:
    """Each of *ours* paired with one of *theirs* of the same volume (to 1e-6
    in^3) and bounds (to 1e-5 in); what finds no partner."""
    left = [_signature(s) for s in theirs]
    missing: list[tuple[float, ...]] = []
    for sig in (_signature(s) for s in ours):
        k = next(
            (
                k
                for k, other in enumerate(left)
                if abs(sig[0] - other[0]) <= 1e-6
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


def test_the_hand_numbers() -> None:
    assert OSB_VOLUME == 22510.236328125
    assert TAIL == 1.22021484375
    assert pytest.approx(1.60259750604, abs=1e-10) == CORNER
    assert roof_volume() == pytest.approx(13606.8886127, abs=1e-6)
    assert analytic_volume() == pytest.approx(61685.4948248, abs=1e-6)


def test_the_scripts_roof_is_b3_at_1_3_0() -> None:
    roof = ripped_roof()
    volume = sum(float(measure_shape(s).volume) for s in roof) / IN**3
    assert len(roof) == 27
    assert volume == pytest.approx(roof_volume(), abs=1e-6)


def test_the_step_is_the_independent_scripts(step_solids: list[Solid]) -> None:
    """Solid for solid: the framing, the roof, and every OSB panel less
    exactly the roof members that meet it (26 notched: 22 tails, the 4
    hips' through two panels each, 30 notches)."""
    mine = script()
    assert len(step_solids) == len(mine) == 91
    assert _unmatched(step_solids, [m.solid for m in mine]) == []
    volume = sum(float(measure_shape(s).volume) for s in step_solids) / IN**3
    assert volume == pytest.approx(analytic_volume(), abs=1e-4)


def test_nothing_interferes(step_solids: list[Solid]) -> None:
    assert _overlapping(step_solids) == []


# --- expected.json's numbers --------------------------------------------------------


def expected_numbers() -> dict[str, Any]:
    """The golden's mass properties, topology and mesh counts from the
    script: volume analytic, the rest measured on the script's solids; a
    planar face of n vertices on h holes meshes as n + 2h - 2 triangles."""
    mine = script()
    volume = analytic_volume() * IN**3
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
    json.dump(expected_numbers(), sys.stdout, indent=2)
    sys.stdout.write("\n")
