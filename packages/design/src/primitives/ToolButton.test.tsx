// @vitest-environment jsdom
/**
 * ToolButton caption accessibility. A tool's `caption` must reach screen
 * readers via `aria-describedby` — not just sighted hover users via the
 * (aria-hidden) tooltip. The description node lives in the DOM permanently
 * (the tooltip hides by opacity), so the association holds without hover.
 *
 * Originally this held only for the DISABLED case (BACKLOG P2, UR2 QA pass
 * 2026-07-17). A11Y-TOOLBTN-1: it must hold for the ENABLED case too, where the
 * caption is a qualifier ("marks the file partial") rather than a gate reason
 * ("Solve a sketch first"). Both directions are asserted here, because a guard
 * written against one failure tends to encode that failure's direction.
 *
 * MECHANISM — why these assertions can see the failure they stand for:
 * `toHaveAccessibleDescription` delegates to `dom-accessibility-api`'s
 * `computeAccessibleDescription` (verified in jest-dom 6.9.1's dist), i.e. it
 * RESOLVES `aria-describedby` against the document and computes the referenced
 * nodes' text the way an AT would. `toHaveAttribute("aria-describedby", …)`
 * would pass on an id that resolves to nothing, so it is never the assertion
 * here — it appears only alongside a resolution check, never instead of one.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ToolButton } from "./ToolButton";

/** A gate reason: why you CANNOT. Rendered while `disabled`. */
const REASON = "Solve a sketch first";
/**
 * A qualifier: what happens if you DO. Rendered while enabled. Deliberately
 * shares no words with the label or the shortcut, so an implementation that
 * folded it into the accessible name could not satisfy a description assertion
 * by accident — the two channels are separable by this string alone.
 */
const QUALIFIER = "marks the file partial";

function renderTool(props: Partial<Parameters<typeof ToolButton>[0]> = {}) {
  return render(
    <ToolButton
      icon={<svg aria-hidden />}
      label="Extrude"
      shortcut="E"
      data-testid="tool-extrude"
      {...props}
    />,
  );
}

afterEach(cleanup);

describe("ToolButton gate-reason description", () => {
  it("exposes the caption as the accessible description while disabled", () => {
    renderTool({ disabled: true, caption: REASON });
    const button = screen.getByRole("button", { name: "Extrude — E" });

    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).toHaveAccessibleDescription(REASON);

    // The description node must exist without hover — resting DOM, no events.
    const id = button.getAttribute("aria-describedby");
    expect(id).toBeTruthy();
    expect(document.getElementById(id as string)).toHaveTextContent(REASON);
  });

  it("exposes an ENABLED button's qualifier as the accessible description", () => {
    // A11Y-TOOLBTN-1. This is the case the primitive used to drop on the floor:
    // the tool works, and the caption says what the click WOULD DO. Reddens
    // against `hasCaption = isDisabled && Boolean(caption)`.
    renderTool({ caption: QUALIFIER });
    const button = screen.getByRole("button", { name: "Extrude — E" });

    expect(button).toBeEnabled();
    expect(button).not.toHaveAttribute("aria-disabled");
    expect(button).toHaveAccessibleDescription(QUALIFIER);

    // Same resting-DOM guarantee as the disabled case: no hover, no events.
    const id = button.getAttribute("aria-describedby");
    expect(id).toBeTruthy();
    expect(document.getElementById(id as string)).toHaveTextContent(QUALIFIER);
  });

  it("keeps the qualifier OUT of the accessible name", () => {
    // The workaround this fix retires (ExportToolGroup's `aria-label` fold) put
    // the qualifier in the NAME, which makes one control answer to two names as
    // its state changes. Name and description are separate channels; assert the
    // name is untouched, or the next fix will "solve" this by folding again.
    renderTool({ caption: QUALIFIER });
    const button = screen.getByTestId("tool-extrude");

    expect(button).toHaveAccessibleName("Extrude — E");
    expect(button).toHaveAccessibleDescription(QUALIFIER);
  });

  it("has no dangling aria-describedby when disabled without a caption", () => {
    renderTool({ disabled: true });
    const button = screen.getByRole("button", { name: "Extrude — E" });

    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).not.toHaveAttribute("aria-describedby");
    expect(button).not.toHaveAccessibleDescription();
  });

  it("has no dangling aria-describedby when enabled without a caption", () => {
    // The symmetric over-correction: wiring the id unconditionally would point
    // at a node that is never rendered. The id must track the caption NODE, not
    // the disabled state and not nothing.
    renderTool();
    const button = screen.getByRole("button", { name: "Extrude — E" });

    expect(button).toBeEnabled();
    expect(button).not.toHaveAttribute("aria-describedby");
    expect(button).not.toHaveAccessibleDescription();
  });

  it("preserves a consumer-provided aria-describedby alongside the reason", () => {
    render(
      <>
        <span id="extra">Extra context</span>
        <ToolButton
          icon={<svg aria-hidden />}
          label="Extrude"
          disabled
          caption={REASON}
          aria-describedby="extra"
        />
      </>,
    );
    const button = screen.getByRole("button", { name: "Extrude" });

    expect(button).toHaveAccessibleDescription(`Extra context ${REASON}`);
  });

  it("preserves a consumer-provided aria-describedby while ENABLED too", () => {
    // Newly reachable: before A11Y-TOOLBTN-1 an enabled button never joined a
    // second id, so the ordering (consumer's first, caption second) was only
    // ever exercised in the disabled case.
    render(
      <>
        <span id="extra">Extra context</span>
        <ToolButton
          icon={<svg aria-hidden />}
          label="Extrude"
          caption={QUALIFIER}
          aria-describedby="extra"
        />
      </>,
    );
    const button = screen.getByRole("button", { name: "Extrude" });

    expect(button).toBeEnabled();
    expect(button).toHaveAccessibleDescription(`Extra context ${QUALIFIER}`);
  });

  it("does not change the visual tooltip or test hooks", () => {
    renderTool({ disabled: true, caption: REASON });
    const button = screen.getByTestId("tool-extrude");

    // Tooltip stays aria-hidden (name announced once) and always mounted.
    const tooltip = button.querySelector('[aria-hidden="true"].absolute');
    expect(tooltip).not.toBeNull();
    expect(tooltip).toHaveTextContent(REASON);
  });
});

