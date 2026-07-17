import { describe, expect, it } from "vitest";

import type {
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

/** A straight-edge signature (the 40 mm bottom edge). */
const lineSig = (): EdgeSignature => ({
  curve: "line",
  end_a: vec(0, 0, 0),
  end_b: vec(40, 0, 0),
  midpoint: vec(20, 0, 0),
  length_mm: 40,
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
  });
});

describe("buildDimensionAnnotation", () => {
  it("draws a diameter across the circle with two arrowheads and an Ø label", () => {
    const a = buildDimensionAnnotation({
      type: "diameter",
      measured: ok(10, "mm"),
      edge: projectedCircle(),
      viewCenter: { x: 20, y: 12.5 },
      toSvg: identity,
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

  it("draws a linear dimension: two witness lines, one dimension line, two arrows", () => {
    const a = buildDimensionAnnotation({
      type: "linear",
      measured: ok(40, "mm"),
      edge: projectedLine(),
      viewCenter: { x: 20, y: 12.5 }, // above the edge → offsets below
      toSvg: identity,
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

  it("flags a foreshortened dimension with a ~ marker", () => {
    const a = buildDimensionAnnotation({
      type: "diameter",
      measured: ok(10, "mm", true),
      edge: projectedCircle(),
      viewCenter: { x: 20, y: 12.5 },
      toSvg: identity,
    });
    expect(a?.kind).toBe("measured");
    if (a?.kind !== "measured") return;
    expect(a.foreshortened).toBe(true);
    expect(a.text.label).toBe("~Ø10.000");
  });

  it("renders a measurement error as an honest marker, never a value", () => {
    const a = buildDimensionAnnotation({
      type: "diameter",
      measured: {
        foreshortened: false,
        error: { code: "subshape_unresolved", message: "gone" },
      },
      edge: projectedCircle(),
      viewCenter: { x: 20, y: 12.5 },
      toSvg: identity,
    });
    expect(a?.kind).toBe("error");
    if (a?.kind !== "error") return;
    expect(a.code).toBe("subshape_unresolved");
  });

  it("does not place an angular dimension in v1 (returns null)", () => {
    const a = buildDimensionAnnotation({
      type: "angular",
      measured: ok(90, "deg"),
      edge: projectedLine(),
      viewCenter: { x: 20, y: 12.5 },
      toSvg: identity,
    });
    expect(a).toBeNull();
  });
});
