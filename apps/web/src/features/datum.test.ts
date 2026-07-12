import { describe, expect, it } from "vitest";

import {
  buildDatumParams,
  canSubmitDatum,
  defaultDatumForm,
  formFromDatumParams,
  offsetError,
  parseOffsetMm,
} from "./datum";

describe("parseOffsetMm", () => {
  it("accepts any finite value (0, negative, positive)", () => {
    expect(parseOffsetMm("30")).toBe(30);
    expect(parseOffsetMm("0")).toBe(0);
    expect(parseOffsetMm("-12.5")).toBe(-12.5);
    expect(parseOffsetMm("  8 ")).toBe(8);
  });

  it("rejects empty and non-numeric input", () => {
    expect(parseOffsetMm("")).toBeNull();
    expect(parseOffsetMm("  ")).toBeNull();
    expect(parseOffsetMm("abc")).toBeNull();
    expect(parseOffsetMm("Infinity")).toBeNull();
  });
});

describe("offsetError", () => {
  it("is null while empty (pending) or valid", () => {
    expect(offsetError("")).toBeNull();
    expect(offsetError("30")).toBeNull();
    expect(offsetError("-5")).toBeNull();
  });

  it("flags a non-numeric offset", () => {
    expect(offsetError("abc")).toMatch(/millimetres/i);
  });
});

describe("buildDatumParams", () => {
  it("builds v1 datum params from the form", () => {
    expect(
      buildDatumParams({ base: "XY", offsetInput: "30", flip: false }),
    ).toEqual({ base: "XY", offset_mm: 30, flip: false });
    expect(
      buildDatumParams({ base: "XZ", offsetInput: "-10", flip: true }),
    ).toEqual({ base: "XZ", offset_mm: -10, flip: true });
  });

  it("returns null (blocks submit) when the offset is missing/invalid", () => {
    expect(
      buildDatumParams({ base: "XY", offsetInput: "", flip: false }),
    ).toBeNull();
    expect(canSubmitDatum({ base: "XY", offsetInput: "x", flip: false })).toBe(
      false,
    );
    expect(canSubmitDatum({ base: "XY", offsetInput: "30", flip: false })).toBe(
      true,
    );
  });
});

describe("form seeding", () => {
  it("defaults to 30 mm above XY (the everyday sketch-up case)", () => {
    expect(defaultDatumForm()).toEqual({
      base: "XY",
      offsetInput: "30",
      flip: false,
    });
  });

  it("round-trips params → form → params", () => {
    const params = { base: "YZ", offset_mm: 12.5, flip: true } as const;
    expect(buildDatumParams(formFromDatumParams(params))).toEqual(params);
  });
});
