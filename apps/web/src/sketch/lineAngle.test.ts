/**
 * SKETCH-LINE-ANGLE: the Line box shows Length AND Angle, as Fusion's does.
 * `450 Tab 73 Enter` makes a 450 mm line at 73° to the sketch X axis and
 * records both as dimensions; the angle is an ordinary `angle` constraint
 * between the X axis datum (or, for a chained segment, the segment before it)
 * and the new line, so the solver holds it.
 */
import { beforeEach, describe, expect, it } from "vitest";

import type { SketchConstraint } from "./constraints";
import { constraintGlyphs, measuredAngleDeg } from "./constraints";
import {
  angleWitness,
  drawDimensionConstraints,
  drawDimensionFields,
  lineAngleDeg,
  resizedTo,
  sizeDraft,
  X_AXIS_REFERENCE,
} from "./drawDimensions";
import { resolveAngleEntry, resolveDrawCells } from "./drawEntry";
import { chainAngleReference } from "./lineChain";
import type { Point2D } from "./plane";
import { useSketchStore } from "./store";
import type { SketchEntity } from "./tools";

const store = useSketchStore.getState;
const rad = (deg: number) => (deg * Math.PI) / 180;
const NO_NAMES = new Map();

const click = (at: Point2D) =>
  store().placeAt(store().aim(at, 0.5, { suppressed: false, axisLock: false }));

const line = (id: string): Extract<SketchEntity, { kind: "line" }> => {
  const entity = store().entities.find((e) => e.id === id);
  if (entity?.kind !== "line") throw new Error(`no line ${id}`);
  return entity;
};

const onLine = (c: SketchConstraint, id: string): boolean =>
  (c.kind === "horizontal" || c.kind === "vertical") && c.entity === id;

describe("the angle cell's geometry", () => {
  it("measures the unsigned angle from the reference, 0 for a point", () => {
    const o = { x: 0, y: 0 };
    expect(lineAngleDeg({ x: 1, y: 0 }, o, { x: 1, y: 1 })).toBeCloseTo(45);
    expect(lineAngleDeg({ x: 1, y: 0 }, o, { x: 1, y: -1 })).toBeCloseTo(45);
    expect(lineAngleDeg({ x: 1, y: 0 }, o, { x: -1, y: 1 })).toBeCloseTo(135);
    expect(lineAngleDeg({ x: 1, y: 0 }, o, o)).toBe(0);
  });

  it("450 at 73 turns the line about its start to 73° off +X", () => {
    const end = resizedTo(
      "line",
      { x: 0, y: 0 },
      { x: 120, y: 80 },
      { length: 450, angle: 73 },
    );
    expect(end.x).toBeCloseTo(450 * Math.cos(rad(73)), 12);
    expect(end.y).toBeCloseTo(450 * Math.sin(rad(73)), 12);
  });

  it("keeps the side the line was drawn on, and the drawn length", () => {
    const from = { x: 10, y: 5 };
    const end = resizedTo("line", from, { x: 40, y: -35 }, { angle: 30 });
    expect(Math.hypot(end.x - from.x, end.y - from.y)).toBeCloseTo(50, 12);
    expect(end.y).toBeLessThan(from.y);
    expect(lineAngleDeg({ x: 1, y: 0 }, from, end)).toBeCloseTo(30, 12);
  });

  it("from a previous segment, turns off it at the joint", () => {
    // The previous segment ran +X into the corner at (10, 0): away from the
    // corner it points -X. A segment drawn upward, typed 60, leans back.
    const reference = { entity: "e1", direction: { x: -10, y: 0 } };
    const end = resizedTo(
      "line",
      { x: 10, y: 0 },
      { x: 10, y: 20 },
      { angle: 60 },
      reference,
    );
    expect(end.x).toBeCloseTo(10 - 20 * Math.cos(rad(60)), 12);
    expect(end.y).toBeCloseTo(20 * Math.sin(rad(60)), 12);
  });

  it("draws the reference ray and the arc between it and the line", () => {
    const segments = angleWitness(
      { x: 0, y: 0 },
      { x: 0, y: 10 },
      { x: 1, y: 0 },
    );
    expect(segments[0]).toEqual([
      { x: 0, y: 0 },
      { x: 10, y: 0 },
    ]);
    const last = segments[segments.length - 1]?.[1];
    expect(last?.x).toBeCloseTo(0, 12);
    expect(last?.y).toBeCloseTo(4, 12);
    expect(
      angleWitness({ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 1, y: 0 }),
    ).toEqual([]);
  });
});

