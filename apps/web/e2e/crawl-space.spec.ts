import { expectSolved, openBuildTool, openCutList } from "./buildFlow";
import { expect, type Page, test } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * CRAWL-SPACE: B9 (docs/reference-parts/buildings.md) in the real app, as
 * Chief Architect and Revit build a crawl space's stem wall from the exterior
 * wall loop. B7's outline and its floor are seeded; Build ▾ > Foundation
 * picks the outline and Floor on it = that floor, every default kept: an
 * 8 in poured stem on a 16 x 8 in footing, a 24 in crawl, five vents and the
 * access cut from the stem's top.
 *
 * The cut list leads with Foundation (FOUNDATION-TAKEOFF): the footing,
 * 2.55 yd³ ordered as its own delivery of 2.75 (2.67 with the 5% allowance,
 * rounded up to 1/4), with its #4 loops of 888 and 968 in, 5 sticks each;
 * the stem, 4.04 yd³ ordered 4.25 (4.24), 7.00 in all; the 18 anchor bolts
 * cast into the stem for the floor's sills (5 + 5 + 4 + 4); and 5 vents
 * 16 x 8 and 1 access door 24 x 16, Each. A 17.5 in crawl then
 * warns (IRC R317.1) and still builds. Golden `b9-crawl-space` pins the
 * geometry.
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

/** B7's outline: 288 x 192 from the origin, fully defined. */
const OUTLINE = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    {
      id: "origin",
      kind: "point",
      construction: true,
      position: { x: 0, y: 0 },
    },
    line("e1", [0, 0], [288, 0]),
    line("e2", [288, 0], [288, 192]),
    line("e3", [288, 192], [0, 192]),
    line("e4", [0, 192], [0, 0]),
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
    { kind: "distance", entity: "e1", name: "length", value_mm: 288 * IN },
    { kind: "distance", entity: "e2", name: "width", value_mm: 192 * IN },
  ],
};

async function submit(page: Page): Promise<void> {
  const editor = page.getByTestId("plugin-editor");
  const button = page.getByTestId("plugin-submit");
  await expect(button).not.toHaveAttribute("aria-disabled", "true", {
    timeout: 90_000,
  });
  await button.click();
  await expect(editor).toBeHidden({ timeout: 60_000 });
}

/** The Foundation group's rows: member, qty, length, stock. */
const FOUNDATION: [string, string, string, string][] = [
  ["Footing", "1", "2.55 yd³", "2.75 yd³"],
  ["Rebar", "1", "888", "5 × 20 ft"],
  ["Rebar", "1", "968", "5 × 20 ft"],
  ["Stem wall", "1", "4.04 yd³", "4.25 yd³"],
  ["Anchor bolt", "18", "—", "Each"],
  ["Vent 16 x 8", "5", "—", "Each"],
  ["Access door 24 x 16", "1", "—", "Each"],
];

test.describe("Crawl space — B9 under B7's floor", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a foundation under the floor lists its pours, rebar, the sills' bolts, vents and access door, and a low crawl warns", async ({
    page,
  }) => {
    test.setTimeout(360_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B9 on a crawl space", length_unit: "in" },
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
    const floor = await createFeature(page, account.token, partId, {
      name: "Floor",
      feature: {
        type: "custom",
        version: 1,
        params: {
          plugin_id: "loft.floor",
          plugin_version: "1.3.0",
          inputs: {
            outline: { kind: "feature", feature_id: sketchId },
            joist_profile: "us_2x10",
          },
        },
      },
      expected_tree_version: sketch.tree_version,
    });
    const floorId = floor.feature.id;

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(2);
    await expectSolved(page);

    // Build ▾ > Foundation on the outline, under the floor, every default kept.
    await openBuildTool(page, "loft.foundation", "Foundation");
    await page.getByTestId("plugin-input-outline").selectOption(sketchId);
    await expect(page.getByTestId("plugin-input-width_mm")).toHaveCount(0);
    await page.getByTestId("plugin-input-floor").selectOption(floorId);
    await expect(page.getByTestId("plugin-input-crawl_height_mm")).toHaveValue(
      "24",
    );
    await expect(page.getByTestId("plugin-input-waste_percent")).toHaveValue(
      "5",
    );
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/crawl-space-form.png` });
    await submit(page);
    await expect(rows).toHaveCount(3);
    await expectSolved(page);

    // From the front: the stem and footing under the floor, the vents and
    // the access in the stem's top.
    await page.getByTestId("view-front").click();
    await page.getByTestId("view-fit").click();
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/crawl-space-front.png` });
    await page.getByTestId("view-iso").click();

    await openCutList(page);
    const panel = page.getByTestId("cut-list-panel");
    const foundation = panel.locator(
      '[data-testid="cut-list-row"][data-system="foundation"]',
    );
    await expect(foundation).toHaveCount(FOUNDATION.length, {
      timeout: 90_000,
    });
    for (const [index, [member, qty, length, stock]] of FOUNDATION.entries()) {
      const row = foundation.nth(index);
      await expect(row.getByTestId("cut-list-member")).toHaveText(member);
      await expect(row.getByTestId("cut-list-qty")).toHaveText(qty);
      await expect(row.getByTestId("cut-list-length")).toHaveText(length);
      await expect(row.getByTestId("cut-list-stock")).toHaveText(stock);
    }
    // The floor is unchanged: its four sills, 2 of 288 and 2 of 181.
    const sills = panel.locator(
      '[data-testid="cut-list-row"][data-member="Sill"]',
    );
    await expect(sills).toHaveCount(2);
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/crawl-space-cut-list.png`,
    });

    // A 17.5 in crawl: under R317.1's 18 in, it warns and still builds.
    await page.getByTestId("feature-select-2").click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("Edit Foundation");
    await expect(page.getByTestId("plugin-warning")).toHaveCount(0);
    await page.getByTestId("plugin-input-crawl_height_mm").fill("17.5");
    await submit(page);
    await expectSolved(page);
    await page.getByTestId("feature-select-2").click();
    const warning = page.getByTestId("plugin-warning");
    await expect(warning).toContainText("Crawl height");
    await expect(warning).toContainText("17.5 in");
    await expect(warning).toContainText("R317.1");
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/crawl-space-warning.png`,
    });
    await page.getByTestId("plugin-cancel").click();
    await expect(editor).toBeHidden();

    // Stored at 1.1.0 with its allowance and the crawl as typed.
    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const features = (
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
    ).features;
    expect(features[2]?.feature.params.plugin_version).toBe("1.1.0");
    expect(features[2]?.feature.params.inputs?.waste_percent).toBe(5);
    expect(features[2]?.feature.params.inputs?.crawl_height_mm).toBeCloseTo(
      17.5 * IN,
      6,
    );
  });
});
