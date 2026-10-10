"""Ladder 3d, the two-body knob, as a parametric part (loft-script).

``docs/reference-parts/ladder.md`` 3d, built through the gateway with a
parameter table (Fusion 360's Change Parameters; PART-PARAMETERS step 9):
every driving dimension is a named parameter, and the ladder's edit, flutes
18 -> 24, is ONE ``part.set_parameter("flutes", "24")``.

Part (mm, Z up, two bodies in one part):

* Body 1: a Ø40 x 22 cylinder with a spherical cap R50 on top (rim Ø40), one
  revolve of its half-section about Z. 18 R2 flutes on axes on Ø42, cut up
  through the cap, as a circular pattern whose count is the parameter
  ``flutes``. A D-bore Ø6 with its flat 4.5 across from the far side of the
  bore, 15 deep from the bottom.
* Body 2: the Ø46 band from Z 6 to Z 16 minus body 1, so it fills the flutes.
  Read as a band ROUND body 1: the D-bore is not filled.

How it is built, and what is a workaround (a finding each, BACKLOG notes): a
boolean consumes its tool body, with no "keep tools" (Fusion's Combine), so
body 2 is not band minus body 1. It is built as what that boolean leaves: an
annulus Ø46/Ø40 extruded as a new body, plus one flute-fill cylinder (the
flute's R2 circle) patterned ``flutes`` times into it. The two bodies then
share the flute walls and the Ø40 face and overlap nowhere, which the STEP
check measures.

Independent check (no kernel): cylinder and spherical cap in closed form; a
flute removes a lens (circle-circle intersection, closed form) times the
cylinder height plus a sliver of the cap, a 1D integral over the lens' radial
span. The STEP export is re-read by OCCT outside the app: two solids, each
volume, and their common volume, which must be zero.

Run against a live gateway::

    uv run python docs/reference-parts/knob.py --url http://127.0.0.1:8000

The run exits 1 when a check misses its expected value by more than 1e-4.
"""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import loft
from formula_sketch import Placer, Row, Timer, check, define, offset_datum
from loft.part import Part
from loft.sketch import Sketch
from loft_wire.expr import Quantity
from loft_wire.features import (
    CircularPatternParamsV1,
    FeatureRef,
    OriginAxis,
    PatternFeature,
    PatternFeaturesScope,
    PatternParamsV1,
    RevolveFeature,
    RevolveParamsV1,
)
from loft_wire.geometry import Vec3


@dataclass(frozen=True)
class Knob:
    knob_d: float = 40.0
    knob_h: float = 22.0
    cap_r: float = 50.0
    flutes: int = 18
    flute_r: float = 2.0
    flute_pcd: float = 42.0
    bore_d: float = 6.0
    bore_flat: float = 4.5
    bore_depth: float = 15.0
    band_d: float = 46.0
    band_z: float = 6.0
    band_h: float = 10.0

    @property
    def cap_h(self) -> float:
        a, r = self.knob_d / 2, self.cap_r
        return r - math.sqrt(r * r - a * a)


def parameter_table(k: Knob) -> list[Row]:
    return [
        ("knob_d", f"{k.knob_d:g}", None, "body 1 diameter"),
        ("knob_h", f"{k.knob_h:g}", None, "body 1 cylinder height"),
        ("cap_r", f"{k.cap_r:g}", None, "spherical cap radius"),
        (
            "cap_h",
            "cap_r - cap_r * sqrt(1 - (knob_d / (2 * cap_r)) * (knob_d / (2 * cap_r)))",
            None,
            "cap height over the rim",
        ),
        ("flutes", f"{k.flutes}", "unitless", "flute count"),
        ("flute_r", f"{k.flute_r:g}", None, "flute radius"),
        ("flute_pcd", f"{k.flute_pcd:g}", None, "flute axes' circle diameter"),
        ("bore_d", f"{k.bore_d:g}", None, "D-bore diameter"),
        ("bore_flat", f"{k.bore_flat:g}", None, "D-bore across the flat"),
        ("bore_depth", f"{k.bore_depth:g}", None, "D-bore depth"),
        ("band_d", f"{k.band_d:g}", None, "body 2 band diameter"),
        ("band_z", f"{k.band_z:g}", None, "body 2 band bottom"),
        ("band_h", f"{k.band_h:g}", None, "body 2 band height"),
    ]


# --------------------------------------------------------------------------
# Hand-derived expectations (no kernel)
# --------------------------------------------------------------------------


def lens_area(big: float, small: float, d: float) -> float:
    """Area common to circles of radii ``big`` and ``small``, centres ``d`` apart."""
    return (
        small**2 * math.acos((d * d + small * small - big * big) / (2 * d * small))
        + big**2 * math.acos((d * d + big * big - small * small) / (2 * d * big))
        - 0.5
        * math.sqrt(
            (-d + small + big)
            * (d + small - big)
            * (d - small + big)
            * (d + small + big)
        )
    )


