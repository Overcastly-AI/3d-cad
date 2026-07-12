import { describe, expect, it } from "vitest";

import type { FeatureTreeResponse } from "../api/parts";
import type { OverlayResult } from "../api/measure";
import {
  buildEvaluateTree,
  buildMeasureRequest,
  describePick,
  formatAngleDeg,
  formatDeltaMm,
  formatDistanceMm,
  formatVec3Mm,
  needsTree,
  occtToScene,
  overlayBounds,
  pickToTarget,
  polylineMidpoint,
  polylineSegments,
  type MeasurePick,
} from "./geometry";

const SKETCH_FEATURE = {
  type: "sketch",
  version: 1,
  params: {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [],
    constraints: [],
  },
} as unknown as FeatureTreeResponse["features"][number]["feature"];

function feature(
  id: string,
  rolledBack: boolean,
): FeatureTreeResponse["features"][number] {
  return {
    id,
    name: id,
    part_id: "p",
    order_index: 0,
    rolled_back: rolledBack,
    created_at: "2026-07-11T00:00:00Z",
    updated_at: "2026-07-11T00:00:00Z",
    feature: SKETCH_FEATURE,
  };
}

const TREE: FeatureTreeResponse = {
  part_id: "11111111-1111-1111-1111-111111111111",
  tree_version: 7,
  rollback_feature_id: "a",
  features: [feature("a", false), feature("b", false), feature("c", true)],
};

describe("buildEvaluateTree", () => {
  it("drops rolled-back features and carries id + version", () => {
    const tree = buildEvaluateTree(TREE);
    expect(tree.part_id).toBe(TREE.part_id);
    expect(tree.tree_version).toBe(7);
    expect(tree.linear_deflection).toBeGreaterThan(0);
    expect(tree.features.map((f) => f.id)).toEqual(["a", "b"]);
  });
});

describe("occtToScene", () => {
  it("applies the Z-up → Y-up rotation (x, y, z) → (x, z, -y)", () => {
    expect(occtToScene({ x: 1, y: 2, z: 3 })).toEqual([1, 3, -2]);
  });
});

describe("polyline helpers", () => {
  it("emits scene-space segment pairs", () => {
    const segs = polylineSegments([
      { x: 0, y: 0, z: 0 },
      { x: 1, y: 0, z: 0 },
      { x: 1, y: 0, z: 2 },
    ]);
    // two segments → 12 floats
    expect(segs).toHaveLength(12);
    expect(Array.from(segs.slice(0, 6))).toEqual([0, 0, 0, 1, 0, 0]);
  });

  it("places a straight (2-point) edge's mark at the true midpoint, not the end vertex", () => {
    // Regression for BACKLOG #6: floor(2/2)=1 used to return the END vertex,
    // so every straight edge's mark landed on a corner and stole the click.
    expect(
      polylineMidpoint([
        { x: 0, y: 0, z: 0 },
        { x: 10, y: 20, z: 30 },
      ]),
    ).toEqual({ x: 5, y: 10, z: 15 });
  });

  it("takes the arc-length half point of a curved polyline", () => {
    expect(
      polylineMidpoint([
        { x: 0, y: 0, z: 0 },
        { x: 5, y: 0, z: 0 },
        { x: 10, y: 0, z: 0 },
      ]),
    ).toEqual({ x: 5, y: 0, z: 0 });
  });

  it("interpolates within the segment that straddles the half-length", () => {
    // Three unequal segments (2 + 4 + 2 = 8, half = 4) → the point sits at the
    // end of the first segment plus 2 into the second: exactly the geometric mid.
    expect(
      polylineMidpoint([
        { x: 0, y: 0, z: 0 },
        { x: 2, y: 0, z: 0 },
        { x: 6, y: 0, z: 0 },
        { x: 8, y: 0, z: 0 },
      ]),
    ).toEqual({ x: 4, y: 0, z: 0 });
  });
});

describe("overlayBounds", () => {
  it("measures the scene-space diagonal of the vertices", () => {
    const overlay: OverlayResult = {
      vertices: [
        { x: 0, y: 0, z: 0 },
        { x: 10, y: 20, z: 30 },
      ],
      edges: [],
    };
    // scene coords: (0,0,0) and (10,30,-20) → diagonal = hypot(10,30,20)
    expect(overlayBounds(overlay).diagonal).toBeCloseTo(
      Math.hypot(10, 30, 20),
      6,
    );
  });

  it("is zero for an empty overlay", () => {
    expect(overlayBounds({ vertices: [], edges: [] }).diagonal).toBe(0);
  });
});

describe("measure request", () => {
  const vertexA: MeasurePick = {
    kind: "vertex",
    index: 0,
    position: { x: 0, y: 0, z: 0 },
  };
  const vertexB: MeasurePick = {
    kind: "vertex",
    index: 6,
    position: { x: 10, y: 20, z: 30 },
  };
  const edge: MeasurePick = { kind: "edge", index: 4 };

  it("echoes a vertex's exact coordinates as a point target", () => {
    expect(pickToTarget(vertexB)).toEqual({
      kind: "point",
      position: { x: 10, y: 20, z: 30 },
    });
  });

  it("sends an edge by its overlay list index", () => {
    expect(pickToTarget(edge)).toEqual({ kind: "edge", index: 4 });
  });

  it("omits the tree for point-point", () => {
    const request = buildMeasureRequest(
      vertexA,
      vertexB,
      buildEvaluateTree(TREE),
    );
    expect(needsTree(vertexA, vertexB)).toBe(false);
    expect(request.tree).toBeUndefined();
  });

  it("attaches the tree when an edge is involved", () => {
    const request = buildMeasureRequest(vertexA, edge, buildEvaluateTree(TREE));
    expect(needsTree(vertexA, edge)).toBe(true);
    expect(request.tree?.tree_version).toBe(7);
  });
});

describe("formatting", () => {
  it("distance is fixed to two decimals", () => {
    expect(formatDistanceMm(Math.sqrt(1400))).toBe("37.42");
  });

  it("deltas carry an explicit sign", () => {
    expect(formatDeltaMm(10)).toBe("+10.00");
    expect(formatDeltaMm(-3)).toBe("-3.00");
  });

  it("angle is degrees or an em dash", () => {
    expect(formatAngleDeg(90)).toBe("90.0°");
    expect(formatAngleDeg(null)).toBe("—");
  });

  it("vec3 reads compact mm without -0", () => {
    expect(formatVec3Mm({ x: 10, y: -0, z: 30 })).toBe("10.00, 0.00, 30.00");
  });

  it("describes a pick for the readout", () => {
    expect(describePick({ kind: "edge", index: 4 })).toBe("Edge 5");
    expect(
      describePick({
        kind: "vertex",
        index: 0,
        position: { x: 1, y: 2, z: 3 },
      }),
    ).toContain("Vertex");
  });
});
