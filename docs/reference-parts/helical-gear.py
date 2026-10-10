"""Helical gear through the PUBLIC scripting API (loft-script) - a QA probe.

A reference part (``docs/VISION.md``). The same part the UI run models, built
through ``loft-script`` - i.e. through the gateway, the same routes the browser
calls - so a run can separate "the kernel cannot" from "the UI cannot reach it".
(The first run's report: ``git show 5b6fd28:docs/qa/helical-gear-2026-09-24.md``.)

Part: normal module 2, 24 teeth, normal pressure angle 20 deg, helix 15 deg
right hand, face width 20 mm, bore 10 mm with a DIN 6885 keyway (3 x 1.4).

Loft has no equation curve and no gear generator, so the involute is drawn as
fit-point splines through exact involute points.

**Parametric route** (the default; PART-PARAMETERS step 9). The part carries a
parameter table, as Fusion 360's Change Parameters: ``module``, ``teeth``,
``alpha_n``, ``beta`` and ``face_width`` drive it, and the gear quantities
(``rp``, ``rbase``, ``ra``, ``rf``, ``twist``, ...) are formulas over them.

1. blank: tip-circle disc, diameter ``2 * ra``, extruded ``face_width``;
2. ONE tooth-gap sketch on XY whose every vertex and involute fit point is
   placed by driving dimensions from the sketch origin, each a formula over
   the table, and ONE path sketch (the gear axis, ``face_width`` long, on XZ);
3. ONE SWEEP CUT along the axis with ``twist_angle_deg = twist`` - Fusion
   360's and SolidWorks' "twist along path", a true helical sweep (the twist
   moved from Extrude to Sweep in TWIST-TO-SWEEP) - then a feature-scope
   circular pattern of ``teeth`` instances;
4. bore + keyway as one closed profile, extrude-cut ``face_width``;
5. independent checks: mass properties against the analytic volume, STEP
   export re-read by OCCT outside the app, twist measured on that STEP.

``--edit`` re-drives the helix with ONE parameter edit,
``part.set_parameter("beta", "20 deg")``: the blank, the gap sketch, the twist
and the pattern all follow the table, and the volume must then match
``expected_volume(Gear(beta_deg=20.0), ...)``.

**Ruled route** (``--ruled``; the only route when the first report was
written, kept as a loft probe): the gap is sketched on XY and again on offset
datum planes, each copy drawn rotated by the helix twist at that height
(``z * tan(beta) / r``), then a RULED loft cut and the same pattern. It is not
parametric (each section's rotation is drawn, not driven), so ``--edit``
refuses it. ``--sections N`` is the number of loft sections (2 = bottom + top
only). A ruled loft joins matching points by STRAIGHT lines, so between
sections the flank sags inside the true helicoid; more sections shrink that
error by ~N^2.

Run against a live gateway::

    uv run python docs/reference-parts/helical-gear.py --url http://127.0.0.1:8000
    uv run python docs/reference-parts/helical-gear.py --url ... --edit
    uv run python docs/reference-parts/helical-gear.py --url ... --ruled --sections 5

The run exits 1 when a volume is more than 1e-4 relative from its expected
value. The STEP check imports build123d, which only a QA probe may do (the
product path never does). It is skipped with a note when build123d is absent,
and with ``--no-step``.
"""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import loft
from formula_sketch import VOLUME_REL_TOL, Placer, Row, Timer, define
from loft.part import Part
from loft.sketch import Sketch
from loft_wire.expr import Quantity
from loft_wire.features import (
    CircularPatternParamsV1,
    DatumFeature,
    DatumOffsetParams,
    FeatureRef,
    LoftFeature,
    LoftParamsV1,
    PatternFeature,
    PatternFeaturesScope,
    PatternParamsV1,
)
from loft_wire.geometry import Vec3
from loft_wire.sketch import Point2D, SketchSpline

