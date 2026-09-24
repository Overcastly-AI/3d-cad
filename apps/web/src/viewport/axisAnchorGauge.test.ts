/**
 * THE ANGULAR GAUGES' ARITHMETIC.
 *
 * Two of these cases exist because `angularTrack` shipped with NO CONSUMER and
 * this is its first one — the condition under which an interface defect cannot
 * be observed. Both were found by mounting it, both are fixed by composition
 * here, and both are the kind that look correct in a screenshot:
 *
 *  · THE LADDER COULD NOT REACH ITS FINEST RUNG. The package floors its minor at
 *    5 degrees, so a draft at its everyday 3-degree default came back with fewer
 *    than three marks and the signature element vanished at the one value it is
 *    used at most. And the obvious fix is silently wrong in the same way: picking
 *    the COARSEST candidate that fits means 5 wins at every zoom where 1 would
 *    also fit, so the 1-degree rung is never once drawn.
 *  · `valueAt` WRAPS INTO [0, 360), WHICH A SIGNED RANGE CANNOT USE. A draft
 *    lives in (-90, 90); a pointer a hair below the reference reads 359.7 and
 *    the clamp then slams the value to the far end of the range.
 */
import { describe, expect, it } from "vitest";

import { LADDER_MIN_RUNGS, MAX_RUNGS, type Vec3 } from "@loft/design";

import { MAX_TWIST_DEG } from "../features/extrude";
import {
  ANGLE_KEY_STEP_DEG,
  angularStops,
  arcPoint,
  draftGaugeTrack,
  MAX_DRAFT_DEG,
  MAX_REVOLVE_DEG,
  MIN_DRAFT_DEG,
  MIN_REVOLVE_DEG,
  revolveGaugeTrack,
  revolveSweepLines,
  rotateAboutAxis,
  twistGaugeTrack,
  type ArcSeat,
} from "./axisAnchorGauge";

/** A protractor of radius 20 about +Y, measuring from +X. */
const SEAT: ArcSeat = {
  centre: [0, 0, 0],
  axis: [0, 1, 0],
  reference: [1, 0, 0],
  arcRadiusMm: 20,
  seatRadiusMm: 20,
};

/** mm per CSS pixel at which one degree of a radius-20 arc is `px` pixels. */
function perPixelForDegree(deg: number, px: number): number {
  return (((deg * Math.PI) / 180) * SEAT.arcRadiusMm) / px;
}

