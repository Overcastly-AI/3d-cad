/**
 * B7-MIXED-FRACTION (RESEARCH §29): carpenter notation in every length entry.
 * `11-15/32` typed into a length field is eleven and fifteen thirty-seconds,
 * never 11 − 15/32; real subtraction keeps its spaces or parentheses; a
 * hyphenated mixed number inside a larger formula is refused, not guessed;
 * and a STORED expression keeps the meaning the server gave it.
 */
import { describe, expect, it } from "vitest";

import { parseLength } from "@loft/design";

import {
  lengthEntryExpression,
  mixedNumberAmbiguity,
  evaluateExpression,
  type Quantity,
} from "../features/expr";
import { blankRow, tableToWire, wireExpression } from "../features/parameters";
import { resolveDrawEntry } from "../sketch/drawEntry";
import {
  classifyDimensionValue,
  dimensionAmbiguity,
} from "../sketch/dimensionExpr";
import {
  carpenterHint,
  parseFieldEntry,
  resolveFieldFormula,
  typedFormulaError,
} from "./length";

const IN = 25.4;
const names = new Map<string, Quantity>([
  ["wall", { value: 4 * IN, kind: "length" }],
]);

/** What a length field typed `text` comes to, in inches, in an inch part. */
function fieldInches(text: string): number | string {
  const entry = parseFieldEntry(text, "length", "in");
  if (entry.kind === "number") {
    const mm = parseLength(text, "in");
    return mm === null ? "not a number" : mm / IN;
  }
  if (entry.kind === "empty") return "empty";
  const refused = typedFormulaError(entry.expression, "length", "in");
  if (refused !== null) return refused;
  const result = resolveFieldFormula(entry.expression, "length", names);
  return result.ok ? result.value / IN : result.message;
}

describe("length fields read carpenter notation", () => {
  it.each([
    ["11-15/32", 11.46875],
    ["11 15/32", 11.46875],
    ['11 15/32"', 11.46875],
    [`5' 6-1/2"`, 66.5],
    [`5'6"`, 66],
    ["-3/4", -0.75],
  ])("%s is a number of %f in", (text, inches) => {
    expect(parseFieldEntry(text, "length", "in").kind).toBe("number");
    expect(fieldInches(text)).toBeCloseTo(inches, 12);
  });

  it("keeps spaced subtraction and parentheses as formulas", () => {
    // A bare number in a formula joins the grammar's mm (RESEARCH §20).
    expect(parseFieldEntry("11 - 15/32", "length", "in").kind).toBe("formula");
    expect(fieldInches("11 - 15/32")).toBeCloseTo((11 - 15 / 32) / IN, 12);
    expect(parseFieldEntry("(11-15)/32", "length", "in").kind).toBe("formula");
    expect(fieldInches("(11-15)/32")).toBeCloseTo(-4 / 32 / IN, 12);
  });

  it("reads parameters in a formula as before (wall - 15/32)", () => {
    expect(fieldInches("wall - 15/32")).toBeCloseTo(4 - 15 / 32 / IN, 12);
    expect(fieldInches("wall-15/32")).toBeCloseTo(4 - 15 / 32 / IN, 12);
    expect(fieldInches("wall - 15 in/32")).toBeCloseTo(4 - 15 / 32, 12);
  });

  it("refuses a hyphenated mixed number inside a formula, saying both readings", () => {
    for (const text of ["2*11-15/32", "wall + 11-15/32", "11 -15/32"]) {
      expect(String(fieldInches(text))).toMatch(
        /could be 11 15\/32 or 11 minus 15\/32: type 11 - 15\/32 to subtract, or 11 in \+ 15 in\/32 for the mixed number\.$/,
      );
    }
    expect(mixedNumberAmbiguity("11 - 15/32", "in")).toBeNull();
    expect(mixedNumberAmbiguity("(11-15)/32", "in")).toBeNull();
    expect(mixedNumberAmbiguity("x1-15/32", "in")).toBeNull();
    expect(typedFormulaError("2*11-15/32", "angle", "in")).toBeNull();
  });

  it("echoes a carpenter entry so a typo shows before commit", () => {
    expect(carpenterHint("11-15/32", "in")).toBe("= 11.46875 in");
    expect(carpenterHint(`5' 6-1/2"`, "mm")).toBe("= 1689.1 mm");
    expect(carpenterHint("11.5", "in")).toBeNull();
  });
});

describe("the sketch L box and the dimension box", () => {
  it("draws 11-15/32 as 11 15/32 in, and refuses it inside a formula", () => {
    const entry = resolveDrawEntry("11-15/32", "in", names);
    expect(entry.kind).toBe("value");
    if (entry.kind === "value") {
      expect(entry.value).toBeCloseTo(11.46875 * IN, 9);
      expect(entry.expression).toBeNull();
    }
    expect(resolveDrawEntry("wall+11-15/32", "in", names).kind).toBe("error");
  });

  it("takes carpenter notation as a literal, but keeps a stored expression", () => {
    const opts = { length: true, stored: null };
    expect(classifyDimensionValue('11 15/32"', opts)).toEqual({
      kind: "literal",
      valueMm: 11.46875 * IN,
    });
    const stored = { length: true, stored: "11-15/32" };
    const reopened = classifyDimensionValue("11-15/32", stored);
    expect(reopened).toEqual({ kind: "expression", expression: "11-15/32" });
    expect(dimensionAmbiguity(reopened, stored)).toBeNull();
    const typed = classifyDimensionValue("2*11-15/32", opts);
    expect(dimensionAmbiguity(typed, opts)).not.toBeNull();
    // An angle box knows nothing of carpenter notation.
    expect(classifyDimensionValue("3/4").kind).toBe("expression");
  });
});

describe("stored expressions keep their meaning", () => {
  it("sends a typed carpenter parameter spelled out, with units", () => {
    const row = { ...blankRow("a"), name: "stud", bareUnit: "in" as const };
    const typed = { ...row, expression: "11-15/32" };
    const spelled = wireExpression(typed);
    expect(spelled).toBe("11 in + 15 in/32");
    expect(evaluateExpression(spelled, new Map()).value).toBeCloseTo(
      11.46875 * IN,
      12,
    );
    expect(wireExpression({ ...row, expression: `5' 6-1/2"` })).toBe(
      "5 ft + 6 in + 1 in/2",
    );
  });

  it("re-sends a STORED 11-15/32 parameter byte for byte", () => {
    const stored = {
      ...blankRow("a"),
      name: "stud",
      expression: "11-15/32",
      bareUnit: null,
    };
    expect(wireExpression(stored)).toBe("11-15/32");
    const sent = tableToWire([stored], [stored]);
    expect("body" in sent && sent.body[0]?.expression).toBe("11-15/32");
  });

  it("refuses a typed parameter formula holding a hyphenated mixed number", () => {
    const row = {
      ...blankRow("a"),
      name: "stud",
      expression: "wall + 11-15/32",
      bareUnit: "in" as const,
    };
    const sent = tableToWire([row], []);
    expect("error" in sent && sent.error.code).toBe(
      "local_expression_ambiguous",
    );
  });

  it("spells assembly spacing the same way, in the assembly's mm", () => {
    expect(lengthEntryExpression("11-15/32", "mm")).toBe("11 mm + 15 mm/32");
    expect(lengthEntryExpression(" 3 mm ", "mm")).toBe("3 mm");
    expect(() => lengthEntryExpression("2*11-15/32", "mm")).toThrow(/could be/);
  });
});
