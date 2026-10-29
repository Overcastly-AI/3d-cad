import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  type ComposedMaterialsTable,
  MaterialsTable,
  tableCells,
} from "./MaterialsTable";

const TABLE: ComposedMaterialsTable = {
  x: 16,
  y: 22,
  width: 200,
  height: 26,
  row_height: 5.2,
  text_mm: 2.6,
  columns: ["Item", "Qty", "Size", "Length", "Material", "Price"],
  column_dx: [0, 36, 54, 82, 114, 174],
  column_w: [36, 18, 28, 32, 60, 26],
  align: ["left", "right", "left", "left", "left", "right"],
  blocks: [
    {
      x: 16,
      y: 22,
      width: 200,
      height: 26,
      header_y: 25.6,
      rows: [
        { kind: "group", y: 30.8, cells: ["WALLS"] },
        {
          kind: "line",
          y: 36,
          cells: ["Stud", "48", "2x6", "8 ft", "SPF", "$239.04"],
        },
        { kind: "total", y: 41.2, cells: ["Total", "", "", "", "", "$239.04"] },
      ],
    },
  ],
};

describe("MaterialsTable", () => {
  it("sets each cell where the server's emitters set it", () => {
    expect(
      tableCells(TABLE, 16, ["Stud", "48", "", "8 ft", "SPF", "$239.04"]),
    ).toEqual([
      { text: "Stud", x: 17.4, anchor: "start" },
      { text: "48", x: 16 + 36 + 18 - 1.4, anchor: "end" },
      { text: "8 ft", x: 16 + 82 + 1.4, anchor: "start" },
      { text: "SPF", x: 16 + 114 + 1.4, anchor: "start" },
      { text: "$239.04", x: 16 + 174 + 26 - 1.4, anchor: "end" },
    ]);
    // A system heading spans the row from the first column.
    expect(tableCells(TABLE, 16, ["WALLS"])).toEqual([
      { text: "WALLS", x: 17.4, anchor: "start" },
    ]);
  });

  it("draws every row with its kind", () => {
    render(
      <svg>
        <MaterialsTable table={TABLE} />
      </svg>,
    );
    expect(screen.getByTestId("drawing-materials-table")).toHaveAttribute(
      "aria-label",
      "Materials list, 1 lines",
    );
    const rows = screen.getAllByTestId("drawing-materials-row");
    expect(rows.map((r) => r.getAttribute("data-row-kind"))).toEqual([
      "group",
      "line",
      "total",
    ]);
    expect(
      screen.getAllByTestId("drawing-materials-cell").map((c) => c.textContent),
    ).toEqual([
      "WALLS",
      "Stud",
      "48",
      "2x6",
      "8 ft",
      "SPF",
      "$239.04",
      "Total",
      "$239.04",
    ]);
  });
});
