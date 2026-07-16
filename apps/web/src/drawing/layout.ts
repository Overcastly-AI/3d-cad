/**
 * Drawing-sheet geometry — the pure layout + edge-to-SVG maths the sheet
 * renderer, the auto-layout action, and the unit tests all share, kept out of
 * the React component so it runs without a DOM. Sheet space is millimetres
 * (drawings.md §9 q4); a view's projected edges arrive already scaled
 * (model-mm × scale), so 1 projected unit == 1 sheet mm == 1 SVG user unit.
 *
 * The renderer works in a single SVG coordinate system (millimetres, y-DOWN,
 * origin top-left) — every helper here emits final SVG coordinates so the
 * component never re-flips axes or reasons about reflected arc sweeps.
 */
import type {
  ProjectedPoint,
  ProjectedViewEdge,
  SheetResponse,
  ViewProjection,
} from "../api/drawings";

/** The four standard views, in the canonical creation + render order. */
export const STANDARD_VIEWS: readonly ViewProjection[] = [
  "front",
  "top",
  "right",
  "iso",
];

/** Human labels for a projection (the stamped caption under each view). */
export const VIEW_LABEL: Record<ViewProjection, string> = {
  front: "Front",
  top: "Top",
  right: "Right",
  iso: "Isometric",
};

type SheetSize = SheetResponse["size"];
type Orientation = SheetResponse["orientation"];

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

/** The border inset (mm) from the sheet edge — the drawn frame. */
export const SHEET_MARGIN_MM = 10;
/** Title-block box (mm), seated in the bottom-right corner inside the border. */
export const TITLE_BLOCK_MM = { width: 96, height: 34 } as const;
/** Clear space (mm) between adjacent views' bounding boxes. */
export const VIEW_GUTTER_MM = 14;

export interface Anchor {
  /** View-centre X in sheet mm (origin bottom-left, y-UP). */
  x: number;
  /** View-centre Y in sheet mm (origin bottom-left, y-UP). */
  y: number;
}

/**
 * The standard third-angle placement of the four views on a sheet: front is
 * the primary; the top view sits ABOVE it and the right view to its RIGHT (the
 * US third-angle convention, drawings.md §1.2/§7), with the isometric filling
 * the free upper-right quadrant. Returned as view-CENTRE anchors in sheet mm
 * (origin bottom-left) — the SINGLE source both the auto-layout writer (view
 * positions) and the renderer read, so a reload lays the sheet out identically.
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
  };
}

export interface Point2D {
  x: number;
  y: number;
}

interface Bounds2D {
  min: Point2D;
  max: Point2D;
  center: Point2D;
}

const p2 = (p: ProjectedPoint): Point2D => ({ x: p.x_mm, y: p.y_mm });

/** Every defining point of an edge (used only for the view's bounding box). */
function edgePoints(edge: ProjectedViewEdge): Point2D[] {
  const pts: Point2D[] = [p2(edge.start), p2(edge.end), p2(edge.midpoint)];
  if (edge.center) pts.push(p2(edge.center));
  for (const p of edge.points ?? []) pts.push(p2(p));
  // A circle's extent is its centre ± radius, not just start/end (which
  // coincide on a seam) — include the radius box so it never clips.
  if (edge.center && typeof edge.radius === "number") {
    const c = p2(edge.center);
    const r = edge.radius;
    pts.push({ x: c.x - r, y: c.y - r }, { x: c.x + r, y: c.y + r });
  }
  return pts;
}

/** The tight 2D bounds (+ centre) of a view's projected edges, or null if empty. */
export function viewBounds(
  edges: readonly ProjectedViewEdge[],
): Bounds2D | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const edge of edges) {
    for (const pt of edgePoints(edge)) {
      minX = Math.min(minX, pt.x);
      minY = Math.min(minY, pt.y);
      maxX = Math.max(maxX, pt.x);
      maxY = Math.max(maxY, pt.y);
    }
  }
  if (!Number.isFinite(minX)) return null;
  return {
    min: { x: minX, y: minY },
    max: { x: maxX, y: maxY },
    center: { x: (minX + maxX) / 2, y: (minY + maxY) / 2 },
  };
}

