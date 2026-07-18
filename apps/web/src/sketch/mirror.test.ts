/**
 * Pure mirror helpers: the target-set toggle, axis resolution, and the local
 * reflection math the ghost preview draws (which must match the backend's
 * documented rule — arcs swap start/end to stay CCW).
 */
import { describe, expect, it } from "vitest";

import {
  axisLinePoints,
  reflectEntity,
  reflectPoint,
  toggleMirrorTarget,
} from "./mirror";
import type { SketchEntity } from "./tools";

describe("toggleMirrorTarget", () => {
  it("adds a fresh id and removes one already present, order-stable", () => {
    expect(toggleMirrorTarget([], "e1")).toEqual(["e1"]);
    expect(toggleMirrorTarget(["e1"], "e2")).toEqual(["e1", "e2"]);
    expect(toggleMirrorTarget(["e1", "e2"], "e1")).toEqual(["e2"]);
  });
});

describe("axisLinePoints", () => {
  const line: SketchEntity = {
    id: "axis",
    kind: "line",
    start: { x: 0, y: -5 },
    end: { x: 0, y: 5 },
    construction: true,
  };
  const circle: SketchEntity = {
    id: "c1",
    kind: "circle",
    center: { x: 0, y: 0 },
    radius: 3,
    construction: false,
  };

  it("returns the two endpoints for a line entity", () => {
    expect(axisLinePoints([line, circle], "axis")).toEqual({
      a: { x: 0, y: -5 },
      b: { x: 0, y: 5 },
    });
  });

  it("returns null for a non-line or missing id", () => {
    expect(axisLinePoints([line, circle], "c1")).toBeNull();
    expect(axisLinePoints([line, circle], "nope")).toBeNull();
  });
});

describe("reflectPoint", () => {
  it("reflects across a vertical axis (x = 0)", () => {
    const p = reflectPoint({ x: 3, y: 2 }, { x: 0, y: -1 }, { x: 0, y: 1 });
    expect(p.x).toBeCloseTo(-3, 9);
    expect(p.y).toBeCloseTo(2, 9);
  });

  it("reflects across a 45° axis (swaps x and y)", () => {
    const p = reflectPoint({ x: 4, y: 0 }, { x: 0, y: 0 }, { x: 1, y: 1 });
    expect(p.x).toBeCloseTo(0, 9);
    expect(p.y).toBeCloseTo(4, 9);
  });

  it("leaves a point on the axis fixed (coincident-duplicate case)", () => {
    const p = reflectPoint({ x: 0, y: 2 }, { x: 0, y: -1 }, { x: 0, y: 1 });
    expect(p.x).toBeCloseTo(0, 9);
    expect(p.y).toBeCloseTo(2, 9);
  });

  it("guards a degenerate (zero-length) axis without NaN", () => {
    const p = reflectPoint({ x: 3, y: 2 }, { x: 1, y: 1 }, { x: 1, y: 1 });
    expect(p).toEqual({ x: 3, y: 2 });
  });
});

describe("reflectEntity", () => {
  const vertA = { x: 0, y: -1 };
  const vertB = { x: 0, y: 1 };

  it("reflects a line across a vertical axis with a fresh id", () => {
    const line: SketchEntity = {
      id: "e1",
      kind: "line",
      start: { x: 2, y: 0 },
      end: { x: 5, y: 3 },
      construction: false,
    };
    const out = reflectEntity(line, vertA, vertB, "ghost-0");
    expect(out).toEqual({
      id: "ghost-0",
      kind: "line",
      start: { x: -2, y: 0 },
      end: { x: -5, y: 3 },
      construction: false,
    });
  });

  it("inherits the construction flag", () => {
    const circle: SketchEntity = {
      id: "c1",
      kind: "circle",
      center: { x: 4, y: 1 },
      radius: 2,
      construction: true,
    };
    const out = reflectEntity(circle, vertA, vertB, "ghost-0");
    expect(out.construction).toBe(true);
    expect(out.kind === "circle" ? out.center : null).toEqual({ x: -4, y: 1 });
    expect(out.kind === "circle" ? out.radius : null).toBe(2);
  });

  it("swaps an arc's start/end to keep the CCW-from-start invariant", () => {
    const arc: SketchEntity = {
      id: "a1",
      kind: "arc",
      center: { x: 3, y: 0 },
      start: { x: 5, y: 0 },
      end: { x: 3, y: 2 },
      construction: false,
    };
    const out = reflectEntity(arc, vertA, vertB, "ghost-0");
    if (out.kind !== "arc") throw new Error("expected arc");
    expect(out.center).toEqual({ x: -3, y: 0 });
    // start = reflected source END; end = reflected source START.
    expect(out.start).toEqual({ x: -3, y: 2 });
    expect(out.end).toEqual({ x: -5, y: 0 });
  });
});
