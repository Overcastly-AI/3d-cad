/**
 * Hole centres on the sheet — the pure half of QA-DRAWING-CENTRE-MARKS.
 *
 * Every circle a view sees end-on carries an automatic centre mark (composed
 * server-side), and that centre is a dimension anchor: a linear dimension runs
 * from a straight edge to a hole centre, or between two hole centres. A centre
 * is named through its circle (the hole rim's `EdgeSignature`), so it resolves
 * through the same durable anchor as every other drawing reference.
 *
 * This module holds what the placement stage needs that is particular to
 * centres: the Fusion rule that the POINTER decides whether a centre-to-centre
 * dimension is horizontal or vertical, the span each orientation is placed
 * against, and reading a placed one back so it can be moved. No React, no DOM.
 */
import { drawing } from "@loft/design";

import type { EdgeSignature, ViewProjection } from "../api/drawings";
import { edgeSignatureKey } from "./dimensions";
import type { Point2D } from "./layout";
import {
  type CentreOrientation,
  type CentrePair,
  type PlaceTarget,
  awayNormal,
  offsetAt,
} from "./placement";

/** A view's drawn extents on the sheet (mm) — what a hole dimension clears. */
export interface SheetBox {
  min: Point2D;
  max: Point2D;
}

/** One picked hole centre (a centre mark on the sheet). */
export interface CentreTarget {
  projection: ViewProjection;
  viewId: string;
  /** The CIRCLE whose centre this is — the stored reference. */
  sourceEdge: EdgeSignature;
  clientX: number;
  clientY: number;
  /** The centre's composed sheet position (mm), when the pick carried it. */
  at?: Point2D;
  /** The view's composed centre — the PLACE stage's outward reference. */
  viewAnchor?: Point2D;
  /** The view's drawn extents, which the auto placement clears. */
  bounds?: SheetBox;
}

/** Do two centre picks name the same hole (same view, same circle)? */
export const sameCentre = (a: CentreTarget, b: CentreTarget): boolean =>
  a.projection === b.projection &&
  edgeSignatureKey(a.sourceEdge) === edgeSignatureKey(b.sourceEdge);

/** Below this (sheet mm) two centres share an x or a y. */
const ALIGNED_MM = 1e-6;

/**
 * The orientation a fresh centre-to-centre dimension opens with: along the
 * larger of the two separations, so the first proposal is the one a drafter
 * would most likely want (a row of holes reads horizontal, a column vertical).
 */
export function initialOrientation(p: Point2D, q: Point2D): CentreOrientation {
  return Math.abs(q.x - p.x) >= Math.abs(q.y - p.y) ? "horizontal" : "vertical";
}

/**
 * The Fusion placement rule: drag the dimension ABOVE or BELOW the two centres
 * and it measures horizontally; drag it to their LEFT or RIGHT and it measures
 * vertically. Inside the box the two centres span (or diagonally outside it)
 * the current orientation holds, so the dimension does not flicker as the
 * pointer crosses a corner. Two centres on one vertical line have no
 * horizontal distance (and vice versa), so that orientation is never offered.
 */
export function orientationAt(
  pair: CentrePair,
  pointer: Point2D,
): CentreOrientation {
  const { p, q } = pair;
  if (Math.abs(q.x - p.x) < ALIGNED_MM) return "vertical";
  if (Math.abs(q.y - p.y) < ALIGNED_MM) return "horizontal";
  const outX = pointer.x < Math.min(p.x, q.x) || pointer.x > Math.max(p.x, q.x);
  const outY = pointer.y < Math.min(p.y, q.y) || pointer.y > Math.max(p.y, q.y);
  if (outY && !outX) return "horizontal";
  if (outX && !outY) return "vertical";
  return pair.orientation;
}

/**
 * The span an orientation is placed against, ordered the way the composer
 * orders its axis (compose.py `_place_linear_along`), so the client's `away`
 * side and the server's agree: aligned is the two centres themselves;
 * horizontal is the pair flattened onto their mid HEIGHT, left to right;
 * vertical onto their mid x, bottom to top (sheet space is y-down).
 */
export function centreSpan(pair: CentrePair): { a: Point2D; b: Point2D } {
  const { p, q, orientation } = pair;
  if (orientation === "aligned") return { a: p, b: q };
  const mx = (p.x + q.x) / 2;
  const my = (p.y + q.y) / 2;
  if (orientation === "horizontal") {
    const [l, r] = p.x <= q.x ? [p, q] : [q, p];
    return { a: { x: l.x, y: my }, b: { x: r.x, y: my } };
  }
  const [lo, hi] = p.y >= q.y ? [p, q] : [q, p];
  return { a: { x: mx, y: lo.y }, b: { x: mx, y: hi.y } };
}

