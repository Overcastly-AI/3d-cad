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
 * The edge a pointer is addressing, or null, from ONE band hit.
 *
 * The single-hit form of {@link resolveBandIntersections}: it applies the
 * occlusion rule and the segment lookup and nothing else. WHICH band hit to ask
 * about is the list resolver's decision, and since EDGE-MARK-OVERLAP that is the
 * hit nearest the CURSOR, not the one nearest in depth.
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
  /**
   * On a band hit: how far the segment passes from the CURSOR, in screen
   * pixels. Absent on a hit nobody measured (r3f's own deduped list), which
   * then resolves by depth alone.
   */
  screenGapPx?: number;
}

/**
 * Two band hits whose screen gaps differ by no more than this are the same
 * distance from the cursor, and the one nearer IN DEPTH wins. One pixel: below
 * it the difference is tessellation noise, and two edges that really do project
 * onto one another (a seam behind its own silhouette) still resolve to the one
 * in front, as they always did.
 */
export const BAND_SCREEN_TIE_PX = 1;

/** The two raycast targets one band layer mounts. */
export interface BandTargets {
  /** The `LineSegments2` carrying the corridors, or null before it mounts. */
  band: object | null;
  /** The invisible solid mounted for the occlusion test, or null. */
  surface: object | null;
}

/**
 * The edge a pointer is addressing, from ONE intersection list.
 *
 * The scan is here rather than in the layer because the pointer handlers and
 * the mark-seat oracle all run it over lists built the same way, so a
 * difference between them would be a pick that depends on who asked — and
 * because "which hits count" is exactly the kind of decision a screenshot
 * cannot check.
 *
 * ## Nearest the CURSOR, not nearest in depth (EDGE-MARK-OVERLAP)
 *
 * This used to take the first band hit, because r3f dedupes a `LineSegments2`
 * to ONE hit (the nearest in depth) and that was all there was to read. On a
 * 2 mm wall that is the wrong edge half the time: the outer and inner rims run
 * 6-11 px apart, both corridors cover the cursor, and the rim nearer the camera
 * won even with the cursor sitting on the other one. Measured on the reference
 * enclosure, four of its eight rim edges could be neither hovered nor picked,
 * their marks were drawn as buried ghosts under their twins' marks, and a
 * fillet aimed at the outer rim went on two inner edges.
 *
 * Fusion 360 and SolidWorks pre-highlight the entity under the cursor, and the
 * click commits exactly what is highlighted. So `EdgeBandLayer` now raycasts
 * the band itself (every segment hit, each with its `screenGapPx`), and this
 * picks the VISIBLE hit whose segment passes closest to the cursor, with depth
 * deciding only a tie ({@link BAND_SCREEN_TIE_PX}). That is one pick model, not
 * a tie-break layered on r3f's: the hover highlight, the click and the mark
 * seats all read this function over the same kind of list.
 *
 * ## Only a PROVABLY visible edge may beat the one in front
 *
 * The body-scale `bias` below is slack for the edge nearest in depth, whose
 * cursor-side surface sample can sit up to 12 px away from it. It is far too
 * loose to prove a SECOND edge visible: it is 5 % of the body radius (2.7 mm
 * on the 80x60x40 enclosure), wider than a 2 mm wall, so from just below the
 * rim the inner edge, hidden behind the outer wall face, passed it and then
 * won on screen distance (review of EDGE-MARK-OVERLAP). So the depth-nearest
 * accepted hit is the default, and a hit farther in depth may beat it only when
 * `visibleAtOwnPixel` confirms it: a ray through the hit's OWN projected point
 * reaches it before any drawn surface, to within a pixel-scale tolerance. With
 * no oracle nothing can be proven, and the result is the depth-nearest hit.
 *
 * ## Slack is not proof, even for the only edge there (EDGE-HIDDEN-LONE)
 *
 * The same slack let a LONE hidden edge through: orthographic, 30 degrees
 * below the rim, the inner rim sits 2 mm / cos 30 = 2.31 mm behind the outer
 * face, inside 2.69 mm, and it was the only edge in the corridor over a
 * 20 px strip of that face, so hover and click there picked it. So a hit that
 * is BEHIND the surface under the cursor, accepted by the slack alone, must
 * also be proven visible at its own pixel before it can be the front hit; an
 * unproven one is skipped. A hit in front of that surface needs no proof,
 * which keeps the common case (the cursor on or beside a visible edge) at one
 * raycast.
 *
 * ## Occlusion
 *
 * THE FIRST SURFACE HIT IS THE OCCLUDER, unconditionally, and any band hit
 * farther than it (plus `bias`) is refused. It used to be
 * screened by a `surfaceOccludes` predicate, because a hidden body in front was
 * reported as the nearest hit and would then refuse every edge behind it. SEL-6
 * moved that decision a layer down — `pickRaycast.drawnSurfaceRaycast` drops
 * hidden triangles inside `Mesh.raycast`, before r3f dedupes — so by the time a
 * surface hit reaches this list it is DRAWN material by construction. Which
 * also fixes the opposite half of the same bug: the predicate made
 * `surfaceDistance` stay null behind a hidden body, so edges genuinely buried
 * inside the still-drawn plate were accepted. The occlusion test applies again.
 */
