/**
 * What a sketch fillet / chamfer does to the constraints — pure, no store.
 *
 * SKETCH-FILLET-UNTRIM (HARD-PARTS 2026-10-01). The corner edit is stateless
 * geometry: it trims the two legs back from their shared corner and appends
 * the bridge (arc or chamfer line), keeping the legs' ids. Reconciling only
 * the dangling ids left every constraint on the legs' OLD shape in force:
 *
 *  - the rectangle's corner coincidence still tied the two trimmed ends
 *    together, so the next solve pulled both back to the sharp corner;
 *  - the leg's typed length (the rectangle's W or H) still asked for the
 *    untrimmed length, so the solve stretched it back;
 *  - and nothing tied the bridge to the legs, so it was left dangling.
 *
 * A second fillet on the next corner was then computed from that re-solved,
 * un-trimmed geometry, and the profile came out open.
 *
 * Fusion 360 and SolidWorks re-home the corner instead: each trimmed end is
 * coincident with the bridge's matching end, a fillet arc carries its radius,
 * and nothing still refers to the sharp corner that is gone. That is what
 * {@link reconcileCornerConstraints} authors. A length dimension on a trimmed
 * leg is dropped (it measured the corner that no longer exists, the same rule
 * trim follows for the length it changes), and so is `equal` / `midpoint` on a
 * leg whose length changed.
 *
 * NO `tangent` IS AUTHORED, deliberately. The solver's line-arc tangent is
 * planegcs's whole-curve `tangent_line_arc` (centre-to-line distance = r). With
 * the arc's end already coincident with the leg's end, that equation is
 * first-order dependent on the coincidence at the solution, so planegcs flags
 * both tangents REDUNDANT and the sketch reads OVER-CONSTRAINED (measured: a
 * filleted rectangle went from DOF 5, clean, to "overconstrained, redundant
 * [10, 11]"). Fusion's fillet tangency is an endpoint tangency, which the wire
 * cannot say yet. Without it the arc is still held by its radius and both
 * joins, and a re-solve keeps it where it is (driving W 80 -> 100 translates
 * the arc and it stays tangent).
 */
import {
  reconcileConstraints,
  type EntityPointRef,
  type ReconcileResult,
  type SketchConstraint,
} from "./constraints";
import type { CornerOp } from "./corner";
import { namedPoints } from "./pick";
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";

/**
 * Two coordinates are the same point. Wider than the edit's arithmetic noise
 * so a solve adopted between the request and its result (last-digit moves)
 * does not read as a trim; far below any real setback.
 */
const SAME_MM = 1e-6;

const same = (a: Point2D, b: Point2D): boolean =>
  Math.hypot(a.x - b.x, a.y - b.y) <= SAME_MM;

const length = (e: SketchEntity): number =>
  e.kind === "line" ? Math.hypot(e.end.x - e.start.x, e.end.y - e.start.y) : 0;

/** The point refs a constraint addresses (whole-entity refs excluded). */
function pointRefs(c: SketchConstraint): EntityPointRef[] {
  switch (c.kind) {
    case "coincident":
    case "symmetric":
      return [c.a, c.b];
    case "fixed":
    case "midpoint":
      return [c.point];
    default:
      return [];
  }
}

/** One trimmed leg: its id, the end the edit moved, and whether it shrank. */
interface TrimmedLeg {
  id: string;
  moved: EntityPointRef[];
  /** Where the moved end now sits — the bridge meets it here. */
  at: Point2D | null;
  lengthChanged: boolean;
}

function trimmedLeg(
  id: string,
  before: readonly SketchEntity[],
  after: readonly SketchEntity[],
): TrimmedLeg | null {
  const was = before.find((e) => e.id === id);
  const now = after.find((e) => e.id === id);
  if (was === undefined || now === undefined) return null;
  const nowPoints = namedPoints(now);
  const moved: EntityPointRef[] = [];
  let at: Point2D | null = null;
  for (const { point, at: wasAt } of namedPoints(was)) {
    const next = nowPoints.find((p) => p.point === point);
    if (next !== undefined && same(next.at, wasAt)) continue;
    moved.push({ entity: id, point });
    at = next?.at ?? null;
  }
  return {
    id,
    moved,
    at,
    lengthChanged: Math.abs(length(was) - length(now)) > SAME_MM,
  };
}

/**
 * The constraints after a corner edit on legs `a` / `b` by `value` mm (the
 * fillet radius or chamfer setback): the stale ones dropped, the corner
 * re-homed onto the bridge. `removed` counts only what was dropped.
 */
export function reconcileCornerConstraints(
  constraints: readonly SketchConstraint[],
  before: readonly SketchEntity[],
  after: readonly SketchEntity[],
  corner: { op: CornerOp; a: string; b: string; value: number },
): ReconcileResult {
  const base = reconcileConstraints(constraints, after);
  const beforeIds = new Set(before.map((e) => e.id));
  const bridge = after.find((e) => !beforeIds.has(e.id));
  const legs = [corner.a, corner.b].map((id) => trimmedLeg(id, before, after));
  if (bridge === undefined || legs.some((leg) => leg === null)) return base;
  const trimmed = legs as TrimmedLeg[];

  const movedKey = (ref: EntityPointRef) => `${ref.entity}\u0000${ref.point}`;
  const gone = new Set(trimmed.flatMap((leg) => leg.moved.map(movedKey)));
  const shrunk = new Set(
    trimmed.filter((leg) => leg.lengthChanged).map((leg) => leg.id),
  );
  const stale = (c: SketchConstraint): boolean => {
    if (pointRefs(c).some((ref) => gone.has(movedKey(ref)))) return true;
    switch (c.kind) {
      case "distance":
        return shrunk.has(c.entity);
      case "equal":
        return shrunk.has(c.a) || shrunk.has(c.b);
      case "midpoint":
        return shrunk.has(c.line);
      default:
        return false;
    }
  };
  const kept = base.constraints.filter((c) => !stale(c));

  // The corner, re-homed: each trimmed end meets the bridge's matching end.
  const bridgeEnds = namedPoints(bridge).filter((p) => p.point !== "center");
  const joins: SketchConstraint[] = [];
  for (const leg of trimmed) {
    const [end] = leg.moved;
    const { at } = leg;
    const onBridge =
      at === null ? undefined : bridgeEnds.find((p) => same(p.at, at));
    if (end === undefined || onBridge === undefined) continue;
    joins.push({
      kind: "coincident",
      a: end,
      b: { entity: bridge.id, point: onBridge.point },
    });
  }
  // The fillet's radius, as Fusion dimensions it. No tangent: see the module
  // note for why the solver would report it redundant.
  const fillet: SketchConstraint[] =
    corner.op === "fillet" && bridge.kind === "arc"
      ? [{ kind: "radius", entity: bridge.id, value_mm: corner.value }]
      : [];
  return {
    constraints: [...kept, ...joins, ...fillet],
    removed: constraints.length - kept.length,
  };
}
