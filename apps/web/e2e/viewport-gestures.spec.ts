import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, seedSession } from "./support";

/**
 * Viewport pointer gestures (FINDINGS burn-down 2026-07-25 #4). The right
 * button PANS the camera (the orbit rig binds `RIGHT: MOUSE.PAN`), and the
 * rig's own `contextmenu` handler only `preventDefault()`s — the event still
 * reaches the container. Before the click-slop gate, every right-drag pan ended
 * by popping the context menu at the release point, which neither Fusion 360
 * nor Plasticity does.
 *
 * Driven in a real browser against the real stack: a right DRAG pans and leaves
 * the menu shut; a right CLICK (including one with hand tremor) still opens it.
 */

async function openEmptyPart(page: Page): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Pan gestures");
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("viewport")).toBeVisible();
  // The bench renders (grid + atmosphere) before any gesture is dispatched.
  await expect(page.getByTestId("viewport").locator("canvas")).toBeVisible();
}

/** Drag the right button from `from` by (dx, dy) in viewport pixels. */
async function rightDrag(
  page: Page,
  from: { x: number; y: number },
  dx: number,
  dy: number,
): Promise<void> {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down({ button: "right" });
  await page.mouse.move(from.x + dx, from.y + dy, { steps: 12 });
  await page.mouse.up({ button: "right" });
}

test.describe("right-button gestures", () => {
  test("a right-drag pans without opening the context menu", async ({
    page,
  }) => {
    await openEmptyPart(page);
    const viewport = page.getByTestId("viewport");
    const menu = page.getByTestId("viewport-context-menu");

    const before = await viewport.locator("canvas").screenshot();
    await rightDrag(page, { x: 760, y: 420 }, 140, 90);

    // The menu never appeared — and stays away (give the handler a beat).
    await expect(menu).toHaveCount(0);
    await page.waitForTimeout(250);
    await expect(menu).toHaveCount(0);

    // The gesture actually panned the camera: the scene raster moved.
    const after = await viewport.locator("canvas").screenshot();
    expect(Buffer.compare(before, after)).not.toBe(0);
  });

  test("a right-click still opens the menu, tremor and all", async ({
    page,
  }) => {
    await openEmptyPart(page);
    const menu = page.getByTestId("viewport-context-menu");

    // A clean click at rest.
    await page
      .getByTestId("viewport")
      .click({ button: "right", position: { x: 700, y: 380 } });
    await expect(menu).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);

    // A click with 2px of hand tremor is still a click.
    await rightDrag(page, { x: 700, y: 380 }, 2, 1);
    await expect(menu).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);
  });
});
