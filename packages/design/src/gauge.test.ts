/**
 * The gauge's arithmetic, tested without a browser or a GPU — which is the
 * whole reason it lives in `packages/design` rather than in the r3f shell.
 *
 * TWO DIFFERENT KINDS OF EVIDENCE ARE IN HERE AND THEY ARE NOT INTERCHANGEABLE.
 * The LINEAR track's behaviour is also pinned by `extrudeHandle.test.ts`, which
 * was written against the pre-extraction code and was not touched by it: that
 * file passing is the proof the move was faithful, and these cases are the
 * proof the moved code is reachable through the new seam. The STEPPED and
 * ANGULAR tracks have no such witness — no shipped call site, no browser
 * run — so their cases here are the only thing standing behind them, and they
 * are written to say so.
 */
import { describe, expect, it } from "vitest";

import {
  angularTrack,
  arrowLength,
  AXIS_SHALLOW,
  axisValueAt,
  clampTo,
  crossArms,
  ladderStops,
  LADDER_MAX,
  linearTrack,
  NO_STOPS,
  nudgeIntent,
  orthographicUnitsPerPixel,
  perspectiveUnitsPerPixel,
  placeGaugeTag,
  quantize,
  rungHalfWidth,
  screenValue,
  steppedTrack,
  steppedValue,
  type GaugeSeat,
  type Vec3,
} from "./gauge";

const SEAT: GaugeSeat = {
  base: [0, 0, 0],
  dir: [0, 0, 1],
  radius: 40,
  arms: [
    [1, 0, 0],
    [0, 1, 0],
  ],
};

function mm(): ReturnType<typeof linearTrack> {
  return linearTrack(SEAT, {
    min: 0.1,
    max: 10_000,
    snap: 0.5,
    keyStep: 0.5,
    format: (v, opts) =>
      opts?.unitSuffix === false ? String(v) : `${String(v)} mm`,
  });
}

describe("axisValueAt — a pointer ray, in track units", () => {
  it("reads the height the ray crosses the track at", () => {
    // A ray fired horizontally from off to the side, aimed at z = 12.
    const at = axisValueAt([0, 0, 0], [0, 0, 1], [100, 0, 12], [-1, 0, 0]);
    expect(at).toBeCloseTo(12, 9);
  });

  it("resolves a SKEW ray — the closest approach, not an intersection", () => {
    // Offset in y so the ray never actually meets the axis.
    const at = axisValueAt([0, 0, 0], [0, 0, 1], [100, 7, 12], [-1, 0, 0]);
    expect(at).toBeCloseTo(12, 9);
  });

  it("refuses when the camera looks straight down the track", () => {
    expect(
      axisValueAt([0, 0, 0], [0, 0, 1], [0, 0, -50], [0, 0, 1]),
    ).toBeNull();
  });

  it("refuses a merely SHALLOW track, not only an exactly parallel one", () => {
    // 5 degrees off the axis: sin^2 = 0.0076, below the 0.05 threshold.
    const t = (5 * Math.PI) / 180;
    const dir: Vec3 = [Math.sin(t), 0, Math.cos(t)];
    expect(1 - Math.cos(t) ** 2).toBeLessThan(AXIS_SHALLOW);
    expect(axisValueAt([0, 0, 0], [0, 0, 1], [0, 0, -50], dir)).toBeNull();
  });

  it("does not require a normalised ray direction", () => {
    const unit = axisValueAt([0, 0, 0], [0, 0, 1], [100, 0, 12], [-1, 0, 0]);
    const long = axisValueAt([0, 0, 0], [0, 0, 1], [100, 0, 12], [-9, 0, 0]);
    expect(long).toBeCloseTo(unit as number, 9);
  });
});

describe("the screen fallback and its two camera models", () => {
  it("grows with upward travel and shrinks with downward", () => {
    expect(screenValue(10, 40, 0.25)).toBeCloseTo(20, 9);
    expect(screenValue(10, -40, 0.25)).toBeCloseTo(0, 9);
  });

  it("refuses to divide by a zero-height viewport", () => {
    expect(perspectiveUnitsPerPixel(40, 500, 0)).toBe(0);
  });

  it("reads a PARALLEL projection from its zoom, not from a distance", () => {
    expect(orthographicUnitsPerPixel(4)).toBeCloseTo(0.25, 12);
    expect(orthographicUnitsPerPixel(0)).toBe(0);
    // The distinguishing property: distance cannot enter the answer. The
    // perspective formula disagrees with itself at two distances; the parallel
    // one has nowhere to put a distance at all.
    expect(perspectiveUnitsPerPixel(40, 500, 800)).not.toBeCloseTo(
      perspectiveUnitsPerPixel(40, 1000, 800),
      6,
    );
  });
});

