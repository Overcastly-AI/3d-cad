"""ROOF-MEMBER-RENUMBER acceptance on the kernel: a 1 in hole stays in its
rafter through the edits that renumbered ``loft.roof`` 1.2.0's members.

Four goldens, B3's hip roof at 1.3.0 (typed bearing: walls' outer faces X
0..144, Y 0..120, plates 97.125 high and 3.5 deep, 2x6 commons and jacks at
24 o.c., 12 in level overhang, 2x8 ridge and dropped hips, SPF) plus a hole
along X through one rafter, named by id, centred 20 in from the front wall at
Z 110 (``packages/loft-plugins/tests/test_roof_member_names.py`` pins the
models):

* ``b3-hip-v1.3-hole-common`` and ``-168-hole-common``: through the front
  ridge-end common (``common/front/ridge/start``, X 59.25..60.75), with the
  roof 144 and 168 long (lengthened by one spacing);
* ``b3-hip-v1.3-hole-jack`` and ``-8-12-hole-jack``: through the front jack
  next to the left hip's ridge end (``jack/front/left/1``, X 35.25..36.75),
  at 6/12 and 8/12.

Every number is derived here, never read from the kernel: from the base
goldens ``b3-hip-6-12`` and ``b3-hip-8-12`` (1.1.0, hand-derived from
buildings.md) and closed forms.

1. **1.1.0 -> 1.3.0.** 1.3.0 is 1.2.0 renamed, and 1.2.0 differs from 1.1.0
   on B3 only by ROOF-HIP-TAIL: each hip's tail is ripped parallel to its top
   to the commons' depth less the hip's drop, so its lowest edge meets the
   commons' undersides. Over the overhang (outside a wall) a hip of plumb
   depth P loses a band of constant vertical thickness d = P - (Pc - drop)
   (Pc the commons' plumb cut) over its plan there: for each q across its
   thickness t (|q| <= t/2), s along it from |q| - oh sqrt 2 to |q|, so the
   plan is t x oh sqrt 2 and the rip is a sheared prism of volume
   d t oh sqrt 2. Inside the walls the band lies below the plate, where the
   seat already removed it (the step is there too). The hip loses the band
   from its four vertical faces round that plan (two sides oh sqrt 2 long,
   two cheeks and two heels t / sqrt 2 long): area d sqrt 2 (2 oh + 2 t);
   its bottom moves up unchanged in shape, so the topology is unchanged. The
   band's centroid is above s = t/4 - oh sqrt 2 / 2 on the centreline, at
   the top line there less (P + Pc - drop) / 2. The four corners are mirror
   images, so X and Y of the centroid stay; the lowest point is now the
   commons' tail bottom, plate - (oh + seat) rise/12.
2. **Lengthening by one spacing** (168): the right half (its hips, jacks,
   king and ridge end) moves 24 in +X, a pair of commons is added (each the
   1.5 in extrusion of the common's side profile, buildings.md: tail plumb
   cut, birdsmouth, ridge plumb cut 59.25 from the wall) and the ridge grows
   24 (a 1.5 x 7.25 section, its top the commons' top at its face). The roof
   is symmetric about X 84, so that is the centroid's X.
3. **The hole**: pi r^2 L out (r 0.5, L 1.5), the bore's wall in less its two
   discs (pi (2 r L - 2 r^2)), one cylindrical face with two circles and a
   seam; centroid and centre of mass re-weighted.
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
R2 = math.sqrt(2.0)
#: SPF (every member: rafter and ridge material), g/mm^3.
DENSITY = 450.0 * 1e-6
RADIUS = 0.5
#: B3: plate height and width, overhang, half span, member sizes (in).
PLATE, PLATE_W, OH, HALF = 97.125, 3.5, 12.0, 60.0
T, RAFTER_D, RIDGE_D, HIP_T, HIP_D = 1.5, 5.5, 7.25, 1.5, 7.25


@dataclass(frozen=True)
class Roof:
    """B3's closed forms at *rise* per 12 (inches)."""

    rise: int

    @property
    def k(self) -> float:
        return self.rise / 12

    @property
    def seat(self) -> float:
        """The birdsmouth seat: the plate, unless the heel would pass 1/3."""
        return min(PLATE_W, RAFTER_D / 3 / self.k)

    @property
    def plumb(self) -> float:
        return RAFTER_D * math.hypot(12, self.rise) / 12

    @property
    def hap(self) -> float:
        """Height above plate at the wall's face: plumb cut less the heel."""
        return self.plumb - self.seat * self.k

    @property
    def hip_plumb(self) -> float:
        return HIP_D * math.hypot(12 * R2, self.rise) / (12 * R2)

    @property
    def m(self) -> float:
        """Rise per unit of plan run along a hip."""
        return self.k / R2

    @property
    def drop(self) -> float:
        return HIP_T / 2 * self.m

    def common_profile(self) -> list[tuple[float, float]]:
        """A common's side profile (d from the wall's face, z), ridge face
        at d = 60 - 0.75."""
        r = HALF - T / 2

        def bottom(d: float) -> float:
            return PLATE + (d - self.seat) * self.k

        return [
            (-OH, bottom(-OH)),
            (0.0, PLATE - self.seat * self.k),
            (0.0, PLATE),
            (self.seat, PLATE),
            (r, bottom(r)),
            (r, bottom(r) + self.plumb),
            (-OH, bottom(-OH) + self.plumb),
        ]

    def common(self) -> tuple[float, float, float]:
        """One common: volume, area, centroid z (polygon closed forms)."""
        pts = self.common_profile()
        n = len(pts)
        cross = [
            pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
            for i in range(n)
        ]
        area = sum(cross) / 2
        cz = sum((pts[i][1] + pts[(i + 1) % n][1]) * cross[i] for i in range(n)) / (
            6 * area
        )
        perimeter = sum(math.dist(pts[i], pts[(i + 1) % n]) for i in range(n))
        return area * T, 2 * area + perimeter * T, cz

    def ridge(self) -> tuple[float, float]:
        """The ridge: section area and its centroid z (top at the commons'
        top at its face, 59.25 from the wall)."""
        top = PLATE + self.hap + self.k * (HALF - T / 2)
        return T * RIDGE_D, top - RIDGE_D / 2

    def rip(self) -> tuple[float, float, float]:
        """One hip tail's rip: volume, area lost, centroid z."""
        d = self.hip_plumb - (self.plumb - self.drop)
        volume = d * HIP_T * OH * R2
        area = d * R2 * (2 * OH + 2 * HIP_T)
        s = HIP_T / 4 - OH * R2 / 2
        top = PLATE + self.hap - self.drop + self.m * s
        return volume, area, top - (self.hip_plumb + self.plumb - self.drop) / 2


