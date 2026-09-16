/**
 * THE ONE COPY OF THE TUPLE VECTOR ARITHMETIC (board #63).
 *
 * ## Why this module exists, when four copies of it already did
 *
 * `axisAnchor.ts`, `edgeAnchor.ts`, `faceAnchor.ts` and `gauge.ts` each carried
 * their own forty lines of `sub`/`dot`/`cross`/normalise, and each copy argued
 * in a comment that a shared micro-vector library would be the premature
 * abstraction the DRY rule exempts. That argument was right on the day it was
 * written and stopped being right when the copies DIVERGED — which they did,
 * silently, in the one function that has a decision in it.
 *
 * MEASURED across the four, at `4e69434`, on the same inputs:
 *
 * | input `a`        | `axisAnchor.unit` | `edgeAnchor.unit` | `gauge.normalize` |
 * |------------------|-------------------|-------------------|-------------------|
 * | `[0,0,0]`        | `null`            | `null`            | **`[0,0,0]`**     |
 * | `[1e-10,0,0]`    | `[1,0,0]`         | **`null`**        | `[1,0,0]`         |
 * | `[1e-300,0,0]`   | `null`            | `null`            | **`[1e-300,0,0]`**|
 * | `[1e200,0,0]`    | **`[0,0,0]`**     | `[1,0,0]`         | **`[0,0,0]`**     |
 * | `cross` of two   | **`[0,0,1]`**     | `null`            | **`[0,0,1]`**     |
 * | near-opposite    |                   |                   |                   |
 * | normals          |                   |                   |                   |
 *
 * Three different answers to "which way does this point", and the two that
 * disagree with `null` are the dangerous ones, because **each returns a vector
 * that CLAIMS to be unit and is not**: a zero, a `1e-300`, or — the row that
 * matters in a real part — a confident direction distilled from `1e-11` of
 * rounding noise in the cross product of two nearly-antiparallel face normals.
 * Nothing downstream re-checks a direction's length, so a non-unit "unit"
 * vector propagates into a gauge pose as a collapsed instrument or a ladder
 * whose rungs have no length — the CRAFT-7 defect class, which the screenshot
 * gate caught once already and no unit assertion can see.
 *
 * ## Two arithmetic hazards, and why `length` is `Math.hypot`
 *
 * Three of the four copies computed length as `Math.sqrt(dot(a, a))`, which
 * squares before it roots and therefore inherits the square's range:
 *
 * - **Overflow.** `|a| > 1.34e154` squares to `Infinity`; `1/Infinity` is `0`,
 *   so `scale(a, 0)` hands back `[0,0,0]`. Measured on `[1e200,0,0]`.
 * - **Underflow, with a precision ramp in front of it.** `|a| < 1.8e-162`
 *   squares to `0` and the guard fires by accident; just ABOVE that boundary
 *   the squared sum is subnormal and has already lost most of its mantissa, so
 *   `[1.82e-162,0,0]` normalises to magnitude **0.818** — a unit vector 18 %
 *   short, with no guard anywhere near it.
 *
 * `Math.hypot` has neither hazard (it scales before squaring). It costs
 * 59 ns/call against 12 ns for `Math.sqrt(dot(a,a))` — measured, 200 k
 * iterations, this container — and the two agree to within 4.4e-16 relative
 * over 2 M random vectors at CAD magnitudes (1e-4..1e4 mm), differing at all in
 * 36 % of them but never past the last two ulp. Nothing here runs per-vertex
 * per-frame: these are O(edges) inside a `useMemo` a drag re-enters, so 47 ns
 * buys a length that is right at every magnitude, which is the trade this
 * module exists to make once instead of four times.
 *
 * ## The floor is a REFUSAL, not an epsilon
 *
 * {@link unit} returns `null` below {@link VEC3_UNIT_FLOOR}. That is
 * `edgeAnchor`'s behaviour, chosen over the majority `l > 0` form deliberately:
 * it is the only one of the three that cannot return a vector claiming to be
 * unit and failing to be, and the only one that refuses a direction distilled
 * from noise. Callers that cannot express refusal in their own signature write
 * an explicit `?? fallback` at the call site, so the policy is visible in the
 * diff rather than buried in a ternary.
 *
 * Note what a `l > 0` guard does once someone "fixes" `length` to `Math.hypot`
 * without touching the guard — the obviously-correct half of this change, made
 * alone: `hypot([5e-324,0,0])` is `5e-324`, which is `> 0`, and `1/5e-324` is
 * `Infinity`, so the result is `[NaN,NaN,NaN]`. That combination does not exist
 * in the tree today and is one plausible refactor away from existing, which is
 * the second reason the floor is a named constant here and not a `0`.
 */