describe("quantize — snapped by default, exact on demand", () => {
  it("snaps to the step", () => {
    expect(quantize(12.4713, 0.5, false, 0.1, 100)).toBeCloseTo(12.5, 9);
  });

  it("hands the exact value back when the snap is suppressed", () => {
    expect(quantize(12.4713, 0.5, true, 0.1, 100)).toBeCloseTo(12.4713, 9);
  });

  it("does not write float noise into a field a human is about to read", () => {
    // THE VALUE HAS TO BE NOISY, AND MOST OBVIOUS CANDIDATES ARE NOT. A literal
    // `12.40000000000000002` parses to exactly 12.4, and so do 0.1 + 12.3,
    // 0.1 * 124, 12.5 - 0.1 and 1.24 * 10 — so a test written with any of them
    // asserts that 12.4 formats as "12.4" and could never fail. The guard is the
    // first line: the input must not already be clean.
    const noisy = 12.4 + 1e-15;
    expect(String(noisy)).toBe("12.400000000000002");
    expect(String(quantize(noisy, 0.5, true, 0.1, 100))).toBe("12.4");
  });

  it("keeps an IMPERIAL snap exactly on its own grid — no 4-decimal round", () => {
    // 1/32 in is 0.79375 mm. Rounding a snapped value would push every one of
    // these off the grid, on inch documents only.
    const snap = 25.4 / 32;
    const got = quantize(10, snap, false, 0.1, 100);
    expect(got / snap).toBeCloseTo(Math.round(got / snap), 12);
  });

  it("never leaves the submittable range", () => {
    expect(quantize(-99, 0.5, false, 0.1, 100)).toBe(0.1);
    expect(quantize(1e9, 0.5, false, 0.1, 100)).toBe(100);
  });
});

describe("steppedValue — the grid you land on is the grid of the key", () => {
  it("takes the NEXT multiple, not nearest-then-along", () => {
    // From 12.4713 a fine press means 12.5, the value you are standing beside —
    // nearest-then-along would give 13 and skip it.
    expect(steppedValue(12.4713, 0.5, 1, 0.1, 100)).toBeCloseTo(12.5, 9);
    // And Shift+Down from 11 means 10, not 5.
    expect(steppedValue(11, 5, -1, 0.1, 100)).toBeCloseTo(10, 9);
  });

  it("always moves, even from a value already on the grid", () => {
    expect(steppedValue(10, 0.5, 1, 0.1, 100)).toBeCloseTo(10.5, 9);
    expect(steppedValue(10, 0.5, -1, 0.1, 100)).toBeCloseTo(9.5, 9);
  });

  it("lets two separately-dragged values meet on the same number", () => {
    // The point of the rule: a boss at 12.4713 and a pocket at 12.63 must be
    // able to be given the SAME depth from the keyboard.
    expect(steppedValue(12.4713, 0.5, 1, 0.1, 100)).toBe(
      steppedValue(12.3, 0.5, 1, 0.1, 100),
    );
  });

  it("degrades to an addition for a nonsensical step rather than dividing by it", () => {
    // A zero step means no grid, so the press is a plain add: 10 + 1*0 = 10,
    // clamped. Behaviour carried over from `steppedDepth` unchanged.
    expect(steppedValue(10, 0, 1, 0.1, 100)).toBe(10);
    // A NaN step PROPAGATES rather than being swallowed, and that is the right
    // direction: a non-finite step is a defect in the TRACK, never a user
    // input, and a NaN arriving in the field is loud where a silently clamped
    // number would look like a value somebody chose.
    expect(Number.isNaN(steppedValue(10, Number.NaN, 1, 0.1, 100))).toBe(true);
  });
});

describe("nudgeIntent — which keys are the gauge's, and how coarse", () => {
  it("grows on Up/Right and shrinks on Down/Left", () => {
    expect(nudgeIntent("ArrowUp", false)).toEqual({ sign: 1, grids: 0 });
    expect(nudgeIntent("ArrowRight", false)).toEqual({ sign: 1, grids: 0 });
    expect(nudgeIntent("ArrowDown", false)).toEqual({ sign: -1, grids: 0 });
    expect(nudgeIntent("ArrowLeft", false)).toEqual({ sign: -1, grids: 0 });
  });

  it("puts Shift+arrow and Page on the SAME coarse grid", () => {
    expect(nudgeIntent("ArrowUp", true)).toEqual({ sign: 1, grids: 1 });
    expect(nudgeIntent("PageUp", false)).toEqual({ sign: 1, grids: 1 });
    expect(nudgeIntent("PageUp", true)).toEqual({ sign: 1, grids: 2 });
  });

  it("returns null for a key that is not ours, so Enter and Escape survive", () => {
    for (const key of ["Enter", "Escape", "Tab", "a", " "]) {
      expect(nudgeIntent(key, false)).toBeNull();
    }
  });
});

