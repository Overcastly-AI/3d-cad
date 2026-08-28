import { describe, expect, it } from "vitest";

import { drawing } from "@loft/design";

import type { EdgeSignature, ProjectedViewEdge } from "../api/drawings";
import {
  SHEET_SIZE_OPTIONS,
  boxExtents,
  endpointHandlesForEdge,
  fitScale,
  sheetDimensions,
  sheetSizeLabel,
  standardLayout,
  vertexGrabMm,
  vertexPaintMm,
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

  it("A3 landscape is 420×297 mm (a bigger sheet than A4)", () => {
    expect(sheetDimensions("A3", "landscape")).toEqual({
      width: 420,
      height: 297,
    });
  });
});

describe("SHEET_SIZE_OPTIONS (the size picker's choices)", () => {
  it("offers every standard size, A4 first, ANSI last", () => {
    const values = SHEET_SIZE_OPTIONS.map((o) => o.value);
    expect(values).toEqual([
      "A4",
      "A3",
      "A2",
      "A1",
      "A0",
      "ANSI_A",
      "ANSI_B",
      "ANSI_C",
      "ANSI_D",
    ]);
  });

  it("labels carry the landscape mm extents (from SHEET_MM_LANDSCAPE, no drift)", () => {
    const a4 = SHEET_SIZE_OPTIONS.find((o) => o.value === "A4");
    expect(a4?.label).toBe("A4 · 297 × 210 mm");
    const a3 = SHEET_SIZE_OPTIONS.find((o) => o.value === "A3");
    expect(a3?.label).toBe("A3 · 420 × 297 mm");
  });

  it("humanises the ANSI display name", () => {
    expect(sheetSizeLabel("A4")).toBe("A4");
    expect(sheetSizeLabel("ANSI_B")).toBe("ANSI B");
    const ansiB = SHEET_SIZE_OPTIONS.find((o) => o.value === "ANSI_B");
    expect(ansiB?.label.startsWith("ANSI B ·")).toBe(true);
  });
});

