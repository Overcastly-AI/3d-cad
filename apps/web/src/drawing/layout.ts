/**
 * Drawing-sheet client helpers — the small surface the browser still owns after
 * the DE-1c placement cutover. PLACEMENT (view anchoring, edge y-flip, arc
 * sampling, dimension drafting) moved server-side into the composed sheet
 * (`geometry.drawings.compose`), so the transforms this file used to carry are
 * gone. What remains is what the CLIENT still needs, none of it placement:
 *
 *  - the standard-view vocabulary (order + captions),
 *  - the create-flow layout (`sheetDimensions` + `standardLayout`) that seeds the
 *    persisted view positions when the sheet is first laid out,
 *  - the scale picker options and the fit that chooses a standard scale (and,
 *    when the size is not fixed, a sheet size) for the standard views, and
 *  - the PICK types + endpoint correspondence the interactive layer reads off the
 *    neutral `ProjectedViewEdge` list (design §C) — positions are supplied by the
 *    composed geometry; this only resolves the canonical end_a/end_b labels.
 */
import { drawing } from "@loft/design";

import type {
  BoundingBox,
  ComposedEdge,
  EdgeSignature,
  ProjectedPoint,
  ProjectedViewEdge,
  SheetResponse,
  ViewProjection,
} from "../api/drawings";

/** Outline role of a composed edge (sheet-metal.md §6): a `body` cut/object edge
 * or a `bend` flat-pattern fold line (styled as a distinct dashed-blue stroke). */
export type EdgeRole = ComposedEdge["edge_role"];

/** The four standard views, in the canonical creation + render order. */
export const STANDARD_VIEWS: readonly ViewProjection[] = [
  "front",
  "top",
  "right",
  "iso",
];

/** Human labels for a projection (the stamped caption under each view).
 *  `flat_pattern` (sheet-metal.md §7) renders the unfold's flat blank — cut
 *  outline as `edge_role="body"`, fold lines as `edge_role="bend"` — plus the
 *  bend-table annotation (DrawingSheet.tsx). */
export const VIEW_LABEL: Record<ViewProjection, string> = {
  front: "Front",
  top: "Top",
  right: "Right",
  iso: "Isometric",
  flat_pattern: "Flat Pattern",
  section: "Section A-A",
  // The house set (HOUSE-DRAWINGS): the composer places these itself.
  plan: "Floor Plan",
  elevation_front: "Front Elevation",
  elevation_back: "Back Elevation",
  elevation_left: "Left Elevation",
  elevation_right: "Right Elevation",
  materials: "Materials List",
};

type SheetSize = SheetResponse["size"];
type Orientation = SheetResponse["orientation"];
type Projection = SheetResponse["projection"];

/** ISO / ANSI sheet dimensions in millimetres, given LANDSCAPE (w ≥ h). */
const SHEET_MM_LANDSCAPE: Record<SheetSize, readonly [number, number]> = {
  A4: [297, 210],
  A3: [420, 297],
  A2: [594, 420],
  A1: [841, 594],
  A0: [1189, 841],
  ANSI_A: [279.4, 215.9],
  ANSI_B: [431.8, 279.4],
  ANSI_C: [558.8, 431.8],
  ANSI_D: [863.6, 558.8],
};

/** The terse display name for a size — "A4" as-is, "ANSI_B" → "ANSI B" (the
 *  form the title block stamps and the post-layout readout shows). */
export function sheetSizeLabel(size: SheetSize): string {
  return size.startsWith("ANSI_") ? `ANSI ${size.slice(5)}` : size;
}

/**
 * The standard sheet SIZES the auto-layout picker offers, in the same order the
 * dimension table declares them (A4 first — the default — up through A0, then
 * the ANSI series). Each label carries the mm extents of the paper the layout
 * will ACTUALLY make, so an engineer can see at a glance how much room a bigger
 * sheet buys: the WB-64 finding was a 258 mm part that fits A4 only at a tiny
 * 1:5, where a larger sheet earns a far more usable scale (the fit-scale half
 * already reduces to the sheet; this lets the sheet itself be chosen).
 *
 * Orientation-aware because the create flow now PROPOSES an orientation
 * (REACH-3-FLOW): a picker reading "A4 · 297 × 210 mm" beside a proposal that
 * is about to make a 210 × 297 sheet states the wrong paper at the exact moment
 * the user is choosing it. Derived from {@link sheetDimensions} — the same
 * reading the layout uses — so the label can never drift from the sheet.
 */
