import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Ready #1 — the Fillet/Chamfer authoring UI, driven through the real browser
 * against the real stack (gateway + documents + geometry, no mocks). The kernel
 * has supported both since Phase 1; this proves the UI path finally reaches it:
 * seed a 20 mm cube, then round (fillet, all edges, r5) or bevel (chamfer, all
 * edges) it through the editor and assert the feature lands in the tree AND the
 * body re-renders with LESS material (rounding/beveling convex edges removes
 * volume). Geometric correctness itself is geometry-qa's golden suite; here we
 * verify the user-facing flow the shipped tool promises.
 */

/** Seed a part whose body is a 20 mm cube (8,000 mm³) at the origin. */
async function seedCubePart(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Modify cube");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
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
  return part.id;
}

async function waitForCube(page: Page): Promise<void> {
  await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/** The body volume (mm³) parsed from the mass-properties readout. */
async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const nums = text.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/g) ?? [];
  return Number.parseFloat(nums[0] ?? "NaN");
}

test.describe("fillet authoring", () => {
  test("fillet (all edges, r5) lands in the tree and rounds the body", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);
    await expect(page.getByTestId("feature-row")).toHaveCount(2);

    // Fillet gates on a body existing — it lights up in the Modify group.
    const filletAction = page.getByTestId("new-fillet");
    await expect(filletAction).toBeEnabled();
    await filletAction.click();

    // The keyboard-first editor: the radius field is focused, defaults to 2,
    // and the edge selector is the honest predicate cell (defaults to all edges).
    const editor = page.getByTestId("fillet-editor");
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("fillet-radius")).toBeFocused();
    await expect(page.getByTestId("fillet-edges")).toHaveValue("all_edges");

    // Round every edge with a 5 mm radius; Enter commits.
    await page.getByTestId("fillet-radius").fill("5");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/fillet-editor-desktop.png`,
    });
    await page.getByTestId("fillet-radius").press("Enter");

    // The fillet is the third feature and the body rebuilds — no rebuild error.
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("feature-row").nth(2)).toContainText(
      "fillet",
    );
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);

    // Rounding convex edges removes material: the volume drops below the cube's.
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBeLessThan(8000);
  });
});

test.describe("chamfer authoring", () => {
  test("chamfer (all edges) lands in the tree and bevels the body", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);
    await expect(page.getByTestId("feature-row")).toHaveCount(2);

    const chamferAction = page.getByTestId("new-chamfer");
    await expect(chamferAction).toBeEnabled();
    await chamferAction.click();

    const editor = page.getByTestId("chamfer-editor");
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("chamfer-distance")).toBeFocused();
    await expect(page.getByTestId("chamfer-edges")).toHaveValue("all_edges");

    // A 2 mm bevel of every edge; Enter commits.
    await page.getByTestId("chamfer-distance").fill("2");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/chamfer-editor-desktop.png`,
    });
    await page.getByTestId("chamfer-distance").press("Enter");

    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("feature-row").nth(2)).toContainText(
      "chamfer",
    );
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);

    // Beveling convex edges removes material: the volume drops below the cube's.
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBeLessThan(8000);
  });

  test.describe("small laptop (1280×800)", () => {
    test.use({ viewport: { width: 1280, height: 800 } });

    test("the fillet editor keeps the viewport dominant; founder screenshot", async ({
      page,
    }) => {
      const partId = await seedCubePart(page);
      await page.goto(`/parts/${partId}`);
      await waitForCube(page);

      await page.getByTestId("new-fillet").click();
      await expect(page.getByTestId("fillet-editor")).toBeVisible();
      await page.getByTestId("fillet-radius").fill("5");
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/fillet-editor-laptop.png`,
      });

      // The viewport still owns the width — chrome recedes (design mandate #3).
      const box = await page.getByTestId("viewport").boundingBox();
      expect(box?.width ?? 0).toBeGreaterThan(560);
    });
  });
});
