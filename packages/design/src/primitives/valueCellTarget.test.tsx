// @vitest-environment jsdom
/**
 * THE VALUE CELL'S INPUT IS THE TARGET (2c24a2d, review S7).
 *
 * A click focuses only the `<input>`, so a cell padded from OUTSIDE leaves the
 * input at its line height: measured 21 px inside a 31 px cell, under the 24 px
 * target floor (WCAG 2.2 SC 2.5.8), in NumberField first and ExpressionField
 * after it. The fix puts the vertical padding ON the input; the drawn cell is
 * the same 31 px. jsdom has no layout, so this pins the structure the
 * measurement depends on (the e2e `fb19-chrome-density` floor is the real
 * gate for NumberField); the cell must not carry the padding the input needs.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ExpressionField } from "./ExpressionField";
import { NumberField } from "./NumberField";

afterEach(cleanup);

function classesOf(el: Element | null): string[] {
  return (el?.getAttribute("class") ?? "").split(/\s+/);
}

describe("a value cell's vertical padding is on its input", () => {
  it("ExpressionField", () => {
    render(<ExpressionField label="Distance" unit="mm" defaultValue="43" />);
    const input = screen.getByLabelText("Distance");
    expect(classesOf(input)).toContain("py-1");
    expect(classesOf(input.parentElement)).not.toContain("py-1");
  });

  it("NumberField (default emphasis)", () => {
    render(<NumberField label="Twist" unit="deg" defaultValue="0" />);
    const input = screen.getByLabelText("Twist");
    expect(classesOf(input)).toContain("py-1");
    expect(classesOf(input.parentElement)).not.toContain("py-1");
  });
});
