/**
 * Measurement view logic — pure functions the overlay, the readout, and
 * PartPage share, kept out of the components so they can be unit-tested without
 * a DOM or a WebGL context. Types come from the generated client (DRY rule).
 */
import type { FeatureTreeResponse } from "../api/parts";
import type {
  EvaluateTreeRequest,
  MeasureRequest,
  MeasureTarget,
  OverlayResult,
  Vec3,
} from "../api/measure";
import { MESH_LINEAR_DEFLECTION_MM } from "../api/client";
import { formatDroMm } from "../lib/format";
import { occtToSceneTuple } from "../sketch/plane";

/** A resolved measurement pick, ready to become a `MeasureTarget`. */
export type MeasurePick =
  | { kind: "vertex"; index: number; position: Vec3 }
  | { kind: "edge"; index: number };

/**
 * Reconstruct the `EvaluateTreeRequest` the geometry service needs from the
 * documents feature tree — the rollback bar is applied client-side (drop the
 * rolled-back suffix) so geometry receives exactly the evaluated prefix, the
 * same body the viewport renders. Presentation deflection matches the mesh.
 */
export function buildEvaluateTree(
  tree: FeatureTreeResponse,
): EvaluateTreeRequest {
  return {
    part_id: tree.part_id,
    tree_version: tree.tree_version,
    linear_deflection: MESH_LINEAR_DEFLECTION_MM,
    features: tree.features
      .filter((feature) => !feature.rolled_back)
      .map((feature) => ({ id: feature.id, feature: feature.feature })),
  };
}

/**
 * OCCT world-mm (Z-up) → three.js scene (Y-up), matching the Z-up→Y-up node
 * rotation build123d bakes into the GLB (`(x, y, z) → (x, z, -y)`), so the
 * overlay lands exactly on the rendered body. The measurement itself always
 * uses the ORIGINAL Z-up coordinates — this transform is presentation only.
 */
export function occtToScene(v: Vec3): [number, number, number] {
  // THE one OCCT→scene rotation lives in `sketch/plane` (shared with the
  // on-face sketch basis — CLAUDE.md DRY rule); -0 is normalised there.
  const [x, y, z] = occtToSceneTuple([v.x, v.y, v.z]);
  return [x, y, z];
}

/** A polyline's scene-space segment endpoints (pairs) for a LineSegments draw. */
export function polylineSegments(polyline: readonly Vec3[]): Float32Array {
  const pairs = Math.max(polyline.length - 1, 0);
  const out = new Float32Array(pairs * 6);
  for (let i = 0; i < pairs; i += 1) {
    const a = occtToScene(polyline[i] as Vec3);
    const b = occtToScene(polyline[i + 1] as Vec3);
    out.set(a, i * 6);
    out.set(b, i * 6 + 3);
  }
  return out;
}

/**
 * The point at HALF the accumulated arc length of a polyline, in OCCT coords —
 * the anchor for an edge's pick-mark. A straight edge's polyline is just
 * `[start, end]`, so the mark lands at `0.5·(start+end)` (the visual middle),
 * never on the end vertex; a tessellated curve's mark lands where its arc
 * length crosses the halfway point (interpolated within the straddling
 * segment), so it always sits mid-span and never coincides with a corner.
 */
export function polylineMidpoint(polyline: readonly Vec3[]): Vec3 {
  if (polyline.length === 0) return { x: 0, y: 0, z: 0 };
  if (polyline.length === 1) return polyline[0] as Vec3;

  const dist = (a: Vec3, b: Vec3): number =>
    Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z);

  let total = 0;
  for (let i = 1; i < polyline.length; i += 1) {
    total += dist(polyline[i - 1] as Vec3, polyline[i] as Vec3);
  }
  const half = total / 2;

  let acc = 0;
  for (let i = 1; i < polyline.length; i += 1) {
    const a = polyline[i - 1] as Vec3;
    const b = polyline[i] as Vec3;
    const seg = dist(a, b);
    if (acc + seg >= half) {
      const t = seg === 0 ? 0 : (half - acc) / seg;
      return {
        x: a.x + (b.x - a.x) * t,
        y: a.y + (b.y - a.y) * t,
        z: a.z + (b.z - a.z) * t,
      };
    }
    acc += seg;
  }
  return polyline[polyline.length - 1] as Vec3;
}

export interface OverlayBounds {
  min: [number, number, number];
  max: [number, number, number];
  diagonal: number;
}

/** Scene-space bounds of the overlay vertices — sizes the pick thresholds. */
export function overlayBounds(overlay: OverlayResult): OverlayBounds {
  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  for (const v of overlay.vertices) {
    const p = occtToScene(v);
    for (let a = 0; a < 3; a += 1) {
      min[a] = Math.min(min[a] as number, p[a] as number);
      max[a] = Math.max(max[a] as number, p[a] as number);
    }
  }
  if (!Number.isFinite(min[0])) {
    return { min: [0, 0, 0], max: [0, 0, 0], diagonal: 0 };
  }
  const dx = (max[0] as number) - (min[0] as number);
  const dy = (max[1] as number) - (min[1] as number);
  const dz = (max[2] as number) - (min[2] as number);
  return { min, max, diagonal: Math.hypot(dx, dy, dz) };
}

/** A pick → its `MeasureTarget` (a vertex echoes its exact coords). */
export function pickToTarget(pick: MeasurePick): MeasureTarget {
  return pick.kind === "vertex"
    ? { kind: "point", position: pick.position }
    : { kind: "edge", index: pick.index };
}

/** True when an edge target is present and therefore `tree` is required. */
export function needsTree(a: MeasurePick, b: MeasurePick): boolean {
  return a.kind === "edge" || b.kind === "edge";
}

/**
 * Build the `/measure` request for two picks. `tree` is attached iff either
 * target is an edge — the backend's headline rule (an edge index is only
 * meaningful against the tree sent in the same request).
 */
export function buildMeasureRequest(
  a: MeasurePick,
  b: MeasurePick,
  tree: EvaluateTreeRequest,
): MeasureRequest {
  const request: MeasureRequest = { a: pickToTarget(a), b: pickToTarget(b) };
  if (needsTree(a, b)) request.tree = tree;
  return request;
}

/** "10, 20, 30" — a Vec3 in compact mm form (no unit; the cell adds it). */
export function formatVec3Mm(v: Vec3): string {
  return [v.x, v.y, v.z]
    .map((n) => (Object.is(n, -0) ? 0 : n).toFixed(2))
    .join(", ");
}

/** The measured distance, fixed to two decimals (mm) — the hero numeral. */
export function formatDistanceMm(distance: number): string {
  return distance.toFixed(2);
}

/** Signed component delta, machine-readout style ("+10.00"). */
export function formatDeltaMm(value: number): string {
  return formatDroMm(value);
}

/** The measured angle in degrees, or "—" when there is no single direction. */
export function formatAngleDeg(angle: number | null | undefined): string {
  return angle === null || angle === undefined ? "—" : `${angle.toFixed(1)}°`;
}

/** Human name for a resolved pick — the readout's "from / to" descriptor. */
export function describePick(pick: MeasurePick): string {
  return pick.kind === "vertex"
    ? `Vertex ${formatVec3Mm(pick.position)}`
    : `Edge ${pick.index + 1}`;
}
