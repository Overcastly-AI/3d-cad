import { describe, expect, it } from "vitest";

import {
  describeGapMm,
  describeOpenEnds,
  openEnds,
  PROFILE_JOIN_TOLERANCE_MM,
} from "./openEnds";
import type { SketchEntity } from "./tools";

const line = (
  id: string,
  a: [number, number],
  b: [number, number],
  construction = false,
): SketchEntity => ({
  id,
  kind: "line",
  construction,
  start: { x: a[0], y: a[1] },
  end: { x: b[0], y: b[1] },
});

/** A closed 10 x 10 square, corner-to-corner. */
const square = (): SketchEntity[] => [
  line("e1", [0, 0], [10, 0]),
  line("e2", [10, 0], [10, 10]),
  line("e3", [10, 10], [0, 10]),
  line("e4", [0, 10], [0, 0]),
];

describe("openEnds", () => {
  it("a closed loop has no open end", () => {
    expect(openEnds(square())).toEqual([]);
  });

  it("an end a sub-micron short of its neighbour is open, and says by how much", () => {
    // The gear test's own gap: 0.285 um = 2.85e-4 mm, wider than the kernel's
    // 1e-4 mm wire tolerance, invisible at any zoom.
    const entities = square();
    entities[1] = line("e2", [10.000285, 0], [10, 10]);
    const open = openEnds(entities);
    expect(open.map((end) => `${end.entity}.${end.point}`)).toEqual([
      "e1.end",
      "e2.start",
    ]);
    expect(open[0]?.gapMm).toBeCloseTo(0.000285, 9);
  });

  it("ends within the kernel's wire tolerance are joined", () => {
    const entities = square();
    const nudge = PROFILE_JOIN_TOLERANCE_MM / 2;
    entities[1] = line("e2", [10 + nudge, 0], [10, 10]);
    expect(openEnds(entities)).toEqual([]);
  });

  it("an arc's end is where the kernel builds it: projected onto the circle through its start", () => {
    // Stored end sits EXACTLY on the line's start, but 7 um off the circle the
    // arc's start defines, so the kernel's arc ends 7 um short.
    const entities: SketchEntity[] = [
      {
        id: "a1",
        kind: "arc",
        construction: false,
        center: { x: 0, y: 0 },
        start: { x: 10, y: 0 },
        end: { x: 0, y: 10.007 },
      },
      line("l1", [0, 10.007], [10, 0]),
    ];
    const open = openEnds(entities);
    expect(open.map((end) => `${end.entity}.${end.point}`)).toEqual([
      "a1.end",
      "l1.start",
    ]);
    expect(open[0]?.at.y).toBeCloseTo(10, 9);
    expect(open[0]?.gapMm).toBeCloseTo(0.007, 9);
  });

  it("construction geometry and the sketch frame are not profile", () => {
    const entities = [
      ...square(),
      line("c1", [-5, -5], [15, 15], true),
      line("x-axis", [-20, 0], [20, 0], true),
    ];
    expect(openEnds(entities)).toEqual([]);
  });

  it("a T-junction end is open: the kernel chains at ends only", () => {
    const entities = [
      line("bar", [0, 0], [10, 0]),
      line("stem", [5, 0], [5, 5]),
    ];
    expect(openEnds(entities).map((e) => `${e.entity}.${e.point}`)).toEqual([
      "bar.start",
      "bar.end",
      "stem.start",
      "stem.end",
    ]);
  });

  it("a lone curve reports both ends, with no neighbour to measure to", () => {
    const open = openEnds([line("e1", [0, 0], [5, 0])]);
    expect(open).toHaveLength(2);
    expect(open[0]?.gapMm).toBe(5);
  });

  it("a closed spline (first fit point = last) has no open end", () => {
    const entities: SketchEntity[] = [
      {
        id: "s1",
        kind: "spline",
        construction: false,
        points: [
          { x: 0, y: 0 },
          { x: 5, y: 5 },
          { x: 10, y: 0 },
          { x: 0, y: 0 },
        ],
      },
    ];
    expect(openEnds(entities)).toEqual([]);
  });
});

describe("describeOpenEnds", () => {
  it("says nothing about a closed profile", () => {
    expect(describeOpenEnds(square())).toBeNull();
  });

  it("flags a near miss and names the gap", () => {
    const entities = square();
    entities[1] = line("e2", [10.0003, 0], [10, 10]);
    const report = describeOpenEnds(entities);
    expect(report?.label).toBe("2 open ends");
    expect(report?.nearMiss).toBe(true);
    expect(report?.title).toContain("0.00030 mm");
  });

  it("a plainly loose end is counted but not flagged", () => {
    const report = describeOpenEnds([line("e1", [0, 0], [5, 0])]);
    expect(report?.label).toBe("2 open ends");
    expect(report?.nearMiss).toBe(false);
  });
});

describe("describeGapMm", () => {
  it("keeps a sub-hundredth gap readable as NOT zero", () => {
    expect(describeGapMm(0.000287)).toBe("0.00029 mm");
    expect(describeGapMm(1.25)).toBe("1.250 mm");
  });
});
