// @vitest-environment jsdom
/**
 * `PanelActionCell` is the footer action of every feature editor and every
 * export cell — 12 editors' Create/Save/Cancel plus STEP/STL. It used the native
 * `disabled` attribute with `disabled:pointer-events-none`, which made all of
 * them DISABLED TRAPS: a greyed Create could be neither hovered nor focused, so
 * the reason it was grey had nowhere to live and the user's only recourse was
 * guessing (UI-REVIEW 2026-07-30 P2). These tests pin the fix, including the
 * negative half — a return to the native attribute must fail here.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PanelActionCell } from "./Panel";

afterEach(cleanup);

describe("PanelActionCell — a gated action can explain itself", () => {
  it("stays in the a11y tree, inert, and describes its own gate", () => {
    const onClick = vi.fn();
    render(
      <PanelActionCell
        label="Create"
        caption="Enter"
        data-testid="create"
        disabled
        disabledReason="Pick a face to drill into."
        onClick={onClick}
      />,
    );
    const cell = screen.getByTestId("create");

    // Reachable: `aria-disabled`, never the native attribute (which removes the
    // control from the a11y tree and, with `pointer-events-none`, from hover).
    expect(cell).toHaveAttribute("aria-disabled", "true");
    expect(cell).not.toBeDisabled();
    expect(cell.className).not.toContain("pointer-events-none");

    // Inert: a click (and therefore Enter/Space, which dispatch one) is swallowed.
    fireEvent.click(cell);
    expect(onClick).not.toHaveBeenCalled();

    // Explains itself, to the eye and to a screen reader, without hovering.
    const reason = "Pick a face to drill into.";
    expect(cell).toHaveTextContent(reason);
    const describedBy = cell.getAttribute("aria-describedby");
    expect(describedBy).not.toBeNull();
    expect(document.getElementById(describedBy!)).toHaveTextContent(reason);
    // The reason takes the caption's line: "Enter" is not the useful thing to
    // say about an action that cannot be taken.
    expect(cell).not.toHaveTextContent("Enter");
  });

  it("keeps its caption and stays actionable when it is not gated", () => {
    const onClick = vi.fn();
    render(
      <PanelActionCell
        label="Create"
        caption="Enter"
        data-testid="create"
        disabledReason="never shown"
        onClick={onClick}
      />,
    );
    const cell = screen.getByTestId("create");
    expect(cell).not.toHaveAttribute("aria-disabled");
    expect(cell).toHaveTextContent("Enter");
    expect(cell).not.toHaveTextContent("never shown");
    fireEvent.click(cell);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("preserves a consumer's own aria-describedby alongside the reason", () => {
    render(
      <>
        <span id="outside">Outside note</span>
        <PanelActionCell
          label="STEP"
          data-testid="step"
          disabled
          disabledReason="No body to export yet."
          aria-describedby="outside"
        />
      </>,
    );
    const ids = (
      screen.getByTestId("step").getAttribute("aria-describedby") ?? ""
    ).split(" ");
    expect(ids).toContain("outside");
    expect(ids).toHaveLength(2);
  });
});
