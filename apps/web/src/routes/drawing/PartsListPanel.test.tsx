/**
 * The drawing's parts list in each structure (DRAWING-PARTS-LIST-LEVEL): the
 * balloon shows the server's full item ('4.3'), an indented row is inset by
 * its level with the All column beside it, and the structure control reports
 * the user's choice.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DrawingBomLine, PartsListStructure } from "../../api/drawings";
import { PartsListPanel } from "./SheetPanels";

function line(
  item: string,
  name: string,
  quantity: number,
  total: number,
  kind: "part" | "assembly" = "part",
): DrawingBomLine {
  const parts = item.split(".");
  return {
    item,
    item_number: Number(parts[parts.length - 1]),
    level: parts.length - 1,
    total_quantity: total,
    quantity,
    name,
    missing: false,
    ref_document_id: `00000000-0000-4000-8000-${item.replace(".", "0").padStart(12, "0")}`,
    ref_document_kind: kind,
  };
}

const INDENTED = [
  line("1", "Frame", 1, 1),
  line("2", "Crankset", 1, 1, "assembly"),
  line("2.1", "Crank arm", 2, 2),
  line("3", "Wheel", 2, 2, "assembly"),
  line("3.1", "Spoke", 32, 64),
];

function renderPanel(
  structure: PartsListStructure,
  lines: DrawingBomLine[],
  onStructureChange = vi.fn(),
) {
  render(
    <PartsListPanel
      sourceKind="assembly"
      lines={lines}
      total={4}
      structure={structure}
      structureBusy={false}
      onStructureChange={onStructureChange}
      loading={false}
      error={null}
      onOpen={vi.fn()}
    />,
  );
  return onStructureChange;
}

describe("PartsListPanel structure", () => {
  it("numbers indented rows with the full item and shows both quantities", () => {
    renderPanel("indented", INDENTED);
    const rows = screen.getAllByTestId("parts-list-row");
    expect(rows.map((row) => row.getAttribute("data-item-number"))).toEqual([
      "1",
      "2",
      "2.1",
      "3",
      "3.1",
    ]);
    const spoke = rows[4]!;
    expect(spoke.getAttribute("data-level")).toBe("1");
    expect(
      within(spoke).getByTestId("parts-list-item-number").textContent,
    ).toBe("3.1");
    expect(within(spoke).getByTestId("parts-list-qty").textContent).toBe("32");
    expect(within(spoke).getByTestId("parts-list-total-qty").textContent).toBe(
      "64",
    );
    expect(screen.getByRole("columnheader", { name: "All" })).toBeTruthy();
  });

  it("has no All column at the top level, and reports a new choice", () => {
    const onChange = renderPanel("top_level", [line("1", "Frame", 1, 1)]);
    expect(screen.queryByTestId("parts-list-total-qty")).toBeNull();
    expect(screen.getByTestId("parts-list-panel").dataset.structure).toBe(
      "top_level",
    );
    fireEvent.click(screen.getByTestId("parts-list-structure-parts"));
    expect(onChange).toHaveBeenCalledWith("parts_only");
  });

  it("offers no structure choice on a part-sourced sheet", () => {
    render(
      <PartsListPanel
        sourceKind="part"
        lines={[]}
        total={0}
        structure="top_level"
        structureBusy={false}
        onStructureChange={vi.fn()}
        loading={false}
        error={null}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("parts-list-structure-top")).toBeNull();
  });
});
