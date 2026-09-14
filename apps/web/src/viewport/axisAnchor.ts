/**
 * THE AXIS AN ANGLE TURNS ABOUT — the anchor an arc gauge hangs on (CRAFT-10).
 *
 * ## Why this file is the FIRST half of the angular-gauge item
 *
 * MEASURED before this landed: **the revolve axis was not drawn in the viewport
 * at all.** It was chosen from a dropdown reading *"Y axis · through the
 * origin"* and the scene showed nothing (`w3-before-revolve-1280.png`). An arc
 * gauge with no visible axis is an arc around NOTHING: the instrument would
 * draw a curved brass rod floating beside the profile with no statement of what
 * it is curving about, which is a decorative sweep, not a dimension. So the
 * axis is drawn first and the arc is hung on it — the direction pass calls this
 * "not scope creep; it is the arc's anchor", and it is the reason the drawn
 * order in {@link RevolveGauge} is axis, then arc, then result.
 *
 * ## The drafting decision: a CHAIN LINE, not a solid rod
 *
 * The axis and the gauge are both brass, because they are one pending edit and
 * a second hue would say they were two things (`tokens.ts` argues this for the
 * ghost/gauge pair and the same argument holds here). What separates them is
 * FORM: the gauge is a solid tube with a point on it — *a thing you pull* — and
 * the axis is an **ISO 128 chain line**, long dash / short dash, which is how
 * an axis of revolution is drawn on every engineering drawing ever issued. It
 * is a quotation from the subject's own vocabulary rather than a new idiom, and
 * it is instantly legible to the only audience that matters: the pattern says
 * "centreline" to a machinist before any label is read.
 *
 * It carries no arrowheads and no engraved letter. The dropdown already names
 * the axis in words and the tag already carries the number; a third statement
 * of the same fact would be the accessory to remove.
 *
 * ## Frame
 *
 * Everything returned here is SCENE space (three.js, Y-up), like
 * `extrudeHandle.ts` and for the same reason: it is the frame a pointer ray
 * arrives in and the frame the body is drawn in. The ONE conversion is for a
 * world origin axis, whose direction is declared in the kernel's Z-up frame and
 * is rotated at the boundary by `occtToSceneTuple` — one rotation, applied
 * once, exactly as `sketch/plane.ts` requires of anything that renders.
 *
 * ## Pure, and deliberately so
 *
 * No `three`, no react. Every decision here — where the axis is, how long the
 * drawn stretch is, where the arc is seated on it — is checkable in node in
 * microseconds. The r3f shells (`RevolveAxisLine`, `RevolveGauge`) are thin.
 */
import type { Vec3 } from "@loft/design";

import type { SketchEntity } from "../api/parts";
import type { OriginAxisName, RevolveAxisRef } from "../features/revolve";
import {
  occtToSceneTuple,
  type PlaneBasis,
  type Vec3Tuple,
} from "../sketch/plane";

/** A line in space: a point on it and a unit direction along it. */
export interface AxisAnchor {
  /** A point the axis passes through, scene mm. */
  base: Vec3;
  /** Unit direction along the axis, scene frame. */
  dir: Vec3;
}

/**
 * World directions of the three origin axes, in the KERNEL frame — the client's
 * copy of `features/revolve`'s `ORIGIN_AXIS_DIRECTIONS`, which is private to
 * that module. They pass through the origin, so a direction fixes the line.
 */
const ORIGIN_AXIS_KERNEL_DIR: Record<OriginAxisName, Vec3Tuple> = {
  X: [1, 0, 0],
  Y: [0, 1, 0],
  Z: [0, 0, 1],
};

