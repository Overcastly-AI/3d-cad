"""WALL-MEMBER-RENUMBER acceptance on the kernel: a 1 in hole stays in its
member through the edit that renumbered 1.0.0's members.

Four goldens, each a 1.0.0 golden's model at 1.1.0 (the same bodies under
stable names, ``packages/loft-plugins/tests/test_member_names.py``) plus a
hole: a 1 in circle extruded as a new body and subtracted (a Boolean) from
one member, named by id.

* ``b2-walls-v1.1-hole-stud-128`` and ``-door-moved-24``: B2's walls with the
  door at 72 and at 48 along the front wall, the hole along Y through the
  front wall's stud at 128 along the wall (world X 16) at Z 48;
* ``plugin-deck-v1.1-b1-16ft-hole-end-joist`` and ``-20ft-``: B1 at 16 and
  20 ft, the hole along X through the end joist at Y 72, Z 24.375.

Every number is derived here from the base golden's hand-derived expectation
(itself typed from buildings.md) and the cylinder's closed form, never from
the kernel: volume less pi r^2 L, area plus the bore's wall less its two
discs, centroid and centre of mass re-weighted by the cylinder at its centre,
mass less density x pi r^2 L, the box and its shells unchanged, and one
cylindrical face with its two circles and seam added. The kernel then has
to meet them (test_goldens.py), and here the hole has to be in the member
the Boolean names, before and after the edit.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from geometry.main import app
from loft_wire.features import BooleanFeature, EvaluateTreeRequest

client = TestClient(app)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
IN = 25.4
RADIUS = 0.5 * IN


@dataclass(frozen=True)
class Hole:
    """A 1 in hole through one member: the golden it is added to, its length
    through the member and the member's box volume (in, in^3), the
    cylinder's centre (in) and the member's density (kg/m^3)."""

    base: str
    length: float
    member_volume: float
    centre: tuple[float, float, float]
    density: float


#: A 2x4 stud is 1.5 x 3.5 x 92.625 (SPF, 450 kg/m^3); a 2x10 joist is
#: 1.5 x 9.25 x 141 (PT, 582). Through the stud's 3.5 depth at world X 16,
#: Z 48; through the end joist's 1.5 at Y 72 and the joist's mid-depth,
#: 19.75 + 9.25 / 2 = 24.375, its centre 0.75 inside the deck's side.
HOLES: dict[str, Hole] = {
    "b2-walls-v1.1-hole-stud-128": Hole(
        "b2-walls-door-window", 3.5, 1.5 * 3.5 * 92.625, (16, 1.75, 48), 450.0
    ),
    "b2-walls-v1.1-hole-door-moved-24": Hole(
        "b2-walls-door-moved-24", 3.5, 1.5 * 3.5 * 92.625, (16, 1.75, 48), 450.0
    ),
    "plugin-deck-v1.1-b1-16ft-hole-end-joist": Hole(
        "plugin-deck-v1-b1-12x16ft", 1.5, 1.5 * 9.25 * 141, (191.25, 72, 24.375), 582.0
    ),
    "plugin-deck-v1.1-b1-20ft-hole-end-joist": Hole(
        "plugin-deck-v1-b1-20ft", 1.5, 1.5 * 9.25 * 141, (239.25, 72, 24.375), 582.0
    ),
}

each_hole = pytest.mark.parametrize("name", sorted(HOLES))


def _expected(name: str) -> dict[str, Any]:
    return json.loads((GOLDENS / name / "expected.json").read_text())


def _bore(hole: Hole) -> tuple[float, float, tuple[float, ...]]:
    """The removed cylinder: volume (mm^3), area change (mm^2), centre (mm)."""
    length = hole.length * IN
    volume = math.pi * RADIUS**2 * length
    area = 2 * math.pi * RADIUS * length - 2 * math.pi * RADIUS**2
    return volume, area, tuple(c * IN for c in hole.centre)


def derived(name: str) -> dict[str, Any]:
    """The golden's properties and topology, from its base golden's and the
    cylinder's closed form (module docstring)."""
    hole = HOLES[name]
    base = _expected(hole.base)
    props = base["properties"]
    v, a, c = _bore(hole)
    volume = props["volume"] - v
    density = hole.density * 1e-6  # g/mm^3
    mass = props["mass_g"] - density * v

    def weighted(total: float, at: dict[str, float], less: float) -> dict[str, float]:
        return {
            axis: (total * at[axis] - less * c[i]) / (total - less)
            for i, axis in enumerate("xyz")
        }

    topology = base["topology"]
    return {
        "properties": {
            "volume": volume,
            "surface_area": props["surface_area"] + a,
            "centroid": weighted(props["volume"], props["centroid"], v),
            "mass_g": mass,
            "center_of_mass": weighted(
                props["mass_g"], props["center_of_mass"], density * v
            ),
            "bounding_box": props["bounding_box"],
        },
        # One cylindrical face, bounded by two circles and its seam.
        "topology": {
            "faces": topology["faces"] + 1,
            "edges": topology["edges"] + 3,
            "shells": topology["shells"],
        },
    }


