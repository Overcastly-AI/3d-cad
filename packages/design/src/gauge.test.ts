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
  acknowledgeAsk,
  angularTrack,
  arrowLength,
  AXIS_SHALLOW,
  axisValueAt,
  clampTo,
  crossArms,
  holdAsks,
  ladderStops,
  LADDER_MAX,
  LADDER_MIN_MAJOR_PX,
  LADDER_MIN_PITCH_PX,
  linearTrack,
  MAX_RUNGS,
  NO_STOPS,
  nudgeIntent,
  orthographicUnitsPerPixel,
  perspectiveUnitsPerPixel,
  placeGaugeTag,
  quantize,
  recordAsk,
  releaseAsks,
  rungHalfWidth,
  screenValue,
  seedAsks,
  steppedTrack,
  steppedValue,
  type AskQueue,
  type GaugeSeat,
  type GaugeStops,
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
  /** Every graduation drawn, whatever its weight. */
  const rungs = (stops: GaugeStops): number =>
    stops.major.length + stops.minor.length;

  it("never draws more MAJOR marks than the ceiling, at any scale", () => {
    for (const span of [0.4, 3, 10, 47, 128, 999, 4321]) {
      expect(ladderStops(span).major.length).toBeLessThanOrEqual(LADDER_MAX);
    }
  });

  it("stays bounded even when the camera invites an endless rule", () => {
    // The screen floor stops a ladder becoming crosshatch; this stops a very
    // close camera on a very long feature turning the shaft into a hairbrush.
    for (const span of [0.4, 3, 10, 47, 128, 999, 4321]) {
      expect(rungs(ladderStops(span, 1e6))).toBeLessThanOrEqual(MAX_RUNGS);
    }
  });

  it("keeps a readable ladder at every scale — five or more, five decades", () => {
    for (const span of [3, 30, 300, 3000, 30_000]) {
      expect(rungs(ladderStops(span))).toBeGreaterThanOrEqual(5);
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
    const { major, minor, pitch } = ladderStops(40);
    expect([...major, ...minor]).not.toContain(0);
    expect(Math.max(...major, ...minor)).toBeLessThan(40 - pitch * 0.5);
  });

  it("has nothing to draw for a zero or negative span", () => {
    expect(ladderStops(0)).toEqual(NO_STOPS);
    expect(ladderStops(-5)).toEqual(NO_STOPS);
  });

  // --- CRAFT-7: the rungs are the stops -------------------------------------

  it("puts every major on a round number and every minor between them", () => {
    // 40 mm takes a 5 mm pitch with no camera information, so the decade marks
    // are major and the halves between them are minor — which is how a rule is
    // engraved, and the answer to "which of these crosses matters".
    const { major, minor, pitch } = ladderStops(40);
    expect(pitch).toBeCloseTo(5, 9);
    expect(major).toEqual([10, 20, 30]);
    expect(minor).toEqual([5, 15, 25, 35]);
    // Lean in and the SAME 40 mm subdivides to 0.5 mm — and the marks you were
    // reading STAY MARKS, at the same weight. That is the property that matters
    // under the pointer: nothing you had your eye on moves or demotes, finer
    // ones simply appear between them.
    const close = ladderStops(40, 20);
    expect(close.pitch).toBeCloseTo(0.5, 9);
    for (const at of major) expect(close.major).toContain(at);
    for (const at of minor) expect(close.major).toContain(at);
    expect(close.minor).toContain(0.5);
  });

  it("every major is a decade multiple, five decades of span", () => {
    for (const span of [0.9, 9, 90, 900, 9000]) {
      for (const px of [Infinity, 40, 8, 2]) {
        const { major, minor, pitch } = ladderStops(span, px);
        if (major.length === 0) continue;
        // Every minor nests inside the major grid: the major step is a whole
        // multiple of the drawn pitch, so no two marks ever land a hair apart.
        const majorStep =
          major.length > 1
            ? (major[1] as number) - (major[0] as number)
            : (major[0] as number);
        const ratio = majorStep / pitch;
        expect(Math.abs(ratio - Math.round(ratio))).toBeLessThan(1e-6);
        expect(Math.round(ratio)).toBeLessThanOrEqual(10);
        for (const at of minor) {
          const n = at / majorStep;
          expect(Math.abs(n - Math.round(n))).toBeGreaterThan(1e-9);
        }
      }
    }
  });

  it("COARSENS until the pitch clears 7 px and its majors 14 — snap follows zoom", () => {
    // Same 40 mm value, three cameras. This is the whole of "snap at what
    // zoom": the ladder the user can see and the grid the drag obeys are one
    // thing, so a distant camera cannot offer a precision the screen cannot
    // show. A constant snap (what shipped before) would read 0.5 in all three.
    expect(ladderStops(40, 20).pitch).toBeCloseTo(0.5, 9); // 0.5 mm = 10 px
    expect(ladderStops(40, 4).pitch).toBeCloseTo(2, 9); // 1 mm would be 4 px
    // …and far enough away there is no legible ladder at all: the whole 40 mm
    // shaft is 16 px long, so the instrument is an arrow and says so.
    expect(ladderStops(40, 0.4)).toEqual(NO_STOPS);
  });

  it("keeps coarsening past one decade, however far away the camera is", () => {
    // The old fixed [1,2,5,10] walk could not reach here: the COUNT ceiling is
    // satisfied within one decade by construction, the SCREEN floor is not.
    // 4000 starts its search at a 100 decade; the screen floor pushes it past
    // 500 into the next one entirely.
    const { pitch, major } = ladderStops(4000, 0.02);
    expect(pitch).toBeCloseTo(500, 9);
    expect(pitch * 0.02).toBeGreaterThanOrEqual(LADDER_MIN_PITCH_PX);
    expect(major).toEqual([1000, 2000, 3000]);
  });

  it("walks the whole series as the camera closes in — 5, 2, 1, 0.5", () => {
    // §3.2 promises "5 -> 2 -> 1 -> 0.5" on one span, and on a 40 mm depth the
    // whole of it is now reachable: 2 needs 3.5 px/mm and 1 needs 7, which sit
    // either side of the DEFAULT camera's 3.658 px/mm. Under the 14 px floor
    // the same camera ruled 5 mm, so 12.5 was not a value a drag could reach at
    // all — that, and not aimability, is what the coarse floor actually cost.
    expect(ladderStops(40, 2).pitch).toBeCloseTo(5, 9); // 2 mm would be 4 px
    expect(ladderStops(40, 3.658).pitch).toBeCloseTo(2, 9); // the DEFAULT camera
    expect(ladderStops(40, 8).pitch).toBeCloseTo(1, 9);
    expect(ladderStops(40, 40).pitch).toBeCloseTo(0.5, 9);
    // …and no further, however close: 0.2 mm on 40 would be 200 rungs, so the
    // COUNT ceiling takes over from the screen floor at the fine end.
    expect(ladderStops(40, 400).pitch).toBeCloseTo(0.5, 9);
    // A 20 mm span subdivides through the same members on its own schedule.
    expect(ladderStops(20, 8).pitch).toBeCloseTo(1, 9);
    expect(ladderStops(20, 20).pitch).toBeCloseTo(0.5, 9);
  });

  it("holds BOTH floors across four decades of span and camera", () => {
    // The invariant, not a sample: a mark you COUNT past gets 7 px, a mark you
    // READ A NUMBER off gets 14. The two are one constant apart because the
    // tightest ratio in the 1/2/5 series is 2 — which is the whole argument for
    // the split, so it is worth a test that would notice if `majorFor` changed
    // and the coincidence stopped holding.
    for (const span of [3, 40, 250, 4000]) {
      for (const px of [0.3, 1, 3.658, 7, 20, 120]) {
        const stops = ladderStops(span, px);
        if (stops === NO_STOPS || stops.pitch <= 0) continue;
        expect(stops.pitch * px).toBeGreaterThanOrEqual(
          LADDER_MIN_PITCH_PX - 1e-9,
        );
        const majorStep =
          Math.pow(10, Math.floor(Math.log10(stops.pitch)) + 1) * px;
        expect(majorStep).toBeGreaterThanOrEqual(LADDER_MIN_MAJOR_PX - 1e-9);
      }
    }
  });

  it("draws an all-minor ladder at full weight rather than in faint stubs", () => {
    // A 5 mm span ruled at 1 mm reaches 4, and no decade mark is in range, so
    // the major/minor rule would render four faint stubs and nothing to
    // measure against. There is nothing to distinguish, so nothing is demoted.
    const { major, minor } = ladderStops(5, 8);
    expect(minor).toEqual([]);
    expect(major).toEqual([1, 2, 3, 4]);
  });

  it("refuses to draw a ladder of fewer than three marks", () => {
    // Two marks are not a scale. The arrow alone is the honest form here, and
    // the drag falls back to the track's own snap rather than to a stop the
    // user cannot see.
    expect(ladderStops(40, 0.06)).toEqual(NO_STOPS);
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

  // --- CRAFT-7 §2.2: the two clamps, across five decades of each input -------

  it("the head is never more than 45% of the shaft it terminates", () => {
    // MEASURED before the clamp: a 66 mm-radius profile extruded 5 mm drew a
    // 16.5 mm head on a 5 mm shaft — 330%, a cone on a stub. A CONSTANT would
    // assert itself here; the grid is what makes this a measurement, because
    // the defect lived at one corner of it (big seat, short shaft) and nowhere
    // else.
    const worst: { ratio: number; radius: number; shaft: number }[] = [];
    for (const radius of [0.5, 5, 50, 500, 5000]) {
      for (const shaft of [0.1, 1, 10, 100, 1000]) {
        const head = arrowLength(radius, shaft);
        worst.push({ ratio: head / shaft, radius, shaft });
      }
    }
    for (const w of worst) {
      expect(
        w.ratio,
        `radius ${w.radius}, shaft ${w.shaft} gave ${w.ratio}`,
      ).toBeLessThanOrEqual(0.45 + 1e-9);
    }
    // …and it is still SIZED FROM THE SEAT wherever the shaft leaves room, so
    // the clamp did not quietly replace the rule it bounds.
    expect(arrowLength(40, 1000)).toBeCloseTo(10, 9);
    expect(arrowLength(20, 1000)).toBeCloseTo(5, 9);
  });

  it("a graduation is never wider than 0.8 of its own pitch", () => {
    // The §1.5 table was a column of ratios up to 1.8 — crosses wider than the
    // gap between them, which reads as a woven band rather than as a scale.
    for (const radius of [0.5, 5, 50, 500, 5000]) {
      for (const pitch of [0.05, 0.5, 5, 50, 500]) {
        const width = 2 * rungHalfWidth(radius, pitch);
        expect(
          width / pitch,
          `radius ${radius}, pitch ${pitch} gave ${width / pitch}`,
        ).toBeLessThanOrEqual(0.8 + 1e-9);
      }
    }
    // …and the seat still drives it where the pitch leaves room.
    expect(rungHalfWidth(100, 1000)).toBeCloseTo(18, 9);
    expect(rungHalfWidth(0, 1000)).toBe(2);
  });

  it("the drawn instrument obeys both clamps at once, five decades of depth", () => {
    // Through the SHIPPED seam rather than the helpers: a clamp that is correct
    // in `arrowLength` and unwired in `draw` is the gap this asserts across.
    for (const depth of [0.5, 5, 50, 500, 5000]) {
      const track = mm();
      const stops = track.stops(depth, 0.05);
      const drawn = track.draw(depth, stops);
      expect(
        drawn.head.length / depth,
        `depth ${depth}: head ${drawn.head.length}`,
      ).toBeLessThanOrEqual(0.45 + 1e-9);
      if (stops.pitch > 0) {
        // EACH CLASS AGAINST ITS OWN GAP. A major sits `majorStep` from its
        // neighbour and a minor sits `pitch`; bounding both by the pitch made
        // the majors shrink with every subdivision until the shaft swallowed
        // them, which is the defect this pairing exists to keep out.
        const span = (r: readonly [Vec3, Vec3]): number =>
          Math.hypot(r[0][0] - r[1][0], r[0][1] - r[1][1], r[0][2] - r[1][2]);
        const major = span(drawn.rungs[0] as readonly [Vec3, Vec3]);
        expect(
          major / stops.majorStep,
          `depth ${depth}: major ${major} step ${stops.majorStep}`,
        ).toBeLessThanOrEqual(0.8 + 1e-9);
        const first = drawn.minorRungs[0];
        if (first !== undefined) {
          const minor = span(first);
          expect(
            minor / stops.pitch,
            `depth ${depth}: minor ${minor} pitch ${stops.pitch}`,
          ).toBeLessThanOrEqual(0.8 + 1e-9);
        }
        // …and a major is never NARROWER than the old pitch-bounded rule made
        // it, strictly wider wherever the two spacings differ. Stated as a
        // relation rather than as a number because the quantity that matters
        // is the CHANGE — a literal floor here would be a constant nobody
        // measured, which is the habit this whole item is correcting.
        expect(major).toBeGreaterThanOrEqual(
          2 * rungHalfWidth(SEAT.radius, stops.pitch) - 1e-9,
        );
      }
    }
  });

  it("a major CLEARS THE ROD it crosses — the founder-shot regression", () => {
    // THE DEFECT, with the numbers that found it. Both classes used to be
    // bounded by the PITCH, which was harmless while the screen floor kept
    // every ladder at 5 mm and fatal the moment CRAFT-7's review halved it: on
    // the shipped extrude seat at the default camera the ladder subdivides to
    // 2 mm, the arm follows it down to 0.8 mm, and the shaft it is drawn
    // across is 0.97 mm — so the cross is INSIDE the rod. Measured on the
    // founder capture: 5 legible crosses before, 0 after. The signature
    // element, present in the vertex buffer and absent from the picture.
    const seat = 28.8; // the e2e fixture's profile radius
    const depth = 40;
    const track = linearTrack(
      { ...SEAT, radius: seat },
      {
        min: 0.1,
        max: 10_000,
        snap: 0.5,
        keyStep: 0.5,
        format: (v) => `${String(v)} mm`,
      },
    );
    const stops = track.stops(depth, 1 / 3.658); // the DEFAULT camera, measured
    expect(stops.pitch).toBeCloseTo(2, 9);
    expect(stops.majorStep).toBeCloseTo(10, 9);
    const drawn = track.draw(depth, stops);
    const rod = 2 * drawn.spineRadius;
    expect(rod).toBeCloseTo(0.968, 3);
    const [a, b] = drawn.rungs[0] as readonly [Vec3, Vec3];
    const major = Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
    expect(major / rod).toBeGreaterThan(4);
    // NEGATIVE CONTROL: the rule this replaces, on the same inputs. A gate that
    // cannot show the wrong answer cannot certify the right one.
    expect((2 * rungHalfWidth(seat, stops.pitch)) / rod).toBeLessThan(2);

    // AND THE MINOR, which is the half that matters for §3.1: the minors ARE
    // the snap. Drawn 0.6 of a pitch-bounded arm they measured 0.96 mm on a
    // 0.968 mm rod — the drawn scale said 10 mm while the drag stopped every 2.
    const [c, d] = drawn.minorRungs[0] as readonly [Vec3, Vec3];
    const minor = Math.hypot(c[0] - d[0], c[1] - d[1], c[2] - d[2]);
    expect(minor / rod).toBeGreaterThan(1.5);
    expect(0.6 * minor).toBeLessThan(rod); // the control, again on real inputs
    // …and still the quieter mark: a fifth of the major's reach.
    expect(minor).toBeLessThan(major / 3);
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

/**
 * THE ASK QUEUE — the rules, asserted by name, every run.
 *
 * The browser case these stand beside (`extrude-drag-handle.spec.ts`, "every
 * press counts, however fast they come") is a real positive control and a WEAK
 * one: re-run twelve times against a mutant that clears the queue on every prop
 * change, it caught the mutant **2 of 12**, because the lost update it detects
 * needs two inputs to collide inside one round trip and usually they do not.
 * Green was the mutant's MODAL outcome, so "it went red once" did not mean the
 * guard was load-bearing.
 *
 * Here the collision is CONSTRUCTED rather than raced for, so every rule fails
 * deterministically when broken. Each case below is one rule; between them they
 * kill the mutations the browser case was supposed to.
 */
describe("the ask queue", () => {
  /** The extrude track's own tolerance — a display-string round trip is lossy. */
  const near = (a: number, b: number) => Math.abs(a - b) <= 1e-4;

  /** Convenience: ask for each value in turn, off the pointer. */
  const askAll = (queue: AskQueue, ...values: number[]): AskQueue =>
    values.reduce((q, v) => recordAsk(q, v, false), queue);

  it("seeds on the owner's value with nothing outstanding", () => {
    expect(seedAsks(10)).toEqual({ asks: [], base: 10, live: null });
  });

  it("rule 1: remembers an ask BEFORE it is sent, so the next step reasons from it", () => {
    // The whole point: two presses land before either acknowledgement, and the
    // second must step off the FIRST ASK, not off the stale prop.
    const first = recordAsk(seedAsks(10), 10.5, false);
    expect(first.base).toBe(10.5);
    const second = recordAsk(first, first.base + 0.5, false);
    expect(second.base).toBe(11);
    expect(second.asks).toEqual([10.5, 11]);
    expect(second.live).toBe(11);
  });

  it("rule 2: an ack retires that ask AND EVERY OLDER ONE, and leaves base alone", () => {
    // Three presses outstanding; the owner echoes the SECOND. The first is
    // stale by definition, and the third has not been answered yet.
    const queue = askAll(seedAsks(10), 10.5, 11, 11.5);
    const acked = acknowledgeAsk(queue, 11, near);
    expect(acked.asks).toEqual([11.5]);
    expect(acked.base).toBe(11.5);
    expect(acked.live).toBe(11.5);
  });

  it("rule 2: the ack for press ONE does not throw away press TWO", () => {
    // The exact regression the queue was built for — the one-pending-value
    // version dropped the second press here and produced 15.5 for 16.
    const queue = askAll(seedAsks(10), 10.5, 11);
    const acked = acknowledgeAsk(queue, 10.5, near);
    expect(acked.asks).toEqual([11]);
    expect(acked.live).toBe(11);
    expect(acked.base).toBe(11);
  });

  it("rule 2: recognition is by TOLERANCE, not equality — an inch round trip is lossy", () => {
    // A value that came back through a display string. Exact equality would
    // read this as a stranger's edit, on inch documents only.
    const queue = recordAsk(seedAsks(10), 12.699999, false);
    const acked = acknowledgeAsk(queue, 12.69995, near);
    expect(acked.asks).toEqual([]);
    expect(acked.base).toBe(12.699999); // OUR ask survived, not the echo
  });

  it("rule 3: a value we never asked for is a stranger's edit and wins outright", () => {
    // Somebody typed 40 into the rail field while two presses were in flight.
    const queue = askAll(seedAsks(10), 10.5, 11);
    const stranger = acknowledgeAsk(queue, 40, near);
    expect(stranger.asks).toEqual([]);
    expect(stranger.base).toBe(40);
    expect(stranger.live).toBeNull();
  });

  it("rule 3 does NOT fire for a value that is merely out of order", () => {
    // The oldest ask arriving last still matches something outstanding, so the
    // queue is trimmed rather than abandoned. Telling this from a real stranger
    // is the entire job of the search.
    const queue = askAll(seedAsks(10), 10.5, 11);
    expect(acknowledgeAsk(queue, 10.5, near).base).toBe(11);
  });

  it("rule 1 mid-drag: the arrow follows the pointer but the queue does not grow", () => {
    // Ten `pointermove` frames. `base`/`live` track the cursor; nothing queues,
    // because rule 5 is about to empty it anyway and the render loop stays
    // allocation-free.
    let queue = holdAsks(seedAsks(10));
    for (let frame = 1; frame <= 10; frame += 1) {
      queue = recordAsk(queue, 10 + frame, true);
    }
    expect(queue.asks).toEqual([]);
    expect(queue.base).toBe(20);
    expect(queue.live).toBe(20);
  });

  it("rule 4: taking the grip shows BASE, not the prop", () => {
    // A grab straight after a key press. Showing the prop here is the "arrow
    // jumps back a step the instant the pointer moves" defect.
    const pressed = recordAsk(seedAsks(10), 10.5, false);
    expect(holdAsks(pressed).live).toBe(10.5);
    expect(holdAsks(pressed).asks).toEqual([10.5]); // and the ask still stands
  });

  it("rule 5: letting go empties the queue and defers to the prop", () => {
    const queue = askAll(seedAsks(10), 10.5, 11);
    const released = releaseAsks(queue);
    expect(released.asks).toEqual([]);
    expect(released.live).toBeNull();
  });

  it("rule 5: ...but KEEPS base on what the drag ended at", () => {
    // A free (Ctrl) drag ends on 12.4713 and the prop has not caught up. The
    // first arrow press afterwards must be able to put it back on a grid, which
    // it can only do from the value you actually dragged to.
    const dragged = recordAsk(holdAsks(seedAsks(10)), 12.4713, true);
    expect(releaseAsks(dragged).base).toBe(12.4713);
  });

  it("the transitions are pure — no input queue is mutated", () => {
    // The shell holds this in a ref and reads it between renders; an in-place
    // mutation would be invisible to React and visible to nothing else.
    const queue = askAll(seedAsks(10), 10.5, 11);
    const before = JSON.stringify(queue);
    acknowledgeAsk(queue, 10.5, near);
    recordAsk(queue, 12, false);
    holdAsks(queue);
    releaseAsks(queue);
    expect(JSON.stringify(queue)).toBe(before);
  });

  it("a whole fast sequence: Up, Up, Shift+Up with the acks trailing", () => {
    // The measured failure, replayed end to end. Presses at 10.5, 11 and 16
    // land before any acknowledgement; then the owner echoes them in order. The
    // answer must be 16 — the one-pending version gave 15.5.
    let queue = seedAsks(10);
    queue = recordAsk(queue, queue.base + 0.5, false);
    queue = recordAsk(queue, queue.base + 0.5, false);
    queue = recordAsk(queue, queue.base + 5, false);
    expect(queue.asks).toEqual([10.5, 11, 16]);

    queue = acknowledgeAsk(queue, 10.5, near);
    expect(queue.live).toBe(16);
    queue = acknowledgeAsk(queue, 11, near);
    expect(queue.live).toBe(16);
    queue = acknowledgeAsk(queue, 16, near);

    expect(queue.asks).toEqual([]);
    expect(queue.live).toBeNull(); // nothing outstanding: the prop speaks now
    expect(queue.base).toBe(16);
  });
});
