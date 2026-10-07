/**
 * SKETCH-POINT-DISTANCE — the Dimension tool's pick logic for points.
 *
 * Fusion 360's Sketch Dimension: two points, then the label's placement picks
 * aligned / horizontal / vertical; a point and a line give the perpendicular
 * distance; two parallel lines the distance between them.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  applyConstraintAction,
  constraintEntityRefs,
  constraintGlyphs,
  type SketchConstraint,
} from "./constraints";
import { reconcileCornerConstraints } from "./cornerConstraints";
import {
  measurePointDimension,
  placementDirection,
  pointDimensionLayout,
  type PointDimensionSubject,
} from "./pointDimension";
import type { SketchPick } from "./pick";
import {
  DIMENSION_PLACE_HINT,
  DIMENSION_FROM_ORIGIN_HINT,
  DIMENSION_SECOND_PICK_HINT,
} from "./dimensionPick";
import { datumFrame, withDatums } from "./datum";
import { useSketchStore } from "./store";
import type { SketchEntity } from "./tools";

const line = (
  id: string,
  a: [number, number],
  b: [number, number],
): SketchEntity => ({
  id,
  kind: "line",
  construction: false,
  start: { x: a[0], y: a[1] },
  end: { x: b[0], y: b[1] },
});

const point = (id: string, x: number, y: number): SketchEntity => ({
  id,
  kind: "point",
  construction: false,
  position: { x, y },
});

/** A rim edge and a lip corner 1 mm inside it, plus a free point. */
const ENTITIES: SketchEntity[] = [
  line("rim", [120, 0], [120, 80]),
  line("lip", [99, 79], [119, 79]),
  point("p", 100, 40),
  line("top", [0, 80], [120, 80]),
];
const byId = new Map(ENTITIES.map((e) => [e.id, e]));

const pt = (entity: string, name: string): SketchPick => ({
  kind: "point",
  entity,
  point: name,
});
const ent = (id: string): SketchPick => ({ kind: "entity", id });

describe("placementDirection — Fusion's label rule", () => {
  const a = { x: 0, y: 0 };
  const b = { x: 30, y: 10 };
  it("above or below the pair is horizontal", () => {
    expect(placementDirection(a, b, { x: 15, y: 25 })).toBe("horizontal");
    expect(placementDirection(a, b, { x: 5, y: -8 })).toBe("horizontal");
  });
  it("left or right of the pair is vertical", () => {
    expect(placementDirection(a, b, { x: 45, y: 5 })).toBe("vertical");
    expect(placementDirection(a, b, { x: -9, y: 2 })).toBe("vertical");
  });
  it("between the points, or off a corner, is aligned", () => {
    expect(placementDirection(a, b, { x: 12, y: 6 })).toBe("aligned");
    expect(placementDirection(a, b, { x: 40, y: 20 })).toBe("aligned");
    expect(placementDirection(a, b, { x: -5, y: -5 })).toBe("aligned");
  });
});

describe("D on points (applyConstraintAction)", () => {
  it("two points go to label placement", () => {
    const result = applyConstraintAction(
      "distance",
      [pt("lip", "end"), pt("p", "position")],
      ENTITIES,
      [],
    );
    expect(result).toEqual({
      outcome: "place",
      a: { entity: "lip", point: "end" },
      b: { entity: "p", point: "position" },
    });
  });

  it("the same point twice is refused", () => {
    const result = applyConstraintAction(
      "distance",
      [pt("lip", "end"), pt("lip", "end")],
      ENTITIES,
      [],
    );
    expect(result.outcome).toBe("hint");
  });

  it("a point and a line open the perpendicular distance, measured", () => {
    const result = applyConstraintAction(
      "distance",
      [pt("lip", "end"), ent("rim")],
      ENTITIES,
      [],
    );
    expect(result).toMatchObject({
      outcome: "editor",
      target: {
        kind: "distance",
        noun: "Distance",
        unit: "mm",
        initialValue: 1,
        constraintIndex: null,
        subject: {
          kind: "point_line_distance",
          point: { entity: "lip", point: "end" },
          line: "rim",
        },
      },
    });
  });

  it("a line's own end is refused as a point to it", () => {
    const result = applyConstraintAction(
      "distance",
      [pt("rim", "start"), ent("rim")],
      ENTITIES,
      [],
    );
    expect(result.outcome).toBe("hint");
  });

  it("an existing point-to-line dimension is EDITED, not stacked", () => {
    const existing: SketchConstraint = {
      kind: "point_line_distance",
      point: { entity: "lip", point: "end" },
      line: "rim",
      value_mm: 1,
      name: "inset",
    };
    const result = applyConstraintAction(
      "distance",
      [ent("rim"), pt("lip", "end")],
      ENTITIES,
      [existing],
    );
    expect(result).toMatchObject({
      outcome: "editor",
      target: { constraintIndex: 0, initialName: "inset" },
    });
  });

  it("two parallel lines dimension from an end of the second", () => {
    const result = applyConstraintAction(
      "distance",
      [ent("top"), ent("lip")],
      ENTITIES,
      [],
    );
    expect(result).toMatchObject({
      outcome: "editor",
      target: {
        initialValue: 1,
        subject: {
          kind: "point_line_distance",
          point: { entity: "lip", point: "start" },
          line: "top",
        },
      },
    });
  });

  it("two lines that are not parallel are not a distance", () => {
    const result = applyConstraintAction(
      "distance",
      [ent("rim"), ent("lip")],
      ENTITIES,
      [],
    );
    expect(result.outcome).toBe("hint");
  });

  it("one line is still its length", () => {
    const result = applyConstraintAction(
      "distance",
      [ent("lip")],
      ENTITIES,
      [],
    );
    expect(result).toMatchObject({
      outcome: "editor",
      target: { entity: "lip", initialValue: 20 },
    });
    if (result.outcome === "editor") {
      expect(result.target.subject).toBeUndefined();
    }
  });
});

