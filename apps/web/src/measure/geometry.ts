/**
 * Measurement view logic — pure functions the overlay, the readout, and
 * PartPage share, kept out of the components so they can be unit-tested without
 * a DOM or a WebGL context. Types come from the generated client (DRY rule).
 */
import { formatLength, type LengthUnit } from "@loft/design";

import type { FeatureTreeResponse } from "../api/parts";
import type {
  EvaluateTreeRequest,
  MeasureRequest,
  MeasureResult,
  MeasureTarget,
  OverlayEdge,
  OverlayResult,
  Vec3,
} from "../api/measure";
import { MESH_LINEAR_DEFLECTION_MM } from "../api/client";
import { formatDro, formatVec3 } from "../lib/format";
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
  /**
   * Stop BEFORE this feature: the body it is built on, which is the body its
   * picked references resolve against. An edge a fillet rounds is not an edge
   * of the tip, so an edge re-pick while editing has to come from here
   * (EDGE-RESOLVE-WARN-1). An id not in the tree stops nowhere.
   */
  beforeFeatureId?: string,
): EvaluateTreeRequest {
  const live = tree.features.filter((feature) => !feature.rolled_back);
  const stop = live.findIndex((feature) => feature.id === beforeFeatureId);
  return {
    part_id: tree.part_id,
    tree_version: tree.tree_version,
    linear_deflection: MESH_LINEAR_DEFLECTION_MM,
    features: (stop < 0 ? live : live.slice(0, stop)).map((feature) => ({
      id: feature.id,
      feature: feature.feature,
    })),
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
 * The point at fraction `t` of a polyline's accumulated ARC LENGTH, in OCCT
 * coords.
 *
 * Arc length and not vertex index, and the difference is not academic: a
 * straight edge's polyline is just `[start, end]`, so an index-based "middle"
 * lands on an END VERTEX — on the corner it shares with two neighbours, where
 * their pick corridors are at least as close as its own. Interpolating by
 * length puts `t = 0.5` at `0.5·(start + end)` for that edge and at the true
 * halfway point of a tessellated curve, straddling segment included.
 *
 * Generalised from `polylineMidpoint` by PICKMARK-OCCLUDE-1, which needs other
 * points of the same edge when the mid-span is buried — one interpolation, so
 * a mark that MOVES cannot land in a different place from the one that stays.
 */
export function polylineAt(polyline: readonly Vec3[], t: number): Vec3 {
  if (polyline.length === 0) return { x: 0, y: 0, z: 0 };
  if (polyline.length === 1) return polyline[0] as Vec3;

  const dist = (a: Vec3, b: Vec3): number =>
    Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z);

  let total = 0;
  for (let i = 1; i < polyline.length; i += 1) {
    total += dist(polyline[i - 1] as Vec3, polyline[i] as Vec3);
  }
  const want = total * Math.min(1, Math.max(0, t));

  let acc = 0;
  for (let i = 1; i < polyline.length; i += 1) {
    const a = polyline[i - 1] as Vec3;
    const b = polyline[i] as Vec3;
    const seg = dist(a, b);
    if (acc + seg >= want) {
      const local = seg === 0 ? 0 : (want - acc) / seg;
      return {
        x: a.x + (b.x - a.x) * local,
        y: a.y + (b.y - a.y) * local,
        z: a.z + (b.z - a.z) * local,
      };
    }
    acc += seg;
  }
  return polyline[polyline.length - 1] as Vec3;
}

/**
 * The point at HALF the accumulated arc length — an edge's pick-mark anchor,
 * and the point its accessible name describes.
 */
export function polylineMidpoint(polyline: readonly Vec3[]): Vec3 {
  return polylineAt(polyline, 0.5);
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
  return formatDro(value, "mm");
}

/** The measured angle in degrees, or "—" when there is no single direction. */
export function formatAngleDeg(angle: number | null | undefined): string {
  return angle === null || angle === undefined ? "—" : `${angle.toFixed(1)}°`;
}

// ---------------------------------------------------------------------------
// CIRCLES — centre-to-centre (MEASURE-LABEL-PITCH-1)
// ---------------------------------------------------------------------------

/**
 * The kernel's own "same point" tolerance for edge signature points (mm) —
 * `geometry.kernel.edges._EDGE_POINT_TOL_MM`. A full circle stores its seam
 * twice, so `end_a` and `end_b` coincide within THIS, not an ad-hoc epsilon.
 */
const EDGE_POINT_TOL_MM = 1e-6;

/** The circle a circular edge lies on, and whether the edge is all of it. */
export interface EdgeCircle {
  /** World-mm centre (OCCT Z-up). */
  centre: Vec3;
  radius: number;
  /** A full circle (seam stored twice) rather than an arc. */
  closed: boolean;
}

const sub = (a: Vec3, b: Vec3): Vec3 => ({
  x: a.x - b.x,
  y: a.y - b.y,
  z: a.z - b.z,
});
const dot = (a: Vec3, b: Vec3): number => a.x * b.x + a.y * b.y + a.z * b.z;
const cross = (a: Vec3, b: Vec3): Vec3 => ({
  x: a.y * b.z - a.z * b.y,
  y: a.z * b.x - a.x * b.z,
  z: a.x * b.y - a.y * b.x,
});
const norm = (a: Vec3): number => Math.hypot(a.x, a.y, a.z);

/**
 * The circle of a circular edge, read off its stage-1 SIGNATURE — three exact
 * points on the B-rep curve the kernel already sends (`end_a`, `end_b`, and
 * `midpoint` at curve parameter 0.5). Not a fit to the tessellated polyline:
 * these are kernel-evaluated points ON the exact circle, so the centre is exact
 * to floating-point round-off, far inside the kernel's 1e-7 m tolerance.
 *
 * The SAME derivation the kernel's durable edge resolver uses
 * (`geometry.kernel.edges._circle_centre`): a FULL circle stores its seam twice
 * with `midpoint` diametrically opposite, so the centre is their midpoint; an
 * ARC's centre is the circumcentre of its three points
 * (`a + ((|u|^2 v - |v|^2 u) x (u x v)) / (2 |u x v|^2)`, `u = m - a`,
 * `v = b - a`). `null` for anything that is not a circle, or for three
 * collinear points — never a divide-by-zero.
 */
export function edgeCircle(edge: OverlayEdge): EdgeCircle | null {
  const sig = edge.signature;
  if (sig.curve !== "circle") return null;
  const a = sig.end_a;
  const b = sig.end_b;
  const m = sig.midpoint;
  let centre: Vec3;
  let closed = false;
  if (norm(sub(a, b)) <= EDGE_POINT_TOL_MM) {
    closed = true;
    centre = { x: (a.x + m.x) / 2, y: (a.y + m.y) / 2, z: (a.z + m.z) / 2 };
  } else {
    const u = sub(m, a);
    const v = sub(b, a);
    const normal = cross(u, v);
    const denominator = 2 * dot(normal, normal);
    if (!(denominator > 0)) return null;
    const uu = dot(u, u);
    const vv = dot(v, v);
    const weighted = {
      x: v.x * uu - u.x * vv,
      y: v.y * uu - u.y * vv,
      z: v.z * uu - u.z * vv,
    };
    const offset = cross(weighted, normal);
    centre = {
      x: a.x + offset.x / denominator,
      y: a.y + offset.y / denominator,
      z: a.z + offset.z / denominator,
    };
  }
  const radius = norm(sub(a, centre));
  if (!(radius > 0)) return null;
  return { centre, radius, closed };
}

/** The overlay edge a pick names, or null (a vertex, or no overlay). */
function pickedEdge(
  pick: MeasurePick,
  overlay: OverlayResult | null,
): OverlayEdge | null {
  if (pick.kind !== "edge" || overlay === null) return null;
  return overlay.edges[pick.index] ?? null;
}

/** The circle a pick lies on, or null when the pick is not a circular edge. */
export function pickCircle(
  pick: MeasurePick,
  overlay: OverlayResult | null,
): EdgeCircle | null {
  const edge = pickedEdge(pick, overlay);
  return edge === null ? null : edgeCircle(edge);
}

/**
 * A reading taken between CENTRES rather than between nearest points — what an
 * engineer means by the distance between two holes (their pitch).
 * `centre_centre`: both picks are circular edges. `centre_point`: one circular
 * edge and one vertex. `from`/`to` keep the pick order and
 * `delta = to - from`, the same B - A convention as `MeasureResult.delta`.
 */
export interface CentreReading {
  kind: "centre_centre" | "centre_point";
  /** Pick A is the circle — decides "Centre to point" vs "Point to centre". */
  centreFirst: boolean;
  from: Vec3;
  to: Vec3;
  delta: Vec3;
  distance: number;
}

/**
 * The centre-based reading for a pick pair, or null when neither pick is a
 * circle — or one is and the other is a non-circular edge, which has no single
 * point to measure to. Pure arithmetic on kernel-exact points; the MINIMUM
 * distance still comes from the kernel's `/measure`.
 */
export function centreReading(
  a: MeasurePick,
  b: MeasurePick,
  overlay: OverlayResult | null,
): CentreReading | null {
  const circleA = pickCircle(a, overlay);
  const circleB = pickCircle(b, overlay);
  if (circleA === null && circleB === null) return null;
  const anchor = (pick: MeasurePick, circle: EdgeCircle | null): Vec3 | null =>
    circle !== null
      ? circle.centre
      : pick.kind === "vertex"
        ? pick.position
        : null;
  const from = anchor(a, circleA);
  const to = anchor(b, circleB);
  if (from === null || to === null) return null;
  const delta = sub(to, from);
  return {
    kind:
      circleA !== null && circleB !== null ? "centre_centre" : "centre_point",
    centreFirst: circleA !== null,
    from,
    to,
    delta,
    distance: norm(delta),
  };
}

/** The readout eyebrow that names a centre reading. */
export function centreReadingLabel(reading: CentreReading): string {
  if (reading.kind === "centre_centre") return "Centre to centre";
  return reading.centreFirst ? "Centre to point" : "Point to centre";
}

/**
 * The eyebrow for the KERNEL's reading. It is always the minimum distance
 * between the two targets. Between two points that is simply "the distance";
 * wherever an edge is involved it must say "minimum", because two picked holes
 * on a 25 mm pitch read 17 mm rim to rim (F-7).
 */
export function minimumReadingLabel(kind: MeasureResult["kind"]): string {
  return kind === "point_point" ? "Distance" : "Min distance";
}

/**
 * A coordinate triple for a LABEL, in the document unit at readout precision.
 * Sub-tolerance round-off (a centre computed as -1e-15) reads 0, never "-0".
 */
function labelVec3(v: Vec3, unit: LengthUnit): string {
  const clean = (n: number) => (Math.abs(n) < EDGE_POINT_TOL_MM ? 0 : n);
  return formatVec3({ x: clean(v.x), y: clean(v.y), z: clean(v.z) }, unit);
}

/** A bare length for a label ("8", "0.315"), document unit, no suffix. */
function labelLength(mm: number, unit: LengthUnit): string {
  return formatLength(mm, unit, { unitSuffix: false });
}

/**
 * Human name for a resolved pick — the readout's "from / to" descriptor.
 *
 * It carries IDENTITY, not just an ordinal (F-7: `Edge 5 -> Edge 6` could not
 * say which two holes had been measured). A circle names its diameter and
 * centre, an arc its radius and centre, a line its length and mid-span,
 * anything else its mid-span, all in the document unit. The `Edge N` ordinal
 * stays as the prefix: it is the name the viewport mark carries.
 */
export function describePick(
  pick: MeasurePick,
  overlay: OverlayResult | null = null,
  unit: LengthUnit = "mm",
): string {
  if (pick.kind === "vertex") {
    return `Vertex ${labelVec3(pick.position, unit)} ${unit}`;
  }
  const name = `Edge ${pick.index + 1}`;
  const edge = pickedEdge(pick, overlay);
  if (edge === null) return name;
  const circle = edgeCircle(edge);
  if (circle !== null) {
    const size = circle.closed
      ? `Ø${labelLength(circle.radius * 2, unit)} circle`
      : `R${labelLength(circle.radius, unit)} arc`;
    return `${name} · ${size}, centre ${labelVec3(circle.centre, unit)} ${unit}`;
  }
  const mid = labelVec3(edge.signature.midpoint, unit);
  if (edge.signature.curve === "line") {
    const length = labelLength(edge.signature.length_mm, unit);
    return `${name} · ${length} ${unit} line, mid ${mid} ${unit}`;
  }
  return `${name} · curve, mid ${mid} ${unit}`;
}

/**
 * The accessible name of an edge's measure mark: WHICH edge, in words a screen
 * reader speaks ("diameter", not "Ø"). A circle is located by its centre and
 * size; any other edge by its mid-span, in the grammar the other pick layers
 * use (`centred at x, y, z millimetres`).
 */
export function measureEdgeLabel(index: number, edge: OverlayEdge): string {
  const name = `Edge ${index + 1}, ${edge.kind}`;
  const round = (n: number) => {
    const r = Math.round(n * 100) / 100;
    return Object.is(r, -0) ? 0 : r;
  };
  const at = (v: Vec3) => `${round(v.x)}, ${round(v.y)}, ${round(v.z)}`;
  const circle = edgeCircle(edge);
  if (circle !== null) {
    const size = circle.closed
      ? `diameter ${round(circle.radius * 2)}`
      : `radius ${round(circle.radius)}`;
    return `${name}, ${size}, centre at ${at(circle.centre)} millimetres`;
  }
  return `${name}, centred at ${at(polylineMidpoint(edge.polyline))} millimetres`;
}
