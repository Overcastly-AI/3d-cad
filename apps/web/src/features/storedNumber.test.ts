import { parseLength } from "@loft/design";
import { describe, expect, it } from "vitest";

import { lengthInputValue, parsePositiveLengthMm } from "../units/length";
import {
  storedLengthInput,
  storedLengthMm,
  storedNumber,
  storedNumberInput,
} from "./storedNumber";

describe("storedLengthInput: the seed a stored length is shown as", () => {
  it("keeps the readable text when it already parses back exactly", () => {
    expect(storedLengthInput(10, "mm")).toBe("10");
    expect(storedLengthInput(25.4, "in")).toBe("1");
  });

  it("shows the shortest exact text when the readable one would round", () => {
    // The 4-fraction-digit display seed was "12.3457".
    expect(storedLengthInput(12.345678901234, "mm")).toBe("12.345678901234");
    const inches = storedLengthInput(12.345678901234, "in");
    expect(parseLength(inches, "in")).toBe(12.345678901234);
  });

  it("falls back to the readable text where no text in the unit is exact", () => {
    // 7.123456789012 / 25.4 * 25.4 is not 7.123456789012: no inch text works.
    const text = storedLengthInput(7.123456789012, "in");
    expect(parseLength(text, "in")).not.toBe(7.123456789012);
    expect(text).toBe(lengthInputValue(7.123456789012, "in"));
  });
});

describe("storedLengthMm: what a length field means on Save", () => {
  it("is the STORED value, exactly, while the field reads its seed", () => {
    const stored = 7.123456789012;
    const seed = storedLengthInput(stored, "in");
    expect(storedLengthMm(seed, "in", stored, parsePositiveLengthMm)).toBe(
      stored,
    );
    // Whitespace around an untouched seed is still the seed.
    expect(
      storedLengthMm(` ${seed} `, "in", stored, parsePositiveLengthMm),
    ).toBe(stored);
  });

  it("parses an EDITED field, and a field with nothing stored", () => {
    expect(storedLengthMm("2", "in", 7.1, parsePositiveLengthMm)).toBe(50.8);
    expect(storedLengthMm("2", "mm", undefined, parsePositiveLengthMm)).toBe(2);
    expect(storedLengthMm("-1", "mm", null, parsePositiveLengthMm)).toBeNull();
  });
});

describe("storedNumber: the unitless twin", () => {
  it("seeds with String and keeps the stored value while untouched", () => {
    expect(storedNumberInput(82.123456789)).toBe("82.123456789");
    const rounding = (input: string) => Math.round(Number(input) * 100) / 100;
    expect(storedNumber("82.123456789", 82.123456789, rounding)).toBe(
      82.123456789,
    );
    expect(storedNumber("90", 82.123456789, rounding)).toBe(90);
  });
});
