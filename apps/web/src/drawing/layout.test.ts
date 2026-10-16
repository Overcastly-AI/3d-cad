import { describe, expect, it } from "vitest";

import { drawing } from "@loft/design";

import type { EdgeSignature, ProjectedViewEdge } from "../api/drawings";
import {
  AUTO_SCALE,
  SCALE_OPTIONS,
  boxExtents,
  chooseSheetSize,
  drawingArea,
  endpointHandlesForEdge,
  fitScale,
  fitStandardScale,
  proposeOrientation,
  reframePinnedCentre,
  sheetDimensions,
  sheetHeaderForNewSheet,
  sheetSizeLabel,
  sheetSizeOptions,
  standardLayout,
  standardViewFrames,
  standardViewsFit,
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

describe("sheetSizeOptions (the size picker's choices)", () => {
  it("offers every standard size, A4 first, ANSI last", () => {
    const values = sheetSizeOptions("landscape").map((o) => o.value);
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

  it("labels carry the mm extents (from SHEET_MM_LANDSCAPE, no drift)", () => {
    const a4 = sheetSizeOptions("landscape").find((o) => o.value === "A4");
    expect(a4?.label).toBe("A4 · 297 × 210 mm");
    const a3 = sheetSizeOptions("landscape").find((o) => o.value === "A3");
    expect(a3?.label).toBe("A3 · 420 × 297 mm");
  });

  it("states the PORTRAIT extents when portrait is the paper being made", () => {
    // REACH-3-FLOW P2: the picker used to read "297 × 210 mm" beside a proposal
    // about to create a 210 × 297 sheet — the wrong paper, at the one moment
    // the user is choosing paper.
    const a4 = sheetSizeOptions("portrait").find((o) => o.value === "A4");
    expect(a4?.label).toBe("A4 · 210 × 297 mm");
  });

  it("humanises the ANSI display name", () => {
    expect(sheetSizeLabel("A4")).toBe("A4");
    expect(sheetSizeLabel("ANSI_B")).toBe("ANSI B");
    const ansiB = sheetSizeOptions("landscape").find(
      (o) => o.value === "ANSI_B",
    );
    expect(ansiB?.label.startsWith("ANSI B ·")).toBe(true);
  });
});

describe("proposeOrientation (which paper this document argues for)", () => {
  /** The 40 x 40 x 150 mm column the REACH-3 specs draft — deliberately tall. */
  const COLUMN = { x: 40, y: 40, z: 150 };
  /** A 200 x 140 x 30 plate — wide, and the A3 size-picker spec's part. */
  const PLATE = { x: 200, y: 140, z: 30 };

  it("offers portrait to a tall part, at a strictly better scale", () => {
    const fit = proposeOrientation(COLUMN, "A4");
    expect(fit.proposed).toBe("portrait");
    expect(fit.scaleByOrientation).toEqual({
      landscape: "1:5",
      portrait: "1:2",
    });
  });

  it("keeps landscape for a wide part", () => {
    expect(proposeOrientation(PLATE, "A3").proposed).toBe("landscape");
  });

  it("breaks a tie for landscape — the shop default, so no surprise", () => {
    const cube = { x: 20, y: 20, z: 20 };
    const fit = proposeOrientation(cube, "A4");
    expect(fit.scaleByOrientation.landscape).toBe(
      fit.scaleByOrientation.portrait,
    );
    expect(fit.proposed).toBe("landscape");
  });
});

describe("sheetHeaderForNewSheet (the ONE header every create path uses)", () => {
  const fit = proposeOrientation({ x: 40, y: 40, z: 150 }, "A4");

  it("proposes the fitted orientation AND the scale it earns", () => {
    // The REACH-3-FLOW P1-1 case: this is what Sheet 1 is now born with, where
    // four call sites used to write `orientation: "landscape"` as a literal.
    const header = sheetHeaderForNewSheet({
      name: "Sheet 1",
      size: "A4",
      layout: "standard",
      fit,
      inherit: null,
    });
    expect(header.orientation).toBe("portrait");
    expect(header.scaleValue).toBe("1:2");
    expect(header.projection).toBe("third_angle");
  });

  it("inherits the convention from the sheet in hand", () => {
    const header = sheetHeaderForNewSheet({
      name: "Sheet 2",
      size: "A4",
      layout: "standard",
      fit,
      inherit: { projection: "first_angle" },
    });
    expect(header.projection).toBe("first_angle");
  });

  it("lets the user's override win outright, with the scale that follows", () => {
    const header = sheetHeaderForNewSheet({
      name: "Sheet 1",
      size: "A4",
      layout: "standard",
      fit,
      inherit: null,
      override: "landscape",
    });
    expect(header.orientation).toBe("landscape");
    expect(header.scaleValue).toBe("1:5");
  });

  it("keeps the default paper and promises NO scale for a lone-view sheet", () => {
    // A flat pattern draws the UNFOLDED blank, which the four-quadrant fit does
    // not model — proposing from it would promise a scale it cannot deliver.
    const header = sheetHeaderForNewSheet({
      name: "Sheet 1",
      size: "A4",
      layout: "lone",
      fit,
      inherit: null,
    });
    expect(header.orientation).toBe("landscape");
    expect(header.scaleValue).toBeNull();
  });

  it("promises no scale when the source could not be measured", () => {
    const header = sheetHeaderForNewSheet({
      name: "Sheet 1",
      size: "A4",
      layout: "standard",
      fit: null,
      inherit: null,
    });
    expect(header.orientation).toBe("landscape");
    expect(header.scaleValue).toBeNull();
  });
});

describe("reframePinnedCentre (a hand-placed view survives the flip)", () => {
  const landscape = sheetDimensions("A4", "landscape");
  const portrait = sheetDimensions("A4", "portrait");

  it("keeps a pin ON the paper when the paper narrows", () => {
    // 270 mm across is 91% of a landscape A4 and OFF a 210 mm-wide portrait one.
    const moved = reframePinnedCentre(
      { x_mm: 270, y_mm: 40 },
      landscape,
      portrait,
    );
    expect(moved.x_mm).toBeLessThan(portrait.width);
    expect(moved.y_mm).toBeLessThan(portrait.height);
  });

  it("preserves the composition — a title-block corner stays a corner", () => {
    const moved = reframePinnedCentre(
      { x_mm: 270, y_mm: 40 },
      landscape,
      portrait,
    );
    expect(moved.x_mm / portrait.width).toBeCloseTo(270 / landscape.width, 10);
    expect(moved.y_mm / portrait.height).toBeCloseTo(40 / landscape.height, 10);
  });

  it("is a no-op when the paper does not change", () => {
    expect(
      reframePinnedCentre({ x_mm: 100, y_mm: 50 }, landscape, landscape),
    ).toEqual({ x_mm: 100, y_mm: 50 });
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

describe("fitScale (the standard scale the views fit — BIKE2-DRAWING-SCALE)", () => {
  const a4 = sheetDimensions("A4", "landscape");

  it("keeps 1:1 under a 1:1 ceiling for a part that fits (the plate)", () => {
    expect(fitScale({ x: 40, y: 25, z: 10 }, a4, "1:1").value).toBe("1:1");
  });

  it("reduces a 258 mm bottle to 1:5 on A4 (1:2 is 307 mm tall)", () => {
    expect(fitScale({ x: 120, y: 120, z: 258 }, a4, "1:1").value).toBe("1:5");
  });

  it("treats a picked scale as a ceiling, never upscaling past it", () => {
    expect(fitScale({ x: 10, y: 10, z: 5 }, a4, "1:10").value).toBe("1:10");
  });

  it("respects an explicit magnification when it fits", () => {
    expect(fitScale({ x: 8, y: 8, z: 4 }, a4, "5:1").value).toBe("5:1");
  });

  it("a magnified choice that overflows steps DOWN through the options", () => {
    expect(fitScale({ x: 100, y: 100, z: 50 }, a4, "5:1").value).toBe("1:2");
  });

  it("reports when even 1:1000 overflows, and still answers 1:1000", () => {
    // 400 m long: 400 mm on the paper at 1:1000, wider than A4's 277 mm border.
    const fit = fitStandardScale({ x: 400000, y: 1000, z: 1000 }, a4, "1:1");
    expect(fit.option.value).toBe("1:1000");
    expect(fit.fits).toBe(false);
  });

  it("a bigger sheet earns a bigger scale (the WB-64 size-control payoff)", () => {
    const bottle = { x: 120, y: 120, z: 258 };
    expect(fitScale(bottle, a4, AUTO_SCALE).value).toBe("1:5");
    expect(
      fitScale(bottle, sheetDimensions("A2", "landscape"), AUTO_SCALE).value,
    ).toBe("1:2");
  });

  it("the SOLVED and SEEDED readings of the reference rig fit DIFFERENT scales (ASMDRAW-FIT-1b)", () => {
    // The arithmetic the assembly-fit e2e leans on, pinned here so a change to
    // the fit cannot quietly make that spec vacuous. Two 40x25x10 plates, the
    // second seeded 80 mm along x and then bolted flush onto the first:
    //   seeded roll-up  -> 120 x 25 x 10: at 2:1 the arrangement is 240 + 24
    //                      + 50 + 2·(0.7071·145) wide, past the 277 mm border
    //   solved compound ->  40 x 25 x 20: fits at 2:1
    const seeded = { x: 120, y: 25, z: 10 };
    const solved = { x: 40, y: 25, z: 20 };
    expect(fitScale(seeded, a4, AUTO_SCALE).value).toBe("1:1");
    expect(fitScale(solved, a4, AUTO_SCALE).value).toBe("2:1");
    // The e2e lays out on A3 under a 5:1 ceiling: the seeds stay 1:1, and the
    // whole band the solved pose is measured in (x 38..60, its best-fit
    // residual) fits 2:1 and never 5:1, so its expectation is exact.
    const a3 = sheetDimensions("A3", "landscape");
    expect(fitScale(seeded, a3, "5:1").value).toBe("1:1");
    for (const x of [38, 42.2, 60]) {
      expect(fitScale({ x, y: 30, z: 25 }, a3, "5:1").value).toBe("2:1");
    }
  });
});

describe("the standard-scale chooser (BIKE2-DRAWING-SCALE)", () => {
  const a4 = sheetDimensions("A4", "landscape");
  /** The round-2 bike: 1,622 x 100 x 911 mm. */
  const BIKE = { x: 1622, y: 100, z: 911 };

  it("puts the 1.6 m bike on A4 at 1:20", () => {
    // 1:10: front 162.2 + 24 + right 10 + iso 2·(0.7071·172.2) = 439 mm wide.
    // 1:20: 166 x 152 mm of geometry, inside the 277 x 190 mm border.
    expect(standardViewsFit(BIKE, a4, 1 / 10)).toBe(false);
    expect(fitStandardScale(BIKE, a4, AUTO_SCALE)).toMatchObject({
      option: { value: "1:20" },
      fits: true,
    });
    expect(proposeOrientation(BIKE, "A4").scaleByOrientation.landscape).toBe(
      "1:20",
    );
  });

  it("enlarges a 20 mm part to 2:1 (5:1 is 297 mm tall)", () => {
    const cube = { x: 20, y: 20, z: 20 };
    expect(standardViewsFit(cube, a4, 5)).toBe(false);
    expect(fitScale(cube, a4, AUTO_SCALE).value).toBe("2:1");
  });

  it("every view frame lands inside the border and off the title block", () => {
    // By hand at 1:20: front geometry 81.1 x 45.55 centred at x 106.05, so its
    // frame (5 mm pad, 13 mm below for the caption) spans x 60.51..151.61,
    // y 21.06..84.61 (y up from the paper's bottom edge).
    const frames = standardViewFrames(BIKE, a4, 1 / 20);
    expect(frames[0]!.minX).toBeCloseTo(60.509345, 6);
    expect(frames[0]!.maxY).toBeCloseTo(84.6062025, 6);
    const { border, titleBlock } = drawingArea(a4);
    for (const frame of frames) {
      expect(frame.minX).toBeGreaterThanOrEqual(border.minX);
      expect(frame.maxX).toBeLessThanOrEqual(border.maxX);
      expect(frame.minY).toBeGreaterThanOrEqual(border.minY);
      expect(frame.maxY).toBeLessThanOrEqual(border.maxY);
      expect(
        frame.maxX <= titleBlock.minX || frame.minY >= titleBlock.maxY,
      ).toBe(true);
    }
  });

  it("moves the arrangement off the title block as the composer does", () => {
    // The 20 mm cube at 2:1, centred, puts its right view at x 152.2..192.2
    // with its caption down to y 30.6: on the title block's corner (x >= 191,
    // y <= 44). Clearing it by 6 mm takes 19.4 mm up or 192.2 - 185 = 7.2 mm
    // left; left is smaller, so the right frame ends at 185 + 5 = 190.
    const frames = standardViewFrames({ x: 20, y: 20, z: 20 }, a4, 2);
    expect(frames[2]!.maxX).toBeCloseTo(190, 9);
    // The iso is the true-iso bound plus the frame: 0.7071·40·2 + 10 wide,
    // (0.8165·20 + 0.4082·40)·2 + 5 + 13 tall.
    expect(frames[3]!.maxX - frames[3]!.minX).toBeCloseTo(66.568, 9);
    expect(frames[3]!.maxY - frames[3]!.minY).toBeCloseTo(83.316, 9);
  });

  it("first angle mirrors the trio, and fits it by its own arrangement", () => {
    // First angle drops the top view BELOW the front: at 1:20 the bike's
    // geometry is 49.3 + 2.5 + 119.1 = 170.9 mm tall, the composer lifts it
    // only for the 9.7 mm caption band, and the top view's frame (13 mm below)
    // dips 3.3 mm under the border. So first angle draws it at 1:50.
    expect(
      fitStandardScale(BIKE, a4, AUTO_SCALE, "first_angle").option.value,
    ).toBe("1:50");
    const third = standardViewFrames(BIKE, a4, 1 / 20);
    const first = standardViewFrames(BIKE, a4, 1 / 20, "first_angle");
    // Right of the front in third angle, left of it in first angle.
    expect(third[2]!.minX).toBeGreaterThan(third[0]!.maxX);
    expect(first[2]!.maxX).toBeLessThan(first[0]!.minX);
  });

  it("grows the paper only when the size is not fixed and nothing fits", () => {
    const long = { x: 400000, y: 1000, z: 1000 };
    expect(chooseSheetSize(long, "A4", true)).toBe("A4");
    // 400 mm at 1:1000 plus its iso needs A1's 821 mm border.
    expect(chooseSheetSize(long, "A4", false)).toBe("A1");
    expect(chooseSheetSize(BIKE, "A4", false)).toBe("A4");
    expect(chooseSheetSize(long, "ANSI_A", false)).toBe("ANSI_D");
  });

  it("offers Auto plus the ISO 5455 scales, largest first", () => {
    expect(SCALE_OPTIONS.map((o) => o.value)).toEqual([
      "5:1",
      "2:1",
      "1:1",
      "1:2",
      "1:5",
      "1:10",
      "1:20",
      "1:50",
      "1:100",
      "1:200",
      "1:500",
      "1:1000",
    ]);
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
