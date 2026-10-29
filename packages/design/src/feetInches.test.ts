import { describe, expect, it } from "vitest";

import { formatFeetInches } from "./feetInches";

const IN = 25.4;

/** The cases `packages/loft-wire/tests/test_feet_inches.py` pins too. */
const CASES: [number, string][] = [
  [288, `24'-0"`],
  [192, `16'-0"`],
  [97.125, `8'-1 1/8"`],
  [82.5, `6'-10 1/2"`],
  [60, `5'-0"`],
  [84, `7'-0"`],
  [5.5, `5 1/2"`],
  [0.75, `3/4"`],
  [0, `0"`],
  [12.03125, `1'-0 1/16"`],
  [11.99, `1'-0"`],
  [-30, `-2'-6"`],
];

describe("formatFeetInches", () => {
  it.each(CASES)("%s in reads %s", (inches, text) => {
    expect(formatFeetInches(inches * IN)).toBe(text);
  });

  it("rounds half up to the sixteenth", () => {
    expect(formatFeetInches((60 + 0.035) * IN)).toBe(`5'-0 1/16"`);
    expect(formatFeetInches((60 + 0.03) * IN)).toBe(`5'-0"`);
  });
});
