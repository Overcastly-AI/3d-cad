import { describe, expect, it } from "vitest";

import {
  formatArea,
  formatExtents,
  formatOverlapVolume,
  formatVec3,
  formatVolume,
} from "./format";

/**
 * The mass-props / bbox readouts honor the document unit (FINDINGS #17). The
 * stored value is always canonical mm/mm²/mm³; these convert at the display
 * boundary. An `mm` document is the identity; an `in` document divides by the
 * squared/cubed length factor, so a readout never prints raw mm under `in`.
 */
describe("readout formatting is unit-aware (FINDINGS #17)", () => {
  it("volume: mm document prints the raw grouped mm³ value", () => {
    expect(formatVolume(31391.38, "mm")).toBe("31,391.38");
  });

  it("volume: inch document converts mm³ → in³ (not the raw mm)", () => {
    // 31391.38 mm³ / 25.4³ = 1.9156… in³.
    expect(formatVolume(31391.38, "in")).toBe("1.9156");
  });

  it("area: inch document converts mm² → in²", () => {
    // 645.16 mm² = 1 in².
    expect(formatArea(645.16, "in")).toBe("1");
  });

  it("centroid vector: each component converts to the document unit", () => {
    expect(formatVec3({ x: 25.4, y: 50.8, z: 0 }, "in")).toBe("1, 2, 0");
    expect(formatVec3({ x: 10, y: 20, z: 30 }, "mm")).toBe("10, 20, 30");
  });

  it("extents: each span converts to the document unit", () => {
    expect(
      formatExtents({ x: 0, y: 0, z: 0 }, { x: 25.4, y: 50.8, z: 76.2 }, "in"),
    ).toBe("1 × 2 × 3");
    expect(
      formatExtents({ x: 0, y: 0, z: 0 }, { x: 10, y: 20, z: 30 }, "mm"),
    ).toBe("10 × 20 × 30");
  });
});

/**
 * Readout PRECISION follows the unit (FINDINGS burn-down 2026-07-25): two
 * fraction digits is right in mm and mush in a coarser unit. A unit 10^n times
 * bigger than a millimetre earns n more digits, so a small feature stays
 * legible in an inch document and every mm readout is unchanged.
 */
describe("readout precision is unit-aware", () => {
  it("keeps a small inch volume legible instead of rounding it to 0.01", () => {
    // 100 mm³ = 0.0061024 in³ — "0.01" at two digits, which reads as noise.
    expect(formatVolume(100, "in")).toBe("0.0061");
    expect(formatArea(100, "in")).toBe("0.155");
  });

  it("keeps a small inch length legible", () => {
    // A 0.8 mm sheet is 0.0315 in — "0.03" loses the gauge.
    expect(formatVec3({ x: 0.8, y: 1.6, z: 0 }, "in")).toBe("0.0315, 0.063, 0");
  });

  it("leaves every millimetre readout byte-identical", () => {
    expect(formatVolume(31391.384, "mm")).toBe("31,391.38");
    expect(formatArea(6451.617, "mm")).toBe("6,451.62");
    expect(formatVec3({ x: 0.125, y: 1, z: 0 }, "mm")).toBe("0.13, 1, 0");
  });

  it("scales with the unit: metres and feet earn more digits than cm", () => {
    // 1 mm in a metre document is 0.001 m — visible, not "0".
    expect(formatVec3({ x: 1, y: 0, z: 0 }, "m")).toBe("0.001, 0, 0");
    expect(formatVec3({ x: 1, y: 0, z: 0 }, "cm")).toBe("0.1, 0, 0");
    expect(formatVec3({ x: 1, y: 0, z: 0 }, "ft")).toBe("0.00328, 0, 0");
  });
});

/**
 * A clash overlap is a volume like any other, so it converts at the same
 * display boundary (the panel was the last mm-only readout on an inch page).
 * The one extra rule: a flagged pair must never read "0", so a value that would
 * vanish at the unit's precision falls back to scientific notation.
 */
describe("clash overlap volume", () => {
  it("reads in the document unit, not raw mm3", () => {
    expect(formatOverlapVolume(31391.38, "mm")).toBe("31,391.38");
    expect(formatOverlapVolume(31391.38, "in")).toBe("1.9156");
  });

  it("never rounds a genuine tiny overlap to zero (mm)", () => {
    expect(formatOverlapVolume(0.005, "mm")).toBe("5.0e-3");
    expect(formatOverlapVolume(0.01, "mm")).toBe("0.01");
  });

  it("never rounds a genuine tiny overlap to zero in a coarser unit", () => {
    // 0.02 mm3 is 1.2e-6 in3 — "0" at the inch readout precision.
    expect(formatOverlapVolume(0.02, "in")).toBe("1.2e-6");
    expect(formatOverlapVolume(0.02, "mm")).toBe("0.02");
  });

  it("leaves an exact zero alone", () => {
    expect(formatOverlapVolume(0, "in")).toBe("0");
  });
});
