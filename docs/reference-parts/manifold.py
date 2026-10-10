"""Ladder 2c, the hydraulic manifold, as a parametric part (loft-script).

``docs/reference-parts/ladder.md`` 2c, built through the gateway with a
parameter table (Fusion 360's Change Parameters; PART-PARAMETERS step 9):
every driving dimension is a named parameter, and the ladder's edit, height
50 -> 60, is ONE ``part.set_parameter("H", "60")``.

Part (6061, mm, X right, Y back, Z up): block L 80 x W 60 x H 50 from the
origin.

* Passage: Ø8 drilled 64 deep (to the shoulder, 118° point) from the left
  face at (Y 30, Z 25), closed by a G1/8 plug port at its mouth: spot face
  Ø15 x 1, Ø8.8 x 10.
* Port P on the top face at (X 20, Y 30) and port A on the front face at
  (X 60, Z 25), 34 deep; both G1/4: spot face Ø25 x 1, tap drill Ø11.4,
  118° point. P is drilled TO the passage: ``p_depth = H - pass_z`` takes its
  shoulder to the passage axis, so P follows the height edit.
* Four M6 x 12 tapped holes on the bottom at X 15/65, Y 10/50: tap drill Ø5,
  118° point, as a two-direction rectangular pattern.

How it is built, and what is a workaround (a finding each, BACKLOG notes):

* Each drilled hole is a REVOLVE CUT of its half-section (spot face, tap
  drill, cone point), sketched on a datum through its axis, the way a
  SolidWorks user models a custom port without the Hole Wizard. The Hole
  feature has no drill point angle and no "To" extent, and needs a picked
  face, which loft-script cannot pick; so the threads are not called out.
* Every sketch vertex is placed by two driving dimensions from the sketch
  origin, each a formula over the table (``formula_sketch.py``).

Independent check (no kernel): the cavity is the union of solids of
revolution; the two overlaps (P with the passage, A with the passage's drill
point) are 1D integrals of closed-form chord areas (``expected``). The STEP
export is re-read by OCCT outside the app: its volume, and the cavity
(the block minus the part) as solids, so P, A and the plug must form ONE
connected cavity beside the four M6 holes.

Run against a live gateway::

    uv run python docs/reference-parts/manifold.py --url http://127.0.0.1:8000

The run exits 1 when a check misses its expected value by more than 1e-4.
"""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import loft
from formula_sketch import Placer, Row, Timer, check, define, offset_datum, revolve_cut
from loft.part import Part
from loft_wire.expr import Quantity
from loft_wire.features import (
    FeatureRef,
    LinearPatternParamsV1,
    PatternFeature,
    PatternFeaturesScope,
    PatternParamsV1,
)
from loft_wire.geometry import Vec3


@dataclass(frozen=True)
class Manifold:
    L: float = 80.0
    W: float = 60.0
    H: float = 50.0
    point_deg: float = 118.0
    pass_d: float = 8.0
    pass_depth: float = 64.0
    pass_z: float = 25.0
    g18_spot: float = 15.0
    g18_spot_depth: float = 1.0
    g18_bore: float = 8.8
    g18_depth: float = 10.0
    g14_spot: float = 25.0
    g14_spot_depth: float = 1.0
    g14_drill: float = 11.4
    p_x: float = 20.0
    a_x: float = 60.0
    a_depth: float = 34.0
    m6_drill: float = 5.0
    m6_depth: float = 12.0
    m6_x: float = 15.0
    m6_y: float = 10.0
    m6_dx: float = 50.0
    m6_dy: float = 40.0

    @property
    def pass_y(self) -> float:
        return self.W / 2

    @property
    def p_depth(self) -> float:
        return self.H - self.pass_z

    def tip(self, diameter: float) -> float:
        """Length of a drill point of ``diameter`` past the shoulder."""
        return diameter / 2 / math.tan(math.radians(self.point_deg / 2))


