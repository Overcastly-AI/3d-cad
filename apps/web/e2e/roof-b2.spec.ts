import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * ROOF: B2's gable roof of docs/reference-parts/buildings.md from ONE Roof
 * feature, inserted from the Build group, with no member drawn by hand.
 *
 * In an inch part: Build > Roof with the form's defaults (B2: 6/12 on walls
 * 120 apart, 144 long), and the roof builds as 14 rafters and a ridge whose
 * cut list gives each rafter's overall length (line length 79.660 plus
 * 5.5 x 6/12) on 8 ft stock. Then the spec's named edit, pitch 6/12 -> 8/12,
 * picked from the pitch list: 89.2985. A reload keeps it.
 *
 * Roof only: the full "B2 from Build features only" e2e waits for the Wall,
 * Window and Door tools (BACKLOG note B2-E2E).
 */

const PLUGIN = "loft.roof";

/** buildings.md B2's roof row: member, qty, overall length (in), stock. */
const ROOF_6_12: [string, string, string, string][] = [
  ["Rafter", "14", "82.4099", "8 ft"],
  ["Ridge", "1", "144", "12 ft"],
];

/** The edit: "Pitch 6/12 -> 8/12: line length 85.632" (+ 5.5 x 8/12). */
const ROOF_8_12: [string, string, string, string][] = [
  ["Rafter", "14", "89.2985", "8 ft"],
  ["Ridge", "1", "144", "12 ft"],
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

async function openCutList(page: Page): Promise<void> {
  const tool = page.getByTestId("cut-list-tool");
  await expect(tool).toBeEnabled({ timeout: 30_000 });
  if ((await page.getByTestId("cut-list-panel").count()) === 0) {
    await tool.click();
  }
  await expect(page.getByTestId("cut-list-panel")).toBeVisible();
}

test.describe("Roof — B2's gable from one feature", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("insert from Build at 6/12, see the rafters and cut list, edit to 8/12, reload", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B2 roof", length_unit: "in" },
      headers: { Authorization: `Bearer ${account.token}` },
    });
    expect(created.ok(), await created.text()).toBe(true);
    const partId = ((await created.json()) as { id: string }).id;

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(0);

    // Build > Roof: the generated form, in the part's inches, B2 by default.
    const tool = page.getByTestId(`plugin-tool-${PLUGIN}`);
    await expect(tool).toBeEnabled({ timeout: 30_000 });
    await expect(tool).toHaveAccessibleName(/^Roof/);
    await tool.click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("New Roof");
    await expect(page.getByTestId("plugin-input-span_mm")).toHaveValue("120");
    await expect(page.getByTestId("plugin-input-plate_height_mm")).toHaveValue(
      "97.125",
    );
    const pitch = page.getByTestId("plugin-input-pitch");
    await expect(pitch.locator("option:checked")).toHaveText("6/12");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });

    // ONE tree row; it unfolds into its members, drawn by the plugin.
    await expect(rows).toHaveCount(1);
    await expect(rows.nth(0)).toContainText("Roof 1");
    await expectSolved(page);
    await page.getByTestId("feature-unfold-0").click();
    const members = page.getByTestId("feature-member-row");
    await expect(members.filter({ hasText: "Rafter" })).toHaveCount(14);
    await expect(members.filter({ hasText: "Ridge" })).toHaveCount(1);
    await page.getByTestId("feature-unfold-0").click();

    await openCutList(page);
    await expectTable(page, ROOF_6_12, "15");
    await expect(page.getByTestId("prop-mass")).toContainText(/\d/, {
      timeout: 60_000,
    });
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/roof-b2-6-12.png` });

    // The spec's edit: pitch 6/12 -> 8/12, picked from the list.
    await page.getByTestId("feature-select-0").click();
    await expect(editor).toContainText("Edit Roof");
    await pitch.selectOption({ label: "8/12" });
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, ROOF_8_12, "15");
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/roof-b2-8-12.png` });

    // A reload keeps the edit.
    await page.reload();
    await expect(rows).toHaveCount(1);
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, ROOF_8_12, "15");
    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const stored = (
      (await tree.json()) as {
        features: {
          feature: { params: { inputs: Record<string, unknown> } };
        }[];
      }
    ).features[0]?.feature.params.inputs;
    expect(stored?.pitch).toBe("rise_8");
  });
});