describe("angularStops — the ladder is 15/5, not the linear one rotated", () => {
  it("rules a comfortable sweep at 15 major / 5 minor", () => {
    // 5 degrees of arc at ~10 px clears the minor floor (7) and 15 at ~30 px
    // clears the major floor (14); 1 degree at 2 px does not.
    const stops = angularStops(90, 20, perPixelForDegree(1, 2));
    expect(stops.majorStep).toBe(15);
    expect(stops.pitch).toBe(5);
    expect(stops.major).toEqual([15, 30, 45, 60, 75]);
    expect(stops.minor).toContain(5);
    expect(stops.minor).not.toContain(15);
  });

  it("NEVER produces a decade series — no 10, 20 or 50 anywhere", () => {
    // The failure mode the direction pass names by number. A builder extending
    // the linear ladder gets 10/20/50, which no machinist uses.
    for (const px of [0.5, 2, 6, 14, 40, 120]) {
      const stops = angularStops(360, 20, perPixelForDegree(1, px));
      for (const step of [stops.majorStep, stops.pitch]) {
        expect([1, 5, 10, 15, 30, 45, 90]).toContain(step);
      }
      expect([10, 20, 50]).not.toContain(stops.majorStep);
    }
  });

  it("SUBDIVIDES TO 1 when there is room — the rung the package cannot reach", () => {
    // Finest-first is the whole point: at this zoom 5 also clears its floor, so
    // a coarsest-first walk would pick 5 and look entirely correct.
    const stops = angularStops(30, 20, perPixelForDegree(1, 9));
    expect(stops.pitch).toBe(1);
    expect(stops.majorStep).toBe(15);
    expect(stops.minor).toContain(7);
    expect(stops.minor).not.toContain(15);
  });

  it("COARSENS to 30, 45 and 90 as the arc shortens on screen", () => {
    expect(angularStops(360, 20, perPixelForDegree(15, 13)).majorStep).toBe(30);
    expect(angularStops(360, 20, perPixelForDegree(30, 13)).majorStep).toBe(45);
    expect(angularStops(360, 20, perPixelForDegree(45, 13)).majorStep).toBe(90);
  });

  it("gives back a THIRD-of-major minor when one fits, never a decade", () => {
    // 30 promoted, 10 below it — and 10 is not a decade rung here, it is a
    // third of 30, which is why the sequence stays 1/5/15/30 rather than
    // becoming 10/20/50.
    expect(angularStops(360, 20, perPixelForDegree(15, 13)).pitch).toBe(10);
  });

  it("drops the minor entirely when a third of the major cannot clear the floor", () => {
    // MEASURED, and it is structural rather than a tuning accident: a major is
    // promoted precisely because the one below it fell under the MAJOR floor
    // (14 px), and a third of the promoted major is HALF of the one that just
    // failed. For 45 that is 15 px-worth of arc at under 7 px — so a 45 major
    // can never carry a 15 minor, at any camera, and the honest answer is a
    // ladder of majors alone rather than a rung nobody can see.
    const stops = angularStops(360, 20, perPixelForDegree(30, 13));
    expect(stops.majorStep).toBe(45);
    expect(stops.pitch).toBe(45);
    expect(stops.minor).toHaveLength(0);
    expect(stops.major.length).toBeGreaterThanOrEqual(LADDER_MIN_RUNGS);
  });

  it("holds the rung ceiling at a close camera on a full turn", () => {
    // A 1-degree minor across 360 would be 360 crosses: a hairbrush, and a
    // vertex buffer nobody asked for.
    const stops = angularStops(360, 20, perPixelForDegree(1, 40));
    expect(stops.major.length + stops.minor.length).toBeLessThanOrEqual(
      MAX_RUNGS,
    );
    expect(stops.major.length + stops.minor.length).toBeGreaterThanOrEqual(
      LADDER_MIN_RUNGS,
    );
  });

  it("draws NO ladder rather than two marks", () => {
    // A 3-degree draft at a normal camera: there is genuinely nothing to rule
    // against, and the honest answer is a plain arrow.
    expect(angularStops(3, 5, perPixelForDegree(1, 2)).major).toHaveLength(0);
    expect(angularStops(3, 5, perPixelForDegree(1, 2)).pitch).toBe(0);
  });

  it("is blind to the sign — a signed track passes its magnitude", () => {
    const a = angularStops(60, 20, perPixelForDegree(1, 2));
    const b = angularStops(-60, 20, perPixelForDegree(1, 2));
    expect(b).toEqual(a);
  });

  it("returns nothing for a degenerate seat rather than NaN rungs", () => {
    expect(angularStops(90, 0, 0.01).pitch).toBe(0);
    expect(angularStops(0, 20, 0.01).pitch).toBe(0);
  });

  it("never rules a graduation ON or PAST the arrowhead", () => {
    const stops = angularStops(45, 20, perPixelForDegree(1, 2));
    for (const d of [...stops.major, ...stops.minor]) {
      expect(d).toBeGreaterThan(0);
      expect(d).toBeLessThan(45);
    }
  });
});

