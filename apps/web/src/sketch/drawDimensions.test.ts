import { describe, expect, it } from "vitest";

import {
  dimensionWitness,
  drawDimensionConstraints,
  drawDimensionFields,
  drawShapeOf,
  resizeDrawn,
  resizedTo,
  shapeRigidity,
} from "./drawDimensions";
import type { SketchEntity } from "./tools";
import { rectangleCorners } from "./tools";

const rectEntities = (
  a: { x: number; y: number },
  b: { x: number; y: number },
): SketchEntity[] => {
  const corners = rectangleCorners(a, b);
  return corners.map((start, i) => ({
    id: `e${i + 1}`,
    kind: "line" as const,
    start,
    end: corners[(i + 1) % 4] as { x: number; y: number },
    construction: false,
  }));
};

describe("drawShapeOf", () => {
  it("offers size cells for the two-point shapes only", () => {
    expect(drawShapeOf("rect")).toBe("rect");
    expect(drawShapeOf("line")).toBe("line");
    expect(drawShapeOf("circle")).toBe("circle");
    // Three-point / open-sequence tools keep the select-then-D fallback.
    expect(drawShapeOf("arc")).toBeNull();
    expect(drawShapeOf("spline")).toBeNull();
    expect(drawShapeOf("select")).toBeNull();
  });
});

describe("drawDimensionFields", () => {
  it("gives a rectangle width on the bottom edge and height on the right", () => {
    const fields = drawDimensionFields(
      "rect",
      { x: 0, y: 0 },
      { x: 40, y: 25 },
      ["e1", "e2", "e3", "e4"],
    );
    expect(fields.map((f) => [f.key, f.measuredMm, f.entity])).toEqual([
      ["width", 40, "e1"],
      ["height", 25, "e2"],
    ]);
  });

  it("measures a rectangle dragged down-left the same as up-right", () => {
    const fields = drawDimensionFields(
      "rect",
      { x: 0, y: 0 },
      { x: -40, y: -25 },
    );
    expect(fields.map((f) => f.measuredMm)).toEqual([40, 25]);
    // Nothing has an id until the placement commits.
    expect(fields.every((f) => f.entity === null)).toBe(true);
  });

  it("gives a line its length and a circle its radius", () => {
    expect(
      drawDimensionFields("line", { x: 0, y: 0 }, { x: 3, y: 4 }, ["e1"]),
    ).toEqual([
      {
        key: "length",
        label: "L",
        name: "Length",
        measuredMm: 5,
        entity: "e1",
        kind: "distance",
      },
    ]);
    expect(
      drawDimensionFields("circle", { x: 1, y: 1 }, { x: 1, y: 7 }, ["e9"]),
    ).toEqual([
      {
        key: "radius",
        label: "R",
        name: "Radius",
        measuredMm: 6,
        entity: "e9",
        kind: "radius",
      },
    ]);
  });
});

describe("resizedTo", () => {
  it("keeps the first point put and moves the second", () => {
    expect(
      resizedTo(
        "rect",
        { x: 10, y: 10 },
        { x: 53, y: 33 },
        {
          width: 50,
          height: 30,
        },
      ),
    ).toEqual({ x: 60, y: 40 });
  });

  it("keeps the drag's direction when only a magnitude is retyped", () => {
    expect(
      resizedTo("rect", { x: 0, y: 0 }, { x: -43, y: -23 }, { width: 50 }),
    ).toEqual({ x: -50, y: -23 });
  });

  it("scales a line along its own direction", () => {
    expect(
      resizedTo("line", { x: 0, y: 0 }, { x: 3, y: 4 }, { length: 10 }),
    ).toEqual({ x: 6, y: 8 });
  });

  it("leaves the shape alone when nothing was typed", () => {
    const to = { x: 3, y: 4 };
    expect(resizedTo("line", { x: 0, y: 0 }, to, {})).toEqual(to);
    expect(resizedTo("circle", { x: 0, y: 0 }, to, {})).toEqual(to);
    expect(resizedTo("rect", { x: 0, y: 0 }, to, {})).toEqual(to);
  });
});

describe("resizeDrawn", () => {
  it("rewrites the rectangle's four lines, ids preserved", () => {
    const entities = rectEntities({ x: 0, y: 0 }, { x: 43, y: 23 });
    const next = resizeDrawn(
      "rect",
      ["e1", "e2", "e3", "e4"],
      { x: 0, y: 0 },
      { x: 43, y: 23 },
      entities,
      { width: 50, height: 30 },
    );
    expect(next.map((e) => e.id)).toEqual(["e1", "e2", "e3", "e4"]);
    expect(next).toEqual(rectEntities({ x: 0, y: 0 }, { x: 50, y: 30 }));
    // The corner the drag started from never moved.
    const bottom = next[0];
    expect(bottom?.kind === "line" && bottom.start).toEqual({ x: 0, y: 0 });
  });

  it("leaves entities the draft does not name untouched", () => {
    const other: SketchEntity = {
      id: "e9",
      kind: "circle",
      center: { x: 0, y: 0 },
      radius: 4,
      construction: false,
    };
    const entities = [...rectEntities({ x: 0, y: 0 }, { x: 4, y: 4 }), other];
    const next = resizeDrawn(
      "rect",
      ["e1", "e2", "e3", "e4"],
      { x: 0, y: 0 },
      { x: 4, y: 4 },
      entities,
      { width: 8 },
    );
    expect(next[4]).toBe(other);
  });

  it("sets a circle's radius", () => {
    const circle: SketchEntity = {
      id: "e1",
      kind: "circle",
      center: { x: 2, y: 2 },
      radius: 3,
      construction: false,
    };
    const [next] = resizeDrawn(
      "circle",
      ["e1"],
      { x: 2, y: 2 },
      { x: 5, y: 2 },
      [circle],
      { radius: 12 },
    );
    expect(next?.kind === "circle" && next.radius).toBe(12);
  });
});

