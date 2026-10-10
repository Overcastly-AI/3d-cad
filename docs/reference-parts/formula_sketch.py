"""Formula-driven sketches for the parametric reference parts (loft-script).

Not a reference part itself: the helpers the parametric parts share
(``helical-gear.py``, ``manifold.py``, ``knob.py``; PART-PARAMETERS step 9).
loft-script's sketch sugar dimensions line lengths, radii and diameters; a
point is placed by its x and y from the origin, which is how a Fusion 360 user
locates a vertex with two driving dimensions. These helpers author exactly
that through the open escape hatch (``Sketch.constrain``), with each value a
formula over the part's parameter table.

Every value a formula gives here is computed by the shared expression library
(``loft.parameters.dimension_value``), the number documents stores beside it.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping, Sequence

from loft.parameters import dimension_value
from loft.part import Part
from loft.sketch import Sketch
from loft_wire.expr import LENGTH, Quantity, coerce, evaluate
from loft_wire.features import (
    DatumFeature,
    DatumOffsetParams,
    FeatureRef,
    RevolveFeature,
    RevolveParamsV1,
    SketchLineAxis,
)
from loft_wire.parameters import ParameterUnit
from loft_wire.sketch import DimensionPointRef, PointDistanceConstraint, PointName

#: A volume further than this (relative) from its expected value fails a run:
#: the ladder's independent-check bound (docs/reference-parts/ladder.md).
VOLUME_REL_TOL = 1e-4

#: A parameter table row: (name, formula, unit or None to infer, comment).
Row = tuple[str, str, ParameterUnit | None, str]


class Timer:
    def __init__(self) -> None:
        self.rows: list[tuple[str, float]] = []

    def step(self, label: str, t0: float) -> None:
        dt = time.perf_counter() - t0
        self.rows.append((label, dt))
        print(f"  {dt:7.2f} s  {label}", flush=True)


def define(part: Part, rows: Sequence[Row]) -> dict[str, Quantity]:
    """Write the parameter table row by row; return its resolved values."""
    for name, formula, unit, comment in rows:
        part.set_parameter(name, formula, comment, unit=unit)
    return dict(part.parameter_values())


def length(formula: str, values: Mapping[str, Quantity]) -> float:
    """The formula's value in mm, as documents will resolve it."""
    return coerce(evaluate(formula, values), LENGTH, formula)


class Placer:
    """Driving dimensions that place sketch points from a fixed origin point.

    Each coordinate is a horizontal or vertical point-to-point dimension whose
    value is a formula over the part's parameters. The dimension is signed by
    the side the point is drawn on, so its formula gives the magnitude.
    """

    def __init__(self, sk: Sketch, values: Mapping[str, Quantity]) -> None:
        self.sk = sk
        self.values = values
        self.origin = sk.point((0.0, 0.0), construction=True)
        sk.fixed((self.origin, "position"))

    def place(
        self, entity: str, point: PointName, x: str | None, y: str | None
    ) -> None:
        dims = (("horizontal", x), ("vertical", y))
        for direction, formula in dims:
            if formula is None:
                continue
            value = dimension_value(formula, self.sk.constraints, lambda: self.values)
            self.sk.constrain(
                PointDistanceConstraint(
                    kind="point_distance",
                    a=DimensionPointRef(entity=self.origin, point="position"),
                    b=DimensionPointRef(entity=entity, point=point),
                    direction="horizontal" if direction == "horizontal" else "vertical",
                    value_mm=value,
                    expression=formula,
                )
            )

    def polar(self, entity: str, point: PointName, r: str, angle: str) -> None:
        """Place a point at radius ``r``, ``angle`` off the sketch x axis."""
        self.place(entity, point, f"{r}*cos({angle})", f"{r}*sin({angle})")

    def polygon(self, corners: Sequence[tuple[str, str]]) -> list[str]:
        """A closed polyline, each corner placed by its (x, y) formulas.

        A leading ``-`` puts the corner on the negative side: it is drawn
        there, and its dimension holds the magnitude (a dimension is > 0).
        Line ``i`` runs from corner ``i`` to corner ``i + 1``.
        """

        def signed(formula: str) -> tuple[float, str]:
            if formula.startswith("-"):
                return -length(formula[1:], self.values), formula[1:]
            return length(formula, self.values), formula

        drawn = [(signed(x), signed(y)) for x, y in corners]
        points = [(x[0], y[0]) for x, y in drawn]
        lines = [
            self.sk.line(points[i], points[(i + 1) % len(points)])
            for i in range(len(points))
        ]
        for i, line in enumerate(lines):
            (_, x), (_, y) = drawn[i]
            self.place(line, "start", x, y)
            self.sk.coincident((line, "end"), (lines[(i + 1) % len(lines)], "start"))
        return lines


def offset_datum(
    part: Part,
    base: str,
    formula: str,
    values: Mapping[str, Quantity],
    name: str,
) -> FeatureRef:
    """An origin plane slid along its normal by a formula (XZ's normal is -Y)."""
    assert base in ("XY", "XZ", "YZ")
    created = part.create_feature(
        name,
        DatumFeature(
            type="datum",
            version=1,
            params=DatumOffsetParams(
                base="XY" if base == "XY" else "XZ" if base == "XZ" else "YZ",
                offset_mm=coerce(evaluate(formula, values), LENGTH, formula),
            ),
            expressions={"/offset_mm": formula},
        ),
    )
    return FeatureRef(kind="feature", feature_id=created.feature.id)


def revolve_cut(part: Part, sk: Sketch, axis: str, name: str) -> uuid.UUID:
    """Cut a full revolution of ``sk``'s profile about its line ``axis``."""
    created = part.create_feature(
        name,
        RevolveFeature(
            type="revolve",
            version=1,
            params=RevolveParamsV1(
                profile=sk.ref(),
                axis=SketchLineAxis(kind="sketch_line", entity=axis),
                operation="cut",
            ),
        ),
    )
    return created.feature.id


def check(label: str, measured: float, expected: float) -> bool:
    """Print measured against expected; True within :data:`VOLUME_REL_TOL`."""
    rel = measured / expected - 1
    ok = abs(rel) <= VOLUME_REL_TOL
    verdict = "ok" if ok else "FAIL"
    print(
        f"  {label}: {measured:.4f} (expected {expected:.4f}, "
        f"{rel:+.2e} relative, tolerance {VOLUME_REL_TOL:g}: {verdict})"
    )
    return ok
