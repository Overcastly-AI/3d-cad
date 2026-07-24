import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Multi-sheet switcher (FINDINGS #18). The drawings API has always stored an
 * ordered LIST of sheets; this spec proves the UI that was missing — a switcher
 * that adds a sheet and moves between them, wired to the real
 * `createSheet`/`createView` routes (no mocks). Each sheet is independently
 * set-up-able; the first sheet composes the printable paper (v1 gateway
 * limitation), and a laid-out secondary sheet reports its honest managed state.
 */

/** Build a 40×25×10 plate via the real gateway (a body the views can project). */
async function createPlateViaApi(
  page: Page,
  token: string,
  name: string,
): Promise<{ id: string }> {
  const auth = { Authorization: `Bearer ${token}` };
  const part = await page.request.post("/api/v1/parts", {
    data: { name },
    headers: auth,
  });
  if (!part.ok()) {
    throw new Error(
      `create part failed: ${part.status()} ${await part.text()}`,
    );
  }
  const partId = ((await part.json()) as { id: string }).id;

  const sketch = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Sketch1",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          entities: [
            {
              id: "e1",
              kind: "line",
              start: { x: 0, y: 0 },
              end: { x: 40, y: 0 },
            },
            {
              id: "e2",
              kind: "line",
              start: { x: 40, y: 0 },
              end: { x: 40, y: 25 },
            },
            {
              id: "e3",
              kind: "line",
              start: { x: 40, y: 25 },
              end: { x: 0, y: 25 },
            },
            {
              id: "e4",
              kind: "line",
              start: { x: 0, y: 25 },
              end: { x: 0, y: 0 },
            },
          ],
          constraints: [],
        },
      },
      expected_tree_version: 0,
    },
    headers: auth,
  });
  if (!sketch.ok()) {
    throw new Error(`sketch failed: ${sketch.status()} ${await sketch.text()}`);
  }
  const sketchBody = (await sketch.json()) as {
    feature: { id: string };
    tree_version: number;
  };

  const extrude = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketchBody.feature.id },
          distance_mm: 10,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketchBody.tree_version,
    },
    headers: auth,
  });
  if (!extrude.ok()) {
    throw new Error(
      `extrude failed: ${extrude.status()} ${await extrude.text()}`,
    );
  }
  return { id: partId };
}

/** Open a fresh drawing on the empty bench and lay out the first sheet. */
async function seedLaidOutDrawing(page: Page, partId: string): Promise<void> {
  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill("Multi-sheet plate");
  await page.getByTestId("create-drawing-submit").click();
  const row = page.getByTestId("drawing-row").first();
  await expect(row).toBeVisible();
  await row.getByTestId("drawing-open").click();

  await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
  await page.getByTestId("drawing-part-select").selectOption(partId);
  await page.getByTestId("drawing-autolayout").click();
  await expect(page.getByTestId("drawing-sheet")).toBeVisible({
    timeout: 30_000,
  });
}

test.describe("drawings — multi-sheet switcher", () => {
  test("add a sheet, move between sheets, set each up", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPlateViaApi(page, account.token, "Sheet plate");
    await seedLaidOutDrawing(page, part.id);

    // The switcher appears with the first sheet, active.
    const tabs = page.getByTestId("sheet-tabs");
    await expect(tabs).toBeVisible();
    await expect(page.getByTestId("sheet-tab-0")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByTestId("sheet-tab-1")).toHaveCount(0);

    // Add a sheet — it appends and becomes active; the empty new sheet invites
    // its own setup (the layout flow targets THIS sheet via its id).
    await page.getByTestId("sheet-tab-add").click();
    await expect(page.getByTestId("sheet-tab-1")).toBeVisible();
    await expect(page.getByTestId("sheet-tab-1")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();

    // Founder frame — the two-sheet switcher, second sheet active (1440).
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.mouse.move(720, 500);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-sheet-switcher-1440.png`,
    });

    // Lay out the SECOND sheet (still the persisted part) — createView targets
    // sheet 2's id, so it lands there. A laid-out secondary sheet reports its
    // honest managed state (v1 composes the first sheet's paper).
    await page.getByTestId("drawing-part-select").selectOption(part.id);
    await page.getByTestId("drawing-autolayout").click();
    await expect(page.getByTestId("drawing-secondary-sheet")).toBeVisible({
      timeout: 30_000,
    });

    // Small-laptop frame (1280×800) — the switcher stays usable.
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.mouse.move(640, 400);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-sheet-switcher-1280.png`,
    });

    // Move back to the first sheet — its composed paper renders again.
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.getByTestId("sheet-tab-0").click();
    await expect(page.getByTestId("sheet-tab-0")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 30_000,
    });
  });
});
