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
 */
import { Vector3 } from "three";

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
  const rd = rayDirection.clone().normalize();
  const w0 = axis.base.clone().sub(rayOrigin);
  const b = axis.dir.dot(rd);
  const denom = 1 - b * b;
  if (Math.abs(denom) < AXIS_SHALLOW) return null;
  const d = axis.dir.dot(w0);
  const e = rd.dot(w0);
  return (b * e - d) / denom;
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
export const AXIS_SHALLOW = 0.05;

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
  return grabDepthMm + dyPx * mmPerPixel;
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
  if (viewportHeightPx <= 0) return 0;
  return (
    (2 * Math.tan((fovDeg * Math.PI) / 180 / 2) * distance) / viewportHeightPx
  );
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
  return zoom > 0 ? 1 / zoom : 0;
}

/** Clamp a depth into the range the form can actually submit. */
export function clampDepth(mm: number): number {
  return Math.min(MAX_DEPTH_MM, Math.max(MIN_DEPTH_MM, mm));
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
  const step = SNAP_MM[unit];
  if (free || step <= 0) return clampDepth(Math.round(mm * 1e4) / 1e4);
  return clampDepth(Math.round(mm / step) * step);
}

/**
 * How near a multiple of the step counts as ON it — a relative epsilon, applied
 * to the step COUNT rather than to the length, because that is the quantity
 * {@link steppedDepth} floors.
 */
const GRID_EPSILON = 1e-9;

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
  if (!Number.isFinite(step) || step <= 0) {
    return clampDepth(current + sign * step);
  }
  const count = current / step;
  const nearest = Math.round(count);
  const already = Math.abs(count - nearest) <= GRID_EPSILON;
  const landing = already
    ? nearest + sign
    : sign > 0
      ? Math.floor(count) + 1
      : Math.ceil(count) - 1;
  // ONE multiply, so the answer is the float nearest to a multiple of the step
  // and carries no addition dust — which matters for the imperial steps (1/32
  // in is 0.79375 mm) that {@link quantizeDepth} deliberately declines to round.
  return clampDepth(landing * step);
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
  const step = keyStepMm(unit) * (shift ? COARSE_STEP_FACTOR : 1);
  switch (key) {
    case "ArrowUp":
    case "ArrowRight":
      return steppedDepth(current, step, 1);
    case "ArrowDown":
    case "ArrowLeft":
      return steppedDepth(current, step, -1);
    case "PageUp":
      return steppedDepth(current, step * COARSE_STEP_FACTOR, 1);
    case "PageDown":
      return steppedDepth(current, step * COARSE_STEP_FACTOR, -1);
    default:
      return null;
  }
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
  if (!(depthMm > 0)) return [];
  const decade = Math.pow(10, Math.floor(Math.log10(depthMm / LADDER_MAX)));
  let step = decade;
  // The last factor always satisfies the ceiling (10*decade >= depth/12 by
  // construction), so this loop is total — no fallback branch is reachable.
  for (const factor of [1, 2, 5, 10]) {
    step = decade * factor;
    if (depthMm / step <= LADDER_MAX) break;
  }
  const ticks: number[] = [];
  for (let at = step; at < depthMm - step * 0.5; at += step) {
    ticks.push(Math.round(at * 1e6) / 1e6);
  }
  return ticks;
}

/** Most graduations a ladder is allowed to show. */
export const LADDER_MAX = 12;

/**
 * Half-width of a graduation, as a fraction of the profile radius. The ladder
 * is a rung ACROSS the axis, not a dot on it, so it reads at a glance without
 * competing with the sketch ink beneath.
 *
 * Sized by SCREENSHOT, not by taste: at 0.06 the rungs measured a couple of
 * millimetres on a 66 mm profile and were invisible in the founder capture —
 * present in the buffer, absent from the picture, which is the worst of both.
 */
export const LADDER_HALF_WIDTH_FRAC = 0.18;

/** Arrow-head length, as a fraction of the profile radius. */
export const ARROW_LENGTH_FRAC = 0.25;

/** Arrow-head radius, as a fraction of its own length. */
export const ARROW_RADIUS_FRAC = 0.42;

/**
 * The arrow is sized from the PROFILE, never from the depth, so it holds still
 * while you drag — a manipulator that grows under the cursor reads as the model
 * moving. Clamped so a tiny profile still gets a grabbable arrow and a huge one
 * does not get a traffic cone.
 */
export function arrowLength(radius: number): number {
  return Math.min(18, Math.max(2, radius * ARROW_LENGTH_FRAC));
}
