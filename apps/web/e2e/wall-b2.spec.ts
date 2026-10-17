import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * STUD-WALL: a B2 wall of docs/reference-parts/buildings.md from ONE Wall
 * feature, inserted from the Build group, with no member drawn by hand.
 *
 * In an inch part: Build > Wall at its defaults (144 long, 2x4 at 16 in
 * o.c., 97.125 plate to plate, double top plate) builds 13 member bodies
 * whose cut list lists the spec's 10 studs at 92.625 and the plates, each
 * weighed by its member material (PT bottom plate, SPF studs and top
 * plates). Then the spacing edit, 16 -> 24 in: 7 studs. A reload keeps it.
 */

const PLUGIN = "loft.wall";

/** One B2 144 wall: member, qty, length (in), stock. */
const WALL_16OC: [string, string, string, string][] = [
  ["Stud", "10", "92.625", "8 ft"],
  ["Top plate", "2", "144", "12 ft"],
  ["Bottom plate", "1", "144", "12 ft"],
];

/** The spacing edit: "spacing 16 -> 24", 0.75, 24, ..., 120, 143.25. */
const WALL_24OC: [string, string, string, string][] = [
  ["Stud", "7", "92.625", "8 ft"],
  ["Top plate", "2", "144", "12 ft"],
  ["Bottom plate", "1", "144", "12 ft"],
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

test.describe("Wall — a B2 wall from one feature", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("insert from Build, see 10 studs in the cut list, edit to 24 in o.c., reload", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B2 wall", length_unit: "in" },
      headers: { Authorization: `Bearer ${account.token}` },
    });
    expect(created.ok(), await created.text()).toBe(true);
    const partId = ((await created.json()) as { id: string }).id;

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(0);

    // Build > Wall: the generated form, in the part's inches, at B2's wall.
    const tool = page.getByTestId(`plugin-tool-${PLUGIN}`);
    await expect(tool).toBeEnabled({ timeout: 30_000 });
    await expect(tool).toHaveAccessibleName(/^Wall/);
    await tool.click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("New Wall");
    await expect(page.getByTestId("plugin-input-length_mm")).toHaveValue("144");
    await expect(page.getByTestId("plugin-input-height_mm")).toHaveValue(
      "97.125",
    );
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });

    // ONE tree row; it unfolds into its members, drawn by the plugin.
    await expect(rows).toHaveCount(1);
    await expect(rows.nth(0)).toContainText("Wall 1");
    await expectSolved(page);
    await page.getByTestId("feature-unfold-0").click();
    const members = page.getByTestId("feature-member-row");
    await expect(members.filter({ hasText: "Stud" })).toHaveCount(10);
    await page.getByTestId("feature-unfold-0").click();

    await openCutList(page);
    await expectTable(page, WALL_16OC, "13");
    await expect(page.getByTestId("prop-mass")).toContainText(/\d/, {
      timeout: 60_000,
    });
    await expect(
      page.getByTestId("material-body-select-1").locator("option:checked"),
    ).toHaveText("From member");
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/wall-b2.png` });

    // The spec's edit: spacing 16 -> 24 in regenerates the studs.
    await page.getByTestId("feature-select-0").click();
    await expect(editor).toContainText("Edit Wall");
    const spacing = page.getByTestId("plugin-input-stud_spacing_mm");
    await expect(spacing).toHaveValue("16");
    await spacing.fill("24");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, WALL_24OC, "10");

    // A reload keeps the edit.
    await page.reload();
    await expect(rows).toHaveCount(1);
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, WALL_24OC, "10");
    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const stored = (
      (await tree.json()) as {
        features: { feature: { params: { inputs: Record<string, number> } } }[];
      }
    ).features[0]?.feature.params.inputs;
    expect(stored?.stud_spacing_mm).toBeCloseTo(24 * 25.4, 9);
    expect(stored?.length_mm).toBeCloseTo(144 * 25.4, 9);
  });
});
