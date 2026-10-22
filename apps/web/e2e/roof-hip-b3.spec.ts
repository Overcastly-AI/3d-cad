import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * ROOF-HIP: B3's hip roof of docs/reference-parts/buildings.md from ONE Roof
 * feature, Style Hip, inserted from Build ▾ over B2's four walls.
 *
 * In an inch part holding B2's walls (no openings): Build ▾ > Roof, Style
 * Hip, on the form's B2 bearing, builds 27 roof members: the cut list lists
 * 6 commons, 16 hip jacks in two lengths (26.833 apart on the line), 4 hips
 * and the 25.5 ridge, at their overall lengths, after the walls' 48 members.
 * Then the pitch edit 6/12 -> 8/12 (buildings.md B3's edit). A reload
 * keeps it.
 */

const IN = 25.4;
const PLUGIN = "loft.roof";

/** B2's walls, clockwise: name, start x, start y, direction, length (in). */
const WALLS: [string, number, number, number, number][] = [
  ["Front wall", 144, 0, 180, 144],
  ["Left wall", 0, 3.5, 90, 113],
  ["Back wall", 0, 120, 0, 144],
  ["Right wall", 144, 116.5, 270, 113],
];

type Row = [string, string, string, string];

/** buildings.md B3's roof table: member, qty, overall length (in), stock. */
const HIP_6_12: Row[] = [
  ["Common", "6", "82.4099", "8 ft"],
  ["Jack", "8", "56.0683", "8 ft"],
  ["Jack", "8", "29.2355", "8 ft"],
  // loft.roof 1.2.0 and later rip the hips' tails to the commons' depth
  // (ROOF-HIP-TAIL): 106.875 + 5.884 x 6/18 (1.1.0's full tail: 109.438).
  ["Hip", "4", "108.8363", "10 ft"],
  ["Ridge", "1", "25.5", "8 ft"],
];

/** The edit to 8/12: commons 85.632, jacks 56.414 and 27.570, hips 111.397
 * on the line, each plus its long points (buildings.md B3 "Edits"). */
const HIP_8_12: Row[] = [
  ["Common", "6", "89.2985", "8 ft"],
  ["Jack", "8", "60.9821", "8 ft"],
  ["Jack", "8", "32.1377", "8 ft"],
  ["Hip", "4", "114.0652", "10 ft"],
  ["Ridge", "1", "25.5", "8 ft"],
];

/** The walls' 48 members come first in tree order; the roof's rows last. */
async function expectRoofRows(page: Page, table: Row[]) {
  const panel = page.getByTestId("cut-list-panel");
  await expect(panel.getByTestId("cut-list-total")).toHaveText("75", {
    timeout: 90_000,
  });
  const rows = panel.getByTestId("cut-list-row");
  const count = await rows.count();
  expect(count).toBeGreaterThan(table.length);
  for (const [index, [member, qty, length, stock]] of table.entries()) {
    const row = rows.nth(count - table.length + index);
    await expect(row.getByTestId("cut-list-member")).toHaveText(member);
    await expect(row.getByTestId("cut-list-qty")).toHaveText(qty);
    await expect(row.getByTestId("cut-list-length")).toHaveText(length);
    await expect(row.getByTestId("cut-list-stock")).toHaveText(stock);
  }
}

/** Scroll the cut list to its last rows, the roof's, for the screenshot. */
async function showRoofRows(page: Page): Promise<void> {
  await page
    .getByTestId("cut-list-panel")
    .getByTestId("cut-list-row")
    .last()
    .scrollIntoViewIfNeeded();
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

test.describe("Roof — B3's hip roof from one feature", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("insert a Hip roof from Build ▾ on B2's walls, see 4 hips and 16 jacks, edit to 8/12, reload", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const account = await seedSession(page);
    const auth = { Authorization: `Bearer ${account.token}` };
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B3 hip shed", length_unit: "in" },
      headers: auth,
    });
    expect(created.ok(), await created.text()).toBe(true);
    const part = (await created.json()) as { id: string; tree_version: number };
    let version = part.tree_version;
    for (const [name, x, y, direction, length] of WALLS) {
      const response = await page.request.post(
        `/api/v1/parts/${part.id}/features`,
        {
          data: {
            name,
            expected_tree_version: version,
            feature: {
              type: "custom",
              version: 1,
              params: {
                plugin_id: "loft.wall",
                plugin_version: "1.0.0",
                inputs: {
                  start_x_mm: x * IN,
                  start_y_mm: y * IN,
                  direction_deg: direction,
                  length_mm: length * IN,
                },
              },
            },
          },
          headers: auth,
        },
      );
      expect(response.ok(), await response.text()).toBe(true);
      version = ((await response.json()) as { tree_version: number })
        .tree_version;
    }

    await page.goto(`/parts/${part.id}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(4);
    await expectSolved(page);

    // Build ▾ > Roof: the generated form, B2's bearing by default; Style Hip.
    await page.getByTestId("build-more").click();
    const tool = page.getByTestId(`plugin-tool-${PLUGIN}`);
    await expect(tool).toBeEnabled({ timeout: 30_000 });
    await tool.click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("New Roof");
    // Style is a two-way segmented control, Gable by default.
    const gable = page.getByTestId("plugin-input-style-gable");
    const hip = page.getByTestId("plugin-input-style-hip");
    await expect(gable).toHaveAttribute("aria-pressed", "true");
    await hip.click();
    await expect(hip).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("plugin-input-span_mm")).toHaveValue("120");
    const hips = page.getByTestId("plugin-input-hip_profile");
    await expect(hips.locator("option:checked")).toHaveText("2x8");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });

    // ONE more tree row; it unfolds into its members, drawn by the plugin.
    await expect(rows).toHaveCount(5);
    await expect(rows.nth(4)).toContainText("Roof 1");
    await expectSolved(page);
    await page.getByTestId("feature-unfold-4").click();
    const members = page.getByTestId("feature-member-row");
    await expect(members.filter({ hasText: "Hip" })).toHaveCount(4);
    await expect(members.filter({ hasText: "Jack" })).toHaveCount(16);
    await expect(members.filter({ hasText: "Common" })).toHaveCount(6);
    await page.getByTestId("feature-unfold-4").click();

    await openCutList(page);
    await expectRoofRows(page, HIP_6_12);
    await showRoofRows(page);
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/roof-hip-b3-6-12.png` });

    // buildings.md B3's edit: pitch 6/12 -> 8/12.
    await page.getByTestId("feature-select-4").click();
    await expect(editor).toContainText("Edit Roof");
    await page
      .getByTestId("plugin-input-pitch")
      .selectOption({ label: "8/12" });
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expectSolved(page);
    await openCutList(page);
    await expectRoofRows(page, HIP_8_12);
    await showRoofRows(page);
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/roof-hip-b3-8-12.png` });

    // A reload keeps the edit, pinned to 1.3.0 (the latest Roof).
    await page.reload();
    await expect(rows).toHaveCount(5);
    await expectSolved(page);
    await openCutList(page);
    await expectRoofRows(page, HIP_8_12);
    const tree = await page.request.get(`/api/v1/parts/${part.id}/features`, {
      headers: auth,
    });
    const roof = (
      (await tree.json()) as {
        features: {
          feature: {
            params: { plugin_version: string; inputs: Record<string, unknown> };
          };
        }[];
      }
    ).features[4]?.feature.params;
    expect(roof?.plugin_version).toBe("1.3.0");
    expect(roof?.inputs.style).toBe("hip");
    expect(roof?.inputs.pitch).toBe("rise_8");
  });
});
