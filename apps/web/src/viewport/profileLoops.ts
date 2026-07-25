/**
 * Sketch profile → closed loops → solid regions, in plane (u,v) mm. Pure math
 * (no three.js) so it unit-tests in node; the {@link ExtrudePreview} component
 * turns the regions into an `ExtrudeGeometry` ghost.
 *
 * The extrude ghost is a CLIENT-SIDE approximation shown while the editor is
 * open (before Save) — the geometry service stays the source of truth for the
 * committed body. So this stitches the solved profile edges into loops with a
 * forgiving tolerance and classifies nesting by even/odd containment; it aims
 * to read right for the common profiles (a rectangle, a disc, a plate with a
 * bored hole, two disjoint islands), not to be a robust planar arrangement.
 */
import { entityPolylines } from "../sketch/geometry";
import type { Point2D } from "../sketch/plane";
import type { SketchEntity } from "../sketch/tools";

/** A solid region: one outer boundary loop with zero or more hole loops. */
export interface ProfileRegion {
  outer: Point2D[];
  holes: Point2D[][];
}

/** Endpoints within this plane-mm gap are treated as the same junction. */
const JOIN_TOL_MM = 1e-3;

function near(a: Point2D, b: Point2D): boolean {
  return (
    Math.abs(a.x - b.x) <= JOIN_TOL_MM && Math.abs(a.y - b.y) <= JOIN_TOL_MM
  );
}

/** Shoelace signed area (CCW positive) of a closed polyline. */
export function signedArea(loop: readonly Point2D[]): number {
  let sum = 0;
  for (let i = 0; i < loop.length; i += 1) {
    const a = loop[i] as Point2D;
    const b = loop[(i + 1) % loop.length] as Point2D;
    sum += a.x * b.y - b.x * a.y;
  }
  return sum / 2;
}

/** Even-odd ray cast: is `point` inside the closed `loop`? */
export function pointInLoop(point: Point2D, loop: readonly Point2D[]): boolean {
  let inside = false;
  for (let i = 0, j = loop.length - 1; i < loop.length; j = i, i += 1) {
    const a = loop[i] as Point2D;
    const b = loop[j] as Point2D;
    const straddles = a.y > point.y !== b.y > point.y;
    if (
      straddles &&
      point.x < ((b.x - a.x) * (point.y - a.y)) / (b.y - a.y) + a.x
    ) {
      inside = !inside;
    }
  }
  return inside;
}

/** A representative interior-ish point: the loop's vertex average (centroid). */
function centroid(loop: readonly Point2D[]): Point2D {
  let x = 0;
  let y = 0;
  for (const p of loop) {
    x += p.x;
    y += p.y;
  }
  const n = Math.max(loop.length, 1);
  return { x: x / n, y: y / n };
}

/**
 * Stitch the profile entities (non-construction curves) into closed loops in
 * plane space. Circles and any already-closed polyline are loops on their own;
 * open edges (lines, arcs, splines) are chained end-to-end by matching
 * endpoints. Dangling chains that never close are dropped (an open profile has
 * no face — the same rule the kernel's `profile_not_closed` enforces).
 */
export function profileLoops(entities: readonly SketchEntity[]): Point2D[][] {
  const open: Point2D[][] = [];
  const closed: Point2D[][] = [];
  for (const entity of entities) {
    if (entity.construction) continue;
    for (const polyline of entityPolylines(entity)) {
      if (polyline.length < 2) continue;
      const first = polyline[0] as Point2D;
      const last = polyline[polyline.length - 1] as Point2D;
      if (near(first, last)) closed.push(polyline);
      else open.push(polyline.map((p) => ({ x: p.x, y: p.y })));
    }
  }

  const used = new Array<boolean>(open.length).fill(false);
  for (let seed = 0; seed < open.length; seed += 1) {
    if (used[seed]) continue;
    used[seed] = true;
    const chain = [...(open[seed] as Point2D[])];
    let extended = true;
    while (
      extended &&
      !near(chain[0] as Point2D, chain[chain.length - 1] as Point2D)
    ) {
      extended = false;
      const tail = chain[chain.length - 1] as Point2D;
      for (let k = 0; k < open.length; k += 1) {
        if (used[k]) continue;
        const seg = open[k] as Point2D[];
        const segStart = seg[0] as Point2D;
        const segEnd = seg[seg.length - 1] as Point2D;
        if (near(tail, segStart)) {
          chain.push(...seg.slice(1));
          used[k] = true;
          extended = true;
          break;
        }
        if (near(tail, segEnd)) {
          chain.push(...seg.slice(0, -1).reverse());
          used[k] = true;
          extended = true;
          break;
        }
      }
    }
    if (
      chain.length >= 3 &&
      near(chain[0] as Point2D, chain[chain.length - 1] as Point2D)
    ) {
      closed.push(chain.slice(0, -1));
    }
  }

  // Drop degenerate (near-zero-area) loops — noise, not a face.
  return closed.filter((loop) => Math.abs(signedArea(loop)) > 1e-6);
}

/**
 * Classify loops into solid regions by even/odd nesting depth: a loop whose
 * centroid sits inside an even number of OTHER loops is an outer boundary; an
 * odd depth is a hole, assigned to the smallest-area loop that contains it (its
 * immediate parent).
 */
export function profileRegions(
  entities: readonly SketchEntity[],
): ProfileRegion[] {
  const loops = profileLoops(entities);
  if (loops.length === 0) return [];

  const centroids = loops.map(centroid);
  const areas = loops.map((loop) => Math.abs(signedArea(loop)));
  // Nesting depth = how many STRICTLY-LARGER loops enclose this one. The area
  // guard is what makes a concentric hole work: a plate's centroid can fall
  // inside a bore drilled at its centre, but the bore is smaller, so it never
  // counts as the plate's container (a hole is always smaller than its shell).
  const depth = loops.map((_, i) => {
    let d = 0;
    for (let j = 0; j < loops.length; j += 1) {
      if (
        j !== i &&
        (areas[j] as number) > (areas[i] as number) &&
        pointInLoop(centroids[i] as Point2D, loops[j] as Point2D[])
      ) {
        d += 1;
      }
    }
    return d;
  });

  const regions: ProfileRegion[] = loops.map((loop, i) =>
    (depth[i] as number) % 2 === 0
      ? { outer: loop, holes: [] }
      : { outer: [], holes: [] },
  );

  // Attach each hole (odd depth) to its immediate parent (smallest containing
  // outer loop).
  for (let i = 0; i < loops.length; i += 1) {
    if ((depth[i] as number) % 2 === 0) continue;
    let parent = -1;
    let parentArea = Infinity;
    for (let j = 0; j < loops.length; j += 1) {
      if (
        (depth[j] as number) % 2 === 0 &&
        (areas[j] as number) > (areas[i] as number) &&
        pointInLoop(centroids[i] as Point2D, loops[j] as Point2D[]) &&
        (areas[j] as number) < parentArea
      ) {
        parent = j;
        parentArea = areas[j] as number;
      }
    }
    if (parent >= 0)
      (regions[parent] as ProfileRegion).holes.push(loops[i] as Point2D[]);
  }

  return regions.filter((r) => r.outer.length >= 3);
}
