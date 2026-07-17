import { describe, expect, it } from "vitest";

import type { LengthUnit } from "@loft/design";

import {
  lengthInputValue,
  parsePositiveLengthMm,
  parseSignedLengthMm,
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
