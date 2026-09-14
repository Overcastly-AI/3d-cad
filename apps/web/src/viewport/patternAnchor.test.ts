/**
 * WHERE THE TWO PATTERN GAUGES STAND (CRAFT-11).
 *
 * The decisive case in this file is `the drawn rungs stand on the ghost
 * copies`. It is written THROUGH the real `steppedTrack` rather than against a
 * re-derivation of the seat arithmetic, because the claim it is checking is a
 * claim about the SHIPPED primitive: that `countSeat`'s one-pitch offset makes
 * the ladder the primitive draws coincide with the instance list the ghosts
 * stand on. A test that recomputed `pointAt` itself would agree with a seat
 * that has drifted from the track, which is the whole failure it exists to
 * catch — the preview and the ladder silently becoming two drawings.
 *
 * The second decisive case is the RAIL SEPARATION. Two gauges on one feature
 * means two DOM hit sleeves in the same neighbourhood, and a sleeve resolving
 * to its sibling is this repo's recurring "present, correct, and unreachable"
 * defect. The e2e spec measures the DOM consequence; this measures the world-
 * space cause, so a regression is named here first and cheaply.
 */
import { steppedTrack, type Vec3 } from "@loft/design";
import { describe, expect, it } from "vitest";

import {
  countRailOffset,
  countSeat,
  MAX_PATTERN_COUNT,
  MIN_PATTERN_COUNT,
  patternAnchor,
  patternPerp,
  RAIL_PITCH_FRAC,
  sceneDirection,
  spacingRailOffset,
  spacingSeat,
  type SceneBounds,
} from "./patternAnchor";
import { patternInstanceOffsets } from "./patternGhost";

/** A 20 x 12 x 8 mm block centred on the origin, in scene mm. */
const BLOCK: SceneBounds = {
  min: [-10, -6, -4],
  max: [10, 6, 4],
};

const X: Vec3 = [1, 0, 0];

const close = (a: Vec3, b: Vec3, tol = 1e-9): void => {
  expect(a[0]).toBeCloseTo(b[0], 9);
  expect(a[1]).toBeCloseTo(b[1], 9);
  expect(a[2]).toBeCloseTo(b[2], 9);
  expect(tol).toBeGreaterThan(0);
};

describe("patternPerp — which way the dimension rails hang", () => {
  it("hangs DOWN for a row that is not itself vertical", () => {
    expect(patternPerp([1, 0, 0])).toEqual([0, -1, 0]);
    expect(patternPerp([0, 0, 1])).toEqual([0, 0 - 1, 0]);
    expect(patternPerp([-1, 0, 0])).toEqual([0, -1, 0]);
  });

  it("goes out sideways for a vertical row, which has no 'below'", () => {
    expect(patternPerp([0, 1, 0])).toEqual([1, 0, 0]);
    expect(patternPerp([0, -1, 0])).toEqual([1, 0, 0]);
  });

  it("is the same side whichever way the row points along its axis", () => {
    // A dimension that swaps sides as the direction flips is a dimension the
    // user cannot point at twice in a row.
    expect(patternPerp([1, 0, 0])).toEqual(patternPerp([-1, 0, 0]));
  });
});

describe("sceneDirection — the one OCCT(Z-up) → scene(Y-up) rotation", () => {
  it("applies (x, y, z) → (x, z, −y) and returns a unit vector", () => {
    expect(sceneDirection({ x: 0, y: 1, z: 0 })).toEqual([0, 0, -1]);
    expect(sceneDirection({ x: 0, y: 0, z: 1 })).toEqual([0, 1, 0]);
    expect(sceneDirection({ x: 1, y: 0, z: 0 })).toEqual([1, 0, 0]);
  });
});

describe("patternAnchor", () => {
  it("centres on the body and measures its half-extent across the row", () => {
    const anchor = patternAnchor(BLOCK, X);
    close(anchor.centre, [0, 0, 0]);
    expect(anchor.perp).toEqual([0, -1, 0]);
    expect(anchor.perpHalf).toBeCloseTo(6, 9);
  });

  it("scales the instrument to the SECTION across the row, not the row", () => {
    // The seat radius is about the thing being repeated. A 2 m-long bar
    // patterned along its own length must not grow a two-metre arrowhead.
    const bar: SceneBounds = { min: [-1000, -6, -4], max: [1000, 6, 4] };
    const along = patternAnchor(bar, X);
    const across = patternAnchor(bar, [0, 0, 1]);
    expect(along.radius).toBeCloseTo(Math.hypot(6, 4), 9);
    // Across the bar's length the section legitimately includes it.
    expect(across.radius).toBeGreaterThan(1000);
  });

  it("gives a degenerate (zero-thickness) body a grabbable instrument", () => {
    const sheet: SceneBounds = { min: [0, 0, 0], max: [0, 0, 0] };
    expect(patternAnchor(sheet, X).radius).toBeGreaterThan(0);
  });
});

