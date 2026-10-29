"""PLUGIN-UPDATE-ALL acceptance: B7 saved at batch48's releases, updated in
one step, on STEP.

``goldens/b7-update-all`` is ``b7-outline`` after one "Update all": the
floor at ``loft.floor`` 1.3.0 (Joists bear on Long walls, byte for byte
1.2.0's floor), the walls 1.4.0, the door and five windows 1.5.0 and the
roof 1.6.0 with its default ceiling joists. ``model.json`` and
``members.json`` are pinned to the plugins by
``packages/loft-plugins/tests/test_update_all.py``, which also shows it is
B7 built fresh today. Geometry never learns plugins exist, so this module
imports nothing from them.

Checked against the INDEPENDENT scripts the two releases were accepted on:
``test_opening_update_b7.script`` (B7, each opening's middle ply and two
1/2 in spacers) and ``test_ceiling_joists_b7.joists`` (11 snipped 2x8
joists beside the inner commons):

1. the STEP's 246 solids are the scripts', solid for solid, and the volume
   is 267 801.7539 + 22 887.596423 = 290 689.350323 in^3;
2. interference none, every pair probed exactly;
3. each body weighs by its member material.

Regenerate expected.json's numbers with
``uv run python services/geometry/tests/test_update_all_b7.py``.
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from build123d import Solid
from geometry.kernel import measure_shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_ceiling_joists_b7 as joists
import test_opening_update_b7 as openings
import test_outline_b7 as b7

NAME = "b7-update-all"
IN = b7.IN


def script() -> list[b7.Member]:
    return [*openings.script(), *joists.joists()]


def analytic_volume() -> float:
    return openings.analytic_volume() + 11 * joists.joist_volume()


@pytest.fixture(scope="module")
def step_solids(tmp_path_factory: pytest.TempPathFactory) -> list[Solid]:
    return b7._step_solids(tmp_path_factory, NAME)  # pyright: ignore[reportPrivateUsage]


def test_the_volume_is_the_updated_openings_and_the_joists() -> None:
    assert openings.analytic_volume() == pytest.approx(267801.7538656, abs=1e-6)
    assert round(11 * joists.joist_volume(), 6) == 22887.596423
    assert round(analytic_volume(), 6) == 290689.350289
    assert analytic_volume() == pytest.approx(267801.7539 + 22887.596423, abs=1e-4)


def test_the_step_is_the_independent_scripts(step_solids: list[Solid]) -> None:
    mine = script()
    assert len(step_solids) == len(mine) == 217 + 18 + 11
    assert b7._unmatched(step_solids, [m.solid for m in mine]) == []  # pyright: ignore[reportPrivateUsage]
    volume = sum(float(measure_shape(s).volume) for s in step_solids) / IN**3
    assert volume == pytest.approx(analytic_volume(), abs=1e-4)


def test_nothing_interferes(step_solids: list[Solid]) -> None:
    assert b7._overlapping(step_solids) == []  # pyright: ignore[reportPrivateUsage]


def test_every_body_weighs_by_its_member_material() -> None:
    request = b7._request(NAME)  # pyright: ignore[reportPrivateUsage]
    response = b7.client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    want = sum(
        float(measure_shape(m.solid).volume) * b7.DENSITY[m.material] * 1e-6
        for m in script()
    )
    assert response.json()["properties"]["mass_g"] == pytest.approx(want, rel=1e-12)


def _expected(name: str) -> dict[str, Any]:
    return json.loads((openings.GOLDENS / name / "expected.json").read_text())


def test_the_golden_is_the_two_releases_goldens_added() -> None:
    """b7-opening-update's bodies plus b7-ceiling-joists' 11 joists: each
    joist adds 8 faces, 18 edges, a shell, 36 mesh vertices and 20
    triangles, and its volume, as b7-ceiling-joists adds them to b7-outline."""
    base, tied, new = (
        _expected("b7-opening-update"),
        _expected("b7-ceiling-joists"),
        _expected(NAME),
    )
    outline = _expected("b7-outline")
    for key in ("faces", "edges", "shells"):
        added = tied["topology"][key] - outline["topology"][key]
        assert new["topology"][key] == base["topology"][key] + added
    for key in ("vertices", "triangles"):
        added = tied["mesh"][key] - outline["mesh"][key]
        assert new["mesh"][key] == base["mesh"][key] + added
    added_volume = tied["properties"]["volume"] - outline["properties"]["volume"]
    assert new["properties"]["volume"] == pytest.approx(
        base["properties"]["volume"] + added_volume, abs=2e-5
    )
    assert new["properties"]["volume"] / IN**3 == pytest.approx(290689.350323, abs=1e-4)
    assert new["properties"]["bounding_box"] == base["properties"]["bounding_box"]


def expected_numbers() -> dict[str, Any]:
    """As test_ceiling_joists_b7.expected_numbers, over this script."""
    mine = script()
    area = 0.0
    moments = [0.0, 0.0, 0.0]
    mass = 0.0
    mass_moments = [0.0, 0.0, 0.0]
    vertices = triangles = faces = edges = 0
    total = 0.0
    for m in mine:
        props = measure_shape(m.solid)
        v = float(props.volume)
        total += v
        area += float(props.surface_area)
        c = props.centroid
        density = b7.DENSITY[m.material] * 1e-6
        for k, value in enumerate((c.x, c.y, c.z)):
            moments[k] += v * value
            mass_moments[k] += v * density * value
        mass += v * density
        faces += len(m.solid.faces())
        edges += len(m.solid.edges())
        for face in m.solid.faces():
            loops = face.wires()
            n = sum(len(w.edges()) for w in loops)
            vertices += n
            triangles += n + 2 * (len(loops) - 1) - 2
    bb = [m.solid.bounding_box() for m in mine]
    return {
        "volume": analytic_volume() * IN**3,
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
