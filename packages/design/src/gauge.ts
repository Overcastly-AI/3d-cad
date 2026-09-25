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
 * exercised only by the tests below. {@link angularTrack} HAS been checked
 * against a real camera — `revolve-gauge.spec.ts` drives it through one,
 * including the arc drag and the ray-intersection path, and `DraftGauge.tsx`,
 * `axisAnchorGauge.ts` and `gaugePose.ts` all consume it. (This note used to
 * say it "has no consumer at all yet" and asked its first one to do that
 * check; the check happened and the sentence did not, which is how a claim
 * about the product goes stale silently.) A correction it needs is still a
 * correction to this file, not a reason to write a fourth projection
 * somewhere else.
 */
import { proposal } from "./tokens";
import {
  add,
  addScaled,
  cross,
  dot,
  scale,
  sub,
  unit,
  type Vec3,
} from "./vec3";

// The tuple arithmetic this module runs on used to live here, as forty private
// lines arguing that a shared micro-vector library would be premature. It is
// now `./vec3`, because the four copies of those forty lines had diverged in
// the one function with a decision in it — see that module's note for the
// measured table. The surface of THIS module is still tracks and stops, not a
// vector library: the helpers are imported, not re-exported.
export type { Vec3 };

/**
 * Where this module lands when a caller hands it a direction that is not one.
 *
 * {@link unit} refuses below `VEC3_UNIT_FLOOR` and returns `null`, which is the
 * right answer and which {@link GaugeTrack}'s signature cannot carry: a track
 * is built or it is not, and every consumer of {@link linearTrack} /
 * {@link angularTrack} would have to learn a new failure mode to say so.
 *
 * So a seat with no direction collapses to a point — `pointAt` returns the base
 * for every value, and there is visibly nothing to grab. That is the behaviour
 * this file already shipped (its old `normalize` returned `[0,0,0]` unchanged
 * for a zero input), and it is kept DELIBERATELY over the alternative of
 * substituting some world axis: a dead instrument is a bug you can see, whereas
 * a gauge that silently runs along an axis nobody chose is a control that moves
 * the model the wrong way. Refuse visibly; never invent a direction.
 */
const NO_DIRECTION: Vec3 = [0, 0, 0];

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
  /**
   * Spacing of the MAJOR graduations, in track units. 0 when none.
   *
   * Carried rather than re-derived because the two are not always a decade
   * apart: when no round number falls inside the span the minors are PROMOTED,
   * and the drawn majors are then a `pitch` apart. A consumer that recomputed
   * `10^(floor(log10(pitch))+1)` would size those marks against a spacing they
   * do not have.
   *
   * It exists because a rung's ARMS are bounded by the gap they sit in
   * (`rungHalfWidth`), and until CRAFT-7's review both classes were bounded by
   * the PITCH. That was invisible while the pitch floor was 14 px and every
   * ladder was coarse; at a 2 mm pitch it put a 0.8 mm arm on a 0.97 mm rod and
   * the ladder VANISHED INTO ITS OWN SHAFT — measured on the founder shot, 5
   * legible crosses before, 0 after. Majors are `majorStep` apart, so bounding
   * them by the pitch was always the wrong gap; it is the ruler's own rule,
   * long marks for the numbers, short ones between.
   */
  majorStep: number;
}

/** No graduations — the rest state, and what a track with nothing to rule returns. */
export const NO_STOPS: GaugeStops = {
  major: [],
  minor: [],
  pitch: 0,
  majorStep: 0,
};

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
   * MAJOR graduation strokes, as pairs of world points. A graduation is a CROSS
   * (two strokes) rather than a single rung: a rung lies along one in-plane
   * axis, so from a three-quarter view it projects as a skewed dash that reads
   * as debris rather than a scale. Two arms always project to something centred
   * on the spine, from any camera.
   */
  rungs: readonly (readonly [Vec3, Vec3])[];
  /**
   * MINOR graduation strokes, drawn shorter and fainter than {@link rungs}.
   *
   * A separate field rather than a flag on each stroke because the shell draws
   * them as two line layers with two opacities — one `Segments` per weight is
   * one draw call per weight, and a per-stroke weight would need a vertex
   * attribute and a custom material to express. It is the drafting convention:
   * without it a ladder is nine identical crosses and none of them says which
   * one is the round number.
   */
  minorRungs: readonly (readonly [Vec3, Vec3])[];
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
  /**
   * Quantise a DRAGGED value: snapped unless `free` (Ctrl/Cmd), then clamped.
   *
   * `stops` is the ladder currently on screen, because **the drawn rungs ARE
   * the stops** (§3.1). Passing it is what unifies the scale you can see with
   * the one the drag obeys; omit it and the track falls back to its own
   * configured snap, which is the honest answer when no ladder is drawn.
   */
  quantize(value: number, free: boolean, stops?: GaugeStops): number;
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