describe("the two rails", () => {
  it("clears the body and puts the count rail outside the spacing rail", () => {
    const anchor = patternAnchor(BLOCK, X);
    expect(spacingRailOffset(anchor)).toBeGreaterThan(anchor.perpHalf);
    expect(countRailOffset(anchor)).toBeGreaterThan(spacingRailOffset(anchor));
  });

  it("clears a WIDE FLAT plate, whose thinnest axis is the rail's own", () => {
    // MEASURED before the clearance was tied to `radius`: a 95 x 65 x 10 mm
    // plate put both rails 6 and 16 mm under a 95 mm-wide part, and because the
    // gauge is `depthTest: false` both rods drew ACROSS its top face. The
    // clearance must scale with how big the part reads, not with the direction
    // the rails happen to hang along.
    const plate = patternAnchor(
      { min: [-47.5, -5, -32.5], max: [47.5, 5, 32.5] },
      X,
    );
    expect(plate.perpHalf).toBeCloseTo(5, 9);
    // Clear of the metal by more than the part is thick, not by less.
    expect(spacingRailOffset(plate) - plate.perpHalf).toBeGreaterThan(
      2 * plate.perpHalf,
    );
  });

  it("separates the two sleeves in PROPORTION to the instrument", () => {
    // THE HAZARD THIS ITEM OWNS. Seated on one line the two gauges would
    // overlap for the whole first gap and each sleeve could answer for its
    // sibling.
    //
    // This used to read `>= 10`, the millimetre floor, and that floor is what
    // put the count gauge off the frame (see `countRailOffset`). The separation
    // is a SCREEN requirement — the sleeve is 12 px half-thick — and the camera
    // frames `radius`, so a fraction of `radius` is the form of it that holds at
    // every part size: measured 78 / 83 / 70 px on parts of 29 / 11 / 102 mm,
    // where the floor gave 208 / 371 / 116 for the same requirement.
    //
    // The hairline body is still here, and it is now held by MIN_SEAT_RADIUS_MM
    // rather than by a rail-pitch floor — one scale floor instead of three.
    for (const bounds of [
      BLOCK,
      { min: [0, 0, 0], max: [40, 0, 0] } as SceneBounds,
    ]) {
      const anchor = patternAnchor(bounds, X);
      expect(anchor.radius).toBeGreaterThanOrEqual(2);
      expect(countRailOffset(anchor) - spacingRailOffset(anchor)).toBeCloseTo(
        RAIL_PITCH_FRAC * anchor.radius,
        9,
      );
    }
  });

  it("SCALES WITH THE PART — the property the floors broke", () => {
    // The regression test for the P1, stated as the invariant rather than as a
    // number: two geometrically SIMILAR bodies must get geometrically similar
    // instruments, so every seat length scales by exactly the body's scale
    // factor. A `max(…, <constant> mm)` cannot do that, which is precisely why
    // the seat stopped shrinking with the part and walked off the frame — and
    // it is why this assertion FAILS on the pre-fix arithmetic at k = 4: the
    // floors select the constant for the small body and the fraction for the
    // large one, so `spacingRailOffset` came out 12 mm and 34.1 mm (it reports
    // "expected 34.095… to be close to 48") and `countRailOffset` 22 mm and
    // 48.5 mm — ratios of 2.84 and 2.20 where the bodies differ by 4.
    //
    // It matters because the camera fits the BODY: an instrument similar to the
    // part occupies a fixed share of the frame at every part size, which is the
    // only version of "it is on screen" that is not a coincidence about one
    // test fixture.
    const k = 4;
    const small = patternAnchor(BLOCK, X);
    const large = patternAnchor(
      {
        min: [BLOCK.min[0] * k, BLOCK.min[1] * k, BLOCK.min[2] * k],
        max: [BLOCK.max[0] * k, BLOCK.max[1] * k, BLOCK.max[2] * k],
      },
      X,
    );
    expect(large.radius).toBeCloseTo(k * small.radius, 9);
    expect(spacingRailOffset(large)).toBeCloseTo(
      k * spacingRailOffset(small),
      9,
    );
    expect(countRailOffset(large)).toBeCloseTo(k * countRailOffset(small), 9);
  });

  it("spends at most 0.7 of the instrument's scale getting clear of the body", () => {
    // A BUDGET, not a restatement of the arithmetic: the frame is fitted to the
    // body, so the rails stay inside it only while the whole stack stays inside
    // a small multiple of the part's own scale. Measured on the spec's
    // 29 x 10 x 23 mm part, 0.65 puts the far rail 274 px below the body centre
    // with 56 px of canvas still under the arrow's grip; the pre-fix seat put it
    // 438 px down, past the bottom edge. Raising either fraction back toward
    // what the floors used to deliver (16 mm of clearance+pitch on this BLOCK,
    // i.e. 2.2 x radius) fails here first, cheaply, instead of in a browser.
    for (const bounds of [
      BLOCK,
      { min: [-47.5, -5, -32.5], max: [47.5, 5, 32.5] } as SceneBounds,
      { min: [-14.5, 0, -11.5], max: [14.5, 10, 11.5] } as SceneBounds,
    ]) {
      const anchor = patternAnchor(bounds, X);
      expect(countRailOffset(anchor) - anchor.perpHalf).toBeLessThanOrEqual(
        0.7 * anchor.radius,
      );
    }
  });

  it("puts both seats on the rails, across the row from the body", () => {
    const anchor = patternAnchor(BLOCK, X);
    close(spacingSeat(anchor).base, [0, -spacingRailOffset(anchor), 0]);
    // The count seat is ALSO pulled one pitch back along the row — see below.
    close(countSeat(anchor, 10).base, [-10, -countRailOffset(anchor), 0]);
  });
});