# --------------------------------------------------------------------------
# Gear geometry (ISO 21771 / DIN 3960 notation, no profile shift)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Gear:
    m_n: float = 2.0
    z: int = 24
    alpha_n_deg: float = 20.0
    beta_deg: float = 15.0  # right hand = +twist about +Z going up
    face_width: float = 20.0
    bore: float = 10.0
    key_width: float = 3.0
    key_depth: float = 1.4  # hub groove depth t2, from the bore surface

    @property
    def beta(self) -> float:
        return math.radians(self.beta_deg)

    @property
    def m_t(self) -> float:
        return self.m_n / math.cos(self.beta)

    @property
    def alpha_t(self) -> float:
        return math.atan(math.tan(math.radians(self.alpha_n_deg)) / math.cos(self.beta))

    @property
    def r(self) -> float:  # pitch radius
        return self.z * self.m_t / 2

    @property
    def rb(self) -> float:  # base radius
        return self.r * math.cos(self.alpha_t)

    @property
    def ra(self) -> float:  # tip radius
        return self.r + self.m_n

    @property
    def rf(self) -> float:  # root radius
        return self.r - 1.25 * self.m_n

    @property
    def r_out(self) -> float:
        """Where the gap cutter's flanks stop - past the tip, inside the point."""
        return self.ra + 0.4 * self.m_n

    def twist_at(self, height: float) -> float:
        """Helix rotation (rad) of the transverse section at ``height``."""
        return height * math.tan(self.beta) / self.r

    def gap_half_angle(self, radius: float) -> float:
        """Half the angular width of a tooth GAP at ``radius`` (>= rb)."""
        alpha = math.acos(min(1.0, self.rb / radius))
        inv = math.tan(alpha) - alpha
        inv_t = math.tan(self.alpha_t) - self.alpha_t
        tooth_half = math.pi / (2 * self.z) + inv_t - inv
        return math.pi / self.z - tooth_half


def involute_radii(g: Gear, n: int) -> list[float]:
    """Fit-point radii from rb to r_out, uniform in ROLL angle (dense at rb)."""
    t_out = math.sqrt((g.r_out / g.rb) ** 2 - 1)
    return [g.rb * math.sqrt(1 + (t_out * i / (n - 1)) ** 2) for i in range(n)]


def polar(radius: float, angle: float) -> tuple[float, float]:
    return (radius * math.cos(angle), radius * math.sin(angle))


# --------------------------------------------------------------------------
# Analytic expectations
# --------------------------------------------------------------------------


def clipped_gap_area(g: Gear, scale: float) -> float:
    """Area of (gap scaled by ``scale``) INSIDE the tip circle, by sampling."""
    # Integrate in polar strips: for each radius the gap spans 2*half(r/scale)
    # radians (flank region) or the root/outer arcs; the area inside ra is
    # int_{rf*s}^{ra} 2*h(rho/s) * rho d rho.
    lo, hi, n = g.rf * scale, g.ra, 4000
    total = 0.0
    for k in range(n):
        rho = lo + (hi - lo) * (k + 0.5) / n
        src = rho / scale
        half = g.gap_half_angle(max(src, g.rb))
        total += 2 * half * rho * (hi - lo) / n
    return total


def keyway_bore_area(g: Gear) -> float:
    rb_ = g.bore / 2
    half_w = g.key_width / 2
    y_edge = math.sqrt(rb_**2 - half_w**2)
    top = rb_ + g.key_depth
    # rectangle from the chord at y_edge up to `top`, plus the bore disc
    segment = rb_**2 * math.asin(half_w / rb_) - half_w * y_edge  # circle cap
    return math.pi * rb_**2 + g.key_width * (top - y_edge) - segment


