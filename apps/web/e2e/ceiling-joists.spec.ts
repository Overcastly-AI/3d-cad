import { expectSolved, openBuildTool, openCutList } from "./buildFlow";
import { expect, type Page, test } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * CEILING-JOISTS: B7's gable (docs/reference-parts/buildings.md) tied by its
 * ceiling joists, as Chief Architect's Build Framing lays them out with the
 * roof (IRC R802.5.2: the joists at the plates are the rafter ties). B7's
 * outline, its floor and its 2x6 walls on the floor are seeded; Build ▾ >
 * Roof picks the walls, the front and back define the slope, 2x8 rafters on
 * a 2x10 ridge, and Ceiling joists keeps its default, Beside each common.
 *
 * The cut list's Roof group gains one line: 11 ceiling joists 2x8, 192 in,
 * one 16 ft piece each (never spliced), beside the inner commons (c = 24 ..
 * 264; the gable-end rafters get none). The sketch's 288 set to 336 re-lays
 * them with the rafters: 13. Golden `b7-ceiling-joists` pins the geometry
 * (each end snipped 1.560920 down and 3.121840 along to the roof plane).
 * Gable ends (roof 1.7.0, GABLE-END-STUDS: gable-studs.spec.ts) is set to
 * None here, so the Roof group is the rafters, the ridge and the joists.
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

/** Open the outline sketch, set its *from* length dimension, save it. */
async function editLength(page: Page, from: string, typed: string) {
  await page.getByTestId("feature-select-0").click();
  await expect(page.getByTestId("sketch-save")).toBeVisible({
    timeout: 30_000,
  });
  await page
    .locator('[data-testid^="glyph-"][data-kind="distance"]')
    .filter({ hasText: new RegExp(`^${from}$`) })
    .click();
  const cell = page.getByTestId("dimension-input");
  await expect(cell).toHaveValue(from);
  await cell.fill(typed);
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("dimension-editor")).toHaveCount(0);
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expectSolved(page);
}

/** The Roof group's rows: member, qty, length, stock. */
async function expectRoof(
  page: Page,
  rows: [string, string, string, string][],
): Promise<void> {
  const roof = page
    .getByTestId("cut-list-panel")
    .locator('[data-testid="cut-list-row"][data-system="roof"]');
  await expect(roof).toHaveCount(rows.length, { timeout: 90_000 });
  for (const [index, [member, qty, length, stock]] of rows.entries()) {
    const row = roof.nth(index);
    await expect(row.getByTestId("cut-list-member")).toHaveText(member);
    await expect(row.getByTestId("cut-list-qty")).toHaveText(qty, {
      timeout: 90_000,
    });
    await expect(row.getByTestId("cut-list-length")).toHaveText(length);
    await expect(row.getByTestId("cut-list-stock")).toHaveText(stock);
  }
}

test.describe("Ceiling joists — B7's gable tied at the plates", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a new gable on the walls ties every inner common pair, and 28 ft frames 13", async ({
    page,
  }) => {
    test.setTimeout(480_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B7 ceiling joists", length_unit: "in" },
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
    await expect(page.getByTestId("plugin-input-span_mm")).toHaveCount(0);
    await side(page, "slope_walls", "Front").click();
    await side(page, "slope_walls", "Back").click();
    await expect(
      page.getByRole("button", { name: "Defines slope: Front, Back" }),
    ).toBeVisible();
    await choose(page, "rafter_profile", "us_2x8");
    await choose(page, "ridge_profile", "us_2x10");
    // Ceiling joists: Beside each common by default, 2x8.
    const joists = page.getByTestId("plugin-input-ceiling_joists");
    await expect(joists).toHaveValue("beside_common");
    await expect(
      page.getByTestId("plugin-input-ceiling_joist_profile"),
    ).toHaveValue("us_2x8");
    await choose(page, "gable_ends", "none");
    await joists.scrollIntoViewIfNeeded();
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/ceiling-joists-form.png`,
    });
    await submit(page);
    await expect(rows).toHaveCount(4);
    await expectSolved(page);

    // From the gable end: the joists' band on the plates, under the
    // rafters (no gable studs yet). Measure on and off drops the highlight a
    // just-saved feature leaves on the house.
    const measure = page.getByTestId("measure-tool");
    await measure.click();
    await measure.click();
    await page.getByTestId("view-right").click();
    await page.getByTestId("view-fit").click();
    await page.mouse.move(800, 990);
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/ceiling-joists-end.png` });
    await page.getByTestId("view-iso").click();

    await openCutList(page);
    await expectRoof(page, [
      ["Rafter", "26", "123.5341", "12 ft"],
      ["Ridge", "1", "288", "24 ft"],
      ["Ceiling joist", "11", "192", "16 ft"],
    ]);
    await page
      .getByTestId("cut-list-panel")
      .locator('[data-testid="cut-list-row"][data-member="Ceiling joist"]')
      .scrollIntoViewIfNeeded();
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/ceiling-joists-cut-list.png`,
    });

    // 24 -> 28 ft: one sketch dimension; the joists follow the rafters.
    await editLength(page, "288", "336");
    await openCutList(page);
    await expectRoof(page, [
      ["Rafter", "30", "123.5341", "12 ft"],
      ["Ridge", "1", "336", "2 × 14 ft"],
      ["Ceiling joist", "13", "192", "16 ft"],
    ]);

    // Stored at 1.8.0 with the joists' default kept.
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
    expect(features[3]?.feature.params.plugin_version).toBe("1.8.0");
    expect(features[3]?.feature.params.inputs?.ceiling_joists).toBe(
      "beside_common",
    );
  });
});