describe("drawDimensionConstraints", () => {
  const rectFields = drawDimensionFields(
    "rect",
    { x: 0, y: 0 },
    { x: 40, y: 25 },
    ["e1", "e2", "e3", "e4"],
  );

  it("authors nothing when nothing was typed", () => {
    expect(
      drawDimensionConstraints(
        "rect",
        ["e1", "e2", "e3", "e4"],
        rectFields,
        {},
      ),
    ).toEqual([]);
  });

  // RECT-1: the rigidity set moved OUT of here and into `shapeRigidity`, run at
  // placement. This asserts the half that matters for the move — that the typed
  // path emits ONLY dimensions — because emitting rigidity in both places would
  // double all twelve equations and report an ordinary rectangle as
  // over-constrained.
  it("emits only the typed dimensions — rigidity is the draw's job now", () => {
    const constraints = drawDimensionConstraints(
      "rect",
      ["e1", "e2", "e3", "e4"],
      rectFields,
      { width: 40, height: 25 },
    );
    expect(constraints).toEqual([
      { kind: "distance", entity: "e1", value_mm: 40 },
      { kind: "distance", entity: "e2", value_mm: 25 },
    ]);
  });

  it("dimensions a lone circle without any rigidity set", () => {
    const fields = drawDimensionFields(
      "circle",
      { x: 0, y: 0 },
      { x: 5, y: 0 },
      ["e1"],
    );
    expect(
      drawDimensionConstraints("circle", ["e1"], fields, { radius: 8 }),
    ).toEqual([{ kind: "radius", entity: "e1", value_mm: 8 }]);
  });
});

describe("shapeRigidity (RECT-1)", () => {
  const ids = ["e1", "e2", "e3", "e4"];

  it("holds a drawn rectangle together whether or not it is dimensioned", () => {
    const constraints = shapeRigidity("rect", ids);
    // 4 corner coincidences + 2 horizontal + 2 vertical. 16 DOF − 12 = 4
    // (x, y, w, h), so the set is exact: no redundancy to report, and the
    // rectangle is still free to translate and resize as an undimensioned
    // profile should be.
    expect(constraints).toHaveLength(8);
    expect(constraints.filter((c) => c.kind === "coincident")).toHaveLength(4);
    expect(
      constraints
        .filter((c) => c.kind === "horizontal")
        .map((c) => (c.kind === "horizontal" ? c.entity : null)),
    ).toEqual(["e1", "e3"]);
    expect(
      constraints
        .filter((c) => c.kind === "vertical")
        .map((c) => (c.kind === "vertical" ? c.entity : null)),
    ).toEqual(["e2", "e4"]);
  });

  it("closes the corner loop end-to-start all the way round", () => {
    const coincident = shapeRigidity("rect", ids).filter(
      (c) => c.kind === "coincident",
    );
    expect(
      coincident.map((c) =>
        c.kind === "coincident" ? [c.a.entity, c.b.entity] : null,
      ),
    ).toEqual([
      ["e1", "e2"],
      ["e2", "e3"],
      ["e3", "e4"],
      ["e4", "e1"],
    ]);
  });

  it("gives a circle nothing — one entity has no topology to hold", () => {
    expect(shapeRigidity("circle", ["e1"])).toEqual([]);
  });

  it("refuses a short id list rather than authoring a partial loop", () => {
    expect(shapeRigidity("rect", ["e1", "e2", "e3"])).toEqual([]);
  });
});

describe("dimensionWitness", () => {
  it("offsets the dimension line away from the shape's centre", () => {
    const segments = dimensionWitness(
      { x: 0, y: 0 },
      { x: 40, y: 0 },
      { x: 20, y: 12.5 },
      3,
    );
    expect(segments).toEqual([
      [
        { x: 0, y: 0 },
        { x: 0, y: -3 },
      ],
      [
        { x: 40, y: 0 },
        { x: 40, y: -3 },
      ],
      [
        { x: 0, y: -3 },
        { x: 40, y: -3 },
      ],
    ]);
  });

  it("falls back to the segment's own normal when it runs through the centre", () => {
    const segments = dimensionWitness(
      { x: -5, y: 0 },
      { x: 5, y: 0 },
      { x: 0, y: 0 },
      2,
    );
    expect(segments).toHaveLength(3);
    expect(segments[2]).toEqual([
      { x: -5, y: 2 },
      { x: 5, y: 2 },
    ]);
  });
});
