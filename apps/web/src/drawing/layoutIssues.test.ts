/**
 * The banner mirror. These pin the two properties that make the on-screen
 * banner the SAME banner the print carries: the composer's own anchors and
 * sentence are used verbatim (no client re-phrasing), and the overflow rule
 * matches the server's `banner_lines()` — at most `BANNER_MAX_LINES` issues plus
 * a "+N MORE" tail, so a pathological sheet cannot paper itself over. A clean
 * sheet must produce NO lines at all: that is what keeps a clean sheet's
 * exported bytes unchanged by this whole mechanism.
 */
import { describe, expect, it } from "vitest";

import type { ComposedLayoutIssue, ComposedSheet } from "../api/drawings";
import {
  BANNER_LINE_MM,
  BANNER_MAX_LINES,
  bannerLines,
  bannerPrefix,
  hasLayoutError,
} from "./layoutIssues";

function issue(
  severity: ComposedLayoutIssue["severity"],
  message: string,
  y: number,
): ComposedLayoutIssue {
  return {
    code: severity === "error" ? "views_overlap" : "views_crowded",
    severity,
    views: ["front", "top"],
    overlap_x_mm: severity === "error" ? 6.33 : -12,
    overlap_y_mm: severity === "error" ? 60 : -0.7,
    clearance_mm: severity === "error" ? 0 : 0.7,
    message,
    at: { x_mm: 13, y_mm: y },
  };
}

function sheet(issues: ComposedLayoutIssue[]): ComposedSheet {
  // Only `layout_issues` is read; the rest of the composed sheet is irrelevant
  // to the banner, so this cast keeps the fixture to the field under test.
  return { layout_issues: issues } as ComposedSheet;
}

describe("bannerLines", () => {
  it("draws nothing for a clean sheet", () => {
    expect(bannerLines(sheet([]))).toEqual([]);
    expect(bannerLines({} as ComposedSheet)).toEqual([]);
  });

  it("stamps the composer's sentence at the composer's anchor", () => {
    const lines = bannerLines(
      sheet([issue("error", "TOP / ISOMETRIC VIEWS OVERLAP BY 6.33 MM", 15)]),
    );
    expect(lines).toEqual([
      {
        x: 13,
        y: 15,
        text: "LAYOUT ERROR: TOP / ISOMETRIC VIEWS OVERLAP BY 6.33 MM",
        error: true,
      },
    ]);
  });

  it("prefixes a crowded pair as a warning, not an error", () => {
    const [line] = bannerLines(
      sheet([issue("warning", "FRONT / TOP VIEWS CLEAR BY ONLY 0.70 MM", 15)]),
    );
    expect(line?.text.startsWith("LAYOUT WARNING: ")).toBe(true);
    expect(line?.error).toBe(false);
  });

  it("caps the stamped lines and counts the rest", () => {
    const many = Array.from({ length: BANNER_MAX_LINES + 3 }, (_, i) =>
      issue("warning", `ISSUE ${i}`, 15 + i * BANNER_LINE_MM),
    );
    const lines = bannerLines(sheet(many));
    expect(lines).toHaveLength(BANNER_MAX_LINES + 1);
    const tail = lines[lines.length - 1];
    expect(tail?.text).toBe("+3 MORE LAYOUT ISSUE(S)");
    // The tail sits one line-step below the last stamped issue.
    expect(tail?.y).toBeCloseTo(
      15 + (BANNER_MAX_LINES - 1) * BANNER_LINE_MM + BANNER_LINE_MM,
      9,
    );
    // Every hidden issue was a warning, so the tail is not inked as an error.
    expect(tail?.error).toBe(false);
  });

  it("inks the overflow tail red when a HIDDEN issue is a collision", () => {
    const many = [
      ...Array.from({ length: BANNER_MAX_LINES }, (_, i) =>
        issue("warning", `ISSUE ${i}`, 15 + i * BANNER_LINE_MM),
      ),
      issue("error", "HIDDEN COLLISION", 99),
    ];
    const lines = bannerLines(sheet(many));
    expect(lines[lines.length - 1]?.error).toBe(true);
  });
});

describe("bannerPrefix / hasLayoutError", () => {
  it("matches the server's severity prefixes", () => {
    expect(bannerPrefix("error")).toBe("LAYOUT ERROR: ");
    expect(bannerPrefix("warning")).toBe("LAYOUT WARNING: ");
  });

  it("escalates only for a real collision", () => {
    expect(hasLayoutError([])).toBe(false);
    expect(hasLayoutError([issue("warning", "TIGHT", 15)])).toBe(false);
    expect(
      hasLayoutError([
        issue("warning", "TIGHT", 15),
        issue("error", "HIT", 19),
      ]),
    ).toBe(true);
  });
});
