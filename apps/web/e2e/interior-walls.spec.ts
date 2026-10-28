import { expectSolved, openBuildTool, openCutList } from "./buildFlow";
import { expect, test, type Page } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * INTERIOR-WALLS: B10's partitions (docs/reference-parts/buildings.md B10)
 * built in the app. B7's outline sketch carries two more lines, X 180 (P1,
 * drawn from the back) and Y 132 (P2, from the right wall to P1); the floor
 * and the 2x6 walls stand on it (seeded). Build > Interior wall on the walls
 * frames both partitions and the walls' backing; Build ▾ > Door in
 * "Partition 2", a 2868 measured 50.25 from P1's face, frames its opening.
 * The cut list lists the 12 ladder blocks and the 20 gypsum panels (48 130.5
 * in², 11 sheets of 4x8) under Walls, and the door once.
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

/** B7's 288 x 192 from the origin, fully defined, and the two partitions. */
const PLAN = {
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
    line("e5", [180, 192], [180, 0]),
    line("e6", [288, 132], [180, 132]),
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
    { kind: "distance", entity: "e1", value_mm: 288 * IN },
    { kind: "distance", entity: "e2", value_mm: 192 * IN },
    { kind: "vertical", entity: "e5" },
    { kind: "horizontal", entity: "e6" },
    {
      kind: "point_line_distance",
      point: end("e5", "start"),
      line: "e4",
      value_mm: 180 * IN,
    },
    {
      kind: "point_line_distance",
      point: end("e6", "start"),
      line: "e1",
      value_mm: 132 * IN,
    },
  ],
};

function custom(plugin: string, version: string, inputs: object) {
  return {
    type: "custom",
    version: 1,
    params: { plugin_id: plugin, plugin_version: version, inputs },
  };
}

const ref = (id: string) => ({ kind: "feature", feature_id: id });

async function submit(page: Page): Promise<void> {
  await page.getByTestId("plugin-submit").click();
  await expect(page.getByTestId("plugin-editor")).toBeHidden({
    timeout: 90_000,
  });
}

/** The cut-list row of *member* whose stock reads *stock*. */
function row(page: Page, member: string, stock: RegExp | string) {
  return page
    .getByTestId("cut-list-panel")
    .getByTestId("cut-list-row")
    .filter({
      has: page
        .getByTestId("cut-list-member")
        .getByText(member, { exact: true }),
    })
    .filter({ has: page.getByTestId("cut-list-stock").getByText(stock) });
}

async function shoot(page: Page, name: string): Promise<void> {
  await page.mouse.move(800, 990);
  await page.waitForTimeout(800);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/interior-walls-${name}.png`,
  });
}

test.describe("Interior walls — B10's partitions", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("two partitions frame their backing, a door stands in one, the gypsum is priced by the sheet", async ({
    page,
  }) => {
    test.setTimeout(480_000);
    const account = await seedSession(page);
    const headers = { Authorization: `Bearer ${account.token}` };
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B10 partitions", length_unit: "in" },
      headers,
    });
    expect(created.ok(), await created.text()).toBe(true);
    const partId = ((await created.json()) as { id: string }).id;
    const sketch = await createFeature(page, account.token, partId, {
      name: "Plan",
      feature: { type: "sketch", version: 1, params: PLAN },
      expected_tree_version: 0,
    });
    const floor = await createFeature(page, account.token, partId, {
      name: "Floor",
      feature: custom("loft.floor", "1.3.0", {
        outline: ref(sketch.feature.id),
        joist_profile: "us_2x10",
      }),
      expected_tree_version: sketch.tree_version,
    });
    const walls = await createFeature(page, account.token, partId, {
      name: "Walls",
      feature: custom("loft.wall", "1.4.0", {
        outline: ref(sketch.feature.id),
        floor: ref(floor.feature.id),
        stud_profile: "us_2x6",
        sheathing: "osb_7_16",
      }),
      expected_tree_version: floor.tree_version,
    });

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(3);
    await expectSolved(page);

    // Build ▾ > Interior wall: on the walls, every default B10's.
    await page.getByTestId("build-more").click();
    const tool = page.getByTestId("plugin-tool-loft.interior_wall");
    await expect(tool).toBeEnabled({ timeout: 30_000 });
    await tool.click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("New Interior wall");
    await page
      .getByTestId("plugin-input-host_wall")
      .selectOption(walls.feature.id);
    await expect(page.getByTestId("plugin-input-finish")).toHaveValue(
      "gypsum_1_2",
    );
    await expect(page.getByTestId("plugin-input-backing")).toHaveCount(1);
    await submit(page);
    await expect(rows).toHaveCount(4);
    await expectSolved(page);
    await shoot(page, "partitions");

    // Build ▾ > Door in Partition 2: a 2868, 50.25 from P1's face (X 232).
    await openBuildTool(page, "loft.door", "Door");
    await page
      .getByTestId("plugin-input-host_wall")
      .selectOption({ label: "Interior wall 1" });
    const pick = page.getByTestId("plugin-input-wall_segment");
    await expect(pick).toContainText("Partition 2");
    await expect(pick).not.toContainText("Front");
    await pick
      .getByRole("button", { name: "Partition 2", exact: true })
      .click();
    await page.getByTestId("plugin-input-size").selectOption("door_2868");
    await page.getByTestId("plugin-input-offset_mm").fill("50.25");
    await shoot(page, "door-pick");
    await submit(page);
    await expect(rows).toHaveCount(5);
    await expectSolved(page);

    await openCutList(page);
    await expect(row(page, "Block", "8 ft")).toHaveCount(1, {
      timeout: 90_000,
    });
    await expect(
      row(page, "Block", "8 ft").getByTestId("cut-list-qty"),
    ).toHaveText("12");
    const gypsum = row(page, "Gypsum", "11 × 4x8");
    await expect(gypsum).toHaveCount(1);
    await expect(gypsum.getByTestId("cut-list-qty")).toHaveText("20");
    await expect(gypsum.getByTestId("cut-list-length")).toHaveText(
      "48,130.5 in²",
    );
    const door = row(page, "Door", "2868 door");
    await expect(door).toHaveCount(1);
    await expect(door.getByTestId("cut-list-qty")).toHaveText("1");
    await row(page, "Block", "8 ft").scrollIntoViewIfNeeded();
    await shoot(page, "cut-list");

    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers,
    });
    const features = (
      (await tree.json()) as {
        features: {
          name: string;
          feature: {
            params: {
              plugin_id?: string;
              plugin_version?: string;
              inputs?: Record<string, unknown>;
              expansion?: { role: string }[];
            };
          };
        }[];
      }
    ).features;
    const wallsRow = features.find(
      (f) => f.feature.params.plugin_id === "loft.wall",
    );
    expect(
      wallsRow?.feature.params.expansion?.filter((m) => m.role === "block"),
    ).toHaveLength(9);
    const stored = features.find(
      (f) => f.feature.params.plugin_id === "loft.door",
    );
    expect(stored?.feature.params.plugin_version).toBe("1.4.0");
    expect(stored?.feature.params.inputs?.wall_segment).toEqual(["e6"]);
    expect(stored?.feature.params.inputs?.measure_from).toBe("end");
  });
});