describe("the angle dimension it records", () => {
  const fields = drawDimensionFields("line", { x: 0, y: 0 }, { x: 3, y: 4 }, [
    "e1",
  ]);

  it("is an angle between the X axis datum and the line", () => {
    expect(
      drawDimensionConstraints("line", ["e1"], fields, {
        length: 450,
        angle: 73,
      }),
    ).toEqual([
      { kind: "distance", entity: "e1", value_mm: 450 },
      { kind: "angle", a: "x-axis", b: "e1", value_deg: 73 },
    ]);
  });

  it("carries a formula, and names the previous segment when chained", () => {
    const chained = drawDimensionFields(
      "line",
      { x: 0, y: 0 },
      { x: 3, y: 4 },
      ["e2"],
      { entity: "e1", direction: { x: -1, y: 0 } },
    );
    expect(
      drawDimensionConstraints(
        "line",
        ["e2"],
        chained,
        { angle: 30 },
        {
          angle: "A/2",
        },
      ),
    ).toEqual([
      { kind: "angle", a: "e1", b: "e2", value_deg: 30, expression: "A/2" },
    ]);
  });

  it("applies no angle at or past 180°", () => {
    const draft = { shape: "line" as const, ids: ["e1"], fields };
    expect(sizeDraft(draft, { angle: 180 }).added).toEqual([]);
    expect(sizeDraft(draft, { angle: 0 }).added).toEqual([]);
    expect(sizeDraft(draft, { angle: 179.5 }).typed).toEqual({ angle: 179.5 });
  });
});

describe("the angle cell's text", () => {
  it("reads degrees whatever the length unit", () => {
    expect(resolveAngleEntry("73", NO_NAMES)).toEqual({
      kind: "value",
      value: 73,
      expression: null,
    });
    const cells = resolveDrawCells(
      [{ key: "length" }, { key: "angle" }],
      (i) => ["2", "73"][i] ?? "",
      "in",
      NO_NAMES,
    );
    expect(cells.values.length).toBeCloseTo(50.8, 12);
    expect(cells.values.angle).toBe(73);
  });

  it("takes a formula over a named angle", () => {
    const names = new Map([["A", { value: 146, kind: "angle" as const }]]);
    expect(resolveAngleEntry("A/2", names)).toEqual({
      kind: "value",
      value: 73,
      expression: "A/2",
    });
  });

  it("refuses 0 and 180, and says a Y typed there is a point", () => {
    const zero = resolveAngleEntry("0", NO_NAMES);
    expect(zero).toMatchObject({ kind: "error" });
    expect(zero.kind === "error" && zero.message).toBe(
      "An angle must be above 0° and below 180°.",
    );
    const y = resolveAngleEntry("450.469", NO_NAMES);
    expect(y.kind === "error" && y.message).toContain(
      "type X Tab Y before you click",
    );
    expect(resolveAngleEntry("180", NO_NAMES)).toMatchObject({
      kind: "error",
    });
  });
});

describe("the angle-to-axis glyph", () => {
  it("is written in the wedge at the line's start", () => {
    const entities: SketchEntity[] = [
      {
        id: "x-axis",
        kind: "line",
        start: { x: -50, y: 0 },
        end: { x: 50, y: 0 },
        construction: true,
      },
      {
        id: "e1",
        kind: "line",
        start: { x: 100, y: 20 },
        end: { x: 100, y: 120 },
        construction: false,
      },
    ];
    const [glyph] = constraintGlyphs(
      [{ kind: "angle", a: "x-axis", b: "e1", value_deg: 90 }],
      entities,
      2,
    );
    // Three offsets out along the 45° bisector from (100, 20).
    expect(glyph?.anchor.x).toBeCloseTo(100 + 6 * Math.SQRT1_2, 9);
    expect(glyph?.anchor.y).toBeCloseTo(20 + 6 * Math.SQRT1_2, 9);
  });
});

