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
 * FLOOR-FRAME: B5's framed floor of docs/reference-parts/buildings.md from
 * ONE Floor feature, inserted from Build ▾, with no member drawn by hand.
 *
 * In an inch part: Build ▾ > Floor at its defaults (144 x 120, 2x8 joists at
 * 16 in o.c. along the depth, PT 2x6 sill plates) builds 16 member bodies:
 * 10 joists, 2 rims and 4 sills, whose cut list is the spec's floor list.
 * Since loft.floor 1.1.0 (SHEATHING) the default floor also has its 23/32
 * plywood subfloor: 6 panels cut from 6 sheets of 4x8 (SHEET-COUNT-PIECES;
 * 4 before a 1/8 in kerf was lost at each cut, SHEET-KERF).
 * Then the spec's edit, joist spacing 16 -> 12: 13 joists. A reload keeps it.
 */

const PLUGIN = "loft.floor";

/** buildings.md B5's floor cut list: member, qty, length (in), stock. */
const FLOOR_16OC: CutRow[] = [
  ["Joist", "10", "117", "10 ft"],
  ["Rim", "2", "144", "12 ft"],
  ["Sill", "2", "109", "10 ft"],
  ["Sill", "2", "144", "12 ft"],
  ["Subfloor", "6", "17,280 in²", "6 × 4x8"],
];

/** "Joist spacing 16 -> 12. That gives 13 joists". */
const FLOOR_12OC: CutRow[] = [
  ["Joist", "13", "117", "10 ft"],
  ...FLOOR_16OC.slice(1),
];

test.describe("Floor — B5's framed floor from one feature", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("insert from Build ▾, see 10 joists, 2 rims and 4 sills, edit to 12 in o.c., reload", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B5 floor", length_unit: "in" },
      headers: { Authorization: `Bearer ${account.token}` },
    });
    expect(created.ok(), await created.text()).toBe(true);
    const partId = ((await created.json()) as { id: string }).id;

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(0);

    // Build ▾ > Floor (the row holds Wall and Deck): the generated form, in
    // the part's inches, at B5's floor.
    await openBuildTool(page, PLUGIN, "Floor");
    const editor = page.getByTestId("plugin-editor");
    await expect(page.getByTestId("plugin-input-width_mm")).toHaveValue("144");
    await expect(page.getByTestId("plugin-input-depth_mm")).toHaveValue("120");
    await expect(page.getByTestId("plugin-input-joist_spacing_mm")).toHaveValue(
      "16",
    );
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });

    // ONE tree row; it unfolds into its members, drawn by the plugin.
    await expect(rows).toHaveCount(1);
    await expect(rows.nth(0)).toContainText("Floor 1");
    await expectSolved(page);
    await page.getByTestId("feature-unfold-0").click();
    const members = page.getByTestId("feature-member-row");
    await expect(members.filter({ hasText: "Joist" })).toHaveCount(10);
    await expect(members.filter({ hasText: "Rim" })).toHaveCount(2);
    await expect(members.filter({ hasText: "Sill" })).toHaveCount(4);
    await expect(members.filter({ hasText: "Subfloor" })).toHaveCount(6);
    await page.getByTestId("feature-unfold-0").click();

    await openCutList(page);
    await expectTable(page, FLOOR_16OC, "22");
    await expect(page.getByTestId("prop-mass")).toContainText(/\d/, {
      timeout: 60_000,
    });
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/floor-b5.png` });

    // The spec's edit: spacing 16 -> 12 in regenerates the joists.
    await page.getByTestId("feature-select-0").click();
    await expect(editor).toContainText("Edit Floor");
    const spacing = page.getByTestId("plugin-input-joist_spacing_mm");
    await spacing.fill("12");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, FLOOR_12OC, "25");
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/floor-b5-12oc.png` });

    // A reload keeps the edit.
    await page.reload();
    await expect(rows).toHaveCount(1);
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, FLOOR_12OC, "25");
    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const stored = (
      (await tree.json()) as {
        features: { feature: { params: { inputs: Record<string, number> } } }[];
      }
    ).features[0]?.feature.params.inputs;
    expect(stored?.joist_spacing_mm).toBeCloseTo(12 * 25.4, 9);
    expect(stored?.width_mm).toBeCloseTo(144 * 25.4, 9);
  });
});
