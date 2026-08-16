/**
 * THE SKETCH PLANE'S OWN FRAME — where (0,0) is, what it IS, and the geometry
 * that draws it. Pure math + copy, no three.js, no store.
 *
 * Founder report, 2026-08-02: *"there isn't an origin to start a drawing
 * from."* Exactly right, twice over — the snap layer offered four kinds
 * (endpoint / midpoint / centre / intersection), all of them derived from
 * geometry you had ALREADY drawn, so the first point of an empty sketch had
 * nothing to hold onto; and nothing on screen said where zero was. That second
 * half is the mechanism behind QA3-2, where a ring drawn at "sketch (0,0)" came
 * out 0.065 mm eccentric: the sketch's zero was the seated face's area
 * centroid, unnamed and unmarked, so "the middle" and "the origin" looked like
 * the same place and were not.
 *
 * ## Which frame the origin names — and the honesty rule
 *
 * The origin is ALWAYS plane (0,0) — `planeToWorld(basis, {x:0,y:0})` is
 * `basis.origin` by construction, so this module never needs the world frame
 * and cannot be broken by a change of world convention (Z-up ↔ Y-up). What
 * differs between plane kinds is what that point IS out in the model, and
 * whether it STAYS PUT:
 *
 *   · an origin datum (XY/XZ/YZ) — the part origin, world zero. Fixed.
 *   · an offset datum — the part origin carried along the base normal. Fixed.
 *   · any other datum (offset-from, midplane) — that datum's own zero. Fixed
 *     for as long as the datum's parents are.
 *   · a sketch seated on a picked FACE — the face's AREA CENTROID (the kernel's
 *     `resolve_face_plane`, mirrored by `faceBasis`). It is NOT fixed: change
 *     the outline of that face and the centroid moves, taking the sketch's zero
 *     with it.
 *
 * The last one is why {@link originIdentity} returns a `note` as well as a
 * label. A marker that called the centroid "Origin" would imply a stability it
 * does not have, which is the same class of defect as a snap that silently
 * grabs the wrong thing: the model ends up subtly wrong and nothing on screen
 * ever said so.
 */
import type { Point2D, SketchPlaneSpec } from "./plane";

/** What a plane's zero is called, and what the user must know about it. */
export interface OriginIdentity {
  /** The word the marker and the snap mark carry. */
  label: string;
  /**
   * The caveat, or null when the point is a fixed datum zero. Present only
   * where the origin can MOVE under the user without them touching the sketch.
   */
  note: string | null;
}

/** Fixed datum zero — the label three of the four plane kinds carry. */
const ORIGIN: OriginIdentity = { label: "Origin", note: null };

/**
 * What this sketch's (0,0) is, named honestly. See the module note: only the
 * face-seated case can move, and it is the only one that carries a caveat.
 */
export function originIdentity(plane: SketchPlaneSpec | null): OriginIdentity {
  if (plane === null) return ORIGIN;
  switch (plane.kind) {
    case "origin":
    case "offset":
    case "datum":
      return ORIGIN;
    case "on_face":
      return {
        label: "Face centre",
        note: "The face's area centre — it moves if the outline changes.",
      };
  }
}

/**
 * Ring radius as a fraction of the frame half-height the sketch camera parks
 * at. A fraction rather than a millimetre count because the sketcher's scale is
 * whatever the subject is: a fixed 1.5 mm mark is a fair centre punch on a
 * datum sheet and an invisible speck on a 400 mm face. Tied to the camera's own
 * framing, the mark holds the same size on screen at every plane size.
 */
export const ORIGIN_RING_FRACTION = 0.022;

/** Axes overrun the entry frame slightly, so they read as axes, not a plus. */
export const ORIGIN_AXIS_FRACTION = 1.25;

/**
 * Where the engraved letter sits along its axis, as a fraction of the axis
 * length. NOT at the tip, and that is a correction rather than a preference:
 * the axes deliberately overrun the entry frame (above), so a letter at the tip
 * of +Y was always outside the top of the view — measured on the first
 * captured frame, where X happened to land inside only because the viewport is
 * wider than it is tall. A label nobody can see is decoration, and decoration
 * is a defect (CLAUDE.md mandate 3a).
 *
 * 0.56 of the axis is 0.7 of the frame half-height, which clears the command
 * band at the top and the DRO at the bottom-left at both 1600 and 1280. The
 * line still runs on past the letter, which is exactly how a drawing engraves a
 * centreline anyway.
 */
export const ORIGIN_LABEL_FRACTION = 0.56;

/** Phantom (−) half dash pattern, as a fraction of the axis length. */
export const ORIGIN_DASH_FRACTION = 0.03;
export const ORIGIN_GAP_FRACTION = 0.022;

