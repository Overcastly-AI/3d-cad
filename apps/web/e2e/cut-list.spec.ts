import { readFile } from "node:fs/promises";

import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { seedSession, SCREENSHOT_DIR } from "./support";

/**
 * CUT-LIST: the B1 deck's cut list in the app, as CSV, and on a drawing.
 *
 * fixtures/b1-deck.loft is the deck of docs/reference-parts/buildings.md B1 as
 * ONE custom feature of the `test.deck_b1` fixture plugin, in an inch part,
 * with its expansion stored (packages/loft-plugins/tests/test_deck_fixture.py
 * pins it). This server has no such plugin, so the part rebuilds read-only
 * from the stored members — 46 bodies, each with its member metadata. What
 * the spec insists on:
 *
 *  - the Cut list panel lists the buildings.md table: member, qty, length in
 *    inches and stock, lengths MEASURED by geometry;
 *  - the CSV button downloads exactly the hand-written CSV;
 *  - a drawing sheet drafting the part shows the same table beside its views.
 */

const PT = '"Southern pine, pressure-treated"';
// No price book saved: one stock piece per piece, the price cells blank
// (never 0) and a Total row that counts the unpriced lines (PRICE-BOOK).
const B1_CSV =
  "Item,System,Member,Profile,Section (in),Material,Qty,Length (in)," +
  "Total length (in),Area (sq in),Stock,Waste each (in),Stock qty," +
  "Unit price (USD)," +
  "Price unit,Extended (USD)\r\n" +
  `1,Other,Ledger,2x10,1.5 x 9.25,${PT},1,192,192,,16 ft,0,1,,,\r\n` +
  `2,Other,Rim,2x10,1.5 x 9.25,${PT},1,192,192,,16 ft,0,1,,,\r\n` +
  `3,Other,Beam,2x10,1.5 x 9.25,${PT},2,192,384,,16 ft,0,2,,,\r\n` +
  `4,Other,Joist,2x10,1.5 x 9.25,${PT},13,141,1833,,12 ft,3,13,,,\r\n` +
  `5,Other,Post,6x6,5.5 x 5.5,${PT},3,10.5,31.5,,8 ft,85.5,3,,,\r\n` +
  `6,Other,Deck,5/4x6,1 x 5.5,${PT},26,192,4992,,16 ft,0,26,,,\r\n` +
  `,"Total of priced lines, 6 unpriced",,,,,,,,,,,,,,\r\n`;

/** buildings.md B1's table: member, qty, length (in), stock. */
const B1_TABLE: [string, string, string, string][] = [
  ["Ledger", "1", "192", "16 ft"],
  ["Rim", "1", "192", "16 ft"],
  ["Beam", "2", "192", "16 ft"],
  ["Joist", "13", "141", "12 ft"],
  ["Post", "3", "10.5", "8 ft"],
  ["Deck", "26", "192", "16 ft"],
];

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

async function expectB1Table(page: Page) {
  const panel = page.getByTestId("cut-list-panel");
  const rows = panel.getByTestId("cut-list-row");
  await expect(rows).toHaveCount(B1_TABLE.length, { timeout: 60_000 });
  for (const [index, [member, qty, length, stock]] of B1_TABLE.entries()) {
    const row = rows.nth(index);
    await expect(row.getByTestId("cut-list-member")).toHaveText(member);
    await expect(row.getByTestId("cut-list-qty")).toHaveText(qty);
    await expect(row.getByTestId("cut-list-length")).toHaveText(length);
    await expect(row.getByTestId("cut-list-stock")).toHaveText(stock);
  }
  await expect(panel.getByTestId("cut-list-total")).toHaveText("46");
}

test.describe("Cut list — the B1 deck", () => {
  test("the panel lists the spec's table and downloads its CSV", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    const account = await seedSession(page);
    const partId = await importDeck(page, account.token);

    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 60_000,
    });
    const tool = page.getByTestId("cut-list-tool");
    await expect(tool).toBeEnabled({ timeout: 30_000 });
    await tool.click();
    await expectB1Table(page);
    await expect(
      page.getByTestId("cut-list-row").first().getByTestId("cut-list-caption"),
    ).toHaveText("2x10 · Southern pine, pressure-treated");

    const downloading = page.waitForEvent("download");
    await page.getByTestId("cut-list-csv").click();
    const download = await downloading;
    expect(download.suggestedFilename()).toBe("B1 deck cut list.csv");
    const path = await download.path();
    expect(await readFile(path, "utf-8")).toBe(B1_CSV);

    // Founder shot: the deck with its cut list.
    await page.mouse.move(800, 950);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/cut-list.png` });
  });

  test("a drawing of the deck shows the cut list beside its views", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const partId = await importDeck(page, account.token);

    await page.goto("/drawings");
    await page.getByTestId("create-drawing-name").fill("Deck sheet");
    await page.getByTestId("create-drawing-name").press("Enter");
    const row = page
      .getByTestId("drawing-row")
      .filter({ hasText: "Deck sheet" });
    await expect(row).toBeVisible();
    await row.getByTestId("drawing-open").click();
    await expect(page).toHaveURL(/\/drawings\/[0-9a-f-]+/);

    await page.getByTestId("drawing-part-select").selectOption(partId);
    await page.getByTestId("drawing-autolayout").click();
    await expect(
      page.locator('[data-testid="drawing-view"]').first(),
    ).toBeVisible({ timeout: 90_000 });

    await expect(page.getByTestId("cut-list-panel")).toHaveAttribute(
      "data-source-kind",
      "part",
    );
    await expectB1Table(page);
  });
});
