/**
 * THE EXTRUDE DEPTH GAUGE — the math under the drag handle (T-23).
 *
 * The design mandate names this the biggest "does not feel like a modeling
 * tool" gap in the product: *"Fusion's extrude is a draggable arrow; the
 * numeric field is the precision fallback. Ours is a form with no handle at
 * all."* The fifth product audit swept the DOM for
 * `[data-testid*="handle|gizmo|drag|arrow|manip"]` in every state it could
 * reach and got `[]` — not one drag affordance anywhere.
 *
 * This module is the part of the fix that a browser is not required to test:
 * where the handle sits, what a pointer drag means in millimetres, how the
 * value is quantised, and what a key press does to it. {@link ExtrudeDragHandle}
 * is then a thin r3f/DOM shell over these, the same seam split
 * `extrudeGhost.ts` already makes for the ghost's shading and pose — and for
 * the same reason: a decision buried in a `useMemo` inside a WebGL-only
 * component is invisible below a full browser run.
 *
 * FRAME. Everything here is SCENE space (three.js, Y-up). The basis handed in
 * must be a scene-frame one (`sceneOriginBasis` / `resolveSpecBasis` /
 * `faceBasis`); a kernel-frame basis puts the handle 90 degrees off the body it
 * is supposed to pull, which is FB-9 wearing a different hat.
 *
 * ## WHAT IS SHIPPED HERE AND WHAT IS ONLY TEST SURFACE — read before editing
 *
 * The gauge was extracted in CRAFT-8 and the arithmetic MOVED to
 * `@loft/design`'s `gauge.ts`. The app now reaches it by ONE path:
 *
 *     handleAxis -> extrudeTrack -> linearTrack -> track.*
 *
 * and `ExtrudeDragHandle.tsx` — the only importer of this module outside its
 * own test — takes exactly four names: {@link handleAxis},
 * {@link extrudeTrack}, {@link MIN_DEPTH_MM}, {@link MAX_DEPTH_MM}.
 *
 * **Everything else exported here has no caller but the test file.**
 * {@link tipPoint}, {@link depthAlongAxis}, {@link screenDragDepth},
 * {@link quantizeDepth}, {@link clampDepth}, {@link nudgeDepth},
 * {@link ladderTicks}, {@link arrowLength}, {@link sameDepth},
 * {@link keyStepMm}, {@link perspectiveMmPerPixel} and
 * {@link orthographicMmPerPixel} are thin delegations kept so the suite written
 * before the move could stay untouched and witness that the move was faithful.
 * That was their whole job and they have done it.
 *
 * Two consequences, because the first cost us a false claim already. (a) THOSE
 * CASES DO NOT COVER THE SHIPPED SEAM: seven mutations to `extrudeTrack`'s
 * options object all survived the 36 cases that were credited as this
 * refactor's evidence, because none of them runs the constructor. The
 * `extrudeTrack` block at the end of the test file is what covers the wiring;
 * keep it in step with the options object, one case per option. (b) If a change
 * in `gauge.ts` moves SHIPPED behaviour, these wrappers will happily keep
 * describing the old one — a green suite about a function nobody calls. When
 * that happens, delete the wrapper and its cases rather than "fixing" them, and
 * make sure the behaviour it described is asserted through `extrudeTrack`.
 */
import { Vector3 } from "three";

import {
  ARROW_LENGTH_FRAC as GAUGE_ARROW_LENGTH_FRAC,
  ARROW_RADIUS_FRAC as GAUGE_ARROW_RADIUS_FRAC,
  arrowLength as gaugeArrowLength,
  AXIS_SHALLOW as GAUGE_AXIS_SHALLOW,
  axisValueAt,
  clampTo,
  formatLength,
  LADDER_HALF_WIDTH_FRAC as GAUGE_LADDER_HALF_WIDTH_FRAC,
  LADDER_MAX as GAUGE_LADDER_MAX,
  ladderStops,
  linearTrack,
  nudgeIntent,
  orthographicUnitsPerPixel,
  perspectiveUnitsPerPixel,
  quantize,
  screenValue,
  steppedValue,
  type GaugeTrack,
  type Vec3,
} from "@loft/design";
import type { LengthUnit } from "@loft/design";
import type { ExtrudeDirection } from "../features/extrude";
import type { PlaneBasis } from "../sketch/plane";
import type { ProfileRegion } from "./profileLoops";

