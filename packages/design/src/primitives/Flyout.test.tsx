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

describe("Flyout rows — availability", () => {
  function renderAvailability() {
    return render(
      <Flyout
        label="Dimension"
        icon={<svg aria-hidden />}
        data-testid="constraint-group-dimensional"
        items={[
          {
            key: "distance",
            icon: <svg aria-hidden />,
            label: "Distance",
            shortcut: "D",
            available: true,
            requires: "a line",
            "aria-label": "Distance dimension (D, on one selected line)",
            onSelect: () => undefined,
          },
          {
            key: "angle",
            icon: <svg aria-hidden />,
            label: "Angle",
            shortcut: "A",
            available: false,
            requires: "2 non-parallel lines",
            "aria-label":
              "Angle dimension (A, on two selected non-parallel lines)",
            onSelect: () => undefined,
          },
          {
            key: "legacy",
            icon: <svg aria-hidden />,
            label: "Legacy",
            onSelect: () => undefined,
          },
        ]}
      />,
    );
  }

  it("says what an unreachable row needs, and stays silent on a live one", () => {
    renderAvailability();
    fireEvent.click(screen.getByTestId("constraint-group-dimensional"));

    const angle = screen.getByRole("menuitem", { name: /^Angle dimension/ });
    expect(angle).toHaveTextContent("needs 2 non-parallel lines");

    const distance = screen.getByRole("menuitem", {
      name: /^Distance dimension/,
    });
    expect(distance).not.toHaveTextContent("needs");
  });

  /**
   * The requirement rides the ACCESSIBLE NAME too. `aria-label` replaces a
   * button's inner text wholesale, so a visible "needs …" line under an
   * aria-labelled row is invisible to a screen reader — and availability's
   * only other channel is the glyph's colour, which is no channel at all
   * (WCAG 1.4.1). Without this the feature is sighted-only.
   */
  it("carries the requirement in the accessible name, not just the ink", () => {
    renderAvailability();
    fireEvent.click(screen.getByTestId("constraint-group-dimensional"));
    expect(
      screen.getByRole("menuitem", {
        name: "Angle dimension (A, on two selected non-parallel lines) — needs 2 non-parallel lines",
      }),
    ).toBeInTheDocument();
  });

  /**
   * An unavailable row is CLICKABLE on purpose. Disabling it would answer a
   * user who reached for the verb with nothing at all — the dead end the whole
   * offer/catalogue split exists to remove. Clicking runs the verb, which then
   * says what it needs in its own words.
   */
  it("leaves an unavailable row enabled — no dead end", () => {
    renderAvailability();
    fireEvent.click(screen.getByTestId("constraint-group-dimensional"));
    const angle = screen.getByRole("menuitem", { name: /^Angle dimension/ });
    expect(angle).toBeEnabled();
    expect(angle).toHaveAttribute("data-available", "false");
  });

  it("leaves a row that never opted in untouched", () => {
    renderAvailability();
    fireEvent.click(screen.getByTestId("constraint-group-dimensional"));
    const legacy = screen.getByRole("menuitem", { name: "Legacy" });
    expect(legacy).not.toHaveAttribute("data-available");
    expect(legacy).not.toHaveTextContent("needs");
  });
});
