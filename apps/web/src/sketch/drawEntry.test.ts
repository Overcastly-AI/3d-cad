import { describe, expect, it } from "vitest";

import type { Quantity } from "../features/expr";
import {
  drawCellsOk,
  oneValueMessage,
  resolveDrawCells,
  resolveDrawEntry,
  secondValueTyped,
} from "./drawEntry";

const names = new Map<string, Quantity>([
  ["W", { value: 80, kind: "length" }],
  ["H", { value: 50, kind: "length" }],
]);

describe("resolveDrawEntry (QA-RECT-BOX-NAMES)", () => {
  it("reads a number in the document unit, with no formula", () => {
    expect(resolveDrawEntry("80", "mm", names)).toEqual({
      kind: "value",
      value: 80,
      expression: null,
    });
    expect(resolveDrawEntry("2", "in", names)).toEqual({
      kind: "value",
      value: 50.8,
      expression: null,
    });
  });

  it("resolves a parameter, keeping the formula for the dimension", () => {
    expect(resolveDrawEntry("W", "mm", names)).toEqual({
      kind: "value",
      value: 80,
      expression: "W",
    });
    expect(resolveDrawEntry(" W/2 + 5 ", "mm", names)).toEqual({
      kind: "value",
      value: 45,
      expression: "W/2 + 5",
    });
  });

  it("says why an unknown name cannot apply, instead of dropping it", () => {
    const entry = resolveDrawEntry("Q", "mm", names);
    expect(entry.kind).toBe("error");
    expect(entry.kind === "error" && entry.message).toMatch(/Q/);
  });

  it("refuses a size that is not above zero, but a coordinate may be", () => {
    expect(resolveDrawEntry("H - W", "mm", names).kind).toBe("error");
    expect(resolveDrawEntry("0", "mm", names).kind).toBe("error");
    expect(resolveDrawEntry("H - W", "mm", names, { signed: true })).toEqual({
      kind: "value",
      value: -30,
      expression: "H - W",
    });
  });

  it("leaves an empty box as drawn", () => {
    expect(resolveDrawEntry("  ", "mm", names)).toEqual({ kind: "empty" });
  });
});

describe("resolveDrawCells", () => {
  const fields = [{ key: "width" as const }, { key: "height" as const }];

  it("resolves W Tab H to 80 x 50 driven by W and H", () => {
    const texts = ["W", "H"];
    const cells = resolveDrawCells(fields, (i) => texts[i] ?? "", "mm", names);
    expect(drawCellsOk(cells)).toBe(true);
    expect(cells.values).toEqual({ width: 80, height: 50 });
    expect(cells.expressions).toEqual({ width: "W", height: "H" });
  });

  it("holds every cell back when one does not resolve", () => {
    const texts = ["W", "Q"];
    const cells = resolveDrawCells(fields, (i) => texts[i] ?? "", "mm", names);
    expect(drawCellsOk(cells)).toBe(false);
    expect(Object.keys(cells.errors)).toEqual(["height"]);
  });
});

describe("one-cell box after Tab (LINE-LENGTH-TAB)", () => {
  it("sees the bike's x Tab y as a second value, never a longer first one", () => {
    expect(secondValueTyped("426.562", "426.562450.469")).toBe(true);
    expect(secondValueTyped("426.562", "426.562 450.469")).toBe(true);
  });

  it("lets the first value alone, or a retyped one, apply", () => {
    expect(secondValueTyped("426.562", "426.562")).toBe(false);
    expect(secondValueTyped("426.562", "426.562 ")).toBe(false);
    expect(secondValueTyped("426.562", "450.469")).toBe(false);
    // Tab before anything was typed: what follows is the only value.
    expect(secondValueTyped("", "450.469")).toBe(false);
  });

  it("names the one value, and for a line how to type the end point", () => {
    expect(oneValueMessage({ key: "length", name: "Length" })).toBe(
      "This box takes one value, the length. To place the end point, type X Tab Y before you click.",
    );
    expect(oneValueMessage({ key: "diameter", name: "Diameter" })).toBe(
      "This box takes one value, the diameter.",
    );
  });
});
