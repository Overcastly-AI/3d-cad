import { describe, expect, it } from "vitest";

import { distanceToPolylinePx, resolveMarkPick } from "./edgeMarkResolve";

/** Two parallel rim edges 6 px apart, as a 2 mm wall projects (y = 100, 106). */
const outer = [0, 100, 200, 100];
const inner = [0, 106, 200, 106];
const paths = new Map<number, number[]>([
  [3, outer],
  [7, inner],
]);
const pathOf = (index: number) => paths.get(index) ?? null;
/** The marks overlap: centres 11 px apart, Ø24 discs. */
const marks = [
  { index: 3, x: 100, y: 100 },
  { index: 7, x: 109, y: 106 },
];

describe("distanceToPolylinePx", () => {
  it("measures to the nearest segment, clamped to its ends", () => {
    expect(distanceToPolylinePx(50, 103, outer)).toBeCloseTo(3);
    expect(distanceToPolylinePx(-4, 103, outer)).toBeCloseTo(5);
    expect(distanceToPolylinePx(0, 0, [])).toBe(Infinity);
  });
});

describe("resolveMarkPick (EDGE-MARK-OVERLAP)", () => {
  it("a click at the outer mark's centre picks the outer edge even when the inner disc is on top", () => {
    // The browser delivered the click to the inner mark (stacked on top).
    expect(resolveMarkPick(100, 100, 7, marks, pathOf)).toBe(3);
  });

  it("a click at the inner mark's centre picks the inner edge", () => {
    expect(resolveMarkPick(109, 106, 3, marks, pathOf)).toBe(7);
  });

  it("resolves the overlap to the edge nearest the pointer", () => {
    // Edge distances 1 vs 5 px: the edge decides, whichever disc is on top.
    expect(resolveMarkPick(104, 101, 7, marks, pathOf)).toBe(3);
    expect(resolveMarkPick(104, 105, 3, marks, pathOf)).toBe(7);
  });

  it("rims a pixel apart resolve by the mark under the pointer, not by rounding", () => {
    const close = new Map<number, number[]>([
      [11, [600, 0, 600, 600]],
      [13, [602, 0, 602, 600]],
    ]);
    const twins = [
      { index: 11, x: 600, y: 293.8 },
      { index: 13, x: 602, y: 283.5 },
    ];
    // A click's whole-pixel coordinates land nearer edge 11's line.
    expect(
      resolveMarkPick(601, 283, 13, twins, (i) => close.get(i) ?? null),
    ).toBe(13);
  });

  it("a lone mark answers its own edge anywhere on its disc", () => {
    const lone = [{ index: 3, x: 100, y: 100 }];
    expect(resolveMarkPick(100, 111, 3, lone, pathOf)).toBe(3);
  });

  it("a mark whose disc does not reach the pointer is no contender", () => {
    const apart = [
      { index: 3, x: 100, y: 100 },
      { index: 7, x: 160, y: 106 },
    ];
    // Nearer the inner EDGE, but only the outer MARK is under the pointer.
    expect(resolveMarkPick(100, 105, 3, apart, pathOf)).toBe(3);
  });
});
