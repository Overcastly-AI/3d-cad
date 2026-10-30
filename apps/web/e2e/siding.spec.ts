import { expectSolved, openBuildTool, openCutList } from "./buildFlow";
import { expect, type Page, test } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * SIDING-TRIM: B7 (docs/reference-parts/buildings.md) sided and trimmed, as
 * Chief Architect's wall types carry a siding layer and its Materials List
 * buys siding by the area net of the openings. B7's outline and floor are
 * seeded; Build ▾ > Wall draws its 2x6 walls with 7/16 OSB on the outline,
 * Exterior finish picked from its default None to fibre-cement lap 8-1/4
 * at 7 in, with 10% waste. The door (3068) and five windows (3 x 3040, 2 x 2030) are seeded
 * with their units drawn, then the roof (6/12, 2x8 on a 2x10 ridge).
 *
 * The house is 329 bodies (golden `b7-siding`): the walls' 4 siding layers,
 * 8 corner boards and 23 casing pieces, and the roof's 2 gable layers. The
 * cut list's Siding and trim group lists one lap line: 6 layers, 99 778.90
 * in² net, x 1.10 / 1 008 in² a 12 ft board = 108.89, 109 boards; 8 corner
 * boards of 108.59375 on 10 ft stock; casing in 5 lengths, 1 099.5 in. The
 * Exterior finish set to Vinyl buys 8 squares.
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

async function expectBodies(page: Page, count: number): Promise<void> {
  await expect(page.getByTestId("bodies-section")).toContainText(
    `Bodies · ${count}`,
    { timeout: 180_000 },
  );
}

async function shot(page: Page, name: string): Promise<void> {
  await page.mouse.move(800, 990);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/${name}.png` });
}

function sidingRow(page: Page) {
  return page
    .getByTestId("cut-list-panel")
    .locator('[data-testid="cut-list-row"][data-member="Siding"]');
}

test.describe("Siding and trim — B7's exterior finish", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a new wall sides B7 in lap, 109 boards with its trim, and vinyl buys 8 squares", async ({
    page,
  }) => {
    test.setTimeout(600_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B7 sided", length_unit: "in" },
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
    await createFeature(page, account.token, partId, {
      name: "Floor",
      feature: custom("loft.floor", "1.3.0", {
        outline,
        joist_profile: "us_2x10",
      }),
      expected_tree_version: sketch.tree_version,
    });

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(2);
    await expectSolved(page);

    // Build ▾ > Wall on the outline and the floor: 2x6, OSB, and Exterior
    // finish picked from None (a material choice) to fibre-cement lap.
    await openBuildTool(page, "loft.wall", "Wall");
    const outlineInput = page.getByTestId("plugin-input-outline");
    await expect(outlineInput).toHaveAttribute("data-armed", "true");
    await page.getByTestId("feature-select-0").click();
    await expect(outlineInput).toHaveValue(sketch.feature.id);
    await expect(page.getByTestId("plugin-editor")).toContainText("New Wall");
    await page
      .getByTestId("plugin-input-floor")
      .selectOption({ label: "Floor" });
    await choose(page, "stud_profile", "us_2x6");
    await choose(page, "sheathing", "osb_7_16");
    const finish = page.getByTestId("plugin-input-exterior_finish");
    await expect(finish).toHaveValue("none");
    await finish.selectOption("fibre_cement_lap_8_25");
    await expect(finish).toHaveValue("fibre_cement_lap_8_25");
    await expect(
      page.getByTestId("plugin-input-siding_waste_percent"),
    ).toHaveValue("10");
    await finish.scrollIntoViewIfNeeded();
    await shot(page, "siding-form");
    await submit(page);
    await expect(rows).toHaveCount(3);
    await expectSolved(page);

    // The openings with their units, then the roof, seeded on the walls.
    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const stored = (await tree.json()) as {
      features: {
        id: string;
        feature: { params: { plugin_version?: string } };
      }[];
      tree_version: number;
    };
    const walls = stored.features[2]!;
    expect(walls.feature.params.plugin_version).toBe("1.5.0");
    const host = { kind: "feature", feature_id: walls.id };
    let version = stored.tree_version;
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
    await createFeature(page, account.token, partId, {
      name: "Roof",
      feature: custom("loft.roof", "1.8.0", {
        walls: [host],
        slope_walls: ["e1", "e3"],
        rafter_profile: "us_2x8",
        ridge_profile: "us_2x10",
      }),
      expected_tree_version: version,
    });
    await page.reload();
    await expect(rows).toHaveCount(10);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 300_000,
    });
    await expectBodies(page, 329);

    const measure = page.getByTestId("measure-tool");
    await measure.click();
    await measure.click();
    await page.getByTestId("view-iso").click();
    await page.getByTestId("view-fit").click();
    await shot(page, "siding-iso");
    await page.getByTestId("view-front").click();
    await page.getByTestId("view-fit").click();
    await shot(page, "siding-front");

    // The cut list: the lap by its net area in whole boards, the trim as
    // 5/4x4 lumber, all under Siding and trim.
    await openCutList(page);
    const lap = sidingRow(page);
    await expect(lap).toHaveCount(1, { timeout: 120_000 });
    await expect(lap).toHaveAttribute("data-system", "siding");
    await expect(lap.getByTestId("cut-list-qty")).toHaveText("6");
    await expect(lap.getByTestId("cut-list-area")).toHaveText(
      "99,778.9024 in²",
    );
    await expect(lap.getByTestId("cut-list-stock")).toHaveText("109 boards");
    const boards = page
      .getByTestId("cut-list-panel")
      .locator('[data-testid="cut-list-row"][data-member="Corner board"]');
    await expect(boards).toHaveCount(1);
    await expect(boards.getByTestId("cut-list-qty")).toHaveText("8");
    await expect(boards.getByTestId("cut-list-length")).toHaveText("108.5938");
    await expect(boards.getByTestId("cut-list-stock")).toHaveText("10 ft");
    const casing = page
      .getByTestId("cut-list-panel")
      .locator('[data-testid="cut-list-row"][data-member="Casing"]');
    await expect(casing).toHaveCount(5);
    const lengths = await casing.getByTestId("cut-list-length").allInnerTexts();
    expect(lengths).toEqual(["31", "43", "44.5", "55", "85.5"]);
    const counts = await casing.getByTestId("cut-list-qty").allInnerTexts();
    expect(counts).toEqual(["4", "10", "1", "6", "2"]);
    await lap.scrollIntoViewIfNeeded();
    await shot(page, "siding-cut-list");

    // Vinyl: the same faces, bought by the square.
    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("plugin-editor")).toContainText("Edit Wall");
    await page
      .getByTestId("plugin-input-exterior_finish")
      .selectOption("vinyl_d4");
    await submit(page);
    // The whole house re-solves under its edited walls (329 bodies).
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 300_000,
    });
    await expectBodies(page, 329);
    // The list measures the re-solved house; a request queued behind the
    // solve may be turned away (geometry's admission control), so reopen it
    // until it lists.
    await expect(async () => {
      await page.getByTestId("cut-list-tool").click();
      await openCutList(page);
      await expect(sidingRow(page).getByTestId("cut-list-stock")).toHaveText(
        "8 squares",
        { timeout: 30_000 },
      );
    }).toPass({ timeout: 300_000 });
    await expect(sidingRow(page)).toHaveAttribute(
      "data-profile",
      "Vinyl siding, double 4",
    );
  });
});