/**
 * The shortest extrude the handle will pull to, mm. Not zero: the form rejects
 * a non-positive distance (`parseDistanceMm`), so a drag that could reach 0
 * would drive the editor into a state its own Save refuses — a dead end, which
 * is the flow rule's fourth test. Dragging past the plane therefore parks here
 * rather than going invalid; reversing the sweep is the Direction control's
 * job, and it is one key away.
 */
export const MIN_DEPTH_MM = 0.1;

/** Absolute ceiling, mm — a 10 m part is past anything this kernel is for. */
export const MAX_DEPTH_MM = 10_000;

/**
 * Drag quantisation, per document unit. A pointer carries about one part in a
 * thousand of the screen; a modeller wants 12.5, not 12.4713. So a drag SNAPS
 * by default and Ctrl/Cmd suppresses it — the sketcher's own grammar, where
 * Ctrl/Cmd is already "ignore the snap" (`SketchScene`'s modifiers), so the
 * gesture transfers rather than being learnt twice.
 *
 * Imperial documents snap to 1/32 in rather than to a metric step: the value is
 * stored in canonical mm either way, but a snap the user cannot name is not a
 * snap, and nobody working in inches thinks in half-millimetres.
 */
export const SNAP_MM: Readonly<Record<LengthUnit, number>> = {
  mm: 0.5,
  cm: 0.5,
  m: 5,
  in: 25.4 / 32,
  ft: (25.4 * 12) / 16,
};

/** Keyboard step (unsnapped), per unit — one snap increment per press. */
export function keyStepMm(unit: LengthUnit): number {
  return SNAP_MM[unit];
}

/** Coarse multiplier for Shift + arrow / PageUp / PageDown. */
export const COARSE_STEP_FACTOR = 10;

/**
 * How close two depths must be to count as THE SAME LENGTH — 1e-4 mm, the
 * kernel's own linear tolerance.
 *
 * Used by the handle to recognise its own value coming back around the
 * round trip. It cannot be an exact comparison: the value passes through the
 * editor's field as a DISPLAY STRING, and `lengthInputValue` guarantees only
 * that the shown value round-trips to within 1e-5 mm of the stored one (see its
 * note — the seed precision is deliberately unit-aware for exactly this
 * reason). On a millimetre document the round trip is exact; on an inch one it
 * is not, and an equality test would therefore read every acknowledgement as a
 * stranger's edit — on inch parts only, which is the worst way for a bug to be
 * unit-dependent.
 */
export const DEPTH_EPSILON_MM = 1e-4;

/** True when two depths are the same length to within {@link DEPTH_EPSILON_MM}. */
export function sameDepth(a: number, b: number): boolean {
  return Math.abs(a - b) <= DEPTH_EPSILON_MM;
}

/** `HandleAxis`'s three-vector, as the plain tuple `@loft/design` works in. */
function tuple(v: Vector3): Vec3 {
  return [v.x, v.y, v.z];
}

/** Where the gauge is anchored and which way it pulls, in scene mm. */
export interface HandleAxis {
  /** Anchor on the sketch plane — the profile's area-weighted centre. */
  base: Vector3;
  /** Unit sweep direction (the plane normal, negated for a reverse extrude). */
  dir: Vector3;
  /** Half-diagonal of the profile's bounding box, mm — the gauge's own scale. */
  radius: number;
}

/**
 * The gauge's seat: the middle of the profile, on the plane, pointing the way
 * the sweep goes.
 *
 * The CENTROID of the outer loops' bounding boxes, not of the vertices —
 * vertex-averaging drifts toward whichever edge happens to carry more points,
 * so a rectangle with one filleted corner would seat the handle off-centre for
 * no reason the user can see. An empty profile yields the plane origin, which
 * is where the sketch's own axes cross: still a truthful place to stand.
 */
export function handleAxis(
  basis: PlaneBasis,
  direction: ExtrudeDirection,
  regions: readonly ProfileRegion[],
): HandleAxis {
  let minU = Infinity;
  let minV = Infinity;
  let maxU = -Infinity;
  let maxV = -Infinity;
  for (const region of regions) {
    for (const point of region.outer) {
      minU = Math.min(minU, point.x);
      maxU = Math.max(maxU, point.x);
      minV = Math.min(minV, point.y);
      maxV = Math.max(maxV, point.y);
    }
  }
  const empty = !Number.isFinite(minU);
  const u = empty ? 0 : (minU + maxU) / 2;
  const v = empty ? 0 : (minV + maxV) / 2;
  const radius = empty ? 0 : Math.hypot(maxU - minU, maxV - minV) / 2;

  const base = new Vector3(
    basis.origin[0] + basis.u[0] * u + basis.v[0] * v,
    basis.origin[1] + basis.u[1] * u + basis.v[1] * v,
    basis.origin[2] + basis.u[2] * u + basis.v[2] * v,
  );
  const dir = new Vector3(...basis.normal).normalize();
  if (direction === "reverse") dir.negate();
  return { base, dir, radius };
}

