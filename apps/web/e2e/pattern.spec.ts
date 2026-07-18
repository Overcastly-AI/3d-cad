import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * BACKLOG #7 (7b): the pattern authoring UI, driven through the real browser
 * against the real stack (gateway + documents + geometry, no mocks). A pattern
 * repeats the current body and unions the copies, so the flow is: sketch a
 * rectangle → extrude it → add a LINEAR pattern (count 3, spacing 6 along +X)
 * → the pattern lands in the tree AND the body re-renders as a wider bar (the
 * copies union onto the seed). A real end-to-end geometric assertion.
 */

/** The lit aluminium solid + B-rep edges paint far more shades than ground. */
async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/** Enter sketch mode on a datum plane. */
async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
}

/** Draw a rectangle (two clicks) and persist it as Sketch1. */
async function sketchRectangle(page: Page): Promise<void> {
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(650, 420);
  await page.mouse.move(980, 640);
  await page.mouse.click(980, 640);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** The i-th extent (mm) of the rendered body: 0 = X, 1 = Y, 2 = Z. The row
 *  reads "Extents  X × Y × Z  mm", so pull the three numbers by regex (the
 *  "Extents"/"mm" chrome carries no digits). */
async function bodyExtent(page: Page, axis: 0 | 1 | 2): Promise<number> {
  const text = await page.getByTestId("prop-extents").innerText();
  const nums = text.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/g) ?? [];
  return Number.parseFloat(nums[axis] ?? "NaN");
}

/** Sketch + extrude a rectangle — the seed body every pattern test starts from. */
async function extrudedSeed(page: Page): Promise<void> {
  await enterSketch(page, "XY");
  await sketchRectangle(page);
  await page.getByTestId("new-extrude").click();
  await page.getByTestId("extrude-distance").press("Enter");
  await expect(page.getByTestId("body-inspector")).toBeVisible();
  await expectRenderedBody(page);
}

test.describe("pattern authoring", () => {
  test("linear pattern lands in the tree and widens the body", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Pattern bar");
    await page.goto(`/parts/${part.id}`);

    await extrudedSeed(page);
    // Two features so far (sketch + extrude); record the seed's X-extent.
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    const seedWidth = await bodyExtent(page, 0);
    expect(seedWidth).toBeGreaterThan(6); // spacing must be < width to union

    // Pattern gates on a body existing — it lights up in the Modify group.
    const patternAction = page.getByTestId("new-pattern");
    await expect(patternAction).toBeEnabled();
    await patternAction.click();

    // The keyboard-first form: Linear is the default mode, count is focused at
    // 3, and the count note explains the seed is included.
    const editor = page.getByTestId("pattern-editor");
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("pattern-kind-linear")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("pattern-count")).toHaveValue("3");
    await expect(page.getByTestId("pattern-count-note")).toBeVisible();

    // Spacing 6 mm along +X (the default direction); Enter creates.
    await page.getByTestId("pattern-spacing").fill("6");
    await page.getByTestId("pattern-spacing").press("Enter");

    // The pattern is the third feature and the body rebuilds — no rebuild error.
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("feature-row").nth(2)).toContainText(
      "pattern",
    );
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);

    // The union of 3 copies 6 mm apart is a wider bar: +12 mm of X-extent
    // (copies at 0/6/12), so the body is meaningfully wider than the seed.
    await expect
      .poll(() => bodyExtent(page, 0), { timeout: 30_000 })
      .toBeGreaterThan(seedWidth + 8);
  });

  test("circular mode swaps to axis + angle fields", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Pattern ring");
    await page.goto(`/parts/${part.id}`);

    await extrudedSeed(page);
    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();

    // Linear shows a spacing field; toggling to circular reveals the axis
    // point + angle and hides spacing — the discriminated params in the UI.
    await expect(page.getByTestId("pattern-spacing")).toBeVisible();
    await page.getByTestId("pattern-kind-circular").click();
    await expect(page.getByTestId("pattern-spacing")).toHaveCount(0);
    await expect(page.getByTestId("pattern-axis-x")).toBeVisible();
    await expect(page.getByTestId("pattern-angle")).toHaveValue("360");
  });
});

test.describe("pattern founder screenshots", () => {
  for (const [name, width, height] of [
    ["desktop", 1600, 1000],
    ["laptop", 1280, 800],
  ] as const) {
    test(`before/after at ${name} width`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      const account = await seedSession(page);
      const part = await createPartViaApi(
        page,
        account.token,
        `Pattern ${name}`,
      );
      await page.goto(`/parts/${part.id}`);
      await extrudedSeed(page);

      // BEFORE: the single seed body with the pattern form open.
      await page.getByTestId("new-pattern").click();
      await expect(page.getByTestId("pattern-editor")).toBeVisible();
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/pattern-ui-before-${name}.png`,
      });

      // AFTER: commit the linear pattern; the body is a wider bar in the tree.
      await page.getByTestId("pattern-spacing").fill("6");
      await page.getByTestId("pattern-spacing").press("Enter");
      await expect(page.getByTestId("feature-row")).toHaveCount(3);
      await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
        timeout: 30_000,
      });
      await expectRenderedBody(page);
      // Re-open the pattern to show the form, body, and tree in one frame.
      await page.getByTestId("feature-select-2").click();
      await expect(page.getByTestId("pattern-editor")).toBeVisible();
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/pattern-ui-after-${name}.png`,
      });
    });
  }
});
