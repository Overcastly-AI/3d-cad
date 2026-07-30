import { describe, expect, it } from "vitest";

import {
  areaUnitLabel,
  formatLength,
  formatMass,
  fromGrams,
  fromMm,
  fromMmArea,
  fromMmVolume,
  LENGTH_UNITS,
  type LengthUnit,
  MASS_G_PER_UNIT,
  massUnitFor,
  MM_PER_UNIT,
  parseLength,
  toMm,
  volumeUnitLabel,
} from "./units";

const FACTORS: Array<[LengthUnit, number]> = [
  ["mm", 1],
  ["cm", 10],
  ["m", 1000],
  ["in", 25.4],
  ["ft", 304.8],
];

describe("MM_PER_UNIT", () => {
  it("uses the exact factors, in both directions", () => {
    for (const [unit, factor] of FACTORS) {
      expect(MM_PER_UNIT[unit]).toBe(factor);
      // A whole unit is exactly its factor in mm.
      expect(toMm(1, unit)).toBe(factor);
      // And back.
      expect(fromMm(factor, unit)).toBe(1);
    }
  });

  it("covers every LengthUnit and nothing else", () => {
    expect(Object.keys(MM_PER_UNIT).sort()).toEqual([...LENGTH_UNITS].sort());
  });
});

describe("toMm / fromMm", () => {
  it("round-trips an arbitrary value through each unit", () => {
    for (const [unit] of FACTORS) {
      for (const value of [0, 1, 2.5, -3.75, 123.456]) {
        expect(fromMm(toMm(value, unit), unit)).toBeCloseTo(value, 9);
      }
    }
  });

  it("converts known imperial anchors exactly", () => {
    expect(toMm(2, "in")).toBe(50.8);
    expect(toMm(1, "in")).toBe(25.4);
    expect(fromMm(25.4, "in")).toBe(1);
    expect(fromMm(50.8, "in")).toBe(2);
    expect(toMm(1, "ft")).toBe(304.8);
    expect(toMm(2, "cm")).toBe(20);
    expect(toMm(0.5, "m")).toBe(500);
  });
});

describe("parseLength", () => {
  it("reads a bare number in the document unit", () => {
    expect(parseLength("50", "mm")).toBe(50);
    expect(parseLength("2", "in")).toBe(50.8);
    expect(parseLength("1", "ft")).toBe(304.8);
    expect(parseLength("3.5", "cm")).toBe(35);
    expect(parseLength("0.5", "m")).toBe(500);
  });

  it("lets an explicit suffix override the document unit", () => {
    expect(parseLength("2in", "mm")).toBe(50.8);
    expect(parseLength("2 in", "mm")).toBe(50.8);
    expect(parseLength("50mm", "in")).toBe(50);
    expect(parseLength("25.4 mm", "in")).toBe(25.4);
    expect(parseLength("3.5 cm", "in")).toBe(35);
    expect(parseLength("1ft", "mm")).toBe(304.8);
    expect(parseLength("2m", "mm")).toBe(2000);
  });

  it("is case-insensitive on the suffix", () => {
    expect(parseLength("2IN", "mm")).toBe(50.8);
    expect(parseLength("2In", "mm")).toBe(50.8);
    expect(parseLength("50MM", "in")).toBe(50);
  });

  it("distinguishes mm from m and cm from m", () => {
    expect(parseLength("5mm", "in")).toBe(5);
    expect(parseLength("5m", "in")).toBe(5000);
    expect(parseLength("5cm", "in")).toBe(50);
  });

  it("tolerates surrounding whitespace", () => {
    expect(parseLength("  10  ", "mm")).toBe(10);
    expect(parseLength("  2  in ", "mm")).toBe(50.8);
    expect(parseLength("\t3.5\tcm\t", "mm")).toBe(35);
  });

  it("accepts negative and signed values (gaps/offsets can be signed)", () => {
    expect(parseLength("-2", "in")).toBe(-50.8);
    expect(parseLength("-25.4mm", "in")).toBe(-25.4);
    expect(parseLength("+3", "mm")).toBe(3);
  });

  it("accepts zero", () => {
    expect(parseLength("0", "in")).toBe(0);
    expect(parseLength("0mm", "in")).toBe(0);
    expect(parseLength("-0", "mm")).toBe(-0);
  });

  it("accepts leading/trailing decimal points", () => {
    expect(parseLength(".5", "cm")).toBe(5);
    expect(parseLength("5.", "mm")).toBe(5);
  });

  it("returns null on empty / whitespace-only input", () => {
    expect(parseLength("", "mm")).toBeNull();
    expect(parseLength("   ", "mm")).toBeNull();
  });

  it("returns null on non-numeric / NaN input", () => {
    expect(parseLength("abc", "mm")).toBeNull();
    expect(parseLength("NaN", "mm")).toBeNull();
    expect(parseLength("1.2.3", "mm")).toBeNull();
    expect(parseLength("5e3", "mm")).toBeNull(); // no scientific notation
    expect(parseLength("--5", "mm")).toBeNull();
  });

  it("returns null on an unknown unit suffix", () => {
    expect(parseLength("5px", "mm")).toBeNull();
    expect(parseLength("5 yd", "mm")).toBeNull();
    expect(parseLength("5cc", "mm")).toBeNull();
  });
});

