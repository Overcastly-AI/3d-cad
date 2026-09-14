/**
 * THE PARAMETRIC GAUGE'S ARITHMETIC — idiom D, the part a browser is not
 * required to test (W3 direction §5, §6.3).
 *
 * ## The law of the idiom, in four lines, because this module serves the fourth
 *
 *  · brass + leader + `Kbd` = an offer you can take right now. (A)
 *  · mist + no leader + no `Kbd` = a name for what is under the pointer. (B)
 *  · band cell + eyebrow + `×` = a held state that renames verbs. (C)
 *  · **brass line-work + grip + graduations = a value you can pull. (D)**
 *
 * A gauge that only DISPLAYS a number is idiom B wearing brass, and is the
 * decorative-chrome defect mandate 3c names. Nothing may add a fifth idiom.
 *
 * ## Why the arithmetic is here and the meshes are not
 *
 * `packages/design` has no `three`, no `@react-three/fiber`, no
 * `@react-three/drei`, and must not gain one: every primitive test would then
 * boot a WebGL stack, and viewport rendering would live inside the package the
 * DOM chrome imports. So the gauge splits along the seam this repo already uses
 * everywhere else (`extrudeHandle.ts` ↔ `ExtrudeDragHandle.tsx`,
 * `extrudeGhost.ts` ↔ `ExtrudePreview.tsx`): stateless arithmetic on plain
 * `[x, y, z]` tuples here, the r3f shell in `apps/web/src/viewport/`.
 *
 * PLAIN TUPLES, NOT `Vector3`. `three`'s vector is mutable and allocating; the
 * arithmetic is about forty lines either way, and staying tuple-based is what
 * lets this package remain dependency-clean and unit-tested in jsdom. The shell
 * converts at the boundary, exactly as `extrudeHandle.ts` already does in
 * reverse.
 *
 * ## One primitive, three tracks — not three primitives, and not modes
 *
 * Everything that is STATE and CORRECTNESS is shared (the optimistic ask-queue
 * and its reconciliation, the DOM grip, the tag, ladder visibility, key
 * stepping, the nested cancel). Everything that DIFFERS is stateless
 * arithmetic: the drawn geometry, the pointer-ray projection, the screen
 * fallback, the stop set, the formatter, the clamp. That is a strategy split,
 * which is why the track is INJECTED and the shell never branches on a `kind`:
 * the hard part is identical across the three and the easy part is not. Three
 * copies of a lost-update fix whose symptom is *an occasional wrong number* is
 * the worst thing this wave could ship.
 *
 * ## What is proven by what, said plainly
 *
 * {@link linearTrack} is the extrude gauge's own arithmetic, MOVED here rather
 * than rewritten: `apps/web/src/viewport/extrudeHandle.ts` still exports every
 * function it used to and now delegates to this module, so that file's
 * untouched unit suite is the evidence the move was faithful.
 * {@link steppedTrack} is `linearTrack` with an integer quantiser and is
 * exercised only by the tests below. {@link angularTrack} has no consumer at
 * all yet — its first one should check it against a real camera before
 * trusting the screen fallback's sign convention, and a correction it needs is
 * a correction to this file, not a reason to write a fourth projection
 * somewhere else.
 */
import { proposal } from "./tokens";

/** A point or direction in world space. Plain tuple — see the module note. */
export type Vec3 = readonly [number, number, number];

// --- TUPLE ARITHMETIC --------------------------------------------------------
// Deliberately not exported: the surface of this module is tracks and stops,
// not a vector library. `three` is the vector library; this is the forty lines
// that let the design system avoid importing it.

function add(a: Vec3, b: Vec3): Vec3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}

