/**
 * WHERE A FILLET OR CHAMFER GAUGE STANDS, AND WHAT ITS DRAG DRAWS (CRAFT-9a).
 *
 * ## The one constraint this file exists to satisfy
 *
 * Direction §8.4, verbatim: *"A gauge whose drag changes a number and not the
 * model is worse than the form it replaces — it promises direct manipulation
 * and delivers a slider."* Fillet and chamfer have no ghost and cannot cheaply
 * get one — a real preview is a kernel round-trip per pointer move. So this is
 * route **(b)**: a GEOMETRIC LINE-WORK PREVIEW, idiom D's own vocabulary, drawn
 * from the picked edge and the current value with no server in the loop.
 *
 *  · **fillet** — the rolling ball. Its tangent circle at the edge's mid
 *    cross-section, the arc of that circle which BECOMES the fillet surface,
 *    and the two tangency lines running the length of the edge, which are
 *    exactly where the round meets each face.
 *  · **chamfer** — the bevel band. The two offset lines the cut reaches to on
 *    each face, closed at both ends and at the middle by the bevel's own
 *    cross-section.
 *
 * Both answer the only question the drag poses — *how big is that?* — and both
 * are the SAME offset arithmetic, which is why they live in one file: the
 * fillet's tangency line at radius r and the chamfer's offset line at distance
 * d are the same line. (Proved below, and it is not a coincidence: a ball of
 * radius r in the corner touches each face exactly r from the edge.)
 *
 * ## PURE, and tuple-based, for the reason `packages/design/src/gauge.ts` is
 *
 * "Which way is out of the material at this edge" is a decision a screenshot
 * cannot check and a WebGL test cannot reach. It is arithmetic, so it is
 * asserted as arithmetic. The r3f plumbing is in `FilletGauge.tsx` /
 * `ChamferGauge.tsx`; the pick-store reading is in `edgeAnchorSource.ts`. This
 * module knows about neither.
 *
 * Everything here is in the **scene frame** (Y-up), already rotated out of
 * OCCT's Z-up by `occtToSceneTuple` — the one rotation in the app. Callers
 * convert at the boundary, exactly as `extrudeHandle.ts` does.
 *
 * ## Convex and concave cannot be told apart from the two normals
 *
 * Worth stating because the obvious implementation is wrong and looks right on
 * a cube. A box's convex top-front edge and an L-bracket's concave inner edge
 * BOTH present outward normals `+Z` and `+X`: the pair is identical and the
 * material is on opposite sides. The discriminator is which way each face
 * EXTENDS from the edge, which only the face centroid knows. So
 * {@link edgeAnchor} derives each face's in-face outward direction from its
 * centroid and reads convexity off that — `dot(faceOut[0], normals[1]) < 0` is
 * convex — rather than from a cross product whose sign it would have had to
 * choose, which is how this arrives at the right answer on an inside corner.
 */
import {
  add,
  addScaled,
  cross,
  dot,
  type GaugeTrack,
  length,
  type LengthUnit,
  formatLength,
  linearTrack,
  reject,
  scale,
  sub,
  unit,
  type Vec3,
} from "@loft/design";

import { COARSE_STEP_FACTOR, keyStepMm, SNAP_MM } from "./extrudeHandle";

// --- SMALL VECTOR ARITHMETIC, on plain tuples --------------------------------
//
// These used to be local copies, arguing that a shared micro-vector library was
// the premature abstraction the DRY rule exempts. Three other modules made the
// same argument and the four copies then diverged (board #63), so they are now
// `@loft/design`'s `vec3` — still tuple-based, still no `three`, so this file
// is still testable without a GPU. THIS file's behaviour is the one that was
// promoted: the picometre floor and the `null` refusal below it, and `length`
// as `Math.hypot`, are `edgeAnchor`'s and are unchanged here. `UNIT_FLOOR` is
// now `VEC3_UNIT_FLOOR`, exported, with this file's reasoning carried across.

/**
 * How far off a plane a point may sit and still count as ON it, scene mm.
 *
 * The overlay carries full-precision kernel coordinates and a curved edge is
 * sampled ON its own curve, so a point of an edge that bounds a planar face is
 * on that face's plane to kernel tolerance. 1e-3 mm is ten times the kernel's
 * documented 1e-4 linear tolerance — loose enough to survive the float32 the
 * scene frame rounds through, tight enough that a parallel face 0.1 mm away is
 * never mistaken for the one the edge belongs to.
 */
