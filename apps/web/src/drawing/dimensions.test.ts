import { describe, expect, it } from "vitest";

import type {
  DimensionParams,
  EdgeSignature,
  MeasuredDimension,
  ProjectedViewEdge,
} from "../api/drawings";
import {
  buildDimensionAnnotation,
  dimensionEdgeSignature,
  edgeSignatureKey,
  edgeSignaturesMatch,
  findMatchingEdge,
  formatDimensionLabel,
} from "./dimensions";
import type { Point2D } from "./layout";

const vec = (x: number, y: number, z: number) => ({ x, y, z });

/** A minimal circular-edge signature (the Ø10 hole at (20,12.5)). */
const circleSig = (): EdgeSignature => ({
  curve: "circle",
  end_a: vec(15, 12.5, 0),
  end_b: vec(15, 12.5, 0),
  midpoint: vec(25, 12.5, 0),
  length_mm: Math.PI * 10,
  subshape_type: "edge",
});

/** The straight 40 mm bottom edge (end_a (0,0,0) → end_b (40,0,0)). */
const lineSig = (): EdgeSignature => ({
  curve: "line",
  end_a: vec(0, 0, 0),
  end_b: vec(40, 0, 0),
  midpoint: vec(20, 0, 0),
  length_mm: 40,
  subshape_type: "edge",
});

/** The straight 25 mm left edge (end_a (0,0,0) → end_b (0,25,0)). */
const vertSig = (): EdgeSignature => ({
  curve: "line",
  end_a: vec(0, 0, 0),
  end_b: vec(0, 25, 0),
  midpoint: vec(0, 12.5, 0),
  length_mm: 25,
  subshape_type: "edge",
});

const projectedLine = (): ProjectedViewEdge => ({
  primitive: "line",
  visible: true,
  start: { x_mm: 0, y_mm: 0 },
  end: { x_mm: 40, y_mm: 0 },
  midpoint: { x_mm: 20, y_mm: 0 },
  dimensionable: true,
  source_edge: lineSig(),
  // Projected `start` (0,0) is the model edge's `end_a` (0,0,0).
  start_is_end_a: true,
});

const projectedVert = (): ProjectedViewEdge => ({
  primitive: "line",
  visible: true,
  start: { x_mm: 0, y_mm: 0 },
  end: { x_mm: 0, y_mm: 25 },
  midpoint: { x_mm: 0, y_mm: 12.5 },
  dimensionable: true,
  source_edge: vertSig(),
  // Projected `start` (0,0) is the model edge's `end_a` (0,0,0).
  start_is_end_a: true,
});

const projectedCircle = (): ProjectedViewEdge => ({
  primitive: "circle",
  visible: true,
  start: { x_mm: 25, y_mm: 12.5 },
  end: { x_mm: 25, y_mm: 12.5 },
  midpoint: { x_mm: 15, y_mm: 12.5 },
  center: { x_mm: 20, y_mm: 12.5 },
  radius: 5,
  dimensionable: true,
  source_edge: circleSig(),
});

/** Identity transform — tests annotation geometry in projected mm directly. */
const identity = (p: Point2D): Point2D => p;

const ok = (
  value: number,
  unit: "mm" | "deg",
  foreshortened = false,
): MeasuredDimension => ({ value, unit, foreshortened });

/** Call the builder with the shared defaults (identity map, plate centre). */
function build(args: {
  dimension: DimensionParams;
  measured: MeasuredDimension;
  edges: ProjectedViewEdge[];
  viewCenter?: Point2D;
  obstacles?: { minX: number; minY: number; maxX: number; maxY: number }[];
}) {
  return buildDimensionAnnotation({
    dimension: args.dimension,
    measured: args.measured,
    edges: args.edges,
    viewCenter: args.viewCenter ?? { x: 20, y: 12.5 },
    toSvg: identity,
    obstacles: args.obstacles,
  });
}

describe("formatDimensionLabel", () => {
  it("prefixes each type and formats to a sensible precision", () => {
    expect(formatDimensionLabel("diameter", 10, "mm")).toBe("Ø10.000");
    expect(formatDimensionLabel("radius", 5, "mm")).toBe("R5.000");
    expect(formatDimensionLabel("linear", 40, "mm")).toBe("40.000");
    expect(formatDimensionLabel("angular", 90, "deg")).toBe("90.0°");
  });
});

