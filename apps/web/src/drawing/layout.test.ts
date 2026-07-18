import { describe, expect, it } from "vitest";

import type { EdgeSignature, ProjectedViewEdge } from "../api/drawings";
import {
  endpointHandlesForEdge,
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