export const PLANE_TOLERANCE_MM = 1e-3;

/**
 * Below this half-angle cosine the two faces have folded flat onto each other
 * and there is no seat between them, so the anchor refuses.
 *
 * Numerically equal to `@loft/design`'s `VEC3_UNIT_FLOOR`, which is where this
 * guard's value came from, and deliberately NOT that constant: a cosine is
 * dimensionless and the shared floor is a length in scene mm. Sharing the
 * symbol would make a later change to one of them silently change the other,
 * which is the failure mode the consolidation in board #63 was fixing, not one
 * to reintroduce by over-sharing.
 */
const DEGENERATE_HALF_ANGLE_COS = 1e-9;

// --- INPUTS ------------------------------------------------------------------

/** One planar face of the body, scene frame. */
export interface EdgeFacePlane {
  /** Outward unit normal. */
  normal: Vec3;
  /** Any point on the plane — in practice the face's area centroid. */
  centroid: Vec3;
}

/** One picked edge, scene frame. */
export interface EdgeAnchorInput {
  /** Stable identity for React keys — the edge signature key. */
  key: string;
  /** Ordered points along the edge, start..end inclusive (>= 2). */
  polyline: readonly Vec3[];
  /** The curve's param-0.5 point — where the gauge is seated. */
  midpoint: Vec3;
  /** Edge length, mm. Drives the gauge's own scale, never its value. */
  lengthMm: number;
}

// --- THE ANCHOR --------------------------------------------------------------

/**
 * A seated gauge anchor: everything both previews and the track need, derived
 * once per edge per camera-independent change.
 */
export interface EdgeAnchor {
  key: string;
  /** The seat — the edge's midpoint. */
  midpoint: Vec3;
  /** Unit tangent along the edge at the midpoint. */
  tangent: Vec3;
  /**
   * Unit bisector of the two faces, pointing INTO FREE SPACE, normal to the
   * edge — the direction the gauge's arrow grows along.
   *
   * It is `normalize(n1 + n2)` for a convex edge and for a concave one alike:
   * both wear their free space on the positive-normal side, which is what makes
   * this one expression rather than a branch. Pointing outward rather than into
   * the solid is the only choice that leaves the instrument visible; an arrow
   * drawn inside material is an arrow nobody can take hold of.
   */
  outward: Vec3;
  /** The two faces' outward unit normals. */
  normals: readonly [Vec3, Vec3];
  /**
   * For each face, the unit direction ALONG that face, away from the edge,
   * toward the face's own interior. A fillet of radius r is tangent to face i
   * exactly `r` along `faceOut[i]`; a chamfer of distance d reaches exactly `d`
   * along it. One construction, both verbs.
   */
  faceOut: readonly [Vec3, Vec3];
  /** True when the material is on the inside of the wedge (a box corner). */
  convex: boolean;
  /** `cos(half the angle between the two outward normals)`, in (0, 1]. */
  halfAngleCos: number;
  /** The edge itself, for drawing offsets along its whole length. */
  polyline: readonly Vec3[];
  lengthMm: number;
}

/** The tangent of the polyline segment nearest the midpoint. */
function tangentAt(
  polyline: readonly Vec3[],
  midpoint: Vec3,
): { tangent: Vec3; index: number } | null {
  let best: { tangent: Vec3; index: number } | null = null;
  let bestDistance = Infinity;
  for (let i = 0; i + 1 < polyline.length; i += 1) {
    const a = polyline[i] as Vec3;
    const b = polyline[i + 1] as Vec3;
    const direction = unit(sub(b, a));
    if (direction === null) continue;
    const centre: Vec3 = scale(add(a, b), 0.5);
    const distance = length(sub(centre, midpoint));
    if (distance < bestDistance) {
      bestDistance = distance;
      best = { tangent: direction, index: i };
    }
  }
  return best;
}

/** True when every point of the edge lies on this face's plane. */
function planeHoldsEdge(
  plane: EdgeFacePlane,
  polyline: readonly Vec3[],
): boolean {
  for (const point of polyline) {
    if (
      Math.abs(dot(plane.normal, sub(point, plane.centroid))) >
      PLANE_TOLERANCE_MM
    ) {
      return false;
    }
  }
  return true;
}

/**
 * True when the edge's two ends coincide — a full circle or a closed spline.
 * The schema guarantees `end` equals `start` in that case, so the polyline's
 * own ends carry it and no curve type needs consulting.
 */