describe("revolveGaugeTrack", () => {
  const track = revolveGaugeTrack(SEAT);

  it("places the grip on the arc, at the angle", () => {
    expect(track.pointAt(0)[0]).toBeCloseTo(20, 9);
    const at90 = track.pointAt(90);
    expect(at90[0]).toBeCloseTo(0, 9);
    expect(at90[2]).toBeCloseTo(-20, 9);
    // and always ON the circle, whatever the angle.
    for (const deg of [17, 123, 259, 360]) {
      const p = track.pointAt(deg);
      expect(Math.hypot(p[0], p[1], p[2])).toBeCloseTo(20, 9);
    }
  });

  it("clamps to a sweep the form can actually submit", () => {
    // `parseAngleDeg` rejects <= 0 and > 360, so a drag that could reach either
    // would leave the editor in a state its own Save refuses — the dead end the
    // flow rule's fourth test forbids. Same reasoning as MIN_DEPTH_MM.
    expect(track.clamp(-40)).toBe(MIN_REVOLVE_DEG);
    expect(track.clamp(0)).toBe(MIN_REVOLVE_DEG);
    expect(track.clamp(400)).toBe(MAX_REVOLVE_DEG);
    expect(track.clamp(360)).toBe(360);
  });

  it("speaks degrees, with the sign written into the number", () => {
    expect(track.format(45)).toBe("45°");
    expect(track.format(45, { unitSuffix: false })).toBe("45");
  });

  it("steps one degree per arrow press and lands on the degree grid", () => {
    expect(track.step({ major: [], minor: [], pitch: 0, majorStep: 0 })).toBe(
      ANGLE_KEY_STEP_DEG,
    );
    expect(track.nudge(44.6, "ArrowUp", false)).toBe(45);
    expect(track.nudge(45, "ArrowDown", false)).toBe(44);
    // Non-value keys fall through, or Enter could never reach the form's submit.
    expect(track.nudge(45, "Enter", false)).toBeNull();
    expect(track.nudge(45, "a", false)).toBeNull();
  });

  it("takes a coarse press to the next TEN-degree mark, not current+10", () => {
    // Each press lands on ITS OWN grid (`steppedValue`'s rule), so a coarse
    // press from 45 goes to 50 rather than 55 — the same behaviour the depth
    // gauge has, and the reason a drag that left you on 43.7 does not leave
    // every later key press off-grid.
    expect(track.nudge(45, "ArrowUp", true)).toBe(50);
    expect(track.nudge(45, "PageUp", false)).toBe(50);
    expect(track.nudge(43.7, "ArrowUp", true)).toBe(50);
    expect(track.nudge(45, "ArrowDown", true)).toBe(40);
  });

  it("snaps a drag TO THE DRAWN LADDER, not to a private grid", () => {
    // "The rungs ARE the stops": a drag obeying a scale other than the one on
    // screen is the decorative-chrome defect inside the signature element.
    const fine = angularStops(30, 20, perPixelForDegree(1, 9));
    expect(fine.pitch).toBe(1);
    expect(track.quantize(23.4, false, fine)).toBe(23);
    // Ctrl frees it.
    expect(track.quantize(23.4, true, fine)).toBeCloseTo(23.4, 9);
    // And a COARSER ladder snaps coarser, from the same call — the drag obeys
    // whatever is currently drawn rather than a constant.
    const coarse = angularStops(90, 20, perPixelForDegree(1, 2));
    expect(coarse.pitch).toBe(5);
    expect(track.quantize(43.4, false, coarse)).toBe(45);
  });

  it("cannot be dragged to an unsubmittable value even when freed", () => {
    expect(track.quantize(999, true)).toBe(MAX_REVOLVE_DEG);
    expect(track.quantize(-5, true)).toBe(MIN_REVOLVE_DEG);
  });

  it("recognises its own value coming back through a display string", () => {
    expect(track.same(45, 45.00000001)).toBe(true);
    expect(track.same(45, 45.5)).toBe(false);
  });

  it("uses the composed ladder, not the package's own floor", () => {
    // The seam under test: the package's `stops` cannot return a 1-degree pitch
    // at any zoom, so reading it here proves the override is wired.
    expect(track.stops(30, perPixelForDegree(1, 9)).pitch).toBe(1);
  });
});