/**
 * How far the sketch camera parks from a datum sheet (mm), and the perspective
 * field of view it looks through. Both live here — with the fractions they
 * scale — rather than in the scene, because the frame's PICK geometry
 * (`sketch/datum.ts`) is derived from the same framing and cannot import
 * three.js. Two copies of "how big is the parked frame" is exactly the drift
 * the pick region was rewritten to close.
 *
 * The fov is the Canvas camera's (`viewport/Viewport.tsx`), mirrored here as
 * the number `cameraFov()` falls back to when a scene hands us an orthographic
 * camera that has none.
 */
export const SKETCH_CAMERA_DISTANCE_MM = 170;
export const SKETCH_CAMERA_FOV_DEG = 40;

/**
 * Half the height of the frame the sketch camera parks at, in plane mm —
 * `distance · tan(fov/2)`, the standard perspective half-extent.
 *
 * DERIVED, not written down, because the written-down version was wrong: a
 * literal `80` shipped under a comment claiming it WAS this derivation, when
 * the derivation gives **61.88 mm** (170 × tan 20°) — 29 % high. It bit in two
 * places, both quiet: the window before the scene reports the measured framing
 * in (`setDatumFrame`), and every unit test that took the default and therefore
 * reasoned about a 1.76 mm origin ring where the product draws 1.36 mm.
 */
export function parkedFrameHalfHeightMm(
  distanceMm: number = SKETCH_CAMERA_DISTANCE_MM,
  fovDeg: number = SKETCH_CAMERA_FOV_DEG,
): number {
  return distanceMm * Math.tan((fovDeg * Math.PI) / 360);
}

/** Segments in the origin ring — enough to read round at any zoom we frame. */
const RING_SEGMENTS = 32;

/**
 * The origin ring as plane-mm segment pairs: a small open circle struck at
 * (0,0). The two axes cross it, so the composite reads as a drafting centre
 * mark without a second element being drawn (Chanel's rule — the axes were
 * already there, so the cross is free). The ring stands alone if the axes are
 * ever hidden, which is why the ring and not the cross is the mark.
 */
export function originRingSegments(
  radiusMm: number,
): Array<[Point2D, Point2D]> {
  const out: Array<[Point2D, Point2D]> = [];
  if (!(radiusMm > 0)) return out;
  const at = (i: number): Point2D => {
    const t = (i / RING_SEGMENTS) * Math.PI * 2;
    return { x: Math.cos(t) * radiusMm, y: Math.sin(t) * radiusMm };
  };
  for (let i = 0; i < RING_SEGMENTS; i += 1) out.push([at(i), at(i + 1)]);
  return out;
}

/** One plane axis, split into the halves that are drawn differently. */
export interface OriginAxisSpan {
  /** Which axis — the DRO's own X/Y, i.e. the plane basis's u and v. */
  key: "x" | "y";
  /** The engraved letter at the positive end. */
  label: string;
  /** Solid half, origin → +end. */
  positive: [Point2D, Point2D];
  /** Phantom (dashed) half, origin → −end. */
  negative: [Point2D, Point2D];
  /** Where the letter hangs — on the positive half, inside the entry frame. */
  tip: Point2D;
}

/**
 * The two plane axes through the origin, each solid on its positive half and
 * phantom on its negative one.
 *
 * That encoding is not decoration and it is not new: `viewport/OriginGeometry`
 * already draws the WORLD triad this way, and dashed-means-absent is this
 * product's language throughout (hidden edges on a drawing sheet, the ghost
 * eye). So the line itself says which way +X runs, with the engraved letter at
 * the positive end confirming it — no legend, and one axis dialect across both
 * places axes are drawn.
 *
 * The letters are X and Y because that is what the DRO calls these two
 * numbers, and the DRO reads them off this same basis (`worldToPlane` projects
 * onto u and v). They name the SKETCH's frame, never the world's — so a change
 * of world convention cannot make this label disagree with the readout beside
 * it.
 */
export function originAxisSpans(halfLengthMm: number): OriginAxisSpan[] {
  const L = Math.max(halfLengthMm, 0);
  const at = L * ORIGIN_LABEL_FRACTION;
  const zero: Point2D = { x: 0, y: 0 };
  return [
    {
      key: "x",
      label: "X",
      positive: [zero, { x: L, y: 0 }],
      negative: [zero, { x: -L, y: 0 }],
      tip: { x: at, y: 0 },
    },
    {
      key: "y",
      label: "Y",
      positive: [zero, { x: 0, y: L }],
      negative: [zero, { x: 0, y: -L }],
      tip: { x: 0, y: at },
    },
  ];
}