function isClosed(polyline: readonly Vec3[]): boolean {
  const first = polyline[0] as Vec3;
  const last = polyline[polyline.length - 1] as Vec3;
  return length(sub(first, last)) <= PLANE_TOLERANCE_MM;
}

/** The in-face direction from the edge toward a planar face's own interior. */
function faceInterior(
  plane: EdgeFacePlane,
  midpoint: Vec3,
  tangent: Vec3,
): Vec3 | null {
  // `centroid - midpoint` already lies IN the plane (both points are on it), so
  // the only component to remove is the one along the edge.
  return unit(reject(sub(plane.centroid, midpoint), tangent));
}

/**
 * Seat a gauge on one picked edge, given the body's planar faces.
 *
 * Returns `null` — no gauge on this edge — rather than guessing, in every case
 * where the two adjacent faces cannot be identified: an edge between two curved
 * surfaces, a degenerate zero-length edge, two faces whose normals cancel. A
 * missing instrument is recoverable; one anchored to a fiction is not.
 *
 * ## The single-planar-face case is not a fallback, it is the shoulder
 *
 * A turned part's shoulder and every slot's end present ONE planar face and one
 * curved one, and the curved one carries no signature (the overlay's face
 * signatures are planar-only). Refusing there would mean no gauge on a large
 * share of real edges. Where a plane meets a surface of revolution, the curved
 * surface's normal at the edge is perpendicular to the plane's normal and
 * points away from the planar face's interior — so it is `-faceOut[0]`, derived
 * and not invented. That is exact for a cylinder or a cone meeting a plane at a
 * right angle, and approximate for a general blend; the approximation moves the
 * arrow's direction, never the value it reports.
 *
 * ## The gap this REFUSES rather than guesses: a closed edge with one planar face
 *
 * A bore's rim and a boss's rim are both a circle bounding one planar face, and
 * **the face centroid cannot tell them apart** — a disc and an annulus with the
 * same outer circle share a centroid, and the material is INSIDE the circle for
 * one and OUTSIDE it for the other. Nothing else in the overlay resolves it
 * (`area` vs `outer_area` says a hole exists, never which circle the edge is).
 * Guessing means drawing the round on the wrong side of the metal, so a CLOSED
 * edge with only one planar face gets no anchor and no gauge. The radius is
 * still typed in the rail field, which is why that field stays (direction §11):
 * the verb is never blocked, only its handle is absent.
 */
export function edgeAnchor(
  input: EdgeAnchorInput,
  planes: readonly EdgeFacePlane[],
): EdgeAnchor | null {
  const { polyline, midpoint, key, lengthMm } = input;
  if (polyline.length < 2) return null;
  const seatTangent = tangentAt(polyline, midpoint);
  if (seatTangent === null) return null;
  const tangent = seatTangent.tangent;

  const holding = planes.filter((plane) => planeHoldsEdge(plane, polyline));
  // More than two planes hold the edge only when the body carries a face
  // COPLANAR with one of the edge's own — an L welded flush, a boolean seam.
  // The two that own the edge are the two whose centroids are nearest it; a
  // coplanar face elsewhere on the body is, by construction, further away.
  const candidates =
    holding.length > 2
      ? [...holding]
          .sort(
            (a, b) =>
              length(sub(a.centroid, midpoint)) -
              length(sub(b.centroid, midpoint)),
          )
          .slice(0, 2)
      : holding;

  let normals: readonly [Vec3, Vec3];
  let faceOut: readonly [Vec3, Vec3];

  if (candidates.length === 2) {
    const [planeA, planeB] = candidates as [EdgeFacePlane, EdgeFacePlane];
    const outA = faceInterior(planeA, midpoint, tangent);
    const outB = faceInterior(planeB, midpoint, tangent);
    if (outA === null || outB === null) return null;
    normals = [planeA.normal, planeB.normal];
    faceOut = [outA, outB];
  } else if (candidates.length === 1) {
    // The closed-edge refusal — see this function's doc comment. A rim's own
    // face centroid sits at the circle's centre whether the metal is inside the
    // circle or outside it, so there is no direction to derive.
    if (isClosed(polyline)) return null;
    const plane = candidates[0] as EdgeFacePlane;
    const outA = faceInterior(plane, midpoint, tangent);
    if (outA === null) return null;
    // See the doc comment: the curved neighbour's normal at the edge.
    const normalB = scale(outA, -1);
    const outB = unit(reject(scale(plane.normal, -1), normalB));
    if (outB === null) return null;
    normals = [plane.normal, normalB];
    faceOut = [outA, outB];
  } else {
    return null;
  }

  const outward = unit(add(normals[0], normals[1]));
  if (outward === null) return null; // back-to-back faces: no bisector exists.

  // CONVEXITY, and the reason it is read here and not from the normals: a box's
  // convex edge and an L's concave one carry the SAME normal pair. What differs
  // is which side each face extends to, which `faceOut` carries and a cross
  // product does not.
  const convexA = dot(faceOut[0], normals[1]) < 0;
  const convexB = dot(faceOut[1], normals[0]) < 0;
  // The two readings disagree only on a face whose centroid sits on the far
  // side of a re-entrant boundary from its own edge. Refuse rather than pick
  // one: a preview drawn on the wrong side of the material is worse than none.
  if (convexA !== convexB) return null;

  const cosine = Math.min(1, Math.max(-1, dot(normals[0], normals[1])));
  const halfAngleCos = Math.sqrt((1 + cosine) / 2);
  if (halfAngleCos <= DEGENERATE_HALF_ANGLE_COS) return null;

  return {
    key,
    midpoint,
    tangent,
    outward,
    normals,
    faceOut,
    convex: convexA,
    halfAngleCos,
    polyline,
    lengthMm,
  };
}