/** The gauge tip — where the grip and the readout ride. */
export function tipPoint(axis: HandleAxis, depthMm: number): Vector3 {
  return axis.base.clone().addScaledVector(axis.dir, depthMm);
}

/**
 * How far along the pull axis a pointer ray points, in mm from the base.
 *
 * The closest approach of two skew lines: the axis `base + t*dir` and the
 * pointer ray `origin + s*direction`. Returns null when the axis is within
 * {@link AXIS_SHALLOW} of the line of sight, where the answer would be
 * arithmetically defined and practically useless — see that constant, because
 * the case it names is the DEFAULT one, not an edge.
 */
export function depthAlongAxis(
  axis: HandleAxis,
  rayOrigin: Vector3,
  rayDirection: Vector3,
): number | null {
  return axisValueAt(
    tuple(axis.base),
    tuple(axis.dir),
    tuple(rayOrigin),
    tuple(rayDirection),
  );
}

/**
 * `sin^2` of the shallowest angle between the pull axis and the line of sight
 * at which projecting the pointer onto the axis is still WORTH doing. 0.05 is
 * about 13 degrees.
 *
 * This is not a numerical-safety epsilon, and choosing one taught the feature
 * something. `1 - (axis . ray)^2` is the divisor, so at 13 degrees a one-pixel
 * pointer move already means twenty pixels of depth; at 3 degrees it means
 * four hundred. The maths never divides by zero, it just becomes a value
 * nobody can aim.
 *
 * AND THIS POSE IS THE COMMON ONE. Save a sketch and the camera is normal to
 * the plane you drew on — the reference cube reads TOP — which is exactly the
 * pose where the extrude axis points at your eye. The first browser run of the
 * drag spec failed here, in the state a modeller reaches by doing the most
 * ordinary thing in the product: sketch, then extrude. Below this threshold the
 * handle switches to {@link screenDragDepth} instead of going dead.
 */
export const AXIS_SHALLOW = GAUGE_AXIS_SHALLOW;

/**
 * The fallback drag, for when the pull axis points at the eye: vertical pointer
 * travel, converted to millimetres at the tip's own distance from the camera.
 *
 * UP GROWS, always — a convention rather than a derivation, because the axis
 * has no readable screen direction in this pose (that is what put us here). It
 * is the one every 3D tool uses for a depth the camera cannot show, and the
 * readout at the tip means you are never guessing what you got.
 *
 * `dyPx` is `grabY - clientY`, so a pointer moved up the screen is positive.
 */
export function screenDragDepth(
  grabDepthMm: number,
  dyPx: number,
  mmPerPixel: number,
): number {
  return screenValue(grabDepthMm, dyPx, mmPerPixel);
}

/**
 * World millimetres per screen pixel at `distance` from a perspective camera —
 * the scale that makes {@link screenDragDepth} move the model at the same rate
 * as the pointer, rather than at some tuned constant that is wrong at every
 * zoom but one.
 */
export function perspectiveMmPerPixel(
  fovDeg: number,
  distance: number,
  viewportHeightPx: number,
): number {
  return perspectiveUnitsPerPixel(fovDeg, distance, viewportHeightPx);
}

/**
 * The parallel-projection counterpart: one screen pixel in world mm under an
 * ORTHOGRAPHIC camera (ORTHO-1).
 *
 * Neither distance nor field of view appears, because neither can change the
 * scale of a parallel projection — that is the definition of one. With r3f's
 * frustum convention (canvas half-extents in CSS pixels) one world unit
 * measures exactly `zoom` pixels, so the inverse is the whole formula.
 *
 * Returns 0 for a nonsensical zoom, matching `perspectiveMmPerPixel`'s
 * degenerate contract, so a caller's drag rate collapses to "no movement"
 * rather than to infinity.
 */
export function orthographicMmPerPixel(zoom: number): number {
  return orthographicUnitsPerPixel(zoom);
}

