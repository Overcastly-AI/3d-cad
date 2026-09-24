/**
 * WHERE THE HOLE GAUGES STAND, AND WHAT THEIR PREVIEW DRAWS (CRAFT-9c — hole
 * diameter + depth).
 *
 * The seam every other manipulator makes (`faceAnchor.ts` <-> `ShellGauge.tsx`,
 * `edgeAnchor.ts` <-> `FilletGauge.tsx`): the arithmetic here, the meshes and
 * the pointer in the `.tsx` beside it, so every decision below is a unit test
 * rather than a `useMemo` inside a WebGL component.
 *
 * ## Two instruments, and why they do not share a seat
 *
 * A hole has two lengths you would pull — the bore's diameter and a blind
 * pocket's depth — and direction §5.3 settles how a verb with two quantities
 * gets them: TWO instruments, each saying by its position which number it
 * moves, never one pointer driving two numbers.
 *
 *  · **Ø** runs from the drill point OUT to the bore's rim, in the face's own
 *    `u` direction. It is a diameter gauge drawn as a radius, which is how a
 *    drafting Ø leader has always been drawn: the value is the diameter and
 *    the arrow lands on the circle. The track carries `unitsPerValue = 0.5`, so
 *    the arrowhead's base sits EXACTLY on the drawn bore circle at every value
 *    and a drag of one millimetre at the rim is two millimetres of Ø.
 *  · **Depth** runs DOWN THE BORE WALL — seated on the rim at `-u`, along the
 *    drill axis into the material. That is where a section view dimensions a
 *    blind depth, and it is also what keeps the two instruments apart.
 *
 * The obvious alternative, both arrows from the drill point, was rejected on a
 * measured reason rather than taste: two 12 px hit sleeves that share an end
 * point claim each other's pixels for the first few samples of either track,
 * so a press near the drill point would take whichever gauge happened to be
 * later in the DOM. Seating depth on the far wall puts one bore RADIUS between
 * the two seats and the Ø track runs away from it, so neither sleeve can
 * answer for its sibling. `gaugeProbe.expectReach` asserts exactly that.
 *
 * The cost, stated because it is a behaviour: pulling Ø slides the depth arrow
 * sideways with the wall it stands on. Its LENGTH and its number do not move —
 * the companion check in `craft9c-hole-gauge.spec.ts` asserts both, in both
 * directions.
 *
 * ## The preview is route (b) — the bore circle and the depth plane
 *
 * Direction §8.4 names them: the BORE CIRCLE on the face at the live Ø (the
 * mouth the drill will leave), and for a blind hole the DEPTH PLANE at the live
 * depth — the bottom circle framed by a square sheet in the face's own axes,
 * plus four wall generators tying mouth to bottom so the pair reads as one
 * cylinder rather than two unrelated rings. Line-work, no kernel round-trip,
 * and it answers the only question either drag poses: *how big is that?*
 *
 * A through-all hole draws the mouth only. Where it exits the body is a
 * kernel answer, and a client that guessed it would be drawing a claim.
 *
 * ## Frame
 *
 * Everything returned is SCENE space (Y-up). The signature and the drill point
 * arrive in OCCT world mm (Z-up) and are rotated at the boundary by the same
 * `faceBasis` / `occtToScene` every other face gauge uses.
 */
import {
  addScaled,
  dot,
  type GaugeSeat,
  negate,
  sub,
  type Vec3,
} from "@loft/design";

import type { PlanarFaceSignature, Vec3 as ApiVec3 } from "../api/parts";
import { occtToScene } from "../measure/geometry";
import { faceBasis } from "../sketch/plane";

/** The smallest bore or pocket a DRAG will produce, mm (the kernel takes any positive). */
export const MIN_HOLE_MM = 0.1;

/** Absolute ceiling, mm — the extrude's own. */
export const MAX_HOLE_MM = 10_000;

/** Smallest seat radius, scene mm — a hairline face still gets a grabbable arrow. */
const MIN_SEAT_RADIUS_MM = 0.5;

