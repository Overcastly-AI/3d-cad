import { expect, test, type Page } from "./fixtures";

import {
  SCREENSHOT_DIR,
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
} from "./support";

/**
 * Makeover Batch 2 — "every element earns its place" (UI-REVIEW 2026-07-16,
 * Track C). Three user-facing guarantees, driven against the REAL stack:
 *   1. a gated tool EXPLAINS itself — reachable by mouse AND keyboard, showing
 *      its reason (the aria-disabled fix; native `disabled` made it mute).
 *   2. an open command SCOPES the band — Fillet locks Extrude, so switching
 *      tools can never silently discard the open command's picks.
 *   3. double-Escape from a fresh sketch mints EXACTLY ONE feature — never the
 *      duplicate "Sketch1" the audit reproduced.
 */

/** A 10×20 rectangle fixed at the origin on XY — solves to clean corners. */
const RECTANGLE_10x20 = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 9.7, y: 0.4 } },
    {
      id: "e2",
      kind: "line",
      start: { x: 10, y: 0.2 },
      end: { x: 10.3, y: 19 },
    },
    {
      id: "e3",
      kind: "line",
      start: { x: 10.2, y: 20.4 },
      end: { x: -0.3, y: 19.7 },
    },
    {
      id: "e4",
      kind: "line",
      start: { x: 0.3, y: 19.5 },
      end: { x: -0.2, y: 0.5 },
    },
  ],
  constraints: [
    {
      kind: "coincident",
      a: { entity: "e1", point: "end" },
      b: { entity: "e2", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e2", point: "end" },
      b: { entity: "e3", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e3", point: "end" },
      b: { entity: "e4", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e4", point: "end" },
      b: { entity: "e1", point: "start" },
    },
    { kind: "horizontal", entity: "e1" },
    { kind: "vertical", entity: "e2" },
    { kind: "horizontal", entity: "e3" },
    { kind: "vertical", entity: "e4" },
    { kind: "distance", entity: "e1", value_mm: 10 },
    { kind: "distance", entity: "e2", value_mm: 20 },
    { kind: "fixed", point: { entity: "e1", point: "start" } },
  ],
};

async function createFeature(
  page: Page,
  token: string,
  partId: string,
  body: unknown,
): Promise<{ feature: { id: string }; tree_version: number }> {
  const response = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: body,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e create feature failed: ${response.status()} ${await response.text()}`,
    );
  }
  return (await response.json()) as {
    feature: { id: string };
    tree_version: number;
  };
}

/** Seed a part whose body is a 10×20×30 box (a solved sketch AND a solid). */
async function seedBoxPart(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Scoped box");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: RECTANGLE_10x20 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 30,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part;
}

/** The computed opacity of a ToolButton's tooltip (0 hidden, ~1 revealed). */
async function tooltipOpacity(page: Page, testId: string): Promise<number> {
  return page.getByTestId(testId).evaluate((btn) => {
    const tip = btn.querySelector(":scope > span:last-child");
    return tip ? Number(getComputedStyle(tip).opacity) : 0;
  });
}

test.describe("gated tools explain themselves", () => {
  test("disabled Extrude is reachable by mouse AND keyboard and shows its reason", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Empty part");
    await page.goto(`/parts/${part.id}`);

    const extrude = page.getByTestId("new-extrude");
    // No sketch yet → honestly disabled (aria-disabled, still in the a11y tree).
    await expect(extrude).toBeDisabled();
    await expect(extrude).toContainText("Solve a sketch first");

    // MOUSE: a native-disabled button is pointer-events:none — hovering it would
    // hit the element behind and time out. This hover SUCCEEDING proves the tool
    // is reachable, and the reason tooltip animates in.
    await extrude.hover();
    await expect
      .poll(() => tooltipOpacity(page, "new-extrude"), { timeout: 3_000 })
      .toBeGreaterThan(0.5);

    // KEYBOARD: a native-disabled button cannot receive focus. This focusing
    // proves the reason is reachable by keyboard too (the audit's P1 defect).
    await extrude.focus();
    await expect(extrude).toBeFocused();
  });
});

test.describe("an open command scopes the band", () => {
  test("Fillet locks Extrude with a reason; picks survive a stray Extrude click", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    // The body renders (10×20×30 = 6,000 mm³).
    await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
      timeout: 30_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);

    const extrude = page.getByTestId("new-extrude");
    const fillet = page.getByTestId("new-fillet");
    await expect(extrude).toBeEnabled();
    await expect(fillet).toBeEnabled();

    // Open the Fillet command and pick one edge (a live, unsaved selection).
    await fillet.click();
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await expect(page.getByTestId("create-strip")).toHaveAttribute(
      "data-command",
      "Fillet",
    );
    await page.getByTestId("fillet-mode-pick").click();
    await page.locator('[data-testid^="edge-pick-"]').first().click();
    await expect(page.getByTestId("selected-count")).toHaveText(
      "1 edge picked",
    );

    // The whole band is now scoped: Extrude is locked with an honest reason.
    await expect(extrude).toBeDisabled();
    await expect(extrude).toContainText("Finish Fillet first");

    // A stray click on the locked Extrude is inert — the Fillet command and its
    // picked edge survive (the silent pick-loss the audit found is gone).
    await extrude.click({ force: true }).catch(() => {});
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await expect(page.getByTestId("selected-count")).toHaveText(
      "1 edge picked",
    );
    await expect(page.getByTestId("extrude-distance")).toHaveCount(0);

    // Cancel is the honest way out — the band unlocks.
    await page.getByTestId("fillet-cancel").click();
    await expect(page.getByTestId("fillet-editor")).toHaveCount(0);
    await expect(page.getByTestId("create-strip")).not.toHaveAttribute(
      "data-command",
      "Fillet",
    );
    await expect(extrude).toBeEnabled();
  });
});

test.describe("sketch exit is idempotent", () => {
  test("double-Escape from a fresh sketch mints exactly one feature", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Escape part");
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(0);

    // Enter sketch, pick XY, draw a rectangle (no constraints → the debounce
    // loop stays quiet; only the exit path can persist it).
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
    await page.keyboard.press("r");
    await page.mouse.click(650, 420);
    await page.mouse.move(950, 620);
    await page.mouse.click(950, 620);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    // Hammer Escape: reset the tool, then finish — and finish again while the
    // create is still in flight. The idempotent guard must mint ONE feature.
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");

    // Sketch mode closes and exactly one "Sketch1" persists.
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    await expect(page.getByTestId("feature-row")).toHaveCount(1);
    await expect(page.getByTestId("feature-row")).toContainText("Sketch1");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // Reload proves the server holds a single feature (no duplicate slipped in).
    await page.reload();
    await expect(page.getByTestId("feature-row")).toHaveCount(1);
  });
});

/**
 * Founder before/after gallery for Batch 2 (gated behind UPDATE_SCREENSHOTS —
 * see e2e/fixtures.ts). Each frame shows one "earns its place" win: the grouped
 * command band, the scoped-in-command band, the mode-legible sketch band with
 * its breadcrumb, and a disabled tool speaking its reason.
 */
async function captureBatch2(page: Page, width: "desktop" | "laptop") {
  const part = await seedBoxPart(page);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);

  // 1) The grouped Create / Modify / Inspect band + breadcrumb + cleaned inspector.
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/makeover-batch2-band-${width}.png`,
  });

  // 2) In-command: the open Fillet scopes (locks) the whole band.
  await page.getByTestId("new-fillet").click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/makeover-batch2-scoped-${width}.png`,
  });
  await page.getByTestId("fillet-cancel").click();

  // 3) Sketch mode: eyebrow-grouped tool band + "… › Sketch" breadcrumb.
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await expect(page.getByTestId("workspace-mode")).toHaveText("Sketch");
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/makeover-batch2-sketch-${width}.png`,
  });
}

test.describe("founder gallery — Batch 2", () => {
  test("desktop states (band, scoped, sketch)", async ({ page }) => {
    await captureBatch2(page, "desktop");
  });

  test("a disabled tool speaks its reason (desktop)", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Empty part");
    await page.goto(`/parts/${part.id}`);
    const extrude = page.getByTestId("new-extrude");
    await expect(extrude).toBeDisabled();
    await extrude.hover();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/makeover-batch2-disabled-reason-desktop.png`,
    });
  });

  test.describe("small laptop (1280×800)", () => {
    test.use({ viewport: { width: 1280, height: 800 } });
    test("laptop states (band, scoped, sketch)", async ({ page }) => {
      await captureBatch2(page, "laptop");
    });
  });
});