def expected(k: Knob) -> dict[str, float]:
    a, b = k.knob_d / 2, k.band_d / 2
    big_r, d, r = k.cap_r, k.flute_pcd / 2, k.flute_r
    rim = math.sqrt(big_r**2 - a**2)
    cylinder = math.pi * a * a * k.knob_h
    cap = math.pi * k.cap_h**2 * (3 * big_r - k.cap_h) / 3

    # A flute at radius rho spans 2 phi(rho) of the circle of radius rho.
    def phi(rho: float) -> float:
        c = (rho * rho + d * d - r * r) / (2 * rho * d)
        return math.acos(max(-1.0, min(1.0, c)))

    n, lo = 200_000, d - r
    h = (a - lo) / n
    rhos = [lo + (i + 0.5) * h for i in range(n)]
    lens = lens_area(a, r, d)
    lens_numeric = h * sum(2 * phi(p) * p for p in rhos)
    assert abs(lens_numeric / lens - 1) < 1e-6, (lens_numeric, lens)
    sliver = h * sum(2 * phi(p) * p * (math.sqrt(big_r**2 - p * p) - rim) for p in rhos)

    rb, f = k.bore_d / 2, k.bore_flat - k.bore_d / 2
    d_area = math.pi * rb * rb - (
        rb * rb * math.acos(f / rb) - f * math.sqrt(rb * rb - f * f)
    )

    body1 = (
        cylinder + cap - k.flutes * (lens * k.knob_h + sliver) - d_area * k.bore_depth
    )
    body2 = (math.pi * (b * b - a * a) + k.flutes * lens) * k.band_h
    return {"part": body1 + body2, "body 1": body1, "body 2": body2}


# --------------------------------------------------------------------------
# Modelling through loft-script
# --------------------------------------------------------------------------


def circular_pattern(part: Part, name: str, feature: uuid.UUID, k: Knob) -> None:
    part.create_feature(
        name,
        PatternFeature(
            type="pattern",
            version=1,
            params=PatternParamsV1(
                pattern=CircularPatternParamsV1(
                    axis_point=Vec3(x=0.0, y=0.0, z=0.0),
                    axis_direction=Vec3(x=0.0, y=0.0, z=1.0),
                    angle_deg=360.0,
                    count=k.flutes,
                ),
                scope=PatternFeaturesScope(
                    kind="features",
                    features=[FeatureRef(kind="feature", feature_id=feature)],
                ),
            ),
            expressions={"/pattern/count": "flutes"},
        ),
    )


def flute_circle(sk: Sketch, k: Knob, values: Mapping[str, Quantity]) -> None:
    """One flute's R2 circle on the +X axis, at half the flute PCD."""
    at = Placer(sk, values)
    d = k.flute_pcd / 2
    ray = sk.line((0.0, 0.0), (d, 0.0), construction=True)
    sk.coincident((ray, "start"), (at.origin, "position"))
    sk.horizontal(ray)
    sk.distance(ray, "flute_pcd/2")
    flute = sk.circle((d, 0.0), radius="flute_r")
    sk.coincident((flute, "center"), (ray, "end"))


def centred_circle(sk: Sketch, diameter: str, at: Placer) -> None:
    circle = sk.circle((0.0, 0.0), diameter=diameter)
    sk.coincident((circle, "center"), (at.origin, "position"))


