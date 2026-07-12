/**
 * Precise sketch picking — pure math, no three.js, no store.
 *
 * The select tool addresses two grains: a *point pick* (a defining point —
 * endpoint, center, position) and an *entity pick* (the curve itself).
 * Points win within tolerance because they are the finer target; repeated
 * clicks at the same spot cycle through stacked candidates (two endpoints
 * meeting at a corner are both reachable — CAD click-through).
 */
import type { components } from "@loft/ts-client/gateway";

import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";

export type PointName = components["schemas"]["EntityPointRef"]["point"];

export type SketchPick =
  | { kind: "entity"; id: string }
  | { kind: "point"; entity: string; point: PointName };

/** Pick tolerance in *screen* pixels; the scene converts px → mm per event. */
export const PICK_TOLERANCE_PX = 8;

export function samePick(a: SketchPick, b: SketchPick): boolean {
  if (a.kind === "entity" && b.kind === "entity") return a.id === b.id;
  if (a.kind === "point" && b.kind === "point") {
    return a.entity === b.entity && a.point === b.point;
  }
  return false;
}

const dist = (a: Point2D, b: Point2D): number =>
  Math.hypot(b.x - a.x, b.y - a.y);

/** The entity's named defining points (the ones constraints can address). */
export function namedPoints(
  entity: SketchEntity,
): ReadonlyArray<{ point: PointName; at: Point2D }> {
  switch (entity.kind) {
    case "point":
      return [{ point: "position", at: entity.position }];
    case "line":
      return [
        { point: "start", at: entity.start },
        { point: "end", at: entity.end },
      ];
    case "circle":
      return [{ point: "center", at: entity.center }];
    case "arc":
      return [
        { point: "center", at: entity.center },
        { point: "start", at: entity.start },
        { point: "end", at: entity.end },
      ];
    case "spline":
      // STUB (#6b upgrades): v1 splines are non-constrained (no solver-
      // addressable named point), so they expose none to the pick/constraint
      // layer. Snapping to fit points arrives with the draw tool (#6b).
      return [];
  }
}

/** Distance from `p` to the segment a–b. */
function segmentDistance(p: Point2D, a: Point2D, b: Point2D): number {
  const abx = b.x - a.x;
  const aby = b.y - a.y;
  const lengthSq = abx * abx + aby * aby;
  if (lengthSq === 0) return dist(p, a);
  let t = ((p.x - a.x) * abx + (p.y - a.y) * aby) / lengthSq;
  t = Math.max(0, Math.min(1, t));
  return dist(p, { x: a.x + t * abx, y: a.y + t * aby });
}

/** Distance from `p` to the entity's curve (Infinity for bare points). */
export function curveDistance(p: Point2D, entity: SketchEntity): number {
  switch (entity.kind) {
    case "point":
      return Infinity; // its defining point already covers it
    case "line":
      return segmentDistance(p, entity.start, entity.end);
    case "circle":
      return Math.abs(dist(p, entity.center) - entity.radius);
    case "arc": {
      const radius = dist(entity.center, entity.start);
      const angle = Math.atan2(p.y - entity.center.y, p.x - entity.center.x);
      const startAngle = Math.atan2(
        entity.start.y - entity.center.y,
        entity.start.x - entity.center.x,
      );
      const endAngle = Math.atan2(
        entity.end.y - entity.center.y,
        entity.end.x - entity.center.x,
      );
      // CCW sweep start → end (schema invariant).
      const sweep = normalizeSweep(endAngle - startAngle);
      const toPoint = normalizeSweep(angle - startAngle);
      if (toPoint <= sweep) {
        return Math.abs(dist(p, entity.center) - radius);
      }
      return Math.min(dist(p, entity.start), dist(p, entity.end));
    }
    case "spline": {
      // STUB (#6b upgrades): approximate the curve by its fit-point control
      // polygon (min distance to a segment). #6b samples the true B-spline for
      // pixel-accurate picking; this keeps a spline coarsely pickable meanwhile.
      let best = Infinity;
      for (let i = 0; i + 1 < entity.points.length; i += 1) {
        best = Math.min(
          best,
          segmentDistance(
            p,
            entity.points[i] as Point2D,
            entity.points[i + 1] as Point2D,
          ),
        );
      }
      return best;
    }
  }
}

function normalizeSweep(angle: number): number {
  const TWO_PI = Math.PI * 2;
  let a = angle % TWO_PI;
  if (a < 0) a += TWO_PI;
  return a;
}

/**
 * All picks within `toleranceMm` of `at`, best first. Point picks always
 * order before entity picks (finer grain wins); within a grain, nearest
 * first, then entity order (stable for stacked corner points).
 */
export function pickCandidates(
  entities: readonly SketchEntity[],
  at: Point2D,
  toleranceMm: number,
): SketchPick[] {
  const points: Array<{ pick: SketchPick; d: number }> = [];
  const curves: Array<{ pick: SketchPick; d: number }> = [];
  for (const entity of entities) {
    for (const { point, at: position } of namedPoints(entity)) {
      const d = dist(at, position);
      if (d <= toleranceMm) {
        points.push({ pick: { kind: "point", entity: entity.id, point }, d });
      }
    }
    const d = curveDistance(at, entity);
    if (d <= toleranceMm) {
      curves.push({ pick: { kind: "entity", id: entity.id }, d });
    }
  }
  // Stable sort keeps entity order for equal distances (stacked corners).
  points.sort((a, b) => a.d - b.d);
  curves.sort((a, b) => a.d - b.d);
  return [...points.map((c) => c.pick), ...curves.map((c) => c.pick)];
}

/**
 * Click toggle rule: the first candidate not already selected gets added;
 * if every candidate is selected, the best one is removed (click-through,
 * then un-pick). No candidates → clear the selection (click on empty steel).
 */
export function toggleSelection(
  selection: readonly SketchPick[],
  candidates: readonly SketchPick[],
): SketchPick[] {
  const first = candidates[0];
  if (first === undefined) return [];
  for (const candidate of candidates) {
    if (!selection.some((pick) => samePick(pick, candidate))) {
      return [...selection, candidate];
    }
  }
  return selection.filter((pick) => !samePick(pick, first));
}
