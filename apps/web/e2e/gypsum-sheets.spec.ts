import { expectSolved, openBuildTool, openCutList } from "./buildFlow";
import { expect, test, type Page } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * GYPSUM-SHEETS: drywall bought by the sheet, and a ceiling hung from the
 * ceiling joists (docs/BACKLOG.md; buildings.md B7 and B10). Revit's
 * Ceiling is an element of its own, found from the room's walls; drywall
 * crews hang a ceiling in 4x12s across the joists, every end joint on one.
 *
 * B7 (its outline, floor, 2x6 walls and 6/12 gable with its ceiling joists,
 * seeded): Build ▾ > Ceiling picks the roof and keeps its defaults, 1/2 in
 * sag-resistant ceiling board from 4x12s. The cut list's Walls group gains
 * one line: 8 Ceiling panels, 50,137 in², 8 sheets of 4x12 (three 48 in
 * courses and a 37 in rip, each 140 + 137 with the joint on the joist at
 * X 145.5). Golden `b7-ceiling` pins the geometry.
 *
 * B10 (B7 with its two partitions and P2's 2868, seeded): the partitions' 20 gypsum
 * panels are bought as the 12 4x8s they are cut from (11 by area before),
 * and the ceiling hung after them stops at their boards: 13 panels from 9
 * 4x12s.
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

/** B7's 288 x 192 from the origin, fully defined; B10's two partitions. */
function plan(partitions: boolean) {
  return {
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
      ...(partitions
        ? [line("e5", [180, 192], [180, 0]), line("e6", [288, 132], [180, 132])]
        : []),
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
      ...(partitions
        ? [
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
          ]
        : []),
    ],
  };
}

function custom(plugin: string, version: string, inputs: object) {
  return {
    type: "custom",
    version: 1,
    params: { plugin_id: plugin, plugin_version: version, inputs },
  };
}

const ref = (id: string) => ({ kind: "feature", feature_id: id });

/** Seed B7 (or B10) up to its roof; the roof's feature id. */
async function seedHouse(
  page: Page,
  token: string,
  partitions: boolean,
): Promise<{ partId: string; roofId: string; rows: number }> {
  const created = await page.request.post("/api/v1/parts", {
    data: {
      name: partitions ? "B10 ceiling" : "B7 ceiling",
      length_unit: "in",
    },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(created.ok(), await created.text()).toBe(true);
  const partId = ((await created.json()) as { id: string }).id;
  const sketch = await createFeature(page, token, partId, {
    name: "Plan",
    feature: { type: "sketch", version: 1, params: plan(partitions) },
    expected_tree_version: 0,
  });
  const outline = ref(sketch.feature.id);
  const floor = await createFeature(page, token, partId, {
    name: "Floor",
    feature: custom("loft.floor", "1.3.0", {
      outline,
      joist_profile: "us_2x10",
    }),
    expected_tree_version: sketch.tree_version,
  });
  let last = await createFeature(page, token, partId, {
    name: "Walls",
    feature: custom("loft.wall", "1.5.0", {
      outline,
      floor: ref(floor.feature.id),
      stud_profile: "us_2x6",
      sheathing: "osb_7_16",
    }),
    expected_tree_version: floor.tree_version,
  });
  const walls = last.feature.id;
  if (partitions) {
    last = await createFeature(page, token, partId, {
      name: "Interior wall 1",
      feature: custom("loft.interior_wall", "1.0.0", { host_wall: ref(walls) }),
      expected_tree_version: last.tree_version,
    });
    // B10's 2868 in Partition 2, 50.25 from P1's face (X 232).
    last = await createFeature(page, token, partId, {
      name: "Door 1",
      feature: custom("loft.door", "1.5.0", {
        host_wall: ref(last.feature.id),
        wall_segment: ["e6"],
        size: "door_2868",
        measure_from: "end",
        offset_mm: 50.25 * IN,
      }),
      expected_tree_version: last.tree_version,
    });
  }
  const roof = await createFeature(page, token, partId, {
    name: "Roof",
    feature: custom("loft.roof", "1.8.0", {
      walls: [ref(walls)],
      slope_walls: ["e1", "e3"],
      rafter_profile: "us_2x8",
      ridge_profile: "us_2x10",
    }),
    expected_tree_version: last.tree_version,
  });
  return { partId, roofId: roof.feature.id, rows: partitions ? 6 : 4 };
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
  await page.screenshot({ path: `${SCREENSHOT_DIR}/gypsum-${name}.png` });
}

/** Build ▾ > Ceiling on *roofId*, every default kept. */
async function hangCeiling(page: Page, roofId: string, rows: number) {
  await openBuildTool(page, "loft.ceiling", "Ceiling");
  await page.getByTestId("plugin-input-roof").selectOption(roofId);
  const board = page.getByTestId("plugin-input-finish");
  await expect(board).toHaveValue("gypsum_ceiling_1_2");
  await expect(
    page.getByTestId("plugin-input-finish_sheet-sheet_4x12"),
  ).toHaveAttribute("aria-pressed", "true");
  return async (shot?: string) => {
    if (shot !== undefined) await shoot(page, shot);
    const button = page.getByTestId("plugin-submit");
    await expect(button).not.toHaveAttribute("aria-disabled", "true", {
      timeout: 90_000,
    });
    await button.click();
    await expect(page.getByTestId("plugin-editor")).toBeHidden({
      timeout: 90_000,
    });
    await expect(page.getByTestId("feature-row")).toHaveCount(rows + 1);
    await expectSolved(page);
  };
}

test.describe("Gypsum by the sheet — B7's ceiling and B10's partitions", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("B7's ceiling hangs from its joists in 8 sheets of 4x12", async ({
    page,
  }) => {
    test.setTimeout(480_000);
    const account = await seedSession(page);
    const { partId, roofId, rows } = await seedHouse(
      page,
      account.token,
      false,
    );
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(rows);
    await expectSolved(page);

    const submit = await hangCeiling(page, roofId, rows);
    await submit("ceiling-form");

    await openCutList(page);
    const ceiling = row(page, "Ceiling", "8 × 4x12");
    await expect(ceiling).toHaveCount(1, { timeout: 90_000 });
    await expect(ceiling.getByTestId("cut-list-qty")).toHaveText("8");
    await expect(ceiling.getByTestId("cut-list-length")).toHaveText(
      "50,137 in²",
    );
    await expect(ceiling).toHaveAttribute("data-system", "walls");
    await ceiling.scrollIntoViewIfNeeded();
    await shoot(page, "ceiling-cut-list");
  });

  test("B10's partitions buy 12 sheets and the ceiling stops at their boards", async ({
    page,
  }) => {
    test.setTimeout(480_000);
    const account = await seedSession(page);
    const { partId, roofId, rows } = await seedHouse(page, account.token, true);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(rows);
    await expectSolved(page);

    const submit = await hangCeiling(page, roofId, rows);
    await submit();

    await openCutList(page);
    const gypsum = row(page, "Gypsum", "12 × 4x8");
    await expect(gypsum).toHaveCount(1, { timeout: 90_000 });
    await expect(gypsum.getByTestId("cut-list-qty")).toHaveText("20");
    await expect(gypsum.getByTestId("cut-list-length")).toHaveText(
      "48,130.5 in²",
    );
    const ceiling = row(page, "Ceiling", "9 × 4x12");
    await expect(ceiling).toHaveCount(1);
    await expect(ceiling.getByTestId("cut-list-qty")).toHaveText("13");
    await gypsum.scrollIntoViewIfNeeded();
    await shoot(page, "partitions-cut-list");
  });
});
