import { describe, expect, it } from "vitest";

import {
  CIRCLE_SEGMENTS,
  definingPointPositions,
  definingPoints,
  entityPolylines,
  entitySegmentPositions,
} from "./geometry";
import type { SketchEntity } from "./tools";

const line: SketchEntity = {
  id: "e1",
  kind: "line",
  start: { x: 0, y: 0 },
  end: { x: 40, y: 0 },
};
const circle: SketchEntity = {
  id: "e2",
  kind: "circle",
  center: { x: 10, y: 10 },
  radius: 5,
};
const quarterArc: SketchEntity = {
  id: "e3",
  kind: "arc",
  center: { x: 0, y: 0 },
  start: { x: 10, y: 0 },
  end: { x: 0, y: 10 },
};

describe("entityPolylines", () => {
  it("keeps a line as its two endpoints", () => {
    expect(entityPolylines(line)).toEqual([[line.start, line.end]]);
  });

  it("samples a closed circle on the circle", () => {
    const [polyline] = entityPolylines(circle);
    expect(polyline).toHaveLength(CIRCLE_SEGMENTS + 1);
    expect(polyline?.[0]).toEqual(polyline?.[polyline.length - 1]);
    for (const point of polyline ?? []) {
      expect(Math.hypot(point.x - 10, point.y - 10)).toBeCloseTo(5, 9);
    }
  });

  it("samples a CCW arc from start to end", () => {
    const [polyline] = entityPolylines(quarterArc);
    expect(polyline?.[0]?.x).toBeCloseTo(10, 9);
    const last = polyline?.[polyline.length - 1];
    expect(last?.x).toBeCloseTo(0, 9);
    expect(last?.y).toBeCloseTo(10, 9);
    // Quarter sweep → a quarter of the circle's chords (never below 8).
    expect((polyline?.length ?? 0) - 1).toBe(CIRCLE_SEGMENTS / 4);
    // CCW: y must be non-decreasing on this quarter.
    const ys = (polyline ?? []).map((p) => p.y);
    expect([...ys].sort((a, b) => a - b)).toEqual(ys);
  });

  it("free points contribute no polylines but do contribute points", () => {
    const point: SketchEntity = {
      id: "e9",
      kind: "point",
      position: { x: 1, y: 2 },
    };
    expect(entityPolylines(point)).toEqual([]);
    expect(definingPoints(point)).toEqual([{ x: 1, y: 2 }]);
  });
});

describe("world-space buffers", () => {
  it("builds segment pairs on the chosen plane (XZ maps v to +Z)", () => {
    const positions = entitySegmentPositions([line], "XZ");
    expect(Array.from(positions)).toEqual([0, 0, 0, 40, 0, 0]);
    const vertical = entitySegmentPositions(
      [{ ...line, start: { x: 0, y: 0 }, end: { x: 0, y: 25 } }],
      "XZ",
    );
    expect(Array.from(vertical)).toEqual([0, 0, 0, 0, 0, 25]);
  });

  it("sizes the buffer from all entities' chords", () => {
    const positions = entitySegmentPositions([line, circle], "XY");
    expect(positions.length).toBe((1 + CIRCLE_SEGMENTS) * 6);
  });

  it("collects defining points across entities", () => {
    const positions = definingPointPositions([line, circle], "XY");
    expect(Array.from(positions)).toEqual([0, 0, 0, 40, 0, 0, 10, 10, 0]);
  });
});
