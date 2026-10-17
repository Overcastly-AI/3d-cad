import { describe, expect, it } from "vitest";

import { centsToDecimal, formatMoney, parseMoney } from "./money";

describe("money", () => {
  it("formats integer cents as USD", () => {
    expect(formatMoney(94394)).toBe("$943.94");
    expect(formatMoney(173608)).toBe("$1,736.08");
    expect(formatMoney(5)).toBe("$0.05");
    expect(formatMoney(0)).toBe("$0.00");
    expect(formatMoney(-1250)).toBe("-$12.50");
    expect(formatMoney(-5)).toBe("-$0.05");
    expect(formatMoney(123456789012)).toBe("$1,234,567,890.12");
  });

  it("refuses a value that is not integer cents", () => {
    expect(() => formatMoney(19.98)).toThrow(RangeError);
  });

  it("edits cents as a plain decimal", () => {
    expect(centsToDecimal(1998)).toBe("19.98");
    expect(centsToDecimal(145)).toBe("1.45");
    expect(centsToDecimal(7)).toBe("0.07");
  });

  it("parses a typed price to exact cents", () => {
    expect(parseMoney("19.98")).toBe(1998);
    expect(parseMoney("$28.47")).toBe(2847);
    expect(parseMoney("1.1")).toBe(110);
    expect(parseMoney("4")).toBe(400);
    expect(parseMoney(".5")).toBe(50);
    expect(parseMoney("1,234.56")).toBe(123456);
    expect(parseMoney(" 0.29 ")).toBe(29);
  });

  it("refuses what is not a price", () => {
    for (const text of ["", ".", "-1", "1.234", "abc", "1,23", "1e3"]) {
      expect(parseMoney(text)).toBeNull();
    }
  });
});
