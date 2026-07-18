/**
 * Drawing-dimension geometry + formatting — the pure drafting maths the sheet
 * renderer and its unit tests share, kept out of React so it runs without a DOM.
 *
 * A dimension is a precise annotation drawn OVER a projected edge: extension
 * (witness) lines, a dimension line with filled arrowheads, and the model-true
 * value stamped with the right prefix (Ø diameter · R radius · ° angular · bare
 * linear). The VALUE is always measured server-side from the model (design
 * §3.1); this module only decides where the annotation lands on the sheet, in
 * the SAME projected(y-up)→SVG(y-down) space `viewTransform` maps edges through,
 * so an annotation sits exactly on the geometry it measures.
 *
 * v1 renders `linear` (edge length), `diameter`, and `radius`. A dimension whose
 * geometry it cannot place (angular / point-to-point, or an unmatched edge) is
 * skipped honestly (null) rather than mis-drawn; a measurement error renders a
 * marker, never a crash.
 */
import { drawing } from "@loft/design";

import type {
  DimensionParams,
  EdgeSignature,
  MeasuredDimension,
  ProjectedPoint,
  ProjectedViewEdge,
} from "../api/drawings";
import type { Point2D, SvgRect } from "./layout";

// --- small 2D vector helpers (projected mm space, y-up) ------------------
type V = Point2D;
const v = (x: number, y: number): V => ({ x, y });
const sub = (a: V, b: V): V => v(a.x - b.x, a.y - b.y);
const add = (a: V, b: V): V => v(a.x + b.x, a.y + b.y);
const mul = (a: V, s: number): V => v(a.x * s, a.y * s);
const dot = (a: V, b: V): number => a.x * b.x + a.y * b.y;
const hyp = (a: V): number => Math.hypot(a.x, a.y);
const neg = (a: V): V => v(-a.x, -a.y);
const perp = (a: V): V => v(-a.y, a.x);
const unit = (a: V): V => {
  const l = hyp(a);
  return l < 1e-9 ? v(0, 0) : v(a.x / l, a.y / l);
};
const fromPt = (p: ProjectedPoint): V => v(p.x_mm, p.y_mm);

// --- signature matching (dimension edge → its projected geometry) --------
/** Round a coordinate so the stored signature matches the re-projected one. */
const r3 = (n: number): string => n.toFixed(3);

/** A rounded, orientation-independent key for a model-edge signature. */
export function edgeSignatureKey(sig: EdgeSignature): string {
  const pt = (p: { x: number; y: number; z: number }): string =>
    `${r3(p.x)},${r3(p.y)},${r3(p.z)}`;
  return `${sig.curve}|${pt(sig.end_a)}|${pt(sig.end_b)}|${pt(sig.midpoint)}`;
}

/** True when two signatures name the same model edge (within rounding). */
export function edgeSignaturesMatch(
  a: EdgeSignature,
  b: EdgeSignature,
): boolean {
  return edgeSignatureKey(a) === edgeSignatureKey(b);
}

/** The primary model edge a dimension references (for locating its geometry). */
export function dimensionEdgeSignature(
  params: DimensionParams,
): EdgeSignature | null {
  switch (params.type) {
    case "diameter":
    case "radius":
      return params.edge;
    case "linear":
      return params.measurement.mode === "edge_length"
        ? params.measurement.edge
        : params.measurement.a.signature;
    case "angular":
      return params.edge_a;
    default:
      return null;
  }
}

/** Find the projected edge whose model source matches `sig`, or null. */
export function findMatchingEdge(
  edges: readonly ProjectedViewEdge[],
  sig: EdgeSignature,
): ProjectedViewEdge | null {
  const key = edgeSignatureKey(sig);
  for (const edge of edges) {
    if (edge.source_edge && edgeSignatureKey(edge.source_edge) === key) {
      return edge;
    }
  }
  return null;
}

// --- value formatting ----------------------------------------------------
/** Format a measured value at a sensible precision (mm to 3dp, angles to 1dp). */
function numberText(value: number, unit: string | null | undefined): string {
  return value.toFixed(unit === "deg" ? 1 : 3);
}

