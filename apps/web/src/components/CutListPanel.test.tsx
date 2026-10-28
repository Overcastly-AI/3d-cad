/**
 * CutListPanel (CUT-LIST): the gateway's lines, formatted in the document's
 * unit; an unclassified body reads with its measured section; CSV downloads
 * the server's file. Prices (CUT-LIST-PRICES) are the gateway's, formatted
 * from integer cents; an unpriced line is blank, never $0, and its blank
 * opens the Price book pre-filled. Sheet goods (SHEATHING) read their net
 * area and the sheets it needs.
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

import {
  type CutListLine,
  type CutListResponse,
  fetchCutList,
} from "../api/cutList";
import {
  CutListPanel,
  groupBySystem,
  spliceLabel,
  SYSTEM_LABEL,
  unpricedLabel,
} from "./CutListPanel";

const IN = 25.4;

const RESPONSE: CutListResponse = {
  document_id: "p1",
  document_kind: "part",
  name: "B1 deck",
  length_unit: "in",
  total_quantity: 15,
  unclassified: 1,
  missing: [{ ref_document_id: "gone", quantity: 2 }],
  currency: "USD",
  total_price_cents: 25974,
  unpriced_lines: 2,
  lines: [
    {
      system: "deck",
      member: "Joist",
      profile: "2x10",
      material: "southern_pine_pt",
      classification: "member",
      quantity: 13,
      length_mm: 141 * IN,
      total_length_mm: 1833 * IN,
      section_mm: [1.5 * IN, 9.25 * IN],
      stock_length_ft: 12,
      stock_pieces_ft: [12],
      waste_mm: 3 * IN,
      stock_quantity: 13,
      unit_price_cents: 1998,
      price_unit: "each",
      extended_price_cents: 25974,
    },
    {
      system: "other",
      member: null,
      profile: "6x6",
      material: "southern_pine_pt",
      classification: "matched",
      quantity: 1,
      length_mm: 10.5 * IN,
      total_length_mm: 10.5 * IN,
      section_mm: [5.5 * IN, 5.5 * IN],
      stock_length_ft: 8,
      stock_pieces_ft: [8],
      waste_mm: 85.5 * IN,
      // No entry in the book: blank, never 0.
      stock_quantity: 1,
      unit_price_cents: null,
      price_unit: null,
      extended_price_cents: null,
    },
    {
      system: "other",
      member: null,
      profile: null,
      material: null,
      classification: "unclassified",
      quantity: 1,
      length_mm: 30 * IN,
      total_length_mm: 30 * IN,
      section_mm: [1 * IN, 2 * IN],
      stock_length_ft: null,
      stock_pieces_ft: null,
      waste_mm: null,
      stock_quantity: null,
      unit_price_cents: null,
      price_unit: null,
      extended_price_cents: null,
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

vi.mock("../api/priceBook", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/priceBook")>()),
  fetchPriceBook: vi.fn(() =>
    Promise.resolve({
      currency: "USD",
      entries: [],
      updated_at: null,
      version: 0,
    }),
  ),
}));

vi.mock("../api/materials", () => ({
  fetchMaterialLibrary: vi.fn(() =>
    Promise.resolve({
      materials: [
        {
          key: "southern_pine_pt",
          name: "Southern pine, pressure-treated",
          density_kg_m3: 582,
          source: "",
        },
      ],
      profiles: [
        { key: "us_6x6", name: "6x6" },
        { key: "us_2x6", name: "2x6" },
      ],
      sheet_goods: [{ key: "osb_7_16", name: "7/16 OSB", material: "osb" }],
      opening_units: [
        {
          key: "window_3040",
          code: "3040",
          kind: "window",
          name: "Window 3040",
          label: `3'0" x 4'0"`,
          material: "pvc",
          width_in: 36,
          height_in: 48,
          ro_width_in: 36.5,
          ro_height_in: 48.5,
        },
      ],
      sheet_sizes: [
        { key: "4x8", width_in: 48, length_in: 96 },
        { key: "4x9", width_in: 48, length_in: 108 },
      ],
      foundation_items: [
        {
          key: "ready_mix",
          kind: "concrete",
          name: "Ready-mix concrete",
          material: "concrete",
          price_unit: "cubic_yard",
          stock_length_ft: null,
        },
        {
          key: "rebar_4",
          kind: "rebar",
          name: "#4 rebar",
          material: "steel_a615",
          price_unit: "each",
          stock_length_ft: 20,
        },
        {
          key: "anchor_bolt_1_2",
          kind: "anchor_bolt",
          name: "1/2 in anchor bolt",
          material: "steel_f1554",
          price_unit: "each",
          stock_length_ft: null,
        },
        {
          key: "foundation_vent",
          kind: "foundation_vent",
          name: "Foundation vent",
          material: "steel_1018",
          price_unit: "each",
          stock_length_ft: null,
        },
        {
          key: "crawl_access_door",
          kind: "access_door",
          name: "Crawl-space access door",
          material: "steel_1018",
          price_unit: "each",
          stock_length_ft: null,
        },
        {
          key: "concrete_bag_80",
          kind: "concrete",
          name: "Concrete, 80 lb bag",
          material: "concrete",
          price_unit: "each",
          stock_length_ft: null,
        },
        {
          key: "post_base_6x6",
          kind: "post_base",
          name: "Post base 6x6 (ABU66)",
          material: "steel_1018",
          price_unit: "each",
          stock_length_ft: null,
        },
      ],
    }),
  ),
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

  it("prices each line from integer cents and totals the priced ones", async () => {
    renderPanel();
    const rows = await screen.findAllByTestId("cut-list-row");
    const joist = within(rows[0]!);
    expect(joist.getByTestId("cut-list-unit-price")).toHaveTextContent(
      "$19.98",
    );
    expect(joist.getByTestId("cut-list-unit-price")).toHaveAttribute(
      "title",
      "Each at 12 ft: one stock piece",
    );
    expect(joist.getByTestId("cut-list-ext-price")).toHaveTextContent(
      "$259.74",
    );
    // Unpriced: blank, never $0.
    for (const row of rows.slice(1)) {
      expect(
        within(row).getByTestId("cut-list-unit-price"),
      ).not.toHaveTextContent("$");
      expect(
        within(row).getByTestId("cut-list-ext-price"),
      ).toBeEmptyDOMElement();
    }
    // A line with no stock length has nothing the book could price.
    expect(within(rows[2]!).queryByTestId("cut-list-price-blank")).toBeNull();
    expect(screen.getByTestId("cut-list-price-total")).toHaveTextContent(
      "$259.74",
    );
    expect(screen.getByTestId("cut-list-unpriced")).toHaveTextContent(
      "2 lines unpriced",
    );
    for (const name of ["Unit price", "Ext. price"]) {
      expect(screen.getByRole("columnheader", { name })).toBeInTheDocument();
    }
    expect(
      screen.getByRole("rowheader", { name: /Total/ }),
    ).toBeInTheDocument();
  });

  it("opens the Price book pre-filled from a blank price", async () => {
    renderPanel();
    const rows = await screen.findAllByTestId("cut-list-row");
    fireEvent.click(
      within(rows[1]!).getByRole("button", { name: "Price 6x6, 6x6 at 8 ft" }),
    );
    expect(
      screen.getByRole("dialog", { name: "Price book" }),
    ).toBeInTheDocument();
    const seeded = await screen.findByTestId("price-book-row");
    expect(seeded).toHaveAttribute("data-profile", "us_6x6");
    expect(within(seeded).getByLabelText("Stock length, price 1")).toHaveValue(
      "8",
    );
    fireEvent.click(screen.getByTestId("price-book-cancel"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("lists sheet goods by area and the sheets they are cut from", async () => {
    // B2's 7/16 OSB (SHEET-COUNT-PIECES): 12 panels, 45 893 in^2, cut from
    // 11 sheets of 4x9, 11 131 in^2 offcut.
    vi.mocked(fetchCutList).mockResolvedValueOnce({
      ...RESPONSE,
      total_quantity: 12,
      unclassified: 0,
      missing: [],
      total_price_cents: null,
      unpriced_lines: 1,
      lines: [
        {
          system: "sheathing",
          member: "Sheathing",
          profile: "7/16 OSB",
          material: "osb",
          classification: "member",
          quantity: 12,
          length_mm: 108 * IN,
          total_length_mm: 972 * IN,
          section_mm: [0.4375 * IN, 48 * IN],
          sheet: "4x9",
          area_mm2: 45893 * IN * IN,
          offcut_area_mm2: 11131 * IN * IN,
          stock_length_ft: null,
          stock_pieces_ft: null,
          waste_mm: null,
          stock_quantity: 11,
          unit_price_cents: null,
          price_unit: null,
          extended_price_cents: null,
        },
      ],
    });
    renderPanel();
    const [row] = await screen.findAllByTestId("cut-list-row");
    const sheet = within(row!);
    expect(row).toHaveAttribute("data-sheet", "4x9");
    expect(sheet.getByTestId("cut-list-qty")).toHaveTextContent("12");
    expect(sheet.getByTestId("cut-list-area")).toHaveTextContent("45,893 in²");
    expect(sheet.getByTestId("cut-list-total-length")).toBeEmptyDOMElement();
    expect(sheet.getByTestId("cut-list-stock")).toHaveTextContent("11 × 4x9");
    expect(sheet.getByTestId("cut-list-stock")).toHaveAttribute(
      "title",
      "11 sheets of 4x9, cut from the panels; 11,131 in² offcut",
    );
    // Its blank price opens the book on a per-sheet row for its sheet.
    fireEvent.click(
      sheet.getByRole("button", {
        name: "Price Sheathing, 7/16 OSB 4x9 sheet",
      }),
    );
    const seeded = await screen.findByTestId("price-book-row");
    expect(seeded).toHaveAttribute("data-profile", "osb_7_16");
    expect(within(seeded).getByLabelText("Sheet, price 1")).toHaveValue("4x9");
  });

  it("lists a window unit by its size and kind, and prices it from its blank", async () => {
    // OPENING-UNITS: B7's three 3040s, one Each line, not in the book yet.
    const unit: CutListLine = {
      member: "Window",
      profile: "3040",
      material: "pvc",
      classification: "member",
      quantity: 3,
      length_mm: 48 * IN,
      total_length_mm: 144 * IN,
      section_mm: [3.5 * IN, 36 * IN],
      system: "walls",
      unit: "window",
      unit_key: "window_3040",
      stock_length_ft: null,
      stock_pieces_ft: null,
      waste_mm: null,
      stock_quantity: 3,
      unit_price_cents: null,
      price_unit: null,
      extended_price_cents: null,
    };
    vi.mocked(fetchCutList).mockResolvedValueOnce({
      ...RESPONSE,
      total_quantity: 4,
      unclassified: 0,
      missing: [],
      total_price_cents: null,
      unpriced_lines: 2,
      // A custom size has no key: listed, but no catalogue entry prices it.
      lines: [
        unit,
        {
          ...unit,
          profile: "30 x 40 in",
          quantity: 1,
          stock_quantity: 1,
          unit_key: null,
        },
      ],
    });
    renderPanel();
    const [row, custom] = await screen.findAllByTestId("cut-list-row");
    const line = within(row!);
    expect(line.getByTestId("cut-list-stock")).toHaveTextContent("3040 window");
    expect(within(custom!).getByTestId("cut-list-stock")).toHaveTextContent(
      "30 x 40 in window",
    );
    expect(within(custom!).queryByTestId("cut-list-price-blank")).toBeNull();
    // The full view lists the unit the same way, and prices it from there.
    fireEvent.click(screen.getByTestId("cut-list-expand"));
    const view = within(screen.getByTestId("cut-list-expanded"));
    const [wide] = view.getAllByTestId("cut-list-row");
    expect(within(wide!).getByTestId("cut-list-stock")).toHaveTextContent(
      "3040 window",
    );
    fireEvent.click(
      within(wide!).getByRole("button", {
        name: "Price Window, 3040 window unit",
      }),
    );
    const seeded = await screen.findByTestId("price-book-row");
    expect(seeded).toHaveAttribute("data-profile", "window_3040");
    expect(seeded).toHaveAttribute("data-kind", "unit");
    expect(seeded).toHaveAttribute("data-material", "pvc");
    expect(
      within(seeded).getByTestId("price-book-stock-unit"),
    ).toHaveTextContent("Unit");
    await waitFor(() =>
      expect(
        within(seeded).getByLabelText("Price in dollars, price 1"),
      ).toHaveFocus(),
    );
  });

  it("lists B8's pour by the yard, its rebar by the stick and its bolts", async () => {
    // SLAB: 308 736 in³ = 6.62 yd³ net, 7.00 ordered with 5%; 2 loops of
    // 912 in in 10 sticks; 19 anchor bolts. The concrete is priced.
    const none = {
      stock_pieces_ft: null,
      waste_mm: null,
      section_mm: [0, 0],
    };
    const lines: CutListLine[] = [
      {
        ...none,
        system: "foundation",
        member: "Slab",
        profile: "Ready-mix concrete",
        material: "concrete",
        classification: "member",
        quantity: 1,
        length_mm: 288 * IN,
        total_length_mm: 288 * IN,
        stock_length_ft: null,
        stock_quantity: null,
        unit_price_cents: 16500,
        price_unit: "cubic_yard",
        extended_price_cents: 115500,
        item: "concrete",
        volume_mm3: 308736 * IN ** 3,
        order_yd3: 7,
        waste_percent: 5,
      },
      {
        ...none,
        system: "foundation",
        member: "Rebar",
        profile: "#4 rebar",
        material: "steel_a615",
        classification: "member",
        quantity: 2,
        length_mm: 912 * IN,
        total_length_mm: 1824 * IN,
        stock_length_ft: 20,
        stock_quantity: 10,
        unit_price_cents: null,
        price_unit: null,
        extended_price_cents: null,
        item: "rebar",
      },
      {
        ...none,
        system: "foundation",
        member: "Anchor bolt",
        profile: "1/2 in anchor bolt",
        material: "steel_f1554",
        classification: "member",
        quantity: 19,
        length_mm: 0,
        total_length_mm: 0,
        stock_length_ft: null,
        stock_quantity: 19,
        unit_price_cents: null,
        price_unit: null,
        extended_price_cents: null,
        item: "anchor_bolt",
      },
    ];
    vi.mocked(fetchCutList).mockResolvedValueOnce({
      ...RESPONSE,
      total_quantity: 22,
      unclassified: 0,
      missing: [],
      total_price_cents: 115500,
      unpriced_lines: 2,
      lines,
    });
    renderPanel();
    const [slab, rebar, bolts] = await screen.findAllByTestId("cut-list-row");
    const pour = within(slab!);
    expect(pour.getByTestId("cut-list-volume")).toHaveTextContent("6.62 yd³");
    expect(pour.getByTestId("cut-list-total-length")).toBeEmptyDOMElement();
    expect(pour.getByTestId("cut-list-stock")).toHaveTextContent("7.00 yd³");
    expect(pour.getByTestId("cut-list-stock")).toHaveAttribute(
      "title",
      "6.62 yd³ + 5% waste, rounded up to 1/4 yd³",
    );
    expect(pour.getByTestId("cut-list-unit-price")).toHaveTextContent(
      "$165.00",
    );
    expect(pour.getByTestId("cut-list-ext-price")).toHaveTextContent(
      "$1,155.00",
    );
    expect(within(rebar!).getByTestId("cut-list-length")).toHaveTextContent(
      "912",
    );
    expect(within(rebar!).getByTestId("cut-list-stock")).toHaveTextContent(
      "10 × 20 ft",
    );
    expect(within(bolts!).getByTestId("cut-list-length")).toHaveTextContent(
      "—",
    );
    expect(within(bolts!).getByTestId("cut-list-stock")).toHaveTextContent(
      "Each",
    );
    // A blank price opens the book on the item, priced its one way.
    fireEvent.click(within(rebar!).getByTestId("cut-list-price-blank"));
    const seeded = await screen.findByTestId("price-book-row");
    expect(seeded).toHaveAttribute("data-profile", "rebar_4");
    expect(seeded).toHaveAttribute("data-kind", "item");
    expect(seeded).toHaveAttribute("data-unit", "each");
    expect(
      within(seeded).getByTestId("price-book-stock-item"),
    ).toHaveTextContent("20 ft");
  });

  it("lists B9's vents and access door Each, priced as a foundation item", async () => {
    // FOUNDATION-TAKEOFF: 5 vents 16 x 8 and 1 access door 24 x 16.
    const each = {
      stock_pieces_ft: null,
      waste_mm: null,
      section_mm: [0, 0],
      system: "foundation" as const,
      classification: "member" as const,
      length_mm: 0,
      total_length_mm: 0,
      stock_length_ft: null,
      material: "steel_1018" as const,
    };
    const lines: CutListLine[] = [
      {
        ...each,
        member: "Vent 16 x 8",
        profile: "Foundation vent",
        quantity: 5,
        stock_quantity: 5,
        unit_price_cents: 1298,
        price_unit: "each",
        extended_price_cents: 6490,
        item: "foundation_vent",
      },
      {
        ...each,
        member: "Access door 24 x 16",
        profile: "Crawl-space access door",
        quantity: 1,
        stock_quantity: 1,
        unit_price_cents: null,
        price_unit: null,
        extended_price_cents: null,
        item: "access_door",
      },
    ];
    vi.mocked(fetchCutList).mockResolvedValueOnce({
      ...RESPONSE,
      total_quantity: 6,
      unclassified: 0,
      missing: [],
      total_price_cents: 6490,
      unpriced_lines: 1,
      lines,
    });
    renderPanel();
    const [vents, door] = await screen.findAllByTestId("cut-list-row");
    for (const row of [vents!, door!]) {
      expect(within(row).getByTestId("cut-list-length")).toHaveTextContent("—");
      expect(
        within(row).getByTestId("cut-list-total-length"),
      ).toBeEmptyDOMElement();
      expect(within(row).getByTestId("cut-list-stock")).toHaveTextContent(
        "Each",
      );
    }
    expect(within(vents!).getByTestId("cut-list-member")).toHaveTextContent(
      "Vent 16 x 8",
    );
    expect(within(vents!).getByTestId("cut-list-unit-price")).toHaveAttribute(
      "title",
      "Each, per unit",
    );
    // The door's blank price opens the book on its key, Each.
    fireEvent.click(within(door!).getByTestId("cut-list-price-blank"));
    const seeded = await screen.findByTestId("price-book-row");
    expect(seeded).toHaveAttribute("data-profile", "crawl_access_door");
    expect(seeded).toHaveAttribute("data-kind", "item");
    expect(seeded).toHaveAttribute("data-unit", "each");
  });

  it("lists B1's footings in whole bags and its post bases Each", async () => {
    // DECK-FOOTINGS: 3 piers, 7 238.23 in³ = 0.16 yd³; x 1.05 / 0.60 ft³ is
    // 7.33, so 8 bags at $6.48; 3 post bases, unpriced.
    const none = {
      stock_pieces_ft: null,
      waste_mm: null,
      section_mm: [0, 0],
    };
    const lines: CutListLine[] = [
      {
        ...none,
        system: "foundation",
        member: "Footing",
        profile: "Concrete, 80 lb bag",
        material: "concrete",
        classification: "member",
        quantity: 3,
        length_mm: 16 * IN,
        total_length_mm: 48 * IN,
        stock_length_ft: null,
        stock_quantity: 8,
        unit_price_cents: 648,
        price_unit: "each",
        extended_price_cents: 5184,
        item: "concrete",
        volume_mm3: 7238.229473870882 * IN ** 3,
        order_yd3: null,
        waste_percent: 5,
        bags: 8,
      },
      {
        ...none,
        system: "foundation",
        member: "Post base",
        profile: "Post base 6x6 (ABU66)",
        material: "steel_1018",
        classification: "member",
        quantity: 3,
        length_mm: 0,
        total_length_mm: 0,
        stock_length_ft: null,
        stock_quantity: 3,
        unit_price_cents: null,
        price_unit: null,
        extended_price_cents: null,
        item: "post_base",
      },
    ];
    vi.mocked(fetchCutList).mockResolvedValueOnce({
      ...RESPONSE,
      total_quantity: 6,
      unclassified: 0,
      missing: [],
      total_price_cents: 5184,
      unpriced_lines: 1,
      lines,
    });
    renderPanel();
    const [footings, bases] = await screen.findAllByTestId("cut-list-row");
    const pour = within(footings!);
    expect(pour.getByTestId("cut-list-volume")).toHaveTextContent("0.16 yd³");
    expect(pour.getByTestId("cut-list-stock")).toHaveTextContent("8 bags");
    expect(pour.getByTestId("cut-list-stock")).toHaveAttribute(
      "title",
      "0.16 yd³ + 5% waste, in 80 lb bags of 0.60 ft³, rounded up to whole bags",
    );
    expect(pour.getByTestId("cut-list-unit-price")).toHaveAttribute(
      "title",
      "Each, per 80 lb bag",
    );
    expect(pour.getByTestId("cut-list-ext-price")).toHaveTextContent("$51.84");
    expect(pour.getByTestId("cut-list-ext-price")).toHaveAttribute(
      "title",
      "8 bags × $6.48",
    );
    expect(within(bases!).getByTestId("cut-list-length")).toHaveTextContent(
      "—",
    );
    expect(within(bases!).getByTestId("cut-list-stock")).toHaveTextContent(
      "Each",
    );
    // The post base's blank opens the book on it, Each with no stock.
    fireEvent.click(within(bases!).getByTestId("cut-list-price-blank"));
    const seeded = await screen.findByTestId("price-book-row");
    expect(seeded).toHaveAttribute("data-profile", "post_base_6x6");
    expect(seeded).toHaveAttribute("data-kind", "item");
    expect(seeded).toHaveAttribute("data-unit", "each");
  });

  it("shows a long member's splice and prices it per member", async () => {
    // B7's 288 in top plates and sills (CUT-LIST-LONG-STOCK): 24 ft, spliced.
    const plate = {
      system: "walls",
      member: "Top plate",
      profile: "2x6",
      material: "southern_pine_pt",
      classification: "member",
      quantity: 4,
      length_mm: 288 * IN,
      total_length_mm: 1152 * IN,
      section_mm: [1.5 * IN, 5.5 * IN],
      stock_length_ft: null,
      stock_pieces_ft: [16, 8],
      waste_mm: 0,
      stock_quantity: 4,
      unit_price_cents: 2046,
      price_unit: "each",
      extended_price_cents: 8184,
    } satisfies CutListLine;
    vi.mocked(fetchCutList).mockResolvedValueOnce({
      ...RESPONSE,
      total_quantity: 6,
      unclassified: 0,
      missing: [],
      total_price_cents: 8184,
      unpriced_lines: 1,
      lines: [
        plate,
        {
          ...plate,
          member: "Sill",
          quantity: 2,
          total_length_mm: 576 * IN,
          stock_pieces_ft: [12, 12],
          stock_quantity: 2,
          unit_price_cents: null,
          price_unit: null,
          extended_price_cents: null,
        },
      ],
    });
    renderPanel();
    const [top, sill] = await screen.findAllByTestId("cut-list-row");
    expect(within(top!).getByTestId("cut-list-stock")).toHaveTextContent(
      "16 ft + 8 ft",
    );
    expect(within(top!).getByTestId("cut-list-unit-price")).toHaveAttribute(
      "title",
      "Each: 16 ft + 8 ft: one member's spliced stock",
    );
    // Stock qty x unit price is the extended price: 4 sets x $20.46.
    expect(within(top!).getByTestId("cut-list-ext-price")).toHaveTextContent(
      "$81.84",
    );
    expect(within(top!).getByTestId("cut-list-ext-price")).toHaveAttribute(
      "title",
      "4 × (16 ft + 8 ft) × $20.46",
    );
    expect(within(sill!).getByTestId("cut-list-stock")).toHaveTextContent(
      "2 × 12 ft",
    );
    // Its blank opens the book on the splice's stock length.
    fireEvent.click(
      within(sill!).getByRole("button", {
        name: "Price Sill, 2x6 at 2 × 12 ft",
      }),
    );
    const seeded = await screen.findByTestId("price-book-row");
    expect(within(seeded).getByLabelText("Stock length, price 1")).toHaveValue(
      "12",
    );
  });

  it("says why a joist past 24 ft has no stock", async () => {
    // NO-SPLICE-SPANS: a joist is one piece, so past 24 ft it has no stock.
    vi.mocked(fetchCutList).mockResolvedValueOnce({
      ...RESPONSE,
      total_quantity: 2,
      unclassified: 0,
      missing: [],
      total_price_cents: null,
      unpriced_lines: 1,
      lines: [
        {
          system: "floor",
          member: "Joist",
          profile: "2x10",
          material: "spf_lumber",
          classification: "member",
          quantity: 2,
          length_mm: 300 * IN,
          total_length_mm: 600 * IN,
          section_mm: [1.5 * IN, 9.25 * IN],
          stock_length_ft: null,
          stock_pieces_ft: null,
          one_piece: true,
          stock_note:
            "One piece, longer than 24 ft stock: a joist is not spliced",
          waste_mm: null,
          stock_quantity: null,
          unit_price_cents: null,
          price_unit: null,
          extended_price_cents: null,
        },
      ],
    });
    renderPanel();
    const [joist] = await screen.findAllByTestId("cut-list-row");
    const stock = within(joist!).getByTestId("cut-list-stock");
    expect(stock).toHaveTextContent("—");
    expect(stock).toHaveAttribute(
      "title",
      "One piece, longer than 24 ft stock: a joist is not spliced",
    );
  });

  it("opens the book on every piece of an unpriced mixed splice", async () => {
    vi.mocked(fetchCutList).mockResolvedValueOnce({
      ...RESPONSE,
      total_quantity: 2,
      unclassified: 0,
      missing: [],
      total_price_cents: null,
      unpriced_lines: 1,
      lines: [
        {
          system: "floor",
          member: "Rim",
          profile: "2x6",
          material: "southern_pine_pt",
          classification: "member",
          quantity: 2,
          length_mm: 288 * IN,
          total_length_mm: 576 * IN,
          section_mm: [1.5 * IN, 5.5 * IN],
          stock_length_ft: null,
          stock_pieces_ft: [16, 8],
          waste_mm: 0,
          stock_quantity: 2,
          unit_price_cents: null,
          price_unit: null,
          extended_price_cents: null,
        },
      ],
    });
    renderPanel();
    const [rim] = await screen.findAllByTestId("cut-list-row");
    fireEvent.click(
      within(rim!).getByRole("button", {
        name: "Price Rim, 2x6 at 16 ft + 8 ft",
      }),
    );
    await waitFor(() =>
      expect(screen.getAllByTestId("price-book-row")).toHaveLength(2),
    );
    const rows = screen.getAllByTestId("price-book-row");
    expect(
      within(rows[0]!).getByLabelText("Stock length, price 1"),
    ).toHaveValue("16");
    expect(
      within(rows[1]!).getByLabelText("Stock length, price 2"),
    ).toHaveValue("8");
  });

  it("heads each system's lines as a group and never cuts a member's name", async () => {
    // CUT-LIST-PANEL: the gateway's order, a takeoff's categories.
    const base = RESPONSE.lines![0]!;
    vi.mocked(fetchCutList).mockResolvedValueOnce({
      ...RESPONSE,
      lines: [
        { ...base, system: "floor", member: "Sill" },
        { ...base, system: "walls", member: "Header" },
        { ...base, system: "walls", member: "Bottom plate, pressure-treated" },
        { ...base, system: "roof", member: "Rafter" },
      ],
    });
    renderPanel();
    await screen.findAllByTestId("cut-list-row");
    const groups = screen.getAllByTestId("cut-list-group");
    expect(groups.map((g) => g.dataset.system)).toEqual([
      "floor",
      "walls",
      "roof",
    ]);
    expect(
      screen.getAllByTestId("cut-list-group-label").map((g) => g.textContent),
    ).toEqual(["Floor1", "Walls2", "Roof1"]);
    const walls = within(groups[1]!).getAllByTestId("cut-list-member");
    expect(walls.map((m) => m.textContent)).toEqual([
      "Header",
      "Bottom plate, pressure-treated",
    ]);
    for (const member of walls) expect(member).not.toHaveClass("truncate");
    // The figures never wrap; the member column does.
    expect(
      within(groups[1]!).getAllByTestId("cut-list-ext-price")[0],
    ).toHaveClass("whitespace-nowrap");
  });

  it("does not head a list of one system", async () => {
    const base = RESPONSE.lines![0]!;
    vi.mocked(fetchCutList).mockResolvedValueOnce({
      ...RESPONSE,
      lines: [base, { ...base, member: "Rim" }],
    });
    renderPanel();
    await screen.findAllByTestId("cut-list-row");
    expect(screen.queryAllByTestId("cut-list-group-label")).toHaveLength(0);
  });

  it("groups runs of one system in the gateway's order", () => {
    const base = RESPONSE.lines![0]!;
    const groups = groupBySystem([
      { ...base, system: "floor" },
      { ...base, system: "floor" },
      { ...base, system: "sheathing" },
    ]);
    expect(groups.map((g) => [g.system, g.lines.map((l) => l.index)])).toEqual([
      ["floor", [0, 1]],
      ["sheathing", [2]],
    ]);
    expect(SYSTEM_LABEL.sheathing).toBe("Sheathing");
  });

  it("writes a splice as a framer does", () => {
    expect(spliceLabel([12, 12])).toBe("2 × 12 ft");
    expect(spliceLabel([20, 20, 8])).toBe("2 × 20 ft + 8 ft");
    expect(spliceLabel([14, 12])).toBe("14 ft + 12 ft");
  });

  it("counts the unpriced lines", () => {
    expect(unpricedLabel(1)).toBe("1 line unpriced");
    expect(unpricedLabel(6)).toBe("6 lines unpriced");
  });

  it("opens full width and closes with Esc, focus back on Expand", async () => {
    renderPanel();
    await screen.findAllByTestId("cut-list-row");
    const expand = screen.getByRole("button", { name: "Expand the cut list" });
    fireEvent.click(expand);
    const view = screen.getByRole("dialog", { name: "Cut list" });
    expect(view).toHaveAttribute("aria-modal", "true");
    // The same table: every line, its prices, the Total and the actions.
    const inView = within(view);
    expect(inView.getAllByTestId("cut-list-row")).toHaveLength(3);
    expect(inView.getByTestId("cut-list-price-total")).toHaveTextContent(
      "$259.74",
    );
    expect(inView.getByText("B1 deck")).toBeInTheDocument();
    expect(inView.getByText("3 lines · 15 pieces")).toBeInTheDocument();
    expect(inView.getByTestId("cut-list-price-book")).toBeInTheDocument();
    expect(inView.getByTestId("cut-list-csv")).toBeEnabled();
    // Its head stays put while the rows scroll.
    expect(view.querySelector("thead")).toHaveClass("sticky", "top-0");
    fireEvent.keyDown(view, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(expand).toHaveFocus();
    // The side panel is as it was.
    expect(screen.getAllByTestId("cut-list-row")).toHaveLength(3);
  });

  it("closes with its Close button", async () => {
    renderPanel();
    await screen.findAllByTestId("cut-list-row");
    fireEvent.click(screen.getByTestId("cut-list-expand"));
    fireEvent.click(
      screen.getByRole("button", { name: "Close the full cut list" }),
    );
    expect(screen.queryByTestId("cut-list-expanded")).toBeNull();
  });

  it("gives Esc to a Price book opened from the full view first", async () => {
    renderPanel();
    await screen.findAllByTestId("cut-list-row");
    fireEvent.click(screen.getByTestId("cut-list-expand"));
    const view = screen.getByTestId("cut-list-expanded");
    fireEvent.click(
      within(view).getByRole("button", { name: "Price 6x6, 6x6 at 8 ft" }),
    );
    const book = screen.getByRole("dialog", { name: "Price book" });
    fireEvent.keyDown(book, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Price book" })).toBeNull();
    expect(screen.getByTestId("cut-list-expanded")).toBeInTheDocument();
  });

  it("downloads the CSV from the full view", async () => {
    const blob = new Blob(["Item"], { type: "text/csv" });
    csv.exportCutListCsv.mockResolvedValue({ blob, filename: "B1.csv" });
    renderPanel();
    await screen.findAllByTestId("cut-list-row");
    fireEvent.click(screen.getByTestId("cut-list-expand"));
    fireEvent.click(
      within(screen.getByTestId("cut-list-expanded")).getByTestId(
        "cut-list-csv",
      ),
    );
    await waitFor(() =>
      expect(csv.downloadBlob).toHaveBeenCalledWith(blob, "B1.csv"),
    );
  });

  it("offers no Expand for an empty list", async () => {
    vi.mocked(fetchCutList).mockResolvedValueOnce({
      ...RESPONSE,
      lines: [],
    });
    renderPanel();
    await screen.findByTestId("cut-list-empty");
    expect(screen.queryByTestId("cut-list-expand")).toBeNull();
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
