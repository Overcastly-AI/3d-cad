/**
 * Sketch corner (fillet/chamfer) pure helpers — the two-line pick set and the
 * anchor the inline value editor hangs from. No three.js, no store, no network:
 * the store composes these, the scene renders them, PartPage POSTs the request.
 *
 * v1 is line-line corners only (honest UI copy): a fillet rounds the corner two
 * lines share with a tangent arc; a chamfer bevels it with a straight line. The
 * backend is the source of truth for the corner and its trim — these helpers
 * only gate the pick (max two legs) and place the editor.
 */
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";

export type CornerOp = "fillet" | "chamfer";

/** A picked corner leg — v1 corners join two lines. */
export type SketchLine = Extract<SketchEntity, { kind: "line" }>;

/**
 * Toggle a line id in the (at most two) corner pick set. Re-clicking a held leg
 * removes it; a fresh pick appends until the two legs are chosen — then further
 * picks are ignored (the value editor is open by that point). The order the two
 * legs are picked is the request's `a`/`b`; it does not change the result.
 */
export function toggleCornerPick(
  picks: readonly string[],
  id: string,
): string[] {
  if (picks.includes(id)) return picks.filter((pick) => pick !== id);
  if (picks.length >= 2) return [...picks];
  return [...picks, id];
}

const distance = (a: Point2D, b: Point2D): number =>
  Math.hypot(a.x - b.x, a.y - b.y);

const midpoint = (a: Point2D, b: Point2D): Point2D => ({
  x: (a.x + b.x) / 2,
  y: (a.y + b.y) / 2,
});

/**
 * The corner the two legs share — the closest endpoint pair's midpoint, where
 * the fillet arc / chamfer line will bridge. Used ONLY to anchor the inline
 * value editor in the viewport; the backend recomputes the true corner and
 * rejects a non-corner (parallel / no shared vertex) with
 * `sketch_corner_not_found`, so an approximate anchor is safe here.
 */
export function cornerPoint(a: SketchLine, b: SketchLine): Point2D {
  const aEnds: Point2D[] = [a.start, a.end];
  const bEnds: Point2D[] = [b.start, b.end];
  let best: { p: Point2D; q: Point2D; d: number } = {
    p: a.start,
    q: b.start,
    d: Number.POSITIVE_INFINITY,
  };
  for (const p of aEnds) {
    for (const q of bEnds) {
      const d = distance(p, q);
      if (d < best.d) best = { p, q, d };
    }
  }
  return midpoint(best.p, best.q);
}