describe("ladderStops — the signature graduation", () => {
  it("never draws more than the ceiling, at any scale", () => {
    for (const span of [0.4, 3, 10, 47, 128, 999, 4321]) {
      expect(ladderStops(span).major.length).toBeLessThanOrEqual(LADDER_MAX);
    }
  });

  it("keeps a readable ladder at every scale — five or more, five decades", () => {
    for (const span of [3, 30, 300, 3000, 30_000]) {
      expect(ladderStops(span).major.length).toBeGreaterThanOrEqual(5);
    }
  });

  it("steps by a number a person would say out loud", () => {
    for (const span of [3, 10, 47, 128, 999]) {
      const { pitch } = ladderStops(span);
      const mantissa = pitch / Math.pow(10, Math.floor(Math.log10(pitch)));
      expect([1, 2, 5, 10]).toContainEqual(Math.round(mantissa));
    }
  });

  it("draws neither the seat nor a rung under the grip", () => {
    const { major, pitch } = ladderStops(40);
    expect(major).not.toContain(0);
    expect(Math.max(...major)).toBeLessThan(40 - pitch * 0.5);
  });

  it("has nothing to draw for a zero or negative span", () => {
    expect(ladderStops(0)).toEqual(NO_STOPS);
    expect(ladderStops(-5)).toEqual(NO_STOPS);
  });
});

describe("proportion — sized from the seat, never from the value", () => {
  it("scales the arrow with the seat so it suits the part", () => {
    expect(arrowLength(40)).toBeCloseTo(10, 9);
    expect(arrowLength(20)).toBeCloseTo(5, 9);
  });

  it("stays grabbable on a tiny seat and sane on a huge one", () => {
    expect(arrowLength(0)).toBe(2);
    expect(arrowLength(100_000)).toBe(18);
  });

  it("gives a hairline profile a rung you can still see", () => {
    expect(rungHalfWidth(0)).toBe(2);
    expect(rungHalfWidth(100)).toBeCloseTo(18, 9);
  });

  it("derives two arms perpendicular to the track, at any orientation", () => {
    for (const dir of [
      [0, 0, 1],
      [1, 0, 0],
      [0, 1, 0],
      [0.577, 0.577, 0.577],
    ] as Vec3[]) {
      const [u, v] = crossArms(dir);
      const dot = (a: Vec3, b: Vec3): number =>
        a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
      expect(dot(u, dir)).toBeCloseTo(0, 6);
      expect(dot(v, dir)).toBeCloseTo(0, 6);
      expect(dot(u, v)).toBeCloseTo(0, 6);
      expect(dot(u, u)).toBeCloseTo(1, 6);
    }
  });
});

describe("clampTo", () => {
  it("holds the range from both ends", () => {
    expect(clampTo(-1, 0.1, 10)).toBe(0.1);
    expect(clampTo(99, 0.1, 10)).toBe(10);
    expect(clampTo(5, 0.1, 10)).toBe(5);
  });
});

