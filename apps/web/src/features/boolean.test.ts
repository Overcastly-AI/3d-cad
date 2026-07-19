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
  it("seeds a union of the first two bodies as target + tool", () => {
    expect(defaultCombineForm(bodies)).toEqual({
      operation: "union",
      targetFeatureId: "x1",
      toolFeatureId: "x2",
    });
  });

  it("leaves slots empty when fewer than two bodies exist", () => {
    expect(defaultCombineForm([bodies[0] as BodyInfo])).toEqual({
      operation: "union",
      targetFeatureId: "x1",
      toolFeatureId: "",
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
      }),
    ).toBe(true);
    expect(
      canSubmitCombine({
        operation: "union",
        targetFeatureId: "",
        toolFeatureId: "x2",
      }),
    ).toBe(false);
    expect(
      canSubmitCombine({
        operation: "union",
        targetFeatureId: "x1",
        toolFeatureId: "",
      }),
    ).toBe(false);
    expect(
      canSubmitCombine({
        operation: "union",
        targetFeatureId: "x1",
        toolFeatureId: "x1",
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
      }),
    ).toEqual({
      operation: "union",
      target: { kind: "feature", feature_id: "x1" },
      tool: { kind: "feature", feature_id: "x2" },
      allow_disjoint: false,
    });
  });

  it("carries the chosen operation (subtract keeps Target − Tool order)", () => {
    expect(
      buildCombineParams({
        operation: "subtract",
        targetFeatureId: "x1",
        toolFeatureId: "x2",
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
      })?.operation,
    ).toBe("intersect");
  });

  it("is null for an incomplete or self-referential form", () => {
    expect(
      buildCombineParams({
        operation: "union",
        targetFeatureId: "x1",
        toolFeatureId: "",
      }),
    ).toBeNull();
    expect(
      buildCombineParams({
        operation: "subtract",
        targetFeatureId: "x1",
        toolFeatureId: "x1",
      }),
    ).toBeNull();
  });
});
