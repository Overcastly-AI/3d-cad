import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, seedSession } from "./support";

/**
 * FB-12 (founder, 2026-08-01: *"the line wouldn't even select"*). A click whose
 * pointer drifted more than 4 px between press and release was silently thrown
 * away as a pan. On a trackpad that is most clicks. The QA pass measured the
 * cliff exactly:
 *
 *     0 px SELECTS · 1 · 2 · 3 · 4 SELECTS · 5 DEAD · 6 · 8 · 10 DEAD
 *
 * AND THE SUITE COULD NOT HAVE CAUGHT IT, which is the more important half:
 * `page.mouse.click()` presses and releases at the identical coordinate, so
 * every existing spec exercises 0 px of travel — a path no human hand takes.
 * Every test here therefore drives `down` → `move` → `up` explicitly. A spec
 * that clicks without moving proves nothing about this bug, so if you find
 * yourself simplifying one of these into `mouse.click`, don't.
 *
 * Threshold reasoning and the numbers behind it live in
 * `apps/web/src/sketch/clickIntent.ts`; the unit suite covers the boundaries.
 * These are the two integration facts a unit test cannot reach: the sketcher
 * really does select under drift, and a real drag really is still a drag.
 */

/** Press, drift `dx`,`dy` over `steps`, release — a click from a live hand. */
async function driftClick(
  page: Page,
  x: number,
  y: number,
  dx: number,
  dy: number,
  steps = 5,
): Promise<void> {
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y + dy, { steps });
  await page.mouse.up();
}

/** Open a fresh part and enter the sketcher on the XY datum. */
async function openSketchOnXy(page: Page): Promise<void> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Trackpad hand");
  await page.goto(`/parts/${part.id}`);
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
}

/** Draw a rectangle with the corners well apart, and return its edge midpoints. */
async function drawRectangle(
  page: Page,
): Promise<{ bottom: [number, number] }> {
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(700, 420);
  await page.mouse.move(1000, 640);
  await page.mouse.click(1000, 640);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  return { bottom: [850, 640] };
}

test.describe("FB-12 — a click still counts when the hand moves", () => {
  test("a drifting click selects the line under it", async ({ page }) => {
    await openSketchOnXy(page);
    const { bottom } = await drawRectangle(page);

    // Back to the select tool (there is no select BUTTON — select is the
    // resting tool the Escape cascade returns to); nothing is picked yet.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("tool-rect")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );

    // 8 px of drift — squarely inside the range the QA pass measured DEAD.
    await driftClick(page, bottom[0], bottom[1], 6, 5);
    await expect(page.getByTestId("selection-readout")).not.toContainText(
      "nothing selected",
    );
  });

  test("a real drag is still a drag, not a selection", async ({ page }) => {
    await openSketchOnXy(page);
    const { bottom } = await drawRectangle(page);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("tool-rect")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );

    // 140 px of deliberate travel from the same start point: an orbit. The
    // threshold has to keep rejecting this or the viewport becomes unusable —
    // it is the whole reason the gate exists and cannot simply be removed.
    await driftClick(page, bottom[0], bottom[1], 120, 70, 12);
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );
  });
});
