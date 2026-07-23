import { copyFile, mkdir, readFile } from "node:fs/promises";

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

/** Build a 200×140×30 plate (no hole) via the real gateway — big enough that its
 * four standard views overflow A4's quadrant cells until 1:5, but fit A3 at 1:2. */
async function createBigPlateViaApi(
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
              end: { x: 200, y: 0 },
            },
            {
              id: "e2",
              kind: "line",
              start: { x: 200, y: 0 },
              end: { x: 200, y: 140 },
            },
            {
              id: "e3",
              kind: "line",
              start: { x: 200, y: 140 },
              end: { x: 0, y: 140 },
            },
            {
              id: "e4",
              kind: "line",
              start: { x: 0, y: 140 },
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
          distance_mm: 30,
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

test("choose A3 for a big part so auto-layout earns a larger scale", async ({
  page,
}) => {
  const account = await seedSession(page);
  const part = await createBigPlateViaApi(page, account.token, "Plate 200×140");

  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill("Big plate — A3");
  await page.getByTestId("create-drawing-submit").click();
  const row = page.getByTestId("drawing-row").first();
  await expect(row).toBeVisible();
  await row.getByTestId("drawing-open").click();

  // Pick the part and the LARGER A3 sheet.
  await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
  await page.getByTestId("drawing-part-select").selectOption(part.id);
  const sizeSelect = page.getByTestId("drawing-size-select");
  await sizeSelect.selectOption("A3");
  await expect(sizeSelect).toHaveValue("A3");

  // Founder frame — the pre-layout command band with the new sheet-SIZE picker.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.mouse.move(720, 500);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-size-picker-1440.png`,
  });

  // Lay out onto the chosen A3 sheet.
  await page.getByTestId("drawing-autolayout").click();

  const sheet = page.getByTestId("drawing-sheet");
  await expect(sheet).toBeVisible({ timeout: 30_000 });

  // The sheet renders at the CHOSEN A3 size (read back from the persisted sheet)
  // and — because A3 is bigger — auto-fit lands the four views at 1:2, a far
  // larger scale than the 1:5 this same part would get on A4 (unit-tested). The
  // A3 sheet is 420 mm wide vs A4's 297; the composed <svg> viewBox proves it.
  await expect(page.getByTestId("drawing-size-readout")).toHaveText("A3");
  await expect(page.getByTestId("drawing-scale-readout")).toHaveText("1:2");
  await expect(sheet).toHaveAttribute("viewBox", "0 0 420 297");

  // All four standard views still land, each with projected edges.
  await expect(page.getByTestId("drawing-view")).toHaveCount(4);

  // Founder frame — the A3 layout at a usable scale, desktop width.
  await page.mouse.move(720, 500);
  await expect(sheet).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-sheet-size-a3-1440.png`,
  });
});

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

/** The tallest vertical line pick-target in a view, by bbox height. */
async function tallestVerticalEdge(page: Page, view: string) {
  const edges = page.locator(
    `[data-testid="drawing-pick-edge"][data-view="${view}"][data-primitive="line"]`,
  );
  const count = await edges.count();
  let best = 0;
  let bestHeight = 0;
  for (let i = 0; i < count; i += 1) {
    const box = await edges.nth(i).boundingBox();
    if (!box) continue;
    if (box.height > box.width && box.height > bestHeight) {
      bestHeight = box.height;
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

test("author an angular dimension between two perpendicular edges", async ({
  page,
}) => {
  const account = await seedSession(page);
  await layOutPlateDrawing(page, account.token);

  // Pick the 40 mm bottom edge in the top view, then choose "Angle" — this ARMS
  // a second-edge pick rather than authoring (the staged two-edge flow).
  const horizontal = await longestHorizontalEdge(page, "top");
  await horizontal.click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-start_angular").click();

  // The menu closes and a hint invites the second edge; the sheet stays live.
  await expect(page.getByTestId("dimension-pick-hint")).toBeVisible();

  // Pick a perpendicular (vertical, 25 mm) edge → the gated menu now offers the
  // angular type; author it.
  const vertical = await tallestVerticalEdge(page, "top");
  await vertical.click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-angular").click();

  // The re-evaluate measures the true 3D angle (a rectangle corner ⇒ 90.0°) and
  // stamps the degree value on the sheet as an arc annotation.
  await expect(
    page.locator(
      '[data-testid="drawing-dimension"][data-dimension-type="angular"][data-dimension-value="90.0°"]',
    ),
  ).toHaveCount(1, { timeout: 30_000 });
  await expect(
    page.locator(
      '[data-testid="dimension-row"][data-dimension-type="angular"]',
    ),
  ).toHaveCount(1);

  // Founder frame — a sheet carrying an angular dimension.
  const sheet = page.getByTestId("drawing-sheet");
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(sheet).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-angular-1440.png`,
  });
});

