/**
 * THE EDGE BAND — a screen-space corridor around every pickable edge, so a
 * fillet or a measurement addresses the edge the modeller can see instead of a
 * 24 px diamond parked at its mid-span.
 *
 * SEL-4, the edge half of spec A2 (`docs/design/pre-selection.md` §6). A face
 * pick can raycast the drawn triangles; an edge cannot, because an edge is
 * 1-D — there is nothing to hit. What it needs instead is a TOLERANCE, and the
 * cheap correct way to get one is `LineSegments2`, whose raycast is already
 * screen-space: with `material.worldUnits === false` a hit is accepted when the
 * pointer is within `(material.linewidth + raycaster.params.Line2.threshold) /
 * 2` SCREEN PIXELS of the segment, and each intersection reports `faceIndex` =
 * the segment index. So the segment→edge lookup this module builds is the only
 * thing the projection maths does not hand us for free.
 *
 * This module is deliberately PURE — no three.js scene, no React — because the
 * two decisions that are easy to get wrong (which edge a segment belongs to,
 * and whether a hit is occluded by the solid) are exactly the two that a
 * screenshot cannot check. `bodyPartition.ts` set the precedent.
 */
import type { Vec3 } from "../api/measure";
import { occtToScene } from "../measure/geometry";

/**
 * Half-width of the pick corridor, in SCREEN pixels.
 *
 * WCAG 2.5.8 asks for a 24 px target. A dot spends that budget as a 24 px
 * square parked at one point of the entity; 12 px each side of the polyline
 * spends the same 24 px as a corridor extended ALONG the entity, so the target
 * grows with the edge instead of staying the same size however large the edge
 * is on screen. That is the whole difference between "the mark is the target"
 * and "the edge is the target".
 *
 * An interaction constant, not a palette value — the same class as
 * `sketch/pick.ts`'s `PICK_TOLERANCE_PX`, and for the same reason it lives in
 * code rather than in `@loft/design`: a design token is something two renderers
 * must agree on, and nothing else draws this.
 */
export const EDGE_BAND_TOLERANCE_PX = 12;

/**
 * The `LineMaterial.linewidth` that produces that corridor.
 *
 * `LineSegments2.raycast` compares against `linewidth * 0.5` (the default
 * `Line2` threshold is 0 — three's `Raycaster` defines no `params.Line2`), so
 * the material width IS the full corridor width. The band never paints, so this
 * is a hit-test dimension only.
 */
export const EDGE_BAND_WIDTH_PX = EDGE_BAND_TOLERANCE_PX * 2;

/** One pickable edge: its polyline plus the ordinal a hit should report. */
export interface EdgeBandInput {
  /** The index the overlay's hover/toggle setters are keyed on. */
  index: number;
  /** The edge's tessellated polyline, in OCCT world mm. */
  polyline: readonly Vec3[];
}

export interface EdgeBand {
  /**
   * Segment endpoint PAIRS in scene space, for a drei `<Line segments>`. An
   * array of triples rather than a `Float32Array` because drei's `Line` maps
   * over `points` before flattening.
   */
  points: [number, number, number][];
  /** Segment ordinal (a hit's `faceIndex`) → the owning `EdgeBandInput.index`. */
  edgeOfSegment: Uint32Array;
}

/** An empty band — a stable shape so callers never branch on null. */
const EMPTY_BAND: EdgeBand = {
  points: [],
  edgeOfSegment: new Uint32Array(0),
};

/**
 * Merge every edge's polyline into ONE segment buffer plus the segment→edge
 * map. One buffer because one `LineSegments2` is one raycast target, and r3f
 * dedupes to one hit per OBJECT (see {@link resolveBandEdge}) — a band per edge
 * would put N objects in the intersection list and hand the caller the job of
 * sorting them, which is the job three has already done.
 */
export function buildEdgeBand(edges: readonly EdgeBandInput[]): EdgeBand {
  const points: [number, number, number][] = [];
  const owners: number[] = [];
  for (const edge of edges) {
    const polyline = edge.polyline;
    for (let i = 0; i + 1 < polyline.length; i += 1) {
      const a = occtToScene(polyline[i] as Vec3);
      const b = occtToScene(polyline[i + 1] as Vec3);
      points.push([a[0], a[1], a[2]], [b[0], b[1], b[2]]);
      owners.push(edge.index);
    }
  }
  if (owners.length === 0) return EMPTY_BAND;
  return { points, edgeOfSegment: Uint32Array.from(owners) };
}

/**
 * Half the diagonal of the band's own bounding box — a body-size proxy, in
 * scene mm.
 *
 * The occlusion bias has to scale with the part (see
 * {@link EDGE_OCCLUSION_BIAS_FRACTION}), and the band already holds every
 * B-rep edge of the body, so its extent IS the body's extent. Deriving it here
 * rather than reaching for the mesh's bounding sphere keeps the whole decision
 * inside this pure module, where it is unit-tested rather than eyeballed.
 */
export function bandRadius(
  points: readonly [number, number, number][],
): number {
  if (points.length === 0) return 0;
  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  for (const point of points) {
    for (let axis = 0; axis < 3; axis += 1) {
      const value = point[axis] as number;
      if (value < (min[axis] as number)) min[axis] = value;
      if (value > (max[axis] as number)) max[axis] = value;
    }
  }
  return (
    Math.hypot(
      (max[0] as number) - (min[0] as number),
      (max[1] as number) - (min[1] as number),
      (max[2] as number) - (min[2] as number),
    ) / 2
  );
}

