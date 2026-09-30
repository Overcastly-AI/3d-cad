/**
 * Twist along a path (TWIST-TO-SWEEP): the angle rules the Sweep editor's
 * Twist field reads and writes, and the build-cost bound its heads-up note
 * keys on. Twist lives on Sweep, as "twist along path" does in Fusion 360 and
 * SolidWorks; an extrude's twist is a stored legacy field the Extrude editor
 * only carries through a save (see `extrude.ts`).
 *
 * Angles follow the document's angle convention, which is the revolve's and
 * the draft's: plain signed degrees, shown with a `°` unit.
 */
import type { SketchEntity } from "../api/parts";

/** The kernel's sanity bound on a twist, degrees (ten turns; design note §4). */
export const MAX_TWIST_DEG = 3600;

/**
 * Below this a twist is no twist: the kernel normalises `|twist| < 1e-9` deg to
 * absent (design note §4), so the form does the same rather than send a value
 * the stored row will not keep.
 */
export const MIN_TWIST_DEG = 1e-9;

/**
 * Parse the twist field to signed degrees: 0 for empty or a vanishing value
 * (no twist), or null when it is not a number or beyond ten turns.
 */
export function parseTwistDeg(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return 0;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || Math.abs(value) > MAX_TWIST_DEG) return null;
  return Math.abs(value) < MIN_TWIST_DEG ? 0 : value;
}

/** Field-level validation message for the twist, or null when it is valid. */
export function twistError(input: string): string | null {
  return parseTwistDeg(input) === null
    ? `Twist must be a number of degrees, at most ${MAX_TWIST_DEG} either way.`
    : null;
}

/** The hand of a twist, as an engineer says it, or null for none. */
export function twistHand(twistDeg: number): "Right-hand" | "Left-hand" | null {
  if (twistDeg === 0) return null;
  return twistDeg > 0 ? "Right-hand" : "Left-hand";
}

/**
 * A STORED twist as field text, exactly: `String` is JavaScript's shortest
 * round-trip form, so `parseTwistDeg(storedTwistInput(t)) === t` for every
 * twist the kernel accepts (1e-9 <= |t| <= 3600), and a no-op Save sends back
 * the number it was given (review B1: rounding here once changed the helix).
 */
export function storedTwistInput(twistDeg: number): string {
  return String(twistDeg);
}

/**
 * The kernel refuses a twist whose own cost estimate exceeds this, in seconds
 * (`TWIST_COST_LIMIT_S` in services/geometry/.../kernel/twist.py; geometry QA
 * F4, design note §6.1). Held to that source by a drift guard in the tests.
 */
export const TWIST_COST_LIMIT_S = 4.5;

/**
 * A conservative UPPER BOUND of the kernel's build-cost estimate for a twist
 * of this profile, in seconds: the formula design note §6.1 publishes for the
 * UI, from the profile's edge counts alone.
 *
 *     upper(T) = T (0.0136 L + 0.0165 C + 0.195 S)
 *              + T^2 (0.0094 L + 0.0002 S + sum over arcs (0.0002 + 0.0086 theta))
 *
 * `T` is turns, `L`/`C`/`S` the line, circle-or-arc and spline edge counts,
 * `theta` each circle's or arc's angle (2 pi for a circle). It never
 * under-states the kernel's estimate on the kernel's stress set but can
 * over-state it about 2x, so a caller may say "may be slow or refused", never
 * predict the refusal: the kernel's own verdict is the authority. The cost is
 * in turns and edges, not length, so it is the same along a sweep path as
 * over an extrude distance. Construction geometry and points are not edges.
 */
export function twistCostUpperS(
  twistDeg: number,
  entities: readonly SketchEntity[],
): number {
  const turns = Math.abs(twistDeg) / 360;
  let linear = 0;
  let quadratic = 0;
  for (const entity of entities) {
    if (entity.construction) continue;
    switch (entity.kind) {
      case "point":
        break;
      case "line":
        linear += 0.0136;
        quadratic += 0.0094;
        break;
      case "circle":
        linear += 0.0165;
        quadratic += 0.0002 + 0.0086 * 2 * Math.PI;
        break;
      case "arc": {
        const a0 = Math.atan2(
          entity.start.y - entity.center.y,
          entity.start.x - entity.center.x,
        );
        const a1 = Math.atan2(
          entity.end.y - entity.center.y,
          entity.end.x - entity.center.x,
        );
        // Counterclockwise from start to end (the wire's arc), in (0, 2 pi].
        let theta = a1 - a0;
        while (theta <= 0) theta += 2 * Math.PI;
        linear += 0.0165;
        quadratic += 0.0002 + 0.0086 * theta;
        break;
      }
      default:
        linear += 0.195;
        quadratic += 0.0002;
    }
  }
  return turns * linear + turns * turns * quadratic;
}
