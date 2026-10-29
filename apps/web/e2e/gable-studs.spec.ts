import { expectSolved, openBuildTool, openCutList } from "./buildFlow";
import { expect, type Page, test } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * GABLE-END-STUDS: B7's gables (docs/reference-parts/buildings.md) framed
 * and sheathed, as Chief Architect's Build Framing frames a gable wall up to
 * the roof with its studs in line with the wall below. B7's outline, its
 * floor and its sheathed 2x6 walls are seeded; Build ▾ > Roof picks the
 * walls, the front and back define the slope, 2x8 rafters on a 2x10 ridge,
 * and Gable ends keeps its default, Studs and sheathing.
 *
 * The cut list's Roof group gains the gable studs: 2x6, two of each of 11
 * long points (d / 2 - 29/12 at the higher face: 3.2083 .. 43.2083, 262.79
 * in a gable; the left wall lays out from the front, the right from the
 * back, mirror images). The Sheathing group gains a 4x8 line: the 12 gable
 * panels, carried up to the rafters' top plane over the end rafters, cut
 * from 6 sheets. The house is 211 bodies (177 with 1.6.0's roof, plus 22
 * studs and 12 panels). 8/12 re-cuts the studs (2d / 3 - 29/12: 5.0833 ..
 * 58.4167). Golden `b7-gable-ends` pins the geometry.
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

function custom(plugin: string, version: string, inputs: object) {
  return {
    type: "custom",
    version: 1,
    params: { plugin_id: plugin, plugin_version: version, inputs },
  };
}

async function submit(page: Page): Promise<void> {
  const editor = page.getByTestId("plugin-editor");
  const button = page.getByTestId("plugin-submit");
  await expect(button).not.toHaveAttribute("aria-disabled", "true", {
    timeout: 90_000,
  });
  await button.click();
  await expect(editor).toBeHidden({ timeout: 60_000 });
}

/** A choice input: a segmented control for a few short options, else a select. */
async function choose(page: Page, input: string, value: string): Promise<void> {
  const segment = page.getByTestId(`plugin-input-${input}-${value}`);
  if ((await segment.count()) > 0) await segment.click();
  else await page.getByTestId(`plugin-input-${input}`).selectOption(value);
}

/** One side of a side pick, by the name the form gives it. */
function side(page: Page, input: string, name: string) {
  return page
    .getByTestId(`plugin-input-${input}`)
    .getByRole("button", { name, exact: true });
}

/** The Roof group's gable-stud rows: two of each length, shortest first. */
async function expectStuds(page: Page, lengths: string[]): Promise<void> {
  const studs = page
    .getByTestId("cut-list-panel")
    .locator('[data-testid="cut-list-row"][data-member="Gable stud"]');
  await expect(studs).toHaveCount(lengths.length, { timeout: 90_000 });
  for (const [index, length] of lengths.entries()) {
    const row = studs.nth(index);
    await expect(row.getByTestId("cut-list-qty")).toHaveText("2", {
      timeout: 90_000,
    });
    await expect(row.getByTestId("cut-list-length")).toHaveText(length);
    await expect(row.getByTestId("cut-list-stock")).toHaveText("8 ft");
  }
}

async function expectBodies(page: Page, count: number): Promise<void> {
  await expect(page.getByTestId("bodies-section")).toContainText(
    `Bodies · ${count}`,
    { timeout: 120_000 },
  );
}

/** d / 2 - 29/12 at 6/12 and 2d / 3 - 29/12 at 8/12, d the higher face's
 * distance from the nearer eave wall's outside face (11.25, 22.25, ...). */
const AT_6_12 = [
  "3.2083",
  "8.7083",
  "11.2083",
  "16.7083",
  "19.2083",
  "24.7083",
  "27.2083",
  "32.7083",
  "35.2083",
  "40.7083",
  "43.2083",
];
const AT_8_12 = [
  "5.0833",
  "12.4167",
  "15.75",
  "23.0833",
  "26.4167",
  "33.75",
  "37.0833",
  "44.4167",
  "47.75",
  "55.0833",
  "58.4167",
];

