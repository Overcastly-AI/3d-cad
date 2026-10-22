/**
 * The client's reading of the expression language agrees with the server's
 * (`packages/loft-wire/tests/test_expr.py`): the same values, kinds and codes
 * for the cases a field meets. The server stays the authority on write.
 */
import { describe, expect, it } from "vitest";

import {
  bareLengths,
  coerceToField,
  evaluateExpression,
  ExprError,
  type Quantity,
} from "./expr";

const NAMES = new Map<string, Quantity>([
  ["W", { value: 40, kind: "length" }],
  ["H", { value: 20, kind: "length" }],
  ["A", { value: 30, kind: "angle" }],
  ["N", { value: 4, kind: "unitless" }],
]);

const value = (text: string): number => evaluateExpression(text, NAMES).value;
const kind = (text: string): string => evaluateExpression(text, NAMES).kind;

function code(text: string, names = NAMES): string {
  try {
    evaluateExpression(text, names);
  } catch (error) {
    if (error instanceof ExprError) return error.code;
    throw error;
  }
  return "ok";
}

describe("evaluateExpression", () => {
  it("does arithmetic with precedence, unary signs and parentheses", () => {
    expect(value("1 + 2 * 3")).toBe(7);
    expect(value("(1 + 2) * 3")).toBe(9);
    expect(value("-2 * -3")).toBe(6);
    expect(value("10 / 4")).toBe(2.5);
    expect(value("2 * pi")).toBeCloseTo(2 * Math.PI, 15);
  });

  it("reads units into mm and degrees", () => {
    expect(value("2 in")).toBeCloseTo(50.8, 12);
    expect(value("1 ft + 1 in")).toBeCloseTo(330.2, 12);
    expect(value("0.5 m")).toBe(500);
    expect(value("3 cm")).toBe(30);
    expect(kind("2 in")).toBe("length");
    expect(value("1 rad")).toBeCloseTo(180 / Math.PI, 12);
    expect(kind("30 deg")).toBe("angle");
  });

  it("reads names with their kinds", () => {
    expect(value("H/2")).toBe(10);
    expect(kind("H/2")).toBe("length");
    expect(value("W / H")).toBe(2);
    expect(kind("W / H")).toBe("unitless");
    expect(value("W - 2 mm")).toBe(38);
    expect(kind("N * H")).toBe("length");
  });

  it("takes degrees in trig and gives degrees back", () => {
    expect(value("sin(30)")).toBeCloseTo(0.5, 15);
    expect(value("20*tan(15)")).toBeCloseTo(20 * Math.tan(Math.PI / 12), 12);
    expect(value("cos(A)")).toBeCloseTo(Math.sqrt(3) / 2, 15);
    expect(value("atan(1)")).toBeCloseTo(45, 12);
    expect(kind("atan2(H, W)")).toBe("angle");
    expect(value("rad(180)")).toBeCloseTo(Math.PI, 15);
    expect(value("deg(pi)")).toBeCloseTo(180, 12);
  });

  it("has the whitelist's helpers, rounding half away from zero", () => {
    expect(value("round(2.5)")).toBe(3);
    expect(value("round(-2.5)")).toBe(-3);
    expect(value("floor(2.7) + ceil(2.1)")).toBe(5);
    expect(value("max(H, W, 5 mm)")).toBe(40);
    expect(value("min(N, 2)")).toBe(2);
    expect(value("abs(-H)")).toBe(20);
    expect(value("sqrt(16)")).toBe(4);
  });

  it("refuses with the server's stable codes", () => {
    expect(code("1 +")).toBe("expression_syntax");
    expect(code("2 $ 3")).toBe("expression_syntax");
    expect(code("evil(1)")).toBe("expression_syntax");
    expect(code("sin")).toBe("expression_syntax");
    expect(code("mm")).toBe("expression_syntax");
    expect(code("1e3")).toBe("expression_syntax");
    expect(code("Q + 1")).toBe("expression_unknown_name");
    expect(code("W + A")).toBe("expression_units");
    expect(code("W * H")).toBe("expression_units");
    expect(code("2 / W")).toBe("expression_units");
    expect(code("sin(W)")).toBe("expression_units");
    expect(code("1 / 0")).toBe("expression_domain");
    expect(code("sqrt(-1)")).toBe("expression_domain");
    expect(code("tan(90)")).toBe("expression_domain");
    expect(code("atan2(0, 0)")).toBe("expression_domain");
    expect(code("1".repeat(257))).toBe("expression_too_complex");
    expect(code(`${"(".repeat(151)}1${")".repeat(151)}`)).toBe(
      "expression_too_complex",
    );
  });

  it("names the unknown name", () => {
    try {
      evaluateExpression("Width / 2", NAMES);
    } catch (error) {
      expect(error).toBeInstanceOf(ExprError);
      expect((error as ExprError).unknownName).toBe("Width");
      expect((error as ExprError).message).toBe("parameter 'Width' not found");
    }
  });

  it("lets a name in scope win over a reserved word in reference position", () => {
    const names = new Map<string, Quantity>([
      ["pi", { value: 3, kind: "unitless" }],
    ]);
    expect(evaluateExpression("pi * 2", names).value).toBe(6);
  });
});