// --- THE ASK QUEUE -----------------------------------------------------------

/**
 * THE OPTIMISTIC ASK QUEUE — what a gauge has asked its owner for and not yet
 * seen come back.
 *
 * ## Why it exists
 *
 * A gauge never owns its value: it asks, the owner's form takes the number, and
 * the new prop arrives several renders later. So a SECOND input landing inside
 * that window would compute from the stale prop and overwrite the first — two
 * quick taps of Up giving 10.5 rather than 11, intermittently. The first fix
 * held ONE pending value and dropped it whenever the prop changed, which throws
 * away press two on the acknowledgement of press one: **13 of 20 fast
 * `Up, Up, Shift+Up` sequences came back wrong.**
 *
 * The queue is the fix, and its correctness is invisible to a normal run —
 * every rule below matters only when two inputs overlap one round trip, which
 * is precisely the case nobody exercises by hand.
 *
 * ## Why it is HERE, as plain functions over plain data
 *
 * It used to live inside `<ParametricGauge>` as three `useRef`s mutated in four
 * places, and the only thing standing behind it was one Playwright case that
 * hammers the keyboard. That case is a real positive control and it is a WEAK
 * one — re-running it twelve times against a mutant that clears the queue on
 * every prop change caught the mutant **2 times in 12**, because the lost
 * update it detects requires two inputs to collide inside one round trip and
 * usually they do not collide. A guard that fires one run in six is green as
 * its modal outcome, so "it went red once" and "it is load-bearing" are not the
 * same sentence.
 *
 * As five pure transitions the same rules are checkable EVERY run, in
 * microseconds, with the collision constructed rather than raced for. The
 * browser case stays — it is the only thing that proves the rules are wired to
 * a real keyboard — but it is no longer the only thing.
 *
 * ## The rules, which are the whole specification
 *
 *  1. {@link recordAsk} — an ask is remembered BEFORE it is sent, so the next
 *     input reasons from it even if no render has happened in between. ALSO
 *     while the pointer is authoring (see "A drag's asks are asks" below); an
 *     ask equal to the newest outstanding one is not queued twice, because the
 *     owner will only ever answer it once.
 *  2. {@link acknowledgeAsk}, match — an arriving value equal (to the track's
 *     own tolerance) to an outstanding ask retires that ask AND EVERY OLDER
 *     ONE, and leaves `base` alone, because a later ask has already superseded
 *     it.
 *  3. {@link acknowledgeAsk}, no match — an arriving value we never asked for
 *     is somebody else's edit (a typed distance, a re-seeded editor, a clamp)
 *     and wins outright: the queue is abandoned and it becomes the new `base`.
 *     Mid-drag the queue is still abandoned, but `base` and `live` stay on the
 *     pointer — the hand is the author until it lets go.
 *  4. {@link holdAsks} — taking the grip shows `base`, not the prop, so a grab
 *     straight after a key press does not jump back a step.
 *  5. {@link releaseAsks} — letting go is not an answer: the drag's unanswered
 *     asks stay outstanding and the newest is drawn until the owner speaks.
 *     With nothing outstanding the prop is the truth again.
 *
 * ## A drag's asks are asks (measured 2026-09-23)
 *
 * The drag used to ask WITHOUT queueing, on the theory that a release would
 * abandon the queue anyway. Once a release stopped abandoning it (the drag's
 * final ask stays outstanding, see `useAskQueue`), that left the queue holding
 * ONE value — the last — while the owner's pipeline was still carrying the
 * two or three before it. The owner answers in ask order, so the answer to a
 * SUPERSEDED drag ask routinely landed after the pointer came up, matched
 * nothing, and was read by rule 3 as the owner overriding the release: the rod
 * stepped back one notch for as long as the next answer took. Measured in the
 * browser: `ask 26 · release · prop 25 (asks=26) · prop 26`, the rod reading 25
 * against a field of 26 on 2-4 frames, on 3 of 12 runs.
 *
 * The owner echoes a bare NUMBER, so the only identity an answer carries is
 * its value and its ORDER. Queueing every drag ask supplies the order: an echo
 * that matches an older entry is recognisably the answer to a superseded ask
 * (rule 2 trims, `live` stays on the newest), and an echo that matches no
 * entry is still the owner speaking (rule 3 wins). A clamp that answers
 * several asks with one echo therefore still wins, because a clamp answers
 * with a value outside the asks it is answering.
 *
 * It also closes a hole the unqueued version had: a clamp whose one echo
 * landed MID-drag (when it cannot move the rod) and never came again (the
 * owner's value does not change) used to leave the rod on the drag's last ask
 * for good. Now that echo abandons the queue, so a release with nothing asked
 * since hands the instrument straight to the owner.
 *
 * What a value-only echo CANNOT tell apart, stated so nobody believes it can:
 * a clamp whose value happens to equal an OLDER outstanding ask (a drag that
 * passed through 30 on its way to 34, against an owner max of 30) reads as the
 * late answer to that older ask, and the rod stays on 34 until the owner next
 * speaks. So does a clamp that answers asks made AFTER its echo, since that
 * value never arrives twice. Resolving either needs the owner to echo WHICH ask
 * it is answering, not just a number. No owner in this codebase clamps today.
 */