describe("chainAngleReference", () => {
  const e1: SketchEntity = {
    id: "e1",
    kind: "line",
    start: { x: 0, y: 0 },
    end: { x: 10, y: 0 },
    construction: false,
  };
  const joint = [{ at: { x: 10, y: 0 }, ref: { entity: "e1", point: "end" } }];

  it("is the X axis for a chain's first segment and off the line tool", () => {
    const start = { x: 0, y: 0 };
    expect(chainAngleReference("line", [start], start, [], [e1])).toBe(
      X_AXIS_REFERENCE,
    );
    expect(chainAngleReference("rect", [start], null, [], [e1])).toBe(
      X_AXIS_REFERENCE,
    );
  });

  it("is the previous segment, away from the joint, when continuing", () => {
    expect(
      chainAngleReference("line", [{ x: 10, y: 0 }], { x: 0, y: 0 }, joint, [
        e1,
      ]),
    ).toEqual({ entity: "e1", direction: { x: -10, y: 0 } });
  });
});

describe("typing 450 Tab 73 into a drawn line (store)", () => {
  beforeEach(() => {
    store().exit();
    store().begin();
    store().choosePlane("XY");
    store().setTool("line");
  });

  it("makes the line 450 at 73°, dimensioned, with the axis grounded", () => {
    click({ x: 0, y: 0 });
    click({ x: 100, y: 0 });
    // Drawn along +X: Horizontal was inferred (SNAP-5).
    expect(store().constraints.some((c) => onLine(c, "e1"))).toBe(true);
    const draft = store().drawDimension;
    expect(draft?.fields.map((f) => f.key)).toEqual(["length", "angle"]);

    store().commitDrawDimensions({ length: 450, angle: 73 });
    const e1 = line("e1");
    expect(e1.start).toEqual({ x: 0, y: 0 });
    expect(e1.end.x).toBeCloseTo(450 * Math.cos(rad(73)), 12);
    expect(e1.end.y).toBeCloseTo(450 * Math.sin(rad(73)), 12);
    const { constraints } = store();
    // The typed angle replaced the inferred Horizontal.
    expect(constraints.some((c) => onLine(c, "e1"))).toBe(false);
    expect(constraints).toContainEqual({
      kind: "angle",
      a: "x-axis",
      b: "e1",
      value_deg: 73,
    });
    expect(constraints).toContainEqual({
      kind: "distance",
      entity: "e1",
      value_mm: 450,
    });
    // The axis is in the buffer and pinned, so the solver measures from it.
    expect(store().entities.some((e) => e.id === "x-axis")).toBe(true);
    expect(constraints).toContainEqual({
      kind: "fixed",
      point: { entity: "x-axis", point: "start" },
    });
    // The chain goes on from the new end.
    expect(store().pending).toEqual([e1.end]);
  });

  it("a chained segment's angle is to the segment before it", () => {
    click({ x: 0, y: 0 });
    click({ x: 40, y: 0 });
    click({ x: 40, y: 30 });
    const angle = store().drawDimension?.fields.find((f) => f.key === "angle");
    expect(angle?.reference?.entity).toBe("e1");
    expect(angle?.measured).toBeCloseTo(90, 9);

    store().commitDrawDimensions({ angle: 60 });
    const e2 = line("e2");
    expect(e2.start).toEqual({ x: 40, y: 0 });
    expect(Math.hypot(e2.end.x - 40, e2.end.y)).toBeCloseTo(30, 9);
    // Interior angle at the joint, as `AngleConstraint` reads it.
    expect(measuredAngleDeg(line("e1"), e2, store().constraints)).toBeCloseTo(
      60,
      9,
    );
    expect(store().constraints).toContainEqual({
      kind: "angle",
      a: "e1",
      b: "e2",
      value_deg: 60,
    });
    // No axis was referenced, so none was grounded.
    expect(store().entities.some((e) => e.id === "x-axis")).toBe(false);
  });

  it("a length typed alone keeps the inferred Horizontal", () => {
    click({ x: 0, y: 0 });
    click({ x: 100, y: 0 });
    store().commitDrawDimensions({ length: 426.562 });
    expect(line("e1").end).toEqual({ x: 426.562, y: 0 });
    expect(store().constraints.some((c) => onLine(c, "e1"))).toBe(true);
    expect(store().constraints.some((c) => c.kind === "angle")).toBe(false);
  });
});
