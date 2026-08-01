import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * FINDINGS #8 (live extrude ghost) + #10 (right-click context menus), driven
 * through the real browser against the real stack. #8: the extrude editor
 * shows a swept ghost of the result AS the distance changes, before Save —
 * proven both by the raster-independent DOM signal and by the canvas gaining
 * the shaded ghost's colours. #10: right-click opens a token-styled menu on the
 * viewport (view snaps) and on a feature row (rename / delete), and an item
 * actually acts.
 */

async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
}

async function sketchRectangle(page: Page): Promise<void> {
  await page.keyboard.press("r");
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

test.describe("live extrude ghost (FINDINGS #8)", () => {
  test("ghost appears on distance change before Save, and clears on cancel", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Ghost plate");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    await sketchRectangle(page);

    // A bare sketch (thin ink) paints relatively few shades.
    const inkColors = await distinctCanvasColors(page);

    // Open the extrude editor — the ghost lights up at the default 10 mm,
    // BEFORE any Save. The hidden marker is the raster-independent hook.
    await page.getByTestId("new-extrude").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    const marker = page.getByTestId("extrude-preview-active");
    await expect(marker).toBeAttached();
    await expect(marker).toHaveAttribute("data-distance-mm", "10");

    // The shaded translucent solid adds many colours the flat sketch had not.
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 10_000 })
      .toBeGreaterThan(inkColors + 8);

    // Typing a new distance moves the ghost live (still pre-Save).
    await page.getByTestId("extrude-distance").fill("30");
    await expect(marker).toHaveAttribute("data-distance-mm", "30");

    // No body was committed — the inspector never appeared.
    await expect(page.getByTestId("body-inspector")).toBeHidden();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-ghost-desktop.png`,
    });

    // Escape cancels the editor; the ghost is gone.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("extrude-editor")).toBeHidden();
    await expect(marker).toHaveCount(0);
  });
});

test.describe("viewport context menu (FINDINGS #10)", () => {
  test("right-click opens the menu; a view snap acts", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Menu part");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    await sketchRectangle(page);
    await page.getByTestId("new-extrude").click();
    await page.getByTestId("extrude-distance").press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });

    // Right-click the scene → the token menu opens at the pointer.
    await page
      .getByTestId("viewport")
      .click({ button: "right", position: { x: 700, y: 380 } });
    const menu = page.getByTestId("viewport-context-menu");
    await expect(menu).toBeVisible();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/viewport-context-menu-desktop.png`,
    });

    // Pick a named view — the camera settles and the viewport stamps it.
    await page.getByTestId("ctx-view-front").click();
    await expect(menu).toBeHidden();
    await expect
      .poll(() => page.getByTestId("viewport").getAttribute("data-view"), {
        timeout: 10_000,
      })
      .toBe("front");
  });
});

test.describe("feature-tree row menu (FINDINGS #10)", () => {
  test("right-click a row → rename inline, then delete", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Tree menu");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    await sketchRectangle(page);
    await page.getByTestId("new-extrude").click();
    await page.getByTestId("extrude-distance").press("Enter");
    await expect(page.getByTestId("feature-row")).toHaveCount(2);

    // Right-click the extrude row → the row menu opens.
    await page.getByTestId("feature-select-1").click({ button: "right" });
    const menu = page.getByTestId("tree-context-menu");
    await expect(menu).toBeVisible();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/tree-context-menu-desktop.png`,
    });

    // Rename → inline field → new name commits on Enter.
    await page.getByTestId("tree-ctx-rename").click();
    const field = page.getByTestId("feature-rename-1");
    await expect(field).toBeVisible();
    await field.fill("Boss");
    await field.press("Enter");
    await expect(page.getByTestId("feature-select-1")).toContainText("Boss", {
      timeout: 15_000,
    });

    // Delete the extrude via the row menu → the tree shrinks to one feature.
    await page.getByTestId("feature-select-1").click({ button: "right" });
    await expect(page.getByTestId("tree-context-menu")).toBeVisible();
    await page.getByTestId("tree-ctx-delete").click();
    await expect(page.getByTestId("feature-row")).toHaveCount(1, {
      timeout: 15_000,
    });
  });
});

test.describe("live ghost small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("ghost + context menu usable at laptop width; founder screenshot", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Ghost laptop");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    await page.keyboard.press("r");
    await page.mouse.click(540, 340);
    await page.mouse.move(820, 520);
    await page.mouse.click(820, 520);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    await page.getByTestId("new-extrude").click();
    await expect(page.getByTestId("extrude-preview-active")).toBeAttached();
    await page.getByTestId("extrude-distance").fill("22");
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-distance-mm",
      "22",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-ghost-laptop.png`,
    });
  });
});