def build(part: Part, k: Knob, timer: Timer) -> None:
    t0 = time.perf_counter()
    values = define(part, parameter_table(k))
    timer.step(f"parameter table ({len(values)} rows)", t0)

    # Body 1: the half-section on XZ (x is world X, y world Z), turned about Z.
    t0 = time.perf_counter()
    sk = part.sketch(on="XZ", name="Knob section")
    at = Placer(sk, values)
    a, top = k.knob_d / 2, k.knob_h + k.cap_h
    bottom = sk.line((0.0, 0.0), (a, 0.0))
    side = sk.line((a, 0.0), (a, k.knob_h))
    cap = sk.arc((0.0, k.knob_h - (k.cap_r - k.cap_h)), (a, k.knob_h), (0.0, top))
    axis = sk.line((0.0, top), (0.0, 0.0))
    sk.coincident((bottom, "start"), (at.origin, "position"))
    sk.horizontal(bottom)
    at.place(bottom, "end", "knob_d/2", None)
    sk.coincident((side, "start"), (bottom, "end"))
    at.place(side, "end", "knob_d/2", "knob_h")
    sk.coincident((cap, "start"), (side, "end"))
    sk.radius(cap, "cap_r")
    sk.coincident((cap, "end"), (axis, "start"))
    sk.coincident((axis, "end"), (at.origin, "position"))
    sk.vertical(axis)
    sk.distance(axis, "knob_h + cap_h")
    sk.save()
    part.create_feature(
        "Knob body",
        RevolveFeature(
            type="revolve",
            version=1,
            params=RevolveParamsV1(
                profile=sk.ref(),
                axis=OriginAxis(kind="origin_axis", axis="Z"),
                operation="add",
            ),
        ),
    )
    timer.step("body 1: revolved section", t0)

    t0 = time.perf_counter()
    flute = part.sketch(on="XY", name="Flute")
    flute_circle(flute, k, values)
    cut = part.extrude(flute, "knob_h + cap_h + 1", operation="cut", name="Flute cut")
    circular_pattern(part, "Flute pattern", cut.id, k)
    part.evaluate(strict=True)
    timer.step(f"flute cut + pattern x flutes={k.flutes}", t0)

    t0 = time.perf_counter()
    bore = part.sketch(on="XY", name="D-bore")
    at = Placer(bore, values)
    rb, f = k.bore_d / 2, k.bore_flat - k.bore_d / 2
    hw = math.sqrt(rb * rb - f * f)
    # The long way round, CCW from the flat's left end to its right end.
    arc = bore.arc((0.0, 0.0), (-hw, f), (hw, f))
    flat = bore.line((hw, f), (-hw, f))
    bore.coincident((arc, "center"), (at.origin, "position"))
    bore.diameter(arc, "bore_d")
    bore.coincident((flat, "start"), (arc, "end"))
    bore.coincident((flat, "end"), (arc, "start"))
    bore.horizontal(flat)
    at.place(flat, "start", None, "bore_flat - bore_d/2")
    part.extrude(bore, "bore_depth", operation="cut", name="D-bore")
    part.evaluate(strict=True)
    timer.step("D-bore", t0)

    # Body 2: an annulus over body 1 as a new body, then the flute fills.
    t0 = time.perf_counter()
    plane = offset_datum(part, "XY", "band_z", values, "Band plane")
    band = part.sketch(on=plane, name="Band")
    at = Placer(band, values)
    centred_circle(band, "band_d", at)
    centred_circle(band, "knob_d", at)
    part.extrude(band, "band_h", merge=False, name="Band (body 2)")
    fill = part.sketch(on=plane, name="Flute fill")
    flute_circle(fill, k, values)
    filled = part.extrude(fill, "band_h", name="Flute fill")
    circular_pattern(part, "Flute fill pattern", filled.id, k)
    part.evaluate(strict=True)
    timer.step("body 2: band + flute fill pattern", t0)


def verify_step(path: Path, want: dict[str, float]) -> bool:
    """Re-read the STEP outside the app: two bodies, each volume, no overlap."""
    try:
        from build123d import import_step  # type: ignore[import-untyped]
    except ImportError:  # pragma: no cover - QA-only dependency
        print("  (build123d not importable here: STEP re-read skipped)")
        return True
    solids = sorted(import_step(str(path)).solids(), key=lambda s: -s.volume)
    print(f"  STEP re-read: {len(solids)} solid(s)")
    if len(solids) != 2:
        return False
    ok = check("STEP body 1", solids[0].volume, want["body 1"])
    ok = check("STEP body 2", solids[1].volume, want["body 2"]) and ok
    common = solids[0].intersect(solids[1])  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    overlap = sum(s.volume for s in common.solids()) if common else 0.0  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownArgumentType]
    print(f"  STEP body 1 x body 2 common volume: {overlap:.3e} mm^3")
    return ok and overlap <= 1e-6


def measure(part: Part, k: Knob, label: str, step: bool, timer: Timer) -> bool:
    want = expected(k)
    t0 = time.perf_counter()
    props = part.mass_properties()
    timer.step(f"mass properties, {label}", t0)
    bb = props.bounding_box
    print(
        f"  bbox x {bb.min.x:.3f}..{bb.max.x:.3f} y {bb.min.y:.3f}..{bb.max.y:.3f} "
        f"z {bb.min.z:.3f}..{bb.max.z:.3f}; faces {props.topology.faces}"
    )
    ok = check(f"app volume (both bodies), {label}", props.volume, want["part"])
    if step:
        with tempfile.TemporaryDirectory() as tmp:
            ok = verify_step(part.export(Path(tmp) / "knob.step"), want) and ok
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--no-step", action="store_true", help="skip the STEP re-read")
    args = ap.parse_args()
    k = Knob()
    for label, value in expected(k).items():
        print(f"expected {label}: {value:.4f} mm^3")

    timer = Timer()
    email = f"knob-{uuid.uuid4().hex[:8]}@example.com"
    with loft.register(args.url, email=email, password="knob-script-pw-123") as session:
        part = session.new_part("Two-body knob (ladder 3d, parametric)")
        try:
            build(part, k, timer)
        except loft.LoftError as exc:
            print(f"FAILED: {exc.as_dict()}")
            return 1
        ok = measure(part, k, "18 flutes", not args.no_step, timer)

        t0 = time.perf_counter()
        part.set_parameter("flutes", "24")
        timer.step('set_parameter("flutes", "24")', t0)
        k2 = replace(k, flutes=24)
        for label, value in expected(k2).items():
            print(f"expected after edit {label}: {value:.4f} mm^3")
        ok = measure(part, k2, "24 flutes", not args.no_step, timer) and ok
        print(f"part id: {part.id}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