test("author a point-to-point linear between two picked vertices", async ({
  page,
}) => {
  const account = await seedSession(page);
  await layOutPlateDrawing(page, account.token);

  // Two vertex handles on straight edges in the top view — the point-to-point
  // pick names a model vertex THROUGH its edge + a canonical endpoint.
  const vertices = page.locator(
    '[data-testid="drawing-pick-vertex"][data-view="top"]',
  );
  await expect(vertices.first()).toBeAttached();

  // First vertex → the "pick the second point" hint (no menu, sheet stays live).
  await vertices.nth(0).click({ force: true });
  await expect(page.getByTestId("dimension-pick-hint")).toBeVisible();

  // A DISTINCT second vertex → the gated menu offers point-to-point; author it.
  await vertices.nth(2).click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-point_to_point").click();

  // The re-evaluate measures the model-true distance between the two vertices
  // and stamps it (a plain linear value, three decimals) on the sheet.
  const stamped = page.locator(
    '[data-testid="drawing-dimension"][data-dimension-type="linear"]',
  );
  await expect(stamped).toHaveCount(1, { timeout: 30_000 });
  await expect(stamped).toHaveAttribute("data-dimension-value", /^\d+\.\d{3}$/);
  await expect(
    page.locator('[data-testid="dimension-row"][data-dimension-type="linear"]'),
  ).toHaveCount(1);

  // Founder frame — a sheet carrying a point-to-point dimension.
  const sheet = page.getByTestId("drawing-sheet");
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(sheet).toBeVisible();
  await page.screenshot({ path: `${SCREENSHOT_DIR}/drawings-p2p-1440.png` });
});

/**
 * WB-64 — free-text note annotations, DOM sheet half. The export half draws
 * notes in the composed SVG/PDF/DXF; this drives the on-screen path end to end:
 * author a note via the Notes panel, then assert it renders on the DOM sheet as
 * a `drawing-note` at its authored sheet point (the same `ComposedSheet.notes`
 * the serializers read), and that deleting it removes it from the sheet.
 */
test("author a free-text note and see it on the sheet", async ({ page }) => {
  const account = await seedSession(page);
  await layOutPlateDrawing(page, account.token);

  // The Notes panel is a quiet precision instrument beside the Dimensions panel.
  const noteText = "MATERIAL 6061-T6 — BREAK SHARP EDGES";
  await page.getByTestId("note-input").fill(noteText);
  await page.getByTestId("note-add").click();

  // It lands in the panel list…
  const row = page.getByTestId("note-row");
  await expect(row).toHaveCount(1);
  await expect(row.getByTestId("note-row-text")).toHaveText(noteText);

  // …and the re-composed sheet draws it as a `drawing-note` at its authored
  // point (top-left, just inside the border: margin 10 + 6 = 16, 10 + 12 = 22).
  const note = page.locator('[data-testid="drawing-note"]');
  await expect(note).toHaveCount(1, { timeout: 30_000 });
  await expect(note).toHaveText(noteText);
  await expect(note).toHaveAttribute("x", "16");
  await expect(note).toHaveAttribute("y", "22");

  // Founder frame — a sheet carrying a visible note.
  const sheet = page.getByTestId("drawing-sheet");
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(sheet).toBeVisible();
  await page.screenshot({ path: `${SCREENSHOT_DIR}/drawings-note-1440.png` });

  // Delete it → it disappears from the sheet (and the panel).
  await row.getByTestId("note-delete").click();
  await expect(page.locator('[data-testid="drawing-note"]')).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("note-row")).toHaveCount(0);
});

