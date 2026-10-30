import { expectSolved, openBuildTool, openCutList } from "./buildFlow";
import { expect, type Page, test } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * SECOND-FLOOR: B7 goes up a storey (docs/reference-parts/buildings.md B7),
 * as Chief Architect frames the floor of the level above on the walls below
 * (Build Floor) and cuts its stairwell (Auto Stairwell). B7's outline, its
 * floor and its sheathed 2x6 walls are seeded; Build ▾ > Floor picks the
 * outline and the walls under it (the roof's Pick Walls), 2x10 joists and a
 * Framed opening (its defaults are B7's well, 43.5 x 120 clear at X 18.25,
 * Y 36). The upper walls, the roof and the free stair are seeded on it.
 *
 * Floor 2 has no sills: 17 joists, 2 trimmers (the joists at X 16 and 64
 * doubled inside), 4 headers 2x10 x 43.5, 4 tail joists of 31.5, 2 rims and
 * 15 subfloor pieces (44 bodies). The house is 401 bodies: floor 1's 39,
 * the walls' 100 a storey, floor 2's 44, the roof's 72 and the stair's 46.
 * Golden `b7-second-floor` pins the geometry.
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

/** The cut list's Floor rows of *member*: [qty, length] each, in order. */
async function expectRows(
  page: Page,
  member: string,
  rows: [string, string][],
): Promise<void> {
  const found = page
    .getByTestId("cut-list-panel")
    .locator(`[data-testid="cut-list-row"][data-member="${member}"]`);
  await expect(found).toHaveCount(rows.length, { timeout: 90_000 });
  for (const [index, [qty, length]] of rows.entries()) {
    await expect(found.nth(index).getByTestId("cut-list-qty")).toHaveText(qty);
    await expect(found.nth(index).getByTestId("cut-list-length")).toHaveText(
      length,
    );
  }
}

test.describe("Second floor — B7 goes up a storey with a stairwell", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a floor on the walls below frames its well, and a stair climbs through it", async ({
    page,
  }) => {
    test.setTimeout(600_000);
    const account = await seedSession(page);
    const auth = { Authorization: `Bearer ${account.token}` };
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B7 two storeys", length_unit: "in" },
      headers: auth,
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
      name: "Floor 1",
      feature: custom("loft.floor", "1.4.0", {
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
      }),
      expected_tree_version: floor.tree_version,
    });

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(3);
    await expectSolved(page);
    await expectBodies(page, 139);

    // Build ▾ > Floor: on the outline and the walls under it, 2x10, with a
    // framed stairwell at its defaults (B7's).
    await openBuildTool(page, "loft.floor", "Floor");
    await page
      .getByTestId("plugin-input-outline")
      .selectOption(sketch.feature.id);
    await page
      .getByTestId("plugin-input-walls-pick")
      .filter({ hasText: "Wall 1" })
      .click();
    // On walls, the base elevation and the sills are the walls' plate's.
    await expect(page.getByTestId("plugin-input-elevation_mm")).toHaveCount(0);
    await choose(page, "joist_profile", "us_2x10");
    await expect(page.getByTestId("plugin-input-well_width_mm")).toHaveCount(0);
    await choose(page, "stairwell", "framed");
    await expect(page.getByTestId("plugin-input-well_width_mm")).toHaveValue(
      "43.5",
    );
    await expect(page.getByTestId("plugin-input-well_depth_mm")).toHaveValue(
      "120",
    );
    await page.getByTestId("plugin-input-stairwell").scrollIntoViewIfNeeded();
    await shot(page, "second-floor-form");
    await submit(page);
    await expect(rows).toHaveCount(4);
    await expectSolved(page);
    await expectBodies(page, 139 + 44);

    // The storey above, its roof and the free stair, seeded on floor 2.
    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: auth,
    });
    const body = (await tree.json()) as {
      tree_version: number;
      features: {
        id: string;
        feature: {
          params: { plugin_version?: string; inputs?: Record<string, unknown> };
        };
      }[];
    };
    const floor2 = body.features[3];
    expect(floor2?.feature.params.plugin_version).toBe("1.4.0");
    expect(floor2?.feature.params.inputs?.stairwell).toBe("framed");
    expect(floor2?.feature.params.inputs?.walls).toEqual([
      { kind: "feature", feature_id: walls.feature.id },
    ]);
    const upper = await createFeature(page, account.token, partId, {
      name: "Wall 2",
      feature: custom("loft.wall", "1.5.0", {
        outline,
        floor: { kind: "feature", feature_id: floor2?.id },
        stud_profile: "us_2x6",
        sheathing: "osb_7_16",
      }),
      expected_tree_version: body.tree_version,
    });
    const roof = await createFeature(page, account.token, partId, {
      name: "Roof",
      feature: custom("loft.roof", "1.8.0", {
        walls: [{ kind: "feature", feature_id: upper.feature.id }],
        slope_walls: ["e1", "e3"],
        rafter_profile: "us_2x8",
        ridge_profile: "us_2x10",
      }),
      expected_tree_version: upper.tree_version,
    });
    // 14 risers of 7.6496 and 13 treads of 10, the head on the far header's
    // face (Y 156): the top nosing 1.875 in front of it. The near header's
    // face is 118.125 from it: 80.39 in of headroom (IRC R311.7.2).
    await createFeature(page, account.token, partId, {
      name: "Stair",
      feature: custom("loft.stair", "1.0.0", {
        rise_mm: 107.09375 * IN,
        x_mm: 40 * IN,
        y_mm: 154.125 * IN,
        bottom_mm: 11.46875 * IN,
        direction: "neg_y",
        tread_depth_mm: 10 * IN,
        risers: "closed",
        opening_length_mm: 118.125 * IN,
        floor_depth_mm: 9.96875 * IN,
      }),
      expected_tree_version: roof.tree_version,
    });
    await page.reload();
    await expect(rows).toHaveCount(7);
    await expectSolved(page);
    await expectBodies(page, 401);

    // Measure on and off drops the highlight a just-saved feature leaves.
    const measure = page.getByTestId("measure-tool");
    await measure.click();
    await measure.click();
    await page.getByTestId("view-iso").click();
    await page.getByTestId("view-fit").click();
    await shot(page, "second-floor-iso");
    // From above, the well's framing round the stair.
    await page.getByTestId("view-top").click();
    await page.getByTestId("view-fit").click();
    await shot(page, "second-floor-top");

    await openCutList(page);
    await expectRows(page, "Trimmer", [["2", "189"]]);
    await expectRows(page, "Header", [["4", "43.5"]]);
    await expectRows(page, "Tail joist", [["4", "31.5"]]);
    await expectRows(page, "Riser", [["13", "36"]]);
    await page
      .getByTestId("cut-list-panel")
      .locator('[data-testid="cut-list-row"][data-member="Trimmer"]')
      .scrollIntoViewIfNeeded();
    await shot(page, "second-floor-cut-list");
  });
});
