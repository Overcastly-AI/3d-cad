"""Geometry-QA gates for offset-surface bodies (OFFSET-SURFACE-VOLUME-1, `b29fa88`).

Written by geometry QA, independently of the builder (RESEARCH §9,
docs/GEOMETRY-QA.md 2026-09-25):

* The golden ``shell-spline-prism-30x10-t1`` is re-derived by a method that
  shares nothing numerical with its ``derive.py``: no quadrature, but a dense
  polygon through the curve (shoelace), Richardson-extrapolated in the step,
  with the curve evaluated by scipy rather than OCCT. The only OCCT input is the
  interpolating spline's poles and knots, which ARE the sketch's definition.
* A SECOND shelled spline prism (40 wide, 20 tall, 2 mm wall). The shell fitted
  the edge between its offset wall and its open rim to 2.15e-4 mm, above the
  kernel's 1e-4 mm linear tolerance, and the rim face's boundary followed the
  loose fit: the rim enclosed 7.3e-3 mm^2 too little, the volume read
  0.023 mm^3 low, and a STEP re-import (whose reader re-derives that boundary)
  moved the area by the same 7e-3. Pinned first as strict xfails on the rim
  face; the kernel fix (kernel.offset_edges, F1) rebuilds that edge on the
  offset's exact isoline, and they now pass as plain gates.
* No golden needs a looser STEP round trip any more; the override machinery
  stays scoped and empty.
* Every body without an offset face reads byte-for-byte as the pre-``b29fa88``
  adaptive rule did, and the offset golden is the one routed differently.
"""

# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

import importlib.util
import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import FunctionType, ModuleType
from typing import Any, cast

import numpy as np
import pytest
from build123d import Edge, Face, Solid, Vector, Wire, extrude
from geometry.harness import build_model_solid, load_model_request
from geometry.kernel import export_step_bytes
from geometry.kernel.imports import import_step_solid
from geometry.kernel.properties import (
    VOLUME_EPS,
    VolumeReading,
    measure_shape,
    volume_integrand,
    volume_properties,
)
from geometry.kernel.shell import shell_body
from geometry.kernel.types import BodyShape
from geometry.schemas import ShapeProperties
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.GProp import GProp_GProps
from scipy.interpolate import BSpline

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
GOLDEN = "shell-spline-prism-30x10-t1"

#: Relative agreement demanded between this file's polygon truth and the pinned
#: golden values. Measured 2026-09-25: volume 2.5e-14 relative, centroid
#: <= 1.1e-14 relative; the 40-digit mpmath / tanh-sinh re-derivation in
#: docs/GEOMETRY-QA.md agrees with the pinned volume to 6.9e-16 relative.
TRUTH_REL = 1e-10

#: The goldens allowed a looser STEP round trip, and the bound each is allowed.
#: Pinned here AS WELL AS in test_goldens, so adding one needs a geometry-QA
#: edit too (docs/GEOMETRY-QA.md 2026-09-25). EMPTY since F1's fix: the golden's
#: 1e-6 override was retired when its round trip met ROUNDTRIP_TOL (1.3e-8).
REVIEWED_OVERRIDE: dict[str, float] = {}

#: The second case: the golden's shape class, other numbers. Its spline's
#: tightest inward radius of curvature is 2.354 mm against the 2 mm wall, so the
#: inward offset is well posed (no swallowtail), and x decreases strictly
#: along the spline.
CASE2_WIDTH, CASE2_HEIGHT, CASE2_WALL = 40.0, 20.0, 2.0
CASE2_FIT = (
    (40.0, 10.0),
    (32.0, 16.0),
    (24.0, 11.0),
    (16.0, 17.0),
    (8.0, 12.0),
    (0.0, 15.0),
)

#: Bound on the rim face's area error, mm^2. Before F1's fix the golden's rim
#: read 1.2e-7 off its truth and case 2's 7.3e-3 off (the defect); since, both
#: read within 6e-11.
RIM_TOL = 1e-6


@dataclass(frozen=True)
class Truth:
    area: float  # the profile, mm^2
    area_in: float  # the cavity's cross-section (inner parallel region), mm^2
    volume: float
    centroid: tuple[float, float, float]