describe("linearTrack — the extrude gauge's own arithmetic, through the seam", () => {
  it("puts the grip `value` units along the track, not `value` units away", () => {
    expect(mm().pointAt(12)).toEqual([0, 0, 12]);
  });

  it("draws a spine to the value and an arrowhead beyond it", () => {
    const d = mm().draw(40, NO_STOPS);
    expect(d.spine[0]).toEqual([0, 0, 0]);
    expect(d.spine[d.spine.length - 1]).toEqual([0, 0, 40]);
    expect(d.head.base).toEqual([0, 0, 40]);
    // The head sits BEYOND the end face, so the shaft measures the value.
    expect((d.head.tip as Vec3)[2]).toBeCloseTo(40 + arrowLength(40), 9);
    expect(d.head.length).toBeCloseTo(arrowLength(40), 9);
    // A stem, not a rod: the spine is a fraction of the head's own radius.
    expect(d.spineRadius).toBeLessThan(d.head.radius);
  });

  it("draws each graduation as a CROSS — two strokes, on the seat's own arms", () => {
    const stops = ladderStops(40);
    const d = mm().draw(40, stops);
    expect(d.rungs).toHaveLength(stops.major.length * 2);
    // Both arms are centred on the track, so the cross projects to something
    // centred from ANY camera — which is the whole reason it is not one rung.
    const [a, b] = d.rungs[0] as readonly [Vec3, Vec3];
    expect((a[0] + b[0]) / 2).toBeCloseTo(0, 9);
    expect((a[1] + b[1]) / 2).toBeCloseTo(0, 9);
  });

  it("steps on the key's own grid, fine and coarse", () => {
    const t = mm();
    expect(t.nudge(10, "ArrowUp", false)).toBeCloseTo(10.5, 9);
    expect(t.nudge(11, "ArrowUp", true)).toBeCloseTo(15, 9);
    expect(t.nudge(10, "PageUp", false)).toBeCloseTo(15, 9);
    expect(t.nudge(10, "Enter", false)).toBeNull();
  });

  it("recognises its own value coming back as a display string", () => {
    const t = mm();
    // An inch document's round trip is not exact; an equality test would read
    // every acknowledgement as a stranger's edit.
    expect(t.same(12.5, 12.50000001)).toBe(true);
    expect(t.same(12.5, 12.51)).toBe(false);
  });

  it("speaks the value with a suffix and writes it bare on the tag", () => {
    const t = mm();
    expect(t.format(12.5)).toBe("12.5 mm");
    expect(t.format(12.5, { unitSuffix: false })).toBe("12.5");
  });

  it("scales value units to world units when they differ", () => {
    // A count-like track: value 3 sits 30 world units along.
    const t = linearTrack(SEAT, {
      min: 1,
      max: 9,
      snap: 1,
      keyStep: 1,
      unitsPerValue: 10,
      format: String,
    });
    expect(t.pointAt(3)).toEqual([0, 0, 30]);
    // …and a pointer ray aimed at world z = 30 reads back as 3, not as 30.
    expect(t.valueAt([100, 0, 30], [-1, 0, 0])).toBeCloseTo(3, 9);
  });
});

describe("steppedTrack — linear with an integer quantiser, and that is all", () => {
  const count = steppedTrack(SEAT, { min: 1, max: 8, pitch: 10 });

  it("lands only on whole counts, with or without the free modifier", () => {
    expect(count.quantize(3.4, false)).toBe(3);
    // There is nothing between two counts to escape to, so Ctrl cannot free it.
    expect(count.quantize(3.4, true)).toBe(3);
    expect(count.quantize(99, false)).toBe(8);
  });

  it("uses the SAME projection as the linear track, at the pitch's scale", () => {
    // The load-bearing claim: a pattern-count gauge needs no new maths, only a
    // new quantiser. Value 4 is 40 world units along at a 10-unit pitch.
    expect(count.pointAt(4)).toEqual([0, 0, 40]);
    expect(count.valueAt([100, 0, 40], [-1, 0, 0])).toBeCloseTo(4, 9);
    // …and it refuses from the same pose the linear one does.
    expect(count.valueAt([0, 0, -50], [0, 0, 1])).toBeNull();
  });

  it("rules every instance position — the rungs ARE the copies", () => {
    expect([...count.stops(5, 1).major]).toEqual([1, 2, 3, 4, 5]);
    expect(count.stops(5, 1).pitch).toBe(1);
  });

  it("steps by one", () => {
    expect(count.nudge(3, "ArrowUp", false)).toBe(4);
    expect(count.nudge(3, "ArrowDown", false)).toBe(2);
  });

  it("writes a plain integer", () => {
    expect(count.format(4)).toBe("4");
  });
});

