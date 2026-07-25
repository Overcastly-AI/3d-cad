import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Feature-localized selection (FINDINGS #9). The bug: any tree selection swapped
 * the studio matcap for flat tan across the WHOLE body — never localized. The
 * fix: the selected feature's faces (every `OverlayFace` whose `feature_id`
 * matches, indexed by GLB primitive ordinal) take a brass tint + brass boundary
 * edges, while the matcap is PRESERVED on every other face.
 *
 * The load-bearing, raster-independent proof rides two viewport QA hooks:
 *   - `data-body-highlight` — "feature" (localized subset) vs "selected"
 *     (whole body) vs "hover"/"none".
 *   - `data-selected-faces` / `data-total-faces` — selecting the HOLE lights a
 *     PROPER subset (`selected < total` ⇒ matcap kept on the rest); selecting a
 *     feature that owns EVERY face (the base extrude of a plain box) lights all
 *     of them ⇒ the distinct whole-body state.
 */

async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/** Draw a rectangle (two clicks) and persist it; wait for the solve. */
async function sketchRectangleAndSave(page: Page): Promise<void> {
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
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** Extrude the solved profile 10 mm through the UI and wait for the body. */
async function extrudeTenMm(page: Page): Promise<void> {
  await expect(page.getByTestId("new-extrude")).toBeEnabled({
    timeout: 30_000,
  });
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
  await page.getByTestId("extrude-distance").press("Enter");
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
  await expectRenderedBody(page);
}

/** Build a 10 mm base box on XY, leaving a body with a top face at z = 10. */
async function buildBaseBox(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await sketchRectangleAndSave(page);
  await extrudeTenMm(page);
}

/** Click the body's TOP face node (greatest z in its accessible name). */
async function clickTopFace(page: Page): Promise<void> {
  const nodes = page.locator('[data-testid^="plane-pick-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const count = await nodes.count();
  let bestZ = -Infinity;
  let bestIndex = 0;
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const z = Number.parseFloat(nums[nums.length - 1] as string);
    if (Number.isFinite(z) && z > bestZ) {
      bestZ = z;
      bestIndex = i;
    }
  }
  await nodes.nth(bestIndex).click();
}

/** Drill a Ø6 through-all hole into the top face; wait for the solved body. */
async function drillTopFaceHole(page: Page): Promise<void> {
  await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-hole").click();
  await expect(page.getByTestId("hole-editor")).toBeVisible();
  await page.getByTestId("hole-face-pick").click();
  await clickTopFace(page);
  await expect(page.getByTestId("hole-face")).toContainText("10");
  await page.getByTestId("hole-submit").click();
  await expect(
    page.getByTestId("feature-row").filter({ hasText: "Hole1" }),
  ).toBeVisible();
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
  await expectRenderedBody(page);
}

test.describe("feature-localized selection (FINDINGS #9)", () => {
  test("selecting the hole lights only its faces; the matcap is preserved", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(
      page,
      account.token,
      "Localized select",
    );
    await page.goto(`/parts/${part.id}`);

    await buildBaseBox(page);
    await drillTopFaceHole(page);

    const viewport = page.getByTestId("viewport");
    // Close the hole editor that opened on the drill so the body is at rest.
    await page.keyboard.press("Escape");

    // Select the Hole row (sketch=0, extrude=1, hole=2). The body warms, then
    // localizes to the hole's faces once the overlay's per-face provenance lands.
    await page.getByTestId("feature-select-2").click();
    await expect(viewport).toHaveAttribute("data-body-highlight", "feature", {
      timeout: 15_000,
    });

    // THE PROOF: a PROPER subset is lit — fewer faces than the body has — so the
    // studio matcap is preserved on every un-selected face (not a clay swap).
    const lit = Number(await viewport.getAttribute("data-selected-faces"));
    const total = Number(await viewport.getAttribute("data-total-faces"));
    expect(total).toBeGreaterThan(6); // a box (6) reshaped by a through-hole
    expect(lit).toBeGreaterThan(0);
    expect(lit).toBeLessThan(total);

    // The localized highlight TRACKS the selection: switching to the base
    // extrude lights a DIFFERENT face set (its own faces), still a subset.
    await page.getByTestId("feature-select-1").click();
    await expect(viewport).toHaveAttribute("data-body-highlight", "feature", {
      timeout: 15_000,
    });
    const extrudeLit = Number(
      await viewport.getAttribute("data-selected-faces"),
    );
    expect(extrudeLit).toBeGreaterThan(0);
    expect(extrudeLit).toBeLessThan(total);
    expect(extrudeLit).not.toBe(lit);
  });

  test("selecting a feature that owns every face is the distinct whole-body state", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(
      page,
      account.token,
      "Whole-body select",
    );
    await page.goto(`/parts/${part.id}`);

    await buildBaseBox(page);

    const viewport = page.getByTestId("viewport");
    // The base extrude of a plain box owns all six faces → the whole-body state,
    // visually distinct from a feature-localized subset.
    await page.getByTestId("feature-select-1").click();
    await expect(viewport).toHaveAttribute("data-body-highlight", "selected");
    await expect
      .poll(
        async () => {
          const lit = Number(
            await viewport.getAttribute("data-selected-faces"),
          );
          const total = Number(await viewport.getAttribute("data-total-faces"));
          return total > 0 && lit === total;
        },
        { timeout: 15_000 },
      )
      .toBe(true);
  });
});

/**
 * Founder before/after gallery (gated behind UPDATE_SCREENSHOTS — see
 * e2e/fixtures.ts). Two distinct AFTER states the fix introduces: the
 * feature-localized highlight (only the hole's faces brass, matcap preserved)
 * and the whole-body state (a feature that owns every face).
 */
async function captureSelectionStates(
  page: Page,
  width: "desktop" | "laptop",
): Promise<void> {
  const account = await seedSession(page);

  // 1) Feature-localized: the hole selected on a drilled plate.
  const holed = await createPartViaApi(page, account.token, "Shot: localized");
  await page.goto(`/parts/${holed.id}`);
  await buildBaseBox(page);
  await drillTopFaceHole(page);
  await page.keyboard.press("Escape");
  const viewport = page.getByTestId("viewport");
  await page.getByTestId("feature-select-2").click();
  await expect(viewport).toHaveAttribute("data-body-highlight", "feature", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
    timeout: 30_000,
  });
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/finding9-feature-localized-${width}.png`,
  });

  // 2) Whole-body: the base extrude of a plain box (owns every face).
  const box = await createPartViaApi(page, account.token, "Shot: whole body");
  await page.goto(`/parts/${box.id}`);
  await buildBaseBox(page);
  await page.getByTestId("feature-select-1").click();
  await expect(viewport).toHaveAttribute("data-body-highlight", "selected");
  await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
    timeout: 30_000,
  });
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/finding9-whole-body-${width}.png`,
  });
}

test.describe("FINDINGS #9 — founder screenshots", () => {
  test("selection states (desktop 1440×900)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await captureSelectionStates(page, "desktop");
  });

  test("selection states (small laptop 1280×800)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await captureSelectionStates(page, "laptop");
  });
});