/**
 * Segments per drawn circle. 64 keeps the polygon's perimeter within 0.2 % of
 * the true circle's, which is below anything a screenshot or the stamp's
 * two-decimal rounding can see, while costing 128 vertices per ring.
 */
export const CIRCLE_SEGMENTS = 64;

/**
 * Half-side of the drawn depth-plane square, as a multiple of the bore
 * DIAMETER. 0.8 puts the square's edge 0.3 Ø outside the bottom circle: close
 * enough that the square reads as "the plane the bore stops on" rather than a
 * sheet the part is sitting on, far enough that the two outlines never merge
 * into one heavy line at the default zoom.
 */
export const DEPTH_PLANE_HALF_FRAC = 0.8;

/** Where a hole stands, in scene space. */
export interface HoleAnchor {
  /** The drill point, on the placement face. */
  centre: Vec3;
  /** Unit drill direction — INTO the material, i.e. the face's inward normal. */
  axis: Vec3;
  /** In-plane axes of the face; the Ø arrow runs along `u`. */
  u: Vec3;
  v: Vec3;
  /**
   * The instruments' own scale — the face's area-equivalent radius, the same
   * reading the shell gauge takes, so a hole's arrows are proportioned by the
   * face they stand on and not by the number being dragged.
   */
  radius: number;
}

/**
 * Seat the hole instruments on a placement face at a drill point.
 *
 * The point is PROJECTED onto the face plane, defensively: the editor derives
 * it from face-frame coordinates so it is on the plane to float precision, but
 * a seat a hair off the face would stand the bore circle in the air, and the
 * projection costs one dot product.
 */
export function holeAnchor(
  signature: PlanarFaceSignature,
  position: ApiVec3,
): HoleAnchor {
  const basis = faceBasis(signature, 0);
  const origin = basis.origin as Vec3;
  const normal = basis.normal as Vec3;
  const point = occtToScene(position) as Vec3;
  const centre = addScaled(point, normal, -dot(sub(point, origin), normal));
  const area = Math.max(signature.outer_area_mm2 ?? signature.area_mm2, 0);
  return {
    centre,
    axis: negate(normal),
    u: basis.u as Vec3,
    v: basis.v as Vec3,
    radius: Math.max(Math.sqrt(area / Math.PI), MIN_SEAT_RADIUS_MM),
  };
}

/**
 * The Ø instrument's seat: the drill point, running out along `u`.
 *
 * Its rungs cross the track in the face plane (`v`) and along the axis, so the
 * graduations stand up off the face instead of lying flat inside the bore.
 */
export function diameterSeat(anchor: HoleAnchor): GaugeSeat {
  return {
    base: anchor.centre,
    dir: anchor.u,
    radius: anchor.radius,
    arms: [anchor.v, anchor.axis],
  };
}

/**
 * How many WORLD millimetres one millimetre of Ø moves the Ø arrow — a half,
 * because the arrow is a radius and the value is a diameter.
 */
export const DIAMETER_UNITS_PER_VALUE = 0.5;

/**
 * The depth instrument's seat: ON THE BORE WALL at `-u`, running down the axis.
 * See the header for why it is not the drill point.
 */
export function depthSeat(anchor: HoleAnchor, diameterMm: number): GaugeSeat {
  return {
    base: addScaled(anchor.centre, anchor.u, -Math.max(diameterMm, 0) / 2),
    dir: anchor.axis,
    radius: anchor.radius,
    arms: [anchor.u, anchor.v],
  };
}

/** A closed circle in the plane spanned by `u`/`v`, as segment endpoint pairs. */
function circleSegments(
  centre: Vec3,
  u: Vec3,
  v: Vec3,
  radius: number,
  steps = CIRCLE_SEGMENTS,
): Float32Array {
  const out = new Float32Array(steps * 6);
  const at = (i: number): Vec3 => {
    const t = (i / steps) * Math.PI * 2;
    return addScaled(
      addScaled(centre, u, Math.cos(t) * radius),
      v,
      Math.sin(t) * radius,
    );
  };
  for (let i = 0; i < steps; i += 1) {
    out.set(at(i), i * 6);
    out.set(at(i + 1), i * 6 + 3);
  }
  return out;
}

