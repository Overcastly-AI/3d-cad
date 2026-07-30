import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Feature suppress (slice 2b) — the tree-row toggle, driven through the real
 * browser against the real stack (gateway + documents + geometry, no mocks).
 * Backend is shipped: geometry SKIPS suppressed features (slice 1), documents
 * persists + carries the flag (slice 2a). This proves the UI verb finally
 * reaches it end-to-end: seed a 20 mm cube + a fillet (the body rounds, volume
 * < 8000), then SUPPRESS the fillet in the tree and assert the body rebuilds
 * UN-filleted (volume back to 8000), the fillet row reads suppressed/dimmed,
 * and the solve stays green — then UN-suppress and the fillet returns.
 */

/** Seed sketch → extrude → fillet(all edges, r5): a rounded 20 mm cube. */
async function seedFilletedCube(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Suppress fillet");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  const extrude = await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  await createFeature(page, account.token, part.id, {
    name: "Fillet1",
    feature: {
      type: "fillet",
      version: 1,
      params: { edges: { kind: "all_edges" }, radius_mm: 5 },
    },
    expected_tree_version: extrude.tree_version,
  });
  return part.id;
}

/** The body volume (mm³) parsed from the mass-properties readout. */
async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const nums = text.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/g) ?? [];
  return Number.parseFloat(nums[0] ?? "NaN");
}

async function waitForSolvedBody(page: Page): Promise<void> {
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

test.describe("feature suppress", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("suppressing the fillet rebuilds the body without it; un-suppress restores it", async ({
    page,
  }) => {
    const partId = await seedFilletedCube(page);
    await page.goto(`/parts/${partId}`);

    // The rounded cube: three feature rows, and the fillet has removed material.
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await waitForSolvedBody(page);
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBeLessThan(8000);

    const filletRow = page.getByTestId("feature-row").nth(2);
    const suppressToggle = page.getByTestId("feature-suppress-2");
    await expect(filletRow).toContainText("fillet");
    await expect(suppressToggle).toHaveAttribute("aria-pressed", "false");

    // Before: the fillet is active (bright row, rounded body).
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/feature-suppress-before-desktop.png`,
    });

    // Suppress the fillet: the row stays but reads dimmed/suppressed and the
    // body rebuilds off the non-suppressed prefix — a clean 8,000 mm³ cube.
    await suppressToggle.click();
    await expect(suppressToggle).toHaveAttribute("aria-pressed", "true");
    await expect(filletRow).toHaveAttribute("data-suppressed", "true");
    await expect(filletRow).toContainText("SUPP");
    await expect(page.getByTestId("feature-row")).toHaveCount(3); // reversible
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBeCloseTo(8000, 0);

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/feature-suppress-on-desktop.png`,
    });

    // Un-suppress: the fillet returns and the body loses material again.
    await suppressToggle.click();
    await expect(suppressToggle).toHaveAttribute("aria-pressed", "false");
    await expect(filletRow).not.toHaveAttribute("data-suppressed", "true");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBeLessThan(8000);

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/feature-suppress-off-desktop.png`,
    });
  });

  test.describe("small laptop (1280×800)", () => {
    test.use({ viewport: { width: 1280, height: 800 } });

    test("the suppressed row stays legible and the tree stays quiet; founder screenshot", async ({
      page,
    }) => {
      const partId = await seedFilletedCube(page);
      await page.goto(`/parts/${partId}`);
      await expect(page.getByTestId("feature-row")).toHaveCount(3);
      await waitForSolvedBody(page);

      const suppressToggle = page.getByTestId("feature-suppress-2");
      await suppressToggle.click();
      await expect(suppressToggle).toHaveAttribute("aria-pressed", "true");
      await expect(page.getByTestId("feature-row").nth(2)).toHaveAttribute(
        "data-suppressed",
        "true",
      );
      await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
        timeout: 30_000,
      });
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/feature-suppress-on-laptop.png`,
      });
    });
  });
});