def expected_volume(g: Gear, sections: int) -> tuple[float, float]:
    """(true helical volume, volume this ruled-loft construction should give)."""
    disc = math.pi * g.ra**2
    hole = keyway_bore_area(g)
    exact = (disc - g.z * clipped_gap_area(g, 1.0) - hole) * g.face_width
    # Between two sections dtheta apart, a ruled loft joins p and R(dtheta) p
    # by a straight chord, i.e. the section at fraction t is the gap SCALED by
    # |1 - t + t e^{i dtheta}| (and rotated). Integrate that.
    dtheta = g.twist_at(g.face_width) / (sections - 1)
    steps = 40
    mean_gap = 0.0
    for k in range(steps):
        t = (k + 0.5) / steps
        s = abs(complex(1 - t + t * math.cos(dtheta), t * math.sin(dtheta)))
        mean_gap += clipped_gap_area(g, s) / steps
    ruled = (disc - g.z * mean_gap - hole) * g.face_width
    return exact, ruled


# --------------------------------------------------------------------------
# Modelling through loft-script
# --------------------------------------------------------------------------


def draw_gap(sk: Sketch, g: Gear, rot: float, fit_points: int) -> None:
    """One closed tooth-gap cutter: root arc, radial runs, involutes, outer arc."""
    gb = g.gap_half_angle(g.rb)
    g_out = g.gap_half_angle(g.r_out)
    radii = involute_radii(g, fit_points)
    # radial run below the base circle (no trochoid root fillet: honest limit)
    sk.line(polar(g.rf, rot - gb), polar(g.rb, rot - gb))
    sk.add(
        SketchSpline(
            id=sk._new_id(),  # pyright: ignore[reportPrivateUsage]
            kind="spline",
            points=[
                Point2D(x=x, y=y)
                for x, y in (polar(r, rot - g.gap_half_angle(r)) for r in radii)
            ],
        )
    )
    sk.arc((0, 0), polar(g.r_out, rot - g_out), polar(g.r_out, rot + g_out))
    sk.add(
        SketchSpline(
            id=sk._new_id(),  # pyright: ignore[reportPrivateUsage]
            kind="spline",
            points=[
                Point2D(x=x, y=y)
                for x, y in (
                    polar(r, rot + g.gap_half_angle(r)) for r in reversed(radii)
                )
            ],
        )
    )
    sk.line(polar(g.rb, rot + gb), polar(g.rf, rot + gb))
    sk.arc((0, 0), polar(g.rf, rot - gb), polar(g.rf, rot + gb))


def draw_bore_keyway(sk: Sketch, g: Gear) -> None:
    rb_ = g.bore / 2
    hw = g.key_width / 2
    y_edge = math.sqrt(rb_**2 - hw**2)
    top = rb_ + g.key_depth
    # the long way round, CCW from the keyway's left edge to its right edge
    sk.arc((0, 0), (-hw, y_edge), (hw, y_edge))
    sk.line((hw, y_edge), (hw, top))
    sk.line((hw, top), (-hw, top))
    sk.line((-hw, top), (-hw, y_edge))


