"""FLOOR-JOIST-SPAN acceptance: B7's floor both ways, on STEP.

``goldens/b7-floor-long-walls`` and ``b7-floor-left-right`` are one
``loft.floor`` 1.3.0 on B7's 288 x 192 outline (2x10 joists at 16 in, PT 2x6
sills, 23/32 plywood subfloor), drawn from the back-left corner down its left
side: the drawing on which 1.2.0 framed 24 ft joists. Joists bear on Long
walls (the default) and on Left and right. ``model.json`` and
``members.json`` are pinned to the plugin by
``packages/loft-plugins/tests/test_floor_joist_span.py``. Geometry never
learns plugins exist, so this module imports nothing from them.

Checked here against members typed by hand from buildings.md B7's floor
(:func:`spec`, sharing no code with the plugin):

1. the cut list: Long walls 19 joists at 189 (the 16 ft span), 2 rims at
   288, sills 2 at 288 and 2 at 181; Left and right 13 joists at 285 (24 ft),
   2 rims at 192, sills 2 at 192 and 2 at 277; 14 and 15 subfloor panels,
   the same 55 296 in^2;
2. the exported STEP's solids are an independent build123d script's, box
   for box, summing to the analytic volume;
3. interference none, every body weighing by its member material.

Regenerate expected.json's analytic numbers with
``uv run python services/geometry/tests/test_floor_joist_span_b7.py <name>``.
"""

import itertools
import json
import sys
from collections import Counter
from collections.abc import Sequence
from fractions import Fraction
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
LONG, LEFT_RIGHT = "b7-floor-long-walls", "b7-floor-left-right"
NAMES = (LONG, LEFT_RIGHT)
IN = Fraction(254, 10)

# --- B7's floor, typed from buildings.md (inches, exact) ---------------------------

L, W = Fraction(288), Fraction(192)  # X and Y outside of the framing
T = Fraction(3, 2)  # every member's thickness
SILL_W = Fraction(11, 2)  # PT 2x6 laid flat
FRAMING_TOP = T + Fraction(37, 4)  # 2x10 on the sills: 10.75
PLY_TOP = FRAMING_TOP + Fraction(23, 32)  # 11.46875

SPF, PT, PLY = "spf_lumber", "southern_pine_pt", "plywood"
DENSITY = {SPF: Fraction(450), PT: Fraction(582), PLY: Fraction(577)}  # kg/m^3

Bounds = tuple[Fraction, Fraction, Fraction, Fraction, Fraction, Fraction]
Row = tuple[str, str, Bounds]  # member, material, x0 x1 y0 y1 z0 z1


def centres(length: Fraction) -> list[Fraction]:
    """0.75, then every 16 while the joist clears the far end joist, then
    length - 0.75 (buildings.md B5's layout)."""
    out = [Fraction(3, 4)]
    k = 1
    while 16 * k + Fraction(3, 4) <= length - T:
        out.append(Fraction(16 * k))
        k += 1
    return [*out, length - Fraction(3, 4)]


def edges(length: Fraction, offset: bool) -> list[Fraction]:
    """A subfloor row's cuts: 96 long panels, a staggered row starting 48."""
    inner = range(48 if offset else 96, int(length), 96)
    return [Fraction(0), *(Fraction(x) for x in inner), length]


def spec(name: str) -> list[Row]:
    """The floor's members, typed by hand. Long walls: rims on the front and
    back (Y 0 and 192), joists along Y. Left and right: rims on the sides
    (X 0 and 288), joists along X."""
    z_sill = (Fraction(0), T)
    z_frame = (T, FRAMING_TOP)
    z_ply = (FRAMING_TOP, PLY_TOP)
    rows: list[Row] = []
    if name == LONG:
        rows += [
            ("Sill", PT, (Fraction(0), L, Fraction(0), SILL_W, *z_sill)),
            ("Sill", PT, (Fraction(0), L, W - SILL_W, W, *z_sill)),
            ("Sill", PT, (Fraction(0), SILL_W, SILL_W, W - SILL_W, *z_sill)),
            ("Sill", PT, (L - SILL_W, L, SILL_W, W - SILL_W, *z_sill)),
            ("Rim", SPF, (Fraction(0), L, Fraction(0), T, *z_frame)),
            ("Rim", SPF, (Fraction(0), L, W - T, W, *z_frame)),
        ]
        rows += [
            ("Joist", SPF, (c - T / 2, c + T / 2, T, W - T, *z_frame))
            for c in centres(L)
        ]
        for row in range(4):
            y0 = Fraction(48 * row)
            for x0, x1 in itertools.pairwise(edges(L, row % 2 == 1)):
                rows.append(("Subfloor", PLY, (x0, x1, y0, y0 + 48, *z_ply)))
    else:
        rows += [
            ("Sill", PT, (Fraction(0), SILL_W, Fraction(0), W, *z_sill)),
            ("Sill", PT, (L - SILL_W, L, Fraction(0), W, *z_sill)),
            ("Sill", PT, (SILL_W, L - SILL_W, Fraction(0), SILL_W, *z_sill)),
            ("Sill", PT, (SILL_W, L - SILL_W, W - SILL_W, W, *z_sill)),
            ("Rim", SPF, (Fraction(0), T, Fraction(0), W, *z_frame)),
            ("Rim", SPF, (L - T, L, Fraction(0), W, *z_frame)),
        ]
        rows += [
            ("Joist", SPF, (T, L - T, c - T / 2, c + T / 2, *z_frame))
            for c in centres(W)
        ]
        for row in range(6):
            x0 = Fraction(48 * row)
            for y0, y1 in itertools.pairwise(edges(W, row % 2 == 1)):
                rows.append(("Subfloor", PLY, (x0, x0 + 48, y0, y1, *z_ply)))
    return rows


