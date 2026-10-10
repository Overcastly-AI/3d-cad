import { describe, expect, it } from "vitest";

import type { LengthUnit } from "@loft/design";

import {
  formatFieldHint,
  formatFieldValue,
  lengthInputValue,
  parseFieldEntry,
  parsePositiveLengthMm,
  parseSignedLengthMm,
  resolveFieldFormula,
} from "./length";

const UNITS: readonly LengthUnit[] = ["mm", "cm", "m", "in", "ft"];

// The kernel's linear tolerance (docs/RESEARCH §; CLAUDE.md). A re-save of an
// unchanged feature must reproduce the stored mm to well within this.
const KERNEL_TOL_MM = 1e-4;

describe("lengthInputValue seed precision", () => {
  // Values that are NOT clean in any foreign unit — the case where a naive
  // 4-digit seed quantises above tolerance and shifts geometry on re-save.
  const storedMm = [50, 12.7, 33.333, 0.05, 123.456, 1000.0009];

  for (const unit of UNITS) {
    for (const mm of storedMm) {
      it(`round-trips ${mm} mm seeded in ${unit} to within kernel tolerance`, () => {
        const seed = lengthInputValue(mm, unit);
        // A bare seed string parses back in the same document unit.
        const back = parseSignedLengthMm(seed, unit);
        expect(back).not.toBeNull();
        expect(Math.abs((back as number) - mm)).toBeLessThan(KERNEL_TOL_MM);
      });
    }
  }

  it('still trims clean values short (25.4 mm → "1" in inches)', () => {
    expect(lengthInputValue(25.4, "in")).toBe("1");
    expect(lengthInputValue(304.8, "ft")).toBe("1");
    expect(lengthInputValue(50, "mm")).toBe("50");
  });

  it('does not reintroduce floating-point noise (50 mm-ish in mm stays "50")', () => {
    expect(lengthInputValue(50.000000001, "mm")).toBe("50");
  });
});

describe("length parse guards", () => {
  it("positive length rejects zero and negatives", () => {
    expect(parsePositiveLengthMm("0", "mm")).toBeNull();
    expect(parsePositiveLengthMm("-5", "mm")).toBeNull();
    expect(parsePositiveLengthMm("5", "mm")).toBe(5);
  });

  it("signed length accepts zero and negatives", () => {
    expect(parseSignedLengthMm("0", "mm")).toBe(0);
    expect(parseSignedLengthMm("-5", "mm")).toBe(-5);
  });

  it("an explicit suffix overrides the document unit", () => {
    // In an inch document, an explicit mm suffix stores mm.
    expect(parseSignedLengthMm("25.4 mm", "in")).toBeCloseTo(25.4, 9);
    // A bare number reads in the document unit (2 in → 50.8 mm).
    expect(parseSignedLengthMm("2", "in")).toBeCloseTo(50.8, 9);
  });
});

describe("parseFieldEntry: a number or a formula (PART-PARAMETERS step 8)", () => {
  it("reads a bare number, a suffixed length and a half-typed one as numbers", () => {
    for (const text of ["20", "-2.5", ".5", "2 in", "50mm", "-", ".", "12 i"]) {
      expect(parseFieldEntry(text, "length", "in")).toEqual({ kind: "number" });
    }
  });

  it("is empty for blank text", () => {
    expect(parseFieldEntry("  ", "length", "mm")).toEqual({ kind: "empty" });
  });

  it("keeps anything else, trimmed, as a formula", () => {
    expect(parseFieldEntry(" H/2 ", "length", "mm")).toEqual({
      kind: "formula",
      expression: "H/2",
    });
    expect(parseFieldEntry("W - 2 mm", "length", "mm")).toEqual({
      kind: "formula",
      expression: "W - 2 mm",
    });
  });

  it("reads only a plain number as a number in an angle or count field", () => {
    expect(parseFieldEntry("30", "angle", "mm")).toEqual({ kind: "number" });
    expect(parseFieldEntry("30 deg", "angle", "mm")).toEqual({
      kind: "formula",
      expression: "30 deg",
    });
    expect(parseFieldEntry("6", "int", "mm")).toEqual({ kind: "number" });
    expect(parseFieldEntry("N*2", "int", "mm").kind).toBe("formula");
  });
});

describe("a formula's value, in the field's terms", () => {
  const names = new Map([
    ["H", { value: 20, kind: "length" as const }],
    ["A", { value: 30, kind: "angle" as const }],
    ["N", { value: 3, kind: "unitless" as const }],
  ]);

  it("resolves over the parameters and coerces to the field", () => {
    expect(resolveFieldFormula("H/2", "length", names)).toEqual({
      ok: true,
      value: 10,
    });
    expect(resolveFieldFormula("A + 15", "angle", names)).toEqual({
      ok: true,
      value: 45,
    });
    expect(resolveFieldFormula("N * 2", "int", names)).toEqual({
      ok: true,
      value: 6,
    });
  });

  it("says why a formula does not resolve, as a sentence", () => {
    expect(resolveFieldFormula("Q/2", "length", names)).toEqual({
      ok: false,
      code: "expression_unknown_name",
      message: "Parameter 'Q' not found.",
    });
    const units = resolveFieldFormula("A", "length", names);
    expect(units.ok ? "" : units.code).toBe("expression_units");
    const whole = resolveFieldFormula("N / 2", "int", names);
    expect(whole.ok ? "" : whole.code).toBe("expression_domain");
  });

  it("waits for the table rather than calling a name unknown", () => {
    expect(resolveFieldFormula("H/2", "length", null)).toMatchObject({
      ok: false,
      code: "pending",
    });
  });

  it("hands the editor the resolved number in the document unit", () => {
    expect(formatFieldValue(10, "length", "mm")).toBe("10");
    expect(Number(formatFieldValue(50.8, "length", "in"))).toBeCloseTo(2, 12);
    expect(formatFieldValue(6, "int", "mm")).toBe("6");
    expect(formatFieldValue(22.5, "angle", "mm")).toBe("22.5");
  });

  it("shows what the formula comes to as the hint", () => {
    expect(formatFieldHint(10, "length", "mm")).toBe("= 10 mm");
    expect(formatFieldHint(50.8, "length", "in")).toBe("= 2 in");
    expect(formatFieldHint(45, "angle", "mm")).toBe("= 45°");
    expect(formatFieldHint(6, "int", "mm")).toBe("= 6");
  });
});
