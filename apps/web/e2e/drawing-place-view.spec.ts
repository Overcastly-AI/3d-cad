import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Multi-sheet drawings — the FRONTEND follow-up (B). Two things the switcher
 * did not yet do, proven against the real gateway (no mocks):
 *
 *  (a) compose/export follow the ACTIVE sheet — switching to sheet 2 renders
 *      sheet 2's OWN content, not sheet 1's (proven with a per-sheet note that
 *      only that sheet's compose carries);
 *  (b) drag-to-place authors a view's position — the dragged centre persists
 *      across a reload and the view lands where it was dropped, not back at its
 *      auto-layout anchor.
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

/** Open a fresh drawing on the empty bench and lay out its first sheet. */
async function seedLaidOutDrawing(
  page: Page,
  partId: string,
  name: string,
): Promise<void> {
  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill(name);
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

/** Add a free-text note through the Notes panel and wait for it on the sheet. */
async function addNote(page: Page, text: string): Promise<void> {
  await page.getByTestId("note-input").fill(text);
  await page.getByTestId("note-add").click();
  await expect(page.getByTestId("drawing-note")).toHaveText(text, {
    timeout: 30_000,
  });
}

test.describe("drawings — active-sheet compose", () => {
  test("switching sheets composes the ACTIVE sheet's content", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPlateViaApi(page, account.token, "Active plate");
    await seedLaidOutDrawing(page, part.id, "Active-sheet plate");

    // Sheet 1 carries its own note.
    await addNote(page, "SHEET ONE");

    // Add + lay out sheet 2, then give it a DIFFERENT note.
    await page.getByTestId("sheet-tab-add").click();
    await expect(page.getByTestId("sheet-tab-1")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
    await page.getByTestId("drawing-part-select").selectOption(part.id);
    await page.getByTestId("drawing-autolayout").click();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 30_000,
    });
    await addNote(page, "SHEET TWO");

    // The composed paper for the ACTIVE sheet (2) shows ONLY sheet 2's note.
    await expect(page.getByTestId("drawing-note")).toHaveText("SHEET TWO");

    // Founder frame — the active (second) sheet's composed paper.
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.mouse.move(720, 500);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-active-sheet-compose-1440.png`,
    });

    // Switch back to sheet 1 — its OWN note composes again.
    await page.getByTestId("sheet-tab-0").click();
    await expect(page.getByTestId("sheet-tab-0")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("drawing-note")).toHaveText("SHEET ONE");
  });
});

test.describe("drawings — drag-to-place", () => {
  test("drag a view; the authored position survives reload", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const account = await seedSession(page);
    const part = await createPlateViaApi(page, account.token, "Drag plate");
    await seedLaidOutDrawing(page, part.id, "Drag-to-place plate");

    const front = page.locator(
      '[data-testid="drawing-view"][data-view="front"]',
    );
    await expect(front).toBeVisible();
    await expect(front).toHaveAttribute("data-placed", "false");

    // Founder BEFORE frame — the auto-laid-out sheet.
    await page.mouse.move(720, 500);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-place-view-before-1440.png`,
    });

    const before = await front.boundingBox();
    if (!before) throw new Error("front view has no box");

    // Reveal the grip (hover the view), then drag it by a known screen delta.
    await front.hover();
    const grip = front.getByTestId("drawing-view-grip");
    const gripBox = await grip.boundingBox();
    if (!gripBox) throw new Error("grip has no box");
    const gx = gripBox.x + gripBox.width / 2;
    const gy = gripBox.y + gripBox.height / 2;
    const dx = 90;
    const dy = 70;
    await page.mouse.move(gx, gy);
    await page.mouse.down();
    await page.mouse.move(gx + dx / 2, gy + dy / 2, { steps: 4 });
    await page.mouse.move(gx + dx, gy + dy, { steps: 4 });
    await page.mouse.up();

    // The view is now manually placed, and it moved on screen by ~the drag delta.
    await expect(front).toHaveAttribute("data-placed", "true", {
      timeout: 30_000,
    });
    const after = await front.boundingBox();
    if (!after) throw new Error("front view has no box after drag");
    expect(Math.abs(after.x - (before.x + dx))).toBeLessThan(25);
    expect(Math.abs(after.y - (before.y + dy))).toBeLessThan(25);

    // The reset-to-auto affordance is now offered (hover keeps the frame up).
    await front.hover();
    await expect(front.getByTestId("drawing-view-reset")).toBeVisible();

    // Founder AFTER frame — the dragged view at its authored spot, reset offered.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-place-view-after-1440.png`,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
    await front.hover();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-place-view-after-1280.png`,
    });
    await page.setViewportSize({ width: 1440, height: 900 });

    // Reload: the authored placement persists (read from the stored view), and
    // the view lands where it was dropped — not back at its auto-layout anchor.
    await page.reload();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 30_000,
    });
    const reloaded = page.locator(
      '[data-testid="drawing-view"][data-view="front"]',
    );
    await expect(reloaded).toHaveAttribute("data-placed", "true");
    const persisted = await reloaded.boundingBox();
    if (!persisted) throw new Error("front view has no box after reload");
    expect(Math.abs(persisted.x - after.x)).toBeLessThan(25);
    expect(Math.abs(persisted.y - after.y)).toBeLessThan(25);
  });
});
