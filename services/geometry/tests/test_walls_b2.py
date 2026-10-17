"""STUD-WALL acceptance: B2's walls from four ``loft.wall`` features, on STEP.

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

#: buildings.md B2's wall cut list with no openings: member, profile,
#: material, qty, length (in), stock (ft), in tree order (front wall first).
TABLES: dict[str, list[tuple[str, str, str, int, float, int]]] = {
    "b2-walls-no-openings-16oc": [
        ("Stud", "2x4", SPF, 36, 92.625, 8),
        ("Top plate", "2x4", SPF, 4, 144.0, 12),
        ("Bottom plate", "2x4", PT, 2, 144.0, 12),
        ("Top plate", "2x4", SPF, 4, 113.0, 10),
        ("Bottom plate", "2x4", PT, 2, 113.0, 10),
    ],
    # "spacing 16 -> 24 gives 26 studs".
    "b2-walls-no-openings-24oc": [
        ("Stud", "2x4", SPF, 26, 92.625, 8),
        ("Top plate", "2x4", SPF, 4, 144.0, 12),
        ("Bottom plate", "2x4", PT, 2, 144.0, 12),
        ("Top plate", "2x4", SPF, 4, 113.0, 10),
        ("Bottom plate", "2x4", PT, 2, 113.0, 10),
    ],
    # The default 144 wall turned 30 degrees: the same list as one B2 front
    # wall, read from turned bodies.
    "plugin-wall-v1-144-30deg": [
        ("Stud", "2x4", SPF, 10, 92.625, 8),
        ("Top plate", "2x4", SPF, 2, 144.0, 12),
        ("Bottom plate", "2x4", PT, 1, 144.0, 12),
    ],
}
#: The spec's volumes (in^3); the 30 degree wall is 10 studs and 3 plates.
VOLUMES = {
    "b2-walls-no-openings-16oc": 25601.625,
    "b2-walls-no-openings-24oc": 20738.8125,
    "plugin-wall-v1-144-30deg": 7130.8125,
}
B2 = ["b2-walls-no-openings-16oc", "b2-walls-no-openings-24oc"]

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
        want[(row[4], 1.5, 3.5)] += row[3]
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
    bottom_in3 = (2 * 144 + 2 * 113) * 1.5 * 3.5
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
