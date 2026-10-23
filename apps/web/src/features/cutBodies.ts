/**
 * OBJECTS TO CUT (CUT-OBJECTS-TO-CUT): which bodies an extrude, revolve,
 * sweep, loft or pipe cut removes material from, as Fusion 360's Objects To
 * Cut and SolidWorks' Feature Scope choose them.
 *
 * The wire (`cut_bodies`, docs/RESEARCH.md §28) has three readings:
 *
 *  · `"all"`: every body the tool meets, found on each rebuild. What a NEW
 *    cut stores, so a notch drawn across a plate and three studs cuts all four.
 *  · a list of bodies, each by its base feature: exactly those. What a cut
 *    stores once the modeller unticks a body in the list; it stays a list
 *    (re-ticking adds the body back) until "Cut every body it meets".
 *  · absent: the ACTIVE body only. Every cut saved before Objects To Cut has
 *    none and rebuilds as it always did; a Save keeps it absent until the
 *    modeller asks for every body.
 *
 * Pure functions, shared by the five cut editors and their tests.
 */
import type { ExtrudeParams } from "../api/parts";
import { type BodyInfo, bodyPickLabel } from "./bodies";

/** Objects To Cut on the wire: every body met, or the listed bodies. */
export type CutBodies = NonNullable<ExtrudeParams["cut_bodies"]>;

/** One listed body: its base feature, as a feature reference. */
type BodyRef = Exclude<CutBodies, "all">[number];

/**
 * A form's Objects To Cut. `undefined` is a cut stored without the field (the
 * active body only); an empty list is the transient "nothing ticked", which
 * blocks Save ({@link cutBodiesBlocker}).
 */
export type CutBodiesChoice = CutBodies | undefined;

/** What a new cut cuts: every body its tool meets. */
export const NEW_CUT_BODIES: CutBodies = "all";

/**
 * The choice an edit opens with. A stored cut keeps exactly what it stored
 * (absent stays absent, so a no-op Save changes nothing); a stored ADD seeds
 * the new-cut default, which applies if the modeller switches it to Cut.
 */
export function seedCutBodies(params: {
  operation: "add" | "cut";
  cut_bodies?: CutBodies | null;
}): CutBodiesChoice {
  if (params.operation !== "cut") return NEW_CUT_BODIES;
  return params.cut_bodies ?? undefined;
}

/**
 * The `cut_bodies` key a Save writes: none on an add (the wire refuses one
 * there) or on a cut stored without it, else the choice.
 */
export function cutBodiesField(
  operation: "add" | "cut",
  choice: CutBodiesChoice,
): { cut_bodies?: CutBodies } {
  if (operation !== "cut" || choice === undefined) return {};
  return { cut_bodies: choice };
}

/** Why Save is blocked by the list, or null (REASON-GATE-1's budget). */
export function cutBodiesBlocker(
  operation: "add" | "cut",
  choice: CutBodiesChoice,
): string | null {
  return operation === "cut" && Array.isArray(choice) && choice.length === 0
    ? "Tick a body under Objects To Cut."
    : null;
}

/** One row of the Objects To Cut list. */
export interface CutBodyRow {
  /** The body's identity, its base feature id. */
  id: string;
  /** As the Combine pickers name a body: "Body 3 · Wall 1". */
  label: string;
  checked: boolean;
}

/**
 * The list's rows, in body (tree) order: the bodies the cut met on its last
 * rebuild (`FeatureResult.cut_bodies`) and any body it lists, each ticked
 * when the choice cuts it. Empty before the cut has been built (a new cut),
 * when the dialog says "every body it meets" instead.
 */
export function cutBodyRows(
  choice: CutBodiesChoice,
  met: readonly string[] | null,
  bodies: readonly BodyInfo[],
): CutBodyRow[] {
  const listed = Array.isArray(choice) ? choice.map((r) => r.feature_id) : [];
  const shown = new Set([...(met ?? []), ...listed]);
  return bodies
    .filter((body) => shown.has(body.baseFeatureId))
    .map((body) => ({
      id: body.baseFeatureId,
      label: bodyPickLabel(body),
      checked: choice === "all" || listed.includes(body.baseFeatureId),
    }));
}

/**
 * The choice after (un)ticking row `id`: the ticked bodies, in body order.
 *
 * Never `"all"` unless the choice already was: the rows are only the bodies
 * the cut met plus the listed ones, so a body excluded earlier (and no longer
 * met) is not a row, and "every row ticked" does not mean "every body". Turning
 * a narrowed cut back into `"all"` is its own action ("Cut every body it
 * meets"), never a side effect of re-ticking a row.
 */
export function toggleCutBody(
  choice: CutBodiesChoice,
  rows: readonly CutBodyRow[],
  id: string,
  checked: boolean,
): CutBodies {
  const ticked = rows
    .filter((row) => (row.id === id ? checked : row.checked))
    .map((row) => row.id);
  if (choice === "all" && ticked.length === rows.length) return "all";
  return ticked.map((featureId): BodyRef => ({
    kind: "feature",
    feature_id: featureId,
  }));
}