def build_ruled(
    part: Part, g: Gear, sections: int, fit_points: int, timer: Timer
) -> dict[str, uuid.UUID]:
    """The ruled route: numbers, one rotated gap section per height."""
    ids: dict[str, uuid.UUID] = {}

    t0 = time.perf_counter()
    blank = part.sketch(on="XY", name="Blank (tip circle)")
    blank.circle((0, 0), diameter=2 * g.ra)
    part.extrude(blank, g.face_width, name="Blank")
    ids["blank"] = blank.id
    timer.step("blank: tip-circle sketch + extrude", t0)

    section_refs: list[FeatureRef] = []
    for i in range(sections):
        t0 = time.perf_counter()
        height = g.face_width * i / (sections - 1)
        if i == 0:
            plane: FeatureRef | str = "XY"
        else:
            datum = part.create_feature(
                f"Datum z={height:g}",
                DatumFeature(
                    type="datum",
                    version=1,
                    params=DatumOffsetParams(base="XY", offset_mm=height),
                ),
            )
            ids[f"datum{i}"] = datum.feature.id
            plane = FeatureRef(kind="feature", feature_id=datum.feature.id)
        sk = part.sketch(on=plane, name=f"Gap section z={height:g}")
        draw_gap(sk, g, g.twist_at(height), fit_points)
        sk.save()
        ids[f"section{i}"] = sk.id
        section_refs.append(sk.ref())
        twist = math.degrees(g.twist_at(height))
        timer.step(f"gap section {i} at z={height:g} (twist {twist:.3f} deg)", t0)

    t0 = time.perf_counter()
    cut = part.create_feature(
        "Tooth gap (ruled loft cut)",
        LoftFeature(
            type="loft",
            version=1,
            params=LoftParamsV1(profiles=section_refs, operation="cut"),
        ),
    )
    ids["loft"] = cut.feature.id
    part.evaluate(strict=True)
    timer.step("loft cut of one gap + evaluate", t0)

    t0 = time.perf_counter()
    ids["pattern"] = gap_pattern(part, cut.feature.id, g.z, None)
    part.evaluate(strict=True)
    timer.step(f"circular pattern x{g.z} (feature scope) + evaluate", t0)

    t0 = time.perf_counter()
    bore = part.sketch(on="XY", name="Bore + keyway")
    draw_bore_keyway(bore, g)
    part.extrude(bore, g.face_width, operation="cut", name="Bore + keyway cut")
    part.evaluate(strict=True)
    timer.step("bore + keyway extrude-cut + evaluate", t0)
    return ids


# --------------------------------------------------------------------------
# The parametric route: a parameter table, and formulas that read it
# --------------------------------------------------------------------------


def parameter_table(g: Gear) -> list[Row]:
    """(name, formula, unit, comment) rows, in dependency order.

    The first five are the gear's design inputs; the rest are the textbook
    (ISO 21771) quantities as formulas over them, so a user who opens Change
    Parameters reads the gear, not a list of magic numbers. A unit of None lets
    the formula say it (a new row is a length unless it evaluates to an angle).
    """
    return [
        ("module", f"{g.m_n:g}", None, "normal module m_n"),
        ("teeth", f"{g.z}", "unitless", "tooth count z"),
        ("alpha_n", f"{g.alpha_n_deg:g} deg", None, "normal pressure angle"),
        ("beta", f"{g.beta_deg:g} deg", None, "helix angle, right hand"),
        ("face_width", f"{g.face_width:g}", None, "face width b"),
        ("mt", "module / cos(beta)", None, "transverse module"),
        ("rp", "teeth * mt / 2", None, "pitch radius"),
        ("alpha_t", "atan(tan(alpha_n) / cos(beta))", None, "transverse pressure"),
        ("rbase", "rp * cos(alpha_t)", None, "base circle radius"),
        ("ra", "rp + module", None, "tip radius"),
        ("rf", "rp - 1.25 * module", None, "root radius"),
        ("r_out", "ra + 0.4 * module", None, "gap cutter's outer radius"),
        (
            "t_out",
            "sqrt((r_out / rbase) * (r_out / rbase) - 1)",
            "unitless",
            "involute roll parameter at r_out",
        ),
        ("inv_t", "tan(alpha_t) - rad(alpha_t)", "unitless", "inv(alpha_t)"),
        ("gap0", "90 deg / teeth - deg(inv_t)", None, "half gap at the base circle"),
        ("twist", "deg(face_width * tan(beta) / rp)", None, "helix twist over b"),
    ]


def roll(i: int, n: int) -> str:
    """Involute roll parameter of fit point ``i`` of ``n`` (``involute_radii``)."""
    return f"t_out*{i}/{n - 1}"


def flank_radius(i: int, n: int) -> str:
    """Radius of fit point ``i``: ``rb * sqrt(1 + t^2)``."""
    return "rbase" if i == 0 else f"rbase*sqrt(1+({roll(i, n)})*({roll(i, n)}))"


def flank_half_gap(i: int, n: int) -> str:
    """``gap_half_angle`` at fit point ``i``: gap0 + inv(alpha), inv = t - atan t."""
    t = roll(i, n)
    return "gap0" if i == 0 else f"(gap0+deg({t})-atan({t}))"


