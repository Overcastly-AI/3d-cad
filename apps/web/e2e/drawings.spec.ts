import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Drawings v1 #7 — the drawing canvas exit gate. Driven end to end through a
 * real browser against the real stack (gateway + documents + geometry, no
 * mocks): a plate-with-a-hole part is built once via the API, a drawing is
 * created through the register UI, and the standard four views (front / top /
 * right + iso, third-angle) are auto-laid-out onto an engineering sheet. The
 * projected edges arrive from `/geometry/drawing/evaluate` (exact HLR) and
 * render as scale-correct SVG — visible solid, hidden dashed. The gate asserts
 * the four view containers render with edges AND that the top view shows the
 * hole as a real circle. This is "a drawing on screen," the v1 founder payoff.
 */

/** Build a 40×25×10 plate with a Ø10 through hole via the real gateway. */
async function createPlateWithHoleViaApi(
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
            {
              id: "e5",
              kind: "circle",
              center: { x: 20, y: 12.5 },
              radius: 5,
              construction: false,
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

test("lay out the standard four views on a sheet", async ({ page }) => {
  const account = await seedSession(page);
  const part = await createPlateWithHoleViaApi(
    page,
    account.token,
    "Plate 40×25",
  );

  // Create the drawing through the register UI.
  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill("Plate — sheet 1");
  await page.getByTestId("create-drawing-submit").click();

  const row = page.getByTestId("drawing-row").first();
  await expect(row).toBeVisible();
  await row.getByTestId("drawing-open").click();

  // The editor opens on the empty bench; choose the part and lay out the views.
  await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
  await page.getByTestId("drawing-part-select").selectOption(part.id);
  await page.getByTestId("drawing-autolayout").click();

  // The sheet renders once the projection returns.
  const sheet = page.getByTestId("drawing-sheet");
  await expect(sheet).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("drawing-title-block")).toBeVisible();

  // All four standard views are placed, each carrying projected edges.
  const views = page.getByTestId("drawing-view");
  await expect(views).toHaveCount(4);
  for (const projection of ["front", "top", "right", "iso"]) {
    const view = page.locator(
      `[data-testid="drawing-view"][data-view="${projection}"]`,
    );
    await expect(view).toHaveAttribute("data-view-error", "false");
    // SVG geometry sub-elements report "hidden" to Playwright's visibility
    // heuristic (zero-area boxes); assert the edges are drawn by count instead.
    expect(
      await view.locator("line, circle, polyline").count(),
    ).toBeGreaterThan(0);
  }

  // The hole projects to a real circle in the top view (looking down the axis).
  const topView = page.locator('[data-testid="drawing-view"][data-view="top"]');
  expect(await topView.locator("circle").count()).toBeGreaterThan(0);

  // Founder frames — desktop + small-laptop widths.
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(sheet).toBeVisible();
  await page.screenshot({ path: `${SCREENSHOT_DIR}/drawings-editor-1440.png` });
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(sheet).toBeVisible();
  await page.screenshot({ path: `${SCREENSHOT_DIR}/drawings-editor-1280.png` });
});

/** Lay out the standard views for a fresh plate-with-hole drawing. */
async function layOutPlateDrawing(page: Page, token: string): Promise<string> {
  const part = await createPlateWithHoleViaApi(page, token, "Plate 40×25");
  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill("Plate — dimensions");
  await page.getByTestId("create-drawing-submit").click();
  const row = page.getByTestId("drawing-row").first();
  await expect(row).toBeVisible();
  await row.getByTestId("drawing-open").click();
  await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
  await page.getByTestId("drawing-part-select").selectOption(part.id);
  await page.getByTestId("drawing-autolayout").click();
  await expect(page.getByTestId("drawing-sheet")).toBeVisible({
    timeout: 30_000,
  });
  return part.id;
}

/** The longest horizontal (≈ 40 mm) line pick-target in a view, by bbox width. */
async function longestHorizontalEdge(page: Page, view: string) {
  const edges = page.locator(
    `[data-testid="drawing-pick-edge"][data-view="${view}"][data-primitive="line"]`,
  );
  const count = await edges.count();
  let best = 0;
  let bestWidth = 0;
  for (let i = 0; i < count; i += 1) {
    const box = await edges.nth(i).boundingBox();
    if (!box) continue;
    if (box.width > box.height && box.width > bestWidth) {
      bestWidth = box.width;
      best = i;
    }
  }
  return edges.nth(best);
}

test("author a diameter on the hole and a linear on the 40 mm edge", async ({
  page,
}) => {
  const account = await seedSession(page);
  await layOutPlateDrawing(page, account.token);

  // --- Diameter: pick the hole's circle in the top view, author Ø. ---------
  const topCircle = page
    .locator(
      '[data-testid="drawing-pick-edge"][data-view="top"][data-primitive="circle"]',
    )
    .first();
  await topCircle.click({ force: true });

  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-diameter").click();

  // The re-evaluate measures it off the model and stamps Ø10.000 on the sheet.
  await expect(
    page.locator(
      '[data-testid="drawing-dimension"][data-dimension-value="Ø10.000"]',
    ),
  ).toHaveCount(1, { timeout: 30_000 });
  // And it appears in the Dimensions panel with the same model-true value.
  await expect(
    page.locator(
      '[data-testid="dimension-row"][data-dimension-type="diameter"]',
    ),
  ).toHaveCount(1);

  // --- Linear: pick a 40 mm edge in the top view, author the length. -------
  const longEdge = await longestHorizontalEdge(page, "top");
  await longEdge.click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-linear").click();

  await expect(
    page.locator(
      '[data-testid="drawing-dimension"][data-dimension-value="40.000"]',
    ),
  ).toHaveCount(1, { timeout: 30_000 });

  // Founder frames — a dimensioned sheet, desktop + small-laptop widths.
  const sheet = page.getByTestId("drawing-sheet");
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(sheet).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-dimensioned-1440.png`,
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(sheet).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-dimensioned-1280.png`,
  });

  // --- Manage: delete the linear dimension, it disappears from the sheet. --
  const linearRow = page.locator(
    '[data-testid="dimension-row"][data-dimension-type="linear"]',
  );
  await linearRow.getByTestId("dimension-delete").click();
  await expect(
    page.locator(
      '[data-testid="drawing-dimension"][data-dimension-value="40.000"]',
    ),
  ).toHaveCount(0, { timeout: 30_000 });
});
