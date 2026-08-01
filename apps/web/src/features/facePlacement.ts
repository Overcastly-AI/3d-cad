/**
 * THE FACE FRAME — the coordinate system a hole is dialled in, and the live
 * material check that says whether a typed point lands on metal.
 *
 * Why this exists (QA-REVIEW 2026-08-01, QA3-1): hole placement offered exactly
 * two points, the face's area centroid and its corner vertices. On a vendor
 * plate whose face centre IS the shaft bore that is a *cannot* — the seeded
 * point fails `hole_off_body` and the only alternatives are the octagon's
 * corners, so a fifth mounting hole could not be authored through the UI at all.
 * A working engineer places holes by COORDINATE and by CONCENTRICITY. Both need
 * a named frame, so the frame is the first thing this module defines.
 *
 * ── The frame ──────────────────────────────────────────────────────────────
 * AXES are the kernel's own on-face axes: `deterministicXDir(normal)` (the port
 * of `geometry.kernel.faces._deterministic_x_dir`) and `y = n x x`, i.e. THE
 * SAME basis a sketch-on-this-face gets. One frame per face across the product,
 * not a second private one for holes.
 *
 * ORIGIN is deliberately NOT the kernel's on-face origin. That origin is the
 * face's AREA CENTROID, which moves whenever a feature changes the face's
 * outline — the exact mechanism behind QA3-2's 0.065 mm eccentric ring: a
 * previously-added Ø3 hole shifted the centroid, and everything measured from it
 * moved with it. A hole position that silently means something different after
 * the next edit is not a coordinate. So the origin here is the PART ORIGIN
 * projected onto the face plane: a fixed point of the part, independent of the
 * face's outline, and on an axis-aligned face the numbers you type ARE world
 * coordinates. It is stated on screen (`HoleEditor`'s FRAME row) and drawn on
 * the model (`HolePointOverlay`), because an X/Y entry that does not say where
 * its zero is, is how QA3-2 happened.
 *
 * ── The material check ─────────────────────────────────────────────────────
 * The overlay carries every B-rep edge as a world-mm polyline. The edges that
 * lie IN the face's plane are its outline plus the mouths of everything bored
 * through it, so an even-odd crossing test over them answers "is this point on
 * metal" without a round trip — and the fitted circles say WHICH opening a bad
 * point fell into.
 *
 * It is ADVISORY, and the UI treats it that way (it warns; it never blocks the
 * write). Two honest reasons. The overlay does not record which face owns which
 * edge, so the test uses coplanarity as a proxy — correct for the ordinary part,
 * approximate where two coplanar faces of one body share an edge. And the
 * authority on whether a hole is on the body is the kernel's typed
 * `hole_off_body`, which is the control that stops a bad hole shipping silently;
 * substituting a client-side guess for it — even a good one — would hide it.
 */
import type { OverlayEdge, Vec3 } from "../api/measure";
import type { PlanarFaceSignature } from "../api/parts";
import { deterministicXDir, type Vec3Tuple } from "../sketch/plane";

/** A point in face-frame millimetres. */
export interface FacePoint {
  x: number;
  y: number;
}

/** A placed orthonormal frame on a planar face (all vectors world mm). */
export interface FaceFrame {
  /** The part origin projected onto the face plane — where (0, 0) is. */
  origin: Vec3;
  /** In-plane +X — the kernel's deterministic face x-direction. */
  u: Vec3;
  /** In-plane +Y — `normal x u`, so (u, v, n) is right-handed. */
  v: Vec3;
  /** The face's outward unit normal. */
  normal: Vec3;
}

/** A circular edge lying in the face's plane — a bore mouth or a boss rim. */
export interface FaceCircle {
  /** Centre in world mm (on the face plane). */
  center: Vec3;
  /** Centre in face-frame mm. */
  point: FacePoint;
  radiusMm: number;
}

/** Everything the placement check reads off the face, computed once. */
export interface FacePlacement {
  frame: FaceFrame;
  /** Circular edges in the face plane, largest first (bores before pin holes). */
  circles: readonly FaceCircle[];
  /**
   * Every in-plane edge as face-frame segment pairs `[ax, ay, bx, by, ...]` —
   * a flat array because the crossing test runs on every keystroke.
   */
  segments: Float64Array;
}

/** What the typed point lands on. `unknown` = the overlay has not arrived. */
export type PlacementVerdict = "material" | "opening" | "outside" | "unknown";

/** The verdict plus the opening it fell into, when there is one. */
export interface PlacementCheck {
  verdict: PlacementVerdict;
  /** The smallest in-plane circle containing the point, when `opening`. */
  circle: FaceCircle | null;
}

