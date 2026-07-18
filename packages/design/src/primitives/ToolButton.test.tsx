// @vitest-environment jsdom
/**
 * ToolButton gate-reason accessibility (BACKLOG P2, UR2 QA pass 2026-07-17):
 * a gated tool is `aria-disabled` and its reason `caption` must reach screen
 * readers via `aria-describedby` — not just sighted hover users via the
 * (aria-hidden) tooltip. The description node lives in the DOM permanently
 * (the tooltip hides by opacity), so the association holds without hover.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ToolButton } from "./ToolButton";

const REASON = "Solve a sketch first";

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

  it("has no accessible description when enabled", () => {
    renderTool({ caption: "3 bodies" });
    const button = screen.getByRole("button", { name: "Extrude — E" });

    expect(button).not.toHaveAttribute("aria-disabled");
    expect(button).not.toHaveAttribute("aria-describedby");
    expect(button).not.toHaveAccessibleDescription();
  });

  it("has no dangling aria-describedby when disabled without a caption", () => {
    renderTool({ disabled: true });
    const button = screen.getByRole("button", { name: "Extrude — E" });

    expect(button).toHaveAttribute("aria-disabled", "true");
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

  it("does not change the visual tooltip or test hooks", () => {
    renderTool({ disabled: true, caption: REASON });
    const button = screen.getByTestId("tool-extrude");

    // Tooltip stays aria-hidden (name announced once) and always mounted.
    const tooltip = button.querySelector('[aria-hidden="true"].absolute');
    expect(tooltip).not.toBeNull();
    expect(tooltip).toHaveTextContent(REASON);
  });
});