// --- THE PREVIEWS ------------------------------------------------------------

/** Line-segment endpoint pairs, flattened for a `lineSegments` draw. */
export type SegmentBuffer = Float32Array;

/** Push one segment's two endpoints into `out` at `at`; returns the new offset. */
function writeSegment(out: Float32Array, at: number, a: Vec3, b: Vec3): number {
  out[at] = a[0];
  out[at + 1] = a[1];
  out[at + 2] = a[2];
  out[at + 3] = b[0];
  out[at + 4] = b[1];
  out[at + 5] = b[2];
  return at + 6;
}

/** A polyline offset bodily along one direction — the tangency/offset line. */
function offsetPolyline(
  polyline: readonly Vec3[],
  direction: Vec3,
  distance: number,
): Vec3[] {
  return polyline.map((point) => addScaled(point, direction, distance));
}

/** A polyline as segment pairs, appended into `out`. */
function writePolyline(
  out: Float32Array,
  at: number,
  points: readonly Vec3[],
): number {
  let cursor = at;
  for (let i = 0; i + 1 < points.length; i += 1) {
    cursor = writeSegment(
      out,
      cursor,
      points[i] as Vec3,
      points[i + 1] as Vec3,
    );
  }
  return cursor;
}

/**
 * Segments a FULL turn would be drawn with; an arc takes its share.
 *
 * 48 is the smallest count at which a curve reads as a curve rather than a
 * polygon at the radii a fillet gauge is used at — chordal error
 * `r * (1 - cos(π/48))` = 0.2 % of the radius, under a pixel for anything that
 * fits on screen.
 */
export const FULL_TURN_SEGMENTS = 48;

/** The rolling ball's centre for a fillet of `radius` at this anchor. */
export function rollingBallCentre(anchor: EdgeAnchor, radius: number): Vec3 {
  // Distance from the edge to the ball's centre along the bisector:
  // `r / cos(φ/2)`, φ the angle between the outward normals. On a 90° box edge
  // that is r·√2, which is the (r, r) offset the hand calculation gives.
  const reach = radius / anchor.halfAngleCos;
  return addScaled(
    anchor.midpoint,
    anchor.outward,
    anchor.convex ? -reach : reach,
  );
}

/**
 * The fillet preview: the round's band.
 *
 * Two tangency lines running the length of the edge, closed at both ends and at
 * the seat by the round's own ARC — the same three-rung band the chamfer draws,
 * differing in the one way the two features differ: the rung is an arc rather
 * than a chord. One idiom, one distinction, and the distinction carries the
 * whole meaning.
 *
 * ## The full tangent circle is DELIBERATELY not drawn, and the screenshot is
 * ## why
 *
 * The first version drew the rolling ball's complete circle at minor weight,
 * with the arc over it at full weight, on the reasoning that the circle says
 * "ball" and the arc says "result". CAPTURED at 1280x800 on the reference
 * 20 mm cube at r=8, and the picture says otherwise on both counts:
 *
 *  · the circle's centre sits `r/cos(φ/2)` = 11.3 mm INSIDE the solid, so the
 *    circle is a 16 mm hoop drawn through a 20 mm part. At minor weight it was
 *    still the largest, loudest mark on screen — the hierarchy inverted, the
 *    quiet element dominating the two that carry the answer;
 *  · and the ARC WAS INVISIBLE, because an arc of a circle drawn on top of
 *    that circle is a mark inside the thing it is supposed to stand out from.
 *    Present in the scene graph, correctly computed, unreadable — the same
 *    shape as the snap-ladder erasure of 2026-09-14, and caught the same way.
 *
 * So the accessory comes off (Chanel's rule, with a measurement behind it). The
 * tangency lines answer *how much of each face does this eat*, the arc answers
 * *what shape does the corner become*, and nothing else is drawn.
 */
