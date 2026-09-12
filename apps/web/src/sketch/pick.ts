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

/** The point on the segment a–b nearest `p`. */
function closestOnSegment(p: Point2D, a: Point2D, b: Point2D): Point2D {
  const abx = b.x - a.x;
  const aby = b.y - a.y;
  const lengthSq = abx * abx + aby * aby;
  if (lengthSq === 0) return a;
  let t = ((p.x - a.x) * abx + (p.y - a.y) * aby) / lengthSq;
  t = Math.max(0, Math.min(1, t));
  return { x: a.x + t * abx, y: a.y + t * aby };
}

/** The point on a circle of `radius` about `center` nearest `p`. */
function closestOnCircle(p: Point2D, center: Point2D, radius: number): Point2D {
  const d = dist(p, center);
  // Dead centre has no nearest point — every point on the circle is equally
  // near. Answering +X keeps the function total and the distance |0 - r| = r,
  // which is the reading `curveDistance` gave before this was factored out.
  const ux = d === 0 ? 1 : (p.x - center.x) / d;
  const uy = d === 0 ? 0 : (p.y - center.y) / d;
  return { x: center.x + ux * radius, y: center.y + uy * radius };
}

/**
 * The point ON the entity's curve nearest `p`, or null for a bare point (whose
 * defining point already covers it).
 *
 * This is the SAME resolution {@link curveDistance} ranks candidates by — the
 * distance is now derived from it rather than computed alongside it, because the
 * pick marker (SEL-2) has to stand exactly where the hit was measured. Two
 * routines that agreed by inspection would be one edit away from a mark that
 * names a curve while standing somewhere else on it.
 */
export function closestOnCurve(
  p: Point2D,
  entity: SketchEntity,
): Point2D | null {
  switch (entity.kind) {
    case "point":
      return null;
    case "line":
      return closestOnSegment(p, entity.start, entity.end);
    case "circle":
      return closestOnCircle(p, entity.center, entity.radius);
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
      if (toPoint <= sweep) return closestOnCircle(p, entity.center, radius);
      return dist(p, entity.start) <= dist(p, entity.end)
        ? entity.start
        : entity.end;
    }
    case "spline": {
      // Measure to the SAMPLED interpolant (the same curve the viewport draws),
      // so hover/pick tracks the ink the user sees rather than the straight
      // fit-point polygon. Matches `entityPolylines`' centripetal Catmull-Rom.
      const sampled = sampleSpline(entity.points);
      let best: Point2D | null = null;
      let bestDistance = Infinity;
      for (let i = 0; i + 1 < sampled.length; i += 1) {
        const on = closestOnSegment(
          p,
          sampled[i] as Point2D,
          sampled[i + 1] as Point2D,
        );
        const d = dist(p, on);
        if (d < bestDistance) {
          bestDistance = d;
          best = on;
        }
      }
      return best;
    }
  }
}

/** Distance from `p` to the entity's curve (Infinity for bare points). */
export function curveDistance(p: Point2D, entity: SketchEntity): number {
  const on = closestOnCurve(p, entity);
  return on === null ? Infinity : dist(p, on);
}

/**
 * WHERE a pick's mark stands, in plane mm: the named point for a point pick, the
 * spot on the curve nearest `at` for an entity pick. Null when the pick does not
 * resolve against `entities` (a stale hover after an undo, say) — the caller
 * draws nothing rather than a mark at the origin.
 */
export function pickAnchor(
  pick: SketchPick,
  entities: readonly SketchEntity[],
  at: Point2D,
): Point2D | null {
  const id = pick.kind === "entity" ? pick.id : pick.entity;
  const entity = entities.find((candidate) => candidate.id === id);
  if (entity === undefined) return null;
  if (pick.kind === "entity") return closestOnCurve(at, entity);
  return namedPoints(entity).find((n) => n.point === pick.point)?.at ?? null;
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
  const taken = replacementPick(selection, candidates);
  return taken === null ? [] : [taken];
}

/**
 * WHICH single candidate a plain click will land on — the cycle rule, stated
 * once so two surfaces can read it.
 *
 * It exists because the hover marker (SEL-2) has to NAME that pick before the
 * click, and `candidates[0]` is the wrong answer precisely when it matters: with
 * one thing already selected, a repeat click walks to the NEXT candidate, so a
 * mark reading the head of the list would promise a pick the click does not
 * make — the discoverability of click-through inverted into a lie about it.
 * The click rule itself is unchanged; `applyPick` above is this function plus
 * the wrapping into a selection.
 */
export function replacementPick(
  selection: readonly SketchPick[],
  candidates: readonly SketchPick[],
): SketchPick | null {
  const first = candidates[0];
  if (first === undefined) return null;
  // Cycle only when the selection IS exactly one of these candidates — the
  // click-through case. Anything else (a different pick, a multi-selection)
  // starts over at the best candidate.
  const sole = selection.length === 1 ? selection[0] : undefined;
  if (sole !== undefined) {
    const at = candidates.findIndex((candidate) => samePick(candidate, sole));
    if (at >= 0) return candidates[(at + 1) % candidates.length] as SketchPick;
  }
  return first;
}