async function shot(page: Page, name: string): Promise<void> {
  await page.mouse.move(800, 990);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/${name}.png` });
}

test.describe("Gable ends — B7's gables framed and sheathed", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a new gable frames each end wall up to the roof, and 8/12 re-cuts its studs", async ({
    page,
  }) => {
    test.setTimeout(480_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B7 gable ends", length_unit: "in" },
      headers: { Authorization: `Bearer ${account.token}` },
    });
    expect(created.ok(), await created.text()).toBe(true);
    const partId = ((await created.json()) as { id: string }).id;
    const sketch = await createFeature(page, account.token, partId, {
      name: "Outline",
      feature: { type: "sketch", version: 1, params: OUTLINE },
      expected_tree_version: 0,
    });
    const outline = { kind: "feature", feature_id: sketch.feature.id };
    const floor = await createFeature(page, account.token, partId, {
      name: "Floor",
      feature: custom("loft.floor", "1.3.0", {
        outline,
        joist_profile: "us_2x10",
      }),
      expected_tree_version: sketch.tree_version,
    });
    await createFeature(page, account.token, partId, {
      name: "Wall 1",
      feature: custom("loft.wall", "1.4.0", {
        outline,
        floor: { kind: "feature", feature_id: floor.feature.id },
        stud_profile: "us_2x6",
        sheathing: "osb_7_16",
      }),
      expected_tree_version: floor.tree_version,
    });

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(3);
    await expectSolved(page);

    // Build ▾ > Roof: the walls, the eaves front and back, B7's lumber.
    await openBuildTool(page, "loft.roof", "Roof");
    await page
      .getByTestId("plugin-input-walls-pick")
      .filter({ hasText: "Wall 1" })
      .click();
    await side(page, "slope_walls", "Front").click();
    await side(page, "slope_walls", "Back").click();
    await expect(
      page.getByRole("button", { name: "Defines slope: Front, Back" }),
    ).toBeVisible();
    await choose(page, "rafter_profile", "us_2x8");
    await choose(page, "ridge_profile", "us_2x10");
    // Gable ends: Studs and sheathing by default.
    const gables = page.getByTestId("plugin-input-gable_ends");
    await expect(gables).toHaveValue("studs_sheathing");
    await gables.scrollIntoViewIfNeeded();
    await shot(page, "gable-studs-form");
    await submit(page);
    await expect(rows).toHaveCount(4);
    await expectSolved(page);
    await expectBodies(page, 211);

    // From the gable end: the OSB carried up over the end rafter. Measure on
    // and off drops the highlight a just-saved feature leaves on the house.
    const measure = page.getByTestId("measure-tool");
    await measure.click();
    await measure.click();
    await page.getByTestId("view-right").click();
    await page.getByTestId("view-fit").click();
    await shot(page, "gable-studs-end");
    await page.getByTestId("view-iso").click();
    await page.getByTestId("view-fit").click();
    await shot(page, "gable-studs-iso");

    await openCutList(page);
    await expectStuds(page, AT_6_12);
    const gableOsb = page
      .getByTestId("cut-list-panel")
      .locator('[data-testid="cut-list-row"][data-system="sheathing"]')
      .filter({ hasText: "4x8" })
      .filter({ hasText: "OSB" });
    await expect(gableOsb).toHaveCount(1, { timeout: 90_000 });
    await expect(gableOsb.getByTestId("cut-list-qty")).toHaveText("12");
    await expect(gableOsb.getByTestId("cut-list-stock")).toHaveText("6 × 4x8");
    await page
      .getByTestId("cut-list-panel")
      .locator('[data-testid="cut-list-row"][data-member="Gable stud"]')
      .first()
      .scrollIntoViewIfNeeded();
    await shot(page, "gable-studs-cut-list");

    // 6/12 -> 8/12: the studs are re-cut to the steeper underside.
    await page.getByTestId("feature-select-3").click();
    await expect(page.getByTestId("plugin-editor")).toContainText("Edit Roof");
    await page
      .getByTestId("plugin-input-pitch")
      .selectOption({ label: "8/12" });
    await submit(page);
    await expectSolved(page);
    await expectBodies(page, 211);
    await openCutList(page);
    await expectStuds(page, AT_8_12);

    // Stored at 1.7.0 with the default kept.
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
    expect(features[3]?.feature.params.plugin_version).toBe("1.7.0");
    expect(features[3]?.feature.params.inputs?.gable_ends).toBe(
      "studs_sheathing",
    );
  });
});
