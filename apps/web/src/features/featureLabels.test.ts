/**
 * The feature VOCABULARY guard: every feature type the app can author must have
 * both a human label and its own verb glyph in the shared design-system map.
 *
 * This is the drift guard for the DRY rule that landed with UI-W1 — one
 * `VERB_GLYPHS` map read by the command band and the timeline. Without it, a new
 * kernel verb reaches the timeline as a generic blank (`StockIcon`) and a
 * snake_case wire name leaks into the UI, both of which look intentional in a
 * screenshot.
 */
import { StockIcon, VERB_GLYPHS } from "@loft/design";
import { describe, expect, it } from "vitest";

import { BODY_AFFECTING_FEATURE_TYPES } from "./face";
import { featureTypeLabel } from "./featureLabels";

/** Everything a tree row / timeline chip can hold: the body chain + sketch/datum. */
const AUTHORABLE_FEATURE_TYPES: readonly string[] = [
  ...BODY_AFFECTING_FEATURE_TYPES,
  "sketch",
  "datum",
];

describe("verb glyphs", () => {
  it("gives every authorable feature type its own glyph, not the blank", () => {
    const missing = AUTHORABLE_FEATURE_TYPES.filter(
      (type) =>
        VERB_GLYPHS[type] === undefined || VERB_GLYPHS[type] === StockIcon,
    );
    expect(missing).toEqual([]);
  });

  it("covers the band-only commands the same map serves", () => {
    for (const verb of ["import_step", "flat_pattern", "measure"]) {
      expect(VERB_GLYPHS[verb]).toBeDefined();
    }
  });

  it("has nothing to say about a verb the frontend has never met", () => {
    // The fallback is `StockIcon` at the use site — never a wrong verb.
    expect(VERB_GLYPHS["warp_drive"]).toBeUndefined();
  });
});

describe("featureTypeLabel", () => {
  it("de-snakes the sheet-metal wire names", () => {
    expect(featureTypeLabel("sheet_metal_base_flange")).toBe("base flange");
    expect(featureTypeLabel("sheet_metal_edge_flange")).toBe("edge flange");
    expect(featureTypeLabel("sheet_metal_hem")).toBe("hem");
    expect(featureTypeLabel("sheet_metal_corner_relief")).toBe("corner relief");
  });

  it("passes through the types that are already plain words", () => {
    expect(featureTypeLabel("extrude")).toBe("extrude");
    expect(featureTypeLabel("fillet")).toBe("fillet");
  });
});