@dataclass(frozen=True)
class Golden:
    base: str  # the 1.1.0 golden at this pitch
    rise: int
    lengthened: bool  # 168 instead of 144
    hole_x: float  # the hole's centre X (in): the rafter's centre plane


GOLDENS_1_3: dict[str, Golden] = {
    "b3-hip-v1.3-hole-common": Golden("b3-hip-6-12", 6, False, 60.0),
    "b3-hip-v1.3-168-hole-common": Golden("b3-hip-6-12", 6, True, 60.0),
    "b3-hip-v1.3-hole-jack": Golden("b3-hip-6-12", 6, False, 36.0),
    "b3-hip-v1.3-8-12-hole-jack": Golden("b3-hip-8-12", 8, False, 36.0),
}
each_golden = pytest.mark.parametrize("name", sorted(GOLDENS_1_3))


def _expected(name: str) -> dict[str, Any]:
    return json.loads((GOLDENS / name / "expected.json").read_text())


class _Sum:
    """Volume, area, mass and their first moments, in mm."""

    def __init__(self, props: dict[str, Any]) -> None:
        self.volume = props["volume"]
        self.area = props["surface_area"]
        self.mass = props["mass_g"]
        self.vm = [self.volume * props["centroid"][a] for a in "xyz"]
        self.mm = [self.mass * props["center_of_mass"][a] for a in "xyz"]

    def add(
        self, volume_in3: float, centre_in: tuple[float, ...], area_in2: float
    ) -> None:
        v = volume_in3 * IN**3
        self.volume += v
        self.area += area_in2 * IN**2
        self.mass += DENSITY * v
        for i in range(3):
            self.vm[i] += v * centre_in[i] * IN
            self.mm[i] += DENSITY * v * centre_in[i] * IN