/**
 * Bounds-aware third-angle placement: spaces the four views by their OWN
 * projected extents (+ a gutter) instead of fixed sheet fractions, so views
 * never overlap for a part taller/wider than the demo plate, then centres the
 * whole arrangement in the sheet. Preserves the third-angle relations — top
 * shares front's X (sits above), right shares front's Y (sits to the right),
 * iso fills the free upper-right — so projection alignment still reads. Falls
 * back to the fixed `standardLayout` when no view has any geometry yet.
 *
 * Half-extents come from each view's `viewBounds`; a missing/empty view
 * contributes zero extent. Scale still fits large parts via the scale picker
 * (this only prevents overlap, not sheet overrun).
 */
export function boundsAwareLayout(
  boundsByProjection: Partial<Record<ViewProjection, Bounds2D | null>>,
  dims: SheetDims,
): Record<ViewProjection, Anchor> {
  const half = (v: ViewProjection): { w: number; h: number } => {
    const b = boundsByProjection[v] ?? null;
    if (!b) return { w: 0, h: 0 };
    return { w: (b.max.x - b.min.x) / 2, h: (b.max.y - b.min.y) / 2 };
  };
  const f = half("front");
  const t = half("top");
  const r = half("right");
  const g = VIEW_GUTTER_MM;

  // No view has any geometry yet (all failed/empty): the fixed fractions spread
  // the placeholders more legibly than clustering them at the centre.
  const anyGeometry = STANDARD_VIEWS.some((v) => {
    const h = half(v);
    return h.w > 0 || h.h > 0;
  });
  if (!anyGeometry) return standardLayout(dims);

  // Relative anchors (front at origin, y-UP): top ABOVE front, right to the
  // RIGHT of front (both spaced by the two half-extents + gutter), iso in the
  // free upper-right quadrant (aligned with right's X and top's Y).
  const rel: Record<ViewProjection, Anchor> = {
    front: { x: 0, y: 0 },
    top: { x: 0, y: f.h + g + t.h },
    right: { x: f.w + g + r.w, y: 0 },
    iso: { x: f.w + g + r.w, y: f.h + g + t.h },
  };

  // Envelope of the placed views (anchor ± half-extent); centre it in the sheet.
  const halfOf: Record<ViewProjection, { w: number; h: number }> = {
    front: f,
    top: t,
    right: r,
    iso: half("iso"),
  };
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const v of STANDARD_VIEWS) {
    const a = rel[v];
    const hh = halfOf[v];
    minX = Math.min(minX, a.x - hh.w);
    maxX = Math.max(maxX, a.x + hh.w);
    minY = Math.min(minY, a.y - hh.h);
    maxY = Math.max(maxY, a.y + hh.h);
  }
  // `anyGeometry` guaranteed at least one real extent, so the envelope is finite.
  const dx = dims.width / 2 - (minX + maxX) / 2;
  const dy = dims.height / 2 - (minY + maxY) / 2;
  return {
    front: { x: rel.front.x + dx, y: rel.front.y + dy },
    top: { x: rel.top.x + dx, y: rel.top.y + dy },
    right: { x: rel.right.x + dx, y: rel.right.y + dy },
    iso: { x: rel.iso.x + dx, y: rel.iso.y + dy },
  };
}

/** An SVG-ready primitive in final sheet coordinates (mm, y-down, top-left). */
export type SvgEdge =
  | {
      kind: "line";
      x1: number;
      y1: number;
      x2: number;
      y2: number;
      visible: boolean;
    }
  | { kind: "circle"; cx: number; cy: number; r: number; visible: boolean }
  | { kind: "polyline"; points: Point2D[]; visible: boolean };

const TAU = Math.PI * 2;
const norm = (a: number): number => ((a % TAU) + TAU) % TAU;

