import { describe, expect, it } from "vitest";

import type { FeatureTreeResponse } from "../api/parts";
import type { OverlayEdge, OverlayResult, Vec3 } from "../api/measure";
import {
  buildEvaluateTree,
  buildMeasureRequest,
  centreReading,
  centreReadingLabel,
  describePick,
  edgeCircle,
  measureEdgeLabel,
  minimumReadingLabel,
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
  can_undo: false,
  can_redo: false,
};

describe("buildEvaluateTree", () => {
  it("drops rolled-back features and carries id + version", () => {
    const tree = buildEvaluateTree(TREE);
    expect(tree.part_id).toBe(TREE.part_id);
    expect(tree.tree_version).toBe(7);
    expect(tree.linear_deflection).toBeGreaterThan(0);
    expect(tree.features.map((f) => f.id)).toEqual(["a", "b"]);
  });

  it("stops BEFORE a feature, for picking on the body that feature is built on", () => {
    // EDGE-RESOLVE-WARN-1: an edge a fillet rounds is not an edge of the tip
    // body any more, so re-picking it has to happen on the body before it.
    const before = buildEvaluateTree(TREE, "b");
    expect(before.features.map((f) => f.id)).toEqual(["a"]);
    expect(before.tree_version).toBe(7);
    // An id that is not in the tree changes nothing.
    expect(buildEvaluateTree(TREE, "zzz").features.map((f) => f.id)).toEqual([
      "a",
      "b",
    ]);
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
      faces: [],
    };
    // scene coords: (0,0,0) and (10,30,-20) → diagonal = hypot(10,30,20)
    expect(overlayBounds(overlay).diagonal).toBeCloseTo(
      Math.hypot(10, 30, 20),
      6,
    );
  });

  it("is zero for an empty overlay", () => {
    expect(overlayBounds({ vertices: [], edges: [], faces: [] }).diagonal).toBe(
      0,
    );
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
    ).toBe("Vertex 1, 2, 3 mm");
  });
});

// ---------------------------------------------------------------------------
// MEASURE-LABEL-PITCH-1 — circles, centre-to-centre, identity labels
// ---------------------------------------------------------------------------

const v = (x: number, y: number, z: number) => ({ x, y, z });

/**
 * A FULL circle as the kernel reports it: the seam stored twice
 * (`end_a == end_b`) and `midpoint` (curve parameter 0.5) diametrically
 * opposite — the shape `geometry.kernel.edges.edge_signature` emits.
 */
function circleEdge(
  cx: number,
  cy: number,
  z: number,
  r: number,
  seamAngle = 0,
): OverlayEdge {
  const at = (t: number) => v(cx + r * Math.cos(t), cy + r * Math.sin(t), z);
  const seam = at(seamAngle);
  return {
    kind: "circle",
    start: seam,
    end: seam,
    polyline: [0, 1, 2, 3, 4].map((i) => at(seamAngle + (i * Math.PI) / 2)),
    signature: {
      subshape_type: "edge",
      curve: "circle",
      end_a: seam,
      end_b: seam,
      midpoint: at(seamAngle + Math.PI),
      length_mm: 2 * Math.PI * r,
    },
  };
}

function lineEdge(a: Vec3, b: Vec3): OverlayEdge {
  return {
    kind: "line",
    start: a,
    end: b,
    polyline: [a, b],
    signature: {
      subshape_type: "edge",
      curve: "line",
      end_a: a,
      end_b: b,
      midpoint: v((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2),
      length_mm: Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z),
    },
  };
}

/** The audit's two Ø8 holes, pitch hypot(24, 7) = 25, plus a line and an arc. */
const HOLES: OverlayResult = {
  vertices: [v(-30, -15, 6)],
  faces: [],
  edges: [
    circleEdge(-12, -3.5, 6, 4, 0.7),
    circleEdge(12, 3.5, 6, 4, 2.1),
    lineEdge(v(-30, -15, 6), v(30, -15, 6)),
    // A quarter arc of R5 about (10, 10, 0): start (15,10), mid at 45deg, end (10,15).
    {
      kind: "circle",
      start: v(15, 10, 0),
      end: v(10, 15, 0),
      polyline: [v(15, 10, 0), v(10, 15, 0)],
      signature: {
        subshape_type: "edge",
        curve: "circle",
        end_a: v(10, 15, 0),
        end_b: v(15, 10, 0),
        midpoint: v(10 + 5 * Math.SQRT1_2, 10 + 5 * Math.SQRT1_2, 0),
        length_mm: (Math.PI * 5) / 2,
      },
    },
  ],
};

const edge = (index: number): MeasurePick => ({ kind: "edge", index });

