import { describe, expect, it } from "vitest";

import {
  curveDistance,
  namedPoints,
  pickCandidates,
  samePick,
  toggleSelection,
  type SketchPick,
} from "./pick";
import type { SketchEntity } from "./tools";

const line: SketchEntity = {
  id: "e1",
  kind: "line",
  start: { x: 0, y: 0 },
  end: { x: 40, y: 0 },
  construction: false,
};
const circle: SketchEntity = {
  id: "e2",
  kind: "circle",
  center: { x: 100, y: 0 },
  radius: 10,
  construction: false,
};
const arc: SketchEntity = {
  id: "e3",
  kind: "arc",
  center: { x: 0, y: 100 },
  start: { x: 10, y: 100 }, // 0°
  end: { x: 0, y: 110 }, // 90°, CCW quarter
  construction: false,
};

describe("namedPoints", () => {
  it("exposes the constraint-addressable points per kind", () => {
    expect(namedPoints(line).map((n) => n.point)).toEqual(["start", "end"]);
    expect(namedPoints(circle).map((n) => n.point)).toEqual(["center"]);
    expect(namedPoints(arc).map((n) => n.point)).toEqual([
      "center",
      "start",
      "end",
    ]);
  });
});

describe("curveDistance", () => {
  it("measures to the line segment, clamped at the ends", () => {
    expect(curveDistance({ x: 20, y: 3 }, line)).toBeCloseTo(3, 12);
    expect(curveDistance({ x: -5, y: 0 }, line)).toBeCloseTo(5, 12);
  });

  it("measures radially to a circle", () => {
    expect(curveDistance({ x: 100, y: 7 }, circle)).toBeCloseTo(3, 12);
    expect(curveDistance({ x: 100, y: 14 }, circle)).toBeCloseTo(4, 12);
  });

  it("respects the arc's CCW sweep — off-sweep falls back to endpoints", () => {
    // 45° — inside the quarter sweep, 2 mm outside the radius.
    const onSweep = {
      x: 12 * Math.cos(Math.PI / 4),
      y: 100 + 12 * Math.sin(Math.PI / 4),
    };
    expect(curveDistance(onSweep, arc)).toBeCloseTo(2, 12);
    // 180° — outside the sweep; nearest is the 90° endpoint (0, 110).
    expect(curveDistance({ x: -10, y: 100 }, arc)).toBeCloseTo(
      Math.hypot(10, 10),
      12,
    );
  });
});

describe("pickCandidates", () => {
  it("prefers defining points over curves inside the tolerance", () => {
    const picks = pickCandidates([line], { x: 0.5, y: 0.5 }, 2);
    expect(picks[0]).toEqual({ kind: "point", entity: "e1", point: "start" });
    expect(picks).toContainEqual({ kind: "entity", id: "e1" });
  });

  it("returns curve-only picks away from any point", () => {
    const picks = pickCandidates([line], { x: 20, y: 1 }, 2);
    expect(picks).toEqual([{ kind: "entity", id: "e1" }]);
  });

  it("returns nothing outside the tolerance", () => {
    expect(pickCandidates([line], { x: 20, y: 9 }, 2)).toEqual([]);
  });

  it("stacks coincident corner points in entity order (click-through)", () => {
    const l2: SketchEntity = {
      id: "e9",
      kind: "line",
      start: { x: 40, y: 0 },
      end: { x: 40, y: 25 },
      construction: false,
    };
    const picks = pickCandidates([line, l2], { x: 40, y: 0 }, 1);
    expect(picks[0]).toEqual({ kind: "point", entity: "e1", point: "end" });
    expect(picks[1]).toEqual({ kind: "point", entity: "e9", point: "start" });
  });
});

describe("toggleSelection", () => {
  const cornerA: SketchPick = { kind: "point", entity: "e1", point: "end" };
  const cornerB: SketchPick = { kind: "point", entity: "e9", point: "start" };

  it("clears the selection when clicking empty space", () => {
    expect(toggleSelection([cornerA], [])).toEqual([]);
  });

  it("adds the best unselected candidate", () => {
    expect(toggleSelection([], [cornerA, cornerB])).toEqual([cornerA]);
  });

  it("cycles to the next stacked candidate when the first is selected", () => {
    expect(toggleSelection([cornerA], [cornerA, cornerB])).toEqual([
      cornerA,
      cornerB,
    ]);
  });

  it("removes the best candidate once every candidate is selected", () => {
    expect(toggleSelection([cornerA, cornerB], [cornerA, cornerB])).toEqual([
      cornerB,
    ]);
  });

  it("samePick distinguishes grains", () => {
    expect(samePick(cornerA, { kind: "entity", id: "e1" })).toBe(false);
    expect(samePick(cornerA, { ...cornerA })).toBe(true);
  });
});