def _conftest() -> ModuleType:
    """The suite's conftest as a module: importlib mode blocks ``import conftest``,
    and the override lookup under test (``roundtrip_tolerance_for``) is no fixture."""
    spec = importlib.util.spec_from_file_location(
        "offset_qa_conftest", Path(__file__).with_name("conftest.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(name: str) -> dict[str, Any]:
    return json.loads((GOLDENS / name / "model.json").read_text())


def _expected(name: str) -> dict[str, Any]:
    return json.loads((GOLDENS / name / "expected.json").read_text())


def _golden_fit() -> tuple[tuple[float, float], ...]:
    sketch = _load(GOLDEN)["features"][0]["feature"]["params"]
    [spline] = [e for e in sketch["entities"] if e["kind"] == "spline"]
    return tuple((float(p["x"]), float(p["y"])) for p in spline["points"])


@cache
def _polygon_truth(
    width: float, height: float, wall: float, fit: tuple[tuple[float, float], ...]
) -> Truth:
    """The prism over [bottom, right, spline, left], shelled inward by *wall* with
    the top open: the prism minus the inner parallel region from z = wall to
    z = height. Areas and first moments by the shoelace formula on polygons
    through the spline and its exact inward offset, Richardson-extrapolated from
    n and 2n points (error O(h^2) -> O(h^4))."""
    edge = Edge.make_spline([Vector(x, y, 0.0) for x, y in fit])
    spline = BRepAdaptor_Curve(edge.wrapped).BSpline()
    knots: list[float] = []
    for i in range(1, spline.NbKnots() + 1):
        knots += [spline.Knot(i)] * spline.Multiplicity(i)
    poles = np.array(
        [
            (spline.Pole(i).X(), spline.Pole(i).Y())
            for i in range(1, spline.NbPoles() + 1)
        ]
    )
    curve = BSpline(np.array(knots), poles, spline.Degree())
    tangent = curve.derivative(1)
    distinct = list(dict.fromkeys(knots))

    def offset(s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x, y = curve(s).T
        dx, dy = tangent(s).T
        speed = np.hypot(dx, dy)
        return x - wall * dy / speed, y + wall * dx / speed  # the LEFT normal

    def trim(target: float, lo: float, hi: float) -> float:
        """Where the offset crosses x = *target* (x decreases along the curve)."""
        for _ in range(200):
            mid = (lo + hi) / 2
            if float(offset(np.array([mid]))[0][0]) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    sa = trim(width - wall, distinct[0], distinct[1])
    sb = trim(wall, distinct[-2], distinct[-1])

    def moments(n: int, inner: bool) -> np.ndarray:
        if inner:
            x, y = offset(np.linspace(sa, sb, n + 1))
            xs = np.concatenate([[wall, width - wall], x])
            ys = np.concatenate([[wall, wall], y])
        else:
            x, y = curve(np.linspace(distinct[0], distinct[-1], n + 1)).T
            xs = np.concatenate([[0.0, width], x])
            ys = np.concatenate([[0.0, 0.0], y])
        x1, y1 = np.roll(xs, -1), np.roll(ys, -1)
        cross = xs * y1 - x1 * ys
        return np.array(
            [
                cross.sum() / 2,
                ((xs + x1) * cross).sum() / 6,
                ((ys + y1) * cross).sum() / 6,
            ]
        )

    def extrapolated(inner: bool) -> np.ndarray:
        coarse, fine = moments(40_000, inner), moments(80_000, inner)
        return (4 * fine - coarse) / 3

    (area, mx, my), (area_in, mx_in, my_in) = extrapolated(False), extrapolated(True)
    cavity = height - wall
    volume = area * height - area_in * cavity
    return Truth(
        area=float(area),
        area_in=float(area_in),
        volume=float(volume),
        centroid=(
            float((mx * height - mx_in * cavity) / volume),
            float((my * height - my_in * cavity) / volume),
            float(
                (area * height**2 / 2 - area_in * (height**2 - wall**2) / 2) / volume
            ),
        ),
    )


@cache
def _case2() -> Solid:
    """Case 2 through the kernel's own ``shell_body``: the function the tree's
    shell feature dispatches to. Built directly because evaluating the tree
    costs ~52 s (it integrates the volume by Gauss-Kronrod, F2); the tree path
    was measured to give the identical body (volume 4913.629446363646 both
    ways, docs/GEOMETRY-QA.md 2026-09-25)."""
    w, fit = CASE2_WIDTH, CASE2_FIT
    wire = Wire(
        [
            Edge.make_line((0, 0, 0), (w, 0, 0)),
            Edge.make_line((w, 0, 0), (w, fit[0][1], 0)),
            Edge.make_spline([Vector(x, y, 0) for x, y in fit]),
            Edge.make_line((0, fit[-1][1], 0), (0, 0, 0)),
        ]
    )
    prism = extrude(Face(wire), CASE2_HEIGHT)
    top = max(prism.faces(), key=lambda f: f.center().Z)
    body = shell_body(prism, [top], CASE2_WALL)
    assert isinstance(body, Solid)
    return body


def _rim_area(body: BodyShape, height: float) -> float:
    """Converged area of the open rim: the planar face at z = *height* (a plane's
    adaptive area converges; this is not the fixed-order reading)."""
    [rim] = [
        f
        for f in body.faces()
        if BRepAdaptor_Surface(f.wrapped).GetType() == GeomAbs_SurfaceType.GeomAbs_Plane
        and abs(f.center().Z - height) < 1e-9
    ]
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(rim.wrapped, props, 1e-12)
    return float(props.Mass())


def _reimport(body: BodyShape) -> BodyShape:
    """Through the product's own STEP export and import paths."""
    return import_step_solid(export_step_bytes(body).decode())


def _adaptive(shape: BodyShape) -> VolumeReading:
    """The pre-b29fa88 rule, verbatim: adaptive at VOLUME_EPS on the integrand."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(
        volume_integrand(shape), props, VOLUME_EPS, False, False
    )
    centre = props.CentreOfMass()
    return VolumeReading(
        volume=float(props.Mass()),
        centroid=(float(centre.X()), float(centre.Y()), float(centre.Z())),
    )


# --- 1. the golden's truth, re-derived without quadrature ---------------------


def test_the_golden_truth_holds_under_an_independent_method() -> None:
    expected = _expected(GOLDEN)["properties"]
    truth = _polygon_truth(30.0, 10.0, 1.0, _golden_fit())
    assert truth.volume == pytest.approx(expected["volume"], rel=TRUTH_REL)
    pinned = expected["centroid"]
    assert truth.centroid == pytest.approx(
        (pinned["x"], pinned["y"], pinned["z"]), rel=TRUTH_REL
    )


def test_the_golden_rim_encloses_its_true_area() -> None:
    """The control for the case-2 xfails below: on the golden the same
    measurement passes (the rim is 1.2e-7 mm^2 off, the loose edge 1.0e-5)."""
    truth = _polygon_truth(30.0, 10.0, 1.0, _golden_fit())
    body = build_model_solid(load_model_request(json.dumps(_load(GOLDEN))))
    assert _rim_area(body, 10.0) == pytest.approx(
        truth.area - truth.area_in, abs=RIM_TOL
    )


# --- 2. a second offset case: the shell's rim edge is fitted too loosely -----


def test_the_second_case_is_the_shell_it_claims_to_be() -> None:
    """Guards the two xfails below against failing for the wrong reason: the case
    must build as the 11-face, 24-edge open shell, with the rim within the
    defect's size (7e-3 mm^2) of the truth, never a solid prism's top face."""
    body = _case2()
    truth = _polygon_truth(CASE2_WIDTH, CASE2_HEIGHT, CASE2_WALL, CASE2_FIT)
    assert (len(body.faces()), len(body.edges())) == (11, 24)
    assert _rim_area(body, CASE2_HEIGHT) == pytest.approx(
        truth.area - truth.area_in, abs=0.05
    )


def test_a_second_shelled_spline_prism_encloses_its_true_rim() -> None:
    """GEOMETRY-QA 2026-09-25 F1, fixed: the shell fitted the rim edge to
    2.15e-4 mm, so the rim enclosed 7.3e-3 mm^2 too little and the volume read
    0.023 mm^3 low. Rebuilt on the isoline, the rim is within 6e-11."""
    truth = _polygon_truth(CASE2_WIDTH, CASE2_HEIGHT, CASE2_WALL, CASE2_FIT)
    assert _rim_area(_case2(), CASE2_HEIGHT) == pytest.approx(
        truth.area - truth.area_in, abs=RIM_TOL
    )


def test_a_second_shelled_spline_prism_round_trips_its_rim() -> None:
    """GEOMETRY-QA 2026-09-25 F1, fixed: the STEP reader re-derived the loose rim
    boundary, so the re-imported rim moved by 7e-3 mm^2 (volume +2.3e-2)."""
    body = _case2()
    assert _rim_area(_reimport(body), CASE2_HEIGHT) == pytest.approx(
        _rim_area(body, CASE2_HEIGHT), abs=RIM_TOL
    )


# --- 3. the round-trip override stays scoped and dies with its reason --------


def test_the_override_is_exactly_the_reviewed_one() -> None:
    declared = {
        path.parent.name: json.loads(path.read_text())["roundtrip_tolerance"]
        for path in sorted(GOLDENS.glob("*/expected.json"))
        if "roundtrip_tolerance" in json.loads(path.read_text())
    }
    assert declared == REVIEWED_OVERRIDE
    conftest = _conftest()
    assert conftest.ROUNDTRIP_TOL == 1e-7
    names = [p.parent.name for p in GOLDENS.glob("*/model.json")]
    assert len(names) > 1
    for name in [*names, "not-a-golden"]:
        want = REVIEWED_OVERRIDE.get(name, conftest.ROUNDTRIP_TOL)
        assert conftest.roundtrip_tolerance_for(name) == want, name


#: A drift the shared bound rejects and a 1e-6 override would absorb, mm.
_DRIFT_MM = 1e-6


@pytest.mark.parametrize(
    ("field", "loosened"),
    [("volume", True), ("surface_area", True), ("centroid", False), ("bbox", False)],
)
def test_an_override_loosens_only_volume_and_area(
    assert_roundtrip_preserved: Callable[[str, ShapeProperties, ShapeProperties], None],
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    loosened: bool,
) -> None:
    """GEOMETRY-QA 2026-09-25 F5: an override was measured on the integrals, so
    it widens volume and area only; the centroid and bounds keep ROUNDTRIP_TOL."""

    def loosened_everywhere(_name: str) -> float:
        return 10 * _DRIFT_MM

    # The check reads the lookup from conftest's globals at call time.
    monkeypatch.setitem(
        cast(FunctionType, assert_roundtrip_preserved).__globals__,
        "roundtrip_tolerance_for",
        loosened_everywhere,
    )
    original = measure_shape(Solid.make_box(10, 20, 30))
    centroid = original.centroid.model_copy(
        update={"x": original.centroid.x + _DRIFT_MM}
    )
    top = original.bounding_box.max.model_copy(
        update={"z": original.bounding_box.max.z + _DRIFT_MM}
    )
    drifted = {
        "volume": original.model_copy(update={"volume": original.volume + _DRIFT_MM}),
        "surface_area": original.model_copy(
            update={"surface_area": original.surface_area + _DRIFT_MM}
        ),
        "centroid": original.model_copy(update={"centroid": centroid}),
        "bbox": original.model_copy(
            update={
                "bounding_box": original.bounding_box.model_copy(update={"max": top})
            }
        ),
    }[field]
    if loosened:
        assert_roundtrip_preserved("an-overridden-golden", drifted, original)
    else:
        with pytest.raises(AssertionError, match=f"round-trip {field}"):
            assert_roundtrip_preserved("an-overridden-golden", drifted, original)


# --- 4. every other body reads exactly as before ------------------------------

#: Goldens whose faces exercise every integrand branch that is NOT an offset:
#: spline extrusions (NURBS twins), a revolve, a loft, a sweep, a twist, a shell
#: of planes, a fillet. Listed, not discovered, so a rename fails loudly.
UNCHANGED = (
    "sketch-spline-extrude",
    "extrude-cut-spline-slots-6x-disc-r20-h10",
    "revolve-vbelt-pulley-od100-bore16",
    "loft-spline-sections-nurbs-h30",
    "sweep-circle-r8-h30",
    "extrude-twist-square20-hole-r3-h30-30deg",
    "shell-open-top-box-40x25x10-t2",
    "fillet-top-edge-40x25x10-r5",
)


@pytest.mark.parametrize("name", UNCHANGED)
def test_a_body_without_offset_faces_reads_byte_for_byte_as_before(name: str) -> None:
    body = build_model_solid(load_model_request(json.dumps(_load(name))))
    assert volume_properties(body) == _adaptive(body)


def test_the_offset_golden_is_the_one_routed_differently() -> None:
    body = build_model_solid(load_model_request(json.dumps(_load(GOLDEN))))
    routed, adaptive = volume_properties(body), _adaptive(body)
    truth = _expected(GOLDEN)["properties"]["volume"]
    assert abs(routed.volume - truth) < 5e-7
    assert abs(adaptive.volume - truth) > 1.0  # the unrouted +1.61 mm^3
