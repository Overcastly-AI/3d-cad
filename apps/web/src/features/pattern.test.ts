import { describe, expect, it } from "vitest";

import type { PatternParams } from "../api/parts";
import {
  buildPatternParams,
  canSubmitPattern,
  coordError,
  countError,
  defaultPatternForm,
  formFromPatternParams,
  nearestPreset,
  parseCount,
  parseSpacingMm,
  presetVec,
  spacingError,
} from "./pattern";

describe("defaultPatternForm", () => {
  it("is a 3-up linear row 10 mm apart along +X", () => {
    const form = defaultPatternForm();
    expect(form.kind).toBe("linear");
    expect(form.countInput).toBe("3");
    expect(form.direction).toBe("+x");
    expect(form.spacingInput).toBe("10");
  });
});

describe("parseCount", () => {
  it("accepts whole numbers >= 2, rejects <2 / non-integer / empty", () => {
    expect(parseCount("3")).toBe(3);
    expect(parseCount(" 12 ")).toBe(12);
    // count includes the seed, so 1 (seed only) is a no-op and rejected.
    expect(parseCount("1")).toBeNull();
    expect(parseCount("0")).toBeNull();
    expect(parseCount("2.5")).toBeNull();
    expect(parseCount("")).toBeNull();
    expect(parseCount("abc")).toBeNull();
  });
});

describe("countError", () => {
  it("is quiet while empty, flags a count that repeats nothing", () => {
    expect(countError("")).toBeNull();
    expect(countError("3")).toBeNull();
    expect(countError("1")).toContain("seed");
  });
});

describe("parseSpacingMm", () => {
  it("accepts positive millimetres only", () => {
    expect(parseSpacingMm("6", "mm")).toBe(6);
    expect(parseSpacingMm("0", "mm")).toBeNull();
    expect(parseSpacingMm("-3", "mm")).toBeNull();
    expect(parseSpacingMm("", "mm")).toBeNull();
    expect(spacingError("0", "mm")).toContain("positive");
  });

  it("converts through the document unit", () => {
    expect(parseSpacingMm("2", "in")).toBe(50.8);
  });
});

describe("coordError", () => {
  it("accepts any finite value (0 / negative ok), flags gibberish", () => {
    expect(coordError("0", "mm")).toBeNull();
    expect(coordError("-25", "mm")).toBeNull();
    expect(coordError("nope", "mm")).toContain("length");
  });
});

describe("presetVec / nearestPreset", () => {
  it("maps presets to unit vectors and back (round-trip)", () => {
    expect(presetVec("+z")).toEqual({ x: 0, y: 0, z: 1 });
    expect(presetVec("-y")).toEqual({ x: 0, y: -1, z: 0 });
    expect(nearestPreset({ x: 0, y: 0, z: 1 })).toBe("+z");
    // An oblique vector snaps to its dominant principal axis.
    expect(nearestPreset({ x: 5, y: 1, z: 0 })).toBe("+x");
    // A zero vector defaults to +X rather than throwing.
    expect(nearestPreset({ x: 0, y: 0, z: 0 })).toBe("+x");
  });
});

describe("buildPatternParams", () => {
  it("builds a linear pattern from a valid linear form", () => {
    const params = buildPatternParams(
      {
        ...defaultPatternForm(),
        kind: "linear",
        direction: "+y",
        spacingInput: "6",
        countInput: "4",
      },
      "mm",
    );
    expect(params).toEqual({
      pattern: {
        kind: "linear",
        direction: { x: 0, y: 1, z: 0 },
        spacing_mm: 6,
        count: 4,
      },
    });
  });

  it("builds a circular pattern, ignoring the linear fields", () => {
    const params = buildPatternParams(
      {
        ...defaultPatternForm(),
        kind: "circular",
        axisDirection: "+z",
        axisPointXInput: "0",
        axisPointYInput: "0",
        axisPointZInput: "0",
        angleInput: "360",
        countInput: "6",
        // stale/garbage linear fields must not block a circular build
        spacingInput: "not-a-number",
      },
      "mm",
    );
    expect(params).toEqual({
      pattern: {
        kind: "circular",
        axis_point: { x: 0, y: 0, z: 0 },
        axis_direction: { x: 0, y: 0, z: 1 },
        angle_deg: 360,
        count: 6,
      },
    });
  });

  it("returns null when a required field is invalid", () => {
    expect(
      buildPatternParams({ ...defaultPatternForm(), countInput: "1" }, "mm"),
    ).toBeNull();
    expect(
      buildPatternParams({ ...defaultPatternForm(), spacingInput: "0" }, "mm"),
    ).toBeNull();
    expect(
      buildPatternParams(
        {
          ...defaultPatternForm(),
          kind: "circular",
          angleInput: "400",
        },
        "mm",
      ),
    ).toBeNull();
  });
});

describe("canSubmitPattern", () => {
  it("mirrors buildPatternParams success", () => {
    expect(canSubmitPattern(defaultPatternForm(), "mm")).toBe(true);
    expect(
      canSubmitPattern({ ...defaultPatternForm(), spacingInput: "" }, "mm"),
    ).toBe(false);
  });
});

describe("formFromPatternParams", () => {
  it("round-trips a linear pattern into editable form state", () => {
    const params: PatternParams = {
      pattern: {
        kind: "linear",
        direction: { x: -1, y: 0, z: 0 },
        spacing_mm: 8,
        count: 5,
      },
    };
    const form = formFromPatternParams(params, "mm");
    expect(form.kind).toBe("linear");
    expect(form.direction).toBe("-x");
    expect(form.spacingInput).toBe("8");
    expect(form.countInput).toBe("5");
  });

  it("round-trips a circular pattern, seeding the axis point + angle", () => {
    const params: PatternParams = {
      pattern: {
        kind: "circular",
        axis_point: { x: 10, y: -4, z: 0 },
        axis_direction: { x: 0, y: 0, z: 1 },
        angle_deg: 270,
        count: 6,
      },
    };
    const form = formFromPatternParams(params, "mm");
    expect(form.kind).toBe("circular");
    expect(form.axisDirection).toBe("+z");
    expect(form.axisPointXInput).toBe("10");
    expect(form.axisPointYInput).toBe("-4");
    expect(form.angleInput).toBe("270");
    expect(form.countInput).toBe("6");
  });

  it("seeds spacing + coords in the document unit, angle stays degrees", () => {
    const params: PatternParams = {
      pattern: {
        kind: "circular",
        axis_point: { x: 25.4, y: -50.8, z: 0 },
        axis_direction: { x: 0, y: 0, z: 1 },
        angle_deg: 90,
        count: 4,
      },
    };
    const form = formFromPatternParams(params, "in");
    expect(form.axisPointXInput).toBe("1");
    expect(form.axisPointYInput).toBe("-2");
    // Angle is unitless — never converted through length.
    expect(form.angleInput).toBe("90");
  });
});
