import { readFile } from "node:fs/promises";

import type { Locator, Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * CUT-LIST-PRICES: the B1 deck priced through the Price book dialog.
 *
 * fixtures/b1-deck.loft is the deck of docs/reference-parts/buildings.md B1
 * (see cut-list.spec.ts). The spec's sample book (docs/BACKLOG.md PRICE-BOOK)
 * is entered through the dialog the way a user would: click a blank price, the
 * row arrives pre-filled with that line's material, profile and stock length,
 * type the price. Then:
 *
 *  - Joist reads 13 at $19.98 = $259.74 and the Total is $943.94;
 *  - deleting the 6x6 entry blanks Post: $839.54 and "1 line unpriced";
 *  - a reload keeps it (the book is the user's, stored in documents);
 *  - the CSV carries the price columns and the Total row.
 */

const PT = "southern_pine_pt";

async function importDeck(page: Page, token: string): Promise<string> {
  const file = await readFile(
    new URL("./fixtures/b1-deck.loft", import.meta.url),
  );
  const response = await page.request.post("/api/v1/parts/import", {
    data: file,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/octet-stream",
    },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e .loft import failed: ${response.status()} ${await response.text()}`,
    );
  }
  return ((await response.json()) as { part: { id: string } }).part.id;
}

async function openCutList(page: Page): Promise<Locator> {
  const tool = page.getByTestId("cut-list-tool");
  await expect(tool).toBeEnabled({ timeout: 30_000 });
  await tool.click();
  const panel = page.getByTestId("cut-list-panel");
  await expect(panel.getByTestId("cut-list-row")).toHaveCount(6, {
    timeout: 60_000,
  });
  return panel;
}

function row(panel: Locator, member: string): Locator {
  return panel.locator(`[data-testid="cut-list-row"][data-member="${member}"]`);
}

/**
 * Click the line's blank price and price the pre-filled row; `unit` changes
 * how it is priced first (Each is the pre-fill).
 */
async function priceLine(
  page: Page,
  panel: Locator,
  member: string,
  expected: { profile: string; stock: string },
  price: string,
  unit?: "linear_foot" | "board_foot",
): Promise<void> {
  await row(panel, member).getByTestId("cut-list-price-blank").click();
  const dialog = page.getByRole("dialog", { name: "Price book" });
  await expect(dialog).toBeVisible();
  const seeded = dialog.getByTestId("price-book-row").last();
  await expect(seeded).toHaveAttribute("data-material", PT);
  await expect(seeded).toHaveAttribute("data-profile", expected.profile);
  await expect(seeded.getByTestId("price-book-unit")).toHaveValue("each");
  await expect(seeded.getByTestId("price-book-stock")).toHaveValue(
    expected.stock,
  );
  const field = seeded.getByTestId("price-book-price");
  await expect(field).toBeFocused();
  if (unit !== undefined) {
    await seeded.getByTestId("price-book-unit").selectOption(unit);
    await expect(seeded.getByTestId("price-book-stock")).toHaveCount(0);
  }
  await field.fill(price);
  await field.press("Enter");
  await expect(dialog).toBeHidden({ timeout: 15_000 });
}

/** Add an `each` row through "Add price" (it copies the last row). */
async function addEach(
  dialog: Locator,
  profile: string,
  stock: string,
  price: string,
): Promise<void> {
  await dialog.getByTestId("price-book-add").click();
  const added = dialog.getByTestId("price-book-row").last();
  await added.getByTestId("price-book-material").selectOption(PT);
  await added.getByTestId("price-book-profile").selectOption(profile);
  await added.getByTestId("price-book-unit").selectOption("each");
  await added.getByTestId("price-book-stock").selectOption(stock);
  await added.getByTestId("price-book-price").fill(price);
}

async function expectPriced(panel: Locator, unpricedPost: boolean) {
  const joist = row(panel, "Joist");
  await expect(joist.getByTestId("cut-list-qty")).toHaveText("13");
  await expect(joist.getByTestId("cut-list-unit-price")).toHaveText("$19.98");
  await expect(joist.getByTestId("cut-list-ext-price")).toHaveText("$259.74");
  await expect(row(panel, "Beam").getByTestId("cut-list-ext-price")).toHaveText(
    "$56.94",
  );
  await expect(row(panel, "Deck").getByTestId("cut-list-ext-price")).toHaveText(
    "$465.92",
  );
  const post = row(panel, "Post");
  if (unpricedPost) {
    // Blank, never $0.
    await expect(post.getByTestId("cut-list-unit-price")).not.toContainText(
      "$",
    );
    await expect(post.getByTestId("cut-list-ext-price")).toHaveText("");
    await expect(panel.getByTestId("cut-list-price-total")).toHaveText(
      "$839.54",
    );
    await expect(panel.getByTestId("cut-list-unpriced")).toHaveText(
      "1 line unpriced",
    );
  } else {
    await expect(post.getByTestId("cut-list-unit-price")).toHaveText("$34.80");
    await expect(post.getByTestId("cut-list-ext-price")).toHaveText("$104.40");
    await expect(panel.getByTestId("cut-list-price-total")).toHaveText(
      "$943.94",
    );
    await expect(panel.getByTestId("cut-list-unpriced")).toHaveCount(0);
  }
}

test.describe("Cut list prices — the B1 deck", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("price B1 through the dialog, delete the 6x6 price, reload, export the CSV", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const account = await seedSession(page);
    const partId = await importDeck(page, account.token);

    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 60_000,
    });
    const panel = await openCutList(page);

    // No book yet: every price blank, the total empty and counting them.
    await expect(panel.getByTestId("cut-list-price-total")).toHaveText("");
    await expect(panel.getByTestId("cut-list-unpriced")).toHaveText(
      "6 lines unpriced",
    );
    await expect(panel.getByTestId("cut-list-price-blank")).toHaveCount(6);

    // The sample book, a blank at a time. One 2x10 x 16 ft price covers the
    // ledger, rim and beam.
    await priceLine(
      page,
      panel,
      "Beam",
      { profile: "us_2x10", stock: "16" },
      "28.47",
    );
    await expect(
      row(panel, "Ledger").getByTestId("cut-list-unit-price"),
    ).toHaveText("$28.47");
    await expect(panel.getByTestId("cut-list-unpriced")).toHaveText(
      "3 lines unpriced",
    );
    await priceLine(
      page,
      panel,
      "Joist",
      { profile: "us_2x10", stock: "12" },
      "19.98",
    );
    await priceLine(
      page,
      panel,
      "Post",
      { profile: "us_6x6", stock: "8" },
      "1.45",
      "board_foot",
    );
    await priceLine(
      page,
      panel,
      "Deck",
      { profile: "us_5_4x6", stock: "16" },
      "1.12",
      "linear_foot",
    );
    await expectPriced(panel, false);

    // The rest of the sample book's PT entries, through "Add price".
    await panel.getByTestId("cut-list-price-book").click();
    const dialog = page.getByRole("dialog", { name: "Price book" });
    await expect(dialog.getByTestId("price-book-row")).toHaveCount(4);
    await addEach(dialog, "us_2x4", "8", "5.27");
    await addEach(dialog, "us_2x4", "10", "6.97");
    await addEach(dialog, "us_2x4", "12", "8.37");
    await page.mouse.move(10, 10);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/price-book-dialog.png`,
    });
    await dialog.getByTestId("price-book-save").click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });
    await expectPriced(panel, false);
    // Founder shot: the priced list from its header (closing the dialog
    // returned focus to Price book, which scrolled the panel to its foot).
    await panel.getByTestId("cut-list-table").scrollIntoViewIfNeeded();
    await panel
      .locator("thead")
      .evaluate((head) => head.scrollIntoView({ block: "start" }));
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/cut-list-prices.png` });

    // Delete the 6x6 price: Post goes blank and the total says so.
    await panel.getByTestId("cut-list-price-book").click();
    const post = dialog.locator(
      '[data-testid="price-book-row"][data-profile="us_6x6"]',
    );
    await expect(post).toHaveCount(1);
    await post.getByTestId("price-book-remove").click();
    await expect(dialog.getByTestId("price-book-row")).toHaveCount(6);
    await dialog.getByTestId("price-book-save").click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });
    await expectPriced(panel, true);

    // A reload keeps the book.
    await page.reload();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 60_000,
    });
    const reloaded = page.getByTestId("cut-list-panel");
    if ((await reloaded.count()) === 0) await openCutList(page);
    await expect(reloaded.getByTestId("cut-list-row")).toHaveCount(6, {
      timeout: 60_000,
    });
    await expectPriced(reloaded, true);

    // The CSV carries the same prices and the Total row.
    const downloading = page.waitForEvent("download");
    await reloaded.getByTestId("cut-list-csv").click();
    const download = await downloading;
    const csv = (await readFile(await download.path(), "utf-8")).split("\r\n");
    expect(csv[0]).toMatch(
      /,Stock qty,Unit price \(USD\),Price unit,Extended \(USD\)$/,
    );
    expect(csv[4]).toMatch(/^4,Joist,.*,12 ft,3,13,19\.98,Each,259\.74$/);
    expect(csv[5]).toMatch(/^5,Post,.*,8 ft,85\.5,3,,,$/);
    expect(csv[6]).toMatch(/^6,Deck,.*,16 ft,0,26,17\.92,Per ft,465\.92$/);
    expect(csv[7]).toBe(
      ',"Total of priced lines, 1 unpriced",,,,,,,,,,,,839.54',
    );
  });
});
