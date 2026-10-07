/**
 * Reconcile constraints against a trim / extend / split of one curve. Split
 * out of `constraints.ts` (FILE-SIZE-RATCHET); the behaviour is unchanged
 * apart from endpoint tangents, which follow their ends as a coincident does.
 */
import {
  reconcileConstraints,
  type EntityPointRef,
  type ReconcileResult,
  type SketchConstraint,
} from "./constraints";
import { followEndpointTangent } from "./endpointTangent";
import { namedPoints } from "./pick";
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";

/** Two sketch points the edit left where they were (1e-9 mm, below any tolerance). */
const samePoint = (a: Point2D, b: Point2D): boolean =>
  Math.abs(a.x - b.x) <= 1e-9 && Math.abs(a.y - b.y) <= 1e-9;

/** A line's length, for "did the edit change it". Other kinds: no length rule. */
const lineLength = (entity: SketchEntity): number | null =>
  entity.kind === "line"
    ? Math.hypot(entity.end.x - entity.start.x, entity.end.y - entity.start.y)
    : null;

/**
 * Reconcile the constraints against a TRIM or EXTEND of `target` (helical-gear
 * gap G7). `reconcileConstraints` drops what names a vanished id; that is not
 * enough for the curve that SURVIVES the edit, because the edit changed its
 * shape, and the constraints that described the old shape fight the new one.
 * Measured in the gear test's keyway (and in `sketch-trim-extend.spec.ts`): a
 * line trimmed back from its typed 40 mm solved straight back to 40, so the
 * trim appeared to do nothing.
 *
 * On the surviving target:
 *
 *  - a constraint on an END that MOVED is re-attached when a new piece of the
 *    split now owns that exact point (the far corner of a line cut in the
 *    middle keeps its coincident), and dropped otherwise;
 *  - a line whose LENGTH changed loses its length-dependent constraints: its
 *    distance dimension, an equal-length pairing, and a midpoint relation (the
 *    middle moved);
 *  - everything still true is kept: orientation (horizontal, vertical,
 *    parallel, perpendicular, collinear, angle), an arc's radius and centre
 *    relations (a trimmed circle is still that circle), and every constraint on
 *    an end that did not move.
 *
 * `removed` counts every dropped constraint, for the edit note.
 */
export function reconcileEditedConstraints(
  constraints: readonly SketchConstraint[],
  before: readonly SketchEntity[],
  after: readonly SketchEntity[],
  target: string,
): ReconcileResult {
  const base = reconcileConstraints(constraints, after);
  const was = before.find((e) => e.id === target);
  const now = after.find((e) => e.id === target);
  if (was === undefined || now === undefined) return base;

  const wasPoints = new Map(namedPoints(was).map((p) => [p.point, p.at]));
  const nowPoints = new Map(namedPoints(now).map((p) => [p.point, p.at]));
  const moved = new Set<string>();
  for (const [name, at] of wasPoints) {
    const next = nowPoints.get(name);
    if (next === undefined || !samePoint(at, next)) moved.add(name);
  }
  const beforeIds = new Set(before.map((e) => e.id));
  const pieces = after.filter((e) => !beforeIds.has(e.id));
  const wasLength = lineLength(was);
  const nowLength = lineLength(now);
  const lengthChanged =
    wasLength !== null &&
    nowLength !== null &&
    Math.abs(wasLength - nowLength) > 1e-9;

  /** A ref that survives the edit: itself, re-homed onto a piece, or null. */
  const follow = (ref: EntityPointRef): EntityPointRef | null => {
    if (ref.entity !== target || !moved.has(ref.point)) return ref;
    const at = wasPoints.get(ref.point);
    if (at === undefined) return null;
    for (const piece of pieces) {
      const found = namedPoints(piece).find((p) => samePoint(p.at, at));
      if (found !== undefined) return { entity: piece.id, point: found.point };
    }
    return null;
  };
  const reconcileOne = (c: SketchConstraint): SketchConstraint | null => {
    switch (c.kind) {
      case "coincident":
      case "symmetric": {
        const a = follow(c.a);
        const b = follow(c.b);
        return a === null || b === null ? null : { ...c, a, b };
      }
      case "fixed": {
        const point = follow(c.point);
        return point === null ? null : { ...c, point };
      }
      case "midpoint": {
        if (c.line === target && lengthChanged) return null;
        const point = follow(c.point);
        return point === null ? null : { ...c, point };
      }
      case "distance":
        return c.entity === target && lengthChanged ? null : c;
      case "equal":
        return (c.a === target || c.b === target) && lengthChanged ? null : c;
      case "tangent":
        return followEndpointTangent(c, follow);
      // A point dimension's operands follow their ends as a coincident's do.
      // A virtual-sharp operand names where two lines MEET, which a trim or
      // extend along the line does not move: it is left as it is.
      case "point_distance": {
        const a = c.a.sharp == null ? follow(c.a) : c.a;
        const b = c.b.sharp == null ? follow(c.b) : c.b;
        return a === null || b === null ? null : { ...c, a, b };
      }
      case "point_line_distance": {
        const point = c.point.sharp == null ? follow(c.point) : c.point;
        return point === null ? null : { ...c, point };
      }
      default:
        return c;
    }
  };

  const kept = base.constraints.flatMap((c) => {
    const next = reconcileOne(c);
    return next === null ? [] : [next];
  });
  return { constraints: kept, removed: constraints.length - kept.length };
}
