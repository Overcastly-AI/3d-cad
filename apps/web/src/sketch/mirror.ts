/**
 * Sketch mirror — pure geometry + selection helpers, no three.js, no store.
 *
 * Mirror reflects a set of target entities about an axis line and ADDS the
 * copies (sources untouched), exactly like offset. The AUTHORITATIVE copies
 * come from the stateless geometry service (`/geometry/sketch/mirror`); the
 * functions here serve two jobs the client owns: build/validate the request
 * axis, and reflect entities LOCALLY for the live "where will it land" ghost
 * preview. Every request/response type is the generated client's (CLAUDE.md
 * DRY rule) — this module never redeclares an API shape.
 */
import type { components } from "@loft/ts-client/gateway";

import { isDatumId, withDatums, type DatumFrame } from "./datum";
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";

export type MirrorAxis = components["schemas"]["SketchMirrorRequest"]["axis"];

/**
 * Toggle an entity id in the mirror target set (whole-entity picks). Adds a
 * fresh id, removes one already present — the same click-to-toggle grain the
 * select tool uses, kept order-stable so the ghost preview is deterministic.
 */
export function toggleMirrorTarget(
  targets: readonly string[],
  id: string,
): string[] {
  return targets.includes(id)
    ? targets.filter((t) => t !== id)
    : [...targets, id];
}

/** The axis line's two defining points, or null when `id` isn't a line. */
export function axisLinePoints(
  entities: readonly SketchEntity[],
  id: string,
): { a: Point2D; b: Point2D } | null {
  const entity = entities.find((e) => e.id === id);
  if (entity === undefined || entity.kind !== "line") return null;
  return { a: entity.start, b: entity.end };
}

/**
 * The axis a mirror-axis PICK sends, or null when the pick is not a line.
 *
 * The sketch's own frame is a legal mirror axis (MIRROR-1). It arrives here as
 * a reserved datum id, and datum entities are LAZY — the origin and the two
 * axes are drawn by the viewport and only materialised into `entities` when a
 * constraint names one (see `datum.ts`) — so two things follow, and both are
 * why this resolution is a function rather than an `entities.find`:
 *
 * 1. The axis GEOMETRY is resolved against the frame-inclusive list, so the
 *    centreline resolves whether or not it has been materialised. A datum
 *    already in the buffer keeps its persisted geometry (`withDatums` adds only
 *    what is missing), so a re-opened sketch mirrors about the same line it
 *    saved.
 * 2. A datum axis is sent as a POINTS axis, never an entity ref. The request
 *    carries the sketch's entity list, and an entity ref the backend cannot
 *    find there is `sketch_target_not_found`; a points axis "no axis entity
 *    need exist in the sketch" (the DTO's own words) and reflects about the
 *    same infinite line. Mirroring about the centreline therefore adds NOTHING
 *    to the sketch — no construction line, no pins, no DOF churn — which is
 *    what "mirror adds copies, not relationships" already means everywhere
 *    else. Drawn axes keep the entity ref: it is the shorter payload and it is
 *    what every existing sketch and spec already sends.
 */
export function mirrorAxisFor(
  id: string,
  entities: readonly SketchEntity[],
  frame: DatumFrame,
): MirrorAxis | null {
  const points = axisLinePoints(withDatums(entities, frame), id);
  if (points === null) return null;
  return isDatumId(id)
    ? { kind: "points", a: points.a, b: points.b }
    : { kind: "entity", entity: id };
}

/**
 * Reflect `p` across the infinite line through a→b. A zero-length axis has no
 * direction, so the point is returned unchanged (the store/backend reject a
 * degenerate axis; this only guards the preview math against NaN).
 */
export function reflectPoint(p: Point2D, a: Point2D, b: Point2D): Point2D {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const lengthSq = dx * dx + dy * dy;
  if (lengthSq === 0) return { x: p.x, y: p.y };
  const t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / lengthSq;
  const projX = a.x + t * dx;
  const projY = a.y + t * dy;
  return { x: 2 * projX - p.x, y: 2 * projY - p.y };
}

/**
 * Reflect a whole entity across the a→b axis, for the LOCAL ghost preview
 * (synthetic id — never persisted). Reflection reverses orientation, so an
 * arc's start/end are SWAPPED to preserve the CCW-from-start invariant, the
 * same rule the backend `SketchMirrorResult` documents — the ghost matches
 * what the service will append. The construction flag is inherited.
 */
export function reflectEntity(
  entity: SketchEntity,
  a: Point2D,
  b: Point2D,
  id: string,
): SketchEntity {
  const r = (p: Point2D): Point2D => reflectPoint(p, a, b);
  switch (entity.kind) {
    case "point":
      return { ...entity, id, position: r(entity.position) };
    case "line":
      return { ...entity, id, start: r(entity.start), end: r(entity.end) };
    case "circle":
      return { ...entity, id, center: r(entity.center) };
    case "arc":
      return {
        ...entity,
        id,
        center: r(entity.center),
        start: r(entity.end),
        end: r(entity.start),
      };
    case "spline":
      // Reflecting a spline reflects each fit point in order (the interpolant
      // follows). Correct as-is — #6b only adds live rendering, not new math.
      return { ...entity, id, points: entity.points.map(r) };
  }
}
