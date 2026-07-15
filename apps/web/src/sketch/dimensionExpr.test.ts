import { describe, expect, it } from "vitest";

import { classifyDimensionValue, dimensionNameError } from "./dimensionExpr";

describe("classifyDimensionValue", () => {
  it("treats a bare number as a literal (→ value_mm)", () => {
    expect(classifyDimensionValue("20")).toEqual({
      kind: "literal",
      valueMm: 20,
    });
    expect(classifyDimensionValue(" 12.5 ")).toEqual({
      kind: "literal",
      valueMm: 12.5,
    });
    expect(classifyDimensionValue("-3")).toEqual({
      kind: "literal",
      valueMm: -3,
    });
  });

  it("treats anything non-numeric as an expression (sent verbatim)", () => {
    expect(classifyDimensionValue("width/2")).toEqual({
      kind: "expression",
      expression: "width/2",
    });
    expect(classifyDimensionValue(" (a + b) * 2 ")).toEqual({
      kind: "expression",
      expression: "(a + b) * 2",
    });
    // A lone reference is an expression, not a literal.
    expect(classifyDimensionValue("width")).toEqual({
      kind: "expression",
      expression: "width",
    });
    // A trailing-dot / partial number is not a bare literal → expression.
    expect(classifyDimensionValue("12.")).toEqual({
      kind: "expression",
      expression: "12.",
    });
  });

  it("flags empty input as its own case", () => {
    expect(classifyDimensionValue("")).toEqual({ kind: "empty" });
    expect(classifyDimensionValue("   ")).toEqual({ kind: "empty" });
  });
});

describe("dimensionNameError", () => {
  it("accepts a valid identifier and an empty (unnamed) field", () => {
    expect(dimensionNameError("width")).toBeNull();
    expect(dimensionNameError("_w2")).toBeNull();
    expect(dimensionNameError("")).toBeNull();
    expect(dimensionNameError("  ")).toBeNull();
  });

  it("rejects a malformed identifier (server owns uniqueness)", () => {
    expect(dimensionNameError("2wide")).not.toBeNull();
    expect(dimensionNameError("a b")).not.toBeNull();
    expect(dimensionNameError("width-2")).not.toBeNull();
  });
});