export interface AskQueue {
  /** Outstanding asks, oldest first. */
  readonly asks: readonly number[];
  /** What the next input reasons from — the last ASK, not the last prop. */
  readonly base: number;
  /** The newest outstanding ask, drawn and announced in place of the prop. */
  readonly live: number | null;
}

/** A queue with nothing outstanding, seated on the owner's current value. */
export function seedAsks(value: number): AskQueue {
  return { asks: [], base: value, live: null };
}

/**
 * Rule 1 — ask the owner for `next`.
 *
 * Queued whether or not the pointer is authoring: the owner answers a drag's
 * asks in order, and only a queue that holds them can tell the late answer to
 * a superseded ask from the owner overriding the release (see the rules). An
 * ask equal to the newest outstanding one is not queued again — the owner's
 * value does not change, so it will answer the pair once, and a duplicate
 * would sit outstanding for ever.
 */
export function recordAsk(queue: AskQueue, next: number): AskQueue {
  return {
    asks: queue.asks.at(-1) === next ? queue.asks : [...queue.asks, next],
    base: next,
    live: next,
  };
}

/**
 * Rules 2 and 3 — the owner has spoken.
 *
 * @param same The track's own tolerance. It cannot be an exact comparison: the
 *   value passes through a form field as a DISPLAY STRING, so on an inch
 *   document the round trip is lossy and equality would read every
 *   acknowledgement as a stranger's edit.
 * @param authoring True while the pointer holds the grip. The owner's answers
 *   still retire the asks they answer — that is what keeps the queue down to
 *   the few asks actually in flight — but `base` and `live` stay on the
 *   pointer, which is the author until it lets go.
 */
export function acknowledgeAsk(
  queue: AskQueue,
  value: number,
  same: (a: number, b: number) => boolean,
  authoring = false,
): AskQueue {
  const at = queue.asks.findIndex((asked) => same(asked, value));
  const asks = at < 0 ? [] : queue.asks.slice(at + 1);
  if (authoring) return { asks, base: queue.base, live: queue.live };
  if (at < 0) return { asks, base: value, live: null };
  return { asks, base: queue.base, live: asks.at(-1) ?? null };
}

/** Rule 4 — the grip has been taken: show what the next step reasons from. */
export function holdAsks(queue: AskQueue): AskQueue {
  return { asks: queue.asks, base: queue.base, live: queue.base };
}

/**
 * Rule 5 — the pointer is done authoring. Letting go is not an answer: what the
 * drag asked and the owner has not answered stays outstanding, and the newest
 * of it is drawn. `base` keeps the value the drag ended on either way, so the
 * first arrow press afterwards steps off what you dragged to.
 */