@each_hole
def test_the_pinned_numbers_are_the_derived_ones(name: str) -> None:
    expected, want = _expected(name), derived(name)
    assert expected["topology"] == want["topology"]
    got, need = expected["properties"], want["properties"]
    assert got["bounding_box"] == need["bounding_box"]
    for key in ("volume", "surface_area", "mass_g"):
        assert got[key] == pytest.approx(need[key], rel=1e-15, abs=0), key
    for key in ("centroid", "center_of_mass"):
        for axis in "xyz":
            assert got[key][axis] == pytest.approx(need[key][axis], rel=1e-15), key


def _request(name: str) -> EvaluateTreeRequest:
    return EvaluateTreeRequest.model_validate_json(
        (GOLDENS / name / "model.json").read_text()
    )


@each_hole
def test_the_hole_is_in_the_member_the_boolean_names(name: str) -> None:
    """The Boolean's target body has lost the bore and no other body has:
    its mass is the member's box less the bore, and the bodies sum to the
    golden's mass with that one change."""
    request = _request(name)
    cut = request.features[-1].feature
    assert isinstance(cut, BooleanFeature) and cut.params.operation == "subtract"
    response = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert all(f["status"] == "ok" for f in body["features"])
    hole = HOLES[name]
    v, _, _ = _bore(hole)
    density = hole.density * 1e-6
    masses = {b["base_feature_id"]: b["mass_g"] for b in body["bodies"]}
    target = str(cut.params.target.feature_id)
    want = density * (hole.member_volume * IN**3 - v)
    assert masses[target] == pytest.approx(want, abs=1e-9)
    others = sum(m for k, m in masses.items() if k != target)
    base_mass = _expected(hole.base)["properties"]["mass_g"]
    assert others == pytest.approx(
        base_mass - density * hole.member_volume * IN**3, abs=1e-6
    )


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("b2-walls-v1.1-hole-stud-128", "b2-walls-v1.1-hole-door-moved-24"),
        (
            "plugin-deck-v1.1-b1-16ft-hole-end-joist",
            "plugin-deck-v1.1-b1-20ft-hole-end-joist",
        ),
    ],
)
def test_the_edit_keeps_the_target(before: str, after: str) -> None:
    """The door moved 24 in, the deck widened 4 ft: the Boolean names the
    same member id, and that id is a member body of both expansions."""

    def target(name: str) -> str:
        request = _request(name)
        cut = request.features[-1].feature
        assert isinstance(cut, BooleanFeature)
        ids = {str(f.id) for f in request.features if f.feature.type == "extrude"}
        assert str(cut.params.target.feature_id) in ids
        return str(cut.params.target.feature_id)

    assert target(before) == target(after)


if __name__ == "__main__":
    # Write each golden's expected.json from its derivation; the mesh counts
    # alone are the kernel's, recorded (the tessellation of the bore).
    from geometry.harness import evaluate_model, load_model_request

    for name, hole in sorted(HOLES.items()):
        base = _expected(hole.base)
        want = derived(name)
        _, meta = evaluate_model(
            load_model_request((GOLDENS / name / "model.json").read_text())
        )
        out: dict[str, Any] = {
            "description": "",
            "derivation": [],
            "tolerance": base["tolerance"],
            "tolerance_rationale": "",
            "roundtrip_tolerance": base["roundtrip_tolerance"],
            "roundtrip_tolerance_rationale": "",
            **want,
            "mesh": {"vertices": meta.mesh.vertices, "triangles": meta.mesh.triangles},
        }
        path = GOLDENS / name / "expected.json"
        if path.exists():
            kept = json.loads(path.read_text())
            for key in ("description", "derivation", "tolerance_rationale"):
                out[key] = kept[key]
            out["roundtrip_tolerance_rationale"] = kept["roundtrip_tolerance_rationale"]
        path.write_text(json.dumps(out, indent=2) + "\n")
        print(name, meta.properties.topology, want["topology"])