/** A band hit that passed the slack test, with its screen gap. */
interface Accepted {
  edge: number;
  gap: number;
  hit: BandIntersection;
}

export function resolveBandIntersections(
  intersections: readonly BandIntersection[],
  targets: BandTargets,
  edgeOfSegment: Uint32Array,
  bias: number,
  visibleAtOwnPixel?: (intersection: BandIntersection) => boolean,
): number | null {
  let surfaceDistance: number | null = null;
  for (const intersection of intersections) {
    if (targets.surface !== null && intersection.object === targets.surface) {
      surfaceDistance = intersection.distance;
      break;
    }
  }
  // Accepted band hits, near -> far (three sorts the list, r3f keeps the
  // order), so the first is the depth-nearest.
  const accepted: Accepted[] = [];
  for (const intersection of intersections) {
    if (
      targets.band === null ||
      intersection.object !== targets.band ||
      typeof intersection.faceIndex !== "number"
    ) {
      continue;
    }
    const edge = resolveBandEdge(
      { segment: intersection.faceIndex, distance: intersection.distance },
      surfaceDistance,
      edgeOfSegment,
      bias,
    );
    if (edge === null) continue;
    accepted.push({
      edge,
      gap: intersection.screenGapPx ?? Number.POSITIVE_INFINITY,
      hit: intersection,
    });
  }
  if (accepted.length === 0) return null;
  if (visibleAtOwnPixel === undefined) return (accepted[0] as Accepted).edge;
  // THE FRONT HIT: the depth-nearest accepted hit that is either in front of
  // the surface under the cursor, or proven visible at its own pixel
  // (EDGE-HIDDEN-LONE). A hit BEHIND that surface was accepted only by the
  // body-scale slack, and the slack is wider than a thin wall: seen from 30
  // degrees below the rim, a 20 px strip of the visible outer face used to
  // pick the hidden inner rim, the only edge in the corridor there.
  let frontAt = -1;
  for (let i = 0; i < accepted.length; i += 1) {
    const candidate = accepted[i] as Accepted;
    const onSlack =
      surfaceDistance !== null && candidate.hit.distance > surfaceDistance;
    if (!onSlack || visibleAtOwnPixel(candidate.hit)) {
      frontAt = i;
      break;
    }
  }
  const front = accepted[frontAt];
  if (front === undefined) return null;
  // Challengers clearly nearer the cursor than the front hit, nearest first.
  // The first one proven visible wins. The proof is a raycast, so it is asked
  // lazily, and on a part with no near-parallel edges not at all.
  const challengers = accepted
    .slice(frontAt + 1)
    .filter((c) => c.gap < front.gap - BAND_SCREEN_TIE_PX)
    .sort((a, b) => a.gap - b.gap);
  for (const challenger of challengers) {
    if (visibleAtOwnPixel(challenger.hit)) return challenger.edge;
  }
  return front.edge;
}