describe("formatLength", () => {
  it("formats canonical mm into the document unit with a suffix", () => {
    expect(formatLength(50.8, "in")).toBe("2 in");
    expect(formatLength(25.4, "in")).toBe("1 in");
    expect(formatLength(10, "mm")).toBe("10 mm");
    expect(formatLength(20, "cm")).toBe("2 cm");
    expect(formatLength(1000, "m")).toBe("1 m");
    expect(formatLength(304.8, "ft")).toBe("1 ft");
  });

  it("trims trailing zeros", () => {
    expect(formatLength(10, "mm")).toBe("10 mm");
    expect(formatLength(2.5, "mm")).toBe("2.5 mm");
    expect(formatLength(50.8, "in")).toBe("2 in"); // not "2.0000 in"
  });

  it("omits the suffix when asked", () => {
    expect(formatLength(50.8, "in", { unitSuffix: false })).toBe("2");
    expect(formatLength(10, "mm", { unitSuffix: false })).toBe("10");
  });

  it("respects a custom precision", () => {
    expect(formatLength(1, "in", { maxFractionDigits: 2 })).toBe("0.04 in");
    expect(formatLength(1, "in", { maxFractionDigits: 4 })).toBe("0.0394 in");
  });

  it("normalises -0 to 0", () => {
    expect(formatLength(-0, "mm")).toBe("0 mm");
    expect(formatLength(0, "in")).toBe("0 in");
  });
});

describe("fromMmArea / fromMmVolume — squared / cubed factor conversion", () => {
  it("is the identity for mm", () => {
    expect(fromMmArea(1234.5, "mm")).toBe(1234.5);
    expect(fromMmVolume(31391.38, "mm")).toBe(31391.38);
  });

  it("divides area by the square of the length factor", () => {
    // 1 in² ≡ 25.4² mm² = 645.16 mm².
    expect(fromMmArea(645.16, "in")).toBeCloseTo(1, 9);
    // 1 cm² ≡ 100 mm².
    expect(fromMmArea(100, "cm")).toBeCloseTo(1, 9);
  });

  it("divides volume by the cube of the length factor", () => {
    // 1 in³ ≡ 25.4³ mm³ = 16387.064 mm³.
    expect(fromMmVolume(16387.064, "in")).toBeCloseTo(1, 9);
    // 1 cm³ ≡ 1000 mm³.
    expect(fromMmVolume(1000, "cm")).toBeCloseTo(1, 9);
    // The audit's exact case: 31391.38 mm³ under `in` ≈ 1.9156 in³, NOT the raw mm.
    expect(fromMmVolume(31391.38, "in")).toBeCloseTo(1.91562, 4);
  });

  it("labels area/volume with the squared/cubed glyph", () => {
    expect(areaUnitLabel("mm")).toBe("mm²");
    expect(areaUnitLabel("in")).toBe("in²");
    expect(volumeUnitLabel("mm")).toBe("mm³");
    expect(volumeUnitLabel("in")).toBe("in³");
  });
});

