import { describe, expect, it } from "vitest";

import type { SketchEntity } from "../sketch/tools";
import {
  pointInLoop,
  profileLoops,
  profileRegions,
  signedArea,
} from "./profileLoops";

/** A closed rectangle drawn as four separate lines (the common rect sketch). */
function rectLines(
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  prefix = "r",
): SketchEntity[] {
  const corners = [
    { x: x0, y: y0 },
    { x: x1, y: y0 },
    { x: x1, y: y1 },
    { x: x0, y: y1 },
  ];
  return corners.map((start, i) => ({
    id: `${prefix}${i}`,
    kind: "line" as const,
    start,
    end: corners[(i + 1) % 4] as { x: number; y: number },
    construction: false,
  }));
}

describe("signedArea / pointInLoop", () => {
  it("measures a unit square and locates its centre", () => {
    const square = [
      { x: 0, y: 0 },
      { x: 2, y: 0 },
      { x: 2, y: 2 },
      { x: 0, y: 2 },
    ];
    expect(Math.abs(signedArea(square))).toBeCloseTo(4, 6);
    expect(pointInLoop({ x: 1, y: 1 }, square)).toBe(true);
    expect(pointInLoop({ x: 3, y: 1 }, square)).toBe(false);
  });
});

describe("profileLoops", () => {
  it("stitches four lines into one closed loop", () => {
    const loops = profileLoops(rectLines(0, 0, 40, 20));
    expect(loops).toHaveLength(1);
    expect(
      Math.abs(signedArea(loops[0] as { x: number; y: number }[])),
    ).toBeCloseTo(800, 3);
  });

  it("treats a circle as its own loop", () => {
    const circle: SketchEntity = {
      id: "c1",
      kind: "circle",
      center: { x: 0, y: 0 },
      radius: 5,
      construction: false,
    };
    const loops = profileLoops([circle]);
    expect(loops).toHaveLength(1);
    // Sampled disc area ≈ πr² (a hair under, being a chord polygon).
    expect(
      Math.abs(signedArea(loops[0] as { x: number; y: number }[])),
    ).toBeGreaterThan(70);
  });

  it("ignores construction geometry and open chains", () => {
    const open: SketchEntity[] = [
      {
        id: "l1",
        kind: "line",
        start: { x: 0, y: 0 },
        end: { x: 10, y: 0 },
        construction: false,
      },
      {
        id: "l2",
        kind: "line",
        start: { x: 10, y: 0 },
        end: { x: 10, y: 10 },
        construction: false,
      },
      {
        id: "axis",
        kind: "line",
        start: { x: 0, y: 0 },
        end: { x: 0, y: 10 },
        construction: true,
      },
    ];
    expect(profileLoops(open)).toHaveLength(0);
  });
});

describe("profileRegions", () => {
  it("returns one solid region for a plain rectangle", () => {
    const regions = profileRegions(rectLines(0, 0, 40, 20));
    expect(regions).toHaveLength(1);
    expect(regions[0]?.holes).toHaveLength(0);
  });

  it("nests a smaller loop as a hole of the enclosing loop", () => {
    const plate = rectLines(0, 0, 40, 40, "outer");
    const bore: SketchEntity = {
      id: "hole",
      kind: "circle",
      center: { x: 20, y: 20 },
      radius: 6,
      construction: false,
    };
    const regions = profileRegions([...plate, bore]);
    expect(regions).toHaveLength(1);
    expect(regions[0]?.holes).toHaveLength(1);
  });

  it("keeps two disjoint loops as two separate solid regions", () => {
    const regions = profileRegions([
      ...rectLines(0, 0, 10, 10, "a"),
      ...rectLines(20, 0, 30, 10, "b"),
    ]);
    expect(regions).toHaveLength(2);
    expect(regions.every((r) => r.holes.length === 0)).toBe(true);
  });
});