/** Clamp a depth into the range the form can actually submit. */
export function clampDepth(mm: number): number {
  return clampTo(mm, MIN_DEPTH_MM, MAX_DEPTH_MM);
}

/**
 * Quantise a dragged depth: snapped to the unit's step unless `free`
 * (Ctrl/Cmd held), then clamped.
 *
 * A FREE value is rounded to 1e-4 mm — the kernel's own linear tolerance, so
 * the field never shows 12.400000000000002 and never loses anything the kernel
 * could have used. A SNAPPED value is NOT rounded, deliberately: it is already
 * an exact multiple of the step, and 1/32 in is 0.79375 mm, so a 4-decimal
 * round would quietly push every imperial snap off its own grid. The precision
 * a value deserves depends on how it was produced.
 */
export function quantizeDepth(
  mm: number,
  unit: LengthUnit,
  free: boolean,
): number {
  return quantize(mm, SNAP_MM[unit], free, MIN_DEPTH_MM, MAX_DEPTH_MM);
}

/**
 * One press of `step`, from wherever you are: THE NEXT MULTIPLE OF `step` IN
 * THE DIRECTION PRESSED.
 *
 * THE GRID YOU LAND ON IS THE GRID OF THE KEY YOU PRESSED — that is the whole
 * rule, and it is the drawing sheet's rule too (`nudgePlacement`,
 * `apps/web/src/drawing/authoring.ts`, fixed in `1e8d8a3`; see the note on
 * {@link nudgeDepth} for why the two are not one function). The step used to be
 * ADDED to whatever the drag left behind, which sounds like a spinner and is a
 * much weaker promise: a free (Ctrl) drag leaves 12.4713, and every press after
 * it lands on 12.9713, 13.4713, 17.4713 — an offset lattice with no round
 * number anywhere in it. The damage is not the ugly figure. It is that TWO
 * features dragged separately could then never be given the same depth, so a
 * boss and the pocket that has to clear it could not be made to agree from the
 * keyboard, and a chain of features that cannot share a dimension is the same
 * failure as a chain of dimensions that cannot line up.
 *
 * Every fine press therefore lands on the fine grid and every coarse press on
 * the COARSE one — 11 mm, Shift+Up, gives 15, not 16. That is deliberate: the
 * coarse step exists to traverse, the round numbers a part is dimensioned in
 * are the decade marks, and those are the very graduations {@link ladderTicks}
 * draws on the gauge, so a coarse press lands on a tick the user can see.
 *
 * NEXT multiple, not "nearest multiple then one along". The two differ only off
 * the grid and the difference is the whole usefulness of the first press: from
 * 12.4713 this gives 12.5, where nearest-then-along gives 13 and SKIPS the very
 * value the user is standing next to. (It also stops Shift+Down from 11 mm
 * meaning 5 mm — nearest-then-along rounds 11 to 10 and then subtracts a whole
 * coarse step. It means 10, which is what anyone would expect.) It cannot
 * no-op: a value already on the grid moves one full step, which is the
 * `already` branch.
 */
export function steppedDepth(
  current: number,
  step: number,
  sign: 1 | -1,
): number {
  return steppedValue(current, step, sign, MIN_DEPTH_MM, MAX_DEPTH_MM);
}

/**
 * The depth a key press means, or null when the key is not ours.
 *
 * Up/Right grow the sweep, Down/Left shrink it — the direction the value moves
 * on screen, not the direction of the axis in space (which points wherever the
 * camera happens to have put it). Shift and the Page keys take ten steps, the
 * spinner convention every numeric control in this app already follows, and
 * each modifier quantises to ITS OWN grid ({@link steppedDepth}).
 *
 * Null for any other key, which is load-bearing rather than tidy: Enter must
 * still reach the editor's submit and Escape its cancel, or the one control
 * that finally lets you set a depth by hand becomes the one place you cannot
 * finish (the flow rule's "no dead ends").
 *
 * NOT SHARED WITH THE DRAWING SHEET'S NUDGE, deliberately. `nudgePlacement`
 * moves a 2-D seat on an authoring state machine in sheet millimetres; this
 * moves a 1-D depth clamped to a submittable range, with the step derived from
 * the document unit and a key map of its own. The only thing genuinely common
 * to them is `round(v/s)*s`, three lines of arithmetic — extracting THAT into a
 * shared module would move a primitive out of both files without removing a
 * line of duplicated logic from either, which is the premature abstraction the
 * DRY rule explicitly excludes. What the two must share is the RULE, so it is
 * stated in both places and each points at the other.
 */
