import { expectSolved, openBuildTool, openCutList } from "./buildFlow";
import { expect, test, type Page } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * OPENING-UNITS (docs/BACKLOG.md): a window is picked by its call size, as
 * Chief Architect's and Revit's window families are typed. On B7's front
 * wall a 2030 picked from the generic form's Size select frames its 24.5 x
 * 36.5 rough opening with no size typed, draws its unit (a frame and a
 * pane), and the cut list lists the unit once, as one Each line priced from
 * the book's `window_2030` entry.
 *
 * The UI half: the form hides the Custom size while a code is picked, the
 * cut list reads a 3040's stock as "3040 window", and its blank price opens
 * the price book on a `window_3040` row, so typing 189 and Enter prices the
 * line and the Total. Screenshots: `opening-units-*.png`.
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

interface Stored {
  id: string;
  name: string;
  feature: {
    params: {
      inputs?: Record<string, unknown>;
      expansion?: {
        role: string;
        name: string | null;
        metadata?: { profile?: string; material?: string } | null;
        feature: {
          type: string;
          params: { entities?: { start: { x: number } }[] };
        };
      }[];
    };
  };
}

async function tree(page: Page, token: string, partId: string) {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { features: Stored[] }).features;
}

/** The window's rough opening (in): its sill's ends along X, from the
 * wall's framing. */
async function roughOpening(page: Page, token: string, partId: string) {
  const features = await tree(page, token, partId);
  const window = features.find((f) => f.name.startsWith("Window"));
  const walls = features.find((f) => f.name.startsWith("Walls"));
  const sill = walls?.feature.params.expansion?.find(
    (m) =>
      m.role === "section" &&
      (m.name ?? "").includes(`sill/opening/${window?.id ?? "-"}/`),
  );
  const xs = (sill?.feature.params.entities ?? []).map((e) => e.start.x / IN);
  expect(xs.length).toBe(4);
  return [Math.min(...xs), Math.max(...xs)];
}

