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
 *  - the scale picker options, and
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
  };
}

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

/** The scale options the picker offers, smallest reduction first. */
export const SCALE_OPTIONS: readonly {
  value: string;
  label: string;
  numerator: number;
  denominator: number;
}[] = [
  { value: "1:1", label: "1:1", numerator: 1, denominator: 1 },
  { value: "2:1", label: "2:1", numerator: 2, denominator: 1 },
  { value: "5:1", label: "5:1", numerator: 5, denominator: 1 },
  { value: "1:2", label: "1:2", numerator: 1, denominator: 2 },
  { value: "1:5", label: "1:5", numerator: 1, denominator: 5 },
  { value: "1:10", label: "1:10", numerator: 1, denominator: 10 },
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

/** Margin (sheet mm) kept between a view's footprint and its cell edge.
 * Calibrated, not padded: the SERVER's bounds-aware composer is the real
 * collision guarantee — this client cell model is a pre-flight estimate, and
 * 4 mm keeps the empirically-verified clean layouts acceptable (the WB-64
 * bottle's true iso height at 1:5 is 61.7 mm — a 6 mm margin would push it to
 * an unnecessarily tiny 1:10) while the exact projection coefficients below
 * keep the estimate honest. */
const FIT_MARGIN_MM = 4;

// Anchor-derived half-gaps, kept in lock-step with standardLayout's 0.32/0.68
// columns and 0.36/0.70 rows: a view's usable half-width is the smaller of its
// column's edge distance (0.32) and the mid-gap to the other column (0.18);
// half-height likewise (bottom row edge 0.36, top row edge 0.30, row mid-gap
// 0.17). If the anchors move, these must move with them.
const CELL_HALF_W_FRACTION = Math.min(0.32, 0.18);
const CELL_HALF_H_FRACTION = Math.min(0.36, 0.3, 0.17);

// EXACT true-isometric projection coefficients of the SERVER's iso frame
// (geometry.drawings.project: N = normalize(−1,−1,1), X = normalize(Z×N)):
// world x → (0.7071, 0.4082), y → (−0.7071, 0.4082), z → (0, 0.8165), so an
// axis-aligned box projects to exactly w = 0.7071·(x+y),
// h = 0.8165·z + 0.4082·(x+y). Code-review 2026-07-22: the previous hand
// coefficients (0.87 / 0.82 / 0.3) mislabelled themselves an over-approx —
// the width was 23% over while the xy-height term UNDER-approximated by 27%,
// letting flat/pancake parts accept a scale whose iso view overflows its cell.
const ISO_W_XY = 0.7071;
const ISO_H_Z = 0.8165;
const ISO_H_XY = 0.4082;

/**
 * The largest standard scale whose four auto-layout views fit their quadrant
 * cells on `dims`, never exceeding `chosenValue` (a user's explicit pick is a
 * ceiling, not a suggestion — auto-fit only ever *reduces*). This is the
 * fit-scale half of the auto-layout fix (BACKLOG 2026-07-20, WB-64 dogfooding:
 * a 258 mm part at the 1:1 default rendered views off-sheet and overlapping).
 *
 * Cells come from the {@link standardLayout} anchor scheme (see the fraction
 * constants above), each less {@link FIT_MARGIN_MM} per side. Footprints are
 * the exact ortho projections (front x·z, right y·z, top x·y) plus the
 * true-iso bound (constants above). If even the smallest option cannot fit,
 * that smallest option is returned (a too-small view beats an unusable
 * overlap, and the server's bounds-aware composer still draws it).
 */
export function fitScale(
  extents: ModelExtents,
  dims: SheetDims,
  chosenValue: string,
): (typeof SCALE_OPTIONS)[number] {
  const cellW = 2 * CELL_HALF_W_FRACTION * dims.width - 2 * FIT_MARGIN_MM;
  const cellH = 2 * CELL_HALF_H_FRACTION * dims.height - 2 * FIT_MARGIN_MM;
  const footprints: readonly [number, number][] = [
    [extents.x, extents.z], // front
    [extents.y, extents.z], // right
    [extents.x, extents.y], // top
    [
      ISO_W_XY * (extents.x + extents.y),
      ISO_H_Z * extents.z + ISO_H_XY * (extents.x + extents.y),
    ], // iso
  ];
  const ratio = (o: { numerator: number; denominator: number }) =>
    o.numerator / o.denominator;
  const chosen = SCALE_OPTIONS.find((o) => o.value === chosenValue);
  const ceiling = chosen ? ratio(chosen) : 1;
  const candidates = SCALE_OPTIONS.filter((o) => ratio(o) <= ceiling).sort(
    (a, b) => ratio(b) - ratio(a),
  );
  for (const option of candidates) {
    const s = ratio(option);
    if (footprints.every(([w, h]) => w * s <= cellW && h * s <= cellH)) {
      return option;
    }
  }
  return candidates[candidates.length - 1] ?? SCALE_OPTIONS[0]!;
}

// --- the orientation proposal, and the ONE header every new sheet is born with

/**
 * What each paper orientation buys THIS document, and which one its own extents
 * therefore argue for.
 */
export interface OrientationFit {
  /** Fitted scale label per orientation ("1:2" / "1:5"). */
  scaleByOrientation: Record<Orientation, string>;
  /** The orientation that fits the document largest (landscape wins a tie — the
   * shop default, so a document with no preference gets no surprise). */
  proposed: Orientation;
}

/**
 * The orientation proposal for a document on a given paper size. Both
 * orientations are fitted against the SAME {@link fitScale} the layout action
 * uses, with a 1:1 ceiling: auto-fit only ever REDUCES, so 1:1 is the neutral
 * maximum and the comparison answers "at best, how big can this be drawn either
 * way?" — which is the question that chooses a paper. (A user's own scale pick
 * stays a ceiling on the LAYOUT; it is not a claim about the paper.)
 */
export function proposeOrientation(
  extents: ModelExtents,
  size: SheetSize,
): OrientationFit {
  const landscape = fitScale(
    extents,
    sheetDimensions(size, "landscape"),
    "1:1",
  );
  const portrait = fitScale(extents, sheetDimensions(size, "portrait"), "1:1");
  const ratio = (o: { numerator: number; denominator: number }) =>
    o.numerator / o.denominator;
  return {
    scaleByOrientation: {
      landscape: landscape.value,
      portrait: portrait.value,
    },
    proposed: ratio(portrait) > ratio(landscape) ? "portrait" : "landscape",
  };
}

/**
 * Which shape of drawing a new sheet is being born for. `standard` is the four
 * quadrant views {@link fitScale} models; `lone` is a single centred view (a
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
