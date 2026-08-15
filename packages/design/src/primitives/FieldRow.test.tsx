// @vitest-environment jsdom
/**
 * FieldRow (FB-19) — the dense field cell. Two contracts are worth pinning in
 * jsdom, because both are invisible in a screenshot:
 *
 *  1. The caption is a REAL label. Setting a label beside a control instead of
 *     above it is a layout change only if the `for`/`id` wiring survives it; if
 *     it does not, the control silently loses its accessible name and the
 *     density pass has broken the product for looks (mandate #5).
 *  2. THE NOTE RULE. A row may hide an explanation behind the balloon; it may
 *     never hide a warning. `noteTone="flag"` must therefore pin the note open
 *     AND drop the toggle — a warning behind a click is the defect this rule
 *     exists to prevent.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { FieldRow } from "./FieldRow";

afterEach(cleanup);

describe("FieldRow caption", () => {
  it("labels the control it names", () => {
    render(
      <FieldRow label="Distance" htmlFor="d1">
        <input id="d1" defaultValue="10" />
      </FieldRow>,
    );
    expect(screen.getByLabelText("Distance")).toHaveValue("10");
  });

  it("renders no caption column when the row is label-less", () => {
    const { container } = render(
      <FieldRow>
        <button type="button">Add</button>
      </FieldRow>,
    );
    // The caption column is a token width; a label-less row must not leave an
    // empty one behind, because that width is exactly what the two-toggle row
    // is spending on its labels.
    expect(container.querySelector(".w-field-label")).toBeNull();
  });

  it("wires an error message to the id the caller describes the control with", () => {
    render(
      <FieldRow label="Distance" htmlFor="d1" error="Too small" errorId="d1-e">
        <input id="d1" aria-describedby="d1-e" />
      </FieldRow>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Too small");
    expect(screen.getByLabelText("Distance")).toHaveAccessibleDescription(
      "Too small",
    );
  });
});

describe("FieldRow note", () => {
  it("keeps an explanation behind the balloon until it is asked for", () => {
    render(
      <FieldRow
        label="Direction"
        note="Builds out from the face."
        noteLabel="About the sweep direction"
        noteTestId="hint"
      >
        <span>controls</span>
      </FieldRow>,
    );
    const note = screen.getByTestId("hint");
    expect(note).toHaveAttribute("hidden");
    const toggle = screen.getByTestId("hint-toggle");
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    expect(note).not.toHaveAttribute("hidden");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(toggle);
    expect(note).toHaveAttribute("hidden");
  });

  it("pins a WARNING open and offers no way to dismiss it", () => {
    render(
      <FieldRow
        label="Direction"
        note="Runs out from the face — nothing to remove there."
        noteTone="flag"
        noteTestId="hint"
      >
        <span>controls</span>
      </FieldRow>,
    );
    expect(screen.getByTestId("hint")).not.toHaveAttribute("hidden");
    expect(screen.queryByTestId("hint-toggle")).toBeNull();
  });

  it("names the note toggle so it is reachable without sight", () => {
    render(
      <FieldRow note="Along the plane normal." noteLabel="About the sweep">
        <span>controls</span>
      </FieldRow>,
    );
    expect(
      screen.getByRole("button", { name: "About the sweep" }),
    ).toHaveAttribute("aria-controls");
  });
});
