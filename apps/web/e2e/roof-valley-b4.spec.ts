import { expect, test } from "./fixtures";
import {
  type CutRow,
  expectSolved,
  openBuildTool,
  openCutList,
} from "./buildFlow";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * ROOF-VALLEY: B4's L-shaped hip roof of docs/reference-parts/buildings.md
 * from ONE Roof feature whose footprint is PICKED from B4's six walls in
 * the Roof form (Revit's Roof by Footprint, Pick Walls).
 *
 * In an inch part holding B4's six walls: Build ▾ > Roof, Style Hip, the six
 * walls ticked in the Walls checklist, builds 52 roof members: the cut list
 * lists 1 Valley and 4 Valley jack (two lengths, 51.641 and 24.808 on the
 * line) after the walls' 85 members. A reload keeps the picks, pinned to
 * loft.roof 1.9.0 (the latest Roof).
 */

const IN = 25.4;
const PLUGIN = "loft.roof";

/** B4's walls, clockwise: name, start x, start y, direction, length (in). */
const WALLS: [string, number, number, number, number][] = [
  ["Back wall", 0, 240, 0, 240],
  ["Right wall", 240, 236.5, 270, 236.5],
  ["Wing front", 236.5, 0, 180, 116.5],
  ["Wing left", 120, 3.5, 90, 116.5],
  ["Main front", 123.5, 120, 180, 123.5],
  ["Left wall", 0, 123.5, 90, 113],
];

/** buildings.md B4's roof table at overall lengths; loft.roof 1.2.0 and later rip
 * the hip and valley tails to the commons' depth (ROOF-HIP-TAIL). */
const ROOF: CutRow[] = [
  ["Common", "2", "82.0626", "8 ft"],
  ["Common", "18", "82.4099", "8 ft"],
  ["Jack", "10", "29.2355", "8 ft"],
  ["Jack", "10", "56.0683", "8 ft"],
  ["Valley jack", "2", "28.397", "8 ft"],
  ["Valley jack", "2", "55.2298", "8 ft"],
  ["Hip", "5", "108.8363", "10 ft"],
  ["Valley", "1", "109.6318", "10 ft"],
  ["Ridge", "1", "120", "10 ft"],
  ["Ridge", "1", "121.5", "12 ft"],
];

/** The walls' 85 members come first in tree order; the roof's rows last. */
async function expectRoofRows(page: import("@playwright/test").Page) {
  const panel = page.getByTestId("cut-list-panel");
  await expect(panel.getByTestId("cut-list-total")).toHaveText("137", {
    timeout: 90_000,
  });
  const rows = panel.getByTestId("cut-list-row");
  const count = await rows.count();
  expect(count).toBeGreaterThan(ROOF.length);
  for (const [index, [member, qty, length, stock]] of ROOF.entries()) {
    const row = rows.nth(count - ROOF.length + index);
    await expect(row.getByTestId("cut-list-member")).toHaveText(member);
    await expect(row.getByTestId("cut-list-qty")).toHaveText(qty);
    await expect(row.getByTestId("cut-list-length")).toHaveText(length);
    await expect(row.getByTestId("cut-list-stock")).toHaveText(stock);
  }
  await rows.last().scrollIntoViewIfNeeded();
}

test.describe("Roof — B4's L-shaped hip and valley roof on picked walls", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("pick B4's six walls in the Roof form, see 1 Valley and 4 Valley jack, reload", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const account = await seedSession(page);
    const auth = { Authorization: `Bearer ${account.token}` };
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B4 L house", length_unit: "in" },
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
    await expect(rows).toHaveCount(6);
    await expectSolved(page);

    // Build ▾ > Roof; Style Hip; tick the six walls in the Walls checklist.
    await openBuildTool(page, PLUGIN, "Roof");
    await page.getByTestId("plugin-input-style-hip").click();
    const picker = page.getByTestId("plugin-input-walls");
    const picks = picker.getByRole("checkbox");
    await expect(picks).toHaveCount(6);
    for (const [name] of WALLS) {
      const pick = picker.getByRole("checkbox", { name });
      await pick.click();
      await expect(pick).toHaveAttribute("aria-checked", "true");
    }
    await expect(picker).toContainText("6 picked");
    await page.getByTestId("plugin-submit").click();
    await expect(page.getByTestId("plugin-editor")).toBeHidden({
      timeout: 30_000,
    });

    // ONE more tree row; it unfolds into its members.
    await expect(rows).toHaveCount(7);
    await expect(rows.nth(6)).toContainText("Roof 1");
    await expectSolved(page);
    await page.getByTestId("feature-unfold-6").click();
    const members = page.getByTestId("feature-member-row");
    // "Valley" also matches the 4 valley jacks: 1 valley.
    await expect(members.filter({ hasText: "Valley" })).toHaveCount(5);
    await expect(members.filter({ hasText: "Valley jack" })).toHaveCount(4);
    await expect(members.filter({ hasText: "Hip" })).toHaveCount(5);
    await page.getByTestId("feature-unfold-6").click();

    await openCutList(page);
    await expectRoofRows(page);
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/roof-valley-b4.png` });

    // A reload keeps the roof and its picks, pinned to 1.9.0 (the latest Roof).
    await page.reload();
    await expect(rows).toHaveCount(7);
    await expectSolved(page);
    await openCutList(page);
    await expectRoofRows(page);
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
    ).features[6]?.feature.params;
    expect(roof?.plugin_version).toBe("1.9.0");
    expect(roof?.inputs.style).toBe("hip");
    expect((roof?.inputs.walls as unknown[]).length).toBe(6);
  });
});
