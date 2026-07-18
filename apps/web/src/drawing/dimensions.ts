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
 * It places every v1 dimension type: `linear` (an edge length OR a point-to-
 * point distance between two named model vertices), `diameter`, `radius`, and
 * `angular` (an arc swept between two straight edges, stamped in degrees). A
 * dimension whose geometry it cannot place (an unmatched edge, parallel angular
 * edges) is skipped honestly (null) rather than mis-drawn; a measurement error
 * renders a marker, never a crash.
 */
import { drawing } from "@loft/design";

import type {
  DimensionParams,
  EdgeSignature,
  MeasuredDimension,
  ProjectedPoint,
  ProjectedViewEdge,
} from "../api/drawings";
import { endpointProjected, type Point2D, type SvgRect } from "./layout";

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
const ARC_R = drawing.dimensionArcRadiusMm;

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
 * A straight linear dimension between two projected points `p`→`q` (both in
 * projected mm) — the shared drafting primitive an edge-length dimension (the
 * edge's two endpoints) and a point-to-point dimension (two named model
 * vertices) both use: extension lines off each point, an offset dimension line
 * with arrowheads, and the stamped value. `viewCenter` picks the conventional
 * outboard side; `obstacles`/`sheet` let it flip away from a neighbour / off
 * the sheet (frontend-QA P1). Null when the two points coincide.
 */
function placeLinearBetween(
  p: V,
  q: V,
  label: string,
  foreshortened: boolean,
  viewCenter: Point2D,
  toSvg: (pt: V) => V,
  obstacles: readonly SvgRect[],
  sheet: { width: number; height: number } | undefined,
): DimensionAnnotation | null {
  const d = unit(sub(q, p));
  if (hyp(sub(q, p)) < 1e-9) return null;
  const mid = mul(add(p, q), 0.5);
  const n0 = perp(d);
  const away = dot(n0, sub(mid, viewCenter)) >= 0 ? n0 : neg(n0);

  const place = (n: V): MeasuredAnnotation => {
    const dimA = add(p, mul(n, O));
    const dimB = add(q, mul(n, O));
    const lines: DimLine[] = [
      svgLine(
        add(p, mul(n, GAP)),
        add(p, mul(n, O + OVER)),
        "extension",
        toSvg,
      ),
      svgLine(
        add(q, mul(n, GAP)),
        add(q, mul(n, O + OVER)),
        "extension",
        toSvg,
      ),
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
      foreshortened,
    };
  };

  return chooseByPenalty(place(away), place(neg(away)), obstacles, sheet);
}

/** Intersection of the two infinite lines through `a0a1` and `b0b1`, or null
 * when they are parallel (an angular dimension then has no apparent vertex). */
function lineIntersection(a0: V, a1: V, b0: V, b1: V): V | null {
  const r = sub(a1, a0);
  const s = sub(b1, b0);
  const denom = r.x * s.y - r.y * s.x;
  if (Math.abs(denom) < 1e-9) return null;
  const qp = sub(b0, a0);
  const t = (qp.x * s.y - qp.y * s.x) / denom;
  return add(a0, mul(r, t));
}

/** Signed angle (rad) in (-π, π] from `a` to `b`. */
function signedAngleBetween(a: V, b: V): number {
  return Math.atan2(a.x * b.y - a.y * b.x, a.x * b.x + a.y * b.y);
}

/**
 * The angular-dimension annotation between two straight projected edges: a
 * vertex at their (apparent) intersection, rays out along each edge, an arc
 * swept through the region the two edges actually enclose, arrowheads tangent
 * to the arc ends, and the model-true degree value stamped outside the arc.
 *
 * Drafting-standard region call: each ray is oriented from the vertex TOWARD
 * its edge (the side the geometry is on), and the arc sweeps the SHORT way
 * between them — so it dimensions the angle you see between the picked edges
 * (the acute/obtuse vee ≤ 180°, never its reflex). The stamped value is the
 * model-true angle (measured server-side); the drawn sweep is the apparent 2D
 * angle, which the `~` flag warns about when the edges are foreshortened.
 */