export function sheetSizeOptions(
  orientation: Orientation,
): readonly { value: SheetSize; label: string }[] {
  return (Object.keys(SHEET_MM_LANDSCAPE) as SheetSize[]).map((size) => {
    const { width, height } = sheetDimensions(size, orientation);
    return {
      value: size,
      label: `${sheetSizeLabel(size)} · ${width} × ${height} mm`,
    };
  });
}

export interface SheetDims {
  /** Sheet width in mm (the SVG viewBox width). */
  width: number;
  /** Sheet height in mm (the SVG viewBox height). */
  height: number;
}

/** The sheet's mm dimensions for its size + orientation. */
export function sheetDimensions(
  size: SheetSize,
  orientation: Orientation,
): SheetDims {
  const [long, short] = SHEET_MM_LANDSCAPE[size];
  return orientation === "portrait"
    ? { width: short, height: long }
    : { width: long, height: short };
}

export interface Anchor {
  /** View-centre X in sheet mm (origin bottom-left, y-UP). */
  x: number;
  /** View-centre Y in sheet mm (origin bottom-left, y-UP). */
  y: number;
}

/**
 * The standard third-angle placement seed used ONLY when a sheet is first laid
 * out: front is the primary; the top view sits ABOVE it and the right view to
 * its RIGHT (the US third-angle convention), with the isometric filling the free
 * upper-right quadrant. Returned as view-CENTRE anchors in sheet mm (origin
 * bottom-left) and persisted as each view's stored position; the SERVER's
 * bounds-aware composer then re-derives the final on-sheet placement from the
 * projected extents, so this only has to be a sane initial spread.
 */
export function standardLayout(
  dims: SheetDims,
): Record<ViewProjection, Anchor> {
  const leftX = dims.width * 0.32;
  const rightX = dims.width * 0.68;
  const bottomY = dims.height * 0.36;
  const topY = dims.height * 0.7;
  return {
    front: { x: leftX, y: bottomY },
    top: { x: leftX, y: topY },
    right: { x: rightX, y: bottomY },
    iso: { x: rightX, y: topY },
    // A flat-pattern view is not part of the standard third-angle seed; it is
    // centred as a lone-view placeholder so the map stays total. Its real
    // placement + bend-table render is the next frontend slice (sheet-metal.md §7).
    flat_pattern: { x: dims.width / 2, y: dims.height / 2 },
    // A section view (drawings-section.md) is likewise a lone centred view, not part
    // of the third-angle seed; the on-screen crosshatch is export-only in v1 (§5), so
    // the DOM sheet renders its edges + cut-face outline here and the hatch ports in a
    // fast-follow. Centred placeholder keeps the map total.
    section: { x: dims.width / 2, y: dims.height / 2 },
    // The house set's views are laid out by the composer (a plan alone, the
    // elevations as a grid, the materials list top-left); centred seeds.
    ...Object.fromEntries(
      HOUSE_VIEWS.map((view) => [
        view,
        { x: dims.width / 2, y: dims.height / 2 },
      ]),
    ),
  } as Record<ViewProjection, Anchor>;
}

/** The house set's views (HOUSE-DRAWINGS), in the order the set lays them out. */
export const HOUSE_VIEWS: readonly ViewProjection[] = [
  "plan",
  "elevation_front",
  "elevation_back",
  "elevation_left",
  "elevation_right",
  "materials",
];

export interface Point2D {
  x: number;
  y: number;
}

const p2 = (p: ProjectedPoint): Point2D => ({ x: p.x_mm, y: p.y_mm });

/**
 * Pick metadata carried alongside a placed SVG primitive so the sheet can make a
 * dimensionable edge interactive: whether a dimension may attach here (design
 * §3.3), the MODEL edge it would name, and the projected primitive kind (which
 * gates the valid dimension types — a circle offers diameter/radius, a line
 * offers linear). Sourced from the aligned evaluate `ProjectedViewEdge`.
 */
export interface EdgePickInfo {
  dimensionable: boolean;
  sourceEdge: EdgeSignature | null;
  edgePrimitive: ProjectedViewEdge["primitive"];
}