/**
 * The band's NEXT-STEP OFFER (`proposal`). The browser proves what is PAINTED
 * and what a real pointer hits (`apps/web/e2e/next-step-label.spec.ts`); these
 * pin the structural half, which is where a refactor would quietly break it.
 */
describe("ToolButton next-step offer", () => {
  const CAPTION = "Round the new body's edges";
  const offerOf = (button: HTMLElement) =>
    button.querySelector<HTMLElement>("[data-testid='next-step-label']");
  const partsOf = (button: HTMLElement) => [
    offerOf(button),
    button.querySelector("[data-next-step-leader]"),
    button.querySelector("[data-testid='next-step-dot']"),
  ];

  it("draws nothing of the offer on an ordinary tool", () => {
    renderTool({ caption: QUALIFIER });
    const button = screen.getByTestId("tool-extrude");
    for (const part of partsOf(button)) expect(part).toBeNull();
  });

  it("names the offer — NEXT, the tool's own name and key, over the caption", () => {
    renderTool({ caption: CAPTION, proposal: "resting" });
    const button = screen.getByTestId("tool-extrude");
    // One source: the words are the tool's own `label` and `shortcut` plus the
    // caption the caller already passes. Nothing here is a second string table.
    expect(offerOf(button)).toHaveTextContent(`NextExtrudeE${CAPTION}`);
    expect(
      button.querySelector("[data-testid='next-step-dot']"),
    ).not.toBeNull();
  });

  it("REPLACES the tooltip: one stamp per tool, never two", () => {
    renderTool({ caption: CAPTION, proposal: "resting" });
    const button = screen.getByTestId("tool-extrude");
    expect(button.querySelectorAll("[data-tooltip]")).toHaveLength(1);
    expect(button.querySelector("[data-tooltip]")).toBe(offerOf(button));
  });

  it("keeps the caption as the description, and is silent itself", () => {
    renderTool({ caption: CAPTION, proposal: "announced" });
    const button = screen.getByRole("button", { name: "Extrude — E" });
    // The words reach a screen reader exactly as before the offer existed…
    expect(button).toHaveAccessibleDescription(CAPTION);
    // …and the drawn note does not announce itself a second time.
    for (const part of partsOf(button)) {
      expect(part).toHaveAttribute("aria-hidden", "true");
    }
  });

  it("can take no pointer: every part of the note is pointer-events-none", () => {
    renderTool({ caption: CAPTION, proposal: "announced" });
    for (const part of partsOf(screen.getByTestId("tool-extrude"))) {
      expect(part?.getAttribute("class") ?? "").toContain(
        "pointer-events-none",
      );
    }
  });

  it("is up unprompted only while announced; otherwise on hover/focus", () => {
    const { rerender } = renderTool({ caption: CAPTION, proposal: "resting" });
    const resting = offerOf(screen.getByTestId("tool-extrude"))!;
    expect(resting).toHaveAttribute("data-announced", "false");
    expect(resting.className).toContain("opacity-0");
    expect(resting.className).toContain("group-hover/tt:opacity-100");
    expect(resting.className).toContain("group-focus-visible/tt:opacity-100");

    rerender(
      <ToolButton
        icon={<svg aria-hidden />}
        label="Extrude"
        shortcut="E"
        data-testid="tool-extrude"
        caption={CAPTION}
        proposal="announced"
      />,
    );
    const said = offerOf(screen.getByTestId("tool-extrude"))!;
    expect(said).toHaveAttribute("data-announced", "true");
    // Exclusive branches: never both, so stylesheet order cannot decide it.
    expect(said.className).toContain("opacity-100");
    expect(said.className).not.toContain("opacity-0");
  });
});
