import { describe, expect, it } from "vitest";

import type { EdgeSignature, ProjectedViewEdge } from "../api/drawings";
import {
  VIEW_GUTTER_MM,
  boundsAwareLayout,
  endpointHandlesForEdge,
  endpointProjected,
  formatScale,
  projectModelPoint,
  sheetDimensions,
  standardLayout,
  viewBounds,
  viewToSvgEdges,
} from "./layout";

const pt = (x: number, y: number) => ({ x_mm: x, y_mm: y });

const line = (
  a: [number, number],
  b: [number, number],
  visible: boolean,
): ProjectedViewEdge => ({
  primitive: "line",
  visible,
  start: pt(a[0], a[1]),
  end: pt(b[0], b[1]),
  midpoint: pt((a[0] + b[0]) / 2, (a[1] + b[1]) / 2),
  dimensionable: false,
});

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

describe("standardLayout (third-angle)", () => {
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

describe("boundsAwareLayout (third-angle, spaced by extent)", () => {
  // A square view of half-extent `h` centred at origin (projected mm).
  const squareBounds = (h: number) => ({
    min: { x: -h, y: -h },
    max: { x: h, y: h },
    center: { x: 0, y: 0 },
  });

  it("preserves third-angle relations", () => {
    const dims = sheetDimensions("A4", "landscape");
    const a = boundsAwareLayout(
      {
        front: squareBounds(20),
        top: squareBounds(20),
        right: squareBounds(20),
        iso: squareBounds(20),
      },
      dims,
    );
    expect(a.top.y).toBeGreaterThan(a.front.y); // top above front
    expect(a.top.x).toBeCloseTo(a.front.x); // shared X
    expect(a.right.x).toBeGreaterThan(a.front.x); // right of front
    expect(a.right.y).toBeCloseTo(a.front.y); // shared Y
  });

  it("spaces adjacent views so their boxes never overlap, even for a large part", () => {
    // A part far larger than the fixed-fraction gaps (~71/107 mm) used to allow.
    const dims = sheetDimensions("A4", "landscape");
    const hw = 90; // half-width 90 → 180 mm wide, dwarfs the sheet fractions
    const hh = 70;
    const b = {
      min: { x: -hw, y: -hh },
      max: { x: hw, y: hh },
      center: { x: 0, y: 0 },
    };
    const a = boundsAwareLayout({ front: b, top: b, right: b, iso: b }, dims);
    // front↔top are stacked in Y: the gap between their boxes == the gutter.
    expect(a.top.y - a.front.y).toBeCloseTo(hh + VIEW_GUTTER_MM + hh);
    // front↔right are side by side in X: gap == the gutter.
    expect(a.right.x - a.front.x).toBeCloseTo(hw + VIEW_GUTTER_MM + hw);
  });

  it("centres the arrangement on the sheet", () => {
    const dims = sheetDimensions("A4", "landscape");
    const a = boundsAwareLayout(
      {
        front: squareBounds(20),
        top: squareBounds(20),
        right: squareBounds(20),
        iso: squareBounds(20),
      },
      dims,
    );
    // The envelope of four equal 40mm squares is symmetric; its centre is the
    // midpoint of front/iso, which must land at the sheet centre.
    expect((a.front.x + a.iso.x) / 2).toBeCloseTo(dims.width / 2);
    expect((a.front.y + a.iso.y) / 2).toBeCloseTo(dims.height / 2);
  });

  it("falls back to the fixed layout when no view has geometry", () => {
    const dims = sheetDimensions("A4", "landscape");
    const a = boundsAwareLayout(
      { front: null, top: null, right: null, iso: null },
      dims,
    );
    expect(a).toEqual(standardLayout(dims));
  });
});

describe("viewBounds", () => {
  it("returns the tight box + centre, null when empty", () => {
    const edges = [line([0, 0], [40, 0], true), line([40, 0], [40, 10], true)];
    const b = viewBounds(edges);
    expect(b).not.toBeNull();
    expect(b?.min).toEqual({ x: 0, y: 0 });
    expect(b?.max).toEqual({ x: 40, y: 10 });
    expect(b?.center).toEqual({ x: 20, y: 5 });
    expect(viewBounds([])).toBeNull();
  });

  it("includes a circle's full radius box", () => {
    const circle: ProjectedViewEdge = {
      primitive: "circle",
      visible: true,
      start: pt(25, 20),
      end: pt(25, 20),
      midpoint: pt(15, 20),
      center: pt(20, 20),
      radius: 5,
      dimensionable: false,
    };
    const b = viewBounds([circle]);
    expect(b?.min).toEqual({ x: 15, y: 15 });
    expect(b?.max).toEqual({ x: 25, y: 25 });
  });
});

describe("viewToSvgEdges", () => {
  const sheetHeight = 210;
  const anchor = { x: 100, y: 100 };

  it("centres the view at the anchor and flips y (up→down)", () => {
    // A 40×10 rectangle centred at (20,5) in projected space.
    const edges = [
      line([0, 0], [40, 0], true),
      line([40, 0], [40, 10], true),
      line([40, 10], [0, 10], true),
      line([0, 10], [0, 0], true),
    ];
    const svg = viewToSvgEdges(edges, anchor, sheetHeight);
    expect(svg).toHaveLength(4);
    // The bottom-left projected corner (0,0) maps to (anchorX - 20, anchorSvgY + 5).
    const anchorSvgY = sheetHeight - anchor.y; // 110
    const first = svg[0];
    expect(first?.kind).toBe("line");
    if (first?.kind === "line") {
      expect(first.x1).toBeCloseTo(anchor.x - 20); // 80
      // projected y=0 is 5 below centre → svg y = anchorSvgY + 5.
      expect(first.y1).toBeCloseTo(anchorSvgY + 5); // 115
    }
  });

  it("maps a circle to an exact <circle> with the radius preserved", () => {
    const circle: ProjectedViewEdge = {
      primitive: "circle",
      visible: false,
      start: pt(25, 20),
      end: pt(25, 20),
      midpoint: pt(15, 20),
      center: pt(20, 20),
      radius: 5,
      dimensionable: false,
    };
    const svg = viewToSvgEdges([circle], anchor, sheetHeight);
    expect(svg[0]?.kind).toBe("circle");
    if (svg[0]?.kind === "circle") {
      expect(svg[0].r).toBe(5);
      expect(svg[0].visible).toBe(false);
    }
  });

  it("samples an arc into a polyline through its midpoint", () => {
    // Quarter arc, centre (0,0) r10, from (10,0) through (√50,√50) to (0,10).
    const arc: ProjectedViewEdge = {
      primitive: "arc",
      visible: true,
      start: pt(10, 0),
      end: pt(0, 10),
      midpoint: pt(Math.SQRT1_2 * 10, Math.SQRT1_2 * 10),
      center: pt(0, 0),
      radius: 10,
      dimensionable: false,
    };
    const svg = viewToSvgEdges([arc], anchor, sheetHeight);
    expect(svg[0]?.kind).toBe("polyline");
    if (svg[0]?.kind === "polyline") {
      expect(svg[0].points.length).toBeGreaterThan(4);
    }
  });
});

describe("formatScale", () => {
  it("renders numerator:denominator", () => {
    expect(formatScale({ numerator: 1, denominator: 1 })).toBe("1:1");
    expect(formatScale({ numerator: 1, denominator: 2 })).toBe("1:2");
    expect(formatScale({ numerator: 2, denominator: 1 })).toBe("2:1");
  });
});

const vec = (x: number, y: number, z: number) => ({ x, y, z });

describe("projectModelPoint", () => {
  it("maps a model point through each standard view's plane", () => {
    const p = vec(40, 25, 10);
    // top looks down +Z → (x, y); front looks down -Y → (x, z); right → (y, z).
    expect(projectModelPoint("top", p, 1)).toEqual({ x: 40, y: 25 });
    expect(projectModelPoint("front", p, 1)).toEqual({ x: 40, y: 10 });
    expect(projectModelPoint("right", p, 1)).toEqual({ x: 25, y: 10 });
  });

  it("applies the view scale factor", () => {
    expect(projectModelPoint("top", vec(40, 25, 0), 0.5)).toEqual({
      x: 20,
      y: 12.5,
    });
  });
});

describe("endpoint handles", () => {
  const lineSig: EdgeSignature = {
    curve: "line",
    end_a: vec(0, 0, 0),
    end_b: vec(40, 0, 0),
    midpoint: vec(20, 0, 0),
    length_mm: 40,
    subshape_type: "edge",
  };
  const edge: ProjectedViewEdge = {
    primitive: "line",
    visible: true,
    start: { x_mm: 0, y_mm: 0 },
    end: { x_mm: 40, y_mm: 0 },
    midpoint: { x_mm: 20, y_mm: 0 },
    dimensionable: true,
    source_edge: lineSig,
  };

  it("labels each projected end with its canonical model endpoint", () => {
    const handles = endpointHandlesForEdge(edge, "top", 1);
    expect(handles).not.toBeNull();
    if (!handles) return;
    const byEnd = Object.fromEntries(
      handles.map((h) => [h.endpoint, h.projected]),
    );
    expect(byEnd.end_a).toEqual({ x: 0, y: 0 });
    expect(byEnd.end_b).toEqual({ x: 40, y: 0 });
  });

  it("resolves a named endpoint back to its projected sheet point", () => {
    expect(endpointProjected(edge, "top", 1, "end_b")).toEqual({ x: 40, y: 0 });
    expect(endpointProjected(edge, "top", 1, "end_a")).toEqual({ x: 0, y: 0 });
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
    };
    expect(endpointHandlesForEdge(circle, "top", 1)).toBeNull();
    expect(
      endpointHandlesForEdge({ ...edge, dimensionable: false }, "top", 1),
    ).toBeNull();
  });
});
