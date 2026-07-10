import { describe, expect, it } from "vitest";

import {
  DIMENSION_MAX_MM,
  parseDimension,
  validateDimensions,
} from "./dimensions";

describe("parseDimension", () => {
  it("accepts positive decimal entries, trimming whitespace", () => {
    expect(parseDimension("10")).toEqual({ ok: true, value: 10 });
    expect(parseDimension(" 0.5 ")).toEqual({ ok: true, value: 0.5 });
    expect(parseDimension(String(DIMENSION_MAX_MM))).toEqual({
      ok: true,
      value: DIMENSION_MAX_MM,
    });
  });

  it("rejects empty entries", () => {
    expect(parseDimension("")).toEqual({
      ok: false,
      error: "Enter a dimension",
    });
    expect(parseDimension("   ")).toEqual({
      ok: false,
      error: "Enter a dimension",
    });
  });

  it("rejects non-numeric entries", () => {
    expect(parseDimension("ten")).toMatchObject({ ok: false });
    expect(parseDimension("1,5")).toMatchObject({ ok: false });
    expect(parseDimension("Infinity")).toMatchObject({ ok: false });
    expect(parseDimension("NaN")).toMatchObject({ ok: false });
  });

  it("rejects zero and negative dimensions", () => {
    expect(parseDimension("0")).toMatchObject({
      ok: false,
      error: "Enter a value above 0 mm",
    });
    expect(parseDimension("-4")).toMatchObject({ ok: false });
  });

  it("rejects entries above the envelope", () => {
    expect(parseDimension(String(DIMENSION_MAX_MM + 1))).toMatchObject({
      ok: false,
    });
  });
});

describe("validateDimensions", () => {
  it("returns typed values when every axis is valid", () => {
    expect(validateDimensions({ x: "10", y: "20", z: "30" })).toEqual({
      ok: true,
      values: { x: 10, y: 20, z: 30 },
    });
  });

  it("collects per-axis errors and fails as a whole", () => {
    const result = validateDimensions({ x: "10", y: "-1", z: "" });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.x).toBeUndefined();
      expect(result.errors.y).toBe("Enter a value above 0 mm");
      expect(result.errors.z).toBe("Enter a dimension");
    }
  });
});