/**
 * Sample a projected arc (centre + radius + endpoints) into the polyline that
 * passes through its midpoint. Sampling — rather than an SVG `A` arc inside the
 * reflected view group — sidesteps every sweep/large-arc sign ambiguity the
 * y-flip would introduce; at print scale the fine sampling is indistinguishable
 * from a true arc, and full circles stay exact `<circle>` elements.
 */
function sampleArc(
  center: Point2D,
  radius: number,
  start: Point2D,
  mid: Point2D,
  end: Point2D,
): Point2D[] {
  const aS = Math.atan2(start.y - center.y, start.x - center.x);
  const aM = Math.atan2(mid.y - center.y, mid.x - center.x);
  const aE = Math.atan2(end.y - center.y, end.x - center.x);
  const spanCCW = norm(aE - aS);
  const midCCW = norm(aM - aS);
  const ccw = midCCW <= spanCCW;
  let total = ccw ? spanCCW : TAU - spanCCW;
  if (total < 1e-9) total = TAU; // degenerate: treat as a full turn
  const dir = ccw ? 1 : -1;
  const segments = Math.min(96, Math.max(8, Math.ceil(total / (Math.PI / 16))));
  const pts: Point2D[] = [];
  for (let i = 0; i <= segments; i += 1) {
    const theta = aS + dir * total * (i / segments);
    pts.push({
      x: center.x + radius * Math.cos(theta),
      y: center.y + radius * Math.sin(theta),
    });
  }
  return pts;
}

/**
 * Map one view's projected edges into final SVG primitives, placing the view's
 * bounding-box centre at `anchor` on a sheet of height `sheetHeight`. Sheet mm
 * are y-UP with a bottom-left origin; SVG is y-DOWN top-left, so the anchor and
 * every edge point are flipped once here (`sheetHeight - y`).
 */
export function viewToSvgEdges(
  edges: readonly ProjectedViewEdge[],
  anchor: Anchor,
  sheetHeight: number,
): SvgEdge[] {
  const bounds = viewBounds(edges);
  const cx = bounds?.center.x ?? 0;
  const cy = bounds?.center.y ?? 0;
  const anchorSvgX = anchor.x;
  const anchorSvgY = sheetHeight - anchor.y;
  // Projected (y-up, centred) → SVG (y-down): translate to the anchor, flip y.
  const toSvg = (p: Point2D): Point2D => ({
    x: anchorSvgX + (p.x - cx),
    y: anchorSvgY - (p.y - cy),
  });

  const out: SvgEdge[] = [];
  for (const edge of edges) {
    if (edge.primitive === "line") {
      const a = toSvg(p2(edge.start));
      const b = toSvg(p2(edge.end));
      out.push({
        kind: "line",
        x1: a.x,
        y1: a.y,
        x2: b.x,
        y2: b.y,
        visible: edge.visible,
      });
    } else if (
      edge.primitive === "circle" &&
      edge.center &&
      typeof edge.radius === "number"
    ) {
      const c = toSvg(p2(edge.center));
      out.push({
        kind: "circle",
        cx: c.x,
        cy: c.y,
        r: edge.radius,
        visible: edge.visible,
      });
    } else if (
      edge.primitive === "arc" &&
      edge.center &&
      typeof edge.radius === "number"
    ) {
      const pts = sampleArc(
        p2(edge.center),
        edge.radius,
        p2(edge.start),
        p2(edge.midpoint),
        p2(edge.end),
      ).map(toSvg);
      out.push({ kind: "polyline", points: pts, visible: edge.visible });
    } else {
      // polyline (or an under-specified circle/arc): draw the sampled vertices,
      // falling back to start→end so a malformed edge still renders a segment.
      const raw =
        edge.points && edge.points.length > 0
          ? edge.points.map(p2)
          : [p2(edge.start), p2(edge.end)];
      out.push({
        kind: "polyline",
        points: raw.map(toSvg),
        visible: edge.visible,
      });
    }
  }
  return out;
}

/** "1:1", "1:2", "2:1" — the printed scale caption. */
export function formatScale(scale: {
  numerator: number;
  denominator: number;
}): string {
  return `${scale.numerator}:${scale.denominator}`;
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