describe("coerceToField", () => {
  it("fits unitless to a length or an angle, and refuses the other kind", () => {
    expect(coerceToField({ value: 5, kind: "unitless" }, "length")).toBe(5);
    expect(coerceToField({ value: 5, kind: "unitless" }, "angle")).toBe(5);
    expect(() => coerceToField({ value: 5, kind: "angle" }, "length")).toThrow(
      "this is an angle; the field needs a length",
    );
    expect(() =>
      coerceToField({ value: 5, kind: "length" }, "unitless"),
    ).toThrow(ExprError);
  });

  it("takes a whole unitless number for an int field", () => {
    expect(
      coerceToField({ value: 4.0000000001, kind: "unitless" }, "int"),
    ).toBe(4);
    expect(() =>
      coerceToField({ value: 4.5, kind: "unitless" }, "int"),
    ).toThrow("this field needs a whole number");
  });
});

describe("bareLengths (FORMULA-BARE-UNIT, the server's bare_lengths)", () => {
  const KINDS = new Map([
    ["wall", "length"],
    ["W", "length"],
    ["n", "unitless"],
    ["a", "angle"],
  ] as const);
  const fixed = (
    text: string,
    field: "length" | "angle" | "unitless" = "length",
    unit = "in",
  ) => bareLengths(text, unit, field, KINDS)?.text ?? null;

  it.each([
    ["wall + 1/2", "wall + 1 in/2"],
    ["W/2 + 3", "W/2 + 3 in"],
    ["3 + W/2", "3 in + W/2"],
    ["1/2", "1 in/2"],
    ["2*(W + 1)", "2*(W + 1 in)"],
    ["-(1+2)", "-(1 in+2 in)"],
    ["max(wall, 3)", "max(wall, 3 in)"],
    ["round(wall + 1)", "round(wall + 1 in)"],
    ["wall + n", "wall + n*1 in"],
    ["wall + pi", "wall + pi*1 in"],
    ["(wall+1)/W", "(wall+1 in)/W*1 in"],
    ["n*2", "n*1 in*2"],
  ])("writes the unit into %s", (text, want) => {
    expect(fixed(text)).toBe(want);
  });

  it.each([
    ["W*2", "length"],
    ["W/2", "length"],
    ["wall + 1 in", "length"],
    ["W/wall", "unitless"],
    ["a + 3", "angle"],
    ["W*sin(30)", "length"],
    ["wall +", "length"],
    ["Q + 1", "length"],
  ] as const)("leaves %s as written", (text, field) => {
    expect(fixed(text, field)).toBeNull();
  });

  it("reads in the part unit and does nothing in mm", () => {
    expect(fixed("wall + 1/2", "length", "mm")).toBeNull();
    expect(fixed("(wall+1)/W", "unitless")).toBe("(wall+1 in)/W");
    const names = new Map<string, Quantity>([
      ["wall", { value: 5.5 * 25.4, kind: "length" }],
    ]);
    const text = fixed("wall + 1/2") ?? "";
    expect(evaluateExpression(text, names).value).toBeCloseTo(6 * 25.4, 9);
    expect(
      bareLengths("wall + 1/2 - (3)", "in", "length", KINDS)?.literals,
    ).toEqual(["1/2", "(3)"]);
  });
});