/**
 * The stamped label with its drafting prefix/suffix: `Ø10.000` (diameter),
 * `R5.000` (radius), `90.0°` (angular), `40.000` (linear).
 */
export function formatDimensionLabel(
  type: DimensionParams["type"],
  value: number,
  unit: string | null | undefined,
): string {
  const n = numberText(value, unit);
  switch (type) {
    case "diameter":
      return `Ø${n}`;
    case "radius":
      return `R${n}`;
    case "angular":
      return `${n}°`;
    default:
      return n;
  }
}

// --- annotation geometry -------------------------------------------------
/** A straight rule of the annotation (SVG space, mm). */
export interface DimLine {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** `extension` = thin witness line; `dimension` = the arrowed measure line. */
  role: "extension" | "dimension";
}
/** The stamped value (SVG space) — `angle` keeps text upright along the line. */
export interface DimText {
  x: number;
  y: number;
  angle: number;
  label: string;
}

/**
 * A placed dimension annotation. `measured` carries the full drafting geometry;
 * `error` carries a marker point + the typed code for a dimension the model
 * could not measure (design §3.3) — surfaced, never crashed.
 */
export type DimensionAnnotation =
  | {
      kind: "measured";
      lines: DimLine[];
      /** Filled arrowhead triangles as SVG `points` strings. */
      arrows: string[];
      text: DimText;
      /** True: value is model-true but the drawn length is foreshortened (§3.2). */
      foreshortened: boolean;
    }
  | { kind: "error"; at: Point2D; code: string };

const O = drawing.dimensionOffsetMm;
const GAP = drawing.dimensionGapMm;
const OVER = drawing.extensionOverrunMm;
const AL = drawing.arrowLengthMm;
const AW = drawing.arrowHalfWidthMm;
const TXT = drawing.dimensionTextMm;

/** An arrowhead triangle: tip at `tip`, barb pointing `dir` (unit), as points. */
function arrowPoints(tip: V, dir: V, toSvg: (p: V) => V): string {
  const base = sub(tip, mul(dir, AL));
  const wing = mul(perp(dir), AW);
  const a = toSvg(tip);
  const b = toSvg(add(base, wing));
  const c = toSvg(sub(base, wing));
  return `${a.x},${a.y} ${b.x},${b.y} ${c.x},${c.y}`;
}

const svgLine = (
  a: V,
  b: V,
  role: DimLine["role"],
  toSvg: (p: V) => V,
): DimLine => {
  const p = toSvg(a);
  const q = toSvg(b);
  return { x1: p.x, y1: p.y, x2: q.x, y2: q.y, role };
};

