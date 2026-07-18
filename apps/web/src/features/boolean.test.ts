import { describe, expect, it } from "vitest";

import type { BodyInfo } from "./bodies";
import {
  buildCombineParams,
  canSubmitCombine,
  defaultCombineForm,
  toolOptionsFor,
} from "./boolean";

const bodies: BodyInfo[] = [
  { baseFeatureId: "x1", name: "Extrude1", featureType: "extrude", ordinal: 1 },
  { baseFeatureId: "x2", name: "Extrude2", featureType: "extrude", ordinal: 2 },
  { baseFeatureId: "x3", name: "Extrude3", featureType: "extrude", ordinal: 3 },
];

describe("defaultCombineForm", () => {
  it("seeds the first two bodies as target + tool", () => {
    expect(defaultCombineForm(bodies)).toEqual({
      targetFeatureId: "x1",
      toolFeatureId: "x2",
    });
  });

  it("leaves slots empty when fewer than two bodies exist", () => {
    expect(defaultCombineForm([bodies[0] as BodyInfo])).toEqual({
      targetFeatureId: "x1",
      toolFeatureId: "",
    });
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
      canSubmitCombine({ targetFeatureId: "x1", toolFeatureId: "x2" }),
    ).toBe(true);
    expect(canSubmitCombine({ targetFeatureId: "", toolFeatureId: "x2" })).toBe(
      false,
    );
    expect(canSubmitCombine({ targetFeatureId: "x1", toolFeatureId: "" })).toBe(
      false,
    );
    expect(
      canSubmitCombine({ targetFeatureId: "x1", toolFeatureId: "x1" }),
    ).toBe(false);
  });
});

describe("buildCombineParams", () => {
  it("builds a union between the two named bodies", () => {
    expect(
      buildCombineParams({ targetFeatureId: "x1", toolFeatureId: "x2" }),
    ).toEqual({
      operation: "union",
      target: { kind: "feature", feature_id: "x1" },
      tool: { kind: "feature", feature_id: "x2" },
    });
  });

  it("is null for an incomplete or self-referential form", () => {
    expect(
      buildCombineParams({ targetFeatureId: "x1", toolFeatureId: "" }),
    ).toBeNull();
    expect(
      buildCombineParams({ targetFeatureId: "x1", toolFeatureId: "x1" }),
    ).toBeNull();
  });
});