describe("measure and layout", () => {
  const pair = (
    direction: "aligned" | "horizontal" | "vertical",
  ): PointDimensionSubject => ({
    kind: "point_distance",
    a: { entity: "lip", point: "start" },
    b: { entity: "p", point: "position" },
    direction,
  });
  it("reads each direction off the geometry", () => {
    expect(measurePointDimension(pair("horizontal"), byId)).toBe(1);
    expect(measurePointDimension(pair("vertical"), byId)).toBe(39);
    expect(measurePointDimension(pair("aligned"), byId)).toBeCloseTo(
      Math.hypot(1, 39),
      12,
    );
  });
  it("a horizontal dimension sits above the pair with two extension lines", () => {
    const layout = pointDimensionLayout(pair("horizontal"), byId, 3);
    expect(layout?.anchor).toEqual({ x: 99.5, y: 85 });
    expect(layout?.ink).toHaveLength(3);
  });
  it("a sharp operand measures to where the two lines meet", () => {
    const subject: PointDimensionSubject = {
      kind: "point_line_distance",
      point: { entity: "lip", point: "end", sharp: "rim" },
      line: "top",
    };
    expect(measurePointDimension(subject, byId)).toBe(1);
  });
  it("the glyph and the refs cover both kinds", () => {
    const constraints: SketchConstraint[] = [
      {
        kind: "point_distance",
        a: { entity: "lip", point: "start" },
        b: { entity: "p", point: "position", sharp: null },
        direction: "vertical",
        value_mm: 39,
      },
      {
        kind: "point_line_distance",
        point: { entity: "lip", point: "end", sharp: "rim" },
        line: "top",
        value_mm: 1,
      },
    ];
    expect(constraintEntityRefs(constraints[1] as SketchConstraint)).toEqual([
      "lip",
      "rim",
      "top",
    ]);
    const glyphs = constraintGlyphs(constraints, ENTITIES, 3);
    expect(glyphs.map((g) => [g.kind, g.label, g.editable])).toEqual([
      ["point_distance", "39", true],
      ["point_line_distance", "1", true],
    ]);
  });
});

