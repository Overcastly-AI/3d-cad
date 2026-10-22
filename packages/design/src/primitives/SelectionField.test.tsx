// @vitest-environment jsdom
/**
 * SelectionField (BUILDING-OUTLINE): the cell names the picks, the live field
 * says so, every option toggles in place and the clear drops them all.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SelectionField } from "./SelectionField";

afterEach(cleanup);

const SIDES = [
  { value: "e1", label: "Front", selected: true },
  { value: "e4", label: "Left", selected: false },
  { value: "e3", label: "Back", selected: true },
];

describe("SelectionField", () => {
  it("names the picks in the cell and marks the live field", () => {
    render(
      <SelectionField
        label="Defines slope"
        armed
        onArm={() => {}}
        picked={["Front", "Back"]}
        options={SIDES}
        onToggle={() => {}}
        data-testid="slope"
      />,
    );
    const cell = screen.getByRole("button", {
      name: "Defines slope: Front, Back",
    });
    expect(cell).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("slope")).toHaveAttribute("data-armed", "true");
    expect(screen.getByRole("button", { name: "Left" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("arms on the cell, toggles an option and clears", () => {
    const onArm = vi.fn();
    const onToggle = vi.fn();
    const onClear = vi.fn();
    render(
      <SelectionField
        label="Wall"
        armed={false}
        onArm={onArm}
        picked={["Front"]}
        options={SIDES}
        onToggle={onToggle}
        onClear={onClear}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Wall: Front" }));
    expect(onArm).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Left" }));
    expect(onToggle).toHaveBeenCalledWith("e4");
    fireEvent.click(screen.getByRole("button", { name: "Clear Wall" }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("shows the placeholder and the hint with nothing to pick", () => {
    render(
      <SelectionField
        label="Wall"
        armed={false}
        onArm={() => {}}
        picked={[]}
        options={[]}
        onToggle={() => {}}
        onClear={() => {}}
        emptyHint="Pick an outline wall first."
        error="Pick at least 1."
      />,
    );
    expect(
      screen.getByRole("button", { name: "Wall: Select" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear Wall" })).toBeNull();
    expect(screen.getByText("Pick an outline wall first.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Pick at least 1.");
  });
});
