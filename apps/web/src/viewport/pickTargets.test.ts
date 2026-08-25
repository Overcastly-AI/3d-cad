import { describe, expect, it } from "vitest";

import { NO_PICK_TARGETS, pickRefusal } from "./pickTargets";

/**
 * PICK-2. The predicate that decides whether a pick may be armed at all.
 *
 * The distinction these tests exist to pin down is between the two ways a pick
 * can have no targets, because they need OPPOSITE instructions: a sketch-only
 * part needs "add a body-affecting feature", and a part whose extrude is right
 * there in the tree but did not build needs "clear the error". The second used
 * to be told the first, which is a tool arguing with what the user can see.
 */
describe("pickRefusal", () => {
  const NO_BODY = "Add a feature that creates a body before drilling a hole.";

  it("allows the pick when the evaluation published a body", () => {
    expect(
      pickRefusal({ hasPickTargets: true, hasBodyFeature: true }, NO_BODY),
    ).toBeNull();
  });

  it("names the missing feature on a part that has never had a body", () => {
    expect(
      pickRefusal({ hasPickTargets: false, hasBodyFeature: false }, NO_BODY),
    ).toBe(NO_BODY);
  });

  it("points at the failing build when a body feature exists but built nothing", () => {
    expect(
      pickRefusal({ hasPickTargets: false, hasBodyFeature: true }, NO_BODY),
    ).toBe(NO_PICK_TARGETS);
  });

  it("never tells a part that HAS a body feature to add one", () => {
    // The founder-visible half of the defect: the repair affordance is offered
    // ON a failed build, so this is the only branch that state can reach.
    const refusal = pickRefusal(
      { hasPickTargets: false, hasBodyFeature: true },
      NO_BODY,
    );
    expect(refusal).not.toBeNull();
    expect(refusal).not.toContain("Add a feature");
  });

  it("states both what happened and what to do about it", () => {
    // Failure copy is direction, not mood (frontend-design skill): the sentence
    // has to carry the action, or the dead end is merely better labelled.
    expect(NO_PICK_TARGETS).toContain("no built body");
    expect(NO_PICK_TARGETS).toContain("feature tree");
  });
});
