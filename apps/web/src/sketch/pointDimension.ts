/**
 * Point dimensions (SKETCH-POINT-DISTANCE) — pure, no store, no three.js.
 *
 * Fusion 360's Sketch Dimension on two points gives the aligned distance, or
 * the horizontal or vertical one, chosen by WHERE THE LABEL IS DROPPED; on a
 * point and a line it gives the perpendicular distance to the line. The wire
 * kinds are `point_distance` (with `direction`) and `point_line_distance`; the
 * geometry service solves them (`point_distance.py`), holding the side the
 * point was drawn on. This module is the client's half: what a pick makes,
 * where the label and its ink sit, and what the geometry currently measures.
 *
 * Either operand may be a virtual sharp (`sharp` on the ref): the corner a
 * fillet trimmed away, as `distance` already keeps its ends (virtualSharp.ts).
 */
import type { components } from "@loft/ts-client/gateway";

import type { EntityPointRef, SketchConstraint } from "./constraints";
import { namedPoints } from "./pick";
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";
import { lineIntersection } from "./virtualSharp";

export type DimensionPointRef = components["schemas"]["DimensionPointRef"];
export type PointDistanceDirection =
  components["schemas"]["PointDistanceConstraint"]["direction"];
export type PointDistanceConstraint = Extract<
  SketchConstraint,
  { kind: "point_distance" }
>;
export type PointLineDistanceConstraint = Extract<
  SketchConstraint,
  { kind: "point_line_distance" }
>;
export type PointDimensionConstraint =
  PointDistanceConstraint | PointLineDistanceConstraint;

/** The operands of a point dimension — what the editor target carries. */
export type PointDimensionSubject =
  | {
      kind: "point_distance";
      a: DimensionPointRef;
      b: DimensionPointRef;
      direction: PointDistanceDirection;
    }
  | { kind: "point_line_distance"; point: DimensionPointRef; line: string };

type Line = Extract<SketchEntity, { kind: "line" }>;
type ById = ReadonlyMap<string, SketchEntity>;

const asLine = (entity: SketchEntity | undefined): Line | null =>
  entity?.kind === "line" ? entity : null;

/** A ref as the wire wants it: `sharp` only when there is one. */
export function operandRef(
  ref: EntityPointRef,
  sharp?: string | null,
): DimensionPointRef {
  return sharp == null
    ? { entity: ref.entity, point: ref.point }
    : { entity: ref.entity, point: ref.point, sharp };
}

export const sameOperand = (
  a: DimensionPointRef,
  b: DimensionPointRef,
): boolean =>
  a.entity === b.entity &&
  a.point === b.point &&
  (a.sharp ?? null) === (b.sharp ?? null);

/** Where an operand is now: the named point, or the virtual sharp it names. */
export function operandPoint(
  ref: DimensionPointRef,
  byId: ById,
): Point2D | null {
  if (ref.sharp != null) {
    const own = asLine(byId.get(ref.entity));
    const other = asLine(byId.get(ref.sharp));
    return own === null || other === null ? null : lineIntersection(own, other);
  }
  const entity = byId.get(ref.entity);
  if (entity === undefined) return null;
  return namedPoints(entity).find((p) => p.point === ref.point)?.at ?? null;
}

/** Every entity id a point dimension binds to (sharps included). */
export function pointDimensionRefs(c: PointDimensionConstraint): string[] {
  const ids = (ref: DimensionPointRef): string[] =>
    ref.sharp == null ? [ref.entity] : [ref.entity, ref.sharp];
  return c.kind === "point_distance"
    ? [...ids(c.a), ...ids(c.b)]
    : [...ids(c.point), c.line];
}

export function subjectOf(c: PointDimensionConstraint): PointDimensionSubject {
  return c.kind === "point_distance"
    ? { kind: c.kind, a: c.a, b: c.b, direction: c.direction }
    : { kind: c.kind, point: c.point, line: c.line };
}

