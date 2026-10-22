/**
 * `AngleConstraint`'s convention, client-side: which corner two lines share
 * and the angle they subtend there. Split out of `constraints.ts`
 * (FILE-SIZE-RATCHET) when the angle-to-axis glyph (SKETCH-LINE-ANGLE) grew
 * it. Pure, no store.
 */
import type { SketchConstraint } from "./constraints";
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";

/** A line's two named ends — the only points an angle's corner can sit on. */
export type LineEnd = "start" | "end";

const isLineEnd = (point: string): point is LineEnd =>
  point === "start" || point === "end";

/**
 * The corner two lines are JOINED at, read symbolically from the sketch's own
 * `coincident` constraints — never from a coordinate-proximity test, which
 * would need an epsilon and would silently change meaning as geometry moved
 * (the rule `AngleConstraint` states, applied client-side so the number we
 * prefill is the number the solver will report back).
 */
export function sharedCorner(
  a: string,
  b: string,
  constraints: readonly SketchConstraint[],
): { a: LineEnd; b: LineEnd } | null {
  for (const constraint of constraints) {
    if (constraint.kind !== "coincident") continue;
    for (const [p, q] of [
      [constraint.a, constraint.b],
      [constraint.b, constraint.a],
    ] as const) {
      if (
        p.entity === a &&
        q.entity === b &&
        isLineEnd(p.point) &&
        isLineEnd(q.point)
      ) {
        return { a: p.point, b: q.point };
      }
    }
  }
  return null;
}

/** A line's direction taken AWAY from `end` (its far end minus that end). */
export function directionFrom(
  entity: SketchEntity,
  end: LineEnd | null,
): Point2D {
  if (entity.kind !== "line") return { x: 0, y: 0 };
  const [from, to] =
    end === "end" ? [entity.end, entity.start] : [entity.start, entity.end];
  return { x: to.x - from.x, y: to.y - from.y };
}

/**
 * The angle two selected lines currently subtend, in degrees, by
 * `AngleConstraint`'s convention: measured away from the corner they are
 * joined at when they have one (the interior angle a user sees at a profile
 * corner), else between their authored start→end directions. Unsigned, in
 * [0, 180] — the side is the geometry's, never the number's.
 */
export function measuredAngleDeg(
  a: SketchEntity,
  b: SketchEntity,
  constraints: readonly SketchConstraint[],
): number {
  const corner = sharedCorner(a.id, b.id, constraints);
  const u = directionFrom(a, corner?.a ?? null);
  const v = directionFrom(b, corner?.b ?? null);
  const scale = Math.hypot(u.x, u.y) * Math.hypot(v.x, v.y);
  if (scale === 0) return 0;
  const cos = Math.min(1, Math.max(-1, (u.x * v.x + u.y * v.y) / scale));
  return (Math.acos(cos) * 180) / Math.PI;
}
