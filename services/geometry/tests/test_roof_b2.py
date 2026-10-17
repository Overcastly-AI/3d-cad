"""ROOF acceptance: B2's gable from one ``loft.roof`` feature, on its STEP.

``goldens/b2-roof-6-12`` and ``b2-roof-8-12`` are the plugin's expansion at
6/12 and 8/12 (``model.json``, with the member materials documents applies)
and each member's metadata (``members.json``), pinned to the plugin by
``packages/loft-plugins/tests/test_roof.py``. Checked here against
buildings.md and an INDEPENDENT build123d script (:func:`script_roof`, typed
from the spec, sharing no code with the plugin):

1. the cut list, measured from the bodies, is 14 rafters at their overall
   length (8 ft stock) and one 144 ridge (VISION: an angled member's cut
   length is its overall length, as a SolidWorks weldment cut list gives it);
2. each rafter's line length, heel and seat, measured on the exported STEP's
   faces, are the spec's (79.660 / 1.75 / 3.5 and 85.632 / 1.833 / 2.75);
3. the STEP's solids are the script's to 1e-4 (each pair's symmetric
   difference), and none interferes with another or with B2's four walls.
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest
from build123d import (
    Box,
    Location,
    Plane,
    Polygon,
    Pos,
    Solid,
    extrude,
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
IN = 25.4
#: Golden -> rise per 12.
RISES = {"b2-roof-6-12": 6, "b2-roof-8-12": 8}
#: buildings.md: line length, heel, seat (in).
SPEC = {
    "b2-roof-6-12": (79.660, 1.75, 3.5),
    "b2-roof-8-12": (85.632, 1.833, 2.75),
}
#: The overall length (long point to long point) the cut list reports: the
#: line length plus the depth x rise / 12 (buildings.md's roof row).
OVERALL = {"b2-roof-6-12": 82.410, "b2-roof-8-12": 89.299}

each_roof = pytest.mark.parametrize("name", sorted(RISES))


# --- The independent script ------------------------------------------------------


def script_roof(rise: int) -> list[Solid]:
    """B2's roof from buildings.md alone: walls' outer faces Y 0 and 120, top
    plates at Z 97.125 and 3.5 deep, a 2x8 ridge centred on Y 60, 2x6
    rafters at X 0.75, 24, ..., 120, 143.25 with a 12 in level overhang, the
    birdsmouth heel on the wall face and at most 1/3 of the depth."""
    slope = rise / 12
    seat = min(3.5, 5.5 / 3 / slope)
    heel = seat * slope
    plumb = 5.5 * math.sqrt(1 + slope * slope)

    def z(y: float) -> float:  # the rafter's bottom edge
        return 97.125 + (y - seat) * slope

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


def script_walls() -> list[Solid]:
    """B2's four walls as solid envelopes, Z 0..97.125 (stricter than their
    members: nothing may enter a wall's volume at all)."""
    h = 97.125

    def box(x0: float, x1: float, y0: float, y1: float) -> Solid:
        return (
            Location(((x0 + x1) / 2 * IN, (y0 + y1) / 2 * IN, h / 2 * IN))
            * Box((x1 - x0) * IN, (y1 - y0) * IN, h * IN)
        ).solid()

    return [
        box(0, 144, 0, 3.5),
        box(0, 144, 116.5, 120),
        box(0, 3.5, 3.5, 116.5),
        box(140.5, 144, 3.5, 116.5),
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


# --- Tests -------------------------------------------------------------------------


@each_roof
def test_the_cut_list_gives_each_rafters_overall_length(name: str) -> None:
    request = _request(name)
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="B2 roof",
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
    assert rows == [
        ("Rafter", "2x6", 14, OVERALL[name], 8),
        ("Ridge", "2x8", 1, 144.0, 12),
    ]
    assert {line.material for line in cut_list.lines} == {"spf_lumber"}
    assert cut_list.unclassified == 0
    # The overall length is the line length plus the depth x rise / 12.
    line_length = SPEC[name][0]
    assert OVERALL[name] == pytest.approx(
        line_length + 5.5 * RISES[name] / 12, abs=1e-3
    )


@each_roof
def test_every_rafter_on_the_step_cuts_to_the_spec(name: str, tmp_path: Path) -> None:
    """Measured on the STEP's faces: the top edge face is 1.5 x the line
    length, the heel face (plumb, across Y) 1.5 x the heel, the seat face
    (level) 1.5 x the seat."""
    line_length, heel, seat = SPEC[name]
    rafters = [s for s in _step_solids(name, tmp_path) if len(s.faces()) == 9]
    assert len(rafters) == 14
    for rafter in rafters:
        faces = rafter.faces()
        sides = [f for f in faces if abs(f.normal_at().X) > 1 - 1e-9]
        rest = [f for f in faces if abs(f.normal_at().X) < 1e-9]
        assert len(sides) == 2 and len(rest) == 7
        top = max(rest, key=lambda f: f.area)
        assert top.area / (1.5 * IN) / IN == pytest.approx(line_length, abs=5e-4)
        level = [f for f in rest if abs(f.normal_at().Z) > 1 - 1e-9]
        assert len(level) == 1  # the seat
        assert level[0].area / (1.5 * IN) / IN == pytest.approx(seat, abs=5e-4)
        assert abs(level[0].center().Z / IN - 97.125) < 1e-9
        plumb = sorted(
            (f for f in rest if abs(f.normal_at().Y) > 1 - 1e-9), key=lambda f: f.area
        )
        assert len(plumb) == 3  # heel, then the two plumb cuts
        assert plumb[0].area / (1.5 * IN) / IN == pytest.approx(heel, abs=5e-4)
        assert plumb[0].center().Y / IN in (pytest.approx(0), pytest.approx(120))
        assert heel <= 5.5 / 3 + 5e-4


@each_roof
def test_the_step_is_the_independent_scripts(name: str, tmp_path: Path) -> None:
    got = sorted(_step_solids(name, tmp_path), key=_key)
    want = sorted(script_roof(RISES[name]), key=_key)
    assert len(got) == len(want) == 15
    total = 0.0
    for a, b in zip(got, want, strict=True):
        assert _volume(a) == pytest.approx(_volume(b), abs=1e-4)
        difference = _volume(a.cut(b)) + _volume(b.cut(a))  # pyright: ignore[reportUnknownMemberType]
        assert difference < 1e-4, (_key(a), difference)
        total += _volume(a)
    # buildings.md's "to 1e-4" is in inches: the summed volume, in^3.
    script = sum(_volume(s) for s in want)
    assert total / IN**3 == pytest.approx(script / IN**3, abs=1e-4)


@each_roof
def test_nothing_interferes_with_the_walls_or_each_other(
    name: str, tmp_path: Path
) -> None:
    roof = _step_solids(name, tmp_path)
    solids = [*roof, *script_walls()]
    boxes = [s.bounding_box() for s in solids]
    probed = 0
    for i in range(len(roof)):
        for j in range(i + 1, len(solids)):
            a, b = boxes[i], boxes[j]
            if all(
                min(getattr(a.max, k), getattr(b.max, k))
                - max(getattr(a.min, k), getattr(b.min, k))
                > 1e-6
                for k in ("X", "Y", "Z")
            ):
                probed += 1
                probe = probe_overlap(solids[i], solids[j])
                assert not probe.unresolved and probe.volume_mm3 == 0.0, (i, j)
    # Each rafter's box overlaps its bearing wall's (the tail hangs past
    # the face below the plate top): those pairs are probed exactly.
    assert probed >= 14


@each_roof
def test_every_body_weighs_by_its_member_material(name: str) -> None:
    request = _request(name)
    assert request.materials is not None
    assert request.materials.default_material is None
    response = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    properties = response.json()["properties"]
    volume = sum(_volume(s) for s in script_roof(RISES[name]))
    assert properties["mass_g"] == pytest.approx(volume * 450.0e-6, rel=1e-12)


def test_the_script_is_rotation_free() -> None:
    """The script's rafters lie flat in YZ: each spans 1.5 in X."""
    for solid in script_roof(6)[:-1]:
        box = solid.bounding_box()
        assert abs((box.max.X - box.min.X) / IN - 1.5) < 1e-9
        assert solid.is_valid