export interface FilletPreview {
  /** Where the round meets each face, along the whole edge. */
  tangencyLines: SegmentBuffer;
  /** The round's cross-section at both ends of the edge and at the seat. */
  arcs: SegmentBuffer;
}

const EMPTY = new Float32Array(0);

/** The three stations a band is closed at: both ends, and the seat. */
function bandStations(anchor: EdgeAnchor): readonly Vec3[] {
  return [
    anchor.polyline[0] as Vec3,
    anchor.midpoint,
    anchor.polyline[anchor.polyline.length - 1] as Vec3,
  ];
}

export function filletPreview(
  anchor: EdgeAnchor,
  radius: number,
): FilletPreview {
  if (!(radius > 0)) return { tangencyLines: EMPTY, arcs: EMPTY };

  const a = offsetPolyline(anchor.polyline, anchor.faceOut[0], radius);
  const b = offsetPolyline(anchor.polyline, anchor.faceOut[1], radius);
  const tangencyLines = new Float32Array((a.length - 1 + (b.length - 1)) * 6);
  let cursor = writePolyline(tangencyLines, 0, a);
  writePolyline(tangencyLines, cursor, b);

  // The arc lives in the plane across the edge. `outward` is already
  // perpendicular to the tangent (both normals are), so the pair is orthonormal
  // by construction and needs no Gram-Schmidt.
  const e1 = anchor.outward;
  const e2 = cross(anchor.tangent, anchor.outward);
  const seatCentre = rollingBallCentre(anchor, radius);

  // The two tangency points as angles in the (e1, e2) basis. The sweep between
  // them is the angle between the two face normals, so it is never more than a
  // half turn and the SHORT way round is always the side facing the edge — the
  // material boundary the round actually creates.
  const toAngle = (point: Vec3): number => {
    const v = sub(point, seatCentre);
    return Math.atan2(dot(v, e2), dot(v, e1));
  };
  const startAngle = toAngle(
    addScaled(anchor.midpoint, anchor.faceOut[0], radius),
  );
  const endAngle = toAngle(
    addScaled(anchor.midpoint, anchor.faceOut[1], radius),
  );
  let sweep = endAngle - startAngle;
  while (sweep > Math.PI) sweep -= Math.PI * 2;
  while (sweep < -Math.PI) sweep += Math.PI * 2;
  const steps = Math.max(
    3,
    Math.round((Math.abs(sweep) / (Math.PI * 2)) * FULL_TURN_SEGMENTS),
  );

  // Each station's arc is the seat's, translated. The anchor carries ONE frame
  // for the whole edge (see `edgeAnchor`), so translating is exactly as true as
  // the offset lines beside it are — and a second derivation would be a second
  // chance for the two to disagree about where the band's corners meet.
  const stations = bandStations(anchor);
  const arcs = new Float32Array(stations.length * steps * 6);
  cursor = 0;
  for (const station of stations) {
    const shift = sub(station, anchor.midpoint);
    const pointAt = (angle: number): Vec3 =>
      add(
        shift,
        addScaled(
          addScaled(seatCentre, e1, Math.cos(angle) * radius),
          e2,
          Math.sin(angle) * radius,
        ),
      );
    for (let i = 0; i < steps; i += 1) {
      cursor = writeSegment(
        arcs,
        cursor,
        pointAt(startAngle + (sweep * i) / steps),
        pointAt(startAngle + (sweep * (i + 1)) / steps),
      );
    }
  }

  return { tangencyLines, arcs };
}

/**
 * The chamfer preview: the bevel band.
 *
 * The two lines the cut reaches to on each face, plus the bevel's own
 * cross-section drawn at both ends of the edge and at its middle — three rungs,
 * which is what turns two parallel lines into a BAND with a width you can read.
 * The end rungs close the figure; the middle one stands where the gauge does.
 */