describe("draftGaugeTrack — the sign rides on the axis, not on the value", () => {
  const positive = draftGaugeTrack(SEAT, 1);
  const negative = draftGaugeTrack(SEAT, -1);

  it("formats the SIGNED angle from a magnitude value", () => {
    // `aria-valuenow` is the magnitude; `valueText` is what the user reads, and
    // it must agree with the field they typed into.
    expect(positive.format(3)).toBe("3°");
    expect(negative.format(3)).toBe("-3°");
    expect(negative.format(3, { unitSuffix: false })).toBe("-3");
  });

  it("sweeps the OTHER WAY for a negative taper", () => {
    // Same magnitude, mirrored arc — so the instrument never doubles back over
    // the geometry it is dimensioning.
    const p = positive.pointAt(30);
    const n = negative.pointAt(30);
    expect(n[0]).toBeCloseTo(p[0], 9);
    expect(n[2]).toBeCloseTo(-p[2], 9);
  });

  it("never reaches zero, which is the one value the form refuses", () => {
    // "A draft needs a non-zero angle to taper by." A drag that could land there
    // would walk the user into a dead end.
    expect(positive.clamp(0)).toBe(MIN_DRAFT_DEG);
    expect(positive.clamp(-20)).toBe(MIN_DRAFT_DEG);
    expect(positive.clamp(95)).toBe(MAX_DRAFT_DEG);
    expect(MAX_DRAFT_DEG).toBeLessThan(90);
  });

  it("never returns a value the kernel's open interval would reject", () => {
    for (const raw of [-1000, -0.0001, 0, 89.99, 90, 1e6]) {
      const q = positive.quantize(raw, true);
      expect(q).toBeGreaterThanOrEqual(MIN_DRAFT_DEG);
      expect(q).toBeLessThan(90);
    }
  });

  it("rules the same ladder as the revolve gauge", () => {
    expect(positive.stops(30, perPixelForDegree(1, 9)).pitch).toBe(1);
    expect(negative.stops(30, perPixelForDegree(1, 9)).pitch).toBe(1);
  });
});

describe("twistGaugeTrack — signed, through zero, and past a whole turn", () => {
  /** The pointer ray straight down onto SEAT's arc at `deg` (perp is -Z). */
  function rayAt(deg: number): [Vec3, Vec3] {
    const r = (deg * Math.PI) / 180;
    return [
      [20 * Math.cos(r), 10, -20 * Math.sin(r)],
      [0, -1, 0],
    ];
  }

  it("reads a pointer just short of the reference as a small NEGATIVE twist", () => {
    // The package answers 350 here, which the drag would read as +350: a
    // left-hand nudge turning the part almost a full turn right-hand.
    const track = twistGaugeTrack(SEAT);
    expect(track.valueAt(...rayAt(-10))).toBeCloseTo(-10, 6);
  });

  it("UNWRAPS: a pointer circling the axis keeps counting past 360", () => {
    // The drag reads grab + (at - atGrab), so a wrapped answer would snap a
    // twist of 370 back to 10 as the pointer crossed the reference.
    const track = twistGaugeTrack(SEAT);
    const seen: number[] = [];
    for (let deg = 0; deg <= 740; deg += 20) {
      seen.push(track.valueAt(...rayAt(deg)) ?? Number.NaN);
    }
    expect(seen[seen.length - 1]).toBeCloseTo(740, 6);
    for (let i = 1; i < seen.length; i += 1) {
      expect((seen[i] as number) - (seen[i - 1] as number)).toBeCloseTo(20, 6);
    }
    // and back down through zero into a left-hand twist.
    let value = 0;
    for (let deg = 740; deg >= -400; deg -= 20) {
      value = track.valueAt(...rayAt(deg)) ?? Number.NaN;
    }
    expect(value).toBeCloseTo(-400, 6);
  });

  it("spans exactly the contract's range, zero included", () => {
    const track = twistGaugeTrack(SEAT);
    expect(track.clamp(0)).toBe(0);
    expect(track.clamp(-5000)).toBe(-MAX_TWIST_DEG);
    expect(track.clamp(5000)).toBe(MAX_TWIST_DEG);
    expect(track.quantize(-12.4, false)).toBe(-10);
    expect(track.nudge(0, "ArrowDown", false)).toBe(-1);
  });

  it("rules its ladder on the side the twist is on", () => {
    const track = twistGaugeTrack(SEAT);
    const upp = perPixelForDegree(1, 2);
    const right = track.stops(90, upp);
    const left = track.stops(-90, upp);
    expect(right.major).toEqual([15, 30, 45, 60, 75]);
    expect(left.major).toEqual([-15, -30, -45, -60, -75]);
    expect(left.pitch).toBe(right.pitch);
    // The drawn rungs of a left-hand sweep sit on the left-hand arc.
    const drawn = track.draw(-90, left);
    const firstRung = drawn.rungs[0] as readonly [Vec3, Vec3];
    const mid = (firstRung[0][2] + firstRung[1][2]) / 2;
    expect(mid).toBeGreaterThan(0);
  });

  it("speaks the signed angle", () => {
    const track = twistGaugeTrack(SEAT);
    expect(track.format(-30)).toBe("-30°");
    expect(track.format(720)).toBe("720°");
  });
});

