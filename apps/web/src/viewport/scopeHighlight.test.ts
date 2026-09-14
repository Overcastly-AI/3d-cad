import { describe, expect, it } from "vitest";

import { highlightedFeatureIds } from "./scopeHighlight";

describe("highlightedFeatureIds", () => {
  it("uses the tree selection when no command is asking", () => {
    expect(highlightedFeatureIds(null, "f-hole")).toEqual(["f-hole"]);
  });

  it("lights nothing when nothing is selected and no command is asking", () => {
    expect(highlightedFeatureIds(null, null)).toEqual([]);
  });

  it("prefers the open command's scope over the selection", () => {
    // The user selected Hole1, opened Pattern, then re-pointed the command at
    // Hole2. The tint follows the COMMAND — the tree stamp already does.
    expect(highlightedFeatureIds(["f-hole-2"], "f-hole-1")).toEqual([
      "f-hole-2",
    ]);
  });

  it("clears the tint when the open command chose the whole body", () => {
    // THE DEFECT, stated: `[]` is a real answer ("this body"), not an absence,
    // so the selection must NOT show through it. A `[] -> falsy -> fall back`
    // reading of the scope reintroduces REACH-2-FLOW-B exactly.
    expect(highlightedFeatureIds([], "f-hole-1")).toEqual([]);
  });

  it("tints a tip-seeded command with nothing selected", () => {
    // The other half: an editor seeded from the TIP feature has a subject while
    // the tree selection is empty, which selection alone can never express.
    expect(highlightedFeatureIds(["f-tip"], null)).toEqual(["f-tip"]);
  });

  it("carries every id of a multi-feature scope", () => {
    expect(highlightedFeatureIds(["a", "b"], null)).toEqual(["a", "b"]);
  });
});