def spline(sk: Sketch, points: list[tuple[float, float]]) -> str:
    return sk.add(
        SketchSpline(
            id=sk._new_id(),  # pyright: ignore[reportPrivateUsage]
            kind="spline",
            points=[Point2D(x=x, y=y) for x, y in points],
        )
    )


def draw_gap_parametric(
    sk: Sketch, g: Gear, n: int, values: Mapping[str, Quantity]
) -> None:
    """The tooth-gap cutter of :func:`draw_gap` (``rot = 0``), every point driven.

    Drawn at the gear ``g`` (the table's current values), then held by
    formulas: each vertex and involute fit point gets its x and |y| from the
    origin, the joins are coincidences, and both arcs are centred on the
    origin. The upper flank's outer point and the root arc's upper end take
    only their y: the arc through them fixes x, so the sketch is fully
    constrained with no redundant dimension.
    """
    at = Placer(sk, values)
    radii = involute_radii(g, n)
    gb = g.gap_half_angle(g.rb)
    lower = [polar(r, -g.gap_half_angle(r)) for r in radii]
    upper = [polar(r, g.gap_half_angle(r)) for r in reversed(radii)]
    root_lo, root_hi = polar(g.rf, -gb), polar(g.rf, gb)

    run_lo = sk.line(root_lo, lower[0])
    flank_lo = spline(sk, lower)
    outer = sk.arc((0, 0), lower[-1], upper[0])
    flank_hi = spline(sk, upper)
    run_hi = sk.line(upper[-1], root_hi)
    root = sk.arc((0, 0), root_lo, root_hi)

    last = n - 1
    at.polar(run_lo, "start", "rf", "gap0")
    sk.coincident((run_lo, "end"), (flank_lo, "fit0"))
    for i in range(n):
        at.polar(flank_lo, f"fit{i}", flank_radius(i, n), flank_half_gap(i, n))
    sk.coincident((outer, "center"), (at.origin, "position"))
    sk.coincident((outer, "start"), (flank_lo, f"fit{last}"))
    sk.coincident((outer, "end"), (flank_hi, "fit0"))
    top = f"{flank_radius(last, n)}*sin({flank_half_gap(last, n)})"
    at.place(flank_hi, "fit0", None, top)
    for j in range(1, n):
        i = last - j
        at.polar(flank_hi, f"fit{j}", flank_radius(i, n), flank_half_gap(i, n))
    sk.coincident((run_hi, "start"), (flank_hi, f"fit{last}"))
    at.place(run_hi, "end", None, "rf*sin(gap0)")
    sk.coincident((root, "center"), (at.origin, "position"))
    sk.coincident((root, "start"), (run_lo, "start"))
    sk.coincident((root, "end"), (run_hi, "end"))


def gap_pattern(
    part: Part, cut: uuid.UUID, count: int, formula: str | None
) -> uuid.UUID:
    """Feature-scope circular pattern of the gap cut about the gear axis."""
    pattern = part.create_feature(
        "Gap pattern",
        PatternFeature(
            type="pattern",
            version=1,
            params=PatternParamsV1(
                pattern=CircularPatternParamsV1(
                    axis_point=Vec3(x=0.0, y=0.0, z=0.0),
                    axis_direction=Vec3(x=0.0, y=0.0, z=1.0),
                    angle_deg=360.0,
                    count=count,
                ),
                scope=PatternFeaturesScope(
                    kind="features",
                    features=[FeatureRef(kind="feature", feature_id=cut)],
                ),
            ),
            expressions=None if formula is None else {"/pattern/count": formula},
        ),
    )
    return pattern.feature.id