describe("rotateAboutAxis / arcPoint", () => {
  it("rotates a point about the seat's axis", () => {
    const r = rotateAboutAxis(SEAT, [20, 7, 0], 90);
    expect(r[0]).toBeCloseTo(0, 9);
    expect(r[1]).toBeCloseTo(7, 9);
    expect(r[2]).toBeCloseTo(-20, 9);
  });

  it("is the SAME parametrisation the gauge's own arc uses", () => {
    // DRY, and load-bearing: a preview computed on a second circle would drift
    // from the instrument by whatever the two derivations disagreed about, and
    // the disagreement is invisible until somebody looks at a large angle.
    const track = revolveGaugeTrack(SEAT);
    for (const deg of [0, 37, 180, 359]) {
      const a = arcPoint(SEAT, deg, SEAT.arcRadiusMm);
      const b = track.pointAt(deg);
      expect(a[0]).toBeCloseTo(b[0], 9);
      expect(a[1]).toBeCloseTo(b[1], 9);
      expect(a[2]).toBeCloseTo(b[2], 9);
    }
  });
});

describe("revolveSweepLines — the result preview (route b)", () => {
  /** A 4-point square loop offset from the axis. */
  const LOOP = [
    [10, -5, 0],
    [20, -5, 0],
    [20, 5, 0],
    [10, 5, 0],
  ] as const;

  it("draws the END SECTION at the current angle, and it MOVES", () => {
    const at90 = revolveSweepLines(SEAT, [LOOP], 90);
    const at180 = revolveSweepLines(SEAT, [LOOP], 180);
    expect(at90.length).toBeGreaterThan(0);
    // The end section is the first four segments (the closed loop).
    expect(at90[0]).toBeCloseTo(0, 6);
    expect(at90[2]).toBeCloseTo(-10, 6);
    expect(at180[0]).toBeCloseTo(-10, 6);
    expect(at180[2]).toBeCloseTo(0, 6);
  });

  it("every drawn point stays on its own sweep circle", () => {
    const buf = revolveSweepLines(SEAT, [LOOP], 200);
    // Each vertex keeps its distance from the axis and its height along it.
    for (let i = 0; i < buf.length; i += 3) {
      const r = Math.hypot(buf[i]!, buf[i + 2]!);
      expect(r).toBeGreaterThanOrEqual(10 - 1e-6);
      expect(r).toBeLessThanOrEqual(20 + 1e-6);
    }
  });

  it("bounds the rails INDEPENDENTLY of how dense the loop is", () => {
    // The property that matters for a drag: the rail cost must not grow with
    // the profile's vertex count, or an arc-approximated loop rebuilds thousands
    // of segments on every pointermove. Measured as a DIFFERENCE between two
    // loop densities rather than against a number I chose, so the assertion
    // cannot drift with the rail constants.
    const ring = (n: number) =>
      Array.from({ length: n }, (_, i) => {
        const t = (i / n) * Math.PI * 2;
        return [15 + Math.cos(t), Math.sin(t), 0] as const;
      });
    const railsFor = (n: number) =>
      revolveSweepLines(SEAT, [ring(n)], 360).length / 6 - n;
    expect(railsFor(400)).toBe(railsFor(100));
    // and it shrinks with the SWEEP, which is the only thing it may depend on.
    const shortSweep = (n: number) =>
      revolveSweepLines(SEAT, [ring(n)], 45).length / 6 - n;
    expect(shortSweep(400)).toBeLessThan(railsFor(400));
  });

  it("draws nothing for a loop that is not a loop", () => {
    expect(revolveSweepLines(SEAT, [[[1, 2, 3]]], 90)).toHaveLength(0);
  });
});