describe("the armed Dimension tool on points (store)", () => {
  beforeEach(() => {
    useSketchStore.getState().exit();
    useSketchStore
      .getState()
      .beginEdit("f1", { kind: "origin", base: "XY" }, ENTITIES, []);
  });
  const store = useSketchStore.getState;

  it("point, point, then the label's placement decides the direction", () => {
    store().applyConstraint("distance");
    store().selectAt({ x: 119, y: 79 }, 0.5); // the lip's corner
    expect(store().dimensionOperands).toEqual([
      { entity: "lip", point: "end" },
    ]);
    expect(store().hint).toBe(DIMENSION_SECOND_PICK_HINT);
    store().selectAt({ x: 100, y: 40 }, 0.5); // the free point
    expect(store().dimensionPlace).toEqual({
      a: { entity: "lip", point: "end" },
      b: { entity: "p", point: "position" },
    });
    expect(store().hint).toBe(DIMENSION_PLACE_HINT);
    store().selectAt({ x: 140, y: 60 }, 0.5); // right of the pair: vertical
    expect(store().dimensionEdit).toMatchObject({
      initialValue: 39,
      subject: { kind: "point_distance", direction: "vertical" },
    });
    store().commitDimension({
      value: 30,
      expression: null,
      name: null,
      driving: true,
    });
    expect(store().constraints).toEqual([
      {
        kind: "point_distance",
        a: { entity: "lip", point: "end" },
        b: { entity: "p", point: "position" },
        direction: "vertical",
        value_mm: 30,
        expression: null,
        name: null,
        driving: null,
      },
    ]);
  });

  it("point, then line: the perpendicular distance editor", () => {
    store().applyConstraint("distance");
    store().selectAt({ x: 119, y: 79 }, 0.5);
    store().selectAt({ x: 120, y: 40 }, 0.5); // the rim edge
    expect(store().dimensionEdit).toMatchObject({
      initialValue: 1,
      subject: { kind: "point_line_distance", line: "rim" },
    });
    expect(store().dimensionPick).toBeNull();
    expect(store().dimensionOperands).toEqual([]);
  });

  it("Escape drops a label being placed", () => {
    store().applyConstraint("distance");
    store().selectAt({ x: 119, y: 79 }, 0.5);
    store().selectAt({ x: 100, y: 40 }, 0.5);
    store().escape();
    expect(store().dimensionPlace).toBeNull();
    expect(store().dimensionEdit).toBeNull();
    expect(store().mode).toBe("draw");
  });

  it("an existing dimension's glyph reopens its editor with the operands", () => {
    store().applyConstraint("distance");
    store().selectAt({ x: 119, y: 79 }, 0.5);
    store().selectAt({ x: 120, y: 40 }, 0.5);
    store().commitDimension({
      value: 1,
      expression: null,
      name: null,
      driving: true,
    });
    store().editDimension(0);
    expect(store().dimensionEdit).toMatchObject({
      constraintIndex: 0,
      subject: { kind: "point_line_distance", line: "rim" },
    });
  });
});

describe("the frame is a TARGET of a point dimension, never its only operand", () => {
  const framed = withDatums(ENTITIES, datumFrame(50));
  const origin = pt("origin", "position");

  it("the origin and a point: placement, dimensioning the point FROM it", () => {
    const result = applyConstraintAction(
      "distance",
      [origin, pt("p", "position")],
      framed,
      [],
    );
    expect(result).toMatchObject({ outcome: "place" });
  });

  it("the origin alone, or the origin and an axis, is refused by name", () => {
    for (const picks of [[origin], [origin, ent("x-axis")]]) {
      const result = applyConstraintAction("distance", picks, framed, []);
      expect(result.outcome).toBe("hint");
      if (result.outcome === "hint") {
        expect(result.hint).toMatch(/origin and axes are fixed/);
      }
    }
  });

  it("armed: the origin is held as the reference, and the point is placed from it", () => {
    useSketchStore.getState().exit();
    useSketchStore
      .getState()
      .beginEdit("f1", { kind: "origin", base: "XY" }, ENTITIES, []);
    const store = useSketchStore.getState;
    store().applyConstraint("distance");
    store().selectAt({ x: 0, y: 0 }, 0.5);
    expect(store().dimensionOperands).toEqual([
      { entity: "origin", point: "position" },
    ]);
    expect(store().hint).toBe(DIMENSION_FROM_ORIGIN_HINT);
    store().selectAt({ x: 100, y: 40 }, 0.5);
    expect(store().dimensionPlace).not.toBeNull();
    store().selectAt({ x: 50, y: 60 }, 0.5); // above the pair: horizontal
    store().commitDimension({
      value: 90,
      expression: null,
      name: null,
      driving: true,
    });
    // The origin is materialised and pinned, so the POINT is what moves.
    expect(store().constraints).toEqual([
      expect.objectContaining({ kind: "point_distance", value_mm: 90 }),
      expect.objectContaining({
        kind: "fixed",
        point: { entity: "origin", point: "position" },
      }),
    ]);
  });
});

describe("a corner fillet keeps a point dimension, to the virtual sharp", () => {
  it("re-attaches an operand on the trimmed end", () => {
    const before = [line("a", [0, 0], [40, 0]), line("b", [40, 0], [40, 30])];
    const after = [
      line("a", [0, 0], [35, 0]),
      line("b", [40, 5], [40, 30]),
      {
        id: "e9",
        kind: "arc",
        construction: false,
        center: { x: 35, y: 5 },
        start: { x: 35, y: 0 },
        end: { x: 40, y: 5 },
      } satisfies SketchEntity,
      point("q", 10, 10),
    ];
    const dim: SketchConstraint = {
      kind: "point_distance",
      a: { entity: "q", point: "position" },
      b: { entity: "a", point: "end" },
      direction: "horizontal",
      value_mm: 30,
    };
    const result = reconcileCornerConstraints(
      [dim],
      [...before, point("q", 10, 10)],
      after,
      { op: "fillet", a: "a", b: "b", value: 5 },
    );
    expect(result.constraints[0]).toEqual({
      ...dim,
      b: { entity: "a", point: "end", sharp: "b" },
    });
    expect(result.removed).toBe(0);
  });
});
