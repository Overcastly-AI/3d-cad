import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import { computeBodies, lumpBadgeLabel, partBodies } from "./bodies";

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

/**
 * THE BODIES THAT BUILT (FAILED-EXTRUDE-BODIES-GHOST-1).
 *
 * The panel used to list every body the TREE describes, and the tree does not
 * know what failed. A failed first extrude was still "Body 1" while Export said
 * nothing was built. The evaluate result's `bodies` is the kernel's own
 * last-good body set, the same state the exported file is written from, so the
 * panel now reads it.
 */
describe("partBodies", () => {
  const built = (...ids: string[]) =>
    ids.map((id) => ({ base_feature_id: id, lumps: 1 }));

  it("lists nothing when the only body-creating feature failed", () => {
    const tree = [extrude("x1", "Extrude1", "add", true)];
    // The negative control: the tree alone still claims a body.
    expect(computeBodies(tree)).toHaveLength(1);
    expect(partBodies(tree, built())).toEqual([]);
  });

  it("keeps the last good body when a later new body fails", () => {
    const tree = [
      extrude("x1", "Extrude1", "add", true),
      extrude("x2", "Extrude2", "add", false),
    ];
    expect(partBodies(tree, built("x1"))).toEqual([
      {
        baseFeatureId: "x1",
        name: "Extrude1",
        featureType: "extrude",
        ordinal: 1,
      },
    ]);
  });

  it("keeps both bodies when the union that would fuse them failed", () => {
    // The tree's partition applies the union whether or not it built, so a
    // filter over it would drop the tool body the file still contains.
    const tree = [
      extrude("x1", "Extrude1", "add", true),
      extrude("x2", "Extrude2", "add", false),
      union("u1", "Combine1", "x1", "x2"),
    ];
    expect(computeBodies(tree).map((b) => b.baseFeatureId)).toEqual(["x1"]);
    expect(
      partBodies(tree, built("x1", "x2")).map((b) => [b.name, b.ordinal]),
    ).toEqual([
      ["Extrude1", 1],
      ["Extrude2", 2],
    ]);
  });

  it("falls back to the tree before anything has been evaluated", () => {
    const tree = [extrude("x1", "Extrude1", "add", true)];
    expect(partBodies(tree, null)).toEqual(computeBodies(tree));
  });

  it("skips a body whose feature is no longer in the tree", () => {
    // A result from before a delete: the row it would name is gone.
    const tree = [extrude("x1", "Extrude1", "add", true)];
    expect(partBodies(tree, built("gone", "x1")).map((b) => b.name)).toEqual([
      "Extrude1",
    ]);
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
