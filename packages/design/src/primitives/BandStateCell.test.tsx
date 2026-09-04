/**
 * The cell's whole contract is that it says something a band ACTION cannot say
 * and cannot be shed by the label tier — plus the one rule that keeps it from
 * becoming decoration: where a state is retractable, the cell carries the
 * retraction, and it names what leaves rather than saying "close".
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BandStateCell } from "./BandStateCell";

describe("BandStateCell", () => {
  it("puts the eyebrow over the value and inks the value in brass", () => {
    render(
      <BandStateCell
        eyebrow="Scope"
        value="Hole1"
        valueTestId="v"
        marker="▸"
      />,
    );
    expect(screen.getByText("Scope")).toBeInTheDocument();
    const value = screen.getByTestId("v");
    expect(value).toHaveTextContent("Hole1");
    expect(value.className).toContain("text-brass");
  });

  it("renders no retraction when the state cannot be retired from here", () => {
    render(
      <BandStateCell eyebrow="In command" value="Pattern" valueTestId="v" />,
    );
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("retires the state it announces, under a name that says what leaves", () => {
    const onClear = vi.fn();
    render(
      <BandStateCell
        eyebrow="Scope"
        value="Hole1"
        valueTestId="v"
        onClear={onClear}
        clearLabel="Clear Hole1 — pattern and mirror go back to the whole body"
        clearTestId="clear"
      />,
    );
    const button = screen.getByTestId("clear");
    // Not "Close" and not "Dismiss": the accessible name names the subject, so
    // a screen-reader user is told which state this retires when two cells
    // could be on the band at once.
    expect(button).toHaveAccessibleName(
      "Clear Hole1 — pattern and mirror go back to the whole body",
    );
    button.click();
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("marks nothing when no marker is given — one glyph, one relationship", () => {
    const { container } = render(
      <BandStateCell eyebrow="Scope" value="Hole1" valueTestId="v" />,
    );
    expect(container.querySelectorAll("[aria-hidden]")).toHaveLength(0);
  });
});
