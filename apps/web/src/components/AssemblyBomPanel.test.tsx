/**
 * AssemblyBomPanel — SolidWorks' three BOM types over one read model (ASM-A3):
 * top level by default (a sub-assembly is one line), indented with per-parent
 * and all-levels counts, and parts only with the total of placed parts.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AssemblyBomResponse } from "../api/bom";
import { AssemblyBomPanel } from "./AssemblyBomPanel";

const line = (
  id: string,
  name: string,
  kind: "part" | "assembly",
  quantity: number,
) => ({
  ref_document_id: id,
  ref_document_kind: kind,
  name,
  missing: false,
  quantity,
});

const BOM: AssemblyBomResponse = {
  assembly_id: "bike",
  lines: [
    line("frame", "Frame", "part", 1),
    line("wheel", "Wheel", "assembly", 2),
  ],
  total_instances: 3,
  indented: [
    {
      ...line("frame", "Frame", "part", 1),
      item: "1",
      level: 0,
      total_quantity: 1,
    },
    {
      ...line("wheel", "Wheel", "assembly", 2),
      item: "2",
      level: 0,
      total_quantity: 2,
    },
    {
      ...line("hub", "Hub", "part", 1),
      item: "2.1",
      level: 1,
      total_quantity: 2,
    },
    {
      ...line("rim", "Rim", "part", 1),
      item: "2.2",
      level: 1,
      total_quantity: 2,
    },
  ],
  parts_only: [
    line("frame", "Frame", "part", 1),
    line("hub", "Hub", "part", 2),
    line("rim", "Rim", "part", 2),
  ],
  total_parts: 5,
};

function rows() {
  return screen.getAllByTestId("bom-row").map((row) => ({
    item: row.dataset.item,
    name: within(row).getByTestId("bom-name").textContent,
    qty: within(row).getByTestId("bom-quantity").textContent,
    all: within(row).queryByTestId("bom-total-quantity")?.textContent ?? null,
  }));
}

describe("AssemblyBomPanel", () => {
  it("shows the top level by default", () => {
    render(<AssemblyBomPanel bom={BOM} loading={false} error={null} />);
    expect(rows().map((r) => [r.name, r.qty])).toEqual([
      ["Frame", "1"],
      ["Wheel", "2"],
    ]);
    expect(screen.getByTestId("bom-total").textContent).toBe("3");
  });

  it("opens sub-assemblies in the indented view", () => {
    render(<AssemblyBomPanel bom={BOM} loading={false} error={null} />);
    fireEvent.click(screen.getByTestId("bom-view-indented"));
    expect(rows()).toEqual([
      { item: "1", name: "Frame", qty: "1", all: "1" },
      { item: "2", name: "Wheel", qty: "2", all: "2" },
      { item: "2.1", name: "Hub", qty: "1", all: "2" },
      { item: "2.2", name: "Rim", qty: "1", all: "2" },
    ]);
  });

  it("counts every placed part in the parts-only view", () => {
    render(<AssemblyBomPanel bom={BOM} loading={false} error={null} />);
    fireEvent.click(screen.getByTestId("bom-view-parts"));
    expect(rows().map((r) => [r.name, r.qty])).toEqual([
      ["Frame", "1"],
      ["Hub", "2"],
      ["Rim", "2"],
    ]);
    expect(screen.getByTestId("bom-total").textContent).toBe("5");
  });
});
