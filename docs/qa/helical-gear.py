"""Helical gear through the PUBLIC scripting API (loft-script) - a QA probe.

Companion to ``docs/qa/helical-gear-2026-09-24.md``. The same part the UI leg of
that report attempts, built through ``loft-script`` - i.e. through the gateway,
the same routes the browser calls - so the report can separate "the kernel
cannot" from "the UI cannot reach it".

Part: normal module 2, 24 teeth, normal pressure angle 20 deg, helix 15 deg
right hand, face width 20 mm, bore 10 mm with a DIN 6885 keyway (3 x 1.4).

Route (Loft has no helix, no twisted extrude, no equation curve, no gear
generator - see the report):

1. blank: tip-circle disc, extruded 20 mm;
2. ONE tooth gap, exact involute flanks as fit-point splines, sketched on XY
   and again on offset datum planes, each copy rotated by the helix twist at
   that height (``z * tan(beta) / r``);
3. a RULED loft cut through those sections (the only non-prismatic tool that
   can twist), then a feature-scope circular pattern x ``z``;
4. bore + keyway as one closed profile, extrude-cut;
5. independent checks: mass properties against an analytic estimate, STEP
   export re-read by OCCT outside the app, twist measured on that STEP.

Run against a live gateway::

    uv run python docs/qa/helical-gear.py --url http://127.0.0.1:8000
    uv run python docs/qa/helical-gear.py --url ... --sections 5 --edit

``--sections N`` is the number of loft sections (2 = bottom + top only). A
ruled loft joins matching points by STRAIGHT lines, so between sections the
flank sags inside the true helicoid; more sections shrink that error by ~N^2.
``--edit`` then re-drives the part to beta = 20 deg and times the rebuild.

The STEP check imports build123d, which only a QA probe may do (the product
path never does). It is skipped with a note when build123d is absent.
"""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import loft
from loft.part import Part
from loft.sketch import Sketch
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


class Timer:
    def __init__(self) -> None:
        self.rows: list[tuple[str, float]] = []

    def step(self, label: str, t0: float) -> None:
        dt = time.perf_counter() - t0
        self.rows.append((label, dt))
        print(f"  {dt:7.2f} s  {label}", flush=True)


def build(
    part: Part, g: Gear, sections: int, fit_points: int, timer: Timer
) -> dict[str, uuid.UUID]:
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
                    count=g.z,
                ),
                scope=PatternFeaturesScope(
                    kind="features",
                    features=[FeatureRef(kind="feature", feature_id=cut.feature.id)],
                ),
            ),
        ),
    )
    ids["pattern"] = pattern.feature.id
    part.evaluate(strict=True)
    timer.step(f"circular pattern x{g.z} (feature scope) + evaluate", t0)

    t0 = time.perf_counter()
    bore = part.sketch(on="XY", name="Bore + keyway")
    draw_bore_keyway(bore, g)
    part.extrude(bore, g.face_width, operation="cut", name="Bore + keyway cut")
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
        from OCP.gp import gp_Pnt  # type: ignore[import-untyped]
        from OCP.TopAbs import TopAbs_IN  # type: ignore[import-untyped]
    except ImportError:  # pragma: no cover - QA-only dependency
        print("  (build123d not importable here: STEP re-read skipped)")
        return
    shape = import_step(str(path))
    solids = shape.solids()
    print(
        f"  STEP re-read: {len(solids)} solid(s), valid={shape.is_valid}, "
        f"volume={shape.volume:.3f} mm^3"
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
        f"the face: {worst:+.4f} deg"
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
    print(
        f"  transverse tooth thickness on the pitch circle: z=0 "
        f"{g.r * (pitch_t - widths[0]):.4f} mm, thinnest z={heights[thin]:g} "
        f"{g.r * (pitch_t - widths[thin]):.4f} mm (true: {g.r * pitch_t / 2:.4f})"
    )
    print(
        f"  root radius: z=0 {roots[0]:.4f} mm, deepest {min(roots):.4f} mm "
        f"(true: {g.rf:.4f})"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--sections", type=int, default=2)
    ap.add_argument("--fit-points", type=int, default=12)
    ap.add_argument(
        "--edit", action="store_true", help="re-drive to beta=20 and time it"
    )
    args = ap.parse_args()
    g = Gear()

    twist_b = math.degrees(g.twist_at(g.face_width))
    print(
        f"gear: m_n={g.m_n} z={g.z} beta={g.beta_deg} -> d={2 * g.r:.3f} "
        f"da={2 * g.ra:.3f} df={2 * g.rf:.3f} db={2 * g.rb:.3f}, "
        f"twist over b = {twist_b:.3f} deg"
    )
    exact, ruled = expected_volume(g, args.sections)
    print(
        f"expected volume: true helical {exact:.1f} mm^3, this "
        f"{args.sections}-section ruled loft {ruled:.1f} mm^3"
    )

    timer = Timer()
    email = f"gear-script-{uuid.uuid4().hex[:8]}@example.com"
    with loft.register(args.url, email=email, password="gear-script-pw-123") as session:
        part = session.new_part(f"Helical gear (script, {args.sections} sections)")
        t_all = time.perf_counter()
        try:
            ids = build(part, g, args.sections, args.fit_points, timer)
        except loft.LoftError as exc:
            print(f"FAILED: {exc.as_dict()}")
            return 1
        timer.step("TOTAL build", t_all)

        t0 = time.perf_counter()
        props = part.mass_properties()
        timer.step("mass properties (evaluate)", t0)
        bb = props.bounding_box
        vs_ruled = 100 * (props.volume / ruled - 1)
        vs_exact = 100 * (props.volume / exact - 1)
        print(
            f"app: volume {props.volume:.3f} mm^3 (vs ruled {ruled:.3f}: "
            f"{vs_ruled:+.3f}%, vs true helical {exact:.3f}: {vs_exact:+.3f}%)"
        )
        topo = props.topology
        print(
            f"app: bbox x {bb.min.x:.3f}..{bb.max.x:.3f} "
            f"y {bb.min.y:.3f}..{bb.max.y:.3f} z {bb.min.z:.3f}..{bb.max.z:.3f}; "
            f"faces {topo.faces} edges {topo.edges} shells {topo.shells}; "
            f"area {props.surface_area:.1f}"
        )

        with tempfile.TemporaryDirectory() as tmp:
            t0 = time.perf_counter()
            step = part.export(Path(tmp) / "gear.step")
            timer.step(f"STEP export ({step.stat().st_size} bytes)", t0)
            verify_step(step, g)

        if args.edit:
            g2 = Gear(beta_deg=20.0)
            t0 = time.perf_counter()
            blank = part.sketch_by_id(ids["blank"])
            blank.entities, blank.constraints = [], []
            blank.circle((0, 0), diameter=2 * g2.ra)
            part.update_feature(blank.id, feature=blank.feature())
            for i in range(args.sections):
                sk = part.sketch_by_id(ids[f"section{i}"])
                sk.entities = []
                draw_gap(
                    sk,
                    g2,
                    g2.twist_at(g2.face_width * i / (args.sections - 1)),
                    args.fit_points,
                )
                sk.part.update_feature(sk.id, feature=sk.feature())
            timer.step("re-drive blank + every section sketch to beta=20 (writes)", t0)
            t0 = time.perf_counter()
            props2 = part.mass_properties()
            timer.step("rebuild after helix edit (evaluate)", t0)
            expected2 = expected_volume(g2, args.sections)[1]
            print(f"after edit: volume {props2.volume:.3f} (expected {expected2:.3f})")
        print(f"part id: {part.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
