/**
 * The drafting callout for the draw-time size cell that has focus. Split out
 * of `SketchScene.tsx` (FILE-SIZE-RATCHET) when the line's box gained its
 * angle cell (SKETCH-LINE-ANGLE).
 */
import { sketch } from "@loft/design/tokens";

import {
  angleWitness,
  dimensionWitness,
  type DrawDimensionKey,
} from "../sketch/drawDimensions";
import { planeToWorld, type PlaneBasis, type Point2D } from "../sketch/plane";
import type { DrawDimensionDraft } from "../sketch/store";
import type { SketchEntity } from "../sketch/tools";

/**
 * Extension lines and a dimension line laid on the very edge the number
 * drives (or, for a line's angle, its reference ray and the arc it is
 * measured on). Without it a pair of cells labelled W and H is a form
 * floating over a picture; with it, typing in a cell points at its own edge,
 * which is how a drawing says the same thing. Empty whenever no cell has
 * focus.
 */
export function witnessPositions(
  draft: DrawDimensionDraft | null,
  focus: DrawDimensionKey | null,
  entities: readonly SketchEntity[],
  basis: PlaneBasis,
): Float32Array {
  if (draft === null || focus === null) return new Float32Array(0);
  const field = draft.fields.find((f) => f.key === focus);
  if (field?.entity == null) return new Float32Array(0);
  const entity = entities.find((e) => e.id === field.entity);
  if (entity === undefined) return new Float32Array(0);
  const centre = {
    x: (draft.from.x + draft.to.x) / 2,
    y: (draft.from.y + draft.to.y) / 2,
  };
  let segments: Array<[Point2D, Point2D]> = [];
  if (entity.kind === "line" && field.reference !== undefined) {
    segments = angleWitness(
      entity.start,
      entity.end,
      field.reference.direction,
    );
  } else if (entity.kind === "line") {
    segments = dimensionWitness(
      entity.start,
      entity.end,
      centre,
      sketch.glyphOffsetMm,
    );
  } else if (entity.kind === "circle") {
    // The diameter the Ø cell drives, rim to rim through the centre.
    const { center, radius } = entity;
    segments = [
      [
        { x: center.x - radius, y: center.y },
        { x: center.x + radius, y: center.y },
      ],
    ];
  }
  if (segments.length === 0) return new Float32Array(0);
  const positions = new Float32Array(segments.length * 6);
  segments.forEach(([a, b], i) => {
    positions.set(planeToWorld(basis, a), i * 6);
    positions.set(planeToWorld(basis, b), i * 6 + 3);
  });
  return positions;
}