describe("edge signature matching", () => {
  it("matches a signature to itself and not to a different edge", () => {
    expect(edgeSignaturesMatch(lineSig(), lineSig())).toBe(true);
    expect(edgeSignaturesMatch(lineSig(), circleSig())).toBe(false);
  });

  it("keys are rounding-stable across full-precision jitter", () => {
    const a = lineSig();
    const b = { ...lineSig(), length_mm: 40.00000001 };
    expect(edgeSignatureKey(a)).toBe(edgeSignatureKey(b));
  });

  it("finds the projected edge whose model source matches", () => {
    const edges = [projectedLine(), projectedCircle()];
    expect(findMatchingEdge(edges, circleSig())?.primitive).toBe("circle");
    expect(findMatchingEdge(edges, lineSig())?.primitive).toBe("line");
  });
});

describe("dimensionEdgeSignature", () => {
  it("extracts the referenced edge per type", () => {
    expect(
      dimensionEdgeSignature({ type: "diameter", edge: circleSig() })?.curve,
    ).toBe("circle");
    expect(
      dimensionEdgeSignature({
        type: "linear",
        measurement: { mode: "edge_length", edge: lineSig() },
      })?.curve,
    ).toBe("line");
    // A point-to-point linear points at its first endpoint's edge.
    expect(
      dimensionEdgeSignature({
        type: "linear",
        measurement: {
          mode: "point_to_point",
          a: { signature: lineSig(), endpoint: "end_b" },
          b: { signature: vertSig(), endpoint: "end_b" },
        },
      })?.curve,
    ).toBe("line");
    // An angular points at its first edge.
    expect(
      dimensionEdgeSignature({
        type: "angular",
        edge_a: lineSig(),
        edge_b: vertSig(),
      })?.length_mm,
    ).toBe(40);
  });
});

