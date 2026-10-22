/**
 * The sketcher reads and takes lengths in the PART's unit (BUILDING-OUTLINE
 * follow-up): a 24 ft wall in an inch part is `288`, typed as `288` or
 * `28 ft`, never `7315.2`. Angles stay in degrees; mm parts are unchanged.
 */
import { describe, expect, it } from "vitest";

import type { SketchConstraint } from "./constraints";
import {
  constraintGlyphs,
  formatDimensionLabel,
  formatSketchLength,
} from "./constraints";
import { classifyDimensionValue } from "./dimensionExpr";
import type { SketchEntity } from "./tools";

describe("sketch lengths in the part's unit", () => {
  it("labels a dimension in inches, keeping mm parts' notation", () => {
    expect(formatSketchLength(7315.2, "in")).toBe("288");
    expect(formatSketchLength(139.7, "in")).toBe("5.5");
    expect(formatSketchLength(7315.2, "mm")).toBe("7315.2");
    expect(formatSketchLength(12.3456, "mm")).toBe("12.35");
    expect(formatDimensionLabel("radius", 12.7, false, "in")).toBe("R0.5");
    expect(formatDimensionLabel("distance", 7315.2, true, "ft")).toBe("(24)");
    // Angles are degrees in every part.
    expect(formatDimensionLabel("angle", 30, false, "in")).toBe("30°");
  });

  it("reads a typed length in the part's unit, a suffix overriding it", () => {
    expect(classifyDimensionValue("336", { length: true, unit: "in" })).toEqual(
      {
        kind: "literal",
        valueMm: 336 * 25.4,
      },
    );
    expect(
      classifyDimensionValue("28 ft", { length: true, unit: "in" }),
    ).toEqual({
      kind: "literal",
      valueMm: 28 * 304.8,
    });
    expect(
      classifyDimensionValue("20 mm", { length: true, unit: "in" }),
    ).toEqual({
      kind: "literal",
      valueMm: 20,
    });
    expect(classifyDimensionValue("43", { length: true, unit: "mm" })).toEqual({
      kind: "literal",
      valueMm: 43,
    });
    // Carpenter notation reads in the part's unit (RESEARCH §29).
    expect(
      classifyDimensionValue("11 15/32", { length: true, unit: "in" }),
    ).toEqual({ kind: "literal", valueMm: 11.46875 * 25.4 });
    // A formula stays a formula; an angle cell reads bare degrees.
    expect(
      classifyDimensionValue("width/2", { length: true, unit: "in" }),
    ).toEqual({
      kind: "expression",
      expression: "width/2",
    });
    expect(classifyDimensionValue("45")).toEqual({
      kind: "literal",
      valueMm: 45,
    });
  });

  it("draws an inch part's glyphs in inches", () => {
    const entities = [
      {
        id: "e1",
        kind: "line",
        construction: false,
        start: { x: 0, y: 0 },
        end: { x: 7315.2, y: 0 },
      },
    ] as SketchEntity[];
    const constraints = [
      { kind: "distance", entity: "e1", value_mm: 7315.2 },
    ] as SketchConstraint[];
    const [inch] = constraintGlyphs(constraints, entities, 5, undefined, "in");
    expect(inch?.label).toBe("288");
    const [metric] = constraintGlyphs(constraints, entities, 5);
    expect(metric?.label).toBe("7315.2");
  });
});
