import { describe, expect, it } from "vitest";

import type { EdgeSignature, ProjectedViewEdge } from "../api/drawings";
import {
  endpointHandlesForEdge,
  fitScale,
  sheetDimensions,
  standardLayout,
} from "./layout";

describe("sheetDimensions", () => {
  it("A4 landscape is 297×210 mm; portrait swaps", () => {
    expect(sheetDimensions("A4", "landscape")).toEqual({
      width: 297,
      height: 210,
    });
    expect(sheetDimensions("A4", "portrait")).toEqual({
      width: 210,
      height: 297,
    });
  });
});

describe("fitScale (auto-layout fit — WB-64 dogfooding fix)", () => {
  const a4 = sheetDimensions("A4", "landscape");

  it("keeps 1:1 for a part whose views fit their cells (the plate)", () => {
    expect(fitScale({ x: 40, y: 25, z: 10 }, a4, "1:1").value).toBe("1:1");
  });

  it("reduces a 258 mm bottle to 1:5 on A4 (1:1 and 1:2 overflow)", () => {
    expect(fitScale({ x: 120, y: 120, z: 258 }, a4, "1:1").value).toBe("1:5");
  });

  it("treats the user's picked scale as a ceiling, never upscaling", () => {
    // A tiny part at an explicit 1:10 stays 1:10 — fit only ever reduces.
    expect(fitScale({ x: 10, y: 10, z: 5 }, a4, "1:10").value).toBe("1:10");
  });

  it("respects an explicit magnification when it fits", () => {
    expect(fitScale({ x: 8, y: 8, z: 4 }, a4, "5:1").value).toBe("5:1");
  });

  it("falls back to the smallest option when nothing fits (never throws)", () => {
    expect(fitScale({ x: 5000, y: 5000, z: 5000 }, a4, "1:1").value).toBe(
      "1:10",
    );
  });

  it("a magnified choice that overflows steps DOWN through the options", () => {
    // 5:1 on a 100 mm part overflows; the fit walks down to what fits.
    const fitted = fitScale({ x: 100, y: 100, z: 50 }, a4, "5:1");
    expect(fitted.value).toBe("1:2");
  });

  it("pancake iso-height bound is honoured (review 2026-07-22 regression)", () => {
    // A flat, wide part whose ORTHO views all fit at 1:1 but whose iso view is
    // HEIGHT-dominated by the xy term: true iso height 0.8165·30 + 0.4082·109
    // ≈ 69.0 mm > the 63.4 mm A4 cell, so 1:1 must be rejected. The previous
    // 0.3 xy-coefficient accepted exactly this shape at 1:1 (its over-wide
    // 0.87 width bound sat just inside the old cell, masking nothing here).
    expect(fitScale({ x: 95, y: 14, z: 30 }, a4, "1:1").value).toBe("1:2");
  });

  it("portrait sheet swaps the cell aspect", () => {
    const portrait = sheetDimensions("A4", "portrait");
    // 210 wide → columns narrow to ~63.6 mm: a 90 mm-wide part no longer fits
    // its column at 1:1 even though it does on landscape.
    expect(fitScale({ x: 90, y: 5, z: 20 }, portrait, "1:1").value).toBe("1:2");
    expect(fitScale({ x: 90, y: 5, z: 20 }, a4, "1:1").value).toBe("1:1");
  });
});

describe("standardLayout (third-angle create-flow seed)", () => {
  it("places top ABOVE front and right to the RIGHT of front", () => {
    const dims = sheetDimensions("A4", "landscape");
    const anchors = standardLayout(dims);
    // Third-angle: top view sits above front (larger y in bottom-left origin).
    expect(anchors.top.y).toBeGreaterThan(anchors.front.y);
    expect(anchors.top.x).toBeCloseTo(anchors.front.x);
    // Right view sits to the right of front.
    expect(anchors.right.x).toBeGreaterThan(anchors.front.x);
    expect(anchors.right.y).toBeCloseTo(anchors.front.y);
    // Iso fills the free upper-right quadrant.
    expect(anchors.iso.x).toBeGreaterThan(anchors.front.x);
    expect(anchors.iso.y).toBeGreaterThan(anchors.front.y);
  });
});

const vec = (x: number, y: number, z: number) => ({ x, y, z });

describe("endpoint handles (start_is_end_a correspondence)", () => {
  const lineSig: EdgeSignature = {
    curve: "line",
    end_a: vec(0, 0, 0),
    end_b: vec(40, 0, 0),
    midpoint: vec(20, 0, 0),
    length_mm: 40,
    subshape_type: "edge",
  };
  // A straight edge whose canonical projected `start` (0,0) IS the model
  // `end_a` — the geometry service tells us so via `start_is_end_a: true`.
  const edge: ProjectedViewEdge = {
    primitive: "line",
    visible: true,
    start: { x_mm: 0, y_mm: 0 },
    end: { x_mm: 40, y_mm: 0 },
    midpoint: { x_mm: 20, y_mm: 0 },
    edge_role: "body",
    dimensionable: true,
    source_edge: lineSig,
    start_is_end_a: true,
  };

  it("maps start→end_a / end→end_b when start_is_end_a is true", () => {
    const handles = endpointHandlesForEdge(edge);
    expect(handles).not.toBeNull();
    if (!handles) return;
    // Returned in [start, end] order — the composed line's (x1,y1)/(x2,y2) order.
    expect(handles[0].projected).toEqual({ x: 0, y: 0 });
    expect(handles[0].endpoint).toBe("end_a");
    expect(handles[1].projected).toEqual({ x: 40, y: 0 });
    expect(handles[1].endpoint).toBe("end_b");
  });

  it("flips the correspondence when start_is_end_a is false", () => {
    // Same projected geometry, but now `start` (0,0) is the model `end_b`.
    const flipped = { ...edge, start_is_end_a: false };
    const handles = endpointHandlesForEdge(flipped);
    expect(handles).not.toBeNull();
    if (!handles) return;
    const byEnd = Object.fromEntries(
      handles.map((h) => [h.endpoint, h.projected]),
    );
    expect(byEnd.end_b).toEqual({ x: 0, y: 0 });
    expect(byEnd.end_a).toEqual({ x: 40, y: 0 });
  });

  it("returns null for a non-line / un-dimensionable edge", () => {
    const circle: ProjectedViewEdge = {
      primitive: "circle",
      visible: true,
      start: { x_mm: 25, y_mm: 0 },
      end: { x_mm: 25, y_mm: 0 },
      midpoint: { x_mm: 15, y_mm: 0 },
      center: { x_mm: 20, y_mm: 0 },
      radius: 5,
      edge_role: "body",
      dimensionable: true,
      source_edge: { ...lineSig, curve: "circle" },
      start_is_end_a: null,
    };
    expect(endpointHandlesForEdge(circle)).toBeNull();
    expect(
      endpointHandlesForEdge({ ...edge, dimensionable: false }),
    ).toBeNull();
  });

  it("returns null for a straight edge missing the correspondence (silhouette)", () => {
    // A dimensionable straight edge that carries no `start_is_end_a` (an
    // un-dimensionable silhouette / ambiguous source) offers no vertex pick.
    const noCorrespondence = { ...edge, start_is_end_a: null };
    expect(endpointHandlesForEdge(noCorrespondence)).toBeNull();
    const noSource = { ...edge, source_edge: null };
    expect(endpointHandlesForEdge(noSource)).toBeNull();
  });
});