function sub(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function scale(a: Vec3, k: number): Vec3 {
  return [a[0] * k, a[1] * k, a[2] * k];
}

function addScaled(a: Vec3, b: Vec3, k: number): Vec3 {
  return [a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k];
}

function norm(a: Vec3): number {
  return Math.sqrt(dot(a, a));
}

/** Unit vector, or `null` when there is no direction to give. */
function unit(a: Vec3): Vec3 | null {
  const l = norm(a);
  return l > 0 ? scale(a, 1 / l) : null;
}

/** A point on the sketch plane, in scene mm. */
function onPlane(basis: PlaneBasis, u: number, v: number): Vec3 {
  return [
    basis.origin[0] + basis.u[0] * u + basis.v[0] * v,
    basis.origin[1] + basis.u[1] * u + basis.v[1] * v,
    basis.origin[2] + basis.u[2] * u + basis.v[2] * v,
  ];
}

/**
 * The scene-frame line a revolve turns about, or null when the reference names
 * geometry this sketch does not carry.
 *
 * NULL IS A REAL ANSWER, not a defensive shrug: a `sketch_line` axis names an
 * entity by sketch-local id, and the editor can be pointed at a different
 * profile (or the sketch re-solved with that line deleted) between the params
 * being stored and this being asked. Returning null draws no axis and mounts no
 * gauge, which is the honest picture — an arc around a line that is not there
 * would be worse than the dropdown-only state this item exists to replace.
 *
 * @param axis The wire reference, exactly as the form persists it.
 * @param basis The PROFILE SKETCH's plane, in SCENE coordinates. Only the
 *   `sketch_line` half uses it; an origin axis is a world line and is
 *   independent of any sketch (which is precisely what makes it the axis that
 *   rescues a profile with no centreline drawn on it).
 * @param entities The profile sketch's solved entities, for the line half.
 */
export function revolveAxisAnchor(
  axis: RevolveAxisRef,
  basis: PlaneBasis,
  entities: readonly SketchEntity[],
): AxisAnchor | null {
  if (axis.kind === "origin_axis") {
    const dir = unit(occtToSceneTuple(ORIGIN_AXIS_KERNEL_DIR[axis.axis]));
    return dir === null ? null : { base: [0, 0, 0], dir };
  }
  const line = entities.find(
    (e): e is Extract<SketchEntity, { kind: "line" }> =>
      e.kind === "line" && e.id === axis.entity,
  );
  if (line === undefined) return null;
  const start = onPlane(basis, line.start.x, line.start.y);
  const end = onPlane(basis, line.end.x, line.end.y);
  const dir = unit(sub(end, start));
  // A zero-length line has no direction; the kernel would refuse it too.
  return dir === null ? null : { base: start, dir };
}

/**
 * The plane a sketch's points are lifted onto, as a line in the plane: the
 * component of `point` that lies OFF the axis, and how far off it is.
 *
 * This is the whole of "where does the arc sit". The revolve's radius is the
 * distance from the axis to the point of the profile that reaches FURTHEST from
 * it, because that is the circle the turned part's silhouette actually sweeps —
 * seating the arc anywhere nearer would draw a protractor buried inside the
 * material it is dimensioning.
 */
export function axisRadial(
  anchor: AxisAnchor,
  point: Vec3,
): { foot: Vec3; radial: Vec3 | null; distance: number } {
  const offset = sub(point, anchor.base);
  const along = dot(offset, anchor.dir);
  const foot = addScaled(anchor.base, anchor.dir, along);
  const out = sub(point, foot);
  const distance = norm(out);
  return { foot, radial: unit(out), distance };
}

/** One drawn stretch of chain line, as the half-length of its dash cycle. */
export interface ChainLineOptions {
  /** How far the drawn line reaches either side of `centre`, scene mm. */
  reach: number;
  /** Long-dash length, scene mm. */
  longMm?: number;
  /** Short-dash length, scene mm. */
  shortMm?: number;
  /** Gap between dashes, scene mm. */
  gapMm?: number;
}

/**
 * ISO 128 chain-line proportions, in scene millimetres, held here rather than
 * spread through the shell.
 *
 * The standard gives ranges rather than one number; these are the middle of the
 * long-dash class scaled for a desk-sized part, and they are RELATIVE to the
 * drawn reach (see {@link chainLineSegments}), so a 200 mm shaft and a 5 mm pin
 * both get a pattern with the same number of cycles rather than one reading as
 * a solid rod and the other as three dots.
 */
const CHAIN_LONG_FRAC = 0.24;
const CHAIN_SHORT_FRAC = 0.05;
const CHAIN_GAP_FRAC = 0.045;

/** Fewest full long/short cycles drawn, so the pattern always reads as a chain. */
const CHAIN_MIN_CYCLES = 2;

/**
 * The chain line's segment endpoints, as flat `[x,y,z, x,y,z, ...]` pairs ready
 * for a `lineSegments` position buffer.
 *
 * Built OUTWARD FROM THE CENTRE in both directions, symmetrically, so the
 * pattern is mirrored about the point the arc is seated at. That is not a
 * flourish: an asymmetric chain line reads as a line that happens to be dashed,
 * whereas a symmetric one reads as a line ABOUT something, and "about
 * something" is the entire message the axis is carrying.
 *
 * ISO 128 also says a chain line begins and ends with a LONG dash, which the
 * outward-from-centre construction gives for free at the centre and which the
 * reach clamp preserves at the ends (a cycle is emitted only if its long dash
 * fits whole; a stub is dropped rather than drawn short).
 */
export function chainLineSegments(
  anchor: AxisAnchor,
  centre: Vec3,
  options: ChainLineOptions,
): Float32Array {
  const { reach } = options;
  if (!(reach > 0)) return new Float32Array(0);
  const long = options.longMm ?? reach * CHAIN_LONG_FRAC;
  const short = options.shortMm ?? reach * CHAIN_SHORT_FRAC;
  const gap = options.gapMm ?? reach * CHAIN_GAP_FRAC;
  const cycle = long + gap + short + gap;
  // Seat the pattern on the axis's own foot beneath `centre`, so the mirror is
  // about the point the instrument stands on rather than about wherever the
  // stored axis happens to declare its base.
  const origin = axisRadial(anchor, centre).foot;

  const out: number[] = [];
  const push = (from: number, to: number): void => {
    const a = addScaled(origin, anchor.dir, from);
    const b = addScaled(origin, anchor.dir, to);
    out.push(a[0], a[1], a[2], b[0], b[1], b[2]);
  };

  // The centre long dash, straddling the origin — one dash, not two halves, so
  // the mirror line is ink rather than a seam.
  push(-long / 2, long / 2);
  const cycles = Math.max(
    CHAIN_MIN_CYCLES,
    Math.ceil((reach - long / 2) / Math.max(cycle, 1e-6)),
  );
  for (let i = 0; i < cycles; i += 1) {
    const base = long / 2 + i * cycle;
    const shortAt = base + gap;
    const longAt = shortAt + short + gap;
    if (shortAt + short <= reach) {
      push(shortAt, shortAt + short);
      push(-shortAt - short, -shortAt);
    }
    // A long dash is drawn only if it fits WHOLE: a chain line that trails off
    // in a stub reads as a line that ran out of ink.
    if (longAt + long <= reach) {
      push(longAt, longAt + long);
      push(-longAt - long, -longAt);
    }
  }
  return new Float32Array(out);
}

/**
 * How far a chain line reaches either side of the seat, given the size of the
 * thing it is the axis of.
 *
 * An axis must visibly OVERRUN the geometry it belongs to — that overrun is
 * what makes it read as an axis rather than as an edge of the part — and the
 * drawing convention is a short, constant-looking overshoot rather than a
 * proportional one. Two to three millimetres at part scale is what a draughtsman
 * leaves; expressed as a fraction here so it survives zoom the way every other
 * proportion in the gauge does.
 */
export const AXIS_OVERRUN_FRAC = 0.35;

/** Shortest drawn axis, scene mm — below this a chain pattern is illegible. */
export const AXIS_MIN_REACH_MM = 1;

/**
 * The reach for an axis serving geometry that spans `extentMm` along it and
 * reaches `radiusMm` from it.
 *
 * BOTH terms are needed and it is not obvious why. `extentMm` alone leaves a
 * disc-shaped profile (wide, flat, turned about its own centre) with an axis
 * shorter than the part is wide, which looks like a pin sticking out of a
 * plate. `radiusMm` alone leaves a long slender shaft with a stub of an axis.
 * Taking the larger of the two, plus the overrun, is the only rule that draws
 * a recognisable centreline for both.
 */
export function axisReach(extentMm: number, radiusMm: number): number {
  const half = Math.max(extentMm / 2, radiusMm);
  return Math.max(AXIS_MIN_REACH_MM, half * (1 + AXIS_OVERRUN_FRAC));
}

/**
 * The profile's extent about an axis: how far it reaches ALONG the axis, how
 * far it reaches FROM it, and the point on the axis it is centred on.
 *
 * Fed the profile's outer loops in sketch-plane (u, v), which is the form
 * `profileRegions` already produces for the extrude ghost — one derivation of
 * "what shape is being swept", two verbs reading it.
 */
export function profileAboutAxis(
  anchor: AxisAnchor,
  basis: PlaneBasis,
  loops: readonly (readonly { x: number; y: number }[])[],
): { centre: Vec3; extentMm: number; radiusMm: number } | null {
  let minAlong = Infinity;
  let maxAlong = -Infinity;
  let radius = 0;
  let any = false;
  for (const loop of loops) {
    for (const p of loop) {
      const world = onPlane(basis, p.x, p.y);
      const along = dot(sub(world, anchor.base), anchor.dir);
      minAlong = Math.min(minAlong, along);
      maxAlong = Math.max(maxAlong, along);
      radius = Math.max(radius, axisRadial(anchor, world).distance);
      any = true;
    }
  }
  if (!any) return null;
  const mid = (minAlong + maxAlong) / 2;
  return {
    centre: addScaled(anchor.base, anchor.dir, mid),
    extentMm: maxAlong - minAlong,
    radiusMm: radius,
  };
}

/**
 * A unit direction across the axis to serve as the arc's ZERO reference, given
 * the profile's own furthest-out point.
 *
 * It is the profile's radial direction whenever there is one, because the turn
 * the user is dimensioning starts AT the material: an arc that begins at an
 * arbitrary reference and sweeps to the angle would be numerically right and
 * would not describe the swept solid. {@link crossReference} is the fallback
 * for a profile centred exactly on its own axis, which is degenerate for a
 * revolve anyway (the kernel refuses it) but must not produce a NaN frame.
 */
export function crossReference(dir: Vec3): Vec3 {
  // The world axis least parallel to `dir` — the standard trick, and it cannot
  // degenerate: the smallest component of a unit vector is at most 1/sqrt(3).
  const ax = Math.abs(dir[0]);
  const ay = Math.abs(dir[1]);
  const az = Math.abs(dir[2]);
  const seed: Vec3 =
    ax <= ay && ax <= az ? [1, 0, 0] : ay <= az ? [0, 1, 0] : [0, 0, 1];
  return unit(cross(dir, cross(seed, dir))) ?? [1, 0, 0];
}

/**
 * The point of the profile furthest from the axis, and the unit radial that
 * reaches it — the arc's seat and its zero-degree reference.
 */
export function arcReference(
  anchor: AxisAnchor,
  basis: PlaneBasis,
  loops: readonly (readonly { x: number; y: number }[])[],
): Vec3 {
  let best: Vec3 | null = null;
  let bestDistance = 0;
  for (const loop of loops) {
    for (const p of loop) {
      const world = onPlane(basis, p.x, p.y);
      const { radial, distance } = axisRadial(anchor, world);
      if (radial !== null && distance > bestDistance) {
        bestDistance = distance;
        best = radial;
      }
    }
  }
  return best ?? crossReference(anchor.dir);
}

/**
 * THE DRAFT'S PIVOT — the line a tapered face rotates about.
 *
 * A draft swings the face about the line where its own plane meets the NEUTRAL
 * (parting) plane, which is why the neutral plane is a field on the form at all.
 * So the anchor is a plane-plane intersection, and the degenerate case is not an
 * error to guard against but a real modelling answer: a face PARALLEL to the
 * neutral plane has no intersection with it and cannot be drafted about it (a
 * box's top face against XY is the everyday instance). We return null, draw no
 * gauge, and leave the face-pick and the Neutral-plane control to say why —
 * which is the honest picture, and a gauge hung on an arbitrary substitute line
 * would be a confident lie about what Save is going to do.
 *
 * @param faceNormal Outward unit normal of the picked face, SCENE frame.
 * @param faceCentroid The face's area centroid, SCENE mm.
 * @param neutralNormal Unit normal of the neutral plane (the PULL direction),
 *   SCENE frame — already flipped if the form's Pull control is flipped.
 * @param neutralPoint Any point on the neutral plane, SCENE mm.
 */
export function draftAxisAnchor(
  faceNormal: Vec3,
  faceCentroid: Vec3,
  neutralNormal: Vec3,
  neutralPoint: Vec3,
): AxisAnchor | null {
  const nf = unit(faceNormal);
  const nn = unit(neutralNormal);
  if (nf === null || nn === null) return null;
  const dir = unit(cross(nf, nn));
  // Parallel planes: no pivot line exists. See the note above.
  if (dir === null) return null;
  // The point of the intersection line closest to the world origin, by the
  // standard two-plane construction. `k` is the cosine between the normals and
  // `1 - k*k` is the squared sine, which the parallel test above has already
  // proved non-zero — so this cannot divide by zero however close to parallel
  // the planes get before `unit` gives up on the cross product.
  const d1 = dot(nf, faceCentroid);
  const d2 = dot(nn, neutralPoint);
  const k = dot(nf, nn);
  const denom = 1 - k * k;
  const a = (d1 - d2 * k) / denom;
  const b = (d2 - d1 * k) / denom;
  return { base: addScaled(scale(nf, a), nn, b), dir };
}

export { onPlane as pointOnPlane };