/**
 * An SVG-ready primitive in final sheet coordinates (mm, y-down, top-left), fused
 * with its pick metadata. Its GEOMETRY comes from the server-composed sheet (the
 * client applies no transform); the pick fields come from the aligned evaluate
 * edge. This is the shape the interactive edge layer draws + hit-tests.
 */
export type SvgEdge = (
  | {
      kind: "line";
      x1: number;
      y1: number;
      x2: number;
      y2: number;
      visible: boolean;
    }
  | { kind: "circle"; cx: number; cy: number; r: number; visible: boolean }
  | { kind: "polyline"; points: Point2D[]; visible: boolean }
) &
  EdgePickInfo & {
    /** Outline role — a `bend` edge draws as the dashed-blue fold stroke; every
     * standard/HLR edge is `body` (sheet-metal.md §6). */
    edgeRole: EdgeRole;
  };

// --- straight-edge endpoint correspondence (model end_a/end_b ↔ projected) ---
//
// A point-to-point witness line needs to know WHICH projected endpoint of a
// straight edge is the model edge's canonical `end_a` (vs `end_b`). The wire
// format canonicalises `start`/`end` lexicographically, which would drop that
// correspondence — so the geometry service ships it explicitly on every
// dimensionable straight edge as `start_is_end_a` (project.py): true means the
// projected `start` point IS `end_a` (false → `end`). We read that bool instead
// of re-deriving the view frame + projection here (the kernel owns projection;
// the client never re-runs it — CLAUDE.md DRY / service-boundary rule).

/** One endpoint of a straight edge: its projected sheet point + canonical label.
 * The interactive layer maps `projected` to final SVG space through the aligned
 * COMPOSED line's endpoints (start→(x1,y1), end→(x2,y2)); this order matches the
 * [start, end] order the handles are returned in. */
export interface EndpointHandle {
  /** Projected (view-plane mm) position — the raw evaluate `start`/`end` point. */
  projected: Point2D;
  /** Which canonical model endpoint this is (design §3.3 point-to-point ref). */
  endpoint: "end_a" | "end_b";
}

/**
 * The two endpoint handles of a dimensionable STRAIGHT projected edge, each
 * tagged with the canonical `end_a`/`end_b` label the backend measures against
 * (design §3.3), returned in [start, end] order. The correspondence comes
 * straight from the wire's `start_is_end_a`: true → the projected `start` point
 * is `end_a` (and `end` is `end_b`), false → the reverse. This is the SINGLE
 * mapping the pick affordance reads, so an authored endpoint names the exact
 * vertex the user clicked. Null unless the edge is a straight, dimensionable edge
 * that actually carries the correspondence (source_edge != null &&
 * start_is_end_a != null) — a circle/arc/polyline or an un-dimensionable
 * silhouette carries neither and offers no vertex pick.
 */
export function endpointHandlesForEdge(
  edge: ProjectedViewEdge,
): [EndpointHandle, EndpointHandle] | null {
  if (
    edge.primitive !== "line" ||
    !edge.dimensionable ||
    edge.source_edge == null ||
    edge.start_is_end_a == null
  ) {
    return null;
  }
  const startIsA = edge.start_is_end_a;
  return [
    { projected: p2(edge.start), endpoint: startIsA ? "end_a" : "end_b" },
    { projected: p2(edge.end), endpoint: startIsA ? "end_b" : "end_a" },
  ];
}

// --- the vertex/edge hit budget on a straight edge ---------------------------
//
// A vertex handle's grab is painted AFTER the edge band it sits on, so whatever
// it claims, it claims OUT OF the edge. A flat +/-`pickHitMm` square therefore
// took 5.2 sheet-mm off every straight line no matter how long the line was,
// and any edge shorter than that had no reachable interior at all: aiming at a
// 4 mm rib edge to dimension it armed the point-to-point pick instead, with
// nothing on screen to say why. The wrong tool, silently, is worse than an
// inert click. (It reads as a small-parts problem and is not one — the budget
// is in SHEET mm, so at 1:5 the same 5.2 mm is 26 mm of the model.)
//
// The rule: **the ends belong to the vertex, the middle belongs to the edge.**
// A vertex may claim at most a third of the shortest straight edge it
// terminates, so the two ends of the shortest edge can never take more than
// two thirds of it and a central third always survives — a guarantee derived
// from the geometry rather than a constant that happens to work at one scale.