describe("boxExtents (the one min/max -> side-lengths conversion)", () => {
  it("reads side lengths off a world-mm AABB, wherever it came from", () => {
    // The assembly route's answer for the reference rig: the solved compound
    // spans 40 x 25 x 20 with the second plate stacked on top of the first.
    expect(
      boxExtents({ min: { x: 0, y: 0, z: 0 }, max: { x: 40, y: 25, z: 20 } }),
    ).toEqual({ x: 40, y: 25, z: 20 });
  });

  it("is origin-independent — a box away from the origin has the same extents", () => {
    // A solved pose puts the compound wherever the mates put it; only the SIZE
    // fits a scale, so a translated box must read identically.
    expect(
      boxExtents({
        min: { x: -12.5, y: 4, z: -3 },
        max: { x: 27.5, y: 29, z: 17 },
      }),
    ).toEqual({ x: 40, y: 25, z: 20 });
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

  it("a bigger sheet earns a bigger scale (the WB-64 size-control payoff)", () => {
    // A 200×140×30 part overflows A4's quadrant cells until 1:5, but the larger
    // A3 sheet fits the same four views at 1:2 — the exact reason the size
    // picker exists (choosing A3 buys a far more usable scale for a big part).
    const big = { x: 200, y: 140, z: 30 };
    const onA4 = fitScale(big, sheetDimensions("A4", "landscape"), "1:1");
    const onA3 = fitScale(big, sheetDimensions("A3", "landscape"), "1:1");
    expect(onA4.value).toBe("1:5");
    expect(onA3.value).toBe("1:2");
    // The A3 scale is strictly larger than the A4 scale.
    expect(onA3.numerator / onA3.denominator).toBeGreaterThan(
      onA4.numerator / onA4.denominator,
    );
  });

  it("the SOLVED and SEEDED readings of the reference rig fit DIFFERENT scales (ASMDRAW-FIT-1b)", () => {
    // The arithmetic the assembly-fit e2e leans on, pinned here so a change to
    // the cell model cannot quietly make that spec vacuous.
    //
    // Two 40x25x10 plates, the second seeded 80 mm along x and then bolted
    // flush onto the first:
    //   seeded roll-up  -> 120 x 25 x 10  (front view 120 mm wide, cell is 98.9)
    //   solved compound ->  40 x 25 x 20  (everything inside its cell at 1:1)
    // So a client that folded the graph's own placements picks 1:2 where the
    // right answer is 1:1 — and from a 2:1 ceiling the two readings stay
    // distinct, which is what makes "the fit ran" and "the fit ran on the
    // solved pose" separately observable.
    const seeded = { x: 120, y: 25, z: 10 };
    const solved = { x: 40, y: 25, z: 20 };
    expect(fitScale(seeded, a4, "1:1").value).toBe("1:2");
    expect(fitScale(solved, a4, "1:1").value).toBe("1:1");
    expect(fitScale(seeded, a4, "2:1").value).toBe("1:2");
    expect(fitScale(solved, a4, "2:1").value).toBe("1:1");
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

describe("vertexGrabMm — the ends belong to the vertex, the middle to the edge", () => {
  it("keeps the full pick radius wherever it costs the edge nothing", () => {
    // 7.8 mm (3 x pickHitMm) is the break-even length; anything longer — i.e.
    // essentially all ordinary geometry — is unchanged by this rule.
    expect(vertexGrabMm(40)).toBeCloseTo(drawing.pickHitMm, 6);
    expect(vertexGrabMm(7.8)).toBeCloseTo(drawing.pickHitMm, 6);
  });

  it("leaves a central third of EVERY straight edge to the edge itself", () => {
    // The property, over lengths spanning three orders of magnitude rather
    // than the one case that prompted the fix: two ends can never eat more
    // than two thirds of the line between them.
    for (const len of [0.4, 1, 2, 4, 7.79, 12, 40, 400]) {
      const eaten = 2 * vertexGrabMm(len);
      expect(len - eaten).toBeGreaterThanOrEqual(len / 3 - 1e-9);
    }
  });

  it("gives the 4 mm rib edge a reachable interior it did not have", () => {
    // Measured on a 40 x 4 x 10 rib: the top view's short edge is 4 sheet mm
    // and a flat +/-2.6 mm grab ate 5.2 — more than the whole edge, so its
    // centre resolved to the vertex and aiming there armed point-to-point.
    expect(2 * drawing.pickHitMm).toBeGreaterThan(4);
    expect(2 * vertexGrabMm(4)).toBeCloseTo(8 / 3, 6);
    expect(2 * vertexGrabMm(4)).toBeLessThan(4);
  });

  it("budgets a mixed corner by the SHORT edge, which costs the long one nothing", () => {
    // Where a 4 mm and a 40 mm edge meet, the grab is the 4 mm edge's third;
    // the long edge simply keeps more of itself. Only the short one binds.
    expect(vertexGrabMm(Math.min(4, 40))).toBeCloseTo(4 / 3, 6);
  });

  it("falls back to the full radius for a vertex with no incident edge", () => {
    expect(vertexGrabMm(Number.POSITIVE_INFINITY)).toBe(drawing.pickHitMm);
    expect(vertexGrabMm(0)).toBe(drawing.pickHitMm);
    expect(vertexGrabMm(Number.NaN)).toBe(drawing.pickHitMm);
  });
});

describe("vertexPaintMm", () => {
  it("paints the usual square wherever the grab is unconstrained", () => {
    expect(vertexPaintMm(drawing.pickHitMm)).toBe(drawing.vertexHandleMm);
  });

  it("never paints a handle larger than the region that can be hit", () => {
    // A control drawn bigger than its hit box is the same defect class as one
    // with no box at all: what you see stops being what you can click.
    for (const len of [0.4, 1, 2, 4, 40]) {
      const grab = vertexGrabMm(len);
      expect(vertexPaintMm(grab)).toBeLessThanOrEqual(grab);
    }
  });
});