/** A point or direction in world space. Plain tuple — no `three`, no GPU. */
export type Vec3 = readonly [number, number, number];

/**
 * Shortest vector this module will normalise, scene mm.
 *
 * Below it a direction is noise: a face centroid that lands ON the edge line,
 * two faces whose normals cancel, the cross product of two parallel normals.
 * Every caller treats `null` as "there is no direction here" and declines to
 * mount the gauge — a refusal, not a guess.
 *
 * 1e-9 mm is a picometre. No CAD input carries meaning at that scale, and the
 * kernel's own linear tolerance is 1e-7 m = 1e-4 mm, five decades above it, so
 * the floor cannot swallow a direction the kernel considers real.
 */
export const VEC3_UNIT_FLOOR = 1e-9;

export function add(a: Vec3, b: Vec3): Vec3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}

export function sub(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

export function scale(a: Vec3, k: number): Vec3 {
  return [a[0] * k, a[1] * k, a[2] * k];
}

export function addScaled(a: Vec3, b: Vec3, k: number): Vec3 {
  return [a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k];
}

export function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

export function cross(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

/**
 * Euclidean length. `Math.hypot`, not `Math.sqrt(dot(a, a))` — see the module
 * note: the squared form overflows above 1.34e154 and loses its mantissa below
 * 1.8e-162, and both failures are silent.
 */
export function length(a: Vec3): number {
  return Math.hypot(a[0], a[1], a[2]);
}

/**
 * Unit vector, or `null` when the input is too short to have a direction.
 *
 * The `null` is the whole point of this function — see the module note. A
 * caller whose own signature cannot carry a refusal should write
 * `unit(a) ?? SOMETHING_NAMED` so the fallback is a decision somebody can read,
 * not a ternary's else-branch.
 */
export function unit(a: Vec3): Vec3 | null {
  const l = length(a);
  // `Number.isFinite` is not belt-and-braces and it is not free of a story: an
  // INFINITE component sails through a `> floor` guard in all four of the
  // implementations this module replaced — `hypot` reports `Infinity`, which is
  // comfortably above any floor — and `scale(a, 1/Infinity)` is `Infinity * 0`,
  // i.e. **`[NaN, NaN, NaN]`**. That is the Inf-into-a-gauge-pose failure board
  // #63 was filed about, it was live in every copy, and a floor alone does not
  // stop it: the floor guards the SMALL end and this is the large one. (A NaN
  // component needs no guard — `NaN > x` is already false.)
  return Number.isFinite(l) && l > VEC3_UNIT_FLOOR ? scale(a, 1 / l) : null;
}

/**
 * Reverse a direction. The `+ 0` normalises `-0` to `+0`, the convention
 * `offsetBasis` already keeps in `sketch/plane`: a `-0` component compares
 * unequal in a deep comparison and prints as `-0` in a readout, so it becomes a
 * difference between two identical directions that nothing can act on.
 */
export function negate(a: Vec3): Vec3 {
  return [-a[0] + 0, -a[1] + 0, -a[2] + 0];
}

/** The component of `a` across `axis` (which must be a unit vector). */
export function reject(a: Vec3, axis: Vec3): Vec3 {
  return addScaled(a, axis, -dot(a, axis));
}