describe("buildDimensionAnnotation", () => {
  it("draws a diameter across the circle with two arrowheads and an Ø label", () => {
    const a = build({
      dimension: { type: "diameter", edge: circleSig() },
      measured: ok(10, "mm"),
      edges: [projectedCircle()],
    });
    expect(a?.kind).toBe("measured");
    if (a?.kind !== "measured") return;
    expect(a.text.label).toBe("Ø10.000");
    expect(a.arrows).toHaveLength(2);
    expect(a.lines).toHaveLength(1);
    // The dimension line spans the full diameter through the centre.
    expect(a.lines[0]?.x1).toBeCloseTo(15);
    expect(a.lines[0]?.x2).toBeCloseTo(25);
  });

  it("draws a linear edge-length: two witness lines, one dimension line, two arrows", () => {
    const a = build({
      dimension: {
        type: "linear",
        measurement: { mode: "edge_length", edge: lineSig() },
      },
      measured: ok(40, "mm"),
      edges: [projectedLine()],
    });
    expect(a?.kind).toBe("measured");
    if (a?.kind !== "measured") return;
    expect(a.text.label).toBe("40.000");
    expect(a.arrows).toHaveLength(2);
    expect(a.lines).toHaveLength(3);
    expect(a.lines.filter((l) => l.role === "extension")).toHaveLength(2);
    expect(a.lines.filter((l) => l.role === "dimension")).toHaveLength(1);
    // The view centre is above the edge, so the dimension line sits below (y<0).
    const dim = a.lines.find((l) => l.role === "dimension");
    expect(dim?.y1).toBeLessThan(0);
  });

  it("stamps the diameter value CLEAR of the circle (halo never masks the arc)", () => {
    const a = build({
      dimension: { type: "diameter", edge: circleSig() },
      measured: ok(10, "mm"),
      edges: [projectedCircle()],
    });
    if (a?.kind !== "measured") throw new Error("expected a measured diameter");
    // The value sits beyond the arc (|x - cx| > radius), so its opaque paper
    // halo lands on empty paper and the circle renders whole (frontend-QA P2).
    expect(Math.abs(a.text.x - 20)).toBeGreaterThan(5);
  });

  it("flips a linear dimension away from a neighbouring view it would overlap", () => {
    const dimension: DimensionParams = {
      type: "linear",
      measurement: { mode: "edge_length", edge: lineSig() },
    };
    // viewCenter above the edge → the conventional outboard side is BELOW (y<0).
    const obstacle = { minX: -50, minY: -30, maxX: 90, maxY: -1 };
    const flipped = build({
      dimension,
      measured: ok(40, "mm"),
      edges: [projectedLine()],
      obstacles: [obstacle],
    });
    if (flipped?.kind !== "measured") throw new Error("expected measured");
    const dim = flipped.lines.find((l) => l.role === "dimension");
    // With the outboard side blocked, the dimension line flips ABOVE (y>0).
    expect(dim?.y1).toBeGreaterThan(0);
    // …and with no obstacle it keeps the conventional outboard (below) side.
    const normal = build({
      dimension,
      measured: ok(40, "mm"),
      edges: [projectedLine()],
    });
    if (normal?.kind !== "measured") throw new Error("expected measured");
    expect(normal.lines.find((l) => l.role === "dimension")?.y1).toBeLessThan(
      0,
    );
  });

  it("flags a foreshortened dimension with a ~ marker", () => {
    const a = build({
      dimension: { type: "diameter", edge: circleSig() },
      measured: ok(10, "mm", true),
      edges: [projectedCircle()],
    });
    expect(a?.kind).toBe("measured");
    if (a?.kind !== "measured") return;
    expect(a.foreshortened).toBe(true);
    expect(a.text.label).toBe("~Ø10.000");
  });

  it("renders a measurement error as an honest marker, never a value", () => {
    const a = build({
      dimension: { type: "diameter", edge: circleSig() },
      measured: {
        foreshortened: false,
        error: { code: "subshape_unresolved", message: "gone" },
      },
      edges: [projectedCircle()],
    });
    expect(a?.kind).toBe("error");
    if (a?.kind !== "error") return;
    expect(a.code).toBe("subshape_unresolved");
  });

  // --- angular: an arc swept between two straight edges (was null in v1) ------
  it("places an angular dimension as an arc between two edges with the degree value", () => {
    const a = build({
      dimension: { type: "angular", edge_a: lineSig(), edge_b: vertSig() },
      measured: ok(90, "deg"),
      edges: [projectedLine(), projectedVert()],
    });
    expect(a?.kind).toBe("measured");
    if (a?.kind !== "measured") return;
    expect(a.text.label).toBe("90.0°");
    // Two arrowheads at the arc ends.
    expect(a.arrows).toHaveLength(2);
    // A sampled arc (many dimension segments) plus the two witness lines.
    const dims = a.lines.filter((l) => l.role === "dimension");
    const ext = a.lines.filter((l) => l.role === "extension");
    expect(dims.length).toBeGreaterThan(3);
    expect(ext).toHaveLength(2);
    // The arc points lie at the drafting radius (13 mm) from the shared vertex
    // (0,0) — every sampled point ~13 mm out.
    for (const l of dims) {
      expect(Math.hypot(l.x1, l.y1)).toBeCloseTo(13, 4);
    }
  });

  it("returns null for an angular between parallel edges (no apparent vertex)", () => {
    const parallel: ProjectedViewEdge = {
      primitive: "line",
      visible: true,
      start: { x_mm: 0, y_mm: 10 },
      end: { x_mm: 40, y_mm: 10 },
      midpoint: { x_mm: 20, y_mm: 10 },
      dimensionable: true,
      source_edge: {
        curve: "line",
        end_a: vec(0, 10, 0),
        end_b: vec(40, 10, 0),
        midpoint: vec(20, 10, 0),
        length_mm: 40,
        subshape_type: "edge",
      },
    };
    const a = build({
      dimension: {
        type: "angular",
        edge_a: lineSig(),
        edge_b: parallel.source_edge as EdgeSignature,
      },
      measured: ok(0, "deg"),
      edges: [projectedLine(), parallel],
    });
    expect(a).toBeNull();
  });

  // --- point-to-point linear: a distance between two named vertices (was null) -
  it("places a point-to-point linear between two projected endpoints", () => {
    const a = build({
      dimension: {
        type: "linear",
        measurement: {
          mode: "point_to_point",
          a: { signature: lineSig(), endpoint: "end_b" }, // (40,0,0) → (40,0)
          b: { signature: vertSig(), endpoint: "end_b" }, // (0,25,0) → (0,25)
        },
      },
      // sqrt(40^2 + 25^2) = 47.16990566…
      measured: ok(47.16990566, "mm"),
      edges: [projectedLine(), projectedVert()],
    });
    expect(a?.kind).toBe("measured");
    if (a?.kind !== "measured") return;
    expect(a.text.label).toBe("47.170");
    expect(a.arrows).toHaveLength(2);
    expect(a.lines.filter((l) => l.role === "extension")).toHaveLength(2);
    expect(a.lines.filter((l) => l.role === "dimension")).toHaveLength(1);
    // The dimension line runs (offset) between the two projected corners
    // (40,0) and (0,25): its span matches the point-to-point distance.
    const dim = a.lines.find((l) => l.role === "dimension");
    if (!dim) throw new Error("expected a dimension line");
    expect(Math.hypot(dim.x2 - dim.x1, dim.y2 - dim.y1)).toBeCloseTo(
      Math.hypot(40, 25),
      4,
    );
  });

  it("returns null for a point-to-point whose second edge is absent from the view", () => {
    const a = build({
      dimension: {
        type: "linear",
        measurement: {
          mode: "point_to_point",
          a: { signature: lineSig(), endpoint: "end_b" },
          b: { signature: vertSig(), endpoint: "end_b" },
        },
      },
      measured: ok(47.16990566, "mm"),
      edges: [projectedLine()], // vertSig edge not present
    });
    expect(a).toBeNull();
  });
});
