/**
 * FLOW-B3 — what the command band proposes after a feature builds.
 *
 * THE LAW THIS OBEYS (docs/design/DIRECTION-W2-PROPOSALS.md §1, verbatim
 * because three builders are extending one idiom in one wave):
 *
 *   - brass + leader + `Kbd` = an offer you can take right now.
 *   - mist + no leader + no `Kbd` = a name for what is under the pointer.
 *   - band cell + eyebrow + `×` = a held state that renames verbs.
 *
 * This module feeds NONE of those three. It feeds the fourth *density* of the
 * first one, not a fourth vocabulary: a 32px band cell has no room for a leader
 * and a stamped chip, so the band's contribution is the leader's own ANCHOR DOT
 * and nothing else — one mark, two densities (`viewport/SketchProposal.tsx`
 * draws the same dot at r=2 with a carbide halo). It deliberately carries no
 * word, no key chip and no colour of its own; the tool it lands on already has
 * a glyph, a name and a tooltip, and the dot only says "this one next".
 *
 * WHAT IT REFUSES TO DO is the load-bearing half. The table below has one row
 * per REASON, and everything not in it proposes NOTHING. A band that guesses
 * ("after an extrude you probably want a shell") is the templated affordance
 * this wave exists to avoid, and it is worse than silence because a user who
 * follows a wrong proposal once stops reading the right ones. If you are adding
 * a row, write the reason in the table or do not add it.
 *
 * Pure and DOM-free on purpose: the table is the part most likely to rot, so it
 * is unit-testable without a browser (`nextStep.test.ts`).
 */
import { BODY_AFFECTING_FEATURE_TYPES } from "../features/face";
import type { FeatureResponse } from "../api/parts";

/**
 * The band tools that can take the accent, named by the `data-testid` they
 * already answer to — the same vocabulary the e2e suite and the shortcut
 * registry use, so a proposal cannot name a tool that does not exist.
 */
export type NextStepTool =
  | "new-extrude"
  | "new-revolve"
  | "new-fillet"
  | "new-chamfer"
  | "new-hole"
  | "new-edge-flange";

export interface NextStepProposal {
  /**
   * The feature whose landing wrote this proposal. It is the ARM/DISARM
   * IDENTITY, not decoration: the accent is written once per build and never
   * re-armed for the same feature, so the dismissal memory keys on this.
   */
  featureId: string;
  /** Which tool wears the dot (`data-testid`). */
  tool: NextStepTool;
  /** The accented tool's tooltip second line — active voice, <= 33 chars. */
  caption: string;
}

/**
 * The repeat rows: a verb whose SECOND use follows its first often enough that
 * we can name why. One row, one reason — see the direction brief's table.
 *
 * `label` is the band's own word for the tool, lower-cased into the caption, so
 * the proposal speaks the name the button wears rather than a feature type.
 *
 * KEYED BY THE GENERATED UNION, not by `string` (W2 review, finding 5). The
 * keys are feature TYPES, and `FeatureResponse["feature"]["type"]` is a real
 * union that arrives from `packages/contracts` — so with `string` a mistyped
 * key was a row that could never match, and the unit test, using the same
 * literal, could never see it. That is the `extra="ignore"` trap in TypeScript
 * clothing: everything downstream agrees with the wrong input. All six keys
 * check out against `documents.openapi.json`; the union makes the seventh a
 * compile error instead of a silently dead row. `Partial`, because most of the
 * union deliberately proposes nothing, and `noUncheckedIndexedAccess` keeps the
 * `row === undefined` branch below honest either way.
 */
const REPEAT_ROWS: Readonly<
  Partial<
    Record<
      FeatureResponse["feature"]["type"],
      { readonly tool: NextStepTool; readonly label: string }
    >
  >
> = {
  // boss-then-cut is the common pair
  extrude: { tool: "new-extrude", label: "Extrude" },
  revolve: { tool: "new-revolve", label: "Revolve" },
  // measured: two holes is the median case, and today the second shares
  // nothing with the first (flow audit F-6)
  hole: { tool: "new-hole", label: "Hole" },
  // edges are broken in passes, not all at once
  fillet: { tool: "new-fillet", label: "Fillet" },
  chamfer: { tool: "new-chamfer", label: "Chamfer" },
  // a sheet part folds several legs
  sheet_metal_edge_flange: { tool: "new-edge-flange", label: "Edge flange" },
};

/** The first-body row's caption — the one row that changes the verb. */
const FIRST_BODY_CAPTION = "Round the new body's edges";

/** A feature that is actually part of the built tip right now. */
const isLive = (feature: FeatureResponse): boolean =>
  !feature.rolled_back && (feature.feature.suppressed ?? false) !== true;

/**
 * What the band should propose given the current feature tree, or null.
 *
 * Derived from the tree rather than from an event, deliberately: an event needs
 * somewhere to live and something to clear it, and the tree already says which
 * feature landed last. The caller supplies the two things the tree cannot know
 * — whether the proposed tool is actually usable, and whether the user has
 * already answered the proposal (`useNextStepAccent`).
 *
 * `sketch` is never here. B1 owns the sketch -> extrude transition and writes a
 * leader note in the viewport for it; a band dot for the same moment would be
 * the two-dialects failure drawn on screen.
 */
export function nextStepFor(
  features: readonly FeatureResponse[],
): NextStepProposal | null {
  let last: FeatureResponse | undefined;
  let bodyCount = 0;
  for (const feature of features) {
    if (!isLive(feature)) continue;
    last = feature;
    if (BODY_AFFECTING_FEATURE_TYPES.has(feature.feature.type)) bodyCount += 1;
  }
  if (last === undefined) return null;

  const type = last.feature.type;
  // THE FIRST BODY WINS over any repeat row: this is the instant the whole
  // MODIFY group stops being disabled, and a band that quietly unlocks eight
  // tools and says nothing is the flow test failing in its purest form.
  if (BODY_AFFECTING_FEATURE_TYPES.has(type) && bodyCount === 1) {
    return {
      featureId: last.id,
      tool: "new-fillet",
      caption: FIRST_BODY_CAPTION,
    };
  }

  const row = REPEAT_ROWS[type];
  if (row === undefined) return null;
  return {
    featureId: last.id,
    tool: row.tool,
    caption: `Another ${row.label.toLowerCase()} on this body`,
  };
}
