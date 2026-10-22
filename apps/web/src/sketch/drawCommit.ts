/**
 * What applying a drawn shape's typed cells does to the sketch (FB-16,
 * SKETCH-LINE-ANGLE): pure, no store. Split out of `store.ts`
 * (FILE-SIZE-RATCHET) when the line's box gained its angle cell.
 */
import { constraintEntityRefs, type SketchConstraint } from "./constraints";
import { datumFrame, groundDatums } from "./datum";
import {
  drawDimensionFields,
  resizeDrawn,
  type AngleReference,
  sizeDraft,
  type DrawDimensionExpressions,
  type DrawDimensionField,
  type DrawDimensionValues,
  type DrawShape,
} from "./drawDimensions";
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";

/**
 * The size cells a just-placed shape offers (FB-16), keyed by the entities
 * the placement emitted; `reference` is the line's angle reference.
 */
export function placedDraft(
  shape: DrawShape,
  from: Point2D,
  to: Point2D,
  emitted: readonly SketchEntity[],
  reference: AngleReference,
) {
  const ids = emitted.map((entity) => entity.id);
  const fields = drawDimensionFields(shape, from, to, ids, reference);
  return { shape, ids, from, to, fields, typed: false };
}

export interface CommittedDraft {
  entities: SketchEntity[];
  constraints: SketchConstraint[];
}

/**
 * The sketch after a draft's typed values apply, or null when nothing typed
 * is worth a dimension. The shape is resized (a typed angle turns a line
 * about its start), and one driving dimension per typed cell is added.
 *
 * A typed angle replaces the Horizontal / Vertical the draw inferred on that
 * line (SNAP-5), as Fusion's does: the user has said what the direction is,
 * and keeping both over-constrains it. An angle to the X axis grounds the
 * axis (the same call a picked axis makes), so the solver has a fixed line to
 * measure it from.
 */
export function commitDraft(
  draft: {
    shape: DrawShape;
    ids: readonly string[];
    from: Point2D;
    to: Point2D;
    fields: readonly DrawDimensionField[];
  },
  entities: readonly SketchEntity[],
  constraints: readonly SketchConstraint[],
  frameHalfMm: number,
  values: DrawDimensionValues,
  expressions?: DrawDimensionExpressions,
): CommittedDraft | null {
  const { shape, ids, from, to } = draft;
  const { typed, added } = sizeDraft(draft, values, expressions);
  if (added.length === 0) return null;
  const reference = draft.fields.find((f) => f.reference !== undefined);
  const resized = resizeDrawn(
    shape,
    ids,
    from,
    to,
    entities,
    typed,
    reference?.reference,
  );
  const kept =
    typed.angle === undefined
      ? constraints
      : constraints.filter(
          (c) =>
            !(
              (c.kind === "horizontal" || c.kind === "vertical") &&
              ids.includes(c.entity)
            ),
        );
  const grounded = groundDatums(
    resized,
    added.flatMap(constraintEntityRefs),
    datumFrame(frameHalfMm),
  );
  return {
    entities: grounded.entities,
    constraints: [...kept, ...added, ...grounded.constraints],
  };
}