/**
 * How much nearer the solid may be before an edge hit counts as OCCLUDED, in
 * scene mm, derived from the body's own size.
 *
 * Two errors to hold apart. An edge on the BACK of the solid must lose to the
 * front face, and that gap is on the order of the body's thickness. An edge on
 * the FRONT must win even though the surface sample under the cursor is up to
 * `EDGE_BAND_TOLERANCE_PX` away from it — on a steeply-angled face those pixels
 * are real depth, and rejecting there would kill exactly the silhouette-adjacent
 * edges the band exists to make pickable. A fraction of the body's radius sits
 * between the two at every part scale, which an absolute millimetre value
 * cannot do: 0.5 mm is generous on a 20 mm cube and invisible on a 2 m weldment.
 */
export const EDGE_OCCLUSION_BIAS_FRACTION = 0.05;

/** Floor for the bias, so a degenerate/zero-radius body still accepts hits. */
export const EDGE_OCCLUSION_MIN_BIAS = 1e-3;

/** The occlusion bias for a body of this bounding radius (scene mm). */
export function edgeOcclusionBias(bodyRadius: number): number {
  if (!Number.isFinite(bodyRadius) || bodyRadius <= 0) {
    return EDGE_OCCLUSION_MIN_BIAS;
  }
  return Math.max(
    bodyRadius * EDGE_OCCLUSION_BIAS_FRACTION,
    EDGE_OCCLUSION_MIN_BIAS,
  );
}

/** The nearest band hit r3f survived, as this module needs it. */
export interface BandHit {
  /** `intersection.faceIndex` — the segment ordinal. */
  segment: number;
  /** `intersection.distance` — ray origin to the hit, in scene mm. */
  distance: number;
}

/**
 * The edge a pointer is addressing, or null.
 *
 * WHAT THIS RESOLVES AND WHAT IT DOES NOT. r3f dedupes intersections by
 * `uuid + '/' + index + instanceId`, and `LineSegments2` sets neither `index`
 * nor `instanceId`, so every segment hit on one band collapses to the survivor
 * with the smallest ray DISTANCE. The band therefore resolves nearest-in-DEPTH,
 * not nearest-in-screen. That is the right answer for a front edge over a back
 * edge, and it is acceptable for coplanar neighbours; do NOT build a
 * screen-distance tie-break on top of it — that would be a second pick model
 * fighting the first.
 *
 * `surfaceDistance` is the ray distance to the drawn solid, or null when the
 * ray missed it. A silhouette edge has no surface behind it and is always
 * accepted; an edge on the far side of the material is refused, because a pick
 * that acts on geometry hidden inside the part is the "which one is live?"
 * confusion the founder reported, one step removed.
 */
export function resolveBandEdge(
  hit: BandHit | null,
  surfaceDistance: number | null,
  edgeOfSegment: Uint32Array,
  bias: number,
): number | null {
  if (hit === null) return null;
  if (!Number.isInteger(hit.segment)) return null;
  if (hit.segment < 0 || hit.segment >= edgeOfSegment.length) return null;
  if (surfaceDistance !== null && hit.distance > surfaceDistance + bias) {
    return null;
  }
  return edgeOfSegment[hit.segment] as number;
}

/** An r3f intersection, as much of one as the band resolution reads. */
export interface BandIntersection {
  /** Compared by IDENTITY against the band and the occlusion surface. */
  object: object;
  /** Ray origin → hit, in scene mm. */
  distance: number;
  /** Segment ordinal on a band hit; struck triangle on a surface hit. */
  faceIndex?: number | null | undefined;
}

/** The two raycast targets one band layer mounts, and how to read the surface. */
export interface BandTargets {
  /** The `LineSegments2` carrying the corridors, or null before it mounts. */
  band: object | null;
  /** The invisible solid mounted for the occlusion test, or null. */
  surface: object | null;
  /**
   * Does a surface hit on this triangle count as MATERIAL IN FRONT of the edge?
   *
   * False for a triangle whose body is switched off. The pick mesh is fused and
   * takes a single material, so `Mesh.raycast` tests a hidden body's triangles
   * exactly like a drawn one's (`partView.ts` `pickHiddenFaces`) — and the
   * nearest hit is the only one r3f keeps, so a hidden body in front would set
   * the occlusion distance and refuse every edge behind it. Hiding a body to
   * reach the geometry behind it is the whole reason to hide one, so that hit
   * has to be discarded rather than measured.
   */
  surfaceOccludes: (faceIndex: number | null | undefined) => boolean;
}

/**
 * The edge a pointer is addressing, from ONE r3f intersection list.
 *
 * The scan is here rather than in the layer because both of its handlers (the
 * band's and the surface's) run it over the same list, so a difference between
 * them would be a pick that depends on hit order — and because "which hits
 * count" is exactly the kind of decision a screenshot cannot check.
 */
export function resolveBandIntersections(
  intersections: readonly BandIntersection[],
  targets: BandTargets,
  edgeOfSegment: Uint32Array,
  bias: number,
): number | null {
  let hit: BandHit | null = null;
  let surfaceDistance: number | null = null;
  for (const intersection of intersections) {
    if (
      hit === null &&
      targets.band !== null &&
      intersection.object === targets.band &&
      typeof intersection.faceIndex === "number"
    ) {
      hit = {
        segment: intersection.faceIndex,
        distance: intersection.distance,
      };
    } else if (
      surfaceDistance === null &&
      targets.surface !== null &&
      intersection.object === targets.surface &&
      targets.surfaceOccludes(intersection.faceIndex)
    ) {
      surfaceDistance = intersection.distance;
    }
  }
  return resolveBandEdge(hit, surfaceDistance, edgeOfSegment, bias);
}
