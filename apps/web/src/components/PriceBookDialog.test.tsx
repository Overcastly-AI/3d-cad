/**
 * The Price book dialog (CUT-LIST-PRICES): the stored book as rows, a seed row
 * pre-filled from a cut-list line, prices parsed to integer cents, a bad or
 * duplicate row refused in a sentence, Escape cancels, Tab stays inside.
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

import type { PriceBook } from "../api/priceBook";
import { PriceBookDialog, type PriceBookSeed } from "./PriceBookDialog";

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
      ],
      profiles: [
        { key: "us_2x10", name: "2x10" },
        { key: "us_5_4x6", name: "5/4x6" },
        { key: "us_6x6", name: "6x6" },
      ],
    }),
  ),
}));

const BOOK: PriceBook = {
  currency: "USD",
  updated_at: "2026-10-17T00:00:00Z",
  entries: [
    {
      material: "southern_pine_pt",
      profile: "us_2x10",
      unit: "each",
      stock_length_ft: 12,
      price_cents: 1998,
    },
  ],
};

function renderDialog(seed: PriceBookSeed | null = null) {
  const onClose = vi.fn();
  const client = new QueryClient();
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
    expect(api.savePriceBook).toHaveBeenCalledWith([
      BOOK.entries![0],
      {
        material: "southern_pine_pt",
        profile: "us_6x6",
        unit: "board_foot",
        stock_length_ft: null,
        price_cents: 145,
      },
    ]);
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
    expect(api.savePriceBook).toHaveBeenCalledWith([]);
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
});
