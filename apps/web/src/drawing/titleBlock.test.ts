import { describe, expect, it } from "vitest";

import type { ComposedTitleBlock } from "../api/drawings";
import { titleBlockFields } from "./titleBlock";

/** A placed title block with the given free-text fields; the geometry fields are
 * fixed (irrelevant to the row-selection logic under test). */
function block(
  fields: Pick<ComposedTitleBlock, "author" | "date" | "notes">,
): ComposedTitleBlock {
  return {
    x: 100,
    y: 180,
    width: 92,
    height: 30,
    split_x: 150,
    mid_y: 195,
    title: "Bracket",
    scale: "1:1",
    size: "A4",
    ...fields,
  };
}

describe("titleBlockFields", () => {
  it("renders DRAWN / DATE / NOTES rows for every authored field, in order", () => {
    const rows = titleBlockFields(
      block({ author: "J. Cobb", date: "2026-07-23", notes: "Deburr edges" }),
    );
    expect(rows.map((r) => r.caption)).toEqual(["DRAWN", "DATE", "NOTES"]);
    expect(rows.map((r) => r.key)).toEqual(["author", "date", "notes"]);
    expect(rows.map((r) => r.value)).toEqual([
      "J. Cobb",
      "2026-07-23",
      "Deburr edges",
    ]);
    // Fixed per-field baselines — a present field keeps its place.
    expect(rows.map((r) => r.dy)).toEqual([20.5, 23.5, 26.5]);
  });

  it("skips a null field but keeps the others at their fixed baselines", () => {
    const rows = titleBlockFields(
      block({ author: "J. Cobb", date: null, notes: "Deburr edges" }),
    );
    expect(rows.map((r) => r.key)).toEqual(["author", "notes"]);
    expect(rows.map((r) => r.dy)).toEqual([20.5, 26.5]);
  });

  it("emits no rows when a title block has no free-text (byte-identical)", () => {
    expect(
      titleBlockFields(block({ author: null, date: null, notes: null })),
    ).toEqual([]);
  });
});
