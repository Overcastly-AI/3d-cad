/**
 * The Price book dialog (CUT-LIST-PRICES): the stored book as rows, a seed row
 * pre-filled from a cut-list line, prices parsed to integer cents, a bad or
 * duplicate row refused in a sentence, Escape cancels, Tab stays inside.
 * SHEATHING: a sheet product is priced Each per sheet. PRICE-BOOK-VERSION:
 * every save names the version its draft was read at, and the server's 412
 * is shown with a Reload.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type PriceBook, PriceBookChangedError } from "../api/priceBook";
import {
  BOOK_CHANGED,
  PriceBookDialog,
  type PriceBookSeed,
} from "./PriceBookDialog";

const api = vi.hoisted(() => ({
  fetchPriceBook: vi.fn(),
  savePriceBook: vi.fn(),
}));

vi.mock("../api/priceBook", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/priceBook")>()),
  fetchPriceBook: api.fetchPriceBook,
  savePriceBook: api.savePriceBook,
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
        { key: "spf_lumber", name: "SPF", density_kg_m3: 420, source: "" },
        { key: "osb", name: "OSB", density_kg_m3: 641, source: "" },
        { key: "plywood", name: "Plywood", density_kg_m3: 577, source: "" },
        { key: "pvc", name: "PVC", density_kg_m3: 1400, source: "" },
        { key: "concrete", name: "Concrete", density_kg_m3: 2400, source: "" },
        {
          key: "steel_f1554",
          name: "Anchor-bolt steel",
          density_kg_m3: 7850,
          source: "",
        },
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
          key: "anchor_bolt_1_2",
          kind: "anchor_bolt",
          name: "1/2 in anchor bolt",
          material: "steel_f1554",
          price_unit: "each",
          stock_length_ft: null,
        },
      ],
      opening_units: [
        {
          key: "window_3040",
          code: "3040",
          kind: "window",
          name: "Window 3040",
          material: "pvc",
        },
        {
          key: "window_2030",
          code: "2030",
          kind: "window",
          name: "Window 2030",
          material: "pvc",
        },
        {
          key: "door_3068",
          code: "3068",
          kind: "door",
          name: "Door 3068",
          material: "spf_lumber",
        },
      ],
      profiles: [
        { key: "us_2x10", name: "2x10" },
        { key: "us_5_4x6", name: "5/4x6" },
        { key: "us_6x6", name: "6x6" },
      ],
      sheet_goods: [
        { key: "osb_7_16", name: "7/16 OSB", material: "osb" },
        { key: "plywood_23_32", name: "23/32 plywood", material: "plywood" },
      ],
      sheet_sizes: [
        { key: "4x8", width_in: 48, length_in: 96 },
        { key: "4x9", width_in: 48, length_in: 108 },
        { key: "4x10", width_in: 48, length_in: 120 },
      ],
    }),
  ),
}));

const BOOK: PriceBook = {
  currency: "USD",
  updated_at: "2026-10-17T00:00:00Z",
  version: 3,
  entries: [
    {
      material: "southern_pine_pt",
      profile: "us_2x10",
      unit: "each",
      stock_length_ft: 12,
      sheet: null,
      price_cents: 1998,
    },
  ],
};

function renderDialog(
  seed: PriceBookSeed | null = null,
  client = new QueryClient(),
) {
  const onClose = vi.fn();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <PriceBookDialog seed={seed} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { onClose, invalidate };
}

beforeEach(() => {
  api.fetchPriceBook.mockReset().mockResolvedValue(BOOK);
  api.savePriceBook
    .mockReset()
    .mockImplementation((entries: unknown) =>
      Promise.resolve({ ...BOOK, entries }),
    );
});

describe("PriceBookDialog", () => {
  it("is a labelled modal listing the stored prices", async () => {
    renderDialog();
    const dialog = screen.getByRole("dialog", { name: "Price book" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const rows = await screen.findAllByTestId("price-book-row");
    expect(rows).toHaveLength(1);
    const row = within(rows[0]!);
    expect(row.getByLabelText("Material, price 1")).toHaveValue(
      "southern_pine_pt",
    );
    expect(row.getByLabelText("Profile, price 1")).toHaveValue("us_2x10");
    expect(row.getByLabelText("Priced, price 1")).toHaveValue("each");
    expect(row.getByLabelText("Stock length, price 1")).toHaveValue("12");
    expect(row.getByLabelText("Price in dollars, price 1")).toHaveValue(
      "19.98",
    );
    for (const name of ["Material", "Profile", "Priced", "Stock"]) {
      expect(screen.getByRole("columnheader", { name })).toBeInTheDocument();
    }
  });

  it("adds a row for each piece of a splice the book does not price yet", async () => {
    // CUT-LIST-LONG-STOCK: a 28 ft 2x10 spliced 16 + 12; 12 ft is priced.
    renderDialog({
      material: "southern_pine_pt",
      profile: "2x10",
      stockLengthFt: 16,
      stockLengthsFt: [16, 12],
    });
    const rows = await screen.findAllByTestId("price-book-row");
    expect(rows).toHaveLength(2);
    const seeded = within(rows[1]!);
    expect(seeded.getByLabelText("Stock length, price 2")).toHaveValue("16");
    await waitFor(() =>
      expect(seeded.getByLabelText("Price in dollars, price 2")).toHaveFocus(),
    );
  });

  it("adds every missing piece of a mixed splice", async () => {
    api.fetchPriceBook.mockResolvedValue({ ...BOOK, entries: [] });
    renderDialog({
      material: "southern_pine_pt",
      profile: "2x10",
      stockLengthFt: 16,
      stockLengthsFt: [16, 8],
    });
    const rows = await screen.findAllByTestId("price-book-row");
    expect(rows).toHaveLength(2);
    expect(
      within(rows[0]!).getByLabelText("Stock length, price 1"),
    ).toHaveValue("16");
    expect(
      within(rows[1]!).getByLabelText("Stock length, price 2"),
    ).toHaveValue("8");
  });

  it("adds a row pre-filled from the seed, its price focused, and saves cents", async () => {
    const { onClose, invalidate } = renderDialog({
      material: "southern_pine_pt",
      profile: "6x6",
      stockLengthFt: 8,
    });
    const rows = await screen.findAllByTestId("price-book-row");
    expect(rows).toHaveLength(2);
    const seeded = within(rows[1]!);
    expect(seeded.getByLabelText("Profile, price 2")).toHaveValue("us_6x6");
    expect(seeded.getByLabelText("Stock length, price 2")).toHaveValue("8");
    const price = seeded.getByLabelText("Price in dollars, price 2");
    await waitFor(() => expect(price).toHaveFocus());

    fireEvent.change(seeded.getByLabelText("Priced, price 2"), {
      target: { value: "board_foot" },
    });
    // Per board foot is for any stock length: no length to pick.
    expect(seeded.queryByLabelText("Stock length, price 2")).toBeNull();
    fireEvent.change(price, { target: { value: "1.45" } });
    fireEvent.submit(screen.getByTestId("price-book-dialog"));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    // Saved over the version the draft was read at.
    expect(api.savePriceBook).toHaveBeenCalledWith(
      [
        BOOK.entries![0],
        {
          material: "southern_pine_pt",
          profile: "us_6x6",
          unit: "board_foot",
          stock_length_ft: null,
          sheet: null,
          price_cents: 145,
        },
      ],
      3,
    );
    // Every cut list re-prices without a reload.
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["cut-list"] }),
    );
  });

  it("focuses the existing row when the seed is already priced", async () => {
    renderDialog({
      material: "southern_pine_pt",
      profile: "2x10",
      stockLengthFt: 12,
    });
    const rows = await screen.findAllByTestId("price-book-row");
    expect(rows).toHaveLength(1);
    await waitFor(() =>
      expect(screen.getByLabelText("Price in dollars, price 1")).toHaveFocus(),
    );
  });

  it("refuses a price that is not dollars and cents, and a duplicate", async () => {
    renderDialog();
    await screen.findAllByTestId("price-book-row");
    fireEvent.click(screen.getByTestId("price-book-add"));
    const added = await screen.findByLabelText("Price in dollars, price 2");
    fireEvent.change(added, { target: { value: "19.989" } });
    fireEvent.submit(screen.getByTestId("price-book-dialog"));
    expect(
      await screen.findByText("Enter a price in dollars, e.g. 19.98."),
    ).toBeInTheDocument();
    // The added row copies the last one: the same key twice is refused.
    fireEvent.change(added, { target: { value: "20" } });
    fireEvent.submit(screen.getByTestId("price-book-dialog"));
    expect(
      await screen.findByText(
        "This material, profile and unit is already priced.",
      ),
    ).toBeInTheDocument();
    expect(api.savePriceBook).not.toHaveBeenCalled();
  });

  it("removes a price", async () => {
    const { onClose } = renderDialog();
    await screen.findAllByTestId("price-book-row");
    fireEvent.click(
      screen.getByRole("button", {
        name: "Remove the 2x10 Southern pine, pressure-treated price",
      }),
    );
    expect(screen.queryAllByTestId("price-book-row")).toHaveLength(0);
    fireEvent.submit(screen.getByTestId("price-book-dialog"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.savePriceBook).toHaveBeenCalledWith([], 3);
  });

  it("Escape cancels without saving", async () => {
    const { onClose } = renderDialog();
    await screen.findAllByTestId("price-book-row");
    fireEvent.keyDown(screen.getByLabelText("Price in dollars, price 1"), {
      key: "Escape",
    });
    expect(onClose).toHaveBeenCalled();
    expect(api.savePriceBook).not.toHaveBeenCalled();
  });

  it("keeps Tab inside the dialog", async () => {
    renderDialog();
    await screen.findAllByTestId("price-book-row");
    const save = screen.getByTestId("price-book-save");
    save.focus();
    fireEvent.keyDown(save, { key: "Tab" });
    expect(screen.getByLabelText("Material, price 1")).toHaveFocus();
  });

  it("drafts from a fresh GET, never a cached book another tab has since replaced", async () => {
    // The cache holds the book as this tab last saw it: empty.
    const client = new QueryClient();
    client.setQueryData(["price-book"], {
      currency: "USD",
      entries: [],
      updated_at: null,
      version: 0,
    });
    let answer: (book: PriceBook) => void = () => undefined;
    api.fetchPriceBook.mockImplementationOnce(
      () =>
        new Promise<PriceBook>((resolve) => {
          answer = resolve;
        }),
    );
    const { onClose } = renderDialog(null, client);
    // Until the GET answers there is no draft to save from.
    expect(screen.getByTestId("price-book-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("price-book-row")).toBeNull();
    expect(screen.getByTestId("price-book-save")).toBeDisabled();
    answer(BOOK);
    // Another tab saved the 2x10 price: the draft has it, so a save keeps it.
    const rows = await screen.findAllByTestId("price-book-row");
    expect(rows).toHaveLength(1);
    fireEvent.submit(screen.getByTestId("price-book-dialog"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.savePriceBook).toHaveBeenCalledWith(BOOK.entries, 3);
  });

  it("shows the server's refusal of a book saved elsewhere, and reloads it", async () => {
    const elsewhere: PriceBook = {
      ...BOOK,
      updated_at: "2026-10-17T01:00:00Z",
      version: 4,
      entries: [
        ...BOOK.entries!,
        { ...BOOK.entries![0]!, stock_length_ft: 16 },
      ],
    };
    api.fetchPriceBook.mockResolvedValueOnce(BOOK).mockResolvedValue(elsewhere);
    // The gateway's 412: version 3 is no longer the stored book's.
    api.savePriceBook.mockRejectedValueOnce(new PriceBookChangedError());
    const { onClose } = renderDialog();
    await screen.findAllByTestId("price-book-row");
    fireEvent.submit(screen.getByTestId("price-book-dialog"));
    expect(await screen.findByText(BOOK_CHANGED)).toBeInTheDocument();
    // One PUT, no re-read before it: the version check is the server's.
    expect(api.savePriceBook).toHaveBeenCalledTimes(1);
    expect(api.savePriceBook).toHaveBeenLastCalledWith(BOOK.entries, 3);
    expect(api.fetchPriceBook).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
    // Reload drafts from the book as it is stored now, at its version.
    fireEvent.click(screen.getByTestId("price-book-reload"));
    await waitFor(() =>
      expect(screen.getAllByTestId("price-book-row")).toHaveLength(2),
    );
    expect(screen.queryByText(BOOK_CHANGED)).toBeNull();
    fireEvent.submit(screen.getByTestId("price-book-dialog"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.savePriceBook).toHaveBeenLastCalledWith(elsewhere.entries, 4);
  });

  it("prices a sheet product Each per sheet, seeded from a sheet line", async () => {
    const { onClose } = renderDialog({
      material: "osb",
      profile: "7/16 OSB",
      stockLengthFt: null,
      sheet: "4x9",
    });
    const rows = await screen.findAllByTestId("price-book-row");
    expect(rows).toHaveLength(2);
    const seeded = within(rows[1]!);
    expect(seeded.getByLabelText("Profile, price 2")).toHaveValue("osb_7_16");
    expect(seeded.getByLabelText("Sheet, price 2")).toHaveValue("4x9");
    // A sheet has no unit to choose and no stock length.
    expect(seeded.queryByLabelText("Priced, price 2")).toBeNull();
    expect(seeded.getByTestId("price-book-unit-sheet")).toHaveTextContent(
      "Each",
    );
    expect(seeded.queryByLabelText("Stock length, price 2")).toBeNull();
    const price = seeded.getByLabelText("Price in dollars, price 2");
    await waitFor(() => expect(price).toHaveFocus());
    fireEvent.change(price, { target: { value: "24.98" } });
    fireEvent.submit(screen.getByTestId("price-book-dialog"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.savePriceBook).toHaveBeenCalledWith(
      [
        BOOK.entries![0],
        {
          material: "osb",
          profile: "osb_7_16",
          unit: "each",
          stock_length_ft: null,
          sheet: "4x9",
          price_cents: 2498,
        },
      ],
      3,
    );
  });

  it("choosing a sheet product prices it Each in its own material", async () => {
    renderDialog();
    const rows = await screen.findAllByTestId("price-book-row");
    const row = within(rows[0]!);
    fireEvent.change(row.getByLabelText("Priced, price 1"), {
      target: { value: "linear_foot" },
    });
    fireEvent.change(row.getByLabelText("Profile, price 1"), {
      target: { value: "plywood_23_32" },
    });
    expect(row.getByLabelText("Material, price 1")).toHaveValue("plywood");
    expect(row.getByLabelText("Sheet, price 1")).toHaveValue("4x8");
    expect(row.getByTestId("price-book-unit-sheet")).toHaveTextContent("Each");
  });

  it("lists window and door units under their own headings", async () => {
    renderDialog();
    const [row] = await screen.findAllByTestId("price-book-row");
    const profile = within(row!).getByLabelText("Profile, price 1");
    const groups = Array.from(profile.querySelectorAll("optgroup"));
    expect(groups.map((g) => g.label)).toEqual([
      "Lumber",
      "Sheet goods",
      "Windows",
      "Doors",
      "Foundation",
    ]);
    expect(
      Array.from(groups[2]!.querySelectorAll("option")).map((o) => o.value),
    ).toEqual(["window_3040", "window_2030"]);
  });

  it("prices a unit Each by its key, seeded from a unit line, and edits a stored one", async () => {
    api.fetchPriceBook.mockResolvedValue({
      ...BOOK,
      entries: [
        ...BOOK.entries!,
        {
          material: "spf_lumber",
          profile: "door_3068",
          unit: "each",
          stock_length_ft: null,
          sheet: null,
          price_cents: 32900,
        },
      ],
    });
    const { onClose } = renderDialog({
      material: "pvc",
      profile: "3040",
      stockLengthFt: null,
      unitKey: "window_3040",
    });
    const rows = await screen.findAllByTestId("price-book-row");
    expect(rows).toHaveLength(3);
    const stored = within(rows[1]!);
    expect(rows[1]).toHaveAttribute("data-kind", "unit");
    expect(stored.getByLabelText("Profile, price 2")).toHaveValue("door_3068");
    expect(stored.getByLabelText("Price in dollars, price 2")).toHaveValue(
      "329.00",
    );
    const seeded = within(rows[2]!);
    expect(seeded.getByLabelText("Profile, price 3")).toHaveValue(
      "window_3040",
    );
    expect(seeded.getByLabelText("Material, price 3")).toHaveValue("pvc");
    // A unit has no unit to choose and no stock length: Each, per unit.
    expect(seeded.queryByLabelText("Priced, price 3")).toBeNull();
    expect(seeded.getByTestId("price-book-unit-each")).toHaveTextContent(
      "Each",
    );
    expect(seeded.queryByLabelText("Stock length, price 3")).toBeNull();
    expect(seeded.getByTestId("price-book-stock-unit")).toHaveTextContent(
      "Unit",
    );
    const price = seeded.getByLabelText("Price in dollars, price 3");
    await waitFor(() => expect(price).toHaveFocus());
    fireEvent.change(price, { target: { value: "189" } });
    fireEvent.change(stored.getByLabelText("Price in dollars, price 2"), {
      target: { value: "349.50" },
    });
    fireEvent.submit(screen.getByTestId("price-book-dialog"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.savePriceBook).toHaveBeenCalledWith(
      [
        BOOK.entries![0],
        {
          material: "spf_lumber",
          profile: "door_3068",
          unit: "each",
          stock_length_ft: null,
          sheet: null,
          price_cents: 34950,
        },
        {
          material: "pvc",
          profile: "window_3040",
          unit: "each",
          stock_length_ft: null,
          sheet: null,
          price_cents: 18900,
        },
      ],
      3,
    );
  });

  it("prices concrete per cubic yard and a bolt Each, each its one way", async () => {
    // SLAB: a stored ready-mix price reads as an item; a bolt seeded from
    // its cut-list line has no stock and no unit to choose.
    api.fetchPriceBook.mockResolvedValue({
      ...BOOK,
      entries: [
        ...BOOK.entries!,
        {
          material: "concrete",
          profile: "ready_mix",
          unit: "cubic_yard",
          stock_length_ft: null,
          sheet: null,
          price_cents: 16500,
        },
      ],
    });
    const { onClose } = renderDialog({
      material: "steel_f1554",
      profile: "1/2 in anchor bolt",
      stockLengthFt: null,
    });
    const rows = await screen.findAllByTestId("price-book-row");
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveAttribute("data-kind", "item");
    expect(
      within(rows[1]!).getByTestId("price-book-unit-item"),
    ).toHaveTextContent("Per yd³");
    expect(
      within(rows[1]!).getByTestId("price-book-stock-item"),
    ).toHaveTextContent("Ordered");
    const bolt = within(rows[2]!);
    expect(rows[2]).toHaveAttribute("data-profile", "anchor_bolt_1_2");
    expect(bolt.queryByLabelText("Priced, price 3")).toBeNull();
    expect(bolt.getByTestId("price-book-unit-item")).toHaveTextContent("Each");
    const price = bolt.getByLabelText("Price in dollars, price 3");
    await waitFor(() => expect(price).toHaveFocus());
    fireEvent.change(price, { target: { value: "2.48" } });
    fireEvent.submit(screen.getByTestId("price-book-dialog"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.savePriceBook).toHaveBeenCalledWith(
      [
        BOOK.entries![0],
        {
          material: "concrete",
          profile: "ready_mix",
          unit: "cubic_yard",
          stock_length_ft: null,
          sheet: null,
          price_cents: 16500,
        },
        {
          material: "steel_f1554",
          profile: "anchor_bolt_1_2",
          unit: "each",
          stock_length_ft: null,
          sheet: null,
          price_cents: 248,
        },
      ],
      3,
    );
  });

  it("choosing a unit prices it Each in its frame's material", async () => {
    renderDialog();
    const rows = await screen.findAllByTestId("price-book-row");
    const row = within(rows[0]!);
    fireEvent.change(row.getByLabelText("Profile, price 1"), {
      target: { value: "door_3068" },
    });
    expect(rows[0]).toHaveAttribute("data-kind", "unit");
    expect(row.getByLabelText("Material, price 1")).toHaveValue("spf_lumber");
    expect(row.getByTestId("price-book-unit-each")).toHaveTextContent("Each");
    // Back to lumber: its unit and stock length return.
    fireEvent.change(row.getByLabelText("Profile, price 1"), {
      target: { value: "us_2x10" },
    });
    expect(row.getByLabelText("Stock length, price 1")).toHaveValue("12");
  });

  it("refuses a second price for the same unit and material", async () => {
    api.fetchPriceBook.mockResolvedValue({ ...BOOK, entries: [] });
    renderDialog();
    await screen.findByTestId("price-book-empty");
    for (const n of [1, 2]) {
      fireEvent.click(screen.getByTestId("price-book-add"));
      const row = within(screen.getAllByTestId("price-book-row")[n - 1]!);
      fireEvent.change(row.getByLabelText(`Profile, price ${n}`), {
        target: { value: "window_3040" },
      });
      fireEvent.change(row.getByLabelText(`Price in dollars, price ${n}`), {
        target: { value: "189" },
      });
    }
    fireEvent.submit(screen.getByTestId("price-book-dialog"));
    expect(
      await screen.findByText(
        "This material, profile and unit is already priced.",
      ),
    ).toBeInTheDocument();
    expect(api.savePriceBook).not.toHaveBeenCalled();
  });

  it("holds Cancel and Escape while a save is in flight", async () => {
    api.savePriceBook.mockImplementation(() => new Promise(() => undefined));
    const { onClose } = renderDialog();
    await screen.findAllByTestId("price-book-row");
    fireEvent.submit(screen.getByTestId("price-book-dialog"));
    await waitFor(() =>
      expect(screen.getByTestId("price-book-cancel")).toBeDisabled(),
    );
    fireEvent.keyDown(screen.getByTestId("price-book-dialog"), {
      key: "Escape",
    });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("says so when the clicked line's profile is not in the library", async () => {
    renderDialog({
      material: "southern_pine_pt",
      profile: "2x14",
      stockLengthFt: 16,
    });
    expect(
      await screen.findByTestId("price-book-seed-notice"),
    ).toHaveTextContent(
      "2x14 is not a profile in the library, so the price book cannot price it.",
    );
    expect(screen.getAllByTestId("price-book-row")).toHaveLength(1);
  });
});