describe("parseLength ∘ formatLength round-trip", () => {
  it("recovers a value that formatLength emitted", () => {
    const samples = [0, 1, 10, 25.4, 50.8, 100, 304.8, 0.5, 123.4, -42];
    for (const unit of LENGTH_UNITS) {
      for (const mm of samples) {
        const text = formatLength(mm, unit, { maxFractionDigits: 6 });
        const back = parseLength(text, unit);
        expect(back).not.toBeNull();
        expect(back as number).toBeCloseTo(mm, 3);
      }
    }
  });
});

/**
 * MASS — the same seam, the same rules (docs/design/materials.md §5). The wire
 * is canonical GRAMS forever; the display unit DERIVES from the document's
 * length unit, so there is no second setting and no second conversion path.
 */
describe("MASS_G_PER_UNIT", () => {
  it("uses the exact factors (the pound is exact by definition)", () => {
    expect(MASS_G_PER_UNIT.g).toBe(1);
    expect(MASS_G_PER_UNIT.kg).toBe(1000);
    expect(MASS_G_PER_UNIT.lb).toBe(453.59237);
    expect(fromGrams(453.59237, "lb")).toBe(1);
    expect(fromGrams(1000, "kg")).toBe(1);
    expect(fromGrams(27, "g")).toBe(27);
  });

  it("covers every MassUnit and nothing else", () => {
    expect(Object.keys(MASS_G_PER_UNIT).sort()).toEqual(["g", "kg", "lb"]);
  });
});

describe("massUnitFor — the mass unit derives from the LENGTH unit", () => {
  it("reads pounds in an imperial document, at any size", () => {
    expect(massUnitFor("in", 27)).toBe("lb");
    expect(massUnitFor("ft", 27)).toBe("lb");
    // No g→kg-style promotion in imperial: 12 kg of steel is still lb.
    expect(massUnitFor("in", 12_000)).toBe("lb");
  });

  it("promotes g to kg above 1000 g in a metric document", () => {
    for (const unit of ["mm", "cm", "m"] as const) {
      expect(massUnitFor(unit, 999.9)).toBe("g");
      expect(massUnitFor(unit, 1000)).toBe("kg");
      expect(massUnitFor(unit, 12_000)).toBe("kg");
    }
  });

  it("uses the magnitude, so a negative never dodges the promotion", () => {
    expect(massUnitFor("mm", -1500)).toBe("kg");
  });
});

describe("formatMass", () => {
  it("reports the golden masses exactly as the kernel measured them", () => {
    // materials.md §8: 10000 mm³ of aluminium 6061 = 27.0 g exactly.
    expect(formatMass(27, "mm")).toBe("27 g");
    // ...and the mixed-material golden's 84.56 g.
    expect(formatMass(84.56, "mm")).toBe("84.56 g");
  });

  it("promotes to kg and converts to lb through the exact factors", () => {
    expect(formatMass(1000, "mm")).toBe("1 kg");
    expect(formatMass(2537.5, "cm")).toBe("2.5375 kg");
    expect(formatMass(453.59237, "in")).toBe("1 lb");
    expect(formatMass(27, "in")).toBe("0.0595 lb");
  });

  it("says 0 g only for a real zero — absence is never routed through here", () => {
    expect(formatMass(0, "mm")).toBe("0 g");
    expect(formatMass(-0, "mm")).toBe("0 g");
  });

  it("omits the suffix and respects a custom precision", () => {
    expect(formatMass(84.56, "mm", { unitSuffix: false })).toBe("84.56");
    expect(formatMass(84.56, "mm", { maxFractionDigits: 1 })).toBe("84.6 g");
  });
});
