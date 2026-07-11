/**
 * Datum-plane math — the ONE mapping between sketch-plane (u,v) mm and world
 * xyz mm, shared by the pointer raycast, the entity renderers, and the
 * camera rig.
 *
 * Bases follow build123d's `Plane.XY` / `Plane.XZ` / `Plane.YZ` exactly
 * (x_dir = u, normal = u × v), so when extrude (BACKLOG #6) maps sketches
 * into the kernel with those planes, what the viewport drew and what the
 * kernel builds agree — including XZ's −Y normal:
 *
 *   XY: u=+X v=+Y normal=+Z
 *   XZ: u=+X v=+Z normal=−Y
 *   YZ: u=+Y v=+Z normal=+X
 *
 * Pure math, no three.js imports — unit-testable in node.
 */
import type { components } from "@loft/ts-client/gateway";

export type DatumPlaneName = components["schemas"]["DatumPlaneRef"]["plane"];
export type Point2D = components["schemas"]["Point2D"];

export type Vec3Tuple = readonly [number, number, number];

export interface PlaneBasis {
  /** Sketch +u axis in world space. */
  u: Vec3Tuple;
  /** Sketch +v axis in world space. */
  v: Vec3Tuple;
  /** Plane normal (u × v) — the extrude "normal" direction. */
  normal: Vec3Tuple;
}

export const DATUM_PLANES: readonly DatumPlaneName[] = ["XY", "XZ", "YZ"];

export const PLANE_BASES: Record<DatumPlaneName, PlaneBasis> = {
  XY: { u: [1, 0, 0], v: [0, 1, 0], normal: [0, 0, 1] },
  XZ: { u: [1, 0, 0], v: [0, 0, 1], normal: [0, -1, 0] },
  YZ: { u: [0, 1, 0], v: [0, 0, 1], normal: [1, 0, 0] },
};

/** Sketch-plane (u,v) mm → world xyz mm. */
export function planeToWorld(
  plane: DatumPlaneName,
  point: Point2D,
): [number, number, number] {
  const { u, v } = PLANE_BASES[plane];
  return [
    u[0] * point.x + v[0] * point.y,
    u[1] * point.x + v[1] * point.y,
    u[2] * point.x + v[2] * point.y,
  ];
}

/** World xyz mm → sketch-plane (u,v) mm (projection along the normal). */
export function worldToPlane(plane: DatumPlaneName, world: Vec3Tuple): Point2D {
  const { u, v } = PLANE_BASES[plane];
  return {
    x: u[0] * world[0] + u[1] * world[1] + u[2] * world[2],
    y: v[0] * world[0] + v[1] * world[1] + v[2] * world[2],
  };
}

export interface CameraPose {
  position: [number, number, number];
  /** Camera up = the sketch +v axis, so +u reads left→right on screen. */
  up: [number, number, number];
  target: [number, number, number];
}

/** Normal-on camera pose for 2D authoring at `distance` mm from origin. */
export function planeCameraPose(
  plane: DatumPlaneName,
  distance: number,
): CameraPose {
  const { v, normal } = PLANE_BASES[plane];
  return {
    position: [
      normal[0] * distance,
      normal[1] * distance,
      normal[2] * distance,
    ],
    up: [v[0], v[1], v[2]],
    target: [0, 0, 0],
  };
}

/** Snap a value to the grid step; step <= 0 disables snapping. */
export function snapValue(value: number, stepMm: number): number {
  if (stepMm <= 0) return value;
  const snapped = Math.round(value / stepMm) * stepMm;
  // Normalize -0 so readouts and payloads never show "-0".
  return snapped === 0 ? 0 : snapped;
}

/** Snap a plane point to the grid step. */
export function snapPoint(point: Point2D, stepMm: number): Point2D {
  return { x: snapValue(point.x, stepMm), y: snapValue(point.y, stepMm) };
}