export interface ChamferPreview {
  /** The two offset lines. Major weight. */
  offsets: SegmentBuffer;
  /** The bevel cross-sections at both ends and the middle. Major weight. */
  bevels: SegmentBuffer;
}

export function chamferPreview(
  anchor: EdgeAnchor,
  distance: number,
): ChamferPreview {
  if (!(distance > 0)) return { offsets: EMPTY, bevels: EMPTY };

  const a = offsetPolyline(anchor.polyline, anchor.faceOut[0], distance);
  const b = offsetPolyline(anchor.polyline, anchor.faceOut[1], distance);
  const offsets = new Float32Array((a.length - 1 + (b.length - 1)) * 6);
  let cursor = writePolyline(offsets, 0, a);
  writePolyline(offsets, cursor, b);

  // Three rungs: both ends, which CLOSE the figure into a band, and the seat,
  // which is where the gauge stands and therefore where the eye already is.
  // The middle one comes from the MIDPOINT, not from a polyline index — a
  // straight edge arrives as exactly two points, so an index-derived middle
  // would land on top of the start rung and the band would read as two marks
  // instead of three. (The shape of the ladder-erasure defect of 2026-09-14:
  // arithmetically fine, invisible on the only geometry that matters.)
  const stations = bandStations(anchor);
  const bevels = new Float32Array(stations.length * 6);
  cursor = 0;
  for (const station of stations) {
    cursor = writeSegment(
      bevels,
      cursor,
      addScaled(station, anchor.faceOut[0], distance),
      addScaled(station, anchor.faceOut[1], distance),
    );
  }
  return { offsets, bevels };
}

// --- THE TRACK ---------------------------------------------------------------

/**
 * Floor for a radius or a bevel, mm — the extrude depth's own floor.
 *
 * Shared rather than re-picked: "the smallest length this product lets a drag
 * produce" is one decision, and two of them drifting apart is how a drag on one
 * verb stops at 0.1 and on another at 0.05 for no reason anybody can state.
 */
export const MIN_EDGE_VALUE_MM = 0.1;

/**
 * Ceiling, mm. A fillet is bounded by its own geometry long before this — the
 * kernel refuses a radius that eats its neighbours — so this is a sanity rail
 * on the DRAG, not a claim about what will build. 1 m is past any edge a
 * single-part fillet is applied to.
 */
export const MAX_EDGE_VALUE_MM = 1_000;

/**
 * The fillet/chamfer gauge's arithmetic — ONE track for both verbs.
 *
 * A radius and a bevel distance are the same kind of quantity seated the same
 * way: a length, measured from the edge, along the face-pair's bisector, in the
 * document's unit. They differ in their tag label and in what the preview draws,
 * and in nothing the track knows about. Two factories here would be two places
 * for the snap increment to drift.
 *
 * `snap`, `keyStep` and the coarse factor come from `extrudeHandle.ts` because
 * that is where the product's per-unit drag quantisation already lives
 * (`SNAP_MM` is documented as a property of the DOCUMENT UNIT, not of extrude).
 * Copying those numbers here would be the WET defect the DRY rule names, and
 * the symptom would be a fillet that snaps on a different grid from an extrude
 * on the same part.
 *
 * The seat's `radius` — the gauge's own drawn scale — is HALF THE EDGE, the
 * same relationship the extrude gauge has to its profile's half-diagonal. It is
 * derived from the edge and never from the value, so the instrument holds still
 * while you drag it; `linearTrack` additionally bounds the arrowhead by 45 % of
 * the shaft, so a 0.5 mm round on a 200 mm edge still reads as a rod with a
 * point rather than a cone on a stub.
 *
 * `arms` are the edge's own tangent and the third axis of the anchor's frame,
 * so a graduation cross is scribed in the plane the edge lies in rather than on
 * an arbitrary derived basis.
 */
export function edgeGaugeTrack(
  anchor: EdgeAnchor,
  unit: LengthUnit,
): GaugeTrack {
  return linearTrack(
    {
      base: anchor.midpoint,
      dir: anchor.outward,
      radius: anchor.lengthMm / 2,
      arms: [anchor.tangent, cross(anchor.tangent, anchor.outward)],
    },
    {
      min: MIN_EDGE_VALUE_MM,
      max: MAX_EDGE_VALUE_MM,
      snap: SNAP_MM[unit],
      keyStep: keyStepMm(unit),
      coarseFactor: COARSE_STEP_FACTOR,
      format: (mm, opts) => formatLength(mm, unit, opts ?? {}),
    },
  );
}