/** Keep stamped text reading left-to-right regardless of the line's slope. */
function uprightAngle(a: V, b: V): number {
  let deg = (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
  if (deg > 90) deg -= 180;
  if (deg < -90) deg += 180;
  return deg;
}

/** The placed-and-measured annotation variant (never the error marker). */
type MeasuredAnnotation = Extract<DimensionAnnotation, { kind: "measured" }>;

/** Half-extents (SVG mm) of the value's paper halo — MUST match `DimensionGlyph`. */
function textHalfExtent(label: string): { w: number; h: number } {
  return { w: (label.length * TXT * 0.62 + 1.8) / 2, h: (TXT + 1.4) / 2 };
}

/** The SVG bounds an annotation occupies — its rules, arrows and value halo. */
function annotationBounds(anno: MeasuredAnnotation): SvgRect {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const acc = (x: number, y: number): void => {
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  };
  for (const l of anno.lines) {
    acc(l.x1, l.y1);
    acc(l.x2, l.y2);
  }
  for (const pts of anno.arrows) {
    for (const pair of pts.split(" ")) {
      const [x, y] = pair.split(",").map(Number);
      if (
        x !== undefined &&
        y !== undefined &&
        Number.isFinite(x) &&
        Number.isFinite(y)
      ) {
        acc(x, y);
      }
    }
  }
  const half = textHalfExtent(anno.text.label);
  acc(anno.text.x - half.w, anno.text.y - half.h);
  acc(anno.text.x + half.w, anno.text.y + half.h);
  return { minX, minY, maxX, maxY };
}

/** Overlap area of two SVG rects (0 when disjoint). */
function rectOverlap(a: SvgRect, b: SvgRect): number {
  const w = Math.min(a.maxX, b.maxX) - Math.max(a.minX, b.minX);
  const h = Math.min(a.maxY, b.maxY) - Math.max(a.minY, b.minY);
  return w > 0 && h > 0 ? w * h : 0;
}

/**
 * How BADLY a candidate placement reads: heavy penalty for overlapping another
 * view's geometry (a callout must never land on a neighbour), plus a light
 * penalty for spilling off the sheet. Lower is better; the caller keeps the
 * conventional outboard side on a tie (0 == both sides clear).
 */
function placementPenalty(
  bbox: SvgRect,
  obstacles: readonly SvgRect[],
  sheet: { width: number; height: number } | undefined,
): number {
  let penalty = 0;
  for (const o of obstacles) penalty += rectOverlap(bbox, o) * 10;
  if (sheet) {
    penalty +=
      Math.max(0, -bbox.minX) +
      Math.max(0, -bbox.minY) +
      Math.max(0, bbox.maxX - sheet.width) +
      Math.max(0, bbox.maxY - sheet.height);
  }
  return penalty;
}

/**
 * Pick the placement that reads cleanest: the `preferred` candidate wins unless
 * an `alternate` measurably clears an obstacle the preferred one hits (so a
 * gutter-facing dimension flips away from the neighbour it would otherwise
 * collide with — frontend-QA P1).
 */
function chooseByPenalty(
  preferred: MeasuredAnnotation,
  alternate: MeasuredAnnotation,
  obstacles: readonly SvgRect[],
  sheet: { width: number; height: number } | undefined,
): MeasuredAnnotation {
  const pPref = placementPenalty(annotationBounds(preferred), obstacles, sheet);
  const pAlt = placementPenalty(annotationBounds(alternate), obstacles, sheet);
  return pAlt < pPref ? alternate : preferred;
}

/**
 * Build the drafting annotation for one measured dimension, placed on the
 * matched projected `edge` and mapped through `toSvg`. `viewCenter` (projected
 * mm) picks the conventional outboard side; `obstacles` (sibling views' SVG
 * bounds) let the placement FLIP away from a neighbour it would otherwise land
 * on in the third-angle gutter (frontend-QA P1), and `sheet` keeps it on paper.
 * Returns null when the type/edge cannot be placed in v1 (angular /
 * point-to-point / a geometry mismatch) — the caller lists it, never mis-draws.
 */
export function buildDimensionAnnotation(args: {
  type: DimensionParams["type"];
  measured: MeasuredDimension;
  edge: ProjectedViewEdge;
  viewCenter: Point2D;
  toSvg: (p: Point2D) => Point2D;
  /** Sibling views' SVG bounds a callout must not overlap (default none). */
  obstacles?: readonly SvgRect[];
  /** The sheet's mm extent, so a placement is nudged to stay on paper. */
  sheet?: { width: number; height: number };
}): DimensionAnnotation | null {
  const { type, measured, edge, viewCenter, toSvg } = args;
  const obstacles = args.obstacles ?? [];
  const sheet = args.sheet;

  // A typed measurement failure: mark the edge, never draw a wrong number.
  if (measured.error || typeof measured.value !== "number") {
    return {
      kind: "error",
      at: toSvg(fromPt(edge.midpoint)),
      code: measured.error?.code ?? "unmeasured",
    };
  }
  const value = measured.value;
  const label =
    (measured.foreshortened ? "~" : "") +
    formatDimensionLabel(type, value, measured.unit);

  if (type === "linear") {
    if (edge.primitive !== "line") return null;
    const s = fromPt(edge.start);
    const e = fromPt(edge.end);
    const d = unit(sub(e, s));
    if (hyp(d) < 1e-9) return null;
    const mid = mul(add(s, e), 0.5);
    const n0 = perp(d);
    // The conventional outboard normal points AWAY from the view centre.
    const away = dot(n0, sub(mid, viewCenter)) >= 0 ? n0 : neg(n0);

    // Build the full annotation for a given offset normal.
    const place = (n: V): MeasuredAnnotation => {
      const dimA = add(s, mul(n, O));
      const dimB = add(e, mul(n, O));
      const lines: DimLine[] = [
        // extension (witness) lines, from a small gap off the edge past the line
        svgLine(
          add(s, mul(n, GAP)),
          add(s, mul(n, O + OVER)),
          "extension",
          toSvg,
        ),
        svgLine(
          add(e, mul(n, GAP)),
          add(e, mul(n, O + OVER)),
          "extension",
          toSvg,
        ),
        // the dimension line between them
        svgLine(dimA, dimB, "dimension", toSvg),
      ];
      const arrows = [
        arrowPoints(dimA, neg(d), toSvg),
        arrowPoints(dimB, d, toSvg),
      ];
      const midDim = mul(add(dimA, dimB), 0.5);
      const anchor = toSvg(add(midDim, mul(n, TXT * 0.5 + 0.6)));
      const angle = uprightAngle(toSvg(dimA), toSvg(dimB));
      return {
        kind: "measured",
        lines,
        arrows,
        text: { x: anchor.x, y: anchor.y, angle, label },
        foreshortened: measured.foreshortened,
      };
    };

    // Prefer the outboard side, but flip to the opposite side if it would land
    // on a neighbouring view in the third-angle gutter (frontend-QA P1).
    return chooseByPenalty(place(away), place(neg(away)), obstacles, sheet);
  }

  if (type === "diameter" || type === "radius") {
    if (!edge.center || typeof edge.radius !== "number") return null;
    const c = fromPt(edge.center);
    const rad = edge.radius;
    if (type === "diameter") {
      // A dimension line straight across the circle through its centre, arrows
      // out to each side. The VALUE is stamped CLEAR of the circle (beyond the
      // arc along the dimension line) so its paper halo never masks the arc —
      // a Ø10 hole must read as a full circle, not a semicircle (frontend-QA P2).
      const a = v(c.x - rad, c.y);
      const b = v(c.x + rad, c.y);
      const half = textHalfExtent(label).w;
      const place = (sign: number): MeasuredAnnotation => {
        const anchor = toSvg(v(c.x + sign * (rad + 1.4 + half), c.y));
        return {
          kind: "measured",
          lines: [svgLine(a, b, "dimension", toSvg)],
          arrows: [
            arrowPoints(a, v(-1, 0), toSvg),
            arrowPoints(b, v(1, 0), toSvg),
          ],
          text: { x: anchor.x, y: anchor.y, angle: 0, label },
          foreshortened: measured.foreshortened,
        };
      };
      // Stamp on the outboard side (away from the view centre), flipping if that
      // side would collide with a neighbouring view.
      const sign = dot(v(1, 0), sub(c, viewCenter)) >= 0 ? 1 : -1;
      return chooseByPenalty(place(sign), place(-sign), obstacles, sheet);
    }
    // radius: a leader from the centre out to the circle at 45°, value clear of
    // the arc (offset past the edge by the text half-width so its halo lands on
    // empty paper, never over the circle — frontend-QA P2).
    const dir = unit(v(1, 1));
    const edgePt = add(c, mul(dir, rad));
    const lines = [svgLine(c, edgePt, "dimension", toSvg)];
    const arrows = [arrowPoints(edgePt, dir, toSvg)];
    const anchor = toSvg(add(edgePt, mul(dir, 2.4 + textHalfExtent(label).w)));
    return {
      kind: "measured",
      lines,
      arrows,
      text: { x: anchor.x, y: anchor.y, angle: 0, label },
      foreshortened: measured.foreshortened,
    };
  }

  // angular / point-to-point linear: not placed in v1 (deferred to BACKLOG).
  return null;
}
