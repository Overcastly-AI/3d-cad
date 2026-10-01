/**
 * SKETCH-FILLET-UNTRIM: a sketch fillet re-homes the corner it rounds, so the
 * next solve keeps the trim and a second fillet on the next corner starts from
 * the trimmed legs, not the sharp rectangle.
 */
import { beforeEach, describe, expect, it } from "vitest";

import type { SketchConstraint } from "./constraints";
import { reconcileCornerConstraints } from "./cornerConstraints";
import { shapeRigidity } from "./drawDimensions";
import type { Point2D } from "./plane";
import { useSketchStore } from "./store";
import type { SketchEntity } from "./tools";

const line = (id: string, start: Point2D, end: Point2D): SketchEntity => ({
  id,
  kind: "line",
  construction: false,
  start,
  end,
});
const arc = (
  id: string,
  center: Point2D,
  start: Point2D,
  end: Point2D,
): SketchEntity => ({
  id,
  kind: "arc",
  construction: false,
  center,
  start,
  end,
});

/** A typed 40 x 25 rectangle: bottom, right, top, left (CCW), as drawn. */
const RECT: SketchEntity[] = [
  line("e1", { x: 0, y: 0 }, { x: 40, y: 0 }),
  line("e2", { x: 40, y: 0 }, { x: 40, y: 25 }),
  line("e3", { x: 40, y: 25 }, { x: 0, y: 25 }),
  line("e4", { x: 0, y: 25 }, { x: 0, y: 0 }),
];
const WIDTH: SketchConstraint = {
  kind: "distance",
  entity: "e1",
  value_mm: 40,
};
const HEIGHT: SketchConstraint = {
  kind: "distance",
  entity: "e2",
  value_mm: 25,
};
const TYPED: SketchConstraint[] = [
  ...shapeRigidity("rect", ["e1", "e2", "e3", "e4"]),
  WIDTH,
  HEIGHT,
];

/** What the geometry service returns for r5 on the top-right corner. */
const TOP_RIGHT: SketchEntity[] = [
  RECT[0] as SketchEntity,
  line("e2", { x: 40, y: 0 }, { x: 40, y: 20 }),
  line("e3", { x: 35, y: 25 }, { x: 0, y: 25 }),
  RECT[3] as SketchEntity,
  arc("e2.1", { x: 35, y: 20 }, { x: 40, y: 20 }, { x: 35, y: 25 }),
];
/** …and then r5 on the bottom-right corner, from the trimmed legs. */
const BOTH: SketchEntity[] = [
  line("e1", { x: 0, y: 0 }, { x: 35, y: 0 }),
  line("e2", { x: 40, y: 5 }, { x: 40, y: 20 }),
  ...TOP_RIGHT.slice(2),
  arc("e1.1", { x: 35, y: 5 }, { x: 35, y: 0 }, { x: 40, y: 5 }),
];

const corner = (a: string, b: string) =>
  ({ op: "fillet", a, b, value: 5 }) as const;

