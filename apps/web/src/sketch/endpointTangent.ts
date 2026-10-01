/**
 * Endpoint tangency (SKETCH-ENDPOINT-TANGENT) — pure, no store.
 *
 * A `tangent` with `a_point`/`b_point` set joins the named ends of the two
 * curves AND makes them tangent there: one constraint that is the coincidence
 * plus the tangency, which the solver encodes as FreeCAD does (a coincidence
 * plus planegcs `angle_via_point`). It exists because the whole-curve tangent
 * (centre-to-line distance = r) is redundant with a coincident at the same
 * join, so a fillet could not carry one, and an R edit then pulled the arc off
 * tangent with no warning. Since it IS the coincidence, a `coincident` on the
 * same two points is redundant with it: where one is authored it replaces the
 * join, as FreeCAD's endpoint-to-endpoint tangency does.
 */
import type { EntityPointRef, SketchConstraint } from "./constraints";
import type { SketchEntity } from "./tools";

/** What the pick hands over: a curve by id and kind. */
type CurveRef = Pick<SketchEntity, "id" | "kind">;

export type CurveEnd = "start" | "end";

export const isCurveEnd = (point: string): point is CurveEnd =>
  point === "start" || point === "end";

/** The two points a constraint makes one: a coincident, or a tangent's join. */
export function joinedPoints(
  c: SketchConstraint,
): [EntityPointRef, EntityPointRef] | null {
  if (c.kind === "coincident") return [c.a, c.b];
  if (c.kind === "tangent" && c.a_point != null && c.b_point != null) {
    return [
      { entity: c.a, point: c.a_point },
      { entity: c.b, point: c.b_point },
    ];
  }
  return null;
}

/**
 * The endpoint tangent for a user's Tangent on `a`/`b` when a `coincident`
 * already joins an end of each (a line meeting an arc, or two arcs, end to
 * end), with the coincident it replaces; null for curves that do not share an
 * end, which keep the whole-curve tangent. Read symbolically from the
 * constraints, never from coordinates, like every other join in the sketcher.
 */
export function endpointTangentFor(
  a: CurveRef,
  b: CurveRef,
  constraints: readonly SketchConstraint[],
): { constraint: SketchConstraint; replaces: SketchConstraint } | null {
  if (a.kind === "circle" || b.kind === "circle") return null;
  for (const c of constraints) {
    if (c.kind !== "coincident") continue;
    for (const [p, q] of [
      [c.a, c.b],
      [c.b, c.a],
    ] as const) {
      if (p.entity !== a.id || q.entity !== b.id) continue;
      if (!isCurveEnd(p.point) || !isCurveEnd(q.point)) continue;
      return {
        constraint: {
          kind: "tangent",
          a: a.id,
          b: b.id,
          a_point: p.point,
          b_point: q.point,
        },
        replaces: c,
      };
    }
  }
  return null;
}

/**
 * An endpoint tangent through a trim/split: both ends followed (re-homed onto
 * the piece that now owns the point) or the constraint dropped, exactly as a
 * coincident on the same join is. A whole-curve tangent passes through.
 */
export function followEndpointTangent(
  c: SketchConstraint & { kind: "tangent" },
  follow: (ref: EntityPointRef) => EntityPointRef | null,
): SketchConstraint | null {
  if (c.a_point == null || c.b_point == null) return c;
  const a = follow({ entity: c.a, point: c.a_point });
  const b = follow({ entity: c.b, point: c.b_point });
  if (a === null || b === null) return null;
  if (!isCurveEnd(a.point) || !isCurveEnd(b.point)) return null;
  return { ...c, a: a.entity, a_point: a.point, b: b.entity, b_point: b.point };
}