/** Share of a straight edge one of its endpoint handles may claim. A third,
 * so the two ends leave the edge its middle third at every length and scale. */
export const VERTEX_EDGE_SHARE = 1 / 3;

/**
 * Half-side (sheet mm) of a vertex handle's transparent grab, given the length
 * of the SHORTEST straight edge terminating at it. Full `pickHitMm` wherever
 * that costs the edge nothing (any edge from 7.8 mm up, i.e. essentially all
 * ordinary geometry), and proportional below it.
 *
 * A corner where a short and a long edge meet is budgeted by the SHORT one:
 * a 2.6 mm grab and a reachable 4 mm edge cannot both exist in the same place,
 * and the smaller grab costs the long edge nothing.
 */
export function vertexGrabMm(shortestIncidentMm: number): number {
  if (!Number.isFinite(shortestIncidentMm) || shortestIncidentMm <= 0) {
    return drawing.pickHitMm;
  }
  return Math.min(drawing.pickHitMm, shortestIncidentMm * VERTEX_EDGE_SHARE);
}

/** Half-side (sheet mm) of the DRAWN handle square for a given grab. Clamped to
 * the grab so the painted affordance is never larger than the region that can
 * be hit — a control that looks bigger than it is, is the same defect class as
 * a control with no box at all (CLAUDE.md, "an SVG stroke is not a hit box"). */
export function vertexPaintMm(grabMm: number): number {
  return Math.min(drawing.vertexHandleMm, grabMm);
}

/**
 * The scale picker's "let the sheet choose" value, and its default. "Lay out
 * standard views" then picks the largest standard scale whose views fit the
 * sheet (see {@link fitScale}), enlarging a small part as Fusion and SolidWorks
 * do when they open a drawing, instead of drawing a 20 mm part at a fixed 1:1.
 * A scale the user picks instead is a ceiling: the fit still reduces from it.
 */
export const AUTO_SCALE = "auto";

/**
 * The standard scales (ISO 5455), largest first: the enlargements 5:1 and 2:1,
 * full size, then the 1-2-5 reductions down to 1:1000. A drawing scale is
 * always one of these. A 1.6 m bike on A4 lands on 1:20 rather than running
 * off the paper at 1:10, the old smallest choice (BIKE2-DRAWING-SCALE).
 */
export const SCALE_OPTIONS: readonly {
  value: string;
  label: string;
  numerator: number;
  denominator: number;
}[] = [
  { value: "5:1", label: "5:1", numerator: 5, denominator: 1 },
  { value: "2:1", label: "2:1", numerator: 2, denominator: 1 },
  { value: "1:1", label: "1:1", numerator: 1, denominator: 1 },
  { value: "1:2", label: "1:2", numerator: 1, denominator: 2 },
  { value: "1:5", label: "1:5", numerator: 1, denominator: 5 },
  { value: "1:10", label: "1:10", numerator: 1, denominator: 10 },
  { value: "1:20", label: "1:20", numerator: 1, denominator: 20 },
  { value: "1:50", label: "1:50", numerator: 1, denominator: 50 },
  { value: "1:100", label: "1:100", numerator: 1, denominator: 100 },
  { value: "1:200", label: "1:200", numerator: 1, denominator: 200 },
  { value: "1:500", label: "1:500", numerator: 1, denominator: 500 },
  { value: "1:1000", label: "1:1000", numerator: 1, denominator: 1000 },
];

/** Model-space bbox extents (mm) along the world axes. */
export interface ModelExtents {
  x: number;
  y: number;
  z: number;
}

/**
 * The side lengths of a world-mm AABB — the ONE conversion between what the
 * server reports (min/max corners) and what {@link fitScale} reads.
 *
 * Shared on purpose: a part reads its box off `evaluate`'s mass properties and
 * an assembly off `GET /assemblies/{id}/extents`, and both are the same
 * generated `BoundingBox`. Two hand-rolled `max.x - min.x` triples are how the
 * assembly branch came to be forgotten in the first place (ASMDRAW-FIT-1b).
 */