/**
 * Drawings v1 #5 — SVG export. The shipped `DrawingSheet` renderer IS the
 * export: the laid-out sheet's `<svg>` (edges, dimensions, title block, inline
 * token colours) is serialized to a standalone, self-contained `.svg` and
 * handed to the browser as a download. This drives it end-to-end — lay out the
 * plate, author a Ø10 diameter, click Export SVG, catch the download, and
 * assert the file is a real standalone SVG carrying the sheet root, the hole's
 * circle, and the model-true dimension value.
 */
test("export the laid-out sheet as a standalone .svg", async ({ page }) => {
  const account = await seedSession(page);
  await layOutPlateDrawing(page, account.token);

  // Pre-layout the export is enabled once views exist; author a dimension so
  // the file carries a value stamp too.
  const exportButton = page.getByTestId("drawing-export-svg");
  await expect(exportButton).toBeEnabled();

  const topCircle = page
    .locator(
      '[data-testid="drawing-pick-edge"][data-view="top"][data-primitive="circle"]',
    )
    .first();
  await topCircle.click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-diameter").click();
  await expect(
    page.locator(
      '[data-testid="drawing-dimension"][data-dimension-value="Ø10.000"]',
    ),
  ).toHaveCount(1, { timeout: 30_000 });

  // Click Export SVG and catch the download the anchor fires.
  const downloadPromise = page.waitForEvent("download");
  await exportButton.click();
  const download = await downloadPromise;

  // Filename is the sanitized drawing name ("Plate — dimensions"), .svg.
  expect(download.suggestedFilename()).toBe("plate-dimensions.svg");

  const path = await download.path();
  const svg = await readFile(path, "utf-8");

  // Standalone + self-contained: XML prolog, the SVG namespace, the sheet root.
  expect(svg.startsWith("<?xml")).toBe(true);
  expect(svg).toContain('xmlns="http://www.w3.org/2000/svg"');
  expect(svg).toContain('data-testid="drawing-sheet"');
  // The hole projects to a real circle, and the authored diameter is stamped.
  expect(svg).toContain("<circle");
  expect(svg).toContain("10.000");
  // The screen-only Tailwind sizing classes are stripped; a concrete mm size
  // is written so the file opens/prints scale-correct.
  expect(svg).toContain('width="297mm"');
  expect(svg).toContain('height="210mm"');
});

/**
 * DE-2 — server-composed PDF export, the shop deliverable. Unlike Export SVG
 * (which serializes the on-screen `<svg>`), Export PDF POSTs the gateway export
 * route; the gateway server-composes the sheet from the SAME persisted placement
 * (byte-deterministic) and streams the PDF bytes back. This drives it end to end
 * against the real stack — lay out the plate, author a Ø10 diameter, click
 * Export PDF, catch the download, and assert it is a real, non-trivial `.pdf`
 * (magic `%PDF-` prefix). Saves the artifact so the founder can open it.
 */
