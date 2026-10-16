/**
 * The sheet's layout issues, as the app shows them (audit N2).
 *
 * Composition measures every pair of placed views and reports a collision
 * (`views_overlap`, an error) or a near-tangency (`views_crowded`, a warning),
 * and every view against the drafting border (`off_sheet`, an error), on
 * {@link ComposedSheet.layout_issues}. The check strip beside the sheet lists
 * them, each with its code, its views and the server's own sentence
 * (`issue.message`; there is deliberately no second sentence table on this
 * side of the wire).
 *
 * They are never printed ON the drawing: the banner the sheet and its exports
 * used to stamp in red put error text on the paper (BIKE2-DRAWING-SCALE). As in
 * SolidWorks and Fusion, a layout problem is the application's to report and
 * the drawing carries only the drawing.
 */
import type { ComposedLayoutIssue } from "../api/drawings";

/** The severity word, tracked-caps — the strip's badge. */
export const SEVERITY_LABEL: Record<ComposedLayoutIssue["severity"], string> = {
  error: "ERROR",
  warning: "WARNING",
};

/** True when any issue is an error (a collision or a view off the sheet, not
 * merely a crowded pair) — the strip escalates to `role="alert"` only for
 * something already wrong. */
export function hasLayoutError(
  issues: readonly ComposedLayoutIssue[],
): boolean {
  return issues.some((issue) => issue.severity === "error");
}
