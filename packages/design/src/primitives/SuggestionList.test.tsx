/**
 * The value cell's formula affordances (PART-PARAMETERS step 8): NumberField's
 * `fx` mark and resolved-value hint, and the completion list, which must never
 * take focus from the cell it serves.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NumberField } from "./NumberField";
import { SuggestionList, suggestionOptionId } from "./SuggestionList";

describe("NumberField formula affordances", () => {
  it("engraves fx and sets the hint in place of the unit", () => {
    render(
      <NumberField
        label="Distance"
        unit="mm"
        formula
        hint="= 10 mm"
        hintTestId="hint"
        defaultValue="H/2"
      />,
    );
    const input = screen.getByLabelText("Distance");
    const cell = input.parentElement as HTMLElement;
    expect(cell.querySelector("[data-formula-mark]")?.textContent).toBe("fx");
    expect(screen.getByTestId("hint").textContent).toBe("= 10 mm");
    expect(cell.textContent).not.toContain("mm=");
    expect(input).toHaveAttribute(
      "aria-describedby",
      screen.getByTestId("hint").id,
    );
  });

  it("hides the hint behind an error", () => {
    render(
      <NumberField
        label="Distance"
        unit="mm"
        formula
        hint="= 10 mm"
        hintTestId="hint"
        error="Parameter 'Q' not found."
      />,
    );
    expect(screen.queryByTestId("hint")).toBeNull();
    expect(screen.getByRole("alert").textContent).toBe(
      "Parameter 'Q' not found.",
    );
  });

  it("draws neither mark nor hint for a plain number", () => {
    render(<NumberField label="Distance" unit="mm" defaultValue="10" />);
    const cell = screen.getByLabelText("Distance").parentElement as HTMLElement;
    expect(cell.querySelector("[data-formula-mark]")).toBeNull();
    expect(cell.textContent).toBe("mm");
  });
});

describe("SuggestionList", () => {
  it("is a listbox of options, the active one selected", () => {
    render(
      <SuggestionList
        id="list"
        options={[{ value: "W", detail: "40 mm" }, { value: "sin" }]}
        activeIndex={1}
        onPick={() => undefined}
      />,
    );
    const options = screen.getAllByRole("option");
    expect(options.map((o) => o.getAttribute("aria-selected"))).toEqual([
      "false",
      "true",
    ]);
    expect(options[1]?.id).toBe(suggestionOptionId("list", 1));
    expect(options[0]?.textContent).toBe("W40 mm");
  });

  it("picks on press without taking focus from the cell", () => {
    const onPick = vi.fn();
    render(
      <SuggestionList
        id="list"
        options={[{ value: "W" }, { value: "H" }]}
        activeIndex={0}
        onPick={onPick}
      />,
    );
    const press = fireEvent.mouseDown(
      screen.getByRole("option", { name: "H" }),
    );
    expect(press).toBe(false); // default prevented: focus stays put
    expect(onPick).toHaveBeenCalledWith(1);
  });
});