def build_parametric(
    part: Part, g: Gear, fit_points: int, timer: Timer
) -> dict[str, uuid.UUID]:
    """The parametric route: the table, then one gap sketch, one axis path, one
    twisted sweep cut and one pattern, every size a formula over the table."""
    ids: dict[str, uuid.UUID] = {}

    t0 = time.perf_counter()
    values = define(part, parameter_table(g))
    timer.step(f"parameter table ({len(values)} rows)", t0)

    t0 = time.perf_counter()
    blank = part.sketch(on="XY", name="Blank (tip circle)")
    tip = blank.circle((0, 0), diameter="2 * ra")
    blank.fixed((tip, "center"))
    part.extrude(blank, "face_width", name="Blank")
    ids["blank"] = blank.id
    timer.step("blank: tip-circle sketch + extrude", t0)

    t0 = time.perf_counter()
    sk = part.sketch(on="XY", name="Tooth gap")
    draw_gap_parametric(sk, g, fit_points, values)
    solved = sk.save().solved
    assert solved is not None
    print(f"  tooth gap sketch: {solved.status}, {solved.dof} DOF")
    ids["gap"] = sk.id
    # The sweep path IS the twist axis: the gear axis, from the gap's own
    # plane (z = 0) up through the face width. On XZ, sketch y is world +Z.
    axis = part.sketch(on="XZ", name="Gear axis (sweep path)")
    shaft = axis.line((0.0, 0.0), (0.0, g.face_width))
    axis.fixed((shaft, "start"))
    axis.vertical(shaft)
    axis.distance(shaft, "face_width")
    axis.save()
    ids["axis"] = axis.id
    cut = part.sweep(
        sk,
        axis,
        operation="cut",
        twist_angle_deg="twist",
        name="Tooth gap (twisted sweep cut)",
    )
    ids["cut"] = cut.id
    part.evaluate(strict=True)
    twist = values["twist"].value
    timer.step(f"gap + axis sketches + twisted sweep cut ({twist:.3f} deg)", t0)

    t0 = time.perf_counter()
    ids["pattern"] = gap_pattern(part, cut.id, g.z, "teeth")
    part.evaluate(strict=True)
    timer.step(f"circular pattern x teeth={g.z} (feature scope) + evaluate", t0)

    t0 = time.perf_counter()
    bore = part.sketch(on="XY", name="Bore + keyway")
    draw_bore_keyway(bore, g)
    part.extrude(bore, "face_width", operation="cut", name="Bore + keyway cut")
    part.evaluate(strict=True)
    timer.step("bore + keyway extrude-cut + evaluate", t0)
    return ids


