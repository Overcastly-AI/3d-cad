import { describe, expect, it } from "vitest";

import type { BodyInfo } from "./bodies";
import {
  buildCombineParams,
  canSubmitCombine,
  defaultCombineForm,
  isOrderedOperation,
  operationCopy,
  toolOptionsFor,
} from "./boolean";

const bodies: BodyInfo[] = [
  { baseFeatureId: "x1", name: "Extrude1", featureType: "extrude", ordinal: 1 },
  { baseFeatureId: "x2", name: "Extrude2", featureType: "extrude", ordinal: 2 },
  { baseFeatureId: "x3", name: "Extrude3", featureType: "extrude", ordinal: 3 },
];

describe("defaultCombineForm", () => {
  it("seeds a union of the first two bodies with the multi-lump opt-in off", () => {
    expect(defaultCombineForm(bodies)).toEqual({
      operation: "union",
      targetFeatureId: "x1",
      toolFeatureId: "x2",
      allowDisjoint: false,
    });
  });

  it("leaves slots empty when fewer than two bodies exist", () => {
    expect(defaultCombineForm([bodies[0] as BodyInfo])).toEqual({
      operation: "union",
      targetFeatureId: "x1",
      toolFeatureId: "",
      allowDisjoint: false,
    });
  });
});

describe("isOrderedOperation", () => {
  it("is true only for subtract (Target − Tool)", () => {
    expect(isOrderedOperation("subtract")).toBe(true);
    expect(isOrderedOperation("union")).toBe(false);
    expect(isOrderedOperation("intersect")).toBe(false);
  });
});

describe("operationCopy", () => {
  it("gives subtract asymmetric role labels and an ordered note", () => {
    const copy = operationCopy("subtract");
    expect(copy.glyph).toBe("−");
    expect(copy.targetLabel).toMatch(/kept/i);
    expect(copy.toolLabel).toMatch(/subtract/i);
    expect(copy.note).toMatch(/Target − Tool/);
  });

  it("gives union/intersect their glyphs", () => {
    expect(operationCopy("union").glyph).toBe("+");
    expect(operationCopy("intersect").glyph).toBe("∩");
  });

  it("gives each operation a specific multi-lump opt-in note", () => {
    expect(operationCopy("union").disjointNote).toMatch(/don't touch/i);
    expect(operationCopy("subtract").disjointNote).toMatch(/sever/i);
    expect(operationCopy("intersect").disjointNote).toMatch(/region/i);
  });
});

describe("toolOptionsFor", () => {
  it("excludes the chosen target (a body can't fuse with itself)", () => {
    expect(toolOptionsFor(bodies, "x2").map((b) => b.baseFeatureId)).toEqual([
      "x1",
      "x3",
    ]);
  });
});

describe("canSubmitCombine", () => {
  it("needs a target, a tool, and the two to differ", () => {
    expect(
      canSubmitCombine({
        operation: "union",
        targetFeatureId: "x1",
        toolFeatureId: "x2",
        allowDisjoint: false,
      }),
    ).toBe(true);
    expect(
      canSubmitCombine({
        operation: "union",
        targetFeatureId: "",
        toolFeatureId: "x2",
        allowDisjoint: false,
      }),
    ).toBe(false);
    expect(
      canSubmitCombine({
        operation: "union",
        targetFeatureId: "x1",
        toolFeatureId: "",
        allowDisjoint: false,
      }),
    ).toBe(false);
    expect(
      canSubmitCombine({
        operation: "union",
        targetFeatureId: "x1",
        toolFeatureId: "x1",
        allowDisjoint: false,
      }),
    ).toBe(false);
  });
});

describe("buildCombineParams", () => {
  it("builds a union between the two named bodies", () => {
    expect(
      buildCombineParams({
        operation: "union",
        targetFeatureId: "x1",
        toolFeatureId: "x2",
        allowDisjoint: false,
      }),
    ).toEqual({
      operation: "union",
      target: { kind: "feature", feature_id: "x1" },
      tool: { kind: "feature", feature_id: "x2" },
      allow_disjoint: false,
    });
  });

  it("threads the multi-lump opt-in into allow_disjoint", () => {
    expect(
      buildCombineParams({
        operation: "union",
        targetFeatureId: "x1",
        toolFeatureId: "x2",
        allowDisjoint: true,
      })?.allow_disjoint,
    ).toBe(true);
    // The opt-in is meaningful for every operation, not just union.
    expect(
      buildCombineParams({
        operation: "subtract",
        targetFeatureId: "x1",
        toolFeatureId: "x2",
        allowDisjoint: true,
      })?.allow_disjoint,
    ).toBe(true);
  });

  it("carries the chosen operation (subtract keeps Target − Tool order)", () => {
    expect(
      buildCombineParams({
        operation: "subtract",
        targetFeatureId: "x1",
        toolFeatureId: "x2",
        allowDisjoint: false,
      }),
    ).toEqual({
      operation: "subtract",
      target: { kind: "feature", feature_id: "x1" },
      tool: { kind: "feature", feature_id: "x2" },
      allow_disjoint: false,
    });
    expect(
      buildCombineParams({
        operation: "intersect",
        targetFeatureId: "x1",
        toolFeatureId: "x2",
        allowDisjoint: false,
      })?.operation,
    ).toBe("intersect");
  });

  it("is null for an incomplete or self-referential form", () => {
    expect(
      buildCombineParams({
        operation: "union",
        targetFeatureId: "x1",
        toolFeatureId: "",
        allowDisjoint: false,
      }),
    ).toBeNull();
    expect(
      buildCombineParams({
        operation: "subtract",
        targetFeatureId: "x1",
        toolFeatureId: "x1",
        allowDisjoint: false,
      }),
    ).toBeNull();
  });
});