/** On-plane tolerance (mm). B-rep vertices are exact; this only rejects drift. */
const PLANE_TOL_MM = 1e-3;

function dot(a: Vec3, b: Vec3): number {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return {
    x: a.y * b.z - a.z * b.y,
    y: a.z * b.x - a.x * b.z,
    z: a.x * b.y - a.y * b.x,
  };
}

function unit(v: Vec3): Vec3 {
  const len = Math.hypot(v.x, v.y, v.z);
  return len === 0
    ? { x: 0, y: 0, z: 0 }
    : { x: v.x / len, y: v.y / len, z: v.z / len };
}

function tupleToVec(t: Vec3Tuple): Vec3 {
  return { x: t[0], y: t[1], z: t[2] };
}

/**
 * The face's placed frame: kernel axes, part-origin-projected origin (see the
 * module header for why the origin is NOT the centroid).
 */
export function faceFrame(signature: PlanarFaceSignature): FaceFrame {
  const normal = unit(signature.normal);
  const u = tupleToVec(deterministicXDir([normal.x, normal.y, normal.z]));
  const v = cross(normal, u);
  // The plane's closest point to the world origin: `(c . n) n`.
  const d = dot(signature.centroid, normal);
  return {
    origin: { x: normal.x * d, y: normal.y * d, z: normal.z * d },
    u,
    v,
    normal,
  };
}

/** World mm → face-frame mm (projected onto the plane). */
export function toFacePoint(frame: FaceFrame, world: Vec3): FacePoint {
  const d: Vec3 = {
    x: world.x - frame.origin.x,
    y: world.y - frame.origin.y,
    z: world.z - frame.origin.z,
  };
  return { x: dot(d, frame.u), y: dot(d, frame.v) };
}

/** Face-frame mm → world mm (`origin + u*x + v*y`), always ON the plane. */
export function toWorldPoint(frame: FaceFrame, point: FacePoint): Vec3 {
  return {
    x: frame.origin.x + frame.u.x * point.x + frame.v.x * point.y,
    y: frame.origin.y + frame.u.y * point.x + frame.v.y * point.y,
    z: frame.origin.z + frame.u.z * point.x + frame.v.z * point.y,
  };
}

/**
 * How an axis reads in world terms: `+X` / `-Z` when it IS a world axis (the
 * everyday case — every face of a milled part), otherwise its rounded
 * direction cosines. Never a guess: the user is told the actual direction.
 */
export function describeDirection(v: Vec3): string {
  const axes: ReadonlyArray<readonly [string, Vec3]> = [
    ["X", { x: 1, y: 0, z: 0 }],
    ["Y", { x: 0, y: 1, z: 0 }],
    ["Z", { x: 0, y: 0, z: 1 }],
  ];
  for (const [name, axis] of axes) {
    const d = dot(v, axis);
    if (Math.abs(Math.abs(d) - 1) < 1e-9) return `${d > 0 ? "+" : "-"}${name}`;
  }
  const round = (n: number) => (Math.abs(n) < 5e-4 ? 0 : Number(n.toFixed(3)));
  // Bracketed, because this string is read inside a comma-separated line: an
  // angled face's `X→(0.707, 0.707, 0)` must not look like three fields.
  return `(${round(v.x)}, ${round(v.y)}, ${round(v.z)})`;
}

/** Signed distance of a world point from the face plane (mm). */
function planeDistance(frame: FaceFrame, p: Vec3): number {
  return (
    (p.x - frame.origin.x) * frame.normal.x +
    (p.y - frame.origin.y) * frame.normal.y +
    (p.z - frame.origin.z) * frame.normal.z
  );
}

/** Circumcentre of three face-frame points, or null when they are collinear. */
function circumcentre(
  a: FacePoint,
  b: FacePoint,
  c: FacePoint,
): FacePoint | null {
  const d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y));
  if (Math.abs(d) < 1e-12) return null;
  const aa = a.x * a.x + a.y * a.y;
  const bb = b.x * b.x + b.y * b.y;
  const cc = c.x * c.x + c.y * c.y;
  return {
    x: (aa * (b.y - c.y) + bb * (c.y - a.y) + cc * (a.y - b.y)) / d,
    y: (aa * (c.x - b.x) + bb * (a.x - c.x) + cc * (b.x - a.x)) / d,
  };
}

/**
 * Fit a circle to an in-plane circular edge's sampled polyline. The polyline
 * samples the exact curve, so three well-spread points fix the circle and the
 * remaining points VERIFY it — a mis-tagged edge is dropped rather than snapped
 * to a fictitious centre.
 */
