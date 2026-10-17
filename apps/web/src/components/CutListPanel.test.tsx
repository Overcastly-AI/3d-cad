/**
 * CutListPanel (CUT-LIST): the gateway's lines, formatted in the document's
 * unit; an unclassified body reads with its measured section; CSV downloads
 * the server's file.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CutListResponse } from "../api/cutList";
import { CutListPanel } from "./CutListPanel";

const IN = 25.4;

const RESPONSE: CutListResponse = {
  document_id: "p1",
  document_kind: "part",
  name: "B1 deck",
  length_unit: "in",
  total_quantity: 15,
  unclassified: 1,
  missing: [{ ref_document_id: "gone", quantity: 2 }],
  lines: [
    {
      member: "Joist",
      profile: "2x10",
      material: "southern_pine_pt",
      classification: "member",
      quantity: 13,
      length_mm: 141 * IN,
      total_length_mm: 1833 * IN,
      section_mm: [1.5 * IN, 9.25 * IN],
      stock_length_ft: 12,
      waste_mm: 3 * IN,
    },
    {
      member: null,
      profile: "6x6",
      material: null,
      classification: "matched",
      quantity: 1,
      length_mm: 10.5 * IN,
      total_length_mm: 10.5 * IN,
      section_mm: [5.5 * IN, 5.5 * IN],
      stock_length_ft: 8,
      waste_mm: 85.5 * IN,
    },
    {
      member: null,
      profile: null,
      material: null,
      classification: "unclassified",
      quantity: 1,
      length_mm: 30 * IN,
      total_length_mm: 30 * IN,
      section_mm: [1 * IN, 2 * IN],
      stock_length_ft: null,
      waste_mm: null,
    },
  ],
};

const csv = vi.hoisted(() => ({
  exportCutListCsv: vi.fn(),
  downloadBlob: vi.fn(),
}));

vi.mock("../api/cutList", () => ({
  fetchCutList: vi.fn(() => Promise.resolve(RESPONSE)),
  exportCutListCsv: csv.exportCutListCsv,
}));

vi.mock("../api/exportPart", () => ({ downloadBlob: csv.downloadBlob }));

vi.mock("../api/materials", () => ({
  fetchMaterials: vi.fn(() =>
    Promise.resolve([
      {
        key: "southern_pine_pt",
        name: "Southern pine, pressure-treated",
        density_kg_m3: 582,
        source: "",
      },
    ]),
  ),
}));

function renderPanel() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <CutListPanel kind="part" documentId="p1" revision={3} />
    </QueryClientProvider>,
  );
}

describe("CutListPanel", () => {
  it("lists each line in the document unit with its stock", async () => {
    renderPanel();
    const rows = await screen.findAllByTestId("cut-list-row");
    expect(rows).toHaveLength(3);
    const joist = within(rows[0]!);
    expect(joist.getByTestId("cut-list-member")).toHaveTextContent("Joist");
    expect(joist.getByTestId("cut-list-qty")).toHaveTextContent("13");
    expect(joist.getByTestId("cut-list-length")).toHaveTextContent("141");
    expect(joist.getByTestId("cut-list-total-length")).toHaveTextContent(
      "1,833",
    );
    expect(joist.getByTestId("cut-list-stock")).toHaveTextContent("12 ft");
    await waitFor(() =>
      expect(joist.getByTestId("cut-list-caption")).toHaveTextContent(
        "2x10 · Southern pine, pressure-treated",
      ),
    );
    // A matched body names its profile; an unclassified one its section.
    expect(within(rows[1]!).getByTestId("cut-list-member")).toHaveTextContent(
      "6x6",
    );
    expect(within(rows[2]!).getByTestId("cut-list-caption")).toHaveTextContent(
      "Unclassified · 1 × 2 in",
    );
    expect(within(rows[2]!).getByTestId("cut-list-stock")).toHaveTextContent(
      "—",
    );
    expect(screen.getByTestId("cut-list-total")).toHaveTextContent("15");
    expect(screen.getByTestId("cut-list-unclassified")).toHaveTextContent(
      "1 unclassified",
    );
    expect(screen.getByTestId("cut-list-missing")).toHaveTextContent(
      "2 placements of deleted parts are not listed.",
    );
  });

  it("downloads the server's CSV", async () => {
    const blob = new Blob(["Item"], { type: "text/csv" });
    csv.exportCutListCsv.mockResolvedValue({
      blob,
      filename: "B1 deck cut list.csv",
    });
    renderPanel();
    await screen.findAllByTestId("cut-list-row");
    fireEvent.click(screen.getByTestId("cut-list-csv"));
    await waitFor(() =>
      expect(csv.downloadBlob).toHaveBeenCalledWith(
        blob,
        "B1 deck cut list.csv",
      ),
    );
    expect(csv.exportCutListCsv).toHaveBeenCalledWith("part", "p1");
  });
});
