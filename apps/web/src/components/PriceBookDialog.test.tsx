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