export function nudgeDepth(
  current: number,
  key: string,
  unit: LengthUnit,
  shift: boolean,
): number | null {
  const intent = nudgeIntent(key, shift);
  if (intent === null) return null;
  const step = keyStepMm(unit) * Math.pow(COARSE_STEP_FACTOR, intent.grids);
  return steppedDepth(current, step, intent.sign);
}

/**
 * THE SIGNATURE ELEMENT: the depth ladder's graduations, in mm from the base.
 *
 * A plain arrow says "you may pull this". A ruled arrow says "and here is what
 * you are pulling against" — which is the difference between a generic gizmo
 * and a machinist's depth gauge, and it is the one place this handle spends
 * boldness. The ticks are not decoration: their spacing IS the readable scale
 * of the sweep, chosen from the 1/2/5 decade series so the step is always a
 * number a person would say out loud (1, 2, 5, 10, 20, 50 mm...).
 *
 * At most {@link LADDER_MAX} graduations, so a 3 mm boss and a 300 mm column
 * both get a legible ladder rather than one tick or four hundred; the 1/2/5
 * rule puts the floor at six in practice, which the unit test pins across five
 * decades rather than a constant asserting it of itself. Excludes the base (the
 * plane draws itself) and any tick within half a step of the tip (it would
 * collide with the grip).
 */
export function ladderTicks(depthMm: number): number[] {
  return [...ladderStops(depthMm).major];
}

/** Most graduations a ladder is allowed to show. */
export const LADDER_MAX = GAUGE_LADDER_MAX;

/**
 * Half-width of a graduation, as a fraction of the profile radius. The ladder
 * is a rung ACROSS the axis, not a dot on it, so it reads at a glance without
 * competing with the sketch ink beneath.
 *
 * Sized by SCREENSHOT, not by taste: at 0.06 the rungs measured a couple of
 * millimetres on a 66 mm profile and were invisible in the founder capture —
 * present in the buffer, absent from the picture, which is the worst of both.
 */
export const LADDER_HALF_WIDTH_FRAC = GAUGE_LADDER_HALF_WIDTH_FRAC;

/** Arrow-head length, as a fraction of the profile radius. */
export const ARROW_LENGTH_FRAC = GAUGE_ARROW_LENGTH_FRAC;

/** Arrow-head radius, as a fraction of its own length. */
export const ARROW_RADIUS_FRAC = GAUGE_ARROW_RADIUS_FRAC;

/**
 * The arrow is sized from the PROFILE, never from the depth, so it holds still
 * while you drag — a manipulator that grows under the cursor reads as the model
 * moving. Clamped so a tiny profile still gets a grabbable arrow and a huge one
 * does not get a traffic cone.
 */
export function arrowLength(radius: number): number {
  return gaugeArrowLength(radius);
}

/**
 * THE EXTRUDE'S GAUGE TRACK — everything above, handed to `<ParametricGauge>`
 * as one object.
 *
 * This is the seam the whole wave stands on. The shell owns the state and the
 * correctness (the ask-queue, pointer capture, key handling, the grip and the
 * tag); the track owns the arithmetic, and the shell never asks what KIND of
 * track it has. Extrude's is a {@link linearTrack} over the profile's seat,
 * carrying the document unit's snap, its key step and its formatter — which is
 * the whole of what makes this an EXTRUDE gauge rather than a generic slider.
 *
 * `arms` are the sketch plane's own `u`/`v`, so a graduation cross is drawn in
 * the plane the profile lives in rather than on an arbitrary derived frame.
 */
export function extrudeTrack(
  axis: HandleAxis,
  basis: PlaneBasis,
  unit: LengthUnit,
): GaugeTrack {
  return linearTrack(
    {
      base: tuple(axis.base),
      dir: tuple(axis.dir),
      radius: axis.radius,
      arms: [basis.u, basis.v],
    },
    {
      min: MIN_DEPTH_MM,
      max: MAX_DEPTH_MM,
      snap: SNAP_MM[unit],
      keyStep: keyStepMm(unit),
      coarseFactor: COARSE_STEP_FACTOR,
      epsilon: DEPTH_EPSILON_MM,
      format: (mm, opts) => formatLength(mm, unit, opts ?? {}),
    },
  );
}