def verify_step(path: Path, g: Gear) -> None:
    """Re-read the exported STEP with OCCT outside the app and measure it.

    Independent of the app's own numbers: tooth count and helix twist are read
    off the solid by point classification, not from anything the tree says.
    """
    try:
        from build123d import import_step  # type: ignore[import-untyped]
        from OCP.BRepClass3d import (
            BRepClass3d_SolidClassifier,  # type: ignore[import-untyped]
        )
        from OCP.BRepGProp import BRepGProp  # type: ignore[import-untyped]
        from OCP.gp import gp_Pnt  # type: ignore[import-untyped]
        from OCP.GProp import GProp_GProps  # type: ignore[import-untyped]
        from OCP.TopAbs import TopAbs_IN  # type: ignore[import-untyped]
    except ImportError:  # pragma: no cover - QA-only dependency
        print("  (build123d not importable here: STEP re-read skipped)")
        return
    shape = import_step(str(path))
    solids = shape.solids()
    # ADAPTIVE integration, the app's own (geometry.kernel.properties.VOLUME_EPS):
    # build123d's `.volume` is fixed-order Gauss, which is 1.7e-5 low on the
    # helicoidal flanks and would read as a round-trip loss that is not there.
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props, 1e-10, False, False)
    print(
        f"  STEP re-read: {len(solids)} solid(s), valid={shape.is_valid}, "
        f"volume={props.Mass():.3f} mm^3 (adaptive)"
    )
    classifier = BRepClass3d_SolidClassifier(solids[0].wrapped)

    def solid_at(angle: float, z: float, radius: float | None = None) -> bool:
        rad = g.r if radius is None else radius
        classifier.Perform(
            gp_Pnt(rad * math.cos(angle), rad * math.sin(angle), z), 1e-7
        )
        return classifier.State() == TopAbs_IN

    def edge(z: float, inside_gap: float, step: float) -> float:
        """Bisect for the gap/tooth boundary on the pitch circle from a gap point."""
        lo, hi = inside_gap, inside_gap
        while not solid_at(hi, z):
            hi += step
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (lo, mid) if solid_at(mid, z) else (mid, hi)
        return (lo + hi) / 2

    def gap_centre(z: float, near: float) -> float:
        step = math.radians(0.05)
        return (edge(z, near, step) + edge(z, near, -step)) / 2

    teeth = 0
    was = solid_at(0.0, 0.5)
    for k in range(1, 721):
        now = solid_at(math.radians(k / 2), 0.5)
        teeth += int(now and not was)
        was = now

    # Track ONE gap up the face in 1 mm steps (it drifts ~0.6 deg/mm, the gap is
    # ~7 deg wide) so the twist is measured, not assumed.
    heights = [0.05] + [float(h) for h in range(1, int(g.face_width))]
    heights.append(g.face_width - 0.05)
    track = [gap_centre(heights[0], 0.0)]
    for h in heights[1:]:
        track.append(gap_centre(h, track[-1]))
    deviation = [
        math.degrees(t - track[0] - g.twist_at(h - heights[0]))
        for h, t in zip(heights, track, strict=True)
    ]
    worst = max(deviation, key=abs)
    twist = math.degrees(track[-1] - track[0])
    expected = math.degrees(g.twist_at(heights[-1] - heights[0]))
    print(f"  teeth counted on the pitch circle at z=0.5: {teeth}")
    print(
        f"  twist z={heights[0]}..{heights[-1]}: {twist:.4f} deg (expected "
        f"{expected:.4f}); worst angular deviation from the true helix along "
        f"the face: {worst:+.5f} deg"
    )

    # Where a ruled loft departs from a helicoid: mid-face, between sections.
    # Every cutter point rides a straight CHORD instead of a helical arc, so the
    # gap there is the true gap scaled toward the axis: a deeper root and a
    # wider gap (thinner tooth) at the pitch circle.
    def gap_width(z: float, near: float) -> float:
        step = math.radians(0.05)
        return edge(z, near, step) - edge(z, near, -step)

    def root_radius(z: float, angle: float) -> float:
        lo, hi = g.rf - 1.0, g.r  # solid at lo, gap at hi
        for _ in range(40):
            rad = (lo + hi) / 2
            lo, hi = (rad, hi) if solid_at(angle, z, rad) else (lo, rad)
        return lo

    widths = [gap_width(h, t) for h, t in zip(heights, track, strict=True)]
    roots = [root_radius(h, t) for h, t in zip(heights, track, strict=True)]
    pitch_t = 2 * math.pi / g.z
    thin = min(range(len(widths)), key=lambda i: -widths[i])
    mid = min(range(len(heights)), key=lambda i: abs(heights[i] - g.face_width / 2))
    print(
        f"  transverse tooth thickness on the pitch circle: z=0 "
        f"{g.r * (pitch_t - widths[0]):.5f} mm, mid-face z={heights[mid]:g} "
        f"{g.r * (pitch_t - widths[mid]):.5f} mm, thinnest z={heights[thin]:g} "
        f"{g.r * (pitch_t - widths[thin]):.5f} mm (true: {g.r * pitch_t / 2:.5f})"
    )
    print(
        f"  root radius: z=0 {roots[0]:.4f} mm, deepest {min(roots):.4f} mm "
        f"(true: {g.rf:.4f})"
    )


