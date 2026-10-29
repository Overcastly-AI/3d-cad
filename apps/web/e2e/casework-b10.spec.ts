import { expectSolved, openBuildTool, openCutList } from "./buildFlow";
import { expect, test, type Page } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * CASEWORK-B10 C4 (docs/reference-parts/casework.md): a bath vanity on B10's
 * partition P1, built in the app. B10's plan, floor, 2x6 walls and Interior
 * wall are seeded; Build ▾ > Cabinets on "Partition 1", its Left face (+X,
 * P1 drawn from the back), 1/2 in from its back end: a V3021 and a VDB1521
 * (3 drawers) in 3/4 melamine, `loft.cabinets` 1.1.0, the backs on P1's
 * gypsum (golden c4-vanity-b10-p1). Its Casework lines: the melamine on 2
 * sheets, the drawer boxes' 1/2 and 1/4 plywood on one each, 49 ft of PVC
 * banding (578.75 in), 4 hinges and 3 pairs of 20 in slides, each priced
 * from its blank. V3021 -> V3621 moves the VDB clear of P2; a 21 in VDB
 * would run through P2 and is refused, naming it.
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

/** B7's 288 x 192 from the origin and B10's two partitions (buildings.md). */
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

function row(page: Page, profile: string) {
  return page
    .getByTestId("cut-list-panel")
    .locator(
      `[data-testid="cut-list-row"][data-system="casework"][data-profile="${profile}"]`,
    );
}

async function expectLine(
  page: Page,
  profile: string,
  qty: string,
  stock: string,
): Promise<void> {
  const found = row(page, profile);
  await expect(found).toHaveCount(1, { timeout: 90_000 });
  await expect(found.getByTestId("cut-list-qty")).toHaveText(qty);
  await expect(found.getByTestId("cut-list-stock")).toHaveText(stock);
}