test("export the laid-out sheet as a server-composed .pdf", async ({
  page,
}, testInfo) => {
  const account = await seedSession(page);
  await layOutPlateDrawing(page, account.token);

  // Disabled before there is anything to export is covered by the Export-SVG
  // spec's shared gate; here the sheet already has views, so PDF is enabled.
  const exportButton = page.getByTestId("drawing-export-pdf");
  await expect(exportButton).toBeEnabled();

  // Author a Ø10 diameter so the composed PDF carries a real dimension stamp.
  const topCircle = page
    .locator(
      '[data-testid="drawing-pick-edge"][data-view="top"][data-primitive="circle"]',
    )
    .first();
  await topCircle.click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-diameter").click();
  await expect(
    page.locator(
      '[data-testid="drawing-dimension"][data-dimension-value="Ø10.000"]',
    ),
  ).toHaveCount(1, { timeout: 30_000 });

  // Founder frame — the drawing sheet with the Export PDF control visible.
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(exportButton).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-export-pdf-desktop.png`,
  });

  // Click Export PDF and catch the download the anchor fires.
  const downloadPromise = page.waitForEvent("download");
  await exportButton.click();
  const download = await downloadPromise;

  // Filename is the sanitized drawing name ("Plate — dimensions"), .pdf.
  expect(download.suggestedFilename()).toMatch(/\.pdf$/);

  const path = await download.path();
  const bytes = await readFile(path);
  // A real, non-trivial PDF: the `%PDF-` magic prefix and a meaningful size.
  expect(bytes.subarray(0, 5).toString("latin1")).toBe("%PDF-");
  expect(bytes.byteLength).toBeGreaterThan(1000);

  // Persist the artifact so the orchestrator/founder can open + verify it.
  await testInfo.attach("drawing-export.pdf", {
    path,
    contentType: "application/pdf",
  });
  await mkdir(SCREENSHOT_DIR, { recursive: true });
  await copyFile(path, `${SCREENSHOT_DIR}/drawing-export.pdf`);
});

/**
 * DE-3 — server-composed DXF export, the interchange deliverable that completes
 * the export loop (SVG / PDF / DXF). Like Export PDF, Export DXF POSTs the
 * gateway export route; the gateway server-composes the sheet from the SAME
 * persisted placement and streams the DXF bytes back (ezdxf R2000, reopens
 * `audit()`-clean, deterministic). This drives it end to end against the real
 * stack — lay out the plate, author a Ø10 diameter, click Export DXF, catch the
 * download, and assert it is a real `.dxf` carrying the DXF group-code signature.
 * Captures the founder frame showing all three Export controls side by side.
 */
test("export the laid-out sheet as a server-composed .dxf", async ({
  page,
}, testInfo) => {
  const account = await seedSession(page);
  await layOutPlateDrawing(page, account.token);

  // The sheet already has views, so DXF is enabled (its disabled-before-layout
  // state shares the Export-SVG spec's gate).
  const exportButton = page.getByTestId("drawing-export-dxf");
  await expect(exportButton).toBeEnabled();

  // Author a Ø10 diameter so the composed DXF carries a real dimension entity.
  const topCircle = page
    .locator(
      '[data-testid="drawing-pick-edge"][data-view="top"][data-primitive="circle"]',
    )
    .first();
  await topCircle.click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-diameter").click();
  await expect(
    page.locator(
      '[data-testid="drawing-dimension"][data-dimension-value="Ø10.000"]',
    ),
  ).toHaveCount(1, { timeout: 30_000 });

  // Founder frame — the drawing sheet with all three Export controls (SVG / PDF
  // / DXF) visible in the Export group.
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByTestId("drawing-export-svg")).toBeVisible();
  await expect(page.getByTestId("drawing-export-pdf")).toBeVisible();
  await expect(exportButton).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-export-dxf-desktop.png`,
  });

  // Click Export DXF and catch the download the anchor fires.
  const downloadPromise = page.waitForEvent("download");
  await exportButton.click();
  const download = await downloadPromise;

  // Filename is the sanitized drawing name ("Plate — dimensions"), .dxf.
  expect(download.suggestedFilename()).toMatch(/\.dxf$/);

  const path = await download.path();
  const bytes = await readFile(path);
  const text = bytes.toString("latin1");
  // A real DXF: the group-code signature (`0\nSECTION`) opens the file, and it
  // carries the ENTITIES section the sheet geometry lands in.
  expect(text).toContain("SECTION");
  expect(text).toContain("ENTITIES");
  expect(bytes.byteLength).toBeGreaterThan(200);

  // Persist the artifact so the orchestrator/founder can open + verify it.
  await testInfo.attach("drawing-export.dxf", {
    path,
    contentType: "image/vnd.dxf",
  });
  await mkdir(SCREENSHOT_DIR, { recursive: true });
  await copyFile(path, `${SCREENSHOT_DIR}/drawing-export.dxf`);
});
