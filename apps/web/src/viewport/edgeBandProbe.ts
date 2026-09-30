/**
 * THE EDGE BAND'S HIT-TEST AT ONE SCREEN POINT — the raycasts around
 * `resolveBandIntersections`, lifted out of `EdgeBandLayer` so the exact code
 * the pointer and the mark seats run can be unit-tested against real three.js
 * objects (a `LineSegments2` band and a surface mesh) without a canvas.
 *
 * Two raycasts live here, and the second is the review fix to
 * EDGE-MARK-OVERLAP:
 *
 *  1. the CURSOR ray: every band segment inside the 24 px corridor, each with
 *     its `screenGapPx`, plus the surface hits for the occlusion test;
 *  2. the OWN-PIXEL ray, asked only for a band hit that is nearer the cursor
 *     than the depth-nearest one: cast through the hit's own projected point,
 *     it proves the edge is in front of every drawn surface THERE. The body-
 *     scale occlusion bias cannot prove that on a wall thinner than the bias
 *     (see `resolveBandIntersections`), and without the proof an edge hidden
 *     behind a 2 mm wall beat the visible rim beside it.
 */
import { Raycaster, Vector2, Vector3 } from "three";
import type { Camera, Intersection, Object3D } from "three";

import { resolveBandIntersections, type BandIntersection } from "./edgeBand";

/**
 * How far in front of an edge a surface may be, at the edge's own pixel, and
 * the edge still count as visible — in SCREEN pixels, converted to depth at
 * the edge's distance. An edge lies ON the faces it bounds, so a ray through
 * its own pixel meets the surface at the edge itself, give or take float error
 * and the chord sag between the edge's polyline and the face tessellation.
 * Three pixels is ~0.3 mm at the enclosure's framing: ample for that, and an
 * order of magnitude inside a 2 mm wall.
 */
export const EDGE_VISIBLE_TOLERANCE_PX = 3;

/** A band hit as three-stdlib's `LineSegments2.raycast` reports it. */
type BandProbeHit = Intersection & {
  /** The segment's point nearest the ray, in world space. */
  pointOnLine?: Vector3;
  screenGapPx?: number;
};

/** World size of one screen pixel at `distance` from the camera. */
function worldPerPixel(camera: Camera, distance: number, height: number) {
  const c = camera as unknown as {
    isPerspectiveCamera?: boolean;
    isOrthographicCamera?: boolean;
    fov?: number;
    top?: number;
    bottom?: number;
    zoom?: number;
  };
  if (c.isOrthographicCamera === true) {
    return ((c.top ?? 1) - (c.bottom ?? -1)) / (c.zoom ?? 1) / height;
  }
  const fov = ((c.fov ?? 50) * Math.PI) / 180;
  return (2 * distance * Math.tan(fov / 2)) / height;
}

/** Scratch held across calls: the probe runs per pointer move and per seat. */
const cursorRaycaster = new Raycaster();
const ownRaycaster = new Raycaster();
const ndc = new Vector2();
const ownNdc = new Vector2();
const projected = new Vector3();
const cursorHits: Intersection[] = [];
const ownHits: Intersection[] = [];

/** Everything one band hit-test needs. */
export interface BandProbeTargets {
  camera: Camera;
  /** Canvas size in CSS px. */
  width: number;
  height: number;
  /** The `LineSegments2` carrying the corridors. */
  band: Object3D;
  /** The drawn surface for occlusion, or null when there is none. */
  surface: Object3D | null;
  edgeOfSegment: Uint32Array;
  bias: number;
}

/**
 * Is this band hit in front of every drawn surface at its OWN pixel?
 */
export function visibleAtOwnPixel(
  hit: BandIntersection,
  targets: BandProbeTargets,
): boolean {
  const point = (hit as unknown as BandProbeHit).pointOnLine;
  if (point === undefined) return false;
  if (targets.surface === null) return true;
  projected.copy(point).project(targets.camera);
  ownNdc.set(projected.x, projected.y);
  ownRaycaster.setFromCamera(ownNdc, targets.camera);
  ownHits.length = 0;
  ownRaycaster.intersectObject(targets.surface, false, ownHits);
  const first = ownHits[0];
  if (first === undefined) return true;
  const distance = ownRaycaster.ray.origin.distanceTo(point);
  const tolerance =
    EDGE_VISIBLE_TOLERANCE_PX *
    worldPerPixel(targets.camera, distance, targets.height);
  return first.distance >= distance - tolerance;
}

/**
 * Which edge a pointer at this NDC point addresses, or null.
 */
export function resolveBandAt(
  ndcX: number,
  ndcY: number,
  targets: BandProbeTargets,
): number | null {
  const { camera, band, surface } = targets;
  ndc.set(ndcX, ndcY);
  cursorRaycaster.setFromCamera(ndc, camera);
  cursorHits.length = 0;
  cursorRaycaster.intersectObject(band, false, cursorHits);
  const halfW = targets.width / 2;
  const halfH = targets.height / 2;
  // Measured before the surface hits join the list, so every entry here is a
  // band hit carrying three-stdlib's `pointOnLine`.
  for (const hit of cursorHits as BandProbeHit[]) {
    if (hit.pointOnLine === undefined) continue;
    projected.copy(hit.pointOnLine).project(camera);
    hit.screenGapPx = Math.hypot(
      (projected.x - ndcX) * halfW,
      (projected.y - ndcY) * halfH,
    );
  }
  // `intersectObject` sorts the whole list after appending, so band and
  // surface hits arrive near -> far together.
  if (surface !== null)
    cursorRaycaster.intersectObject(surface, false, cursorHits);
  return resolveBandIntersections(
    cursorHits as unknown as BandIntersection[],
    { band, surface },
    targets.edgeOfSegment,
    targets.bias,
    (hit) => visibleAtOwnPixel(hit, targets),
  );
}
