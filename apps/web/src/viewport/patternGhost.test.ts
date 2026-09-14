/**
 * THE PATTERN PREVIEW's instance list (CRAFT-11).
 *
 * The case that matters most here is the negative one: the SEED gets no ghost.
 * Instance 0 is the real body, already on screen as committed metal, and a
 * translucent copy laid exactly on top of it would say that metal is pending —
 * an off-by-one that draws perfectly and states the opposite of the truth.
 */
import type { Vec3 } from "@loft/design";
import { describe, expect, it } from "vitest";

import { patternInstanceOffsets } from "./patternGhost";

const X: Vec3 = [1, 0, 0];

describe("patternInstanceOffsets", () => {
  it("ghosts the COPIES and never the seed", () => {
    // count = 3 means three bodies total, of which one already exists.
    expect(patternInstanceOffsets(3, 10, X)).toEqual([
      [10, 0, 0],
      [20, 0, 0],
    ]);
  });

  it("draws nothing for a row that repeats nothing", () => {
    expect(patternInstanceOffsets(1, 10, X)).toEqual([]);
    expect(patternInstanceOffsets(0, 10, X)).toEqual([]);
    expect(patternInstanceOffsets(-4, 10, X)).toEqual([]);
  });

  it("steps along the direction it is given, in scene mm", () => {
    expect(patternInstanceOffsets(3, 4, [0, 0, -1])).toEqual([
      [0, 0, -4],
      [0, 0, -8],
    ]);
  });

  it("ignores a fractional count rather than drawing half a copy", () => {
    expect(patternInstanceOffsets(3.9, 10, X)).toHaveLength(2);
  });

  it("has one entry per drawn copy at the ceiling", () => {
    expect(patternInstanceOffsets(500, 1, X)).toHaveLength(499);
  });
});
