import {
  type CutRow,
  expectSolved,
  expectTable,
  openBuildTool,
  openCutList,
} from "./buildFlow";
import { expect, test } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * FLOOR-JOIST-SPAN: a Floor on an outline bears on its long walls by
 * default, so its joists span the short way whatever the drawing, and
 * "Joists bear on" turns them (Chief Architect's joist direction, Revit's
 * span direction).
 *
 * B7's outline turned a quarter: 192 wide (X) by 288 deep (Y). At the
 * default, Long walls, the rims run on the 288 sides and 19 joists span
 * 189 along X. Front and back turns them: 13 joists at 285 along Y, the
 * rims at 192 (golden `b7-floor-left-right`, turned).
 */

const IN = 25.4;

function line(id: string, a: [number, number], b: [number, number]) {
  return {
    id,
    kind: "line",
    construction: false,
    start: { x: a[0] * IN, y: a[1] * IN },
    end: { x: b[0] * IN, y: b[1] * IN },
  };
}

const end = (entity: string, point: "start" | "end") => ({ entity, point });

/** 192 x 288 from the origin, fully defined. */
const OUTLINE = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    {
      id: "origin",
      kind: "point",
      construction: true,
      position: { x: 0, y: 0 },
    },
    line("e1", [0, 0], [192, 0]),
    line("e2", [192, 0], [192, 288]),
    line("e3", [192, 288], [0, 288]),
    line("e4", [0, 288], [0, 0]),
  ],
  constraints: [
    { kind: "fixed", point: { entity: "origin", point: "position" } },
    { kind: "horizontal", entity: "e1" },
    { kind: "coincident", a: end("e1", "end"), b: end("e2", "start") },
    { kind: "vertical", entity: "e2" },
    { kind: "coincident", a: end("e2", "end"), b: end("e3", "start") },
    { kind: "horizontal", entity: "e3" },
    { kind: "coincident", a: end("e3", "end"), b: end("e4", "start") },
    { kind: "vertical", entity: "e4" },
    { kind: "coincident", a: end("e4", "end"), b: end("e1", "start") },
    {
      kind: "coincident",
      a: end("e1", "start"),
      b: { entity: "origin", point: "position" },
    },
    { kind: "distance", entity: "e1", value_mm: 192 * IN },
    { kind: "distance", entity: "e2", value_mm: 288 * IN },
  ],
};

/** Long walls: the joists span the 16 ft way. */
const LONG_WALLS: CutRow[] = [
  ["Joist", "19", "189", "16 ft"],
  ["Rim", "2", "288", "2 × 12 ft"],
  ["Sill", "2", "181", "16 ft"],
  ["Sill", "2", "288", "2 × 12 ft"],
  ["Subfloor", "14", "55,296 in²", "12 × 4x8"],
];

/** Front and back: the joists span the 24 ft way. */
const FRONT_AND_BACK: CutRow[] = [
  ["Joist", "13", "285", "2 × 12 ft"],
  ["Rim", "2", "192", "16 ft"],
  ["Sill", "2", "192", "16 ft"],
  ["Sill", "2", "277", "2 × 12 ft"],
  ["Subfloor", "15", "55,296 in²", "12 × 4x8"],
];

test.describe("Floor — Joists bear on", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("an outline floor spans its short way; Front and back turns the joists", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "Deep floor", length_unit: "in" },
      headers: { Authorization: `Bearer ${account.token}` },
    });
    expect(created.ok(), await created.text()).toBe(true);
    const partId = ((await created.json()) as { id: string }).id;
    const sketch = await createFeature(page, account.token, partId, {
      name: "Outline",
      feature: { type: "sketch", version: 1, params: OUTLINE },
      expected_tree_version: 0,
    });
    const sketchId = sketch.feature.id;

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(1);
    await expectSolved(page);

    // Build ▾ > Floor on the outline, 2x10 joists, the bearing left at
    // its default.
    await openBuildTool(page, "loft.floor", "Floor");
    const editor = page.getByTestId("plugin-editor");
    await page.getByTestId("plugin-input-outline").selectOption(sketchId);
    await page
      .getByTestId("plugin-input-joist_profile")
      .selectOption("us_2x10");
    const bearing = page.getByTestId("plugin-input-joists_bear_on");
    await expect(bearing).toHaveValue("long_walls");
    await expect(bearing.locator("option")).toHaveText([
      "Long walls",
      "Front and back",
      "Left and right",
    ]);
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 60_000 });
    await expect(rows).toHaveCount(2);
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, LONG_WALLS, "39");
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/floor-joist-span-long.png`,
    });

    // Front and back: the joists turn to run front to back.
    await page.getByTestId("feature-select-1").click();
    await expect(editor).toContainText("Edit Floor");
    await bearing.selectOption({ label: "Front and back" });
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 60_000 });
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, FRONT_AND_BACK, "34");
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/floor-joist-span-front-back.png`,
    });

    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const floor = (
      (await tree.json()) as {
        features: {
          feature: {
            params: {
              plugin_version?: string;
              inputs?: Record<string, unknown>;
            };
          };
        }[];
      }
    ).features[1]?.feature.params;
    expect(floor?.plugin_version).toBe("1.3.0");
    expect(floor?.inputs?.joists_bear_on).toBe("front_back");
  });
});
