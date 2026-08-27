/**
 * The drop rule, tested against the SHAPES the wire actually carries — a
 * whole-feature `FeatureRef` (extrude → sketch), a named-face `SubshapeRef`
 * (hole → extrude) and a predicate selector that references nothing at all
 * (an all-edges fillet). Those three are the reason the rule is a generic
 * `feature_id` walk rather than a per-type table: a fillet with a picked-edge
 * selector DOES carry refs and one with `all_edges` does not, and no test that
 * only knows feature types can tell them apart.
 */
import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import {
  conflictMessage,
  featureReferenceIds,
  firstOrderConflict,
  movedOrder,
  nearestLegalIndex,
  repairLabel,
} from "./featureOrder";

function row(
  id: string,
  name: string,
  feature: FeatureResponse["feature"],
): FeatureResponse {
  return {
    id,
    name,
    part_id: "p1",
    order_index: 0,
    created_at: "2026-08-27T00:00:00Z",
    updated_at: "2026-08-27T00:00:00Z",
    rolled_back: false,
    feature,
  };
}

const sketch = row("f1", "Sketch1", {
  type: "sketch",
  version: 1,
  params: {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [],
    constraints: [],
  },
});

const extrude = row("f2", "Extrude1", {
  type: "extrude",
  version: 1,
  params: {
    profile: { kind: "feature", feature_id: "f1" },
    distance_mm: 20,
    operation: "add",
    direction: "normal",
    merge: true,
  },
});

const hole = row("f3", "Hole1", {
  type: "hole",
  version: 1,
  params: {
    face: {
      kind: "subshape",
      feature_id: "f2",
      subshape_type: "face",
      selector: {
        selector_version: 1,
        signature: {
          subshape_type: "face",
          surface: "plane",
          area_mm2: 1600,
          centroid: { x: 20, y: 20, z: 20 },
          normal: { x: 0, y: 0, z: 1 },
        },
      },
    },
    position: { x: 20, y: 20, z: 20 },
    diameter_mm: 8,
    depth: { kind: "through_all" },
  },
});

const fillet = row("f4", "Fillet1", {
  type: "fillet",
  version: 1,
  params: { edges: { kind: "all_edges" }, radius_mm: 1 },
});

const tree = [sketch, extrude, hole, fillet];

describe("featureReferenceIds", () => {
  it("finds a whole-feature ref (extrude → its profile sketch)", () => {
    expect(featureReferenceIds(extrude)).toEqual(["f1"]);
  });

  it("finds a NAMED-FACE ref nested under a selector (hole → extrude)", () => {
    expect(featureReferenceIds(hole)).toEqual(["f2"]);
  });

  it("reports nothing for a predicate selector — an all-edges fillet is free", () => {
    expect(featureReferenceIds(fillet)).toEqual([]);
  });

  it("finds every section of a loft, not just the first", () => {
    const loft = row("f9", "Loft1", {
      type: "loft",
      version: 1,
      params: {
        profiles: [
          { kind: "feature", feature_id: "f1" },
          { kind: "feature", feature_id: "f5" },
        ],
        operation: "add",
        merge: true,
      },
    });
    expect(featureReferenceIds(loft).sort()).toEqual(["f1", "f5"]);
  });
});

describe("firstOrderConflict", () => {
  it("accepts the tree as authored", () => {
    expect(firstOrderConflict(tree)).toBeNull();
  });

  it("accepts the fillet moving ABOVE the hole — it references nothing", () => {
    expect(firstOrderConflict(movedOrder(tree, 3, 2))).toBeNull();
  });

  it("refuses the hole moving above the extrude it is placed on", () => {
    const conflict = firstOrderConflict(movedOrder(tree, 2, 1));
    expect(conflict).toEqual({
      dependentId: "f3",
      dependentName: "Hole1",
      referenceId: "f2",
      referenceName: "Extrude1",
    });
  });

  it("refuses a SKETCH dragged below its own extrude — the same edge, other end", () => {
    const conflict = firstOrderConflict(movedOrder(tree, 0, 1));
    expect(conflict?.dependentName).toBe("Extrude1");
    expect(conflict?.referenceName).toBe("Sketch1");
  });

  it("names both features in one sentence", () => {
    const conflict = firstOrderConflict(movedOrder(tree, 2, 1));
    expect(conflict).not.toBeNull();
    expect(conflictMessage(conflict!)).toBe(
      "Hole1 is built on Extrude1, so Extrude1 has to stay above it.",
    );
  });
});

describe("movedOrder", () => {
  it("lifts and re-seats without dropping or duplicating a row", () => {
    const next = movedOrder(tree, 3, 0);
    expect(next.map((f) => f.id)).toEqual(["f4", "f1", "f2", "f3"]);
    expect(next).toHaveLength(tree.length);
  });

  it("leaves the source list untouched", () => {
    movedOrder(tree, 0, 3);
    expect(tree.map((f) => f.id)).toEqual(["f1", "f2", "f3", "f4"]);
  });
});

describe("nearestLegalIndex / repairLabel", () => {
  it("walks back to the first seat the tree would take", () => {
    // Hole (index 2) aimed at the very top: seats 0 and 1 are both above its
    // extrude, so the nearest legal seat is 2 — i.e. it never moved.
    expect(nearestLegalIndex(tree, 2, 0)).toBe(2);
  });

  it("offers the seat just under the reference when there is room", () => {
    // Order: Sketch, Extrude, Fillet, Hole — Hole aimed at 1 (above Extrude)
    // is refused, and the nearest legal seat is 2, right under the extrude.
    const swapped = movedOrder(tree, 3, 2);
    expect(swapped.map((f) => f.name)).toEqual([
      "Sketch1",
      "Extrude1",
      "Fillet1",
      "Hole1",
    ]);
    expect(nearestLegalIndex(swapped, 3, 1)).toBe(2);
    expect(repairLabel(swapped, 3, 2)).toBe("Move Hole1 after Extrude1");
  });

  it("names the top rather than a row number when the seat is 0", () => {
    expect(repairLabel(tree, 3, 0)).toBe("Move Fillet1 to the top");
  });
});