/**
 * THE BORE CIRCLE — the mouth the drill leaves on the placement face, at the
 * live Ø. Empty for a non-positive diameter: there is no honest picture of a
 * hole of no size.
 */
export function boreCircle(
  anchor: HoleAnchor,
  diameterMm: number,
): Float32Array {
  if (!(diameterMm > 0)) return new Float32Array(0);
  return circleSegments(anchor.centre, anchor.u, anchor.v, diameterMm / 2);
}

/**
 * THE DEPTH PLANE — where a blind pocket stops: the bottom circle at the live
 * depth, framed by a square sheet in the face's own axes. Every vertex lies at
 * exactly `depthMm` along the axis, which is what makes `faceAnchor.ts`'s
 * `drawnAdvance` over this buffer a reading of the PICTURE rather than of the
 * number.
 */
export function depthPlane(
  anchor: HoleAnchor,
  diameterMm: number,
  depthMm: number,
): Float32Array {
  if (!(diameterMm > 0) || !(depthMm > 0)) return new Float32Array(0);
  const bottom = addScaled(anchor.centre, anchor.axis, depthMm);
  const ring = circleSegments(bottom, anchor.u, anchor.v, diameterMm / 2);
  const half = diameterMm * DEPTH_PLANE_HALF_FRAC;
  const { u, v } = anchor;
  const corners: Vec3[] = [
    addScaled(addScaled(bottom, u, -half), v, -half),
    addScaled(addScaled(bottom, u, half), v, -half),
    addScaled(addScaled(bottom, u, half), v, half),
    addScaled(addScaled(bottom, u, -half), v, half),
  ];
  const out = new Float32Array(ring.length + corners.length * 6);
  out.set(ring, 0);
  for (let i = 0; i < corners.length; i += 1) {
    out.set(corners[i] as Vec3, ring.length + i * 6);
    out.set(corners[(i + 1) % corners.length] as Vec3, ring.length + i * 6 + 3);
  }
  return out;
}

/**
 * The bore's four wall generators — mouth to bottom at `+u`, `+v`, `-u`, `-v` —
 * so the two rings read as one cylinder. Drawn separately from the depth plane
 * so that plane's QA stamp is not averaged over lines that span the depth.
 */
export function boreWalls(
  anchor: HoleAnchor,
  diameterMm: number,
  depthMm: number,
): Float32Array {
  if (!(diameterMm > 0) || !(depthMm > 0)) return new Float32Array(0);
  const r = diameterMm / 2;
  const out = new Float32Array(4 * 6);
  const around: [Vec3, number][] = [
    [anchor.u, r],
    [anchor.v, r],
    [anchor.u, -r],
    [anchor.v, -r],
  ];
  around.forEach(([dir, k], i) => {
    const top = addScaled(anchor.centre, dir, k);
    out.set(top, i * 6);
    out.set(addScaled(top, anchor.axis, depthMm), i * 6 + 3);
  });
  return out;
}

/**
 * The DRAWN diameter of a ring buffer about `centre`, scene mm — twice the
 * mean vertex distance. The bore preview's QA stamp: read from the vertices
 * handed to the renderer, so a ring that stopped following the drag reports
 * the size it was left at, not the size the field asked for.
 */
export function drawnDiameter(positions: Float32Array, centre: Vec3): number {
  if (positions.length === 0) return 0;
  let total = 0;
  let count = 0;
  for (let i = 0; i + 2 < positions.length; i += 3) {
    total += Math.hypot(
      (positions[i] as number) - centre[0],
      (positions[i + 1] as number) - centre[1],
      (positions[i + 2] as number) - centre[2],
    );
    count += 1;
  }
  return (2 * total) / count;
}
