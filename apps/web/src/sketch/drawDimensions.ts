/**
 * DIMENSION WHILE YOU DRAW (FB-16) — pure logic, no store, no three.js.
 *
 * Founder, 2026-08-01: *"usually dimensions are applied automatically with text
 * boxes."* In Fusion / SolidWorks / Onshape the size of a shape is typed AS it
 * is made: drag a rectangle, its width and height appear as cells at the
 * corner, Tab walks them, Enter commits. You almost never go back afterwards
 * and dimension what you drew — which is why the founder's very FIRST report
 * ("dimensions are not working when I click a line to [assign] height") read as
 * broken: select-then-D is the FALLBACK path, and we shipped only the fallback.
 *
 * This module owns the three pure questions that path asks:
 *   1. which cells does a gesture offer  ({@link drawDimensionFields});
 *   2. what geometry does a typed value produce ({@link resizeDrawn});
 *   3. which constraints record it       ({@link drawDimensionConstraints}).
 *
 * WHY THE GEOMETRY IS REWRITTEN AND *THEN* CONSTRAINED, rather than left for
 * the solver to move: typing 50 into a rectangle drawn at 43 must produce a
 * 50 mm rectangle with the corner you started from where you put it. Handing
 * the solver an unsatisfied distance instead makes IT choose which end moves —
 * a choice it makes on numerics, not intent, and one that lands somewhere new
 * every time. So the value is applied to the geometry immediately (instant,
 * deterministic, correct with no round-trip) and the driving constraint records
 * it; the next solve then CONFIRMS rather than decides.
 *
 * WHY A RECTANGLE GETS ITS RIGIDITY CONSTRAINTS: `tools.ts` emits a rectangle
 * as four independent lines with no constraints tying them, so a bare
 * `distance` on one edge stretches THAT LINE ALONE and tears the rectangle open
 * at the next solve — the profile then fails to close and the extrude dies. A
 * rectangle therefore carries the four corner coincidences and the two
 * horizontal / two vertical constraints that make it a rectangle
 * (16 DOF − 12 = 4: x, y, w, h — no redundancy, and two dimensions leave it
 * free to translate, as an unanchored sketch should be).
 *
 * RECT-1, 2026-08-16 — WHERE they are authored moved, and the original choice
 * is worth recording because it was deliberate and wrong. They used to ride
 * with the first TYPED dimension, on the reasoning that "a shape nobody
 * dimensioned still solves exactly as it did before this landed" — i.e.
 * touching the undimensioned case was treated as the risk. It is the opposite.
 * An undimensioned rectangle is the ORDINARY case, and leaving it bare means
 * the most common closed-profile gesture in CAD produces four numerically
 * coincident but topologically disconnected lines: dimension any one edge
 * later and the other three stay put, so it tears at the corners on the first
 * re-drive. Worse, this was invisible until DIM-1 (`a810524`) — draw-time
 * keystrokes were not registering at all, so essentially every rectangle drawn
 * against this build took the untyped path.
 *
 * So rigidity is now authored at PLACEMENT ({@link shapeRigidity}, called from
 * the store's `placeAt`), where it belongs: a rectangle is a closed,
 * axis-aligned profile the moment it is drawn, which is what the word means.
 * {@link drawDimensionConstraints} therefore no longer emits it — authoring it
 * in both places would double every equation and report a rectangle the user
 * merely dimensioned as OVER-CONSTRAINED, which is a worse failure than the
 * one being fixed. One author, one place; the typed path adds only dimensions.
 */
import type { Point2D } from "./plane";
import { rectangleCorners, type SketchEntity, type SketchTool } from "./tools";
import type { SketchConstraint } from "./constraints";

/** The shapes whose size is offered at draw time. */
export type DrawShape = "rect" | "line" | "circle";

/** Which measurement a cell drives. */
export type DrawDimensionKey = "width" | "height" | "length" | "radius";

/**
 * The tools that offer draw-time dimensions. Arc and spline are deliberately
 * absent: an arc is three points (its size is not settled until the last one,
 * so a cell would keep changing what it means mid-gesture) and a spline has no
 * single scalar size at all. Both keep the select-then-D fallback.
 */
export function drawShapeOf(tool: SketchTool): DrawShape | null {
  switch (tool) {
    case "rect":
      return "rect";
    case "line":
      return "line";
    case "circle":
      return "circle";
    default:
      return null;
  }
}

