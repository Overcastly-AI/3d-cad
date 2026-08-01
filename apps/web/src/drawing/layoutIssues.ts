/**
 * The sheet's layout-issue BANNER — the DOM twin of the server composer's
 * `banner_lines()` (audit N2).
 *
 * Composition measures every pair of placed views and reports a collision
 * (`views_overlap`, an error) or a near-tangency (`views_crowded`, a warning) on
 * {@link ComposedSheet.layout_issues}. All three server serializers stamp those
 * issues as a banner on the print; the app rendered NOTHING, so an overlapping
 * sheet looked fine on screen and only announced itself once exported — the
 * product telling the truth on the print and not on the screen (audit N1/N2
 * frontend half).
 *
 * This module is the ONE place the client decides which issues are stamped and
 * what each line says, mirroring the server EXACTLY (same max-line cap, same
 * "+N MORE" tail, same severity prefix), the way `titleBlock.ts` mirrors the
 * title-block field rows. The PHRASE itself is always the server's
 * (`issue.message`) — there is deliberately no second sentence table on this
 * side of the wire. Both client surfaces read from here: the on-paper SVG banner
 * (so the sheet you see is the sheet you export — `exportSvg.ts` serializes the
 * live node) and the DOM check strip beside it.
 */
import type { ComposedLayoutIssue, ComposedSheet } from "../api/drawings";

/** The severity word, tracked-caps — the machinist reads severity first.
 * Mirrors the server's `_BANNER_PREFIX` keys; the prefix below is built from it
 * so the strip's badge and the stamped line can never drift apart. */
export const SEVERITY_LABEL: Record<ComposedLayoutIssue["severity"], string> = {
  error: "ERROR",
  warning: "WARNING",
};

/** Stamped-line prefix per severity — the server's `_BANNER_PREFIX` verbatim. */
export function bannerPrefix(
  severity: ComposedLayoutIssue["severity"],
): string {
  return `LAYOUT ${SEVERITY_LABEL[severity] ?? ""}: `;
}

/** Stamped banner lines before the "+N MORE" tail — the server's
 * `_BANNER_MAX_LINES`, so a pathological sheet cannot paper itself over. */
export const BANNER_MAX_LINES = 4;

/** Baseline step (mm) between stamped banner lines — the server's
 * `_BANNER_LINE_MM`. Only used for the overflow tail; every real issue carries
 * its own composer-given anchor. */
export const BANNER_LINE_MM = 4.2;

/** Banner text height (mm) — the server's `_BANNER_TEXT_MM`, so the on-screen
 * banner and the exported SVG/PDF/DXF read one height (the cross-renderer rule
 * `titleBlock.ts` / `drawing.noteTextMm` carry). */
export const BANNER_TEXT_MM = 2.8;

/** One stamped banner line: sheet-mm position, the text, and its severity. */
export interface BannerLine {
  x: number;
  y: number;
  text: string;
  /** True for an overlap (drafting red); false for a crowding warning. */
  error: boolean;
}

/**
 * The sheet's banner as stamped text lines — the first {@link BANNER_MAX_LINES}
 * issues at their composed anchors, plus a "+N MORE" tail when there are more.
 * Empty for a clean sheet, which is why a clean sheet draws no banner ink at all.
 */
export function bannerLines(composed: ComposedSheet): BannerLine[] {
  const issues = composed.layout_issues ?? [];
  const lines: BannerLine[] = issues
    .slice(0, BANNER_MAX_LINES)
    .map((issue) => ({
      x: issue.at.x_mm,
      y: issue.at.y_mm,
      text: bannerPrefix(issue.severity) + issue.message,
      error: issue.severity === "error",
    }));
  const remaining = issues.length - lines.length;
  const last = lines[lines.length - 1];
  if (remaining > 0 && last !== undefined) {
    lines.push({
      x: last.x,
      y: last.y + BANNER_LINE_MM,
      text: `+${remaining} MORE LAYOUT ISSUE(S)`,
      error: issues
        .slice(BANNER_MAX_LINES)
        .some((issue) => issue.severity === "error"),
    });
  }
  return lines;
}

/** True when any issue is an outright collision (not merely a crowded pair) —
 * the strip escalates to `role="alert"` only for something already wrong. */
export function hasLayoutError(
  issues: readonly ComposedLayoutIssue[],
): boolean {
  return issues.some((issue) => issue.severity === "error");
}