describe("angularTrack — NO SHIPPED CALL SITE; these cases are its only witness", () => {
  const sweep = angularTrack(
    {
      base: [0, 0, 0],
      // The axis of ROTATION is +Z; arms[0] is the zero-degree reference.
      dir: [0, 0, 1],
      radius: 40,
      arms: [
        [1, 0, 0],
        [0, 1, 0],
      ],
    },
    {
      min: 0,
      max: 360,
      radius: 20,
      snap: 5,
      keyStep: 5,
      format: (v, opts) =>
        opts?.unitSuffix === false ? String(v) : `${String(v)}°`,
    },
  );

  it("puts the grip on the arc at the angle asked for", () => {
    const at0 = sweep.pointAt(0);
    expect(at0[0]).toBeCloseTo(20, 9);
    expect(at0[1]).toBeCloseTo(0, 9);
    const at90 = sweep.pointAt(90);
    expect(at90[0]).toBeCloseTo(0, 9);
    expect(at90[1]).toBeCloseTo(20, 9);
  });

  it("reads a pointer ray as an angle about the axis", () => {
    // Straight down the +Z axis at the 90-degree point on the arc.
    const got = sweep.valueAt([0, 20, 50], [0, 0, -1]);
    expect(got).toBeCloseTo(90, 6);
    // …and it comes back in [0, 360), never negative.
    const behind = sweep.valueAt([0, -20, 50], [0, 0, -1]);
    expect(behind).toBeCloseTo(270, 6);
  });

  it("refuses when the sweep plane is edge-on, as the linear track does", () => {
    expect(sweep.valueAt([0, 0, 0], [1, 0, 0])).toBeNull();
  });

  it("is NOT the linear ladder rotated — 15 and 5, coarsening upward", () => {
    // Zoomed in: 15 degrees of a 20-unit arc is 5.2 units, which at 0.05 units
    // per pixel is 105 px — comfortably legible, so the finest majors stand.
    const near = sweep.stops(180, 0.05);
    expect(near.major.slice(0, 3)).toEqual([15, 30, 45]);
    expect(near.pitch).toBe(5);
    // Zoomed out far enough that even 90 degrees is under the floor, the
    // coarsening runs out at 90 rather than inventing a finer set.
    const far = sweep.stops(180, 50);
    expect(far.major.every((d) => d % 90 === 0)).toBe(true);
  });

  it("marks a minor graduation only where there is no major on it", () => {
    const { major, minor } = sweep.stops(180, 0.05);
    for (const d of minor) expect(major).not.toContain(d);
  });

  it("draws the spine as a polyline and points the head along the tangent", () => {
    const d = sweep.draw(90, NO_STOPS);
    expect(d.spine.length).toBeGreaterThan(2);
    // Every point of the arc is `radius` from the axis.
    for (const p of d.spine) expect(Math.hypot(p[0], p[1])).toBeCloseTo(20, 6);
    // At 90 degrees the tangent runs along -X, so the head points that way.
    const dx = (d.head.tip as Vec3)[0] - d.head.base[0];
    expect(dx).toBeLessThan(0);
  });

  it("speaks degrees, and steps in them", () => {
    expect(sweep.format(45)).toBe("45°");
    expect(sweep.format(45, { unitSuffix: false })).toBe("45");
    expect(sweep.nudge(43, "ArrowUp", false)).toBeCloseTo(45, 9);
    expect(sweep.nudge(43, "ArrowUp", true)).toBeCloseTo(45, 9);
  });
});

describe("placeGaugeTag — the tag hangs off the grip, and flips at the frame", () => {
  const size = { width: 90, height: 26 };

  it("defaults up and to the right of the grip, which is the reading direction", () => {
    const p = placeGaugeTag("up-right", size);
    expect(p.side).toBe("up-right");
    expect(p.tag.left).toBeGreaterThan(0);
    expect(p.tag.top).toBeLessThan(-size.height);
  });

  it("runs the leader from the grip to the tag corner NEAREST it", () => {
    const p = placeGaugeTag("up-right", size);
    expect(p.leader.x1).toBe(0);
    expect(p.leader.y1).toBe(0);
    // Up-right: the near corner is the strip's bottom-left.
    expect(p.leader.x2).toBe(p.tag.left);
    expect(p.leader.y2).toBe(p.tag.top + size.height);
  });

  it("flips rather than clamping when the default side would overflow", () => {
    // A grip near the top-right corner: both axes must turn over.
    const p = placeGaugeTag("up-right", size, {
      anchor: { x: 1250, y: 10 },
      frame: { width: 1280, height: 800 },
    });
    expect(p.side).toBe("down-left");
    expect(p.tag.left).toBeLessThan(0);
    expect(p.tag.top).toBeGreaterThan(0);
  });

  it("drags the leader with the flip instead of leaving it pointing at nothing", () => {
    const p = placeGaugeTag("up-right", size, {
      anchor: { x: 1250, y: 10 },
      frame: { width: 1280, height: 800 },
    });
    // Down-left: the near corner is the strip's top-right.
    expect(p.leader.x2).toBe(p.tag.left + size.width);
    expect(p.leader.y2).toBe(p.tag.top);
  });

  it("honours the preference when it has no frame to judge against", () => {
    // A gauge that cannot know where it is on screen still gets a well-formed
    // leader rather than no tag at all.
    expect(placeGaugeTag("down-left", size).side).toBe("down-left");
  });
});