/**
 * The same DIMENSION, whatever its number: the same pair of points in either
 * order and the same direction, or the same point to the same line. A
 * horizontal and a vertical on one pair are two dimensions, not one.
 */
export function sameSubject(
  a: PointDimensionSubject,
  b: PointDimensionSubject,
): boolean {
  if (a.kind === "point_distance" && b.kind === "point_distance") {
    return (
      a.direction === b.direction &&
      ((sameOperand(a.a, b.a) && sameOperand(a.b, b.b)) ||
        (sameOperand(a.a, b.b) && sameOperand(a.b, b.a)))
    );
  }
  if (a.kind === "point_line_distance" && b.kind === "point_line_distance") {
    return sameOperand(a.point, b.point) && a.line === b.line;
  }
  return false;
}

/** Foot of the perpendicular from `p` onto the line's support; null if degenerate. */
function foot(p: Point2D, line: Line): Point2D | null {
  const dx = line.end.x - line.start.x;
  const dy = line.end.y - line.start.y;
  const length2 = dx * dx + dy * dy;
  if (length2 === 0) return null;
  const t = ((p.x - line.start.x) * dx + (p.y - line.start.y) * dy) / length2;
  return { x: line.start.x + t * dx, y: line.start.y + t * dy };
}

/** The unsigned value the dimension reads on this geometry, or null. */
export function measurePointDimension(
  subject: PointDimensionSubject,
  byId: ById,
): number | null {
  if (subject.kind === "point_distance") {
    const a = operandPoint(subject.a, byId);
    const b = operandPoint(subject.b, byId);
    if (a === null || b === null) return null;
    switch (subject.direction) {
      case "aligned":
        return Math.hypot(b.x - a.x, b.y - a.y);
      case "horizontal":
        return Math.abs(b.x - a.x);
      case "vertical":
        return Math.abs(b.y - a.y);
    }
  }
  const p = operandPoint(subject.point, byId);
  const line = asLine(byId.get(subject.line));
  const f = p === null || line === null ? null : foot(p, line);
  return p === null || f === null ? null : Math.hypot(p.x - f.x, p.y - f.y);
}

/**
 * FUSION'S LABEL RULE for two points: drag the label above or below the pair
 * (inside its horizontal extent) and the dimension is HORIZONTAL; left or
 * right of it (inside its vertical extent) and it is VERTICAL; anywhere else —
 * between the points, or off a corner of their box — it is ALIGNED.
 */
export function placementDirection(
  a: Point2D,
  b: Point2D,
  label: Point2D,
): PointDistanceDirection {
  const insideX =
    label.x >= Math.min(a.x, b.x) && label.x <= Math.max(a.x, b.x);
  const insideY =
    label.y >= Math.min(a.y, b.y) && label.y <= Math.max(a.y, b.y);
  if (insideX && !insideY) return "horizontal";
  if (insideY && !insideX) return "vertical";
  return "aligned";
}

/** One straight piece of dimension ink, in sketch-plane mm. */
export type InkSegment = [Point2D, Point2D];

/**
 * Where a point dimension's number sits, and the ink that says what it
 * measures: the dimension line, plus extension lines for a horizontal or
 * vertical one, plus the line's own extension to the foot for a point to a
 * line that lies past the drawn segment. Null when an operand is gone.
 */