export function boxExtents(box: BoundingBox): ModelExtents {
  return {
    x: box.max.x - box.min.x,
    y: box.max.y - box.min.y,
    z: box.max.z - box.min.z,
  };
}

// The sheet the composer draws on, mirrored from `geometry.drawings.layout` so
// the fit predicts where the server will actually put each view.
/** Border inset from the paper edge (server SHEET_MARGIN_MM). */
const SHEET_MARGIN_MM = 10;
/** Title block, bottom-right inside the border (server _TITLE_BLOCK_W/_H). */
const TITLE_BLOCK_W_MM = 96;
const TITLE_BLOCK_H_MM = 34;
/** Clear space between adjacent views (server VIEW_GUTTER_MM). */
const VIEW_GUTTER_MM = 24;
/** Least clearance between a view's ink and the title block (server
 * MIN_VIEW_CLEARANCE_MM, applied by `_title_block_shift`). */
const MIN_VIEW_CLEARANCE_MM = 6;
/** The caption band the server keeps inside the border below a view
 * (_VIEW_CAPTION_BAND_MM: label baseline 8 mm + half its 3.4 mm cap). */
const CAPTION_BAND_MM = 8 + 3.4 / 2;
/** Below a view, its frame reaches the caption baseline (8 mm under the
 * geometry) plus the pad: the frame the sheet draws round geometry + label. */
const CAPTION_BASELINE_MM = 8;

// EXACT true-isometric projection coefficients of the SERVER's iso frame
// (geometry.drawings.project: N = normalize(−1,−1,1), X = normalize(Z×N)):
// world x → (0.7071, 0.4082), y → (−0.7071, 0.4082), z → (0, 0.8165), so an
// axis-aligned box projects to exactly w = 0.7071·(x+y),
// h = 0.8165·z + 0.4082·(x+y). Any body inside the box projects inside that.
const ISO_W_XY = 0.7071;
const ISO_H_Z = 0.8165;
const ISO_H_XY = 0.4082;