function placeAngular(
  edgeA: ProjectedViewEdge,
  edgeB: ProjectedViewEdge,
  label: string,
  foreshortened: boolean,
  toSvg: (pt: V) => V,
): DimensionAnnotation | null {
  const a0 = fromPt(edgeA.start);
  const a1 = fromPt(edgeA.end);
  const b0 = fromPt(edgeB.start);
  const b1 = fromPt(edgeB.end);
  const apex = lineIntersection(a0, a1, b0, b1);
  if (apex === null) return null;
  // Ray directions point from the vertex toward each edge's midpoint.
  const dirA = unit(sub(fromPt(edgeA.midpoint), apex));
  const dirB = unit(sub(fromPt(edgeB.midpoint), apex));
  if (hyp(dirA) < 1e-9 || hyp(dirB) < 1e-9) return null;

  const startAng = Math.atan2(dirA.y, dirA.x);
  const delta = signedAngleBetween(dirA, dirB); // short way, (-π, π]
  if (Math.abs(delta) < 1e-6) return null; // collinear rays — nothing to sweep

  const arcAt = (t: number): V => {
    const ang = startAng + delta * t;
    return add(apex, v(Math.cos(ang) * ARC_R, Math.sin(ang) * ARC_R));
  };
  const segments = Math.max(6, Math.ceil(Math.abs(delta) / (Math.PI / 24)));
  const lines: DimLine[] = [];
  for (let i = 0; i < segments; i += 1) {
    lines.push(
      svgLine(
        arcAt(i / segments),
        arcAt((i + 1) / segments),
        "dimension",
        toSvg,
      ),
    );
  }
  // Witness lines extend each side from the vertex out past the arc.
  lines.push(
    svgLine(
      add(apex, mul(dirA, GAP)),
      add(apex, mul(dirA, ARC_R + OVER)),
      "extension",
      toSvg,
    ),
  );
  lines.push(
    svgLine(
      add(apex, mul(dirB, GAP)),
      add(apex, mul(dirB, ARC_R + OVER)),
      "extension",
      toSvg,
    ),
  );

  // Arrowheads at the arc ends, tangent to the arc (pointing along the sweep).
  const tipA = arcAt(0);
  const tipB = arcAt(1);
  const arrows = [
    arrowPoints(tipA, unit(sub(arcAt(0.01), tipA)), toSvg),
    arrowPoints(tipB, unit(sub(arcAt(0.99), tipB)), toSvg),
  ];
  // Value stamped just outside the arc at its mid-sweep bearing.
  const midAng = startAng + delta / 2;
  const midDir = v(Math.cos(midAng), Math.sin(midAng));
  const anchor = toSvg(add(apex, mul(midDir, ARC_R + TXT * 0.7 + 1.8)));
  return {
    kind: "measured",
    lines,
    arrows,
    text: { x: anchor.x, y: anchor.y, angle: 0, label },
    foreshortened,
  };
}

/**
 * Build the drafting annotation for one measured `dimension`, resolved against
 * the view's projected `edges` and mapped through `toSvg`. `viewCenter`
 * (projected mm) picks the conventional outboard side; `obstacles` (sibling
 * views' SVG bounds) let a placement FLIP away from a neighbour in the third-
 * angle gutter (frontend-QA P1), and `sheet` keeps it on paper. A point-to-point
 * dimension's named model vertices come from each straight edge's
 * `start_is_end_a` correspondence (design §3.3).
 * Returns null when the dimension cannot be placed (an unmatched/mismatched
 * edge, parallel angular edges) — the caller lists it, never mis-draws.
 */
export function buildDimensionAnnotation(args: {
  dimension: DimensionParams;
  measured: MeasuredDimension;
  edges: readonly ProjectedViewEdge[];
  viewCenter: Point2D;
  toSvg: (p: Point2D) => Point2D;
  /** Sibling views' SVG bounds a callout must not overlap (default none). */
  obstacles?: readonly SvgRect[];
  /** The sheet's mm extent, so a placement is nudged to stay on paper. */
  sheet?: { width: number; height: number };
}): DimensionAnnotation | null {
  const { dimension, measured, edges, viewCenter, toSvg } = args;
  const type = dimension.type;
  const obstacles = args.obstacles ?? [];
  const sheet = args.sheet;

  // A representative sheet point for an error marker / mismatch fallback.
  const primarySig = dimensionEdgeSignature(dimension);
  const primaryEdge = primarySig ? findMatchingEdge(edges, primarySig) : null;
  const markerAt = primaryEdge
    ? toSvg(fromPt(primaryEdge.midpoint))
    : toSvg(viewCenter);

  // A typed measurement failure: mark the geometry, never draw a wrong number.
  if (measured.error || typeof measured.value !== "number") {
    return {
      kind: "error",
      at: markerAt,
      code: measured.error?.code ?? "unmeasured",
    };
  }
  const value = measured.value;
  const label =
    (measured.foreshortened ? "~" : "") +
    formatDimensionLabel(type, value, measured.unit);

  if (type === "linear") {
    if (dimension.measurement.mode === "point_to_point") {
      const ref = dimension.measurement;
      const edgeA = findMatchingEdge(edges, ref.a.signature);
      const edgeB = findMatchingEdge(edges, ref.b.signature);
      if (!edgeA || !edgeB) return null;
      const p = endpointProjected(edgeA, ref.a.endpoint);
      const q = endpointProjected(edgeB, ref.b.endpoint);
      if (!p || !q) return null;
      return placeLinearBetween(
        p,
        q,
        label,
        measured.foreshortened,
        viewCenter,
        toSvg,
        obstacles,
        sheet,
      );
    }
    const edge = primaryEdge;
    if (!edge || edge.primitive !== "line") return null;
    return placeLinearBetween(
      fromPt(edge.start),
      fromPt(edge.end),
      label,
      measured.foreshortened,
      viewCenter,
      toSvg,
      obstacles,
      sheet,
    );
  }

  if (type === "angular") {
    const edgeA = findMatchingEdge(edges, dimension.edge_a);
    const edgeB = findMatchingEdge(edges, dimension.edge_b);
    if (!edgeA || !edgeB) return null;
    if (edgeA.primitive !== "line" || edgeB.primitive !== "line") return null;
    return placeAngular(edgeA, edgeB, label, measured.foreshortened, toSvg);
  }

  if (type === "diameter" || type === "radius") {
    const edge = primaryEdge;
    if (!edge || !edge.center || typeof edge.radius !== "number") return null;
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

  return null;
}
