/**
 * The layout-issue helpers the check strip reads. Issues are never stamped on
 * the sheet (BIKE2-DRAWING-SCALE), so what is left to pin is the escalation
 * rule and the severity words.
 */
import { describe, expect, it } from "vitest";

import type { ComposedLayoutIssue } from "../api/drawings";
import { SEVERITY_LABEL, hasLayoutError } from "./layoutIssues";

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

describe("hasLayoutError / SEVERITY_LABEL", () => {
  it("names the severities as the strip's badge reads them", () => {
    expect(SEVERITY_LABEL).toEqual({ error: "ERROR", warning: "WARNING" });
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
