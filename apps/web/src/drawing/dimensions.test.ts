import { describe, expect, it } from "vitest";

import type { EdgeSignature } from "../api/drawings";
import { edgeSignatureKey, formatDimensionLabel } from "./dimensions";

const vec = (x: number, y: number, z: number) => ({ x, y, z });

/** The straight 40 mm bottom edge (end_a (0,0,0) → end_b (40,0,0)). */
const lineSig = (): EdgeSignature => ({
  curve: "line",
  end_a: vec(0, 0, 0),
  end_b: vec(40, 0, 0),
  midpoint: vec(20, 0, 0),
  length_mm: 40,
  subshape_type: "edge",
});

describe("formatDimensionLabel", () => {
  it("prefixes each type and formats to a sensible precision", () => {
    expect(formatDimensionLabel("diameter", 10, "mm")).toBe("Ø10.000");
    expect(formatDimensionLabel("radius", 5, "mm")).toBe("R5.000");
    expect(formatDimensionLabel("linear", 40, "mm")).toBe("40.000");
    expect(formatDimensionLabel("angular", 90, "deg")).toBe("90.0°");
  });
});

describe("edgeSignatureKey", () => {
  it("is rounding-stable across full-precision jitter", () => {
    const a = lineSig();
    const b = { ...lineSig(), length_mm: 40.00000001 };
    // The key rounds coordinates to 3dp so re-projection jitter still matches.
    expect(edgeSignatureKey(a)).toBe(edgeSignatureKey(b));
  });

  it("distinguishes different edges", () => {
    const circle: EdgeSignature = {
      ...lineSig(),
      curve: "circle",
      midpoint: vec(25, 12.5, 0),
    };
    expect(edgeSignatureKey(lineSig())).not.toBe(edgeSignatureKey(circle));
  });
});
