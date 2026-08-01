import { describe, expect, it } from "vitest";

import {
  applyPick,
  curveDistance,
  namedPoints,
  pickCandidates,
  samePick,
  toggleSelection,
  type SketchPick,
} from "./pick";
import { sampleSpline } from "./spline";
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

  it("exposes a spline's fit points as fitN (zero-based, no leading zeros)", () => {
    const spline: SketchEntity = {
      id: "e4",
      kind: "spline",
      points: [
        { x: 0, y: 0 },
        { x: 10, y: 20 },
        { x: 20, y: 0 },
      ],
      construction: false,
    };
    const named = namedPoints(spline);
    expect(named.map((n) => n.point)).toEqual(["fit0", "fit1", "fit2"]);
    // Each fitN resolves to its Nth fit coordinate — the pick's anchor.
    expect(named[1]?.at).toEqual({ x: 10, y: 20 });
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

  it("measures a spline against its sampled curve, not the fit polygon", () => {
    const points = [
      { x: 0, y: 0 },
      { x: 10, y: 20 },
      { x: 20, y: 0 },
    ];
    const spline: SketchEntity = {
      id: "e4",
      kind: "spline",
      points,
      construction: false,
    };
    // Every fit point is on the curve.
    expect(curveDistance({ x: 10, y: 20 }, spline)).toBeCloseTo(0, 9);
    // A vertex sampled BETWEEN fit points (off the straight fit polygon) reads
    // as ~0 too — proof the distance tracks the smooth ink, not the polygon.
    const mid =
      sampleSpline(points)[Math.floor(sampleSpline(points).length / 4)];
    expect(mid).toBeDefined();
    if (mid) expect(curveDistance(mid, spline)).toBeCloseTo(0, 9);
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

  it("picks a spline fit point like any defining point", () => {
    const spline: SketchEntity = {
      id: "e4",
      kind: "spline",
      points: [
        { x: 0, y: 0 },
        { x: 10, y: 20 },
        { x: 20, y: 0 },
      ],
      construction: false,
    };
    // Near the middle fit point: the point pick wins over the curve.
    const picks = pickCandidates([spline], { x: 10.4, y: 20.2 }, 2);
    expect(picks[0]).toEqual({ kind: "point", entity: "e4", point: "fit1" });
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

describe("applyPick — plain click replaces, modifier adds (FB-14)", () => {
  const lineA: SketchPick = { kind: "entity", id: "e1" };
  const lineB: SketchPick = { kind: "entity", id: "e2" };
  const cornerA: SketchPick = { kind: "point", entity: "e1", point: "end" };
  const cornerB: SketchPick = { kind: "point", entity: "e9", point: "start" };

  // The founder's exact path: click line A, click line B, expect ONE line
  // selected so `distance` dimensions it instead of refusing.
  it("a plain click on a second line replaces the first", () => {
    expect(applyPick([lineA], [lineB], "replace")).toEqual([lineB]);
  });

  it("a plain click starts over from a multi-selection", () => {
    expect(applyPick([lineA, lineB], [lineB], "replace")).toEqual([lineB]);
  });

  it("plain clicks CYCLE through stacked candidates, one at a time", () => {
    expect(applyPick([], [cornerA, cornerB], "replace")).toEqual([cornerA]);
    expect(applyPick([cornerA], [cornerA, cornerB], "replace")).toEqual([
      cornerB,
    ]);
    // …and back round, so a click-through never strands you on nothing.
    expect(applyPick([cornerB], [cornerA, cornerB], "replace")).toEqual([
      cornerA,
    ]);
  });

  it("a plain click on the only candidate keeps it selected", () => {
    expect(applyPick([lineA], [lineA], "replace")).toEqual([lineA]);
  });

  it("a plain click on empty steel clears", () => {
    expect(applyPick([lineA, lineB], [], "replace")).toEqual([]);
  });

  it("a modifier click ADDS — the two-entity constraint path", () => {
    expect(applyPick([lineA], [lineB], "add")).toEqual([lineA, lineB]);
    expect(applyPick([cornerA], [cornerA, cornerB], "add")).toEqual([
      cornerA,
      cornerB,
    ]);
  });

  it("a modifier click un-picks a candidate that is already held", () => {
    expect(applyPick([lineA, lineB], [lineB], "add")).toEqual([lineA]);
  });

  it("a modifier MISS keeps the selection being assembled", () => {
    expect(applyPick([lineA, lineB], [], "add")).toEqual([lineA, lineB]);
  });
});