describe("the spacing gauge spans exactly the first gap", () => {
  it("lands its point on the first copy's position", () => {
    const anchor = patternAnchor(BLOCK, X);
    const seat = spacingSeat(anchor);
    const rail = spacingRailOffset(anchor);
    const [first] = patternInstanceOffsets(2, 14, anchor.dir);
    expect(first).toBeDefined();
    // base + spacing·dir === the first copy's offset, on the rail.
    close(
      [
        seat.base[0] + anchor.dir[0] * 14,
        seat.base[1] + anchor.dir[1] * 14,
        seat.base[2] + anchor.dir[2] * 14,
      ],
      [(first as Vec3)[0], -rail + (first as Vec3)[1], (first as Vec3)[2]],
    );
  });
});

describe("the drawn rungs stand on the ghost copies", () => {
  /**
   * The property the whole seat arithmetic exists for, asked of the SHIPPED
   * primitive: build the real `steppedTrack` on `countSeat` and check that the
   * majors it publishes project to the same points the ghosts are translated
   * to. If these ever disagree the preview and the ladder have become two
   * drawings and this item's central claim is false.
   */
  const check = (count: number, spacing: number): void => {
    const anchor = patternAnchor(BLOCK, X);
    const track = steppedTrack(countSeat(anchor, spacing), {
      pitch: spacing,
      min: MIN_PATTERN_COUNT,
      max: MAX_PATTERN_COUNT,
    });
    const rail = countRailOffset(anchor);
    const stops = track.stops(count, 1);
    const ghosts = patternInstanceOffsets(count, spacing, anchor.dir);

    // One rung per copy — the seed (instance 0) is real metal and gets none.
    expect(stops.major).toHaveLength(ghosts.length);
    stops.major.forEach((n, i) => {
      const ghost = ghosts[i] as Vec3;
      close(track.pointAt(n), [
        anchor.centre[0] + ghost[0],
        anchor.centre[1] - rail + ghost[1],
        anchor.centre[2] + ghost[2],
      ]);
    });

    // …and the grip itself sits on the LAST copy, which is the thing you pull.
    const last = ghosts[ghosts.length - 1] as Vec3;
    close(track.pointAt(count), [
      anchor.centre[0] + last[0],
      anchor.centre[1] - rail + last[1],
      anchor.centre[2] + last[2],
    ]);
  };

  it("at the default 3-up row", () => check(3, 10));
  it("at a long row", () => check(9, 6));
  it("at a fine pitch", () => check(4, 0.5));
  it("at the smallest row that repeats anything", () => check(2, 25));
});

describe("the count track is a counter, not a length", () => {
  const anchor = patternAnchor(BLOCK, X);
  const track = steppedTrack(countSeat(anchor, 10), {
    pitch: 10,
    min: MIN_PATTERN_COUNT,
    max: MAX_PATTERN_COUNT,
  });

  it("quantises to whole copies, with no Ctrl-to-free between them", () => {
    expect(track.quantize(4.4, false)).toBe(4);
    expect(track.quantize(4.6, true)).toBe(5);
  });

  it("cannot reach a count the form would refuse", () => {
    // `parseCount` rejects anything under 2 (a count of 1 repeats nothing), so
    // a drag that could reach it would be a dead end the user can see.
    expect(track.quantize(-3, false)).toBe(MIN_PATTERN_COUNT);
    expect(track.clamp(1)).toBe(MIN_PATTERN_COUNT);
    expect(track.clamp(10_000)).toBe(MAX_PATTERN_COUNT);
  });

  it("agrees with the server's own work bound rather than a rounder number", () => {
    expect(MAX_PATTERN_COUNT).toBe(500);
  });
});
