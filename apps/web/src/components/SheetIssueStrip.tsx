/**
 * The sheet check strip — the redline slip clipped above the drawing board.
 *
 * Composition MEASURES every pair of placed views and reports a collision or a
 * near-tangency on `ComposedSheet.layout_issues` (audit N2). Every export stamped
 * that banner; the app showed nothing, so an unreadable sheet looked fine right
 * up until a machinist opened the PDF. This is the on-screen half.
 *
 * Design: a checking print comes back from the checker's desk with marks in red
 * down the margin, and that is the vernacular here — a single 2 px drafting-red
 * rule down the left edge (the one bold stroke; boldness stays spent on the
 * sheet itself), a tracked-caps severity stamp per row reusing the shared
 * {@link Stamp} primitive, and the composer's own uppercase sentence in the data
 * face so the words on screen are literally the words on the print. Nothing here
 * is decorative: every row that CAN be fixed in one click carries the action that
 * fixes it (design mandate 3c), and a row that cannot says what to do instead.
 */
import { Stamp } from "@loft/design";

import type { ComposedLayoutIssue, ViewProjection } from "../api/drawings";
import { VIEW_LABEL } from "../drawing/layout";
import { SEVERITY_LABEL, hasLayoutError } from "../drawing/layoutIssues";

export interface SheetIssueStripProps {
  /** The composer's measured issues, in composed order. */
  issues: readonly ComposedLayoutIssue[];
  /** The projections currently carrying a hand-dragged placement — the ONLY ones
   * "return to auto-layout" can act on (an auto-placed pair that still collides
   * needs a bigger sheet or a smaller scale, not another reset). */
  handPlaced: ReadonlySet<ViewProjection>;
  /** Return these views to bounds-aware auto-layout. */
  onAutoPlace: (projections: readonly ViewProjection[]) => void;
  /** A placement write is in flight — the row actions rest. */
  busy?: boolean;
}

/** "Front and Top" / "Front, Top and Right" — a readable list of view names. */
function viewList(projections: readonly ViewProjection[]): string {
  const names = projections.map((p) => VIEW_LABEL[p]);
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export function SheetIssueStrip({
  issues,
  handPlaced,
  onAutoPlace,
  busy = false,
}: SheetIssueStripProps) {
  if (issues.length === 0) return null;
  const errored = hasLayoutError(issues);
  return (
    <div
      data-testid="sheet-issue-strip"
      data-severity={errored ? "error" : "warning"}
      // An outright collision is already wrong and interrupts; a crowded pair is
      // an observation and does not.
      role={errored ? "alert" : "status"}
      aria-label="Sheet layout check"
      className={`w-full max-w-3xl shrink-0 border border-hairline border-l-2 bg-anvil shadow-float ${
        errored ? "border-l-flag" : "border-l-etch"
      }`}
    >
      <header className="flex items-baseline gap-2 border-b border-hairline px-3 py-1.5">
        <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Sheet check
        </h2>
        <span className="grow" />
        <span
          data-testid="sheet-issue-count"
          className="font-data text-2xs tabular-nums text-gauge"
        >
          {issues.length}
        </span>
      </header>
      <ul className="divide-y divide-hairline">
        {issues.map((issue, i) => {
          const fixable = issue.views.filter((view) => handPlaced.has(view));
          return (
            <li
              key={i}
              data-testid="sheet-issue-row"
              data-issue-code={issue.code}
              data-severity={issue.severity}
              className="flex items-center gap-2.5 px-3 py-1.5"
            >
              <Stamp
                tone={issue.severity === "error" ? "flag" : "gauge"}
                data-testid="sheet-issue-severity"
              >
                {SEVERITY_LABEL[issue.severity]}
              </Stamp>
              {/* The composer's sentence, verbatim — the words on screen are the
                  words stamped on the print. */}
              <span
                data-testid="sheet-issue-message"
                className={`grow font-data text-2xs ${
                  issue.severity === "error" ? "text-mist" : "text-gauge"
                }`}
              >
                {issue.message}
              </span>
              {fixable.length > 0 ? (
                <button
                  type="button"
                  disabled={busy}
                  data-testid="sheet-issue-autoplace"
                  aria-label={`Return the ${viewList(fixable)} view${
                    fixable.length > 1 ? "s" : ""
                  } to auto-layout`}
                  onClick={() => onAutoPlace(fixable)}
                  className="shrink-0 rounded-sm px-1.5 py-0.5 font-display text-2xs uppercase tracking-[0.14em] text-brass transition-colors duration-fast hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40"
                >
                  Auto-place
                </button>
              ) : (
                <span
                  data-testid="sheet-issue-advice"
                  className="shrink-0 font-body text-2xs text-gauge"
                >
                  Choose a larger sheet or a smaller scale
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
