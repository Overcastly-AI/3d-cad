"""Re-derive this golden's analytic mass properties WITHOUT GProp.

The golden (model.json) is a prism of height H over a profile bounded by a
bottom line y = 0, two vertical lines x = 0 and x = W, and a sketch SPLINE
across the top, shelled INWARD by t with the top face open. The shell is the
prism minus a cavity: the region inside the profile at distance >= t from its
boundary (the inner parallel region), from z = t to z = H. So

    V = A H - A_in (H - t)

A is Green's theorem on the profile: 1/2 closed-integral (x dy - y dx). A_in is
Green's theorem on the cavity's boundary: the offset lines y = t, x = t and
x = W - t, and the spline's EXACT inward offset O(s) = C(s) + t n(s), n the
unit left normal of the counter-clockwise loop, trimmed where it meets the
offset verticals (solved by bisection). O'(s) comes in closed form from C' and
C''. The first moments use the same boundary integrals (int x dA = closed-integral
x^2/2 dy, int y dA = -closed-integral y^2/2 dx), so the centroid is analytic
too.

The spline terms are integrated by Gauss-Legendre on every knot span, at four
increasing orders and subdivisions. On the profile they are polynomial, so
exact to float; the offset's are not (its normal divides by |C'|), so the
script requires the orders to agree to 1e-10 before it reports.

Nothing here calls an OCCT mass-property integrator, so this is an
independent truth for what the golden pins. Only the curve (the kernel's
``Edge.make_spline`` through the sketch fit points) is taken from OCCT.

Run: ``uv run python services/geometry/goldens/<this dir>/derive.py`` prints
the numbers and exits non-zero if expected.json disagrees with them.
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
from OCP.gp import gp_Pnt, gp_Vec

HERE = Path(__file__).resolve().parent

#: (Gauss order, subdivisions per knot span) of the successive integrations.
RULES = ((8, 1), (16, 2), (24, 4), (32, 8))

#: Largest disagreement allowed between the last two rules, relative to the
#: quantity. Measured: the volume moves by 6e-15 between them.
RULE_AGREEMENT = 1e-10

Point = tuple[float, float]


@dataclass(frozen=True)
class Derivation:
    volume: float
    centroid: tuple[float, float, float]
    surface_area: float
    max_y: float


def _integrate(
    fn: Callable[[float], float], breaks: list[float], rule: tuple[int, int]
) -> float:
    order, split = rule
    nodes, weights = np.polynomial.legendre.leggauss(order)
    total = 0.0
    for a, b in itertools.pairwise(breaks):
        for k in range(split):
            lo, hi = a + (b - a) * k / split, a + (b - a) * (k + 1) / split
            for node, weight in zip(nodes, weights, strict=True):
                total += (
                    float(weight)
                    * (hi - lo)
                    / 2
                    * fn((lo + hi) / 2 + (hi - lo) / 2 * float(node))
                )
    return total


class _Spline:
    def __init__(self, points: list[Point]) -> None:
        edge = Edge.make_spline([Vector(x, y, 0.0) for x, y in points])
        self.curve = BRepAdaptor_Curve(edge.wrapped)
        spline = self.curve.BSpline()
        self.knots = [spline.Knot(i) for i in range(1, spline.NbKnots() + 1)]

    def d2(self, s: float) -> tuple[Point, Point, Point]:
        p, v1, v2 = gp_Pnt(), gp_Vec(), gp_Vec()
        self.curve.D2(s, p, v1, v2)
        return (p.X(), p.Y()), (v1.X(), v1.Y()), (v2.X(), v2.Y())

    def point(self, s: float) -> tuple[Point, Point]:
        position, tangent, _ = self.d2(s)
        return position, tangent

    def offset(self, s: float, t: float) -> tuple[Point, Point]:
        """Point and derivative of C(s) + t n(s), n the unit LEFT normal."""
        (x, y), (dx, dy), (ddx, ddy) = self.d2(s)
        speed = math.hypot(dx, dy)
        dspeed = (dx * ddx + dy * ddy) / speed
        nx, ny = -dy / speed, dx / speed
        dnx = (-ddy * speed + dy * dspeed) / speed**2
        dny = (ddx * speed - dx * dspeed) / speed**2
        return (x + t * nx, y + t * ny), (dx + t * dnx, dy + t * dny)


def _moments_segment(p: Point, q: Point) -> tuple[float, float, float]:
    """(area, int x dA, int y dA) contributions of a straight boundary segment."""
    (x0, y0), (x1, y1) = p, q
    return (
        0.5 * (x0 * y1 - y0 * x1),
        0.5 * (y1 - y0) * (x0 * x0 + x0 * x1 + x1 * x1) / 3,
        -0.5 * (x1 - x0) * (y0 * y0 + y0 * y1 + y1 * y1) / 3,
    )


def _moments_curve(
    evaluate: Callable[[float], tuple[Point, Point]],
    breaks: list[float],
    rule: tuple[int, int],
) -> tuple[float, float, float]:
    def area(s: float) -> float:
        (x, y), (dx, dy) = evaluate(s)
        return 0.5 * (x * dy - y * dx)

    def first_x(s: float) -> float:
        (x, _), (_, dy) = evaluate(s)
        return 0.5 * x * x * dy

    def first_y(s: float) -> float:
        (_, y), (dx, _) = evaluate(s)
        return -0.5 * y * y * dx

    return (
        _integrate(area, breaks, rule),
        _integrate(first_x, breaks, rule),
        _integrate(first_y, breaks, rule),
    )


def _length(
    evaluate: Callable[[float], tuple[Point, Point]],
    breaks: list[float],
    rule: tuple[int, int],
) -> float:
    return _integrate(lambda s: math.hypot(*evaluate(s)[1]), breaks, rule)


def _bisect(fn: Callable[[float], float], lo: float, hi: float) -> float:
    assert fn(lo) * fn(hi) <= 0, "no sign change: the offset does not meet the wall"
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if fn(lo) * fn(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def _sum(*parts: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        sum(p[0] for p in parts),
        sum(p[1] for p in parts),
        sum(p[2] for p in parts),
    )


def _derive(model: dict[str, Any], rule: tuple[int, int]) -> Derivation:
    features = [item["feature"] for item in model["features"]]
    [sketch] = [f["params"] for f in features if f["type"] == "sketch"]
    [extrude] = [f["params"] for f in features if f["type"] == "extrude"]
    [shell] = [f["params"] for f in features if f["type"] == "shell"]
    height, t = float(extrude["distance_mm"]), float(shell["thickness_mm"])
    bottom, right, top, left = sketch["entities"]
    assert [bottom["kind"], right["kind"], top["kind"], left["kind"]] == [
        "line",
        "line",
        "spline",
        "line",
    ]
    width = float(bottom["end"]["x"])
    fit = [(float(p["x"]), float(p["y"])) for p in top["points"]]
    spline = _Spline(fit)
    first, last = spline.knots[0], spline.knots[-1]

    # Outer profile, counter-clockwise: bottom, right, spline (x: W -> 0), left.
    outer = _sum(
        _moments_segment((0.0, 0.0), (width, 0.0)),
        _moments_segment((width, 0.0), fit[0]),
        _moments_curve(spline.point, spline.knots, rule),
        _moments_segment(fit[-1], (0.0, 0.0)),
    )

    # Cavity: the spline's inward offset between the offset verticals.
    def offset(s: float) -> tuple[Point, Point]:
        return spline.offset(s, t)

    sa = _bisect(lambda s: offset(s)[0][0] - (width - t), first, spline.knots[1])
    sb = _bisect(lambda s: offset(s)[0][0] - t, spline.knots[-2], last)
    breaks = [sa, *[k for k in spline.knots if sa < k < sb], sb]
    pa, pb = offset(sa)[0], offset(sb)[0]
    inner = _sum(
        _moments_segment((t, t), (width - t, t)),
        _moments_segment((width - t, t), pa),
        _moments_curve(offset, breaks, rule),
        _moments_segment(pb, (t, t)),
    )
    (area, mx, my), (area_in, mx_in, my_in) = outer, inner
    cavity = height - t
    volume = area * height - area_in * cavity
    centroid = (
        (mx * height - mx_in * cavity) / volume,
        (my * height - my_in * cavity) / volume,
        (area * height**2 / 2 - area_in * (height**2 - t**2) / 2) / volume,
    )
    perimeter = (
        width + fit[0][1] + _length(spline.point, spline.knots, rule) + fit[-1][1]
    )
    perimeter_in = (
        (width - 2 * t) + (pa[1] - t) + _length(offset, breaks, rule) + (pb[1] - t)
    )
    # outer bottom + outer walls + cavity floor + cavity walls + the rim (A - A_in)
    surface = 2 * area + perimeter * height + perimeter_in * cavity
    peak = _bisect(lambda s: spline.point(s)[1][1], *_bracket_peak(spline))
    return Derivation(volume, centroid, surface, spline.point(peak)[0][1])


def _bracket_peak(spline: _Spline) -> tuple[float, float]:
    """A knot span holding the spline's highest point (its y' changes sign)."""
    samples = np.linspace(spline.knots[0], spline.knots[-1], 2001)
    ys = [spline.point(float(s))[0][1] for s in samples]
    i = int(np.argmax(ys))
    return float(samples[max(i - 1, 0)]), float(samples[min(i + 1, len(samples) - 1)])


def derive(model: dict[str, Any]) -> Derivation:
    """The golden's analytic numbers from its own model.json, rule-checked."""
    previous, final = (_derive(model, rule) for rule in RULES[-2:])
    for a, b in (
        (previous.volume, final.volume),
        (previous.surface_area, final.surface_area),
    ):
        if abs(a - b) > RULE_AGREEMENT * abs(b):
            raise AssertionError(f"integration rules disagree: {a!r} vs {b!r}")
    return final


def main() -> int:
    model = json.loads((HERE / "model.json").read_text())
    expected = json.loads((HERE / "expected.json").read_text())
    derived = derive(model)
    pinned = expected["properties"]
    tolerance = float(expected["tolerance"])
    print(f"volume        {derived.volume!r} mm^3 (expected.json {pinned['volume']!r})")
    print(f"centroid      {derived.centroid!r}")
    print(f"surface area  {derived.surface_area!r} mm^2 (analytic)")
    print(f"max y         {derived.max_y!r} mm")
    centroid = pinned["centroid"]
    ok = abs(derived.volume - pinned["volume"]) <= tolerance and all(
        abs(a - centroid[k]) <= tolerance
        for a, k in zip(derived.centroid, "xyz", strict=True)
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
