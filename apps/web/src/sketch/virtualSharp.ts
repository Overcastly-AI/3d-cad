/**
 * Virtual sharps (SKETCH-FILLET-KEEP-DIMS) — pure, no store, no three.js.
 *
 * A sketch fillet or chamfer trims its two legs back from their corner. The
 * rectangle's W and H used to be dropped with the corner, and an R edit then
 * grew the outline (80 x 50 at R5 -> R15 became 100 x 70). SolidWorks and
 * Fusion 360 keep such a dimension and measure it to the VIRTUAL SHARP: the
 * point where the two legs' lines meet. On the wire a `distance` names the
 * other leg for either end (`start_sharp` / `end_sharp`); the geometry
 * service solves it (`virtual_sharp.py`). This module is the client's half:
 * the ids the sharp binds to, where the dimension's ends and glyph sit, and
 * the marks Fusion draws there (a small point where the extended legs meet).
 */
import type { SketchConstraint } from "./constraints";
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";

export type DistanceConstraint = Extract<
  SketchConstraint,
  { kind: "distance" }
>;
type Line = Extract<SketchEntity, { kind: "line" }>;
type ById = ReadonlyMap<string, SketchEntity>;

/** Where the infinite supports of two lines meet; null when parallel. */
export function lineIntersection(a: Line, b: Line): Point2D | null {
  const rx = a.end.x - a.start.x;
  const ry = a.end.y - a.start.y;
  const sx = b.end.x - b.start.x;
  const sy = b.end.y - b.start.y;
  const cross = rx * sy - ry * sx;
  if (cross === 0) return null;
  const t =
    ((b.start.x - a.start.x) * sy - (b.start.y - a.start.y) * sx) / cross;
  return { x: a.start.x + t * rx, y: a.start.y + t * ry };
}

/** The other legs a distance's virtual sharps bind to (none for a plain one). */
export function sharpIds(c: DistanceConstraint): string[] {
  return [c.start_sharp, c.end_sharp].filter(
    (id): id is string => id !== null && id !== undefined,
  );
}

const asLine = (entity: SketchEntity | undefined): Line | null =>
  entity?.kind === "line" ? entity : null;

/**
 * The dimensioned span: the line itself, with each end moved to its virtual
 * sharp where the constraint names one. An unresolvable sharp (the other leg
 * gone or parallel) keeps the line's own end, as the solver reports conflict.
 */
export function dimensionSpan(
  c: DistanceConstraint,
  entity: SketchEntity,
  byId: ById,
): SketchEntity {
  const line = asLine(entity);
  if (line === null) return entity;
  const sharp = (other: string | null | undefined, own: Point2D): Point2D => {
    const leg = other == null ? null : asLine(byId.get(other));
    return (leg === null ? null : lineIntersection(line, leg)) ?? own;
  };
  return {
    ...line,
    start: sharp(c.start_sharp, line.start),
    end: sharp(c.end_sharp, line.end),
  };
}

/** A line's annotation point: its midpoint pushed `offsetMm` along the left normal. */
export function lineAnnotationAnchor(
  entity: SketchEntity,
  offsetMm: number,
): Point2D {
  if (entity.kind !== "line") return { x: 0, y: 0 };
  const mid = {
    x: (entity.start.x + entity.end.x) / 2,
    y: (entity.start.y + entity.end.y) / 2,
  };
  const dx = entity.end.x - entity.start.x;
  const dy = entity.end.y - entity.start.y;
  const length = Math.hypot(dx, dy);
  if (length === 0) return mid;
  // Left-hand normal: H/V sit on one side, dimensions on the other.
  return {
    x: mid.x + (-dy / length) * offsetMm,
    y: mid.y + (dx / length) * offsetMm,
  };
}

/** One virtual sharp as drawn: the point, and each leg's extension to it. */
export interface VirtualSharpMark {
  key: string;
  at: Point2D;
  /** From each leg's nearer end to the sharp — the "extended legs". */
  extensions: Array<[Point2D, Point2D]>;
}

const nearerEnd = (line: Line, at: Point2D): Point2D =>
  Math.hypot(line.start.x - at.x, line.start.y - at.y) <=
  Math.hypot(line.end.x - at.x, line.end.y - at.y)
    ? line.start
    : line.end;

/** Every virtual sharp some distance is anchored to, once per pair of legs. */
export function virtualSharpMarks(
  constraints: readonly SketchConstraint[],
  entities: readonly SketchEntity[],
): VirtualSharpMark[] {
  const byId: ById = new Map(entities.map((e) => [e.id, e]));
  const marks = new Map<string, VirtualSharpMark>();
  for (const c of constraints) {
    if (c.kind !== "distance") continue;
    const line = asLine(byId.get(c.entity));
    if (line === null) continue;
    for (const other of sharpIds(c)) {
      const leg = asLine(byId.get(other));
      const at = leg === null ? null : lineIntersection(line, leg);
      if (leg === null || at === null) continue;
      const key = [line.id, leg.id].sort().join("\u0000");
      if (marks.has(key)) continue;
      marks.set(key, {
        key,
        at,
        extensions: [line, leg].map((l) => [nearerEnd(l, at), at]),
      });
    }
  }
  return [...marks.values()];
}