export interface DrawDimensionField {
  key: DrawDimensionKey;
  /** Terse drafting label on the cell — W / H / L / R. */
  label: string;
  /** Spoken name, for the accessible label. */
  name: string;
  /** The as-drawn value (mm) the cell shows until something is typed. */
  measuredMm: number;
  /**
   * The entity this cell dimensions, or null while the shape is still being
   * dragged (nothing has an id until the gesture commits).
   */
  entity: string | null;
  kind: "distance" | "radius";
}

const distance = (a: Point2D, b: Point2D): number =>
  Math.hypot(b.x - a.x, b.y - a.y);

/**
 * The cells a gesture from `from` to `to` offers. `ids` are the entity ids the
 * placement emitted, in emission order (rectangle: bottom, right, top, left) —
 * pass none while the shape is still being drawn.
 *
 * A rectangle's WIDTH is the bottom edge and its HEIGHT the right edge: the two
 * adjacent edges of the corner the drag ends on, so the pair the user is
 * looking at is the pair they can type into.
 */
export function drawDimensionFields(
  shape: DrawShape,
  from: Point2D,
  to: Point2D,
  ids: readonly string[] = [],
): DrawDimensionField[] {
  switch (shape) {
    case "rect":
      return [
        {
          key: "width",
          label: "W",
          name: "Width",
          measuredMm: Math.abs(to.x - from.x),
          entity: ids[0] ?? null,
          kind: "distance",
        },
        {
          key: "height",
          label: "H",
          name: "Height",
          measuredMm: Math.abs(to.y - from.y),
          entity: ids[1] ?? null,
          kind: "distance",
        },
      ];
    case "line":
      return [
        {
          key: "length",
          label: "L",
          name: "Length",
          measuredMm: distance(from, to),
          entity: ids[0] ?? null,
          kind: "distance",
        },
      ];
    case "circle":
      return [
        {
          key: "radius",
          label: "R",
          name: "Radius",
          measuredMm: distance(from, to),
          entity: ids[0] ?? null,
          kind: "radius",
        },
      ];
  }
}

/** Typed values (mm), keyed by cell. Absent/undefined = "leave as drawn". */
export type DrawDimensionValues = Partial<Record<DrawDimensionKey, number>>;

/** Signed unit step: keeps the drag's direction when a magnitude is retyped. */
const sign = (delta: number): number => (delta < 0 ? -1 : 1);

/**
 * The second gesture point, moved so the typed values hold. The FIRST point
 * never moves — it is where the user chose to start, and every other CAD keeps
 * it put while the size is retyped.
 */
export function resizedTo(
  shape: DrawShape,
  from: Point2D,
  to: Point2D,
  values: DrawDimensionValues,
): Point2D {
  switch (shape) {
    case "rect": {
      const width = values.width ?? Math.abs(to.x - from.x);
      const height = values.height ?? Math.abs(to.y - from.y);
      return {
        x: from.x + sign(to.x - from.x) * width,
        y: from.y + sign(to.y - from.y) * height,
      };
    }
    case "line": {
      const length = values.length;
      const drawn = distance(from, to);
      if (length === undefined || drawn === 0) return to;
      return {
        x: from.x + ((to.x - from.x) / drawn) * length,
        y: from.y + ((to.y - from.y) / drawn) * length,
      };
    }
    case "circle": {
      const radius = values.radius;
      const drawn = distance(from, to);
      if (radius === undefined || drawn === 0) return to;
      return {
        x: from.x + ((to.x - from.x) / drawn) * radius,
        y: from.y + ((to.y - from.y) / drawn) * radius,
      };
    }
  }
}

/**
 * Rewrite the drafted entities to the typed size, in place in the entity list
 * (ids preserved, so every constraint already bound to them survives). Entities
 * the draft does not name are returned untouched, and an id the list no longer
 * holds is skipped rather than resurrected.
 */
export function resizeDrawn(
  shape: DrawShape,
  ids: readonly string[],
  from: Point2D,
  to: Point2D,
  entities: readonly SketchEntity[],
  values: DrawDimensionValues,
): SketchEntity[] {
  const end = resizedTo(shape, from, to, values);
  const patch = new Map<string, (entity: SketchEntity) => SketchEntity>();
  switch (shape) {
    case "rect": {
      const corners = rectangleCorners(from, end);
      ids.slice(0, 4).forEach((id, i) => {
        const start = corners[i] as Point2D;
        const finish = corners[(i + 1) % 4] as Point2D;
        patch.set(id, (entity) =>
          entity.kind === "line" ? { ...entity, start, end: finish } : entity,
        );
      });
      break;
    }
    case "line": {
      const id = ids[0];
      if (id !== undefined) {
        patch.set(id, (entity) =>
          entity.kind === "line" ? { ...entity, end } : entity,
        );
      }
      break;
    }
    case "circle": {
      const id = ids[0];
      if (id !== undefined) {
        patch.set(id, (entity) =>
          entity.kind === "circle"
            ? { ...entity, radius: distance(from, end) }
            : entity,
        );
      }
      break;
    }
  }
  return entities.map((entity) => patch.get(entity.id)?.(entity) ?? entity);
}