/** A new in part with B7's outline and its 2x6 walls, open and solved. */
async function seedWalls(page: Page) {
  const account = await seedSession(page);
  const auth = { Authorization: `Bearer ${account.token}` };
  const created = await page.request.post("/api/v1/parts", {
    data: { name: "B7 front wall units", length_unit: "in" },
    headers: auth,
  });
  expect(created.ok(), await created.text()).toBe(true);
  const partId = ((await created.json()) as { id: string }).id;
  const sketch = await createFeature(page, account.token, partId, {
    name: "Outline",
    feature: { type: "sketch", version: 1, params: OUTLINE },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, partId, {
    name: "Walls",
    feature: {
      type: "custom",
      version: 1,
      params: {
        plugin_id: "loft.wall",
        plugin_version: "1.3.0",
        inputs: {
          outline: { kind: "feature", feature_id: sketch.feature.id },
          stud_profile: "us_2x6",
        },
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("feature-row")).toHaveCount(2);
  await expectSolved(page);
  return { account, partId };
}

/** The typed size 1.3.0 reads only when Size is Custom. */
const CUSTOM_FIELDS = [
  "width_mm",
  "height_mm",
  "ro_width_allowance_mm",
  "ro_height_allowance_mm",
];

test.describe("Window and door units picked by size", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a 3040 hides the Custom size, lists one unit line and is priced from its blank", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const { account, partId } = await seedWalls(page);

    // A new window on the front wall: Size proposes a 3040, and the typed
    // Custom size is hidden until Custom is chosen.
    await openBuildTool(page, "loft.window", "Window");
    await expect(page.getByTestId("plugin-input-host_wall")).toHaveValue(/.+/);
    await page
      .getByTestId("plugin-input-wall_segment")
      .getByRole("button", { name: "Front", exact: true })
      .click();
    const size = page.getByTestId("plugin-input-size");
    await expect(size).toHaveValue("window_3040");
    for (const name of CUSTOM_FIELDS) {
      await expect(page.getByTestId(`plugin-input-${name}`)).toHaveCount(0);
    }
    await size.selectOption("custom");
    for (const name of CUSTOM_FIELDS) {
      await expect(page.getByTestId(`plugin-input-${name}`)).toBeVisible();
    }
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/opening-units-form-custom.png`,
    });
    await size.selectOption({ label: `3040 (3'0" x 4'0")` });
    for (const name of CUSTOM_FIELDS) {
      await expect(page.getByTestId(`plugin-input-${name}`)).toHaveCount(0);
    }
    await page.getByTestId("plugin-input-offset_mm").fill("60");
    const submit = page.getByTestId("plugin-submit");
    await expect(submit).not.toHaveAttribute("aria-disabled", "true", {
      timeout: 90_000,
    });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/opening-units-form-3040.png`,
    });
    await submit.click();
    await expect(page.getByTestId("plugin-editor")).toBeHidden({
      timeout: 60_000,
    });
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expectSolved(page);
    const window = (await tree(page, account.token, partId)).find((f) =>
      f.name.startsWith("Window"),
    );
    expect(window?.feature.params.inputs?.size).toBe("window_3040");

    // One Window line, its stock the size and kind, its price blank.
    await openCutList(page);
    const panel = page.getByTestId("cut-list-panel");
    const unit = panel.locator(
      '[data-testid="cut-list-row"][data-member="Window"]',
    );
    await expect(unit).toHaveCount(1, { timeout: 60_000 });
    await expect(unit).toHaveAttribute("data-profile", "3040");
    await expect(unit.getByTestId("cut-list-qty")).toHaveText("1");
    await expect(unit.getByTestId("cut-list-stock")).toHaveText("3040 window");
    await expect(unit.getByTestId("cut-list-unit-price")).toHaveText("Price");
    const total = panel.getByTestId("cut-list-price-total");
    await expect(total).toHaveText("");
    await total.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/opening-units-cut-list-blank.png`,
    });

    // The blank opens the book on window_3040, Each, its price focused.
    await unit
      .getByRole("button", { name: "Price Window, 3040 window unit" })
      .click();
    const dialog = page.getByTestId("price-book-dialog");
    await expect(dialog).toBeVisible();
    const row = dialog.locator(
      '[data-testid="price-book-row"][data-profile="window_3040"]',
    );
    await expect(row).toHaveCount(1);
    await expect(row).toHaveAttribute("data-kind", "unit");
    await expect(row.getByTestId("price-book-material")).toHaveValue("pvc");
    await expect(row.getByTestId("price-book-stock-unit")).toHaveText("Unit");
    const price = row.getByTestId("price-book-price");
    await expect(price).toBeFocused();
    await price.fill("189");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/opening-units-price-book.png`,
    });
    await price.press("Enter");
    await expect(dialog).toBeHidden({ timeout: 30_000 });

    // The cut list re-prices without a reload: the unit and the Total.
    await expect(unit.getByTestId("cut-list-unit-price")).toHaveText(
      "$189.00",
      { timeout: 30_000 },
    );
    await expect(unit.getByTestId("cut-list-ext-price")).toHaveText("$189.00");
    await expect(total).toHaveText("$189.00");
    await total.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/opening-units-cut-list-priced.png`,
    });

    // Reopened from the button, the book lists the unit's row to edit.
    await panel.getByTestId("cut-list-price-book").click();
    const stored = dialog.locator(
      '[data-testid="price-book-row"][data-profile="window_3040"]',
    );
    await expect(stored.getByTestId("price-book-price")).toHaveValue("189.00");
    await stored.getByTestId("price-book-price").fill("204.50");
    await dialog.getByTestId("price-book-save").click();
    await expect(dialog).toBeHidden({ timeout: 30_000 });
    await expect(total).toHaveText("$204.50", { timeout: 30_000 });
  });

  test("a 2030 picked from the Size list frames its rough opening, draws its unit and prices as one line", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const { account, partId } = await seedWalls(page);
    const auth = { Authorization: `Bearer ${account.token}` };
    const rows = page.getByTestId("feature-row");

    // A new window on the front wall: Size proposes a 3040; pick 2030.
    await openBuildTool(page, "loft.window", "Window");
    await expect(page.getByTestId("plugin-input-host_wall")).toHaveValue(/.+/);
    await page
      .getByTestId("plugin-input-wall_segment")
      .getByRole("button", { name: "Front", exact: true })
      .click();
    const size = page.getByTestId("plugin-input-size");
    await expect(size).toHaveValue("window_3040");
    await size.selectOption({ label: `2030 (2'0" x 3'0")` });
    await expect(page.getByTestId("plugin-input-draw_unit")).toHaveValue(
      "draw",
    );
    await page.getByTestId("plugin-input-offset_mm").fill("60");
    const submit = page.getByTestId("plugin-submit");
    await expect(submit).not.toHaveAttribute("aria-disabled", "true", {
      timeout: 90_000,
    });
    await submit.click();
    await expect(page.getByTestId("plugin-editor")).toBeHidden({
      timeout: 60_000,
    });
    await expect(rows).toHaveCount(3);
    await expectSolved(page);

    // The 2030 frames 24.5 wide centred on X 60, and its unit is two bodies.
    const window = (await tree(page, account.token, partId)).find((f) =>
      f.name.startsWith("Window"),
    );
    expect(window?.feature.params.inputs?.size).toBe("window_2030");
    const [left, right] = await roughOpening(page, account.token, partId);
    expect(left).toBeCloseTo(60 - 12.25, 6);
    expect(right).toBeCloseTo(60 + 12.25, 6);
    const bodies = (window?.feature.params.expansion ?? [])
      .filter((m) => m.feature.type === "extrude")
      .map((m) => [m.role, m.metadata?.profile, m.metadata?.material]);
    expect(bodies).toEqual([
      ["frame", "2030", "pvc"],
      ["glazing", "2030", "glass"],
      // OPENING-UPDATE: the 2x6 wall's filled header (three plies) takes a
      // 1/2 plywood spacer in each of its two 1/2 in gaps.
      ["spacer", "1/2 plywood", "plywood"],
      ["spacer", "1/2 plywood", "plywood"],
    ]);

    // The book prices the unit by its key and frame material.
    const read = await page.request.get("/api/v1/price-book", {
      headers: auth,
    });
    const book = (await read.json()) as { version: number };
    const saved = await page.request.put("/api/v1/price-book", {
      headers: { ...auth, "If-Match": `"${book.version}"` },
      data: {
        currency: "USD",
        entries: [
          {
            material: "pvc",
            profile: "window_2030",
            unit: "each",
            stock_length_ft: null,
            sheet: null,
            price_cents: 18900,
          },
        ],
      },
    });
    expect(saved.status(), await saved.text()).toBe(200);

    // One Window line, 2030 x 1 at $189.00: the pane is part of it.
    await page.reload();
    await expectSolved(page);
    await openCutList(page);
    const panel = page.getByTestId("cut-list-panel");
    const unit = panel.locator(
      '[data-testid="cut-list-row"][data-member="Window"]',
    );
    await expect(unit).toHaveCount(1, { timeout: 60_000 });
    await expect(unit).toHaveAttribute("data-profile", "2030");
    await expect(unit.getByTestId("cut-list-qty")).toHaveText("1");
    await expect(unit.getByTestId("cut-list-unit-price")).toHaveText("$189.00");
    await expect(unit.getByTestId("cut-list-ext-price")).toHaveText("$189.00");
    await expect(
      panel.locator('[data-testid="cut-list-row"][data-member="Glazing"]'),
    ).toHaveCount(0);
    await expect(panel.getByTestId("cut-list-price-total")).toHaveText(
      "$189.00",
    );
  });
});
