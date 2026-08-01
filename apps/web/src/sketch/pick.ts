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
import { sampleSpline } from "./spline";
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
      // A spline's fit points ARE its constraint-addressable points: the Nth
      // fit point is `fitN` — zero-based, no leading zeros (the EntityPointRef
      // contract). Exposing them here is the whole seam: a fit point then
      // picks, hovers, selects, and constrains (coincident / fixed / symmetric)
      // through the exact same path as a line's `start`/`end` — it is just
      // another EntityPointRef.
      return entity.points.map((at, index) => ({
        point: `fit${index}`,
        at,
      }));
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
      // Measure to the SAMPLED interpolant (the same curve the viewport draws),
      // so hover/pick tracks the ink the user sees rather than the straight
      // fit-point polygon. Matches `entityPolylines`' centripetal Catmull-Rom.
      const sampled = sampleSpline(entity.points);
      let best = Infinity;
      for (let i = 0; i + 1 < sampled.length; i += 1) {
        best = Math.min(
          best,
          segmentDistance(p, sampled[i] as Point2D, sampled[i + 1] as Point2D),
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
 *
 * This is the ADD grain — reached by a modifier-click (`applyPick` below) and
 * by the DOM fit-point handles, which are `aria-pressed` buttons and so are
 * toggles by contract.
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

/**
 * How a click composes with the standing selection.
 * `replace` = a plain click; `add` = Shift or Ctrl/Cmd held.
 */
export type PickMode = "replace" | "add";

/**
 * Apply one click to the selection.
 *
 * A PLAIN click REPLACES (FB-14, founder session 2026-08-01). It used to
 * append: clicking line A then line B left BOTH selected, so `distance`
 * refused with "Select one line to dimension" while the user believed they had
 * selected one line — and a user hunting for a click that works (FB-12) built
 * a selection that could not be dimensioned. Every tool a working engineer
 * comes from replaces on a plain click and adds on a modifier.
 *
 * Multi-entity constraints (parallel / perpendicular / equal / symmetric /
 * concentric / coincident) are authored by holding **Shift** or **Ctrl/Cmd**,
 * which switches this to the toggle grain above. Both modifiers, because Shift
 * is the CAD convention (Onshape, Plasticity, Rhino) and Ctrl/Cmd is the
 * desktop-selection one (SolidWorks, Fusion; Cmd on macOS, Ctrl elsewhere) —
 * neither is bound to anything else while the select tool is live.
 *
 * Click-through survives the change: repeated plain clicks on stacked
 * candidates (the two endpoints meeting at a corner) CYCLE, one at a time,
 * instead of piling up. Empty steel clears — unless a modifier is held, where
 * a miss must not throw away the selection being assembled.
 */
export function applyPick(
  selection: readonly SketchPick[],
  candidates: readonly SketchPick[],
  mode: PickMode,
): SketchPick[] {
  if (mode === "add") {
    if (candidates.length === 0) return [...selection];
    return toggleSelection(selection, candidates);
  }
  const first = candidates[0];
  if (first === undefined) return [];
  // Cycle only when the selection IS exactly one of these candidates — the
  // click-through case. Anything else (a different pick, a multi-selection)
  // starts over at the best candidate.
  const sole = selection.length === 1 ? selection[0] : undefined;
  if (sole !== undefined) {
    const at = candidates.findIndex((candidate) => samePick(candidate, sole));
    if (at >= 0) {
      return [candidates[(at + 1) % candidates.length] as SketchPick];
    }
  }
  return [first];
}
