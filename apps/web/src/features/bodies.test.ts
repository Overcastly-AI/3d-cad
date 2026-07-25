import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import { computeBodies, lumpBadgeLabel } from "./bodies";

function base(id: string, name: string): Omit<FeatureResponse, "feature"> {
  return {
    id,
    name,
    part_id: "p",
    order_index: 0,
    created_at: "2026-07-18T00:00:00Z",
    updated_at: "2026-07-18T00:00:00Z",
    rolled_back: false,
  };
}

function extrude(
  id: string,
  name: string,
  operation: "add" | "cut",
  merge: boolean,
): FeatureResponse {
  return {
    ...base(id, name),
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: "sk" },
        distance_mm: 10,
        operation,
        direction: "normal",
        merge,
      },
    },
  };
}

function union(
  id: string,
  name: string,
  targetId: string,
  toolId: string,
): FeatureResponse {
  return {
    ...base(id, name),
    feature: {
      type: "boolean",
      version: 1,
      params: {
        operation: "union",
        target: { kind: "feature", feature_id: targetId },
        tool: { kind: "feature", feature_id: toolId },
        allow_disjoint: false,
      },
    },
  };
}

function baseFlange(id: string, name: string, merge = true): FeatureResponse {
  return {
    ...base(id, name),
    feature: {
      type: "sheet_metal_base_flange",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: "sk" },
        thickness_mm: 2,
        bend_radius_mm: 3,
        k_factor: 0.44,
        direction: "normal",
        merge,
      },
    },
  };
}

function edgeFlange(id: string, name: string): FeatureResponse {
  return {
    ...base(id, name),
    feature: {
      type: "sheet_metal_edge_flange",
      version: 1,
      params: {
        edge: {
          kind: "subshape",
          feature_id: "bf",
          subshape_type: "edge",
          selector: {
            selector_version: 1,
            signature: {
              curve: "line",
              end_a: { x: 50, y: 0, z: 2 },
              end_b: { x: 50, y: 20, z: 2 },
              midpoint: { x: 50, y: 10, z: 2 },
              length_mm: 20,
              subshape_type: "edge",
            },
          },
        },
        flange_length_mm: 20,
        bend_angle_deg: 90,
      },
    },
  };
}

describe("computeBodies", () => {
  it("a base flange starts the sheet body; an edge flange modifies it", () => {
    const bodies = computeBodies([
      baseFlange("bf", "Base flange1"),
      edgeFlange("ef", "Edge flange1"),
    ]);
    expect(bodies.map((b) => b.baseFeatureId)).toEqual(["bf"]);
    expect(bodies[0]?.name).toBe("Base flange1");
    expect(bodies[0]?.featureType).toBe("sheet_metal_base_flange");
  });

  it("counts the first add as one body regardless of merge", () => {
    const bodies = computeBodies([extrude("x1", "Extrude1", "add", true)]);
    expect(bodies.map((b) => b.baseFeatureId)).toEqual(["x1"]);
    expect(bodies[0]?.ordinal).toBe(1);
    expect(bodies[0]?.name).toBe("Extrude1");
  });

  it("merges a second add into the active body (still one body)", () => {
    const bodies = computeBodies([
      extrude("x1", "Extrude1", "add", true),
      extrude("x2", "Extrude2", "add", true),
    ]);
    expect(bodies.map((b) => b.baseFeatureId)).toEqual(["x1"]);
  });

  it("a merge:false add starts a second body", () => {
    const bodies = computeBodies([
      extrude("x1", "Extrude1", "add", true),
      extrude("x2", "Extrude2", "add", false),
    ]);
    expect(bodies.map((b) => b.baseFeatureId)).toEqual(["x1", "x2"]);
    expect(bodies.map((b) => b.ordinal)).toEqual([1, 2]);
  });

  it("a cut never creates a body", () => {
    const bodies = computeBodies([
      extrude("x1", "Extrude1", "add", true),
      extrude("x2", "Cut1", "cut", true),
    ]);
    expect(bodies.map((b) => b.baseFeatureId)).toEqual(["x1"]);
  });

  it("a union consumes the tool body and keeps the target's identity", () => {
    const bodies = computeBodies([
      extrude("x1", "Extrude1", "add", true),
      extrude("x2", "Extrude2", "add", false),
      union("b1", "Combine1", "x1", "x2"),
    ]);
    expect(bodies.map((b) => b.baseFeatureId)).toEqual(["x1"]);
    expect(bodies[0]?.ordinal).toBe(1);
  });

  it("ignores rolled-back features", () => {
    const rolled = extrude("x2", "Extrude2", "add", false);
    const bodies = computeBodies([
      extrude("x1", "Extrude1", "add", true),
      { ...rolled, rolled_back: true },
    ]);
    expect(bodies.map((b) => b.baseFeatureId)).toEqual(["x1"]);
  });
});

describe("lumpBadgeLabel", () => {
  it("shows a multi-solid badge when a body has more than one lump", () => {
    expect(lumpBadgeLabel(2)).toBe("2 solids");
    expect(lumpBadgeLabel(5)).toBe("5 solids");
  });

  it("shows no badge for a single-lump body", () => {
    expect(lumpBadgeLabel(1)).toBeNull();
  });

  it("shows no badge when the lump count is unknown", () => {
    expect(lumpBadgeLabel(undefined)).toBeNull();
  });
});