def report(label: str, volume: float, expected: float, exact: float) -> bool:
    """Print a volume against its expected value; True when within tolerance."""
    rel = volume / expected - 1
    ok = abs(rel) <= VOLUME_REL_TOL
    print(
        f"{label}: volume {volume:.3f} mm^3, expected {expected:.3f} "
        f"({rel:+.2e} relative, tolerance {VOLUME_REL_TOL:g}: "
        f"{'ok' if ok else 'FAIL'}); vs true helical {exact:.3f}: "
        f"{volume - exact:+.3f} mm^3"
    )
    return ok


def export_and_verify(part: Part, g: Gear, timer: Timer) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t0 = time.perf_counter()
        step = part.export(Path(tmp) / "gear.step")
        timer.step(f"STEP export ({step.stat().st_size} bytes)", t0)
        verify_step(step, g)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument(
        "--ruled",
        action="store_true",
        help="the legacy route: rotated gap sections and a RULED loft cut",
    )
    ap.add_argument("--sections", type=int, default=2, help="ruled route only")
    ap.add_argument("--fit-points", type=int, default=12)
    ap.add_argument(
        "--edit",
        action="store_true",
        help='re-drive with one set_parameter("beta", "20 deg") and time it',
    )
    ap.add_argument("--no-step", action="store_true", help="skip the STEP re-read")
    args = ap.parse_args()
    if args.edit and args.ruled:
        ap.error("--edit re-drives the parametric route; the ruled route is drawn")
    g = Gear()

    twist_b = math.degrees(g.twist_at(g.face_width))
    print(
        f"gear: m_n={g.m_n} z={g.z} beta={g.beta_deg} -> d={2 * g.r:.3f} "
        f"da={2 * g.ra:.3f} df={2 * g.rf:.3f} db={2 * g.rb:.3f}, "
        f"twist over b = {twist_b:.3f} deg"
    )
    exact, ruled = expected_volume(g, args.sections)
    # A twisted sweep is the helicoid itself: its expected volume is the true
    # helical one. Only the ruled loft sags inside it.
    expected = ruled if args.ruled else exact
    route = f"{args.sections}-section ruled loft" if args.ruled else "twisted cut"
    print(f"expected volume: true helical {exact:.3f} mm^3, {route} {expected:.3f}")

    timer = Timer()
    email = f"gear-script-{uuid.uuid4().hex[:8]}@example.com"
    with loft.register(args.url, email=email, password="gear-script-pw-123") as session:
        part = session.new_part(f"Helical gear (script, {route})")
        t_all = time.perf_counter()
        try:
            if args.ruled:
                build_ruled(part, g, args.sections, args.fit_points, timer)
            else:
                build_parametric(part, g, args.fit_points, timer)
        except loft.LoftError as exc:
            print(f"FAILED: {exc.as_dict()}")
            return 1
        timer.step("TOTAL build", t_all)

        t0 = time.perf_counter()
        props = part.mass_properties()
        timer.step("mass properties (evaluate)", t0)
        ok = report("app", props.volume, expected, exact)
        bb, topo = props.bounding_box, props.topology
        print(
            f"app: bbox x {bb.min.x:.3f}..{bb.max.x:.3f} "
            f"y {bb.min.y:.3f}..{bb.max.y:.3f} z {bb.min.z:.3f}..{bb.max.z:.3f}; "
            f"faces {topo.faces} edges {topo.edges} shells {topo.shells}; "
            f"area {props.surface_area:.1f}"
        )
        if not args.no_step:
            export_and_verify(part, g, timer)

        if args.edit:
            g2 = Gear(beta_deg=20.0)
            t0 = time.perf_counter()
            part.set_parameter("beta", "20 deg")
            timer.step('set_parameter("beta", "20 deg")', t0)
            t0 = time.perf_counter()
            props2 = part.mass_properties()
            timer.step("rebuild after helix edit (evaluate)", t0)
            exact2, _ = expected_volume(g2, args.sections)
            ok = report("after edit", props2.volume, exact2, exact2) and ok
            if not args.no_step:
                export_and_verify(part, g2, timer)
        print(f"part id: {part.id}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
