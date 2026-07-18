/**
 * Interpolating spline sampling — pure math, no three.js, no store.
 *
 * The backend's authoritative spline is an OCCT `GeomAPI_Interpolate` C2
 * B-spline through the fit points; the profile edge, mesh, and any export come
 * from there. This module samples a **centripetal Catmull-Rom** curve through
 * the same fit points purely for the CLIENT render (viewport ink + hover
 * picking). Catmull-Rom is interpolating (it passes through every fit point,
 * exactly — the property the draw tool and picking rely on) and, at the
 * centripetal parameterization (α = 0.5), free of the cusps and self-overshoot
 * the uniform/chordal variants show. It is a VISUAL APPROXIMATION: the sampled
 * polyline and the server's B-spline are not byte-identical between fit points,
 * and that is fine — the client only needs to look smooth and honour the fit
 * points; the server stays the source of truth for geometry.
 */
import type { Point2D } from "./plane";

/** Chords per fit-point span — smooth at sketch scale, still cheap. */
export const SPLINE_SAMPLES_PER_SEGMENT = 16;

/** Centripetal parameterization — the cusp/overshoot-free Catmull-Rom. */
const ALPHA = 0.5;

const knotSpacing = (a: Point2D, b: Point2D): number =>
  Math.pow(Math.hypot(b.x - a.x, b.y - a.y), ALPHA);

const lerp = (a: Point2D, b: Point2D, t: number): Point2D => ({
  x: a.x + (b.x - a.x) * t,
  y: a.y + (b.y - a.y) * t,
});

/**
 * Evaluate one centripetal Catmull-Rom span p1→p2 (neighbours p0, p3) at the
 * normalized parameter s ∈ [0, 1] via the Barry-Goldman pyramid. Degenerate
 * knot spans (coincident neighbours) collapse to a straight lerp rather than
 * divide by zero — placement rejects coincident fit points, so this only ever
 * guards pathological server input.
 */
function catmullRom(
  p0: Point2D,
  p1: Point2D,
  p2: Point2D,
  p3: Point2D,
  s: number,
): Point2D {
  const t0 = 0;
  const t1 = t0 + knotSpacing(p0, p1);
  const t2 = t1 + knotSpacing(p1, p2);
  const t3 = t2 + knotSpacing(p2, p3);
  if (t2 === t1) return lerp(p1, p2, s); // coincident middle span
  const t = t1 + (t2 - t1) * s;
  const a1 = t1 === t0 ? p1 : lerp(p0, p1, (t - t0) / (t1 - t0));
  const a2 = lerp(p1, p2, (t - t1) / (t2 - t1));
  const a3 = t3 === t2 ? p2 : lerp(p2, p3, (t - t2) / (t3 - t2));
  const b1 = t2 === t0 ? a2 : lerp(a1, a2, (t - t0) / (t2 - t0));
  const b2 = t3 === t1 ? a2 : lerp(a2, a3, (t - t1) / (t3 - t1));
  return lerp(b1, b2, (t - t1) / (t2 - t1));
}

/**
 * Sample the interpolating spline through `points` into a polyline that passes
 * exactly through every fit point. Fewer than two points has no curve (returns
 * the points as-is); two points is a straight segment. Endpoint tangents come
 * from reflected phantom neighbours (`2·p0 − p1`), which keeps the centripetal
 * knot spacing non-zero at the ends where duplicating the endpoint would divide
 * by zero.
 */
export function sampleSpline(
  points: readonly Point2D[],
  samplesPerSegment: number = SPLINE_SAMPLES_PER_SEGMENT,
): Point2D[] {
  const n = points.length;
  if (n < 2) return points.map((p) => ({ x: p.x, y: p.y }));
  const first = points[0] as Point2D;
  const second = points[1] as Point2D;
  const last = points[n - 1] as Point2D;
  const penult = points[n - 2] as Point2D;
  // Reflected phantom endpoints frame the interpolant with real neighbours.
  const head: Point2D = {
    x: 2 * first.x - second.x,
    y: 2 * first.y - second.y,
  };
  const tail: Point2D = { x: 2 * last.x - penult.x, y: 2 * last.y - penult.y };
  const ext: Point2D[] = [head, ...points, tail];

  const out: Point2D[] = [{ x: first.x, y: first.y }];
  const steps = Math.max(1, samplesPerSegment);
  for (let i = 0; i + 3 < ext.length; i += 1) {
    const p0 = ext[i] as Point2D;
    const p1 = ext[i + 1] as Point2D;
    const p2 = ext[i + 2] as Point2D;
    const p3 = ext[i + 3] as Point2D;
    // j = 1..steps: j = steps lands exactly on p2 (the next fit point), so the
    // shared boundary is emitted once and every fit point is in the output.
    for (let j = 1; j <= steps; j += 1) {
      out.push(catmullRom(p0, p1, p2, p3, j / steps));
    }
  }
  return out;
}