describe("edgeCircle", () => {
  it("a full circle's centre is the seam/antipode midpoint, exactly", () => {
    const circle = edgeCircle(HOLES.edges[0] as OverlayEdge);
    expect(circle).not.toBeNull();
    expect(circle!.closed).toBe(true);
    expect(circle!.centre.x).toBeCloseTo(-12, 12);
    expect(circle!.centre.y).toBeCloseTo(-3.5, 12);
    expect(circle!.centre.z).toBe(6);
    expect(circle!.radius).toBeCloseTo(4, 12);
  });

  it("an arc's centre is the circumcentre of its three points", () => {
    const circle = edgeCircle(HOLES.edges[3] as OverlayEdge);
    expect(circle).not.toBeNull();
    expect(circle!.closed).toBe(false);
    expect(circle!.centre.x).toBeCloseTo(10, 12);
    expect(circle!.centre.y).toBeCloseTo(10, 12);
    expect(circle!.radius).toBeCloseTo(5, 12);
  });

  it("a line is not a circle", () => {
    expect(edgeCircle(HOLES.edges[2] as OverlayEdge)).toBeNull();
  });
});

describe("centreReading", () => {
  it("two holes read their PITCH, not the rim-to-rim minimum", () => {
    const reading = centreReading(edge(0), edge(1), HOLES);
    expect(reading).not.toBeNull();
    expect(reading!.kind).toBe("centre_centre");
    expect(reading!.distance).toBeCloseTo(25, 12);
    expect(reading!.delta.x).toBeCloseTo(24, 12);
    expect(reading!.delta.y).toBeCloseTo(7, 12);
    expect(reading!.delta.z).toBeCloseTo(0, 12);
    expect(centreReadingLabel(reading!)).toBe("Centre to centre");
  });

  it("keeps the pick order: delta is B - A", () => {
    const reading = centreReading(edge(1), edge(0), HOLES);
    expect(reading!.delta.x).toBeCloseTo(-24, 12);
  });

  it("a circle and a vertex read centre to point, named by order", () => {
    const vertex: MeasurePick = {
      kind: "vertex",
      index: 0,
      position: v(-30, -15, 6),
    };
    const forward = centreReading(edge(0), vertex, HOLES);
    expect(forward!.kind).toBe("centre_point");
    expect(forward!.distance).toBeCloseTo(Math.hypot(18, 11.5), 12);
    expect(centreReadingLabel(forward!)).toBe("Centre to point");
    const backward = centreReading(vertex, edge(0), HOLES);
    expect(centreReadingLabel(backward!)).toBe("Point to centre");
  });

  it("offers no centre reading without a circle, or against a line", () => {
    expect(centreReading(edge(2), edge(2), HOLES)).toBeNull();
    expect(centreReading(edge(0), edge(2), HOLES)).toBeNull();
    expect(centreReading(edge(0), edge(1), null)).toBeNull();
  });
});

describe("reading labels", () => {
  it("the kernel reading says MINIMUM whenever an edge is involved", () => {
    expect(minimumReadingLabel("point_point")).toBe("Distance");
    expect(minimumReadingLabel("point_edge")).toBe("Min distance");
    expect(minimumReadingLabel("edge_edge")).toBe("Min distance");
  });

  it("an edge pick names WHICH edge: diameter + centre, length + mid-span", () => {
    expect(describePick(edge(0), HOLES)).toBe(
      "Edge 1 · Ø8 circle, centre -12, -3.5, 6 mm",
    );
    expect(describePick(edge(1), HOLES)).toBe(
      "Edge 2 · Ø8 circle, centre 12, 3.5, 6 mm",
    );
    expect(describePick(edge(2), HOLES)).toBe(
      "Edge 3 · 60 mm line, mid 0, -15, 6 mm",
    );
    expect(describePick(edge(3), HOLES)).toBe(
      "Edge 4 · R5 arc, centre 10, 10, 0 mm",
    );
  });

  it("labels follow the document unit", () => {
    expect(describePick(edge(0), HOLES, "in")).toBe(
      "Edge 1 · Ø0.315 circle, centre -0.4724, -0.1378, 0.2362 in",
    );
  });

  it("the viewport mark's accessible name carries the same identity", () => {
    expect(measureEdgeLabel(0, HOLES.edges[0] as OverlayEdge)).toBe(
      "Edge 1, circle, diameter 8, centre at -12, -3.5, 6 millimetres",
    );
    expect(measureEdgeLabel(2, HOLES.edges[2] as OverlayEdge)).toBe(
      "Edge 3, line, centred at 0, -15, 6 millimetres",
    );
  });
});