function sub(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function scale(a: Vec3, k: number): Vec3 {
  return [a[0] * k, a[1] * k, a[2] * k];
}

function addScaled(a: Vec3, b: Vec3, k: number): Vec3 {
  return [a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k];
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

function length(a: Vec3): number {
  return Math.sqrt(dot(a, a));
}

/** Unit vector, or the input when it has no direction to give. */
function normalize(a: Vec3): Vec3 {
  const l = length(a);
  return l > 0 ? scale(a, 1 / l) : a;
}

// --- STOPS, DRAWING, AND THE TRACK CONTRACT ----------------------------------

/**
 * The graduations in view at this value and this camera scale.
 *
 * MAJOR AND MINOR ARE SEPARATE FIELDS RATHER THAN ONE ARRAY, from the start.
 * Only the angular track distinguishes them today, but flattening now would
 * force a signature change the moment one does — the `ViewCreate.auto_place`
 * trap this repo has already paid for once, where a required-field change and
 * its callers had to land in one commit across two agents' territories.
 */
export interface GaugeStops {
  /** Values a major graduation is drawn at — and, per §3.1, the snap stops. */
  major: readonly number[];
  /** Finer graduations between the majors. Empty when the track has none. */
  minor: readonly number[];
  /** Spacing of the finest graduation drawn, in track units. 0 when none. */
  pitch: number;
}

/** No graduations — the rest state, and what a track with nothing to rule returns. */
export const NO_STOPS: GaugeStops = { major: [], minor: [], pitch: 0 };

/**
 * What the instrument looks like, in world space, at one value.
 *
 * A DESCRIPTION, not geometry: the shell owns the meshes because only it has
 * `three`. Radii are here rather than in the shell because they are derived
 * from the seat's own scale, which is the track's business, and because a
 * manipulator whose proportions live in a `useMemo` inside a WebGL-only
 * component is invisible below a full browser run.
 */
export interface TrackDrawing {
  /**
   * The drawn spine, seat → value: two points for a straight track, a polyline
   * for an arc. The arrowhead sits on the far end.
   */
  spine: readonly Vec3[];
  /**
   * Radius of the spine drawn as a SOLID tube. WebGL line width is clamped to
   * 1 px on every desktop driver we target, so a GL line reads as an
   * annotation — which is what a dimension leader is and what a manipulator
   * must not be.
   */
  spineRadius: number;
  /** The arrowhead terminating the spine: its base ring, its point, its size. */
  head: { base: Vec3; tip: Vec3; length: number; radius: number };
  /**
   * Graduation strokes, as pairs of world points. A graduation is a CROSS (two
   * strokes) rather than a single rung: a rung lies along one in-plane axis, so
   * from a three-quarter view it projects as a skewed dash that reads as debris
   * rather than a scale. Two arms always project to something centred on the
   * spine, from any camera.
   */
  rungs: readonly (readonly [Vec3, Vec3])[];
}

/**
 * The stateless half of a gauge: where it is drawn, what a pointer means on it,
 * and how its value is spoken. Injected into the shell, never switched on.
 */
export interface GaugeTrack {
  /** World point of the grip at `value`. */
  pointAt(value: number): Vec3;
  /** Pointer ray → value, or null when the track is unaimable from here. */
  valueAt(rayOrigin: Vec3, rayDirection: Vec3): number | null;
  /** Fallback when {@link valueAt} is null: screen travel → value. */
  screenValueAt(
    grabValue: number,
    dxPx: number,
    dyPx: number,
    unitsPerPixel: number,
  ): number;
  /** The instrument's drawn form at `value`, ruled with `stops`. */
  draw(value: number, stops: GaugeStops): TrackDrawing;
  /** The graduations in view at this value and camera scale. */
  stops(value: number, unitsPerPixel: number): GaugeStops;
  /** Clamp into the range the owning form can actually submit. */
  clamp(value: number): number;
  /** Quantise a DRAGGED value: snapped unless `free` (Ctrl/Cmd), then clamped. */
  quantize(value: number, free: boolean): number;
  /** Spoken and displayed form — `unitSuffix: false` for the bare tag cell. */
  format(value: number, opts?: { unitSuffix?: boolean }): string;
  /** One fine key press, in track units. */
  step(stops: GaugeStops): number;
  /** One coarse key press (Shift / the Page keys), in track units. */
  coarseStep(stops: GaugeStops): number;
  /**
   * The value a key press means, or null when the key is not ours — which is
   * load-bearing rather than tidy: Enter must still reach the editor's submit
   * and Escape its cancel, or the one control that finally lets you set this
   * number by hand becomes the one place you cannot finish.
   */
  nudge(current: number, key: string, coarse: boolean): number | null;
  /**
   * Are these the same value? Used by the ask-queue to recognise its own value
   * coming back around the round trip, so it cannot be an exact comparison: the
   * value passes through a form field as a DISPLAY STRING.
   */
  same(a: number, b: number): boolean;
}

// --- PROJECTION --------------------------------------------------------------

/**
 * `sin²` of the shallowest angle between a straight track and the line of sight
 * at which projecting the pointer onto it is still WORTH doing. 0.05 is about
 * 13 degrees.
 *
 * This is not a numerical-safety epsilon, and choosing one taught the feature
 * something. `1 - (axis · ray)²` is the divisor, so at 13 degrees a one-pixel
 * pointer move already means twenty pixels of value; at 3 degrees it means four
 * hundred. The maths never divides by zero, it just becomes a value nobody can
 * aim.
 *
 * AND THIS POSE IS THE COMMON ONE. Save a sketch and the camera is normal to
 * the plane you drew on, which is exactly the pose where an extrude axis points
 * at your eye. Below this threshold the gauge switches to
 * {@link GaugeTrack.screenValueAt} instead of going dead.
 */
export const AXIS_SHALLOW = 0.05;

/**
 * How far along a straight track a pointer ray points, in track units from the
 * seat — the closest approach of two skew lines. Null when the track is within
 * {@link AXIS_SHALLOW} of the line of sight.
 */
export function axisValueAt(
  base: Vec3,
  dir: Vec3,
  rayOrigin: Vec3,
  rayDirection: Vec3,
): number | null {
  const rd = normalize(rayDirection);
  const w0 = sub(base, rayOrigin);
  const b = dot(dir, rd);
  const denom = 1 - b * b;
  if (Math.abs(denom) < AXIS_SHALLOW) return null;
  const d = dot(dir, w0);
  const e = dot(rd, w0);
  return (b * e - d) / denom;
}

/**
 * World units per screen pixel at `distance` from a PERSPECTIVE camera — the
 * scale that makes a screen-fallback drag move the model at the same rate as
 * the pointer, rather than at some tuned constant that is wrong at every zoom
 * but one. Returns 0 for a degenerate viewport.
 */
export function perspectiveUnitsPerPixel(
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
 * The fallback drag, for when the track points at the eye: screen travel,
 * converted to track units at the grip's own distance from the camera.
 *
 * UP GROWS, always — a convention rather than a derivation, because the track
 * has no readable screen direction in this pose (that is what put us here). It
 * is the one every 3D tool uses for a value the camera cannot show, and the
 * readout at the tip means you are never guessing what you got.
 *
 * `dyPx` is `grabY - clientY`, so a pointer moved up the screen is positive.
 */
export function screenValue(
  grabValue: number,
  dyPx: number,
  unitsPerPixel: number,
): number {
  return grabValue + dyPx * unitsPerPixel;
}

/**
 * The parallel-projection counterpart (ORTHO-1). Neither distance nor field of
 * view appears, because neither can change the scale of a parallel
 * projection — that is the definition of one. With r3f's frustum convention one
 * world unit measures exactly `zoom` pixels, so the inverse is the whole
 * formula. Returns 0 for a nonsensical zoom, matching
 * {@link perspectiveUnitsPerPixel}'s degenerate contract, so a caller's drag
 * rate collapses to "no movement" rather than to infinity.
 */
export function orthographicUnitsPerPixel(zoom: number): number {
  return zoom > 0 ? 1 / zoom : 0;
}

// --- QUANTISING AND STEPPING -------------------------------------------------

/** Clamp `value` into `[min, max]`. */
export function clampTo(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * Quantise a dragged value: snapped to `snap` unless `free`, then clamped.
 *
 * A FREE value is rounded to `precision` — the kernel's own linear tolerance
 * for a length — so the field never shows 12.400000000000002 and never loses
 * anything the kernel could have used. A SNAPPED value is NOT rounded,
 * deliberately: it is already an exact multiple of the step, and 1/32 in is
 * 0.79375 mm, so a 4-decimal round would quietly push every imperial snap off
 * its own grid. The precision a value deserves depends on how it was produced.
 */
export function quantize(
  value: number,
  snap: number,
  free: boolean,
  min: number,
  max: number,
  precision = 1e4,
): number {
  if (free || snap <= 0) {
    return clampTo(Math.round(value * precision) / precision, min, max);
  }
  return clampTo(Math.round(value / snap) * snap, min, max);
}

/**
 * How near a multiple of the step counts as ON it — a relative epsilon, applied
 * to the step COUNT rather than to the value, because that is the quantity
 * {@link steppedValue} floors.
 */
const GRID_EPSILON = 1e-9;

/**
 * One press of `step`, from wherever you are: THE NEXT MULTIPLE OF `step` IN
 * THE DIRECTION PRESSED.
 *
 * THE GRID YOU LAND ON IS THE GRID OF THE KEY YOU PRESSED — that is the whole
 * rule, and it is the drawing sheet's rule too (`nudgePlacement`,
 * `apps/web/src/drawing/authoring.ts`). The step used to be ADDED to whatever
 * the drag left behind, which sounds like a spinner and is a much weaker
 * promise: a free (Ctrl) drag leaves 12.4713, and every press after it lands on
 * 12.9713, 13.4713, 17.4713 — an offset lattice with no round number anywhere
 * in it. The damage is not the ugly figure. It is that TWO features dragged
 * separately could then never be given the same value, so a boss and the pocket
 * that has to clear it could not be made to agree from the keyboard, and a
 * chain of features that cannot share a dimension is the same failure as a
 * chain of dimensions that cannot line up.
 *
 * NEXT multiple, not "nearest multiple then one along". The two differ only off
 * the grid and the difference is the whole usefulness of the first press: from
 * 12.4713 this gives 12.5, where nearest-then-along gives 13 and SKIPS the very
 * value the user is standing next to. It cannot no-op: a value already on the
 * grid moves one full step, which is the `already` branch.
 */
export function steppedValue(
  current: number,
  step: number,
  sign: 1 | -1,
  min: number,
  max: number,
): number {
  if (!Number.isFinite(step) || step <= 0) {
    return clampTo(current + sign * step, min, max);
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
  // in is 0.79375 mm) that {@link quantize} deliberately declines to round.
  return clampTo(landing * step, min, max);
}

/**
 * Which way a key press moves the value, and by how many grids — or null when
 * the key is not the gauge's.
 *
 * Up/Right grow, Down/Left shrink: the direction the value moves ON SCREEN, not
 * the direction of the track in space (which points wherever the camera happens
 * to have put it). Shift and the Page keys take a coarse grid, the spinner
 * convention every numeric control in this app already follows.
 */
export function nudgeIntent(
  key: string,
  coarse: boolean,
): { sign: 1 | -1; grids: number } | null {
  switch (key) {
    case "ArrowUp":
    case "ArrowRight":
      return { sign: 1, grids: coarse ? 1 : 0 };
    case "ArrowDown":
    case "ArrowLeft":
      return { sign: -1, grids: coarse ? 1 : 0 };
    case "PageUp":
      return { sign: 1, grids: coarse ? 2 : 1 };
    case "PageDown":
      return { sign: -1, grids: coarse ? 2 : 1 };
    default:
      return null;
  }
}

// --- THE LADDER --------------------------------------------------------------

/** Most graduations a ladder is allowed to show. */
export const LADDER_MAX = 12;

/**
 * THE SIGNATURE ELEMENT: the ladder's graduations, in track units from the seat.
 *
 * A plain arrow says "you may pull this". A ruled arrow says "and here is what
 * you are pulling against" — which is the difference between a generic gizmo
 * and a machinist's depth gauge, and it is the one place this instrument spends
 * boldness. The ticks are not decoration: their spacing IS the readable scale
 * of the value, chosen from the 1/2/5 decade series so the step is always a
 * number a person would say out loud (1, 2, 5, 10, 20, 50…).
 *
 * At most {@link LADDER_MAX} graduations, so a 3 mm boss and a 300 mm column
 * both get a legible ladder rather than one tick or four hundred; the 1/2/5
 * rule puts the floor at six in practice. Excludes the seat (the plane draws
 * itself) and any tick within half a step of the tip (it would collide with the
 * grip).
 */
export function ladderStops(span: number): GaugeStops {
  if (!(span > 0)) return NO_STOPS;
  const decade = Math.pow(10, Math.floor(Math.log10(span / LADDER_MAX)));
  let step = decade;
  // The last factor always satisfies the ceiling (10*decade >= span/12 by
  // construction), so this loop is total — no fallback branch is reachable.
  for (const factor of [1, 2, 5, 10]) {
    step = decade * factor;
    if (span / step <= LADDER_MAX) break;
  }
  const major: number[] = [];
  for (let at = step; at < span - step * 0.5; at += step) {
    major.push(Math.round(at * 1e6) / 1e6);
  }
  return { major, minor: [], pitch: step };
}

// --- SEAT AND PROPORTION -----------------------------------------------------

/** Where a gauge is anchored, which way it runs, and its own scale. */
export interface GaugeSeat {
  /** Anchor in world space — the point value 0 sits at. */
  base: Vec3;
  /** Unit direction the value grows along. */
  dir: Vec3;
  /**
   * The gauge's own scale in world units — for an extrude, the half-diagonal of
   * the profile it stands on. Drives the arrowhead and the rung width, so the
   * instrument suits the part rather than the number.
   */
  radius: number;
  /**
   * Two unit directions across {@link dir}, the arms a graduation cross is
   * drawn on. For a sketch-plane gauge these are the plane's own `u` and `v`;
   * {@link crossArms} derives a pair for a track that has no natural basis.
   */
  arms: readonly [Vec3, Vec3];
}

/** Arrow-head length, as a fraction of the seat radius. */
export const ARROW_LENGTH_FRAC = 0.25;

/** Arrow-head radius, as a fraction of its own length. */
export const ARROW_RADIUS_FRAC = 0.42;

/** Shaft radius as a fraction of the arrowhead's — a stem, not a rod. */
export const SHAFT_RADIUS_FRAC = 0.16;

/**
 * Rung half-width as a fraction of the seat radius. The ladder is a rung ACROSS
 * the track, not a dot on it, so it reads at a glance without competing with
 * the ink beneath. Sized by SCREENSHOT, not by taste: at 0.06 the rungs
 * measured a couple of millimetres on a 66 mm profile and were invisible in the
 * founder capture — present in the buffer, absent from the picture, which is
 * the worst of both.
 */
export const LADDER_HALF_WIDTH_FRAC = 0.18;

/** Rung half-width floor, world units, so a hairline profile still gets a ladder. */
export const LADDER_MIN_HALF_WIDTH = 2;

/**
 * The arrow is sized from the SEAT, never from the value, so it holds still
 * while you drag — a manipulator that grows under the cursor reads as the model
 * moving. Clamped so a tiny profile still gets a grabbable arrow and a huge one
 * does not get a traffic cone.
 */
export function arrowLength(radius: number): number {
  return Math.min(18, Math.max(2, radius * ARROW_LENGTH_FRAC));
}

/** Half-width of one graduation arm, from the seat's own scale. */
export function rungHalfWidth(radius: number): number {
  return Math.max(LADDER_MIN_HALF_WIDTH, radius * LADDER_HALF_WIDTH_FRAC);
}

/** Two unit directions across `dir`, for a track with no natural in-plane basis. */
export function crossArms(dir: Vec3): readonly [Vec3, Vec3] {
  // Pick the world axis least aligned with `dir`, so the cross product is well
  // conditioned at every orientation.
  const [x, y, z] = [Math.abs(dir[0]), Math.abs(dir[1]), Math.abs(dir[2])];
  const seed: Vec3 =
    x <= y && x <= z ? [1, 0, 0] : y <= z ? [0, 1, 0] : [0, 0, 1];
  const u = normalize(cross(dir, seed));
  return [u, normalize(cross(dir, u))];
}

/** The graduation strokes for a straight track ruled at `stops`. */
function straightRungs(
  seat: GaugeSeat,
  stops: GaugeStops,
  unitsPerValue: number,
): readonly (readonly [Vec3, Vec3])[] {
  const half = rungHalfWidth(seat.radius);
  const [armU, armV] = seat.arms;
  const u = scale(normalize(armU), half);
  const v = scale(normalize(armV), half);
  const out: (readonly [Vec3, Vec3])[] = [];
  for (const at of stops.major) {
    const centre = addScaled(seat.base, seat.dir, at * unitsPerValue);
    out.push([sub(centre, u), add(centre, u)]);
    out.push([sub(centre, v), add(centre, v)]);
  }
  return out;
}

// --- THE TRACKS --------------------------------------------------------------

/** What a straight track needs beyond its seat. */
export interface LinearTrackOptions {
  /** Submittable range, in the value's own units. */
  min: number;
  max: number;
  /** Drag snap increment, value units. `0` disables snapping. */
  snap: number;
  /** One fine key press, value units. */
  keyStep: number;
  /** Coarse multiplier for Shift and the Page keys. */
  coarseFactor?: number;
  /** How close two values count as the same, for the ask-queue's recognition. */
  epsilon?: number;
  /** Display form. `unitSuffix: false` must give the bare number for the tag. */
  format(value: number, opts?: { unitSuffix?: boolean }): string;
  /**
   * World units per value unit. 1 for a length in scene millimetres; the
   * instance spacing for a {@link steppedTrack} counting copies.
   */
  unitsPerValue?: number;
  /** Rounding grid for a FREE (Ctrl) drag — reciprocal, so 1e4 is 1e-4 units. */
  precision?: number;
}

/**
 * A STRAIGHT gauge: a value that is a distance along a direction.
 *
 * This is the extrude depth gauge's own arithmetic. `extrudeHandle.ts` builds
 * one of these and keeps its published functions as thin delegates, so its
 * unit suite — untouched across the extraction — is the evidence this is a move
 * and not a rewrite.
 */
export function linearTrack(
  seat: GaugeSeat,
  options: LinearTrackOptions,
): GaugeTrack {
  const {
    min,
    max,
    snap,
    keyStep,
    coarseFactor = 10,
    epsilon = 1e-4,
    format,
    unitsPerValue = 1,
    precision = 1e4,
  } = options;
  const dir = normalize(seat.dir);
  const seated: GaugeSeat = { ...seat, dir };

  const clamp = (value: number): number => clampTo(value, min, max);

  return {
    pointAt: (value) => addScaled(seated.base, dir, value * unitsPerValue),
    valueAt: (rayOrigin, rayDirection) => {
      const along = axisValueAt(seated.base, dir, rayOrigin, rayDirection);
      return along === null ? null : along / unitsPerValue;
    },
    // `dxPx` is unused: with the track pointing at the eye there is no readable
    // screen direction, so UP GROWS is a convention rather than a derivation —
    // the one every 3D tool uses for a value the camera cannot show. The
    // readout at the tip means you are never guessing what you got.
    screenValueAt: (grabValue, _dxPx, dyPx, unitsPerPixel) =>
      screenValue(grabValue, dyPx, unitsPerPixel / unitsPerValue),
    stops: (value) => ladderStops(value),
    draw: (value, stops) => {
      const headLength = arrowLength(seated.radius);
      const tip = addScaled(seated.base, dir, value * unitsPerValue);
      return {
        spine: [seated.base, tip],
        spineRadius: headLength * ARROW_RADIUS_FRAC * SHAFT_RADIUS_FRAC,
        head: {
          base: tip,
          tip: addScaled(tip, dir, headLength),
          length: headLength,
          radius: headLength * ARROW_RADIUS_FRAC,
        },
        rungs: straightRungs(seated, stops, unitsPerValue),
      };
    },
    clamp,
    quantize: (value, free) => quantize(value, snap, free, min, max, precision),
    format,
    step: () => keyStep,
    coarseStep: () => keyStep * coarseFactor,
    nudge: (current, key, coarse) => {
      const intent = nudgeIntent(key, coarse);
      if (intent === null) return null;
      const grid = keyStep * Math.pow(coarseFactor, intent.grids);
      return steppedValue(current, grid, intent.sign, min, max);
    },
    same: (a, b) => Math.abs(a - b) <= epsilon,
  };
}

/** What a stepped (counting) track needs. */
export interface SteppedTrackOptions extends Omit<
  LinearTrackOptions,
  "snap" | "keyStep" | "coarseFactor" | "epsilon" | "format" | "precision"
> {
  /** World units between one count and the next. */
  pitch: number;
  /** Display form; defaults to the plain integer. */
  format?: (value: number, opts?: { unitSuffix?: boolean }) => string;
}

/**
 * A COUNTING gauge: {@link linearTrack} with an integer quantiser.
 *
 * Saying that is load-bearing rather than tidy — it means a pattern-count gauge
 * needs no new projection, only a new quantiser, so the drag that adds a copy
 * uses the same skew-line maths (and the same eye-on fallback) that a depth
 * drag does. Every integer is a stop, so there is no `Ctrl`-to-free: there is
 * no value between two counts to escape to.
 */
export function steppedTrack(
  seat: GaugeSeat,
  options: SteppedTrackOptions,
): GaugeTrack {
  const { pitch, min, max, format, unitsPerValue } = options;
  const line = linearTrack(seat, {
    min,
    max,
    snap: 1,
    keyStep: 1,
    coarseFactor: 10,
    epsilon: 1e-6,
    unitsPerValue: unitsPerValue ?? pitch,
    format: format ?? ((value) => String(Math.round(value))),
  });
  return {
    ...line,
    // Every integer in range is a stop, and the arrow crossing one is what
    // makes a copy appear — so the ladder IS the instance positions.
    stops: (value) => {
      const lo = Math.max(Math.ceil(min), 1);
      const hi = Math.min(Math.floor(max), Math.ceil(value));
      const major: number[] = [];
      for (let n = lo; n <= hi; n += 1) major.push(n);
      return { major, minor: [], pitch: 1 };
    },
    // No free drag: `free` is ignored, because there is nothing between counts.
    quantize: (value) => clampTo(Math.round(value), min, max),
  };
}

/** What an angular track needs beyond its seat. */
export interface AngularTrackOptions {
  /** Submittable range, DEGREES. */
  min: number;
  max: number;
  /** Radius the arc is drawn at, world units. */
  radius: number;
  /** Drag snap, degrees. */
  snap: number;
  /** One fine key press, degrees. */
  keyStep: number;
  /** Coarse multiplier for Shift and the Page keys. */
  coarseFactor?: number;
  /** How close two angles count as the same, degrees. */
  epsilon?: number;
  /** Display form. */
  format(value: number, opts?: { unitSuffix?: boolean }): string;
  /** Points per full turn when the arc is tessellated. */
  segmentsPerTurn?: number;
}

/**
 * A SWEPT gauge: a value that is an angle about an axis.
 *
 * The seat's `dir` is the AXIS OF ROTATION and `arms[0]` is the zero-degree
 * reference; the arc is drawn in the plane those two span, at `radius` from the
 * axis. The pointer is intersected with that plane and its angle about the axis
 * read off — the direct analogue of the straight track's skew-line projection,
 * and it refuses for the same reason (a plane nearly edge-on to the eye gives
 * an answer nobody can aim).
 *
 * THE ANGULAR SNAPS ARE NOT THE LINEAR LADDER ROTATED: 15° and 5° coarsening to
 * 30/45/90, because those are the angles a part is actually dimensioned in.
 *
 * NO CONSUMER YET — its first one (a revolve or draft gauge) should verify the
 * screen fallback's sign convention against a real camera before trusting it.
 */
export function angularTrack(
  seat: GaugeSeat,
  options: AngularTrackOptions,
): GaugeTrack {
  const {
    min,
    max,
    radius,
    snap,
    keyStep,
    coarseFactor = 3,
    epsilon = 1e-4,
    format,
    segmentsPerTurn = 96,
  } = options;
  const axis = normalize(seat.dir);
  // A right-handed frame on the sweep plane: `ref` is 0°, `perp` is +90°.
  const ref = normalize(seat.arms[0]);
  const perp = normalize(cross(axis, ref));
  const DEG = 180 / Math.PI;

  const at = (deg: number): Vec3 => {
    const r = deg / DEG;
    return add(
      seat.base,
      add(scale(ref, radius * Math.cos(r)), scale(perp, radius * Math.sin(r))),
    );
  };

  const clamp = (value: number): number => clampTo(value, min, max);

  return {
    pointAt: at,
    valueAt: (rayOrigin, rayDirection) => {
      const rd = normalize(rayDirection);
      const facing = dot(axis, rd);
      // Edge-on to the sweep plane: the intersection runs away to infinity
      // along the arc, which is arithmetically defined and useless to aim.
      if (Math.abs(facing) < AXIS_SHALLOW) return null;
      const t = dot(sub(seat.base, rayOrigin), axis) / facing;
      if (!Number.isFinite(t)) return null;
      const hit = sub(addScaled(rayOrigin, rd, t), seat.base);
      const deg = Math.atan2(dot(hit, perp), dot(hit, ref)) * DEG;
      return deg < 0 ? deg + 360 : deg;
    },
    // Tangential screen travel at the arc radius, converted to degrees: one
    // pixel of travel turns the sweep by the angle that pixel subtends at
    // `radius`. Horizontal travel is added to vertical so the gesture works
    // whichever way the arc happens to lie on screen.
    screenValueAt: (grabValue, dxPx, dyPx, unitsPerPixel) => {
      if (radius <= 0) return grabValue;
      return grabValue + ((dxPx + dyPx) * unitsPerPixel * DEG) / radius;
    },
    stops: (value, unitsPerPixel) => {
      // Coarsen until a major graduation is at least a legible arc apart on
      // screen. A ladder whose rungs land on the same pixel is crosshatch.
      const arcPx = (deg: number): number =>
        unitsPerPixel > 0 ? ((deg / DEG) * radius) / unitsPerPixel : Infinity;
      const majorStep = [15, 30, 45, 90].find((d) => arcPx(d) >= 14) ?? 90;
      const minorStep = majorStep === 15 ? 5 : majorStep / 3;
      const major: number[] = [];
      const minor: number[] = [];
      for (let d = majorStep; d < value - majorStep * 0.5; d += majorStep) {
        major.push(Math.round(d * 1e6) / 1e6);
      }
      for (let d = minorStep; d < value - minorStep * 0.5; d += minorStep) {
        const rounded = Math.round(d * 1e6) / 1e6;
        if (!major.includes(rounded)) minor.push(rounded);
      }
      return { major, minor, pitch: minorStep };
    },
    draw: (value, stops) => {
      const headLength = arrowLength(seat.radius);
      const steps = Math.max(
        2,
        Math.ceil((Math.abs(value) / 360) * segmentsPerTurn),
      );
      const spine: Vec3[] = [];
      for (let i = 0; i <= steps; i += 1) spine.push(at((value * i) / steps));
      const tip = at(value);
      // The head points along the tangent at the sweep's end.
      const tangent = normalize(sub(at(value + 0.5), at(value - 0.5)));
      const half = rungHalfWidth(seat.radius);
      const rungs: (readonly [Vec3, Vec3])[] = [];
      for (const deg of [...stops.major, ...stops.minor]) {
        const out = normalize(sub(at(deg), seat.base));
        const centre = at(deg);
        rungs.push([
          addScaled(centre, out, -half),
          addScaled(centre, out, half),
        ]);
        rungs.push([
          addScaled(centre, axis, -half),
          addScaled(centre, axis, half),
        ]);
      }
      return {
        spine,
        spineRadius: headLength * ARROW_RADIUS_FRAC * SHAFT_RADIUS_FRAC,
        head: {
          base: tip,
          tip: addScaled(tip, tangent, headLength),
          length: headLength,
          radius: headLength * ARROW_RADIUS_FRAC,
        },
        rungs,
      };
    },
    clamp,
    quantize: (value, free) => quantize(value, snap, free, min, max, 1e4),
    format,
    step: () => keyStep,
    coarseStep: () => keyStep * coarseFactor,
    nudge: (current, key, coarse) => {
      const intent = nudgeIntent(key, coarse);
      if (intent === null) return null;
      const grid = keyStep * Math.pow(coarseFactor, intent.grids);
      return steppedValue(current, grid, intent.sign, min, max);
    },
    same: (a, b) => Math.abs(a - b) <= epsilon,
  };
}

// --- WHERE THE TAG HANGS -----------------------------------------------------

/** Which quadrant of the grip the tag sits in. */
export type GaugeTagSide = "up-right" | "up-left" | "down-right" | "down-left";

/** The tag's own box, in CSS pixels. */
export interface GaugeTagSize {
  width: number;
  height: number;
}

/**
 * The placed tag, in pixels RELATIVE TO THE GRIP — which is the origin drei
 * `Html` already gives the tag's container, so the shell applies these numbers
 * directly and never has to know where the grip is on screen.
 */
export interface GaugeTagPlacement {
  /** The strip's top-left corner, relative to the grip. */
  tag: { left: number; top: number };
  /** The leader stub: the grip at (0, 0) → the strip's nearest corner. */
  leader: { x1: number; y1: number; x2: number; y2: number };
  /**
   * Which side the tag ended up on. Exposed because it is the only externally
   * checkable evidence that a flip happened at all — a placement test that only
   * asserts "inside the frame" passes just as well when the tag is clamped into
   * a corner on top of the grip.
   */
  side: GaugeTagSide;
}

/**
 * Place the gauge's tag beside its grip, flipping at the frame edge.
 *
 * SAME GEOMETRY RULE AS THE PROPOSAL NOTE (`placeProposal`,
 * `apps/web/src/viewport/sketchProposal.ts`) and deliberately not the same
 * function: that one works in FRAME coordinates against live chrome rects, this
 * one in GRIP-RELATIVE coordinates with no obstruction list, because an `Html`
 * container is already anchored at the point the leader starts from. What the
 * two must share is the RULE — offset diagonally, flip rather than clamp when
 * the default side would overflow, and run the leader to the tag corner NEAREST
 * the anchor so a flip drags the stub with it instead of leaving it pointing at
 * where the tag used to be — so it is stated in both places and each points at
 * the other. This is the same call `nudgeDepth` and `nudgePlacement` already
 * made: three lines of shared arithmetic is not an abstraction, the rule is.
 *
 * `anchor` and `frame` are optional. Without them the preferred side is simply
 * honoured: a gauge that cannot know where it is on screen still gets a
 * well-formed leader, rather than no tag at all.
 */
export function placeGaugeTag(
  prefer: GaugeTagSide,
  size: GaugeTagSize,
  opts: {
    /** The grip's position in frame coordinates, if known. */
    anchor?: { x: number; y: number };
    /** The viewport box, if known. */
    frame?: { width: number; height: number };
    /** Diagonal offset of the tag's near corner from the grip. */
    offset?: number;
    /** Keep-out from the frame edge. */
    margin?: number;
  } = {},
): GaugeTagPlacement {
  const {
    anchor,
    frame,
    offset = proposal.offset,
    margin = proposal.margin,
  } = opts;
  const [preferY, preferX] = prefer.split("-") as [
    "up" | "down",
    "right" | "left",
  ];

  let x: "right" | "left" = preferX;
  let y: "up" | "down" = preferY;
  if (anchor !== undefined && frame !== undefined) {
    if (
      x === "right" &&
      anchor.x + offset + size.width > frame.width - margin
    ) {
      x = "left";
    } else if (x === "left" && anchor.x - offset - size.width < margin) {
      x = "right";
    }
    if (y === "up" && anchor.y - offset - size.height < margin) {
      y = "down";
    } else if (
      y === "down" &&
      anchor.y + offset + size.height > frame.height - margin
    ) {
      y = "up";
    }
  }

  const left = x === "left" ? -offset - size.width : offset;
  const top = y === "up" ? -offset - size.height : offset;
  // The leader lands on the tag corner NEAREST the grip — the corner on the
  // grip's side in both axes.
  const x2 = x === "left" ? left + size.width : left;
  const y2 = y === "up" ? top + size.height : top;

  return {
    tag: { left, top },
    leader: { x1: 0, y1: 0, x2, y2 },
    side: `${y}-${x}` as GaugeTagSide,
  };
}