async function shoot(page: Page, name: string): Promise<void> {
  await page.mouse.move(800, 990);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/casework-b10-${name}.png` });
}

async function submit(page: Page): Promise<void> {
  await page.getByTestId("plugin-submit").click();
  await expect(page.getByTestId("plugin-editor")).toBeHidden({
    timeout: 90_000,
  });
}

test.describe("Casework on B10 — C4's vanity on P1", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a V3021 and a VDB1521 stand on P1's gypsum and price their plywood drawer boxes", async ({
    page,
  }) => {
    test.setTimeout(480_000);
    const account = await seedSession(page);
    const headers = { Authorization: `Bearer ${account.token}` };
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B10 bath vanity", length_unit: "in" },
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
    await createFeature(page, account.token, partId, {
      name: "Interior wall 1",
      feature: custom("loft.interior_wall", "1.0.0", {
        host_wall: ref(walls.feature.id),
      }),
      expected_tree_version: walls.tree_version,
    });

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(4);
    await expectSolved(page);

    // Build ▾ > Cabinets on Partition 1's left (+X) face, 1/2 in from its
    // back end: V3021, then a VDB1521 copied from it.
    await openBuildTool(page, "loft.cabinets", "Cabinets");
    await page
      .getByTestId("plugin-input-wall")
      .selectOption({ label: "Interior wall 1" });
    const pick = page.getByTestId("plugin-input-wall_segment");
    await expect(pick).toContainText("Partition 1");
    await pick
      .getByRole("button", { name: "Partition 1", exact: true })
      .click();
    await page.getByTestId("plugin-input-face-left").click();
    await page.getByTestId("plugin-input-offset_mm").fill("0.5");
    await page.getByTestId("plugin-input-carcass").selectOption("melamine");
    await page.getByTestId("plugin-input-boxes-0-type").selectOption("vanity");
    await page.getByTestId("plugin-input-boxes-0-width_mm").fill("30");
    await page.getByTestId("plugin-input-boxes-0-shelves").fill("0");
    await page.getByTestId("plugin-input-boxes-add").click();
    await page.getByTestId("plugin-input-boxes-1-width_mm").fill("15");
    await page
      .getByTestId("plugin-input-boxes-1-fronts")
      .selectOption("drawers");
    await shoot(page, "c4-form");
    await submit(page);
    await expect(rows).toHaveCount(5);
    await expectSolved(page);
    // From the top: the vanity in the bath, on P1's +X face behind P2.
    await page.getByTestId("view-top").click();
    await shoot(page, "c4");

    await openCutList(page);
    await expectLine(page, "3/4 melamine", "20", "2 × 4x8");
    await expectLine(page, "1/2 plywood", "12", "1 × 4x8");
    await expectLine(page, "1/4 plywood", "3", "1 × 4x8");
    await expectLine(page, "Edge banding 7/8 in", "14", "49 ft");
    await expect(
      row(page, "Edge banding 7/8 in").getByTestId("cut-list-length"),
    ).toContainText("578.75");
    await expectLine(page, "Concealed hinge", "4", "Each");
    await expectLine(page, "Drawer slides 20 in, pair", "3", "Each");

    // Each casework blank opens the book on its line: the plywood too.
    const dialog = page.getByTestId("price-book-dialog");
    const prices = [
      ["3/4 melamine", "melamine_3_4", "42.98", "$85.96"],
      ["1/2 plywood", "plywood_1_2", "54.98", "$54.98"],
      ["1/4 plywood", "plywood_1_4", "26.98", "$26.98"],
      ["Edge banding 7/8 in", "edge_banding", "0.35", "$17.15"],
      ["Concealed hinge", "hinge", "4.50", "$18.00"],
      ["Drawer slides 20 in, pair", "slide_20", "12.99", "$38.97"],
    ] as const;
    for (const [profile, key, price] of prices) {
      await row(page, profile).getByTestId("cut-list-price-blank").click();
      await expect(dialog).toBeVisible();
      const entry = dialog.locator(
        `[data-testid="price-book-row"][data-profile="${key}"]`,
      );
      await expect(entry).toHaveCount(1);
      const field = entry.getByTestId("price-book-price");
      await expect(field).toBeFocused();
      await field.fill(price);
      await field.press("Enter");
      await expect(dialog).toBeHidden({ timeout: 30_000 });
    }
    for (const [profile, , , extended] of prices) {
      await expect(
        row(page, profile).getByTestId("cut-list-ext-price"),
      ).toHaveText(extended, { timeout: 30_000 });
    }
    // No casework line is left unpriced (the house's framing is not priced
    // here).
    await expect(
      page.locator(
        '[data-testid="cut-list-row"][data-system="casework"] [data-testid="cut-list-price-blank"]',
      ),
    ).toHaveCount(0);
    await row(page, "3/4 melamine").scrollIntoViewIfNeeded();
    await shoot(page, "c4-priced");

    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers,
    });
    const stored = (
      (await tree.json()) as {
        features: {
          feature: {
            params: {
              plugin_id?: string;
              plugin_version?: string;
              inputs?: Record<string, unknown>;
            };
          };
        }[];
      }
    ).features.find((f) => f.feature.params.plugin_id === "loft.cabinets");
    expect(stored?.feature.params.plugin_version).toBe("1.1.0");
    expect(stored?.feature.params.inputs?.wall_segment).toEqual(["e5"]);
    expect(stored?.feature.params.inputs?.face).toBe("left");

    // V3021 -> V3621: the VDB moves to Y 150..135, clear of P2's board.
    await page.getByTestId("feature-select-4").click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("Edit Cabinets");
    await page.getByTestId("plugin-input-boxes-0-width_mm").fill("36");
    await submit(page);
    await expectSolved(page);

    // A 21 in VDB would end at Y 129, through P2: refused on Distance,
    // naming it.
    await page.getByTestId("feature-select-4").click();
    await page.getByTestId("plugin-input-boxes-1-width_mm").fill("21");
    await page.getByTestId("plugin-submit").click();
    await expect(editor.getByRole("alert")).toContainText(
      "would pass partition e6, which meets this face 52.25 to 56.75 in",
      { timeout: 60_000 },
    );
    await page.getByTestId("plugin-input-offset_mm").scrollIntoViewIfNeeded();
    await shoot(page, "refused");
  });
});