def parameter_table(m: Manifold) -> list[Row]:
    return [
        ("L", f"{m.L:g}", None, "block length (X)"),
        ("W", f"{m.W:g}", None, "block width (Y)"),
        ("H", f"{m.H:g}", None, "block height (Z)"),
        ("drill_point", f"{m.point_deg:g} deg", None, "drill point angle"),
        ("pass_d", f"{m.pass_d:g}", None, "passage drill"),
        ("pass_depth", f"{m.pass_depth:g}", None, "passage depth to shoulder"),
        ("pass_y", "W / 2", None, "passage axis Y"),
        ("pass_z", f"{m.pass_z:g}", None, "passage axis Z"),
        ("g18_spot", f"{m.g18_spot:g}", None, "G1/8 plug port spot face"),
        ("g18_spot_depth", f"{m.g18_spot_depth:g}", None, "G1/8 spot face depth"),
        ("g18_bore", f"{m.g18_bore:g}", None, "G1/8 tap drill"),
        ("g18_depth", f"{m.g18_depth:g}", None, "G1/8 thread depth"),
        ("g14_spot", f"{m.g14_spot:g}", None, "G1/4 port spot face"),
        ("g14_spot_depth", f"{m.g14_spot_depth:g}", None, "G1/4 spot face depth"),
        ("g14_drill", f"{m.g14_drill:g}", None, "G1/4 tap drill"),
        ("p_x", f"{m.p_x:g}", None, "port P X (top face)"),
        ("p_y", "pass_y", None, "port P Y: over the passage"),
        ("p_depth", "H - pass_z", None, "port P drilled to the passage axis"),
        ("a_x", f"{m.a_x:g}", None, "port A X (front face)"),
        ("a_z", "pass_z", None, "port A Z: on the passage axis"),
        ("a_depth", f"{m.a_depth:g}", None, "port A depth to shoulder"),
        ("m6_drill", f"{m.m6_drill:g}", None, "M6 tap drill"),
        ("m6_depth", f"{m.m6_depth:g}", None, "M6 hole depth"),
        ("m6_x", f"{m.m6_x:g}", None, "first M6 hole X"),
        ("m6_y", f"{m.m6_y:g}", None, "first M6 hole Y"),
        ("m6_dx", f"{m.m6_dx:g}", None, "M6 pitch along X"),
        ("m6_dy", f"{m.m6_dy:g}", None, "M6 pitch along Y"),
    ]


# --------------------------------------------------------------------------
# Hand-derived expectations (no kernel)
# --------------------------------------------------------------------------


def chord_area(radius: float, half: float) -> float:
    """Area of the strip |t| <= half of a disc of ``radius`` (half <= radius):
    the integral of the chord 2 sqrt(radius^2 - t^2) over [-half, half]."""
    half = min(half, radius)
    if half <= 0.0:
        return 0.0
    return 2 * (
        half * math.sqrt(radius**2 - half**2) + radius**2 * math.asin(half / radius)
    )


def integrate(
    f: Callable[[float], float], lo: float, hi: float, n: int = 200_000
) -> float:
    """Midpoint rule; the integrands have only sqrt-type endpoint behaviour."""
    h = (hi - lo) / n
    return h * sum(f(lo + (k + 0.5) * h) for k in range(n))


def drilled(
    spot_d: float, spot_depth: float, d: float, depth: float, tip: float
) -> float:
    """Spot face + drill to the shoulder + cone point (depths from the face)."""
    r = d / 2
    return (
        math.pi * (spot_d / 2) ** 2 * spot_depth
        + math.pi * r**2 * (depth - spot_depth)
        + math.pi * r**2 * tip / 3
    )


def expected(m: Manifold) -> dict[str, float]:
    """Part volume, the main cavity (P + A + passage) and one M6 hole."""
    r_pass, r_g14 = m.pass_d / 2, m.g14_drill / 2
    tan_half = math.tan(math.radians(m.point_deg / 2))
    v_p = drilled(
        m.g14_spot, m.g14_spot_depth, m.g14_drill, m.p_depth, m.tip(m.g14_drill)
    )
    v_a = drilled(
        m.g14_spot, m.g14_spot_depth, m.g14_drill, m.a_depth, m.tip(m.g14_drill)
    )
    v_pass = (
        math.pi * (m.g18_spot / 2) ** 2 * m.g18_spot_depth
        + math.pi * (m.g18_bore / 2) ** 2 * (m.g18_depth - m.g18_spot_depth)
        + math.pi * r_pass**2 * (m.pass_depth - m.g18_depth)
        + math.pi * r_pass**2 * m.tip(m.pass_d) / 3
    )
    v_m6 = drilled(m.m6_drill, m.m6_depth, m.m6_drill, m.m6_depth, m.tip(m.m6_drill))

    # P (vertical, axis over the passage axis) with the passage: at height z
    # P is a disc of radius R(z), the passage a strip |y - pass_y| <= s(z), so
    # the overlap's cross-section is a chord area. P's shoulder is at the
    # passage axis, its point below it; the passage is Ø8 there (x = 20).
    shoulder = m.H - m.p_depth
    tip_p = shoulder - m.tip(m.g14_drill)

    def p_section(z: float) -> float:
        radius = r_g14 if z >= shoulder else (z - tip_p) * tan_half
        return chord_area(radius, math.sqrt(max(0.0, r_pass**2 - (z - m.pass_z) ** 2)))

    i_p = integrate(p_section, max(tip_p, m.pass_z - r_pass), m.pass_z + r_pass)

    # A (along +Y, axis on the passage axis' Z) with the passage and its drill
    # point: at station x the passage is a disc of radius r(x), A a strip
    # |z - a_z| <= c(x). A is at full radius over the passage's whole Y span.
    assert m.g14_spot_depth < m.pass_y - r_pass and m.a_depth >= m.pass_y + r_pass
    x_tip = m.pass_depth + m.tip(m.pass_d)

    def a_section(x: float) -> float:
        radius = r_pass if x <= m.pass_depth else max(0.0, (x_tip - x) * tan_half)
        return chord_area(radius, math.sqrt(max(0.0, r_g14**2 - (x - m.a_x) ** 2)))

    i_a = integrate(a_section, m.a_x - r_g14, min(m.a_x + r_g14, x_tip))

    main = v_p + v_a + v_pass - i_p - i_a
    return {
        "part": m.L * m.W * m.H - main - 4 * v_m6,
        "main cavity": main,
        "M6 hole": v_m6,
    }