/**
 * The offset (from the span's midpoint, on the `away` side) the composer's
 * AUTO placement gives a hole dimension: the default offset beyond the farther
 * of its two points AND beyond the view's drawn extents — a centre sits inside
 * the part, so the line must clear the part, not the hole (compose.py
 * `clear_of`). Without extents it clears the points only.
 */
export function clearedOffset(
  span: { a: Point2D; b: Point2D },
  points: readonly Point2D[],
  viewAnchor: Point2D,
  bounds: SheetBox | undefined,
): number {
  const n = awayNormal(span.a, span.b, viewAnchor);
  if (n === null) return drawing.dimensionOffsetMm;
  const along = (p: Point2D) => p.x * n.x + p.y * n.y;
  const reach = points.map(along);
  if (bounds !== undefined) {
    for (const x of [bounds.min.x, bounds.max.x]) {
      for (const y of [bounds.min.y, bounds.max.y]) reach.push(along({ x, y }));
    }
  }
  const mid = {
    x: (span.a.x + span.b.x) / 2,
    y: (span.a.y + span.b.y) / 2,
  };
  return Math.max(...reach) + drawing.dimensionOffsetMm - along(mid);
}

/**
 * The PLACE target a fresh centre-to-centre dimension opens at: the initial
 * orientation, seated where the composer's own auto placement would put it
 * (clear of the part, on the side away from the view centre).
 */
export function centrePairTarget(
  p: Point2D,
  q: Point2D,
  viewAnchor: Point2D,
  bounds?: SheetBox,
): Extract<PlaceTarget, { mode: "offset" }> {
  const pair: CentrePair = { p, q, orientation: initialOrientation(p, q) };
  const span = centreSpan(pair);
  return {
    mode: "offset",
    span,
    viewAnchor,
    offsetMm: clearedOffset(span, [p, q], viewAnchor, bounds),
    centres: pair,
  };
}

/** Re-aim a live centre-to-centre placement at the pointer (orientation + offset). */
export function moveCentrePlacement(
  target: Extract<PlaceTarget, { mode: "offset" }>,
  pair: CentrePair,
  pointer: Point2D,
): Extract<PlaceTarget, { mode: "offset" }> {
  const centres = { ...pair, orientation: orientationAt(pair, pointer) };
  const span = centreSpan(centres);
  return {
    ...target,
    centres,
    span,
    offsetMm: offsetAt(span.a, span.b, target.viewAnchor, pointer),
  };
}

/**
 * Read a PLACED horizontal / vertical centre-to-centre dimension back into a
 * live placement, so it can be picked up and moved. Each witness line runs
 * from its own centre (one gap out) to past the dimension line, so walking it
 * back one gap along its OWN direction recovers that centre — whichever side
 * of the centre the dimension line sits. A centre the dimension line passes
 * through has no witness line; its dimension-line end is the centre.
 */
export function centrePlacementFromComposed(
  lines: readonly {
    role: string;
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  }[],
  viewAnchor: Point2D,
  orientation: "horizontal" | "vertical",
  gapMm: number,
): Extract<PlaceTarget, { mode: "offset" }> | null {
  const dim = lines.find((l) => l.role === "dimension");
  if (dim === undefined) return null;
  const witness = lines.filter((l) => l.role === "extension");
  const along = (pt: Point2D): number =>
    orientation === "horizontal" ? pt.x : pt.y;
  const centreAt = (end: Point2D): Point2D => {
    const w = witness.find(
      (l) => Math.abs(along({ x: l.x1, y: l.y1 }) - along(end)) < 1e-6,
    );
    if (w === undefined) return end;
    const len = Math.hypot(w.x2 - w.x1, w.y2 - w.y1);
    if (len < 1e-9) return end;
    return {
      x: w.x1 - ((w.x2 - w.x1) / len) * gapMm,
      y: w.y1 - ((w.y2 - w.y1) / len) * gapMm,
    };
  };
  const p = centreAt({ x: dim.x1, y: dim.y1 });
  const q = centreAt({ x: dim.x2, y: dim.y2 });
  const centres: CentrePair = { p, q, orientation };
  const span = centreSpan(centres);
  if (Math.hypot(span.b.x - span.a.x, span.b.y - span.a.y) < 1e-9) return null;
  const dimMid = { x: (dim.x1 + dim.x2) / 2, y: (dim.y1 + dim.y2) / 2 };
  return {
    mode: "offset",
    span,
    viewAnchor,
    offsetMm: offsetAt(span.a, span.b, viewAnchor, dimMid),
    centres,
  };
}