/**
 * The rigidity set a freshly-placed shape carries — the constraints that make
 * it the shape the user asked for rather than a coincidence of coordinates.
 * Called from the store's `placeAt` at the moment of the draw; see the module
 * note (RECT-1) for why this is not deferred to the first typed dimension.
 *
 * A circle needs nothing: `tools.ts` emits it as a single entity, so there is
 * no topology to hold together.
 */
export function shapeRigidity(
  shape: DrawShape,
  ids: readonly string[],
): SketchConstraint[] {
  return shape === "rect" ? rectangleRigidity(ids) : [];
}

/**
 * The rectangle's rigidity set: four corner coincidences plus horizontal on the
 * bottom/top and vertical on the left/right edges.
 */
function rectangleRigidity(ids: readonly string[]): SketchConstraint[] {
  const [bottom, right, top, left] = ids;
  if (
    bottom === undefined ||
    right === undefined ||
    top === undefined ||
    left === undefined
  ) {
    return [];
  }
  const loop = [bottom, right, top, left];
  const constraints: SketchConstraint[] = loop.map((id, i) => ({
    kind: "coincident",
    a: { entity: id, point: "end" },
    b: { entity: loop[(i + 1) % 4] as string, point: "start" },
  }));
  constraints.push(
    { kind: "horizontal", entity: bottom },
    { kind: "horizontal", entity: top },
    { kind: "vertical", entity: right },
    { kind: "vertical", entity: left },
  );
  return constraints;
}

/**
 * One driving dimension per typed cell, and nothing else. Returns nothing when
 * nothing was typed.
 *
 * The shape's rigidity set is NOT here: it is authored at placement by
 * {@link shapeRigidity}, so by the time this runs the rectangle is already a
 * rectangle. Emitting it again would duplicate all twelve equations and turn an
 * ordinary draw-then-dimension into an OVER-CONSTRAINED report — see the module
 * note (RECT-1). `shape` is kept in the signature because the caller's draft is
 * keyed by it and a future shape may need per-shape dimension handling.
 */
export function drawDimensionConstraints(
  _shape: DrawShape,
  _ids: readonly string[],
  fields: readonly DrawDimensionField[],
  values: DrawDimensionValues,
): SketchConstraint[] {
  const typed = fields.filter(
    (field) => field.entity !== null && values[field.key] !== undefined,
  );
  if (typed.length === 0) return [];
  const constraints: SketchConstraint[] = [];
  for (const field of typed) {
    constraints.push({
      kind: field.kind,
      entity: field.entity as string,
      value_mm: values[field.key] as number,
    });
  }
  return constraints;
}

/**
 * Witness geometry for the dimension a cell is driving — the drafting callout
 * drawn in the scene while that cell has focus, so "which edge is this number"
 * is never a guess. Extension lines at each end plus the dimension line between
 * them, offset AWAY from the shape's centre; a radius is its own spoke.
 * Returns plane-mm segment pairs.
 */
export function dimensionWitness(
  a: Point2D,
  b: Point2D,
  awayFrom: Point2D,
  offsetMm: number,
): Array<[Point2D, Point2D]> {
  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  let ox = mid.x - awayFrom.x;
  let oy = mid.y - awayFrom.y;
  const length = Math.hypot(ox, oy);
  if (length < 1e-9) {
    // Degenerate (the segment runs through the centre): fall back to the
    // segment's own left normal so a witness line still appears.
    ox = -(b.y - a.y);
    oy = b.x - a.x;
    const fallback = Math.hypot(ox, oy);
    if (fallback < 1e-9) return [];
    ox = (ox / fallback) * offsetMm;
    oy = (oy / fallback) * offsetMm;
  } else {
    ox = (ox / length) * offsetMm;
    oy = (oy / length) * offsetMm;
  }
  const a2 = { x: a.x + ox, y: a.y + oy };
  const b2 = { x: b.x + ox, y: b.y + oy };
  return [
    [a, a2],
    [b, b2],
    [a2, b2],
  ];
}