# --------------------------------------------------------------------------
# Modelling through loft-script
# --------------------------------------------------------------------------


def port(
    part: Part,
    base: str,
    offset: str,
    corners: list[tuple[str, str]],
    values: dict[str, Quantity],
    name: str,
) -> uuid.UUID:
    """A drilled hole: its half-section on a datum through the axis, revolved.

    The LAST corner joins the first along the drill axis, which is the
    revolve axis.
    """
    plane = offset_datum(part, base, offset, values, f"{name} plane")
    sk = part.sketch(on=plane, name=f"{name} section")
    lines = Placer(sk, values).polygon(corners)
    sk.save()
    return revolve_cut(part, sk, lines[-1], name)


def linear_pattern(
    part: Part,
    name: str,
    features: list[uuid.UUID],
    direction: Vec3,
    spacing: str,
    values: dict[str, Quantity],
) -> uuid.UUID:
    created = part.create_feature(
        name,
        PatternFeature(
            type="pattern",
            version=1,
            params=PatternParamsV1(
                pattern=LinearPatternParamsV1(
                    direction=direction,
                    spacing_mm=values[spacing].value,
                    count=2,
                ),
                scope=PatternFeaturesScope(
                    kind="features",
                    features=[
                        FeatureRef(kind="feature", feature_id=f) for f in features
                    ],
                ),
            ),
            expressions={"/pattern/spacing_mm": spacing},
        ),
    )
    return created.feature.id


def build(part: Part, m: Manifold, timer: Timer) -> None:
    t0 = time.perf_counter()
    values = define(part, parameter_table(m))
    timer.step(f"parameter table ({len(values)} rows)", t0)

    t0 = time.perf_counter()
    block = part.sketch(on="XY", name="Block")
    block.rect("L", "W")
    part.extrude(block, "H", name="Block")
    timer.step("block", t0)

    point = "/tan(drill_point/2)"
    t0 = time.perf_counter()
    # On an XY datum sketch x is world X and y world Y.
    port(
        part,
        "XY",
        "pass_z",
        [
            ("-1", "pass_y"),
            ("-1", "pass_y + g18_spot/2"),
            ("g18_spot_depth", "pass_y + g18_spot/2"),
            ("g18_spot_depth", "pass_y + g18_bore/2"),
            ("g18_depth", "pass_y + g18_bore/2"),
            ("g18_depth", "pass_y + pass_d/2"),
            ("pass_depth", "pass_y + pass_d/2"),
            (f"pass_depth + pass_d/2{point}", "pass_y"),
        ],
        values,
        "Passage + G1/8 plug port",
    )
    # On an XZ datum sketch x is world X and y world Z; its normal is -Y.
    port(
        part,
        "XZ",
        "-p_y",
        [
            ("p_x", "H + 1"),
            ("p_x + g14_spot/2", "H + 1"),
            ("p_x + g14_spot/2", "H - g14_spot_depth"),
            ("p_x + g14_drill/2", "H - g14_spot_depth"),
            ("p_x + g14_drill/2", "H - p_depth"),
            ("p_x", f"H - p_depth - g14_drill/2{point}"),
        ],
        values,
        "Port P (G1/4, to the passage)",
    )
    port(
        part,
        "XY",
        "a_z",
        [
            ("a_x", "-1"),
            ("a_x + g14_spot/2", "-1"),
            ("a_x + g14_spot/2", "g14_spot_depth"),
            ("a_x + g14_drill/2", "g14_spot_depth"),
            ("a_x + g14_drill/2", "a_depth"),
            ("a_x", f"a_depth + g14_drill/2{point}"),
        ],
        values,
        "Port A (G1/4)",
    )
    part.evaluate(strict=True)
    timer.step("passage + plug, P, A: three revolve cuts", t0)

    t0 = time.perf_counter()
    hole = port(
        part,
        "XZ",
        "-m6_y",
        [
            ("m6_x", "-1"),
            ("m6_x + m6_drill/2", "-1"),
            ("m6_x + m6_drill/2", "m6_depth"),
            ("m6_x", f"m6_depth + m6_drill/2{point}"),
        ],
        values,
        "M6 tap drill",
    )
    along_x = linear_pattern(
        part, "M6 pattern X", [hole], Vec3(x=1.0, y=0.0, z=0.0), "m6_dx", values
    )
    linear_pattern(
        part,
        "M6 pattern Y",
        [hole, along_x],
        Vec3(x=0.0, y=1.0, z=0.0),
        "m6_dy",
        values,
    )
    part.evaluate(strict=True)
    timer.step("M6 hole + 2 x 2 pattern", t0)