describe("reconcileCornerConstraints", () => {
  it("re-homes the rounded corner onto the arc and drops what measured it", () => {
    const { constraints, removed } = reconcileCornerConstraints(
      TYPED,
      RECT,
      TOP_RIGHT,
      corner("e2", "e3"),
    );
    // Nothing may still tie the two trimmed ends to each other (the sharp
    // corner), and the trimmed leg's typed H no longer holds it at 25.
    expect(constraints).not.toContainEqual({
      kind: "coincident",
      a: { entity: "e2", point: "end" },
      b: { entity: "e3", point: "start" },
    });
    expect(constraints).not.toContainEqual(HEIGHT);
    expect(removed).toBe(2);
    // The untouched corners, the axes and W (bottom is not trimmed) survive.
    expect(constraints).toContainEqual(WIDTH);
    expect(constraints).toContainEqual({ kind: "vertical", entity: "e2" });
    // The arc joins both trimmed ends, is tangent to both legs, carries r.
    expect(constraints.slice(-5)).toEqual([
      {
        kind: "coincident",
        a: { entity: "e2", point: "end" },
        b: { entity: "e2.1", point: "start" },
      },
      {
        kind: "coincident",
        a: { entity: "e3", point: "start" },
        b: { entity: "e2.1", point: "end" },
      },
      { kind: "tangent", a: "e2.1", b: "e2" },
      { kind: "tangent", a: "e2.1", b: "e3" },
      { kind: "radius", entity: "e2.1", value_mm: 5 },
    ]);
  });

  it("a second fillet keeps the first corner's joins (the shared leg)", () => {
    const first = reconcileCornerConstraints(
      TYPED,
      RECT,
      TOP_RIGHT,
      corner("e2", "e3"),
    ).constraints;
    const { constraints } = reconcileCornerConstraints(
      first,
      TOP_RIGHT,
      BOTH,
      corner("e1", "e2"),
    );
    // e2's top end did not move this time: its join to the first arc stays.
    expect(constraints).toContainEqual({
      kind: "coincident",
      a: { entity: "e2", point: "end" },
      b: { entity: "e2.1", point: "start" },
    });
    expect(constraints).toContainEqual({
      kind: "coincident",
      a: { entity: "e1", point: "end" },
      b: { entity: "e1.1", point: "start" },
    });
    expect(constraints).toContainEqual({
      kind: "coincident",
      a: { entity: "e2", point: "start" },
      b: { entity: "e1.1", point: "end" },
    });
    // No constraint still names either sharp corner's old pairing, and no
    // length dimension on a trimmed leg survives.
    expect(
      constraints.filter(
        (c) =>
          c.kind === "coincident" &&
          [c.a.entity, c.b.entity].every((id) => /^e\d$/.test(id)),
      ),
    ).toEqual([
      {
        kind: "coincident",
        a: { entity: "e3", point: "end" },
        b: { entity: "e4", point: "start" },
      },
      {
        kind: "coincident",
        a: { entity: "e4", point: "end" },
        b: { entity: "e1", point: "start" },
      },
    ]);
    expect(constraints.filter((c) => c.kind === "distance")).toEqual([]);
    expect(constraints.filter((c) => c.kind === "radius")).toHaveLength(2);
  });

  it("a chamfer joins its bridge line and adds no tangency or radius", () => {
    const chamfered: SketchEntity[] = [
      RECT[0] as SketchEntity,
      line("e2", { x: 40, y: 0 }, { x: 40, y: 20 }),
      line("e3", { x: 35, y: 25 }, { x: 0, y: 25 }),
      RECT[3] as SketchEntity,
      line("e2.1", { x: 40, y: 20 }, { x: 35, y: 25 }),
    ];
    const { constraints } = reconcileCornerConstraints(TYPED, RECT, chamfered, {
      op: "chamfer",
      a: "e2",
      b: "e3",
      value: 5,
    });
    expect(constraints.slice(-2)).toEqual([
      {
        kind: "coincident",
        a: { entity: "e2", point: "end" },
        b: { entity: "e2.1", point: "start" },
      },
      {
        kind: "coincident",
        a: { entity: "e3", point: "start" },
        b: { entity: "e2.1", point: "end" },
      },
    ]);
    expect(
      constraints.some((c) => c.kind === "tangent" || c.kind === "radius"),
    ).toBe(false);
  });
});

describe("applyCornerResult", () => {
  const store = useSketchStore.getState;
  beforeEach(() => {
    store().exit();
    store().begin();
    store().choosePlane("XY");
    store().setTool("rect");
    store().placeAt({ x: 0, y: 0 });
    store().placeAt({ x: 40, y: 25 });
  });

  it("swaps in the trimmed legs with the corner re-homed, and says what it dropped", () => {
    expect(store().entities).toEqual(RECT);
    store().setTool("fillet");
    store().pickCornerLine("e2");
    store().pickCornerLine("e3");
    store().armCorner(5);
    store().applyCornerResult(TOP_RIGHT);

    expect(store().entities).toEqual(TOP_RIGHT);
    expect(store().constraints).toEqual(
      reconcileCornerConstraints(
        shapeRigidity("rect", ["e1", "e2", "e3", "e4"]),
        RECT,
        TOP_RIGHT,
        corner("e2", "e3"),
      ).constraints,
    );
    expect(store().editNote).toBe("Filleted. 1 constraint removed.");
  });
});