def derived(name: str) -> dict[str, Any]:
    """The golden's properties and topology (module docstring)."""
    golden = GOLDENS_1_3[name]
    base = _expected(golden.base)
    props, box = base["properties"], base["properties"]["bounding_box"]
    roof = Roof(golden.rise)
    total = _Sum(props)
    gx, gy = props["centroid"]["x"] / IN, props["centroid"]["y"] / IN
    # 1. The four ripped hip tails, mirror images about the centre (gx, gy).
    v_rip, a_rip, z_rip = roof.rip()
    total.add(-4 * v_rip, (gx, gy, z_rip), -4 * a_rip)
    x_max = box["max"]["x"]
    faces, edges, shells = (base["topology"][k] for k in ("faces", "edges", "shells"))
    if golden.lengthened:
        # 2. The right half moves 24 +X (moment only), plus a pair of commons
        # and 24 of ridge; the roof is then symmetric about X 84.
        v_c, a_c, z_c = roof.common()
        ridge_area, z_ridge = roof.ridge()
        total.add(2 * v_c, (0.0, gy, z_c), 2 * a_c)
        total.add(ridge_area * 24, (0.0, gy, z_ridge), 24 * 2 * (T + RIDGE_D))
        total.vm[0] = total.volume * 84 * IN
        total.mm[0] = total.mass * 84 * IN
        x_max += 24 * IN
        faces, edges, shells = faces + 18, edges + 42, shells + 2
    # 3. The hole.
    bore = math.pi * RADIUS**2 * T
    total.add(
        -bore,
        (golden.hole_x, 20.0, 110.0),
        math.pi * (2 * RADIUS * T - 2 * RADIUS**2),
    )
    low = (PLATE - (OH + roof.seat) * roof.k) * IN
    return {
        "properties": {
            "volume": total.volume,
            "surface_area": total.area,
            "centroid": {a: total.vm[i] / total.volume for i, a in enumerate("xyz")},
            "mass_g": total.mass,
            "center_of_mass": {
                a: total.mm[i] / total.mass for i, a in enumerate("xyz")
            },
            "bounding_box": {
                "min": {**box["min"], "z": low},
                "max": {**box["max"], "x": x_max},
            },
        },
        "topology": {"faces": faces + 1, "edges": edges + 3, "shells": shells},
    }


def test_the_rip_is_research_s_45_967() -> None:
    """RESEARCH §23 (ROOF-HIP-TAIL): each B4 hip loses 45.967 in^3 at 6/12."""
    assert Roof(6).rip()[0] == pytest.approx(45.967, abs=5e-4)


@each_golden
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


@each_golden
def test_the_hole_is_in_the_rafter_the_boolean_names(name: str) -> None:
    """The Boolean's target has lost the bore and no other body has: every
    other body's mass is what it is without the hole."""
    request = _request(name)
    cut = request.features[-1].feature
    assert isinstance(cut, BooleanFeature) and cut.params.operation == "subtract"
    holed = client.post("/api/v1/evaluate", json=request.model_dump(mode="json"))
    plain = request.model_copy(update={"features": request.features[:-4]})
    whole = client.post("/api/v1/evaluate", json=plain.model_dump(mode="json"))
    assert holed.status_code == whole.status_code == 200
    with_hole = {b["base_feature_id"]: b["mass_g"] for b in holed.json()["bodies"]}
    without = {b["base_feature_id"]: b["mass_g"] for b in whole.json()["bodies"]}
    target = str(cut.params.target.feature_id)
    assert with_hole.keys() == without.keys()
    bore = DENSITY * math.pi * RADIUS**2 * T * IN**3
    assert with_hole[target] == pytest.approx(without[target] - bore, abs=1e-9)
    for key, mass in with_hole.items():
        if key != target:
            assert mass == pytest.approx(without[key], abs=1e-9), key


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("b3-hip-v1.3-hole-common", "b3-hip-v1.3-168-hole-common"),
        ("b3-hip-v1.3-hole-jack", "b3-hip-v1.3-8-12-hole-jack"),
    ],
)
def test_the_edit_keeps_the_target(before: str, after: str) -> None:
    """Lengthened one spacing, re-pitched: the Boolean names the same member
    id, a body of both expansions."""

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

    for name, golden in sorted(GOLDENS_1_3.items()):
        base = _expected(golden.base)
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
        props = meta.properties
        print(name, props.topology, want["topology"])
        for key in ("volume", "surface_area", "mass_g"):
            print("  ", key, getattr(props, key) - want["properties"][key])
        for key in ("centroid", "center_of_mass"):
            got = getattr(props, key)
            print(
                "  ", key, [getattr(got, a) - want["properties"][key][a] for a in "xyz"]
            )
        print("   bbox", props.bounding_box, want["properties"]["bounding_box"])
