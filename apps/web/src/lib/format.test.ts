import { describe, expect, it } from "vitest";

import { formatArea, formatExtents, formatVec3, formatVolume } from "./format";

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
    expect(formatVolume(31391.38, "in")).toBe("1.92");
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