function fitCircle(
  points: readonly FacePoint[],
): { point: FacePoint; radiusMm: number } | null {
  const n = points.length;
  if (n < 4) return null;
  const a = points[0] as FacePoint;
  const b = points[Math.floor(n / 3)] as FacePoint;
  const c = points[Math.floor((2 * n) / 3)] as FacePoint;
  const centre = circumcentre(a, b, c);
  if (centre === null) return null;
  const radius = Math.hypot(a.x - centre.x, a.y - centre.y);
  if (!(radius > 0)) return null;
  for (const p of points) {
    const r = Math.hypot(p.x - centre.x, p.y - centre.y);
    if (Math.abs(r - radius) > Math.max(1e-4, radius * 1e-3)) return null;
  }
  return { point: centre, radiusMm: radius };
}

/**
 * Read the face's in-plane geometry off the body overlay: the frame, the
 * circles to snap to, and the segments the material check crosses.
 */
export function facePlacement(
  signature: PlanarFaceSignature,
  edges: readonly OverlayEdge[] | null,
): FacePlacement {
  const frame = faceFrame(signature);
  const circles: FaceCircle[] = [];
  const flat: number[] = [];
  for (const edge of edges ?? []) {
    const polyline = edge.polyline;
    if (polyline.length < 2) continue;
    let onPlane = true;
    const points: FacePoint[] = [];
    for (const p of polyline) {
      if (Math.abs(planeDistance(frame, p)) > PLANE_TOL_MM) {
        onPlane = false;
        break;
      }
      points.push(toFacePoint(frame, p));
    }
    if (!onPlane) continue;
    // CLOSE a loop that only nearly closes. A tessellated full circle comes
    // back sampled from parameter 0 to 2π, and the two ends can differ by a
    // rounding — which leaves the "polygon" open by ~1e-16 and lets the parity
    // ray escape through the gap, reporting a point inside a bore as solid
    // material. Snapping the last sample onto the first costs nothing and
    // removes the whole failure class.
    const first = points[0] as FacePoint;
    const last = points[points.length - 1] as FacePoint;
    const gap = Math.hypot(last.x - first.x, last.y - first.y);
    if (gap > 0 && gap <= 1e-6) points[points.length - 1] = first;
    for (let i = 1; i < points.length; i += 1) {
      const a = points[i - 1] as FacePoint;
      const b = points[i] as FacePoint;
      if (a.x === b.x && a.y === b.y) continue;
      flat.push(a.x, a.y, b.x, b.y);
    }
    if (edge.kind === "circle") {
      const fitted = fitCircle(points);
      if (fitted !== null) {
        circles.push({
          point: fitted.point,
          radiusMm: fitted.radiusMm,
          center: toWorldPoint(frame, fitted.point),
        });
      }
    }
  }
  // Largest first: a bore is the landmark you aim at, a pin hole is detail.
  circles.sort((a, b) => b.radiusMm - a.radiusMm);
  return { frame, circles, segments: Float64Array.from(flat) };
}

/**
 * Where a face-frame point lands: on metal, in one of the face's openings, or
 * off the face entirely. Even-odd crossings of a +X ray against every in-plane
 * segment — the outline and every bore mouth are closed loops, so parity is the
 * answer; the fitted circles then name the opening a miss fell into.
 */
export function checkPlacement(
  placement: FacePlacement,
  point: FacePoint,
): PlacementCheck {
  const { segments, circles } = placement;
  if (segments.length === 0) return { verdict: "unknown", circle: null };
  let crossings = 0;
  for (let i = 0; i < segments.length; i += 4) {
    const ax = segments[i] as number;
    const ay = segments[i + 1] as number;
    const bx = segments[i + 2] as number;
    const by = segments[i + 3] as number;
    if (ay > point.y !== by > point.y) {
      const t = (point.y - ay) / (by - ay);
      if (ax + t * (bx - ax) > point.x) crossings += 1;
    }
  }
  if (crossings % 2 === 1) return { verdict: "material", circle: null };
  let smallest: FaceCircle | null = null;
  for (const circle of circles) {
    const inside =
      Math.hypot(point.x - circle.point.x, point.y - circle.point.y) <
      circle.radiusMm;
    if (inside && (smallest === null || circle.radiusMm < smallest.radiusMm)) {
      smallest = circle;
    }
  }
  return smallest === null
    ? { verdict: "outside", circle: null }
    : { verdict: "opening", circle: smallest };
}
