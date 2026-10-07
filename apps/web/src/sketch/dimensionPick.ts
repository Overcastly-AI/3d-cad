/**
 * The armed Dimension verb's clicks — pure, no store.
 *
 * Split out of `store.ts` (file-size ratchet, SKETCH-POINT-DISTANCE). Armed,
 * Dimension is Fusion 360's Sketch Dimension: a line opens its length, a round
 * its diameter, a point waits for a second point (then the label's placement
 * picks aligned / horizontal / vertical) or a line (the perpendicular
 * distance). These return the store fields each click changes.
 */
import {
  applyConstraintAction,
  pointDimensionEditor,
  type DimensionEditorTarget,
  type SketchConstraint,
} from "./constraints";
import { isDatumId } from "./datum";
import type { SketchPick } from "./pick";
import {
  operandPoint,
  operandRef,
  placementDirection,
  type DimensionPointRef,
} from "./pointDimension";
import type { Point2D } from "./plane";
import type { SketchSet, SketchState } from "./store";
import type { SketchEntity } from "./tools";

/** The two verbs that open a value editor, hence the two that can be ARMED. */
export type DimensionPickAction = "distance" | "radius";

/** What an armed dimension verb asks for, in the user's words. */
export const DIMENSION_PICK_HINT: Readonly<
  Record<DimensionPickAction, string>
> = {
  distance:
    "Click a line to dimension it — or a point, then a point or a line.",
  radius: "Click a circle or arc to dimension it.",
};

/** An armed Dimension holding its first point (SKETCH-POINT-DISTANCE). */
export const DIMENSION_SECOND_PICK_HINT =
  "Click a second point, or a line, to dimension to.";

/**
 * Two points are held: the label follows the pointer and the click that drops
 * it decides the direction, as Fusion's does (`placementDirection`).
 */
export const DIMENSION_PLACE_HINT =
  "Click to place: above or below for horizontal, left or right for vertical, between for aligned. Esc cancels.";

/** How a picked entity is named back to the user ("That is a circle."). */
const ENTITY_KIND_LABEL: Readonly<Record<SketchEntity["kind"], string>> = {
  point: "a point",
  line: "a line",
  circle: "a circle",
  arc: "an arc",
  spline: "a spline",
};

/**
 * What to say when an ARMED dimension verb is handed the wrong thing (DIM-3).
 *
 * NOT the selection-first refusal — "Select one line to dimension." is the exact
 * sentence arming exists to eliminate, and while armed it is also false: the
 * user DID click, and "select" names a step this flow no longer has. Answering
 * a click with it reads as the dead end the fix was supposed to have removed.
 * So the reply names what was picked and repeats the standing instruction,
 * which is the truthful pair: this is not it, here is what is.
 *
 * THE FRAME IS THE EXCEPTION, and for a different reason: the origin and axes
 * are refused as a SUBJECT rather than for their kind (SKETCH-2 — the axis is
 * not yours to move), and that refusal stays true while armed. It is passed
 * through from the verb that owns it rather than re-derived here.
 */
export const wrongPickHint = (
  armed: DimensionPickAction,
  pickedId: string,
  entities: readonly SketchEntity[],
  refusal: string | null,
): string => {
  if (isDatumId(pickedId)) return refusal ?? DIMENSION_PICK_HINT[armed];
  const picked = entities.find((entity) => entity.id === pickedId);
  // An id the buffer cannot resolve names nothing, so say nothing about it and
  // keep asking — better a repeated instruction than an invented noun.
  if (picked === undefined) return DIMENSION_PICK_HINT[armed];
  return `That is ${ENTITY_KIND_LABEL[picked.kind]}. ${DIMENSION_PICK_HINT[armed]}`;
};

/** Two points held, the label not yet placed (`SketchState.dimensionPlace`). */
export interface DimensionPlace {
  a: DimensionPointRef;
  b: DimensionPointRef;
}

/**
 * The click that DROPS a two-point dimension's label: where it lands decides
 * aligned, horizontal or vertical (`placementDirection`), and the editor opens
 * on that dimension — on the existing one if the pair already has it.
 */
