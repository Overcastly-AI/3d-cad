import { describe, expect, it } from "vitest";

import {
  arcEndPoint,
  escapeAction,
  placePoint,
  previewEntities,
  type SketchEntity,
} from "./tools";

const p = (x: number, y: number) => ({ x, y });

describe("placePoint — line", () => {
  it("buffers the start, then emits a line with a sequential id", () => {
    const first = placePoint("line", [], p(0, 0), 1);
    expect(first.entities).toEqual([]);
    expect(first.pending).toEqual([p(0, 0)]);
    expect(first.nextIdIndex).toBe(1);

    const second = placePoint("line", first.pending, p(40, 0), 1);
    expect(second.pending).toEqual([]);
    expect(second.nextIdIndex).toBe(2);
    expect(second.entities).toEqual([
      {
        id: "e1",
        kind: "line",
        start: p(0, 0),
        end: p(40, 0),
        construction: false,
      },
    ]);
  });

  it("rejects a zero-length line and keeps waiting", () => {
    const start = placePoint("line", [], p(5, 5), 3);
    const rejected = placePoint("line", start.pending, p(5, 5), 3);
    expect(rejected.entities).toEqual([]);
    expect(rejected.pending).toEqual([p(5, 5)]);
    expect(rejected.nextIdIndex).toBe(3);
  });
});

describe("placePoint — rect", () => {
  it("emits four CCW closed lines regardless of drag direction", () => {
    const first = placePoint("rect", [], p(40, 25), 1);
    const second = placePoint("rect", first.pending, p(0, 0), 1);
    expect(second.nextIdIndex).toBe(5);
    expect(second.entities.map((e) => e.id)).toEqual(["e1", "e2", "e3", "e4"]);
    expect(second.entities).toEqual([
      {
        id: "e1",
        kind: "line",
        start: p(0, 0),
        end: p(40, 0),
        construction: false,
      },
      {
        id: "e2",
        kind: "line",
        start: p(40, 0),
        end: p(40, 25),
        construction: false,
      },
      {
        id: "e3",
        kind: "line",
        start: p(40, 25),
        end: p(0, 25),
        construction: false,
      },
      {
        id: "e4",
        kind: "line",
        start: p(0, 25),
        end: p(0, 0),
        construction: false,
      },
    ]);
  });

  it("rejects zero-width and zero-height rectangles", () => {
    const armed = placePoint("rect", [], p(10, 10), 1);
    for (const corner of [p(10, 30), p(30, 10), p(10, 10)]) {
      const rejected = placePoint("rect", armed.pending, corner, 1);
      expect(rejected.entities).toEqual([]);
      expect(rejected.pending).toEqual([p(10, 10)]);
    }
  });
});

describe("placePoint — circle", () => {
  it("emits a circle from center + rim point", () => {
    const first = placePoint("circle", [], p(10, 10), 7);
    const second = placePoint("circle", first.pending, p(15, 10), 7);
    expect(second.entities).toEqual([
      {
        id: "e7",
        kind: "circle",
        center: p(10, 10),
        radius: 5,
        construction: false,
      },
    ]);
    expect(second.nextIdIndex).toBe(8);
  });

  it("rejects a zero radius", () => {
    const first = placePoint("circle", [], p(10, 10), 1);
    const rejected = placePoint("circle", first.pending, p(10, 10), 1);
    expect(rejected.entities).toEqual([]);
    expect(rejected.pending).toEqual([p(10, 10)]);
  });
});

describe("placePoint — arc", () => {
  it("emits a CCW arc: center, start, then end projected onto the circle", () => {
    const one = placePoint("arc", [], p(0, 0), 1);
    const two = placePoint("arc", one.pending, p(10, 0), 1);
    expect(two.entities).toEqual([]);
    // Cursor at 45° off-circle: end lands ON the circle (radius 10).
    const three = placePoint("arc", two.pending, p(30, 30), 1);
    const arc = three.entities[0];
    expect(arc).toMatchObject({ id: "e1", kind: "arc", center: p(0, 0) });
    if (arc?.kind !== "arc") throw new Error("expected an arc");
    expect(Math.hypot(arc.end.x, arc.end.y)).toBeCloseTo(10, 9);
    expect(arc.end.x).toBeCloseTo(10 / Math.SQRT2, 9);
    expect(arc.end.y).toBeCloseTo(10 / Math.SQRT2, 9);
  });

  it("rejects a degenerate radius, direction, and zero sweep", () => {
    expect(arcEndPoint(p(0, 0), p(0, 0), p(5, 5))).toBeNull(); // r = 0
    expect(arcEndPoint(p(0, 0), p(10, 0), p(0, 0))).toBeNull(); // no direction
    expect(arcEndPoint(p(0, 0), p(10, 0), p(20, 0))).toBeNull(); // zero sweep
  });
});

describe("select tool", () => {
  it("places nothing", () => {
    const result = placePoint("select", [], p(1, 2), 1);
    expect(result).toEqual({ pending: [], entities: [], nextIdIndex: 1 });
  });
});

describe("previewEntities", () => {
  it("is empty with nothing pending", () => {
    expect(previewEntities("line", [], p(3, 3))).toEqual([]);
    expect(previewEntities("select", [], p(3, 3))).toEqual([]);
  });

  it("rubber-bands a line to the cursor", () => {
    expect(previewEntities("line", [p(0, 0)], p(9, 9))).toEqual([
      {
        id: "preview",
        kind: "line",
        start: p(0, 0),
        end: p(9, 9),
        construction: false,
      },
    ]);
  });

  it("previews the full four-line rectangle", () => {
    const preview = previewEntities("rect", [p(0, 0)], p(4, 3));
    expect(preview).toHaveLength(4);
    expect(preview.every((e: SketchEntity) => e.kind === "line")).toBe(true);
  });

  it("previews the arc radius spoke, then the arc itself", () => {
    const spoke = previewEntities("arc", [p(0, 0)], p(10, 0));
    expect(spoke).toEqual([
      {
        id: "preview",
        kind: "line",
        start: p(0, 0),
        end: p(10, 0),
        construction: false,
      },
    ]);
    const arc = previewEntities("arc", [p(0, 0), p(10, 0)], p(0, 25));
    expect(arc[0]).toMatchObject({ kind: "arc", end: p(0, 10) });
  });
});

describe("escapeAction cascade", () => {
  it("cancels the placement first, then the tool, then exits", () => {
    expect(escapeAction("line", 1)).toBe("cancel-placement");
    expect(escapeAction("line", 0)).toBe("reset-tool");
    expect(escapeAction("select", 0)).toBe("exit");
  });
});