#: The cut list (no price book): member, profile, material, quantity, length
#: (in) or net area (in^2), stock, the members over 20 ft spliced from the
#: fewest stock pieces (CUT-LIST-LONG-STOCK, as B7's 288 sills). In the
#: list's order (CUT-LIST-PANEL): the sheet goods first, then the lumber by
#: member as it first appears.
TABLES: dict[str, list[tuple[str, str, str, int, float, str]]] = {
    LONG: [
        ("Subfloor", "23/32 plywood", PLY, 14, 55296.0, "12 x 4x8"),
        ("Joist", "2x10", SPF, 19, 189.0, "16 ft"),
        ("Rim", "2x10", SPF, 2, 288.0, "2 x 12 ft"),
        ("Sill", "2x6", PT, 2, 181.0, "16 ft"),
        ("Sill", "2x6", PT, 2, 288.0, "2 x 12 ft"),
    ],
    LEFT_RIGHT: [
        ("Subfloor", "23/32 plywood", PLY, 15, 55296.0, "12 x 4x8"),
        ("Joist", "2x10", SPF, 13, 285.0, "2 x 12 ft"),
        ("Rim", "2x10", SPF, 2, 192.0, "16 ft"),
        ("Sill", "2x6", PT, 2, 192.0, "16 ft"),
        ("Sill", "2x6", PT, 2, 277.0, "2 x 12 ft"),
    ],
}


def _volume(b: Bounds) -> Fraction:
    return (b[1] - b[0]) * (b[3] - b[2]) * (b[5] - b[4])


def _area(b: Bounds) -> Fraction:
    x, y, z = b[1] - b[0], b[3] - b[2], b[5] - b[4]
    return 2 * (x * y + y * z + z * x)