export function pointDimensionLayout(
  subject: PointDimensionSubject,
  byId: ById,
  offsetMm: number,
): { anchor: Point2D; ink: InkSegment[] } | null {
  if (subject.kind === "point_line_distance") {
    const p = operandPoint(subject.point, byId);
    const line = asLine(byId.get(subject.line));
    const f = p === null || line === null ? null : foot(p, line);
    if (p === null || line === null || f === null) return null;
    const dx = line.end.x - line.start.x;
    const dy = line.end.y - line.start.y;
    const length = Math.hypot(dx, dy);
    const along = { x: dx / length, y: dy / length };
    const ink: InkSegment[] = [[p, f]];
    const t =
      ((f.x - line.start.x) * dx + (f.y - line.start.y) * dy) /
      (length * length);
    if (t < 0) ink.push([line.start, f]);
    if (t > 1) ink.push([line.end, f]);
    return {
      anchor: {
        x: (p.x + f.x) / 2 + along.x * offsetMm,
        y: (p.y + f.y) / 2 + along.y * offsetMm,
      },
      ink,
    };
  }
  const a = operandPoint(subject.a, byId);
  const b = operandPoint(subject.b, byId);
  if (a === null || b === null) return null;
  switch (subject.direction) {
    case "horizontal": {
      const y = Math.max(a.y, b.y) + offsetMm;
      const ends: InkSegment = [
        { x: a.x, y },
        { x: b.x, y },
      ];
      return {
        anchor: { x: (a.x + b.x) / 2, y: y + offsetMm },
        ink: [ends, [a, ends[0]], [b, ends[1]]],
      };
    }
    case "vertical": {
      const x = Math.max(a.x, b.x) + offsetMm;
      const ends: InkSegment = [
        { x, y: a.y },
        { x, y: b.y },
      ];
      return {
        anchor: { x: x + offsetMm, y: (a.y + b.y) / 2 },
        ink: [ends, [a, ends[0]], [b, ends[1]]],
      };
    }
    case "aligned": {
      const length = Math.hypot(b.x - a.x, b.y - a.y);
      const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
      const anchor =
        length === 0
          ? mid
          : {
              x: mid.x + ((b.y - a.y) / length) * offsetMm,
              y: mid.y - ((b.x - a.x) / length) * offsetMm,
            };
      return { anchor, ink: [[a, b]] };
    }
  }
}

/** The ink of every point dimension in the sketch, for the scene to draw. */
export function pointDimensionInk(
  constraints: readonly SketchConstraint[],
  entities: readonly SketchEntity[],
  offsetMm: number,
): InkSegment[] {
  const byId: ById = new Map(entities.map((e) => [e.id, e]));
  return constraints.flatMap((c) =>
    c.kind === "point_distance" || c.kind === "point_line_distance"
      ? (pointDimensionLayout(subjectOf(c), byId, offsetMm)?.ink ?? [])
      : [],
  );
}

/** The wire constraint for a subject and its typed fields. */
export function pointDimensionConstraint(
  subject: PointDimensionSubject,
  fields: {
    value_mm: number;
    expression: string | null;
    name: string | null;
    driving: boolean | null;
  },
): PointDimensionConstraint {
  return subject.kind === "point_distance"
    ? {
        kind: "point_distance",
        a: subject.a,
        b: subject.b,
        direction: subject.direction,
        ...fields,
      }
    : {
        kind: "point_line_distance",
        point: subject.point,
        line: subject.line,
        ...fields,
      };
}

/**
 * A corner fillet or chamfer moved `moved` (a trimmed leg's end); an operand
 * on it is re-attached to the corner's virtual sharp with `otherLeg`, as a
 * length dimension is (cornerConstraints.ts). Null when nothing changes.
 */
export function sharpenOperands(
  c: PointDimensionConstraint,
  moved: (ref: DimensionPointRef) => string | null,
): PointDimensionConstraint | null {
  const sharpen = (ref: DimensionPointRef): DimensionPointRef | null => {
    if (ref.sharp != null) return null;
    const other = moved(ref);
    return other === null ? null : { ...ref, sharp: other };
  };
  if (c.kind === "point_distance") {
    const a = sharpen(c.a);
    const b = sharpen(c.b);
    return a === null && b === null ? null : { ...c, a: a ?? c.a, b: b ?? c.b };
  }
  const point = sharpen(c.point);
  // A sharp ON the dimensioned line is always on it: the wire refuses it.
  return point === null || point.sharp === c.line ? null : { ...c, point };
}
