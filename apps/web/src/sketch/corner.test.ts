import { describe, expect, it } from "vitest";

import { cornerPoint, toggleCornerPick, type SketchLine } from "./corner";

const line = (
  id: string,
  start: { x: number; y: number },
  end: { x: number; y: number },
): SketchLine => ({ id, kind: "line", start, end, construction: false });

describe("toggleCornerPick — the two-line corner set", () => {
  it("appends fresh legs until two are held", () => {
    expect(toggleCornerPick([], "e1")).toEqual(["e1"]);
    expect(toggleCornerPick(["e1"], "e2")).toEqual(["e1", "e2"]);
  });

  it("re-clicking a held leg removes it", () => {
    expect(toggleCornerPick(["e1", "e2"], "e1")).toEqual(["e2"]);
  });

  it("ignores a third leg once two are held", () => {
    expect(toggleCornerPick(["e1", "e2"], "e3")).toEqual(["e1", "e2"]);
  });
});

describe("cornerPoint — anchors the value editor at the shared vertex", () => {
  it("finds the endpoints the two legs share", () => {
    // Two legs of an L meeting at the origin.
    const a = line("e1", { x: 0, y: 0 }, { x: 40, y: 0 });
    const b = line("e2", { x: 0, y: 0 }, { x: 0, y: 30 });
    expect(cornerPoint(a, b)).toEqual({ x: 0, y: 0 });
  });

  it("uses the closest endpoint pair when the legs only nearly meet", () => {
    const a = line("e1", { x: 0, y: 0 }, { x: 40, y: 0 });
    const b = line("e2", { x: 40, y: 2 }, { x: 40, y: 30 });
    // Closest pair is a.end (40,0) and b.start (40,2) → midpoint (40,1).
    expect(cornerPoint(a, b)).toEqual({ x: 40, y: 1 });
  });
});