def _centre(b: Bounds) -> tuple[Fraction, Fraction, Fraction]:
    return ((b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2)


def expected_numbers(name: str) -> dict[str, Any]:
    """The golden's properties from :func:`spec` in exact rationals."""
    rows = spec(name)
    volume = sum((_volume(b) for _, _, b in rows), Fraction(0))
    area = sum((_area(b) for _, _, b in rows), Fraction(0))
    centroid = [
        sum((_volume(b) * _centre(b)[k] for _, _, b in rows), Fraction(0)) / volume
        for k in range(3)
    ]
    # Grams per in^3 at 1 kg/m^3: (0.0254 m)^3 x 1000 g/kg.
    per = (IN / 1000) ** 3 * 1000
    mass = sum((DENSITY[m] * _volume(b) * per for _, m, b in rows), Fraction(0))
    com = [
        sum((DENSITY[m] * _volume(b) * _centre(b)[k] for _, m, b in rows), Fraction(0))
        / sum((DENSITY[m] * _volume(b) for _, m, b in rows), Fraction(0))
        for k in range(3)
    ]
    xs = [v for _, _, b in rows for v in b[:2]]
    ys = [v for _, _, b in rows for v in b[2:4]]
    zs = [v for _, _, b in rows for v in b[4:]]
    n = len(rows)

    def mm(v: Fraction) -> float:
        return float(v * IN)

    return {
        "volume_in3": str(volume),
        "properties": {
            "volume": float(volume * IN**3),
            "surface_area": float(area * IN**2),
            "centroid": dict(zip("xyz", (mm(c) for c in centroid), strict=True)),
            "mass_g": float(mass),
            "center_of_mass": dict(zip("xyz", (mm(c) for c in com), strict=True)),
            "bounding_box": {
                "min": {"x": mm(min(xs)), "y": mm(min(ys)), "z": mm(min(zs))},
                "max": {"x": mm(max(xs)), "y": mm(max(ys)), "z": mm(max(zs))},
            },
        },
        "topology": {"faces": 6 * n, "edges": 12 * n, "shells": n},
        "mesh": {"vertices": 24 * n, "triangles": 12 * n},
        "centroid_in": [str(c) for c in centroid],
        "center_of_mass_in": [str(c) for c in com],
        "surface_area_in2": str(area),
    }


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


def _script(rows: Sequence[Row]) -> list[Solid]:
    """The independent script: each member a build123d Box, no Loft code."""
    out: list[Solid] = []
    for _, _, b in rows:
        x0, x1, y0, y1, z0, z1 = (float(v * IN) for v in b)
        out.append(
            (
                Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
                * Box(x1 - x0, y1 - y0, z1 - z0)
            ).solid()
        )
    return out


def _signature(solid: Solid) -> tuple[float, ...]:
    """Volume (in^3, to 1e-6) and the box (in, to 1e-6) of a solid."""
    box = solid.bounding_box()
    values = (box.min.X, box.max.X, box.min.Y, box.max.Y, box.min.Z, box.max.Z)
    inch = float(IN)
    volume = float(measure_shape(solid).volume) / inch**3
    return (round(volume, 6), *(round(v / inch, 6) + 0.0 for v in values))


each_golden = pytest.mark.parametrize("name", NAMES)


# --- 1. The cut list ----------------------------------------------------------------


def _stock(line: Any) -> str:
    if line.sheet:
        return f"{line.stock_quantity} x {line.sheet}"
    pieces = list(line.stock_pieces_ft or [])
    if len(pieces) > 1 and len(set(pieces)) == 1:
        return f"{len(pieces)} x {pieces[0]} ft"
    if pieces:
        return " + ".join(f"{p} ft" for p in pieces)
    return f"{line.stock_length_ft} ft"


@each_golden
def test_the_cut_list_is_the_hand_typed_floors(name: str) -> None:
    request = _request(name)
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    extents = BodyExtentsResult.model_validate_json(response.content)
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B7 floor",
        length_unit="in",
        pieces=part_pieces(extents, _members(name), request.materials),
    )
    rows = [
        (
            line.member,
            line.profile,
            line.material,
            line.quantity,
            round((line.area_mm2 or 0) / float(IN) ** 2, 6)
            if line.sheet
            else round(line.length_mm / float(IN), 6),
            _stock(line),
        )
        for line in cut_list.lines
    ]
    assert rows == TABLES[name]
    assert cut_list.unclassified == 0
    # The hand-typed members give the same counts and lengths.
    counted: Counter[tuple[str, float]] = Counter()
    for member, _, b in spec(name):
        if member != "Subfloor":
            counted[(member, float(max(b[1] - b[0], b[3] - b[2])))] += 1
    assert counted == Counter(
        {(m, v): q for m, _, _, q, v, _ in TABLES[name] if m != "Subfloor"}
    )


# --- 2. The STEP against the hand-typed script --------------------------------------


@each_golden
def test_the_step_is_the_independent_scripts(name: str, tmp_path: Path) -> None:
    solids = _step_solids(name, tmp_path)
    script = _script(spec(name))
    assert len(solids) == len(script) == sum(row[3] for row in TABLES[name])
    assert Counter(_signature(s) for s in solids) == Counter(
        _signature(s) for s in script
    )
    ours = sum(float(measure_shape(s).volume) for s in solids) / float(IN) ** 3
    want = float(sum((_volume(b) for _, _, b in spec(name)), Fraction(0)))
    assert ours == pytest.approx(want, abs=1e-4)


@each_golden
def test_expected_json_is_the_analytic_numbers(name: str) -> None:
    expected = json.loads((GOLDENS / name / "expected.json").read_text())
    numbers = expected_numbers(name)
    for key in ("properties", "topology", "mesh"):
        assert expected[key] == numbers[key], key


# --- 3. Interference none and mass -------------------------------------------------


@each_golden
def test_nothing_interferes(name: str, tmp_path: Path) -> None:
    solids = _step_solids(name, tmp_path)
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
    assert bad == []


@each_golden
def test_every_body_weighs_by_its_member_material(name: str) -> None:
    request = _request(name)
    assert request.materials is not None
    assert request.materials.default_material is None
    response = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    want = expected_numbers(name)["properties"]["mass_g"]
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


if __name__ == "__main__":
    json.dump(expected_numbers(sys.argv[1]), sys.stdout, indent=2)
    sys.stdout.write("\n")
