import {
  type CutRow,
  expectSolved,
  expectTable,
  openBuildTool,
  openCutList,
} from "./buildFlow";
import { expect, test } from "./fixtures";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * SHEATHING: sheet goods as options on the Wall and the Floor, counted by
 * the sheets the panels are cut from (SHEET-COUNT-PIECES) and priced per
 * sheet (docs/BACKLOG.md SHEATHING).
 *
 *  - A 144 in Wall from Build ▾ with Exterior sheathing 7/16 OSB lists 3
 *    panels (13 986 in², 97.125 tall) cut from 3 sheets of 4x9; pricing the
 *    blank through the dialog at $24.98 per 4x9 sheet extends to $74.94.
 *  - A Floor from Build ▾ at its defaults has the 23/32 plywood subfloor:
 *    6 panels, 17 280 in², cut from 4 sheets of 4x8 (two 96 x 48 whole, a
 *    96 x 24 and its 48 x 24 from one, two 48 x 48 from one).
 */

/** The default 144 wall's framing (wall-b2's list) and its OSB. */
const WALL_OSB: CutRow[] = [
  ["Stud", "10", "92.625", "8 ft"],
  ["Top plate", "2", "144", "12 ft"],
  ["Bottom plate", "1", "144", "12 ft"],
  ["Sheathing", "3", "13,986 in²", "3 × 4x9"],
];

/** B5's floor (floor-b5's list) and its subfloor. */
const FLOOR_SUBFLOOR: CutRow[] = [
  ["Joist", "10", "117", "10 ft"],
  ["Rim", "2", "144", "12 ft"],
  ["Sill", "2", "109", "10 ft"],
  ["Sill", "2", "144", "12 ft"],
  ["Subfloor", "6", "17,280 in²", "4 × 4x8"],
];

async function inchPart(
  page: import("@playwright/test").Page,
  token: string,
  name: string,
): Promise<string> {
  const created = await page.request.post("/api/v1/parts", {
    data: { name, length_unit: "in" },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(created.ok(), await created.text()).toBe(true);
  return ((await created.json()) as { id: string }).id;
}

test.describe("Sheathing — sheet goods on the Wall and the Floor", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a Wall with OSB lists 3 sheets of 4x9, priced $74.94 per the book", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const account = await seedSession(page);
    const partId = await inchPart(page, account.token, "Sheathed wall");
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(0);

    await openBuildTool(page, "loft.wall", "Wall");
    const editor = page.getByTestId("plugin-editor");
    await expect(page.getByTestId("plugin-input-length_mm")).toHaveValue("144");
    const sheathing = page.getByTestId("plugin-input-sheathing");
    await expect(sheathing).toHaveValue("none");
    await sheathing.selectOption("osb_7_16");
    // SIDING-TRIM: the sheathing alone (siding.spec.ts sides a house).
    await page.getByTestId("plugin-input-exterior_finish").selectOption("none");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expectSolved(page);

    await openCutList(page);
    await expectTable(page, WALL_OSB, "16");
    const panel = page.getByTestId("cut-list-panel");
    const osb = panel.locator(
      '[data-testid="cut-list-row"][data-member="Sheathing"]',
    );
    await expect(osb).toHaveAttribute("data-sheet", "4x9");
    await expect(osb.getByTestId("cut-list-caption")).toContainText("7/16 OSB");

    // Its blank price opens the book on a per-sheet row for a 4x9 sheet.
    await osb.getByTestId("cut-list-price-blank").click();
    const dialog = page.getByRole("dialog", { name: "Price book" });
    await expect(dialog).toBeVisible();
    const seeded = dialog.getByTestId("price-book-row").last();
    await expect(seeded).toHaveAttribute("data-profile", "osb_7_16");
    await expect(seeded).toHaveAttribute("data-material", "osb");
    await expect(seeded.getByTestId("price-book-unit-sheet")).toHaveText(
      "Each",
    );
    await expect(seeded.getByTestId("price-book-sheet")).toHaveValue("4x9");
    const field = seeded.getByTestId("price-book-price");
    await expect(field).toBeFocused();
    await field.fill("24.98");
    await page.mouse.move(10, 10);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sheathing-price-book.png`,
    });
    await field.press("Enter");
    await expect(dialog).toBeHidden({ timeout: 15_000 });

    await expect(osb.getByTestId("cut-list-unit-price")).toHaveText("$24.98");
    await expect(osb.getByTestId("cut-list-ext-price")).toHaveText("$74.94");
    await expect(osb.getByTestId("cut-list-unit-price")).toHaveAttribute(
      "title",
      "Each per 4x9 sheet",
    );
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/sheathing-wall.png` });

    // The book is stored per sheet, at version 1.
    const book = await page.request.get("/api/v1/price-book", {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const stored = (await book.json()) as {
      version: number;
      entries: { profile: string; sheet: string | null; price_cents: number }[];
    };
    expect(stored.version).toBe(1);
    expect(stored.entries).toEqual([
      expect.objectContaining({
        profile: "osb_7_16",
        sheet: "4x9",
        price_cents: 2498,
      }),
    ]);
  });

  test("a Floor from Build ▾ has its 23/32 plywood subfloor: 4 sheets of 4x8", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const account = await seedSession(page);
    const partId = await inchPart(page, account.token, "Sheathed floor");
    await page.goto(`/parts/${partId}`);
    await openBuildTool(page, "loft.floor", "Floor");
    await expect(page.getByTestId("plugin-input-subfloor")).toHaveValue(
      "plywood_23_32",
    );
    await page.getByTestId("plugin-submit").click();
    await expect(page.getByTestId("plugin-editor")).toBeHidden({
      timeout: 30_000,
    });
    await expectSolved(page);
    await page.getByTestId("feature-unfold-0").click();
    await expect(
      page.getByTestId("feature-member-row").filter({ hasText: "Subfloor" }),
    ).toHaveCount(6);
    await page.getByTestId("feature-unfold-0").click();

    await openCutList(page);
    await expectTable(page, FLOOR_SUBFLOOR, "22");
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/sheathing-floor.png` });
  });
});