def verify_step(path: Path, m: Manifold, want: dict[str, float]) -> bool:
    """Re-read the STEP outside the app: the part, and the cavity as solids."""
    try:
        from build123d import Align, Box, import_step  # type: ignore[import-untyped]
    except ImportError:  # pragma: no cover - QA-only dependency
        print("  (build123d not importable here: STEP re-read skipped)")
        return True
    shape = import_step(str(path))
    ok = check("STEP part volume", shape.volume, want["part"])
    cavity = Box(m.L, m.W, m.H, align=(Align.MIN, Align.MIN, Align.MIN)) - shape
    pieces = sorted(cavity.solids(), key=lambda s: -s.volume)
    print(f"  cavity (block minus part): {len(pieces)} solid(s)")
    if len(pieces) != 5:
        print("  FAIL: expected one connected P + A + plug cavity and four M6 holes")
        return False
    ok = check("STEP main cavity", pieces[0].volume, want["main cavity"]) and ok
    for k, hole in enumerate(pieces[1:]):
        ok = check(f"STEP M6 hole {k + 1}", hole.volume, want["M6 hole"]) and ok
    # Key dimensions: each M6 hole's axis sits on its grid point.
    grid = [
        (m.m6_x + i * m.m6_dx, m.m6_y + j * m.m6_dy) for i in (0, 1) for j in (0, 1)
    ]
    off = max(
        min(math.dist((h.center().X, h.center().Y), p) for p in grid)
        for h in pieces[1:]
    )
    print(f"  M6 axes off their grid points by at most {off:.2e} mm")
    return ok and off <= 1e-6


def measure(part: Part, m: Manifold, label: str, step: bool, timer: Timer) -> bool:
    want = expected(m)
    t0 = time.perf_counter()
    props = part.mass_properties()
    timer.step(f"mass properties, {label}", t0)
    bb = props.bounding_box
    print(
        f"  bbox {bb.max.x - bb.min.x:.3f} x {bb.max.y - bb.min.y:.3f} x "
        f"{bb.max.z - bb.min.z:.3f}; faces {props.topology.faces}"
    )
    ok = check(f"app volume, {label}", props.volume, want["part"])
    if step:
        with tempfile.TemporaryDirectory() as tmp:
            ok = verify_step(part.export(Path(tmp) / "manifold.step"), m, want) and ok
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--no-step", action="store_true", help="skip the STEP re-read")
    args = ap.parse_args()
    m = Manifold()
    for label, value in expected(m).items():
        print(f"expected {label}: {value:.4f} mm^3")

    timer = Timer()
    email = f"manifold-{uuid.uuid4().hex[:8]}@example.com"
    with loft.register(args.url, email=email, password="manifold-pw-12345") as session:
        part = session.new_part("Hydraulic manifold (ladder 2c, parametric)")
        try:
            build(part, m, timer)
        except loft.LoftError as exc:
            print(f"FAILED: {exc.as_dict()}")
            return 1
        ok = measure(part, m, "H = 50", not args.no_step, timer)

        t0 = time.perf_counter()
        part.set_parameter("H", "60")
        timer.step('set_parameter("H", "60")', t0)
        m2 = replace(m, H=60.0)
        for label, value in expected(m2).items():
            print(f"expected after edit {label}: {value:.4f} mm^3")
        ok = measure(part, m2, "H = 60", not args.no_step, timer) and ok
        print(f"part id: {part.id}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
