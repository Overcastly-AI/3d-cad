/**
 * A picked body edge to the sketch entity it lands as (SKETCH-PROJECT-EDGES).
 *
 * The server re-projects every projected entity on each solve, so this is the
 * honest first draw, not the authority. It reads the edge's exact signature
 * points (never the tessellated polyline), so the first draw and the kernel's
 * agree to round-off.
 */
import type { OverlayEdge, Vec3 } from "../api/measure";
import { edgeCircle } from "../measure/geometry";
import {
  occtToSceneTuple,
  type PlaneBasis,
  type Point2D,
  worldToPlane,
} from "./plane";
import type { SketchProjection } from "./project";
import type { SketchEntity } from "./tools";

/** Why an edge cannot be projected, said to the user. */
export type ProjectRefusal =
  | { reason: "spline"; hint: string }
  | { reason: "ellipse"; hint: string }
  | { reason: "degenerate"; hint: string };

export const PROJECT_SPLINE_HINT =
  "Spline edges cannot be projected yet. Pick a straight or circular edge.";
const PROJECT_ELLIPSE_HINT =
  "That circle is tilted to the sketch, so it would project as an ellipse. Pick an edge parallel to the sketch.";
const PROJECT_DEGENERATE_HINT =
  "That edge runs straight at the sketch, so it projects to a point.";

/** Below this (mm) two projected points are the same point. */
const DEGENERATE_MM = 1e-6;

/** Off-parallel tolerance for a circle's axis vs the sketch normal (|sin|). */
const PARALLEL_TOL = 1e-6;

const toPlane = (basis: PlaneBasis, p: Vec3): Point2D =>
  worldToPlane(basis, occtToSceneTuple([p.x, p.y, p.z]));

const same = (a: Point2D, b: Point2D): boolean =>
  Math.hypot(a.x - b.x, a.y - b.y) < DEGENERATE_MM;

/**
 * The entity a picked overlay edge projects to on `basis` (the sketch plane,
 * SCENE frame — what `resolveSpecBasis` returns), or why it cannot be.
 *
 *  - A line: its two exact signature endpoints, projected. Start is `end_a`
 *    (the kernel keeps the ends in their slots on re-projection).
 *  - A circle seen face-on: a circle when closed, else a CCW arc through the
 *    exact start/mid/end. A tilted circle would be an ellipse: refused.
 *  - Anything else (spline, ellipse): refused, SKETCH-PROJECT-SPLINE.
 *
 * `anchorFeatureId` is the body-affecting feature the edge belongs to (the
 * body before the sketch), stamped as the ref's `feature_id`.
 */
export function projectOverlayEdge(
  edge: OverlayEdge,
  basis: PlaneBasis,
  anchorFeatureId: string,
  id: string,
): { entity: SketchEntity } | ProjectRefusal {
  const signature = edge.signature;
  const projection: SketchProjection = {
    edge: {
      kind: "subshape",
      feature_id: anchorFeatureId,
      subshape_type: "edge",
      selector: { selector_version: 1, signature },
    },
  };
  if (signature.curve === "line") {
    const start = toPlane(basis, signature.end_a);
    const end = toPlane(basis, signature.end_b);
    if (same(start, end)) {
      return { reason: "degenerate", hint: PROJECT_DEGENERATE_HINT };
    }
    return {
      entity: {
        id,
        kind: "line",
        start,
        end,
        construction: false,
        projection,
      },
    };
  }
  if (signature.curve !== "circle") {
    return { reason: "spline", hint: PROJECT_SPLINE_HINT };
  }
  const circle = edgeCircle(edge);
  if (circle === null) {
    return { reason: "spline", hint: PROJECT_SPLINE_HINT };
  }
  // The circle's own axis, from three exact points on it. A full circle's
  // seam and midpoint are diametric, so take a polyline sample for the third.
  const a = signature.end_a;
  const m = signature.midpoint;
  const third = circle.closed
    ? (edge.polyline[Math.floor(edge.polyline.length / 4)] ?? m)
    : signature.end_b;
  const axis = cross(sub(m, a), sub(third, a));
  const sceneNormal = basis.normal;
  const axisScene = occtToSceneTuple([axis.x, axis.y, axis.z]);
  const axisLength = Math.hypot(...axisScene);
  if (axisLength > 0) {
    const s = crossTuple(axisScene, sceneNormal);
    if (Math.hypot(...s) / axisLength > PARALLEL_TOL) {
      return { reason: "ellipse", hint: PROJECT_ELLIPSE_HINT };
    }
  }
  const center = toPlane(basis, circle.centre);
  if (circle.closed) {
    return {
      entity: {
        id,
        kind: "circle",
        center,
        radius: circle.radius,
        construction: false,
        projection,
      },
    };
  }
  // The edge's own direction (curve parameter 0 -> 1) is `start` -> `end`;
  // the signature's ends are sorted, so orient by the midpoint: a sketch arc
  // runs CCW from start to end, so swap the ends when start -> mid -> end
  // turns clockwise in the plane.
  let start = toPlane(basis, signature.end_a);
  let end = toPlane(basis, signature.end_b);
  const mid = toPlane(basis, m);
  if (same(start, end)) {
    return { reason: "degenerate", hint: PROJECT_DEGENERATE_HINT };
  }
  const turn =
    (mid.x - start.x) * (end.y - mid.y) - (mid.y - start.y) * (end.x - mid.x);
  if (turn < 0) [start, end] = [end, start];
  return {
    entity: {
      id,
      kind: "arc",
      center,
      start,
      end,
      construction: false,
      projection,
    },
  };
}

const sub = (a: Vec3, b: Vec3): Vec3 => ({
  x: a.x - b.x,
  y: a.y - b.y,
  z: a.z - b.z,
});
const cross = (a: Vec3, b: Vec3): Vec3 => ({
  x: a.y * b.z - a.z * b.y,
  y: a.z * b.x - a.x * b.z,
  z: a.x * b.y - a.y * b.x,
});
const crossTuple = (
  a: readonly [number, number, number],
  b: readonly [number, number, number],
): [number, number, number] => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
