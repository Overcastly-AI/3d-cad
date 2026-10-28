import { expectSolved, openBuildTool, openCutList } from "./buildFlow";
import { expect, type Page, test } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * SLAB: B8 (docs/reference-parts/buildings.md) in the real app, as Chief
 * Architect and Revit build a slab on grade from the exterior wall loop.
 * Build ▾ > Slab picks B7's outline sketch (4 in, a 12 in thickened edge 12
 * deep, 5% concrete waste by default); the walls pick the same outline and
 * stand On floor = the slab, at its top, Z 0; the door cuts the front wall's
 * bottom plate in two.
 *
 * The cut list leads with Foundation: the slab's 308 736 in³ as 6.62 yd³,
 * ordered 7.00 yd³ (6.95 with the allowance, rounded up to 1/4); 2 #4 loops
 * of 912 in in 10 sticks; 19 anchor bolts (3 + 3 on the front's two pieces,
 * 5 on the back, 4 on each side). Pricing the pour from its blank, at $165
 * a yard, extends to $1,155.00. Golden `b8-slab-house` pins the geometry.
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

/** A choice input: a segmented control for a few short options, else a select. */
async function choose(page: Page, input: string, value: string): Promise<void> {
  const segment = page.getByTestId(`plugin-input-${input}-${value}`);
  if ((await segment.count()) > 0) await segment.click();
  else await page.getByTestId(`plugin-input-${input}`).selectOption(value);
}

/** The Foundation group's rows: member, qty, length, stock. */
const FOUNDATION: [string, string, string, string][] = [
  ["Slab", "1", "6.62 yd³", "7.00 yd³"],
  ["Rebar", "2", "912", "10 × 20 ft"],
  ["Anchor bolt", "19", "—", "Each"],
];

test.describe("Slab — B8 on its slab", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a slab on the outline lists its concrete, rebar and bolts, and the walls stand on it", async ({
    page,
  }) => {
    test.setTimeout(360_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B8 on a slab", length_unit: "in" },
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

    // Build ▾ > Slab on the outline, every default kept.
    await openBuildTool(page, "loft.slab", "Slab");
    await page.getByTestId("plugin-input-outline").selectOption(sketchId);
    await expect(page.getByTestId("plugin-input-width_mm")).toHaveCount(0);
    await expect(page.getByTestId("plugin-input-waste_percent")).toHaveValue(
      "5",
    );
    await expect(page.getByTestId("plugin-input-edge_width_mm")).toBeVisible();
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/slab-form.png` });
    await submit(page);
    await expect(rows).toHaveCount(2);
    await expectSolved(page);

    // Walls on the outline, On floor = the slab: no base elevation to type.
    const wallTool = page.getByTestId("plugin-tool-loft.wall");
    await expect(wallTool).toBeEnabled({ timeout: 30_000 });
    await wallTool.click();
    await expect(page.getByTestId("plugin-editor")).toContainText("New Wall");
    await page.getByTestId("plugin-input-outline").selectOption(sketchId);
    await page
      .getByTestId("plugin-input-floor")
      .selectOption({ label: "Slab 1" });
    await expect(page.getByTestId("plugin-input-elevation_mm")).toHaveCount(0);
    await choose(page, "stud_profile", "us_2x6");
    await submit(page);
    await expect(rows).toHaveCount(3);
    await expectSolved(page);

    // The front door, 144 from the end nearer the origin: X 125..163.
    await openBuildTool(page, "loft.door", "Door");
    await page.getByRole("button", { name: "Front wall" }).click();
    await page.getByTestId("plugin-input-offset_mm").fill("144");
    await page.getByTestId("plugin-input-draw_unit").selectOption("none");
    await submit(page);
    await expect(rows).toHaveCount(4);
    await expectSolved(page);

    await openCutList(page);
    const panel = page.getByTestId("cut-list-panel");
    const foundation = panel.locator(
      '[data-testid="cut-list-row"][data-system="foundation"]',
    );
    await expect(foundation).toHaveCount(3, { timeout: 90_000 });
    for (const [index, [member, qty, length, stock]] of FOUNDATION.entries()) {
      const row = foundation.nth(index);
      await expect(row.getByTestId("cut-list-member")).toHaveText(member);
      await expect(row.getByTestId("cut-list-qty")).toHaveText(qty);
      await expect(row.getByTestId("cut-list-length")).toHaveText(length);
      await expect(row.getByTestId("cut-list-stock")).toHaveText(stock);
    }
    // The front wall's bottom plate is two pieces of 125, bolted 3 each.
    const plates = panel.locator(
      '[data-testid="cut-list-row"][data-member="Bottom plate"]',
    );
    await expect(plates.first().getByTestId("cut-list-length")).toHaveText(
      "125",
    );
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/slab-cut-list.png` });

    // Price the pour from its blank: per cubic yard, on the 7 ordered.
    const slab = foundation.first();
    await slab.getByTestId("cut-list-price-blank").click();
    const dialog = page.getByTestId("price-book-dialog");
    const seeded = dialog.getByTestId("price-book-row").last();
    await expect(seeded).toHaveAttribute("data-profile", "ready_mix");
    await expect(seeded.getByTestId("price-book-unit-item")).toHaveText(
      "Per yd³",
    );
    await seeded.getByTestId("price-book-price").fill("165");
    await page.screenshot({ path: `${SCREENSHOT_DIR}/slab-price-book.png` });
    await dialog.getByTestId("price-book-save").click();
    await expect(dialog).toBeHidden();
    await expect(slab.getByTestId("cut-list-unit-price")).toHaveText(
      "$165.00",
      {
        timeout: 60_000,
      },
    );
    await expect(slab.getByTestId("cut-list-ext-price")).toHaveText(
      "$1,155.00",
    );
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/slab-priced.png` });

    // The slab is stored at 1.0.0 with its allowance; the walls at 1.4.0.
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
    expect(features[1]?.feature.params.plugin_version).toBe("1.0.0");
    expect(features[1]?.feature.params.inputs?.waste_percent).toBe(5);
    expect(features[2]?.feature.params.plugin_version).toBe("1.4.0");
  });
});
