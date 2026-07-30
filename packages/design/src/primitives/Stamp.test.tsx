/**
 * The Stamp exists so "we measured this" and "we could not" can never be drawn
 * the same way. Both facts are one short word in tracked caps, so the ONLY
 * thing carrying the difference is the rule style and the ink — which makes
 * these two assertions the primitive's whole contract.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Stamp } from "./Stamp";

describe("Stamp", () => {
  it("inks an established exception and marks its tone", () => {
    render(
      <Stamp tone="flag" data-testid="s">
        Broken
      </Stamp>,
    );
    const stamp = screen.getByTestId("s");
    expect(stamp).toHaveAttribute("data-stamp", "flag");
    expect(stamp.className).toContain("border-flag");
    expect(stamp.className).toContain("text-flag");
    expect(stamp.className).not.toContain("border-dashed");
  });

  it("draws an indeterminate fact as a phantom rule, never in an alarm ink", () => {
    render(
      <Stamp tone="flag" indeterminate data-testid="s">
        Was broken
      </Stamp>,
    );
    const stamp = screen.getByTestId("s");
    expect(stamp).toHaveAttribute("data-stamp", "indeterminate");
    expect(stamp.className).toContain("border-dashed");
    expect(stamp.className).toContain("text-gauge");
    // `tone` is deliberately overridden: an unknown is never coloured as if it
    // were known, even when a caller passes the tone of the raw record.
    expect(stamp.className).not.toContain("text-flag");
    expect(stamp.className).not.toContain("border-flag");
  });
});
