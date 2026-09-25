"""Re-derive this golden's analytic volume WITHOUT GProp (review N3 of a0a70ec).

The golden is an r = R disc of height H with N identical slots cut through it,
each bounded by two sketch SPLINES and two lines (model.json). Its volume is

    V = pi R^2 H - N A H

where A, the slot's area, comes from Green's theorem on the slot boundary:

    A = 1/2 closed-integral (x dy - y dx)

evaluated on the very curves the kernel models (``Edge.make_spline`` through
the sketch's fit points, i.e. ``GeomAPI_Interpolate``) by Gauss-Legendre
quadrature on every knot span. On a polynomial span ``x y'`` is a polynomial,
so the rule is exact to float; 8-, 16- and 24-point rules must agree, and the
script checks that they do. No OCCT mass-property integrator is involved, so
this is an independent truth for the one the golden pins.

The analytic SURFACE AREA, 2 (pi R^2 - N A) + 2 pi R H + N P H with P the slot
perimeter, is printed too: expected.json pins the fixed-order reading instead,
which is knowingly 0.264 mm^2 higher (see its derivation notes).

Run: ``uv run python services/geometry/goldens/<this dir>/derive.py`` prints
the numbers and exits non-zero if expected.json's volume disagrees.
``tests/test_golden_derivations.py`` runs the same check in the suite.
"""
# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import itertools
import json
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from build123d import Edge, Vector
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_CurveType
from OCP.gp import gp_Pnt, gp_Vec

HERE = Path(__file__).resolve().parent
QUADRATURE_ORDERS = (8, 16, 24)

#: Largest disagreement (mm^2) allowed between the 8-, 16- and 24-point slot
#: areas. The integrand is polynomial on every span, so they agree to float
#: rounding: measured 2e-14.
ORDER_AGREEMENT_MM2 = 1e-12


@dataclass(frozen=True)
class Derivation:
    slot_area: float
    slot_perimeter: float
    volume: float
    surface_area: float


def _point(raw: dict[str, float]) -> Vector:
    return Vector(raw["x"], raw["y"], 0.0)


def _edge(entity: dict[str, Any]) -> Edge:
    if entity["kind"] == "spline":
        return Edge.make_spline([_point(p) for p in entity["points"]])
    if entity["kind"] == "line":
        return Edge.make_line(_point(entity["start"]), _point(entity["end"]))
    raise ValueError(f"unexpected slot entity {entity['kind']!r}")


def _integrate(edge: Edge, order: int, fn: Callable[[gp_Pnt, gp_Vec], float]) -> float:
    """Integral of fn(point, derivative) over *edge*, Gauss per knot span."""
    curve = BRepAdaptor_Curve(edge.wrapped)
    first, last = curve.FirstParameter(), curve.LastParameter()
    breaks = {first, last}
    if curve.GetType() == GeomAbs_CurveType.GeomAbs_BSplineCurve:
        spline = curve.BSpline()
        breaks |= {spline.Knot(i) for i in range(1, spline.NbKnots() + 1)}
    knots = sorted(k for k in breaks if first <= k <= last)
    nodes, weights = np.polynomial.legendre.leggauss(order)
    total = 0.0
    for a, b in itertools.pairwise(knots):
        for node, weight in zip(nodes, weights, strict=True):
            point, derivative = gp_Pnt(), gp_Vec()
            curve.D1((a + b) / 2 + (b - a) / 2 * float(node), point, derivative)
            total += float(weight) * (b - a) / 2 * fn(point, derivative)
    return total


def _green(point: gp_Pnt, derivative: gp_Vec) -> float:
    return 0.5 * (point.X() * derivative.Y() - point.Y() * derivative.X())


def _speed(_: gp_Pnt, derivative: gp_Vec) -> float:
    return derivative.Magnitude()


def derive(model: dict[str, Any]) -> Derivation:
    """The golden's analytic numbers from its own model.json."""
    features = [item["feature"] for item in model["features"]]
    sketches = [f["params"] for f in features if f["type"] == "sketch"]
    extrudes = [f["params"] for f in features if f["type"] == "extrude"]
    [pattern] = [f["params"]["pattern"] for f in features if f["type"] == "pattern"]
    [disc] = sketches[0]["entities"]
    radius = float(disc["radius"])
    height = float(extrudes[0]["distance_mm"])
    count = int(pattern["count"])
    edges = [_edge(entity) for entity in sketches[1]["entities"]]

    areas = [
        abs(sum(_integrate(edge, order, _green) for edge in edges))
        for order in QUADRATURE_ORDERS
    ]
    spread = max(areas) - min(areas)
    if spread > ORDER_AGREEMENT_MM2:
        raise AssertionError(f"quadrature orders disagree by {spread:.3e} mm^2")
    area = areas[-1]
    perimeter = sum(_integrate(edge, QUADRATURE_ORDERS[-1], _speed) for edge in edges)
    disc_area = math.pi * radius * radius
    return Derivation(
        slot_area=area,
        slot_perimeter=perimeter,
        volume=disc_area * height - count * area * height,
        surface_area=2 * (disc_area - count * area)
        + 2 * math.pi * radius * height
        + count * perimeter * height,
    )


def main() -> int:
    model = json.loads((HERE / "model.json").read_text())
    expected = json.loads((HERE / "expected.json").read_text())
    derived = derive(model)
    pinned = float(expected["properties"]["volume"])
    print(f"slot area      {derived.slot_area!r} mm^2")
    print(f"slot perimeter {derived.slot_perimeter!r} mm")
    print(f"volume         {derived.volume!r} mm^3 (expected.json {pinned!r})")
    print(f"surface area   {derived.surface_area!r} mm^2 (analytic)")
    return 0 if abs(derived.volume - pinned) <= float(expected["tolerance"]) else 1


if __name__ == "__main__":
    sys.exit(main())
