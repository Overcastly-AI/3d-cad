/**
 * WHY a feature editor's commit action is currently gated — one sentence that
 * names the field AND the way out — or `null` when it can be taken.
 *
 * THE DISABLED SAVE IS THE SUBJECT, not a by-product. `PanelActionCell` has
 * carried `disabledReason` since UI-REVIEW 2026-07-30 P1, and until REASON-GATE-1
 * exactly two of the seventeen editors passed one: a user who reached a grey
 * Create in the other fifteen got `aria-disabled="true"`, an empty caption line,
 * and no way to tell "not yet" from "not ever" (design mandate: no dead ends, no
 * ambiguous exits). The toolbar tier had solved this long ago — 41 of 43 gated
 * `ToolButton`s carry a gate-aware caption — so this was an unfinished rollout,
 * not an open design question.
 *
 * THE SHAPE THAT MAKES IT DURABLE (from `hemSubmitBlocker`, HEM-1B). Every
 * editor's `canSubmitX` is now DEFINED as `xSubmitBlocker(...) === null`, so the
 * gate and its explanation are one computation. A rollout that passed a reason
 * ALONGSIDE an independently-computed boolean would drift the first time somebody
 * edited one and not the other — fifteen fresh chances for a grey cell to go
 * silent again. Defining one in terms of the other makes that unreachable rather
 * than merely fixed.
 *
 * WHY THE 48-CHARACTER BUDGET IS A HARD RULE AND NOT A STYLE NOTE.
 * `PanelActionCell` renders the reason in the footer cell it explains, which is
 * HALF an editor card wide — about 19 characters a line at the data face. HEM-1B
 * measured a 74-character first draft at FIVE wrapped lines, eating the card it
 * was meant to unblock. So the division of labour is: the FIELD states the rule
 * it broke (`radiusError` and friends render inline, in red, on the input) and
 * the Save cell states what to do next. One job each.
 */

/** The widest a reason may be — see the module header for the measurement. */
export const MAX_BLOCKER_CHARS = 48;

/**
 * The reason a numeric field is holding a commit action, or null when it parses.
 *
 * Blank and wrong are DIFFERENT user situations and get different sentences: an
 * empty field is a missing answer ("Enter the …"), anything else is an answer the
 * parser rejected ("Check the …") — and in the second case the field is already
 * red with the rule, so the cell points at it instead of repeating it.
 *
 * `noun` is the field's own LABEL, lower-cased ("bend radius", "gauge"), so the
 * sentence names the control the user is looking at rather than an internal
 * concept. Fifteen editors reach for this pair, which is what earned the helper.
 */
export function fieldBlocker(
  input: string,
  parsed: number | null,
  noun: string,
): string | null {
  if (parsed !== null) return null;
  return input.trim() === "" ? `Enter the ${noun}.` : `Check the ${noun}.`;
}
