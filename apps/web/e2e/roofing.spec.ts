import { openBuildTool, openCutList } from "./buildFlow";
import { expect, type Page, test } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * ROOFING: B7 (docs/reference-parts/buildings.md) dried in, as Chief
 * Architect's roof planes carry a sheathing and a roofing layer and its
 * Materials List counts roofing in squares and drip edge by length. B7's
 * outline, floor, walls sided in fibre-cement lap and its door and five
 * windows are seeded; Build ▾ > Roof picks the walls, the front and back
 * define the slope, 2x8 rafters on a 2x10 ridge, and Roofing is picked from
 * its default None to Asphalt shingles, 10% waste.
 *
 * The house is 361 bodies (golden `b7-roofing`): b7-siding's 329, 24 deck
 * panels, 4 fascia boards and 4 rake boards. The cut list's Roof group: the
 * deck, 70 246.42 in² on 21 4x8 sheets (each sheet jointed on a rafter's
 * centre); 17 bundles of shingles (4.8782 squares x 1.10 x 3 = 16.10); 1
 * roll of underlayment; drip edge in 14 10 ft sticks; 49 ft of starter and
 * 25 ft of ridge cap; the 1x10 fascia on 4 14 ft sticks and the 1x6 rakes
 * on 4 12 ft. Siding and trim's casing nests on 14 8 ft sticks, not 23.
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

/** B7's openings, from each wall's start (the front runs from X 288). */
const OPENINGS: [string, string, string, number, string][] = [
  ["Door", "loft.door", "e1", 144, "door_3068"],
  ["Window 1", "loft.window", "e1", 228, "window_3040"],
  ["Window 2", "loft.window", "e1", 60, "window_3040"],
  ["Window 3", "loft.window", "e3", 144, "window_3040"],
  ["Window 4", "loft.window", "e4", 90.5, "window_2030"],
  ["Window 5", "loft.window", "e2", 90.5, "window_2030"],
];

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

function side(page: Page, input: string, name: string) {
  return page
    .getByTestId(`plugin-input-${input}`)
    .getByRole("button", { name, exact: true });
}

async function expectBodies(page: Page, count: number): Promise<void> {
  await expect(page.getByTestId("bodies-section")).toContainText(
    `Bodies · ${count}`,
    { timeout: 300_000 },
  );
}

async function shot(page: Page, name: string): Promise<void> {
  await page.mouse.move(800, 990);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/${name}.png` });
}

function row(page: Page, member: string) {
  return page
    .getByTestId("cut-list-panel")
    .locator(`[data-testid="cut-list-row"][data-member="${member}"]`);
}

test.describe("Roofing — B7 dried in", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a roof picks Asphalt shingles: a deck on 21 sheets, 17 bundles, 14 sticks of drip edge, trim nested", async ({
    page,
  }) => {
    test.setTimeout(720_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B7 roofed", length_unit: "in" },
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
    const walls = await createFeature(page, account.token, partId, {
      name: "Wall 1",
      feature: custom("loft.wall", "1.5.0", {
        outline,
        floor: { kind: "feature", feature_id: floor.feature.id },
        stud_profile: "us_2x6",
        sheathing: "osb_7_16",
        exterior_finish: "fibre_cement_lap_8_25",
      }),
      expected_tree_version: floor.tree_version,
    });
    const host = { kind: "feature", feature_id: walls.feature.id };
    let version = walls.tree_version;
    for (const [name, plugin, segment, offset, size] of OPENINGS) {
      const made = await createFeature(page, account.token, partId, {
        name,
        feature: custom(plugin, "1.5.0", {
          host_wall: host,
          wall_segment: [segment],
          measure_from: "start",
          offset_mm: offset * IN,
          size,
        }),
        expected_tree_version: version,
      });
      version = made.tree_version;
    }

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(9);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 300_000,
    });

    // Build ▾ > Roof: the walls, the eaves front and back, B7's lumber, and
    // Roofing picked from None (a material choice) to Asphalt shingles.
    await openBuildTool(page, "loft.roof", "Roof");
    await page
      .getByTestId("plugin-input-walls-pick")
      .filter({ hasText: "Wall 1" })
      .click();
    await side(page, "slope_walls", "Front").click();
    await side(page, "slope_walls", "Back").click();
    await choose(page, "rafter_profile", "us_2x8");
    await choose(page, "ridge_profile", "us_2x10");
    const roofing = page.getByTestId("plugin-input-roofing");
    await expect(roofing).toHaveValue("none");
    await roofing.selectOption("asphalt_shingles");
    await expect(roofing).toHaveValue("asphalt_shingles");
    await expect(
      page.getByTestId("plugin-input-roofing_waste_percent"),
    ).toHaveValue("10");
    await roofing.scrollIntoViewIfNeeded();
    await shot(page, "roofing-form");
    await submit(page);
    await expect(rows).toHaveCount(10);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 300_000,
    });
    await expectBodies(page, 361);

    // Measure on and off drops the highlight a just-saved feature leaves.
    const measure = page.getByTestId("measure-tool");
    await measure.click();
    await measure.click();
    await page.getByTestId("view-iso").click();
    await page.getByTestId("view-fit").click();
    await shot(page, "roofing-iso");
    await page.getByTestId("view-right").click();
    await page.getByTestId("view-fit").click();
    await shot(page, "roofing-gable");

    // The cut list: the deck by its sheets, the covering by the bundle,
    // roll, stick and foot, the trim nested on its sticks.
    await openCutList(page);
    const deck = row(page, "Roof deck");
    await expect(deck).toHaveCount(1, { timeout: 120_000 });
    await expect(deck).toHaveAttribute("data-system", "roof");
    await expect(deck.getByTestId("cut-list-qty")).toHaveText("24");
    await expect(deck.getByTestId("cut-list-area")).toHaveText(
      "70,246.4249 in²",
    );
    await expect(deck.getByTestId("cut-list-stock")).toHaveText("21 × 4x8");
    await expect(
      row(page, "Shingles").getByTestId("cut-list-stock"),
    ).toHaveText("17 bundles");
    await expect(
      row(page, "Underlayment").getByTestId("cut-list-stock"),
    ).toHaveText("1 roll");
    const drip = row(page, "Drip edge");
    await expect(drip.getByTestId("cut-list-qty")).toHaveText("6");
    await expect(drip.getByTestId("cut-list-stock")).toHaveText("14 × 10 ft");
    await expect(row(page, "Starter").getByTestId("cut-list-stock")).toHaveText(
      "49 ft",
    );
    await expect(
      row(page, "Ridge cap").getByTestId("cut-list-stock"),
    ).toHaveText("25 ft");
    const fascia = row(page, "Fascia");
    await expect(fascia).toHaveAttribute("data-profile", "1x10");
    await expect(fascia.getByTestId("cut-list-stock")).toHaveText("4 × 14 ft");
    await expect(
      row(page, "Rake board").getByTestId("cut-list-stock"),
    ).toHaveText("4 × 12 ft");
    const casing = row(page, "Casing");
    await expect(casing.getByTestId("cut-list-qty")).toHaveText("23");
    await expect(casing.getByTestId("cut-list-stock")).toHaveText("14 × 8 ft");
    await deck.scrollIntoViewIfNeeded();
    await shot(page, "roofing-cut-list");
  });
});