export function releaseAsks(queue: AskQueue): AskQueue {
  return {
    asks: queue.asks,
    base: queue.base,
    live: queue.asks.at(-1) ?? null,
  };
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
  // A ray with no direction points nowhere, so the pointer is not on the track.
  // Null is already this function's word for that; the old `normalize` returned
  // `[0,0,0]` here and went on to compute a confident NUMBER from it.
  const rd = unit(rayDirection);
  if (rd === null) return null;
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

/**
 * Most graduations a ladder is allowed to show before CRAFT-7's screen floor
 * existed — kept as the no-camera default and as the shape of the old ladder.
 *
 * It cannot be the cap any more. A total cap and a zoom-aware ladder are
 * incompatible: a 40 mm span can never carry twelve-or-fewer 1 mm rungs, so the
 * pitch would be pinned at `span / 12` at every magnification and "zoom in and
 * it subdivides" — the whole of §3.2 — could not happen. The screen floor does
 * the legibility work now, and {@link MAX_RUNGS} is the draw's own sanity bound.
 */
export const LADDER_MAX = 12;

/**
 * The hard ceiling on drawn graduations, whatever the camera says.
 *
 * The screen floor already stops a ladder becoming crosshatch; this stops a
 * very close camera on a very long feature turning the shaft into a hairbrush,
 * and it bounds the vertex buffer. A rule with eighty marks on it is a rule.
 */
export const MAX_RUNGS = 80;

/**
 * The smallest on-screen spacing a MAJOR graduation may have, CSS pixels.
 *
 * 14 is the repo's own dense-target half (`target.dense = 24`) and, measured in
 * the W3 captures, the smallest pitch at which two crosses read as two marks
 * rather than as crosshatch. A major is the mark a VALUE IS READ OFF — it lands
 * on a round number and it is what the eye anchors to — so this is the floor
 * for "legible as a separate, identifiable mark".
 */
export const LADDER_MIN_MAJOR_PX = 14;

/**
 * The smallest on-screen spacing the PITCH may have, CSS pixels.
 *
 * ## WHY THIS IS NOT 14 (CRAFT-7 review)
 *
 * 14 was the right number on the wrong member of the series. `majorStep` is the
 * decade above the pitch, so majors sit 2x, 5x or 10x the pitch apart — and a
 * value is read off a MAJOR, while the pitch is a COUNTING interval, a mark you
 * pass rather than one you name. Those want different floors. In the worst case
 * (pitch 5 -> major 10, the only ratio-2 member) a 7 px pitch floor yields
 * exactly a 14 px major floor, so the direction's own number survives one level
 * up and nothing a number is read off has moved closer together.
 *
 * Derived rather than borrowed, all measured on this app:
 *
 *  · a rung's ink footprint along the track is 1.0-1.3 px, and two 1 px lines
 *    resolve down to about 3-4 px;
 *  · `SketchScene` ships `cellSize = 1` mm, which at the default sketch camera
 *    is 6.88 px, and the sketcher calls that a readable grid — a graduation
 *    floor at twice the grid we draw under the cursor is not defensible;
 *  · a 1 mm ruler graduation is 3.78 px at 96 dpi, and people read rulers.
 *
 * What this buys is the REACHABLE VALUE SET, which is what the old constant
 * cost. It was never aimability: the pre-CRAFT-7 `SNAP_MM = 0.5` was 1.83 px of
 * pointer travel per stop at the default camera, below aiming resolution — that
 * was rounding, not a detent, and nobody could land on a chosen 0.5. Aimability
 * went UP tenfold at 14 px. But a 5 mm ladder on a 40 mm depth cannot reach
 * 12.5 by drag at all; at 7 px the same camera rules 2 mm and most of the set
 * comes back.
 */
export const LADDER_MIN_PITCH_PX = 7;

/**
 * Fewer rungs than this and there is no ladder at all.
 *
 * Two marks are not a scale — they are two marks, and drawing them costs the
 * instrument its meaning while adding ink. The gauge falls back to a plain
 * arrow, which is an honest statement that there is nothing to rule against at
 * this zoom.
 */
export const LADDER_MIN_RUNGS = 3;

/**
 * The `k`-th member of the 1/2/5 decade series; `k = 0` is 1, and `k` may be
 * negative. One function rather than a literal array because the ladder now
 * walks the series in BOTH directions and past any fixed decade — up for the
 * major step at a distant camera, down for the minor one at a close one.
 */
function seriesStep(k: number): number {
  const decade = Math.pow(10, Math.floor(k / 3));
  return decade * ([1, 2, 5][((k % 3) + 3) % 3] as number);
}

/**
 * The MAJOR step for a given pitch: the decade above it.
 *
 * So a major always lands on a round number and the minors between two majors
 * number 2, 5 or 10 — the drafting grouping, and the answer to "which of these
 * identical crosses matters". Because the pitch is a 1/2/5 member, its decade
 * is always a whole multiple of it, so no ladder can draw a major and a minor a
 * hair apart and a subdivision never moves a mark the user was already reading.
 */
function majorFor(pitch: number): number {
  return Math.pow(10, Math.floor(Math.log10(pitch)) + 1);
}

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
 *
 * ## THE RUNGS ARE THE STOPS (CRAFT-7, direction §3.1)
 *
 * They were two different ladders until this item. The rungs came from the
 * decade series below; the drag snapped to a CONSTANT (`SNAP_MM = {mm: 0.5}`),
 * so at the default 10 mm extrude the user saw rungs 1 mm apart while the drag
 * stopped every 0.5 mm. **The scale you could see had nothing to do with what
 * the drag did** — the decorative-chrome defect (mandate 3c) in the one element
 * the roadmap calls the signature. `pitch` is now what a dragged value snaps
 * to, so the instrument tells you what the snap will do BEFORE you drag.
 *
 * ## Why a SCREEN floor, and what it buys
 *
 * `pxPerValue` — screen pixels per one unit of VALUE — keeps every graduation
 * at least {@link LADDER_MIN_PITCH_PX} apart and every MAJOR at least
 * {@link LADDER_MIN_MAJOR_PX} apart, and it is what makes the snap zoom-aware:
 * **zoom in and the ladder subdivides, 5 -> 2 -> 1 -> 0.5, and the drag gets
 * finer with it; zoom out and it coarsens.** That is Fusion's and Plasticity's
 * behaviour, and it is why their drags feel precise without a settings panel —
 * precision is a function of how closely you are looking.
 *
 * The caller owes an HONEST `pxPerValue`: the pixels and the units must
 * describe ONE segment of the drawn track. A shell that divides a shaft's
 * world length by a seat-to-ARROWHEAD-TIP projection inflates it, and the floor
 * then clears at a pitch nobody chose — see `projectedSpineLength` in the web
 * app, which is where that was measured and fixed.
 *
 * It defaults to `Infinity` — no floor — so a caller that cannot measure the
 * camera gets a purely value-driven ladder rather than none at all.
 *
 * ## Major and minor, and where the count ceiling now bites
 *
 * {@link LADDER_MAX} is no longer the cap when a camera is known — it could not
 * be. A total cap and a zoom-aware ladder are incompatible: a 40 mm span can
 * never carry twelve-or-fewer 1 mm rungs however close the camera is, so the
 * pitch would be frozen at `span / 12` at every magnification and the screen
 * floor could only ever coarsen it. {@link MAX_RUNGS} bounds the draw instead,
 * so a 40 mm depth is ruled every 5 mm at arm's length and every 1 mm when you
 * lean in — the same instrument at two magnifications, which is what a rule is.
 *
 * MAJORS FALL OUT OF THE PITCH rather than being chosen separately: a rung on
 * the decade ABOVE the pitch is major, the rest are minor. Because the pitch is
 * a 1/2/5 member, its decade is always a whole multiple of it, so the majors
 * land on round numbers and the minors nest inside them — no ladder can ever
 * draw a major and a minor a hair apart, and a subdivision never moves a mark
 * the user was already reading.
 */
export function ladderStops(span: number, pxPerValue = Infinity): GaugeStops {
  if (!(span > 0)) return NO_STOPS;

  // THE PITCH — the finest drawn graduation, and therefore the snap.
  //
  // ONE walk, not two. The finest member of the 1/2/5 series that the screen
  // can carry and the draw can afford; the majors then fall out of it, because
  // a decade multiple of a 1/2/5 step is always a member of the same lattice.
  // Choosing the major first and subdividing it afterwards — which this did for
  // one draft — cannot reach the finer half of the series at all: a 40 mm span
  // takes a 5 mm major, 2 does not divide 5, and the ladder is then pinned at
  // 5 mm however close the camera gets.
  //
  // A caller with NO camera information keeps the OLD, conservative count
  // ceiling: `Infinity` means "no floor", and running the fine end of the
  // series with no floor would draw eighty graduations on faith — a ladder it
  // has no evidence anyone can see, which is the decorative-chrome defect this
  // item exists to remove.
  const cap = Number.isFinite(pxPerValue) ? MAX_RUNGS : LADDER_MAX;
  const from = 3 * Math.floor(Math.log10(span / cap));
  let pitch = 0;
  for (let i = 0; i < 90; i += 1) {
    const step = seriesStep(from + i);
    // TWO FLOORS, because the series carries two kinds of mark. A candidate
    // must be countable at the pitch AND readable at the decade above it, which
    // is where the numbers land. The pitch floor binds in every case today —
    // the tightest ratio in the 1/2/5 series is 2, and 7 x 2 is 14 — so the
    // second test is the INVARIANT stated where `majorStep` is chosen, not a
    // second lever: change how majors are derived and it starts holding the
    // line on its own.
    if (
      span / step <= cap &&
      step * pxPerValue >= LADDER_MIN_PITCH_PX &&
      majorFor(step) * pxPerValue >= LADDER_MIN_MAJOR_PX
    ) {
      pitch = step;
      break;
    }
  }
  if (pitch <= 0) return NO_STOPS;

  const majorStep = majorFor(pitch);
  const major: number[] = [];
  const minor: number[] = [];
  // Excludes the seat (the plane draws itself) and the half-pitch under the
  // arrowhead's base. Every rung inside the band is a stop and every stop is
  // drawn, which is the property that makes the ladder honest.
  for (let at = pitch; at < span - pitch * 0.5; at += pitch) {
    const rounded = Math.round(at * 1e6) / 1e6;
    const count = rounded / majorStep;
    const onMajor = Math.abs(count - Math.round(count)) < 1e-9;
    (onMajor ? major : minor).push(rounded);
  }
  // Two marks are not a scale. Refuse rather than draw a ladder that cannot be
  // read — the arrow alone is the honest form at this zoom.
  if (major.length + minor.length < LADDER_MIN_RUNGS) return NO_STOPS;
  // A span too short to contain a round number — a 5 mm extrude ruled at 1 mm
  // reaches 4 and no major is in range. There is then nothing to distinguish,
  // and a ladder drawn ENTIRELY in the minor weight is four faint stubs, i.e.
  // strictly worse than an unweighted one. Promote.
  if (major.length === 0)
    return { major: minor, minor: [], pitch, majorStep: pitch };
  return { major, minor, pitch, majorStep };
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
 * Rung half-width as a fraction of the ladder's own pitch — the ceiling that
 * keeps width/pitch at 0.8 or below, so two graduations always read as two.
 */
export const LADDER_PITCH_HALF_WIDTH_FRAC = 0.4;

/**
 * The head may never be more than this fraction of the shaft it terminates.
 *
 * MEASURED before the clamp existed: a 66 mm-radius profile extruded 5 mm drew
 * a 16.5 mm head on a 5 mm shaft — a cone on a stub, and the arrow no longer
 * read as an arrow at all. The two lengths came from two unrelated quantities
 * (the seat's radius and the value), which is the whole defect; bounding one by
 * the other is the fix.
 */
export const ARROW_SHAFT_FRAC = 0.45;

/**
 * The arrow is sized from the SEAT, never from the value, so it holds still
 * while you drag — a manipulator that grows under the cursor reads as the model
 * moving. Clamped so a tiny profile still gets a grabbable arrow and a huge one
 * does not get a traffic cone.
 *
 * `shaft` BOUNDS it (CRAFT-7, direction §2.2). The size still comes from the
 * seat — the arrow does not grow as you drag — but it may not exceed
 * {@link ARROW_SHAFT_FRAC} of the drawn shaft, so the instrument always reads
 * as *a rod with a point on it* rather than *a cone on a stub*. Omitted, there
 * is no bound, which is the old behaviour and is what the delegating callers in
 * `extrudeHandle.ts` still describe.
 */
export function arrowLength(radius: number, shaft = Infinity): number {
  const fromSeat = Math.min(18, Math.max(2, radius * ARROW_LENGTH_FRAC));
  // The shaft bound WINS over the 2 mm floor, deliberately: the floor exists so
  // a hairline PROFILE still gets a grabbable arrow, and a 0.1 mm extrude is
  // not that case — there the arrow would be four hundred per cent of the thing
  // it terminates. The DOM grip is 24 px at every size, so nothing becomes
  // ungrabbable when the drawn head gets small.
  return Math.min(fromSeat, Math.max(0, shaft) * ARROW_SHAFT_FRAC);
}

/**
 * Half-width of one graduation arm, from the seat's own scale — bounded by the
 * ladder's own PITCH (CRAFT-7, direction §2.2).
 *
 * The same two-scales defect as the arrowhead, in the other direction. The
 * width came from the seat's radius and the spacing from the value, so a wide
 * profile ruled at a fine pitch drew crosses wider than the gap between them:
 * measured 9 mm arms at a 5 mm pitch, a ratio of 1.8, which reads as a woven
 * band rather than as graduations. Bounding the width by 0.4 x pitch puts
 * width/pitch at 0.8 or below at every depth on every profile.
 *
 * The {@link LADDER_MIN_HALF_WIDTH} floor applies to the SEAT term only, for
 * the same reason as above: it is there so a hairline profile still gets a
 * visible rung, not so a fine pitch gets an illegible one.
 */
export function rungHalfWidth(radius: number, pitch = Infinity): number {
  return Math.min(
    Math.max(LADDER_MIN_HALF_WIDTH, radius * LADDER_HALF_WIDTH_FRAC),
    Math.max(0, pitch) * LADDER_PITCH_HALF_WIDTH_FRAC,
  );
}

/** The arms used when a direction is too degenerate to derive a pair from. */
const WORLD_ARMS: readonly [Vec3, Vec3] = [
  [1, 0, 0],
  [0, 1, 0],
];

/** Two unit directions across `dir`, for a track with no natural in-plane basis. */
export function crossArms(dir: Vec3): readonly [Vec3, Vec3] {
  // Pick the world axis least aligned with `dir`, so the cross product is well
  // conditioned at every orientation.
  const [x, y, z] = [Math.abs(dir[0]), Math.abs(dir[1]), Math.abs(dir[2])];
  const seed: Vec3 =
    x <= y && x <= z ? [1, 0, 0] : y <= z ? [0, 1, 0] : [0, 0, 1];
  // `dir` is least aligned with `seed`, so both crosses are well conditioned
  // and neither `??` branch is reachable from a real seat. They are not a
  // formality: the OLD code returned `[[0,0,0],[0,0,0]]` for a degenerate
  // `dir`, and arms of zero length draw a ladder of zero-length crosses — a
  // ruler with no graduations, which is exactly the CRAFT-7 defect the
  // screenshot gate caught and no unit assertion can see. A real orthonormal
  // pair keeps the ladder legible even when the seat is nonsense.
  const u = unit(cross(dir, seed)) ?? WORLD_ARMS[0];
  return [u, unit(cross(dir, u)) ?? WORLD_ARMS[1]];
}

/**
 * The graduation strokes for a straight track ruled at `at`.
 *
 * `widthFrac` is what separates a minor from a major: 0.6, the drafting
 * convention, applied to the length rather than only to the opacity so the
 * distinction survives on a bright face where every hairline reads the same.
 */
function straightRungs(
  seat: GaugeSeat,
  at: readonly number[],
  pitch: number,
  unitsPerValue: number,
  widthFrac = 1,
): readonly (readonly [Vec3, Vec3])[] {
  const half = rungHalfWidth(seat.radius, pitch) * widthFrac;
  const [armU, armV] = seat.arms;
  // `GaugeSeat.arms` is contracted to be a unit pair, so these normalisations
  // are defensive. A degenerate arm draws no rung in that direction — the same
  // outcome the old code reached by scaling a zero vector, now said out loud.
  const u = scale(unit(armU) ?? NO_DIRECTION, half);
  const v = scale(unit(armV) ?? NO_DIRECTION, half);
  const out: (readonly [Vec3, Vec3])[] = [];
  for (const value of at) {
    const centre = addScaled(seat.base, seat.dir, value * unitsPerValue);
    out.push([sub(centre, u), add(centre, u)]);
    out.push([sub(centre, v), add(centre, v)]);
  }
  return out;
}

/**
 * Minor graduations are drawn at this fraction of a major's length.
 *
 * ## 1, NOT 0.6, SINCE CRAFT-7's REVIEW — and the constant survives as the
 * statement that the contrast is now STRUCTURAL rather than a multiplier.
 *
 * Each class is bounded by its own spacing (`GaugeStops.majorStep`), so a major
 * is already 2x to 10x a minor's length before anything is scaled: at the
 * default camera on a 40 mm depth that is an 8 mm cross against a 1.6 mm one.
 * Multiplying the minor by 0.6 ON TOP of that was double-counting a difference
 * the geometry already states — and it was the half of the CRAFT-7 regression
 * that survived the `majorStep` fix. MEASURED on the founder capture: a 0.48 mm
 * minor arm on a rod of 0.484 mm radius is a mark drawn INSIDE the thing it is
 * meant to graduate, so the drawn scale read 10 mm while the drag snapped every
 * 2 mm — "the rungs ARE the stops" (direction §3.1) broken by a factor of five,
 * in the one element the roadmap calls the signature.
 *
 * The weights still differ, and by more than they did: length from the spacing,
 * and ink from `manipulator.ladderMinorOpacity` (0.5) against
 * `ladderMajorOpacity` (0.85).
 */
export const MINOR_RUNG_FRAC = 1;

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
  const dir = unit(seat.dir) ?? NO_DIRECTION;
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
    // `unitsPerPixel` is WORLD units per pixel; the ladder is chosen in VALUE
    // units, so the conversion carries `unitsPerValue` — the two differ for a
    // counting track and agree for a length.
    stops: (value, unitsPerPixel) =>
      ladderStops(
        value,
        unitsPerPixel > 0 ? unitsPerValue / unitsPerPixel : Infinity,
      ),
    draw: (value, stops) => {
      const headLength = arrowLength(seated.radius, value * unitsPerValue);
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
        // TWO THINGS HAPPEN HERE, both about units.
        //
        // (1) A spacing arrives in VALUE units and the width is a WORLD length,
        // so the conversion belongs here — for a counting track one count is
        // `unitsPerValue` millimetres apart, and a width bounded by the raw
        // count would be the unit confusion this clamp exists to remove.
        //
        // (2) EACH CLASS IS BOUNDED BY ITS OWN SPACING. A major sits
        // `majorStep` from its neighbour, so that is the gap its arms must not
        // exceed; bounding it by the PITCH shrank it with every subdivision
        // until the rod swallowed it. `majorStep` falls back to the pitch when
        // the ladder was promoted, which is exactly when the two coincide.
        rungs: straightRungs(
          seated,
          stops.major,
          (stops.majorStep > 0 ? stops.majorStep : stops.pitch) * unitsPerValue,
          unitsPerValue,
        ),
        minorRungs: straightRungs(
          seated,
          stops.minor,
          stops.pitch * unitsPerValue,
          unitsPerValue,
          MINOR_RUNG_FRAC,
        ),
      };
    },
    clamp,
    // THE DRAWN RUNGS ARE THE STOPS. `stops.pitch` when there is a ladder, the
    // configured `snap` when there is not — which is the rest state (no ladder
    // is built until the grip is addressed) and the degenerate zoom where fewer
    // than three rungs fit. A drag always arms the ladder first, so the value a
    // pointer produces is always a rung the user can see.
    quantize: (value, free, stops) =>
      quantize(
        value,
        stops !== undefined && stops.pitch > 0 ? stops.pitch : snap,
        free,
        min,
        max,
        precision,
      ),
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
      return { major, minor: [], pitch: 1, majorStep: 1 };
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
  const axis = unit(seat.dir) ?? NO_DIRECTION;
  // A right-handed frame on the sweep plane: `ref` is 0°, `perp` is +90°.
  const ref = unit(seat.arms[0]) ?? NO_DIRECTION;
  const perp = unit(cross(axis, ref)) ?? NO_DIRECTION;
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
      const rd = unit(rayDirection);
      if (rd === null) return null;
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
      // Majors carry the numbers, so they take the MAJOR floor; the minors
      // below take the pitch floor. Same split as `ladderStops`, and the same
      // reason — a mark you count past needs less room than one you read.
      const majorStep =
        [15, 30, 45, 90].find((d) => arcPx(d) >= LADDER_MIN_MAJOR_PX) ?? 90;
      // The MINOR pitch must clear the screen floor too, or the snap lands on a
      // rung nobody can see — the same defect in the smaller half.
      const minorStep =
        arcPx(majorStep === 15 ? 5 : majorStep / 3) >= LADDER_MIN_PITCH_PX
          ? majorStep === 15
            ? 5
            : majorStep / 3
          : majorStep;
      const major: number[] = [];
      const minor: number[] = [];
      for (let d = majorStep; d < value - majorStep * 0.5; d += majorStep) {
        major.push(Math.round(d * 1e6) / 1e6);
      }
      for (let d = minorStep; d < value - minorStep * 0.5; d += minorStep) {
        const rounded = Math.round(d * 1e6) / 1e6;
        if (!major.includes(rounded)) minor.push(rounded);
      }
      if (major.length + minor.length < LADDER_MIN_RUNGS) return NO_STOPS;
      return { major, minor, pitch: minorStep, majorStep };
    },
    draw: (value, stops) => {
      // Bounded by the ARC it terminates, not by the angle: the shaft's drawn
      // length is `radius * angle`, and that is the quantity the head must stay
      // a fraction of. An arrowhead sized against a NUMBER OF DEGREES would be
      // a third unrelated scale, which is the defect §2.2 exists to end.
      const headLength = arrowLength(
        seat.radius,
        (Math.abs(value) / DEG) * radius,
      );
      const steps = Math.max(
        2,
        Math.ceil((Math.abs(value) / 360) * segmentsPerTurn),
      );
      const spine: Vec3[] = [];
      for (let i = 0; i <= steps; i += 1) spine.push(at((value * i) / steps));
      const tip = at(value);
      // The head points along the tangent at the sweep's end.
      // The chord across 1° at `radius`, so it degenerates only on a gauge with
      // no radius at all — which `screenValueAt` already guards as `radius<=0`.
      const tangent =
        unit(sub(at(value + 0.5), at(value - 0.5))) ?? NO_DIRECTION;
      // One half-width per CLASS, for the reason `GaugeStops.majorStep`
      // documents: arms are bounded by the gap they sit in, and a major's gap
      // is `majorStep`, not `pitch`.
      const armFor = (step: number): number =>
        rungHalfWidth(seat.radius, (step / DEG) * radius);
      const cross = (
        degrees: readonly number[],
        step: number,
        widthFrac: number,
      ): (readonly [Vec3, Vec3])[] => {
        const half = armFor(step) * widthFrac;
        const out: (readonly [Vec3, Vec3])[] = [];
        for (const deg of degrees) {
          const radial = unit(sub(at(deg), seat.base)) ?? NO_DIRECTION;
          const centre = at(deg);
          out.push([
            addScaled(centre, radial, -half),
            addScaled(centre, radial, half),
          ]);
          out.push([
            addScaled(centre, axis, -half),
            addScaled(centre, axis, half),
          ]);
        }
        return out;
      };
      return {
        spine,
        spineRadius: headLength * ARROW_RADIUS_FRAC * SHAFT_RADIUS_FRAC,
        head: {
          base: tip,
          tip: addScaled(tip, tangent, headLength),
          length: headLength,
          radius: headLength * ARROW_RADIUS_FRAC,
        },
        rungs: cross(
          stops.major,
          stops.majorStep > 0 ? stops.majorStep : stops.pitch,
          1,
        ),
        minorRungs: cross(stops.minor, stops.pitch, MINOR_RUNG_FRAC),
      };
    },
    clamp,
    // The angular ladder is already screen-floored in `stops`, so its pitch is
    // a drawn rung exactly as the linear one is.
    quantize: (value, free, stops) =>
      quantize(
        value,
        stops !== undefined && stops.pitch > 0 ? stops.pitch : snap,
        free,
        min,
        max,
        1e4,
      ),
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