export function placeDimensionLabel(
  place: DimensionPlace,
  entities: readonly SketchEntity[],
  constraints: readonly SketchConstraint[],
  at: Point2D,
): {
  dimensionPlace: null;
  dimensionEdit: DimensionEditorTarget | null;
} {
  const byId = new Map(entities.map((e) => [e.id, e]));
  const a = operandPoint(place.a, byId);
  const b = operandPoint(place.b, byId);
  if (a === null || b === null) {
    return { dimensionPlace: null, dimensionEdit: null };
  }
  return {
    dimensionPlace: null,
    dimensionEdit: pointDimensionEditor(
      {
        kind: "point_distance",
        a: place.a,
        b: place.b,
        direction: placementDirection(a, b, at),
      },
      entities,
      constraints,
    ),
  };
}

/**
 * One click while Dimension is ARMED: the finest thing under the pointer, so a
 * click on a corner takes the POINT and one along an edge the line. A first
 * point is held; a second point goes to label placement; a line after a point
 * opens the perpendicular distance; a line or a round alone opens its own
 * dimension, as before. Anything else keeps the verb armed and says why.
 */
export function armedDistanceClick(
  held: readonly DimensionPointRef[],
  pick: SketchPick | undefined,
  entities: readonly SketchEntity[],
  constraints: readonly SketchConstraint[],
): {
  dimensionOperands?: DimensionPointRef[];
  dimensionPick?: null;
  dimensionEdit?: DimensionEditorTarget;
  dimensionPlace?: DimensionPlace;
  hint?: string | null;
} {
  if (pick === undefined) return {}; // empty space: stay armed, keep asking
  if (pick.kind === "point" && held.length === 0) {
    return {
      dimensionOperands: [operandRef(pick)],
      hint: DIMENSION_SECOND_PICK_HINT,
    };
  }
  const picks: SketchPick[] = [
    ...held.map((ref): SketchPick => ({
      kind: "point",
      entity: ref.entity,
      point: ref.point,
    })),
    pick,
  ];
  const result = applyConstraintAction(
    "distance",
    picks,
    entities,
    constraints,
  );
  if (result.outcome === "editor") {
    return {
      dimensionEdit: result.target,
      dimensionPick: null,
      dimensionOperands: [],
      hint: null,
    };
  }
  if (result.outcome === "place") {
    return {
      dimensionPlace: { a: result.a, b: result.b },
      dimensionPick: null,
      dimensionOperands: [],
      hint: DIMENSION_PLACE_HINT,
    };
  }
  const refusal = result.outcome === "hint" ? result.hint : null;
  if (held.length > 0) return { hint: refusal ?? DIMENSION_SECOND_PICK_HINT };
  return {
    hint: wrongPickHint(
      "distance",
      pick.kind === "entity" ? pick.id : pick.entity,
      entities,
      refusal,
    ),
  };
}

/**
 * ARMED IS NEVER SILENT (DIM-3). `dimensionPick` has no surface of its own: the
 * hint is the only thing on screen saying the next canvas click will open a
 * dimension editor rather than select something. Clearing the hint is what an
 * ordinary action DOES when its own message is over — `selectConstraint` and
 * `togglePick` both did, correctly, and both left the verb armed and silent, so
 * the click after them opened an editor with no visible cause.
 *
 * Restoring the prompt at those two call sites would have fixed the two we
 * found and not the third. This is `withSketchHistory`'s argument again: a rule
 * that has to be remembered at every site will be forgotten at one, and the
 * cost here is a UI state that cannot be explained from the screen. So it is an
 * INVARIANT, re-established after every transition — "armed with no hint" is
 * not a state this store can be left in, by any action, present or future.
 *
 * Two things it deliberately does not do: it never overwrites a hint (a site
 * with something more specific to say — the wrong-kind pick — keeps its own),
 * and it never fires for a site that DISARMS, because clearing `dimensionPick`
 * and the prompt together is the arming ending, not going quiet.
 */
export const withArmedPrompt =
  (creator: (set: SketchSet, get: () => SketchState) => SketchState) =>
  (set: SketchSet, get: () => SketchState): SketchState =>
    creator((partial) => {
      set(partial);
      const after = get();
      if (after.dimensionPick === null || after.hint !== null) return;
      set({ hint: DIMENSION_PICK_HINT[after.dimensionPick] });
    }, get);
