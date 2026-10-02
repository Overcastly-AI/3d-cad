/**
 * SKETCH-FILLET-KEEP-DIMS: the client's half of a dimension measured to a
 * virtual sharp — what it binds to, where its glyph sits, and the marks drawn
 * where the extended legs meet.
 */
import { describe, expect, it } from "vitest";

import {
  constraintEntityRefs,
  constraintGlyphs,
  reconcileConstraints,
  type SketchConstraint,
} from "./constraints";
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";
import {
  dimensionSpan,
  lineIntersection,
  virtualSharpMarks,
  type DistanceConstraint,
} from "./virtualSharp";

const line = (id: string, start: Point2D, end: Point2D) =>
  ({ id, kind: "line", construction: false, start, end }) as const;

/** An 80 x 50 rectangle with its two right corners rounded R5. */
const LEGS = [
  line("e1", { x: 0, y: 0 }, { x: 75, y: 0 }),
  line("e2", { x: 80, y: 5 }, { x: 80, y: 45 }),
  line("e3", { x: 75, y: 50 }, { x: 0, y: 50 }),
  line("e4", { x: 0, y: 50 }, { x: 0, y: 0 }),
];
const byId = new Map<string, SketchEntity>(LEGS.map((e) => [e.id, e]));
const W: DistanceConstraint = {
  kind: "distance",
  entity: "e1",
  value_mm: 80,
  end_sharp: "e2",
};
const H: DistanceConstraint = {
  kind: "distance",
  entity: "e2",
  value_mm: 50,
  start_sharp: "e1",
  end_sharp: "e3",
};

describe("virtual sharps", () => {
  it("meet where the legs' lines do, and parallel lines never meet", () => {
    expect(lineIntersection(LEGS[0]!, LEGS[1]!)).toEqual({ x: 80, y: 0 });
    expect(lineIntersection(LEGS[0]!, LEGS[2]!)).toBeNull();
  });

  it("bind the dimension to the other legs, so deleting one drops it", () => {
    expect(constraintEntityRefs(H)).toEqual(["e2", "e1", "e3"]);
    const withoutTop = LEGS.filter((e) => e.id !== "e3");
    const kept = reconcileConstraints([W, H], withoutTop).constraints;
    expect(kept).toEqual([W]);
  });

  it("measure the span sharp to sharp", () => {
    const span = dimensionSpan(H, LEGS[1]!, byId);
    expect(span).toMatchObject({
      start: { x: 80, y: 0 },
      end: { x: 80, y: 50 },
    });
  });

  it("centre the glyph on the span, not on the trimmed leg", () => {
    const [w, h] = constraintGlyphs([W, H], LEGS, 3.5);
    // W: midway between (0,0) and the sharp (80,0), 3.5 below (right normal).
    expect(w?.anchor).toEqual({ x: 40, y: -3.5 });
    // H: midway between the two right sharps (80,0)-(80,50), 3.5 to the right.
    expect(h?.anchor).toEqual({ x: 83.5, y: 25 });
  });

  it("draw each sharp once, with both legs extended to it", () => {
    const marks = virtualSharpMarks([W, H], LEGS);
    expect(marks.map((m) => m.at)).toEqual([
      { x: 80, y: 0 },
      { x: 80, y: 50 },
    ]);
    expect(marks[0]?.extensions).toEqual([
      [
        { x: 75, y: 0 },
        { x: 80, y: 0 },
      ],
      [
        { x: 80, y: 5 },
        { x: 80, y: 0 },
      ],
    ]);
  });

  it("draw nothing for a plain dimension or an unresolvable sharp", () => {
    const plain: SketchConstraint = {
      kind: "distance",
      entity: "e1",
      value_mm: 75,
    };
    const parallel: SketchConstraint = { ...plain, end_sharp: "e3" };
    expect(virtualSharpMarks([plain, parallel], LEGS)).toEqual([]);
  });
});