/** A sheet rectangle, y-UP from the bottom-left corner (sheet mm). */
export interface SheetRect {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

/**
 * Where the composer will put the four standard views of a part this size, at
 * this scale, and the frame the sheet draws round each one.
 *
 * A mirror of the server's `bounds_aware_layout`: each view's half extents from
 * the model box (front x·z, top x·y, right y·z, the true-iso bound), front at
 * the origin, top and right one gutter away (mirrored for first angle), the
 * iso in the free upper-right corner, the whole arrangement centred on the
 * paper and lifted only as far as its captions need. Every real view is no
 * bigger than its box estimate, so the frames returned here bound the drawn
 * ones. A frame is the geometry plus the placement pad, and below it the
 * caption baseline plus the pad.
 */
export function standardViewFrames(
  extents: ModelExtents,
  dims: SheetDims,
  ratio: number,
  projection: Projection = "third_angle",
): SheetRect[] {
  const s = ratio / 2;
  const f = { x: extents.x * s, y: extents.z * s };
  const t = { x: extents.x * s, y: extents.y * s };
  const r = { x: extents.y * s, y: extents.z * s };
  const i = {
    x: ISO_W_XY * (extents.x + extents.y) * s,
    y: (ISO_H_Z * extents.z + ISO_H_XY * (extents.x + extents.y)) * s,
  };
  const g = VIEW_GUTTER_MM;
  const sign = projection === "third_angle" ? 1 : -1;
  const views = [
    { at: { x: 0, y: 0 }, half: f },
    { at: { x: 0, y: sign * (f.y + g + t.y) }, half: t },
    { at: { x: sign * (f.x + g + r.x), y: 0 }, half: r },
    {
      at: { x: Math.max(f.x, t.x) + g + i.x, y: Math.max(f.y, r.y) + g + i.y },
      half: i,
    },
  ];
  const minX = Math.min(...views.map((v) => v.at.x - v.half.x));
  const maxX = Math.max(...views.map((v) => v.at.x + v.half.x));
  const minY = Math.min(...views.map((v) => v.at.y - v.half.y));
  const maxY = Math.max(...views.map((v) => v.at.y + v.half.y));
  let dx = dims.width / 2 - (minX + maxX) / 2;
  let dy = dims.height / 2 - (minY + maxY) / 2;
  // The server's `_fit_shift`: lift the arrangement just clear of the bottom
  // border with its captions, when it fits at all.
  const lo = minY + dy - CAPTION_BAND_MM;
  const hi = maxY + dy;
  const loBound = SHEET_MARGIN_MM;
  const hiBound = dims.height - SHEET_MARGIN_MM;
  if (hi - lo <= hiBound - loBound) {
    if (lo < loBound) dy += loBound - lo;
    else if (hi > hiBound) dy += hiBound - hi;
  }
  // The server's `_title_block_shift`: move up or left (the smaller move that
  // stays inside the border) until no view's ink, caption included, comes
  // within MIN_VIEW_CLEARANCE_MM of the title block.
  const ink = views.map((v) => ({
    minX: v.at.x + dx - v.half.x,
    maxX: v.at.x + dx + v.half.x,
    minY: v.at.y + dy - v.half.y - CAPTION_BAND_MM,
    maxY: v.at.y + dy + v.half.y,
  }));
  const blockLeft =
    dims.width - SHEET_MARGIN_MM - TITLE_BLOCK_W_MM - MIN_VIEW_CLEARANCE_MM;
  const blockTop = SHEET_MARGIN_MM + TITLE_BLOCK_H_MM + MIN_VIEW_CLEARANCE_MM;
  const near = ink.filter((r) => r.maxX > blockLeft && r.minY < blockTop);
  if (near.length > 0) {
    const up = blockTop - Math.min(...near.map((r) => r.minY));
    const left = Math.max(...near.map((r) => r.maxX)) - blockLeft;
    const fitsUp = Math.max(...ink.map((r) => r.maxY)) + up <= hiBound;
    const fitsLeft =
      Math.min(...ink.map((r) => r.minX)) - left >= SHEET_MARGIN_MM;
    if (fitsUp && (!fitsLeft || up <= left)) dy += up;
    else if (fitsLeft) dx -= left;
  }
  const pad = drawing.placementPadMm;
  return views.map((v) => ({
    minX: v.at.x + dx - v.half.x - pad,
    maxX: v.at.x + dx + v.half.x + pad,
    minY: v.at.y + dy - v.half.y - CAPTION_BASELINE_MM - pad,
    maxY: v.at.y + dy + v.half.y + pad,
  }));
}

/** The drawing area: inside the border, and the title block it must clear. */
export function drawingArea(dims: SheetDims): {
  border: SheetRect;
  titleBlock: SheetRect;
} {
  const right = dims.width - SHEET_MARGIN_MM;
  return {
    border: {
      minX: SHEET_MARGIN_MM,
      minY: SHEET_MARGIN_MM,
      maxX: right,
      maxY: dims.height - SHEET_MARGIN_MM,
    },
    titleBlock: {
      minX: right - TITLE_BLOCK_W_MM,
      minY: SHEET_MARGIN_MM,
      maxX: right,
      maxY: SHEET_MARGIN_MM + TITLE_BLOCK_H_MM,
    },
  };
}

/** True when the standard views at `ratio` sit inside the border, clear of the
 * title block. */
export function standardViewsFit(
  extents: ModelExtents,
  dims: SheetDims,
  ratio: number,
  projection: Projection = "third_angle",
): boolean {
  const { border, titleBlock } = drawingArea(dims);
  return standardViewFrames(extents, dims, ratio, projection).every(
    (frame) =>
      frame.minX >= border.minX &&
      frame.maxX <= border.maxX &&
      frame.minY >= border.minY &&
      frame.maxY <= border.maxY &&
      (frame.maxX <= titleBlock.minX || frame.minY >= titleBlock.maxY),
  );
}

type ScaleOption = (typeof SCALE_OPTIONS)[number];

const scaleRatio = (o: { numerator: number; denominator: number }) =>
  o.numerator / o.denominator;

/** The fitted scale, and whether the views actually fit at it. */
export interface ScaleFit {
  option: ScaleOption;
  /** False when even the smallest scale overflows: the sheet is too small, and
   * the composer's `off_sheet` check reports it in the check strip. */
  fits: boolean;
}

/**
 * The largest standard scale at which the four standard views fit the sheet's
 * drawing area ({@link standardViewsFit}), never above `chosenValue`: Auto
 * ({@link AUTO_SCALE}) may enlarge up to 5:1, an explicit pick is a ceiling.
 * This is how Fusion and SolidWorks default a new drawing's scale: the biggest
 * standard scale that fits the sheet. When nothing fits, the smallest scale,
 * with `fits: false`.
 */
export function fitStandardScale(
  extents: ModelExtents,
  dims: SheetDims,
  chosenValue: string,
  projection: Projection = "third_angle",
): ScaleFit {
  const chosen = SCALE_OPTIONS.find((o) => o.value === chosenValue);
  const ceiling = chosen ? scaleRatio(chosen) : Infinity;
  const candidates = SCALE_OPTIONS.filter((o) => scaleRatio(o) <= ceiling);
  for (const option of candidates) {
    if (standardViewsFit(extents, dims, scaleRatio(option), projection)) {
      return { option, fits: true };
    }
  }
  const smallest = SCALE_OPTIONS[SCALE_OPTIONS.length - 1]!;
  return { option: candidates[candidates.length - 1] ?? smallest, fits: false };
}

/** {@link fitStandardScale}'s scale alone. */
export function fitScale(
  extents: ModelExtents,
  dims: SheetDims,
  chosenValue: string,
  projection: Projection = "third_angle",
): ScaleOption {
  return fitStandardScale(extents, dims, chosenValue, projection).option;
}

/** The paper series a sheet size belongs to, smallest first. A size that is
 * not fixed only ever grows within its own series. */
const SIZE_SERIES: readonly (readonly SheetSize[])[] = [
  ["A4", "A3", "A2", "A1", "A0"],
  ["ANSI_A", "ANSI_B", "ANSI_C", "ANSI_D"],
];

/**
 * The paper size the next layout makes. A size the user fixed is kept, whether
 * or not the views fit it (they get the check strip's warning). Otherwise the
 * smallest size in the same series, starting at `size`, on which the standard
 * views fit at a standard scale in either orientation — in practice `size`
 * itself, since the scales reach 1:1000; a bigger sheet only when nothing fits.
 */
export function chooseSheetSize(
  extents: ModelExtents,
  size: SheetSize,
  sizeFixed: boolean,
  chosenValue: string = AUTO_SCALE,
  projection: Projection = "third_angle",
): SheetSize {
  if (sizeFixed) return size;
  const series = SIZE_SERIES.find((sizes) => sizes.includes(size)) ?? [size];
  for (const candidate of series.slice(series.indexOf(size))) {
    const fits = (["landscape", "portrait"] as const).some(
      (orientation) =>
        fitStandardScale(
          extents,
          sheetDimensions(candidate, orientation),
          chosenValue,
          projection,
        ).fits,
    );
    if (fits) return candidate;
  }
  return size;
}

// --- the orientation proposal, and the ONE header every new sheet is born with

/**
 * What each paper orientation buys THIS document, and which one its own extents
 * therefore argue for.
 */
export interface OrientationFit {
  /** Fitted scale label per orientation ("1:2" / "1:5"). */
  scaleByOrientation: Record<Orientation, string>;
  /** Whether the standard views fit that orientation at all (at its smallest
   * scale they may still overflow — the composer then reports `off_sheet`). */
  fitsByOrientation: Record<Orientation, boolean>;
  /** The orientation that fits the document largest (landscape wins a tie — the
   * shop default, so a document with no preference gets no surprise). */
  proposed: Orientation;
}

/**
 * The orientation proposal for a document on a given paper size. Both
 * orientations are fitted with the SAME {@link fitStandardScale} the layout
 * action uses, under the same ceiling (Auto by default), so the scale the
 * header cell quotes is the scale the next "Lay out" delivers.
 */
export function proposeOrientation(
  extents: ModelExtents,
  size: SheetSize,
  chosenValue: string = AUTO_SCALE,
  projection: Projection = "third_angle",
): OrientationFit {
  const fit = (orientation: Orientation) =>
    fitStandardScale(
      extents,
      sheetDimensions(size, orientation),
      chosenValue,
      projection,
    );
  const landscape = fit("landscape");
  const portrait = fit("portrait");
  // A fitting orientation beats an overflowing one; then the larger scale.
  const better =
    portrait.fits !== landscape.fits
      ? portrait.fits
      : scaleRatio(portrait.option) > scaleRatio(landscape.option);
  return {
    scaleByOrientation: {
      landscape: landscape.option.value,
      portrait: portrait.option.value,
    },
    fitsByOrientation: { landscape: landscape.fits, portrait: portrait.fits },
    proposed: better ? "portrait" : "landscape",
  };
}

/**
 * Which shape of drawing a new sheet is being born for. `standard` is the four
 * standard views {@link fitScale} models; `lone` is a single centred view (a
 * flat pattern, a section).
 */
export type SheetLayoutKind = "standard" | "lone";

/** The header a `SheetCreate` is built from, plus the scale that header earns. */
export interface NewSheetHeader {
  name: string;
  size: SheetSize;
  orientation: Orientation;
  projection: Projection;
  /**
   * The scale the proposed orientation earns, or null when nothing argues for
   * one — an unmeasurable source, or a lone-view sheet whose drawn footprint is
   * not the four-view footprint this fit models. Null means "leave the user's
   * picked scale alone" (the `bounding_box: null` rule from `69b3ef7`): a
   * silently-guessed scale is worse than an honest one.
   */
  scaleValue: string | null;
}

/**
 * The ONE header derivation every create path uses — REACH-3-FLOW.
 *
 * The proposal used to live at a single call site (`handleAddSheet`, the SECOND
 * sheet) while all four Sheet-1 paths wrote `orientation: "landscape"` as a
 * literal, so the feature never fired on the only sheet most drawings have. A
 * proposal that never fires on the first sheet is worse than no proposal: the
 * user learns the tool has no opinion and stops looking for one.
 *
 * Three things are decided here, together, because they are one decision:
 *   - ORIENTATION — proposed from the document's own extents for a four-view
 *     sheet; landscape (the shop default) for a lone-view sheet, whose drawn
 *     footprint {@link fitScale} does not model. Guessing there would be exactly
 *     the "promises a scale it will not deliver" defect in a new place.
 *   - CONVENTION — INHERITED from the sheet in hand, so a first-angle shop
 *     states its standard once per drawing rather than once per sheet.
 *   - SCALE — the one that orientation actually earns, so the very next layout
 *     lands at the size the header cell promised.
 *
 * Nothing here is a dead end: both fields are one keystroke away on the sheet
 * header cells, and flipping orientation re-fits.
 */
export function sheetHeaderForNewSheet(input: {
  name: string;
  size: SheetSize;
  layout: SheetLayoutKind;
  /** The measured proposal, or null when the source could not be measured. */
  fit: OrientationFit | null;
  /** The sheet whose convention a new sheet inherits (null → the ISO default). */
  inherit: Pick<SheetResponse, "projection"> | null;
  /**
   * The user's own answer to the proposal, when they gave one — the "disposes"
   * half. It wins outright: a proposal the user has already overruled is not a
   * proposal any more.
   */
  override?: Orientation | null;
}): NewSheetHeader {
  const standard = input.layout === "standard";
  const orientation: Orientation =
    input.override ??
    (standard ? (input.fit?.proposed ?? "landscape") : "landscape");
  return {
    name: input.name,
    size: input.size,
    orientation,
    projection: input.inherit?.projection ?? "third_angle",
    scaleValue:
      standard && input.fit ? input.fit.scaleByOrientation[orientation] : null,
  };
}

/**
 * Where a HAND-PLACED view centre lands when the paper it was pinned to changes
 * shape. Proportional in each axis, so the composition the user arranged keeps
 * its relative position — a view pinned beside the title block stays beside the
 * title block — and, crucially, a pin can never fall off the new paper.
 *
 * Auto-placed views need none of this (the server re-derives them from the
 * sheet's own extents); this exists because `auto_place: false` means the
 * composer honours the stored mm verbatim, and 270 mm across is off the edge of
 * a 210 mm-wide portrait sheet.
 */
export function reframePinnedCentre(
  centre: { x_mm: number; y_mm: number },
  from: SheetDims,
  to: SheetDims,
): { x_mm: number; y_mm: number } {
  return {
    x_mm: (centre.x_mm / from.width) * to.width,
    y_mm: (centre.y_mm / from.height) * to.height,
  };
}
