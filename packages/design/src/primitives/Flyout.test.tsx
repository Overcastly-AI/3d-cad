// @vitest-environment jsdom
/**
 * Flyout — the band's LABEL-TIER contract (QA-R1, 2026-08-27).
 *
 * The functional gate for QA-R1 is `apps/web/e2e/qa-reach-batch.spec.ts`,
 * which measures real boxes against a real 1280/1366 window; jsdom has no
 * layout and no Tailwind, so it cannot see width. What it CAN hold is the
 * structural contract the measurement depends on: the trigger label opts into
 * the band's `data-labels` mechanism, and a shed trigger still names itself.
 *
 * Both were absent before QA-R1 and the absence was silent — the band measured
 * itself into the "icon" tier and saved 0 px, because the only labelled control
 * on the sketch strip was a `Flyout`, which ignored the tier.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Flyout } from "./Flyout";

/** The ancestor-attribute selector `CommandBand`'s probe drives. */
const SHED = "[[data-labels=off]_&]:hidden";

function renderFlyout() {
  return render(
    <Flyout
      label="Relational"
      icon={<svg aria-hidden />}
      eyebrow="Relational"
      data-testid="constraint-group-relational"
      items={[
        {
          key: "coincident",
          icon: <svg aria-hidden />,
          label: "Coincident",
          shortcut: "C",
          onSelect: () => undefined,
        },
      ]}
    />,
  );
}

afterEach(cleanup);

describe("Flyout trigger — measured label tier", () => {
  it("lets the band shed the trigger label, like every other band control", () => {
    renderFlyout();
    const trigger = screen.getByTestId("constraint-group-relational");
    const label = Array.from(trigger.querySelectorAll("span")).find(
      (span) => span.textContent === "Relational",
    );
    expect(label, "the trigger renders its group name").toBeDefined();
    expect(
      (label as HTMLElement).className,
      "the trigger label must collapse under an ancestor's data-labels=off",
    ).toContain(SHED);
  });

  it("keeps naming itself once shed — icon, caret and a stamp", () => {
    renderFlyout();
    const trigger = screen.getByTestId("constraint-group-relational");
    // The stamp is the pointer's name for a label-less trigger; aria-label is
    // assistive tech's, and is unconditional.
    expect(trigger.querySelector("[data-tooltip]")).toHaveTextContent(
      "Relational",
    );
    expect(trigger).toHaveAttribute("aria-label", "Relational");
  });

  it("drops the stamp while the menu is open (it would cover the menu)", () => {
    renderFlyout();
    const trigger = screen.getByTestId("constraint-group-relational");
    fireEvent.click(trigger);
    expect(screen.getByRole("menu")).toBeInTheDocument();
    expect(trigger.querySelector("[data-tooltip]")).toBeNull();
  });
});
