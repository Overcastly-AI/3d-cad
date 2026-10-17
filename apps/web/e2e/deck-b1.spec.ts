import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * DECK: the B1 deck of docs/reference-parts/buildings.md from ONE Deck
 * feature, inserted from the Build group, with no member drawn by hand.
 *
 * In an inch part: Build > Deck, set 16 ft x 12 ft in the generated form,
 * and the deck builds as 46 member bodies whose cut list is the spec's
 * table, weighed by their member material (the Material panel says "From
 * member", never "No material"). Then the spec's named edit, width 16 ->
 * 20 ft: 50 members and the edit's table. A reload keeps it.
 */

const PLUGIN = "loft.deck";

/** buildings.md B1's cut list: member, qty, length (in), stock. */
const B1_TABLE: [string, string, string, string][] = [
  ["Ledger", "1", "192", "16 ft"],
  ["Rim", "1", "192", "16 ft"],
  ["Beam", "2", "192", "16 ft"],
  ["Joist", "13", "141", "12 ft"],
  ["Post", "3", "10.5", "8 ft"],
  ["Deck", "26", "192", "16 ft"],
];

/** The edit: "Ledger, rim, beam plies and decking become 240 (20 ft
 * stock), joists 16, posts 4." */
const B1_20FT_TABLE: [string, string, string, string][] = [
  ["Ledger", "1", "240", "20 ft"],
  ["Rim", "1", "240", "20 ft"],
  ["Beam", "2", "240", "20 ft"],
  ["Joist", "16", "141", "12 ft"],
  ["Post", "4", "10.5", "8 ft"],
  ["Deck", "26", "240", "20 ft"],
];

async function expectTable(
  page: Page,
  table: [string, string, string, string][],
  total: string,
) {
  const panel = page.getByTestId("cut-list-panel");
  await expect(panel.getByTestId("cut-list-total")).toHaveText(total, {
    timeout: 90_000,
  });
  const rows = panel.getByTestId("cut-list-row");
  await expect(rows).toHaveCount(table.length);
  for (const [index, [member, qty, length, stock]] of table.entries()) {
    const row = rows.nth(index);
    await expect(row.getByTestId("cut-list-member")).toHaveText(member);
    await expect(row.getByTestId("cut-list-qty")).toHaveText(qty);
    await expect(row.getByTestId("cut-list-length")).toHaveText(length);
    await expect(row.getByTestId("cut-list-stock")).toHaveText(stock);
  }
}

async function expectSolved(page: Page): Promise<void> {
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 90_000,
  });
}

/** The members weigh: a mass, and a member body's cell says From member. */
async function expectWeighed(page: Page): Promise<void> {
  await expect(page.getByTestId("prop-mass")).toContainText(/\d/, {
    timeout: 60_000,
  });
  await expect(
    page.getByTestId("material-body-select-1").locator("option:checked"),
  ).toHaveText("From member");
}

async function openCutList(page: Page): Promise<void> {
  const tool = page.getByTestId("cut-list-tool");
  await expect(tool).toBeEnabled({ timeout: 30_000 });
  if ((await page.getByTestId("cut-list-panel").count()) === 0) {
    await tool.click();
  }
  await expect(page.getByTestId("cut-list-panel")).toBeVisible();
}

test.describe("Deck — the B1 deck from one feature", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("insert from Build at 16 x 12 ft, see the members and cut list, edit to 20 ft, reload", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B1 deck", length_unit: "in" },
      headers: { Authorization: `Bearer ${account.token}` },
    });
    expect(created.ok(), await created.text()).toBe(true);
    const partId = ((await created.json()) as { id: string }).id;

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(0);

    // Build > Deck: the generated form, in the part's inches.
    const tool = page.getByTestId(`plugin-tool-${PLUGIN}`);
    await expect(tool).toBeEnabled({ timeout: 30_000 });
    await expect(tool).toHaveAccessibleName(/^Deck/);
    await tool.click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("New Deck");
    await page.getByTestId("plugin-input-width_mm").fill("16 ft");
    await page.getByTestId("plugin-input-depth_mm").fill("12 ft");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });

    // ONE tree row; it unfolds into its members, drawn by the plugin.
    await expect(rows).toHaveCount(1);
    await expect(rows.nth(0)).toContainText("Deck 1");
    await expectSolved(page);
    await page.getByTestId("feature-unfold-0").click();
    const members = page.getByTestId("feature-member-row");
    await expect(members.filter({ hasText: "Joist" })).toHaveCount(13);
    await expect(members.filter({ hasText: "Post" })).toHaveCount(3);
    await page.getByTestId("feature-unfold-0").click();

    await openCutList(page);
    await expectTable(page, B1_TABLE, "46");
    await expectWeighed(page);
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/deck-b1.png` });

    // The spec's edit: width 16 -> 20 ft regenerates every member.
    await page.getByTestId("feature-select-0").click();
    await expect(editor).toContainText("Edit Deck");
    const width = page.getByTestId("plugin-input-width_mm");
    await expect(width).toHaveValue("192");
    await width.fill("20 ft");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, B1_20FT_TABLE, "50");
    await expectWeighed(page);
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/deck-b1-20ft.png` });

    // A reload keeps the edit.
    await page.reload();
    await expect(rows).toHaveCount(1);
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, B1_20FT_TABLE, "50");
    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const stored = (
      (await tree.json()) as {
        features: { feature: { params: { inputs: Record<string, number> } } }[];
      }
    ).features[0]?.feature.params.inputs;
    expect(stored?.width_mm).toBeCloseTo(240 * 25.4, 9);
    expect(stored?.depth_mm).toBeCloseTo(144 * 25.4, 9);
  });
});
