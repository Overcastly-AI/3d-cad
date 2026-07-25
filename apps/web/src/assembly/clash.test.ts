import { describe, expect, it } from "vitest";

import type { ClashPair } from "../api/assemblies";
import { clashEyebrow, clashInstanceIds, clashRows } from "./clash";

/**
 * The clash schedule has two jobs it used to get wrong: read in the document
 * unit, and never let a pair the kernel could NOT measure pass as a
 * measurement. `unresolved: true` means the exact boolean failed while the
 * solved bounding boxes overlap — the kernel refuses to call that clear, and
 * neither may the panel.
 */
function pair(
  a: string,
  b: string,
  mm3: number,
  unresolved = false,
): ClashPair {
  return {
    instance_a: a,
    instance_b: b,
    overlap_volume_mm3: mm3,
    unresolved,
  };
}

describe("clashRows", () => {
  it("reads a measured overlap in the document unit", () => {
    const [row] = clashRows([pair("a", "b", 31391.38)], "in");
    expect(row?.magnitude).toBe("1.9156");
    expect(row?.magnitudeCaption).toBe("in³ overlap");
    expect(row?.unresolved).toBe(false);
  });

  it("keeps a millimetre document byte-identical to before", () => {
    const [row] = clashRows([pair("a", "b", 31391.38)], "mm");
    expect(row?.magnitude).toBe("31,391.38");
    expect(row?.magnitudeCaption).toBe("mm³ overlap");
  });

  it("stamps an unverified magnitude as a parenthesised upper bound", () => {
    const [row] = clashRows([pair("a", "b", 31391.38, true)], "in");
    expect(row?.unresolved).toBe(true);
    // Parentheses = a reference figure (drafting convention): this is a bound
    // from the bounding boxes, not a reading.
    expect(row?.magnitude).toBe("(1.9156)");
    expect(row?.magnitudeCaption).toBe("in³ at most");
  });

  it("sorts measured clashes above unverified pairs, order stable in each", () => {
    const rows = clashRows(
      [
        pair("a", "c", 10, true),
        pair("a", "b", 20),
        pair("b", "c", 30, true),
        pair("c", "d", 40),
      ],
      "mm",
    );
    expect(rows.map((row) => row.key)).toEqual(["a-b", "c-d", "a-c", "b-c"]);
  });
});

describe("clashEyebrow", () => {
  it("counts the two states separately", () => {
    expect(clashEyebrow([])).toBe("Interference");
    expect(clashEyebrow([pair("a", "b", 1)])).toBe("Interference · 1");
    expect(clashEyebrow([pair("a", "b", 1, true)])).toBe(
      "Interference · 1 unverified",
    );
    expect(clashEyebrow([pair("a", "b", 1), pair("a", "c", 2, true)])).toBe(
      "Interference · 1 · 1 unverified",
    );
  });
});

describe("clashInstanceIds", () => {
  it("badges a measured clash red and an unmeasurable pair as unverified", () => {
    const ids = clashInstanceIds([pair("a", "b", 1), pair("c", "d", 2, true)]);
    expect([...ids.measured].sort()).toEqual(["a", "b"]);
    expect([...ids.unverifiedOnly].sort()).toEqual(["c", "d"]);
    expect([...ids.flagged].sort()).toEqual(["a", "b", "c", "d"]);
  });

  it("lets a measured clash outrank an unverified pair on the same instance", () => {
    const ids = clashInstanceIds([pair("a", "b", 1), pair("b", "c", 2, true)]);
    expect(ids.measured.has("b")).toBe(true);
    expect(ids.unverifiedOnly.has("b")).toBe(false);
    expect([...ids.unverifiedOnly]).toEqual(["c"]);
  });

  it("is empty for a clash-free report", () => {
    const ids = clashInstanceIds([]);
    expect(ids.flagged.size).toBe(0);
  });
});
