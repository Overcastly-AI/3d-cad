/**
 * Sketch entity → renderable primitives (pure math, no three.js).
 *
 * Every entity flattens to plane-space polylines; the viewport turns them
 * into ONE world-space LineSegments buffer per layer (buffer / preview /
 * solved) — one draw call each, nothing per-entity in the render loop.
 */
import type { components } from "@loft/ts-client/gateway";

import { planeToWorld, type DatumPlaneName, type Point2D } from "./plane";
import { namedPoints, type SketchPick } from "./pick";
import type { SketchEntity } from "./tools";

export type SolvedSketchData = components["schemas"]["SolvedSketchData"];

/** Chord count for a full circle — smooth at sketch scale, still cheap. */
export const CIRCLE_SEGMENTS = 96;

const TWO_PI = Math.PI * 2;

function circlePolyline(
  center: Point2D,
  radius: number,
  startAngle: number,
  sweep: number,
  segments: number,
): Point2D[] {
  const points: Point2D[] = [];
  for (let i = 0; i <= segments; i += 1) {
    const angle = startAngle + (sweep * i) / segments;
    points.push({
      x: center.x + radius * Math.cos(angle),
      y: center.y + radius * Math.sin(angle),
    });
  }
  return points;
}

/** Flatten one entity to plane-space polylines (arcs/circles are sampled). */
export function entityPolylines(entity: SketchEntity): Point2D[][] {
  switch (entity.kind) {
    case "point":
      return [];
    case "line":
      return [[entity.start, entity.end]];
    case "circle": {
      const polyline = circlePolyline(
        entity.center,
        entity.radius,
        0,
        TWO_PI,
        CIRCLE_SEGMENTS,
      );
      // Close the loop exactly (cos/sin of 2π drift in float).
      polyline[polyline.length - 1] = { ...(polyline[0] as Point2D) };
      return [polyline];
    }
    case "arc": {
      const radius = Math.hypot(
        entity.start.x - entity.center.x,
        entity.start.y - entity.center.y,
      );
      const startAngle = Math.atan2(
        entity.start.y - entity.center.y,
        entity.start.x - entity.center.x,
      );
      const endAngle = Math.atan2(
        entity.end.y - entity.center.y,
        entity.end.x - entity.center.x,
      );
      // CCW start → end (schema invariant); zero comes back as full sweep
      // only when start === end, which placement rejects.
      let sweep = endAngle - startAngle;
      if (sweep <= 0) sweep += TWO_PI;
      const segments = Math.max(
        8,
        Math.ceil((CIRCLE_SEGMENTS * sweep) / TWO_PI),
      );
      return [
        circlePolyline(entity.center, radius, startAngle, sweep, segments),
      ];
    }
  }
}

/** The entity's defining points (endpoints, centers) in plane space. */
export function definingPoints(entity: SketchEntity): Point2D[] {
  switch (entity.kind) {
    case "point":
      return [entity.position];
    case "line":
      return [entity.start, entity.end];
    case "circle":
      return [entity.center];
    case "arc":
      return [entity.center, entity.start, entity.end];
  }
}

/**
 * All entities of one layer → a world-space segment-pair position buffer
 * (xyzxyz per segment end), ready for a THREE.LineSegments geometry.
 */
export function entitySegmentPositions(
  entities: readonly SketchEntity[],
  plane: DatumPlaneName,
): Float32Array {
  let segmentCount = 0;
  const polylinesPerEntity: Point2D[][][] = [];
  for (const entity of entities) {
    const polylines = entityPolylines(entity);
    polylinesPerEntity.push(polylines);
    for (const polyline of polylines) {
      segmentCount += Math.max(0, polyline.length - 1);
    }
  }
  const positions = new Float32Array(segmentCount * 6);
  let offset = 0;
  for (const polylines of polylinesPerEntity) {
    for (const polyline of polylines) {
      for (let i = 0; i + 1 < polyline.length; i += 1) {
        const a = planeToWorld(plane, polyline[i] as Point2D);
        const b = planeToWorld(plane, polyline[i + 1] as Point2D);
        positions.set(a, offset);
        positions.set(b, offset + 3);
        offset += 6;
      }
    }
  }
  return positions;
}

/** Point picks of the selection/hover → world-space xyz buffer. */
export function pickedPointPositions(
  picks: readonly SketchPick[],
  entities: readonly SketchEntity[],
  plane: DatumPlaneName,
): Float32Array {
  const byId = new Map(entities.map((e) => [e.id, e]));
  const points: Point2D[] = [];
  for (const pick of picks) {
    if (pick.kind !== "point") continue;
    const entity = byId.get(pick.entity);
    if (entity === undefined) continue;
    const named = namedPoints(entity).find((n) => n.point === pick.point);
    if (named !== undefined) points.push(named.at);
  }
  const positions = new Float32Array(points.length * 3);
  points.forEach((point, i) => {
    positions.set(planeToWorld(plane, point), i * 3);
  });
  return positions;
}

/** All defining points of one layer → world-space xyz buffer for THREE.Points. */
export function definingPointPositions(
  entities: readonly SketchEntity[],
  plane: DatumPlaneName,
): Float32Array {
  const points: Point2D[] = [];
  for (const entity of entities) {
    points.push(...definingPoints(entity));
  }
  const positions = new Float32Array(points.length * 3);
  points.forEach((point, i) => {
    positions.set(planeToWorld(plane, point), i * 3);
  });
  return positions;
}
