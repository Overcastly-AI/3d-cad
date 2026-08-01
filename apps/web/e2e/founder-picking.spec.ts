import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, distinctCanvasColors, seedSession } from "./support";

/**
 * FOUNDER SESSION 2026-08-01 — the picking reports (BACKLOG FB-2/FB-3/FB-5,
 * plus FB-12/FB-13 which this pass found while reproducing them).
 *
 * The founder said a sketch line "wouldn't even select" and picking a face was
 * "very difficult". Driven at HEAD in a real browser against the real stack,
 * the pick MATH is fine — a clean click on a line selects the line and D opens
 * the dimension editor, at every commit tested. What is NOT fine is everything
 * around it, and each of those is pinned below.
 *
 * The `test.fail()` cases here encode a defect as it exists TODAY, so the suite
 * stays green while the bug is open AND turns red the moment somebody fixes it
 * without flipping the annotation. Resolving the annotation is part of each fix.
 *
 * Status, kept current because a stale census here is itself a defect (this
 * block said "three" for a while after two had been resolved):
 *   - FB-2  — never reproduced; kept as a live baseline guard, a plain `test`.
 *   - FB-12 — FIXED `b6d2f2d` (sketch/clickIntent.ts); flipped to a plain
 *     `test` that fails if the 4 px slop ever returns.
 *   - FB-13 — FIXED `d2e2162`; case REMOVED, not flipped (see the note below —
 *     it had also gone stale, waiting on a row that is no longer minted).
 *   - FB-3/FB-5 — STILL OPEN: the face itself is not a click target.
 */

/** Enter the sketcher on a base plane with snap OFF, so clicks land on pixels. */
async function sketchOnXY(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
  // Snap off: with the 1 mm grid magnet on, a corner lands up to ~7 px from
  // where it was clicked and the edge under test moves out from under the
  // fixed probe point. Off, the rectangle's edges ARE the clicked pixels.
  await page.keyboard.press("g");
}

/** Draw the probe rectangle; its bottom edge is the horizontal line y = 640. */
async function drawProbeRectangle(page: Page): Promise<void> {
  await page.keyboard.press("r");
  await page.mouse.click(650, 420);
  await page.mouse.move(980, 640);
  await page.mouse.click(980, 640);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.keyboard.press("Escape"); // rect tool -> select tool
}

/** Midpoint of the probe rectangle's bottom edge, in screen px. */
const BOTTOM_EDGE = { x: 815, y: 640 };

/** Build a 10 mm box on XY so there is a body with six planar faces. */
async function buildBox(page: Page): Promise<void> {
  await sketchOnXY(page);
  await drawProbeRectangle(page);
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("new-extrude")).toBeEnabled({
    timeout: 30_000,
  });
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
  await page.getByTestId("extrude-distance").press("Enter");
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

test.describe("founder picking reports", () => {
  test("FB-2 baseline: a clean click on a line selects it and D dimensions it", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Pick a line");
    await page.goto(`/parts/${part.id}`);
    await sketchOnXY(page);
    await drawProbeRectangle(page);

    await page.mouse.click(BOTTOM_EDGE.x, BOTTOM_EDGE.y);
    await page.keyboard.press("d");

    // The distance branch needs EXACTLY ONE selected LINE; anything else
    // answers with a hint. The editor opening proves the click resolved to the
    // line entity and not to an endpoint point, an empty pick, or two lines.
    await expect(page.getByTestId("dimension-input")).toBeVisible();
    await expect(page.getByTestId("constraint-hint")).toHaveCount(0);
  });

  test("FB-12 FIXED: a click that drifts 6 px still selects the line", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Slop");
    await page.goto(`/parts/${part.id}`);
    await sketchOnXY(page);
    await drawProbeRectangle(page);

    // A real hand on a trackpad drifts between press and release, and r3f
    // reports that travel as `e.delta`. This USED to be discarded: the handler
    // returned early above CLICK_SLOP_PX = 4, so a 6 px click did nothing at
    // all — no hint, no cursor change, no log (measured: 4 px selected, 5 px
    // was dead). That is the defect the founder hit as "the line wouldn't even
    // select", and no spec could see it because `mouse.click()` moves 0 px.
    // `sketch/clickIntent.ts` now decides by intent rather than one constant;
    // this asserts the fix and fails if the old threshold ever returns.
    await page.mouse.move(BOTTOM_EDGE.x, BOTTOM_EDGE.y);
    await page.mouse.down();
    await page.mouse.move(BOTTOM_EDGE.x + 6, BOTTOM_EDGE.y);
    await page.mouse.up();
    await page.keyboard.press("d");

    await expect(page.getByTestId("dimension-input")).toBeVisible();
  });

  /*
   * FB-13 is FIXED and its case has been REMOVED rather than flipped.
   *
   * `d2e2162` gave `escapeAction` a "none" rung: at rest with work in the
   * sketch Escape now unwinds nothing and says so, and "exit" survives only
   * when there is nothing to lose. The behaviour is covered end to end by
   * `sketch-escape-select.spec.ts` (6 tests), so re-asserting it here would be
   * duplication.
   *
   * Deleting it also removes a live trap. The case was written to wait up to
   * 30 s for the feature row that `finishSketch` used to mint — a row that is
   * now never created. It still "failed as expected" under `test.fail()`, so
   * the suite stayed green while the assertion had quietly stopped meaning
   * anything, at a cost of ~35 s every run. A `test.fail()` that passes for a
   * NEW reason is the same defect class as a green gate measuring the wrong
   * thing: read why it failed, never just that it did.
   */

  test.fail(
    "FB-3/FB-5: clicking a highlighted face does not seat the sketch on it",
    async ({ page }) => {
      const account = await seedSession(page);
      const part = await createPartViaApi(page, account.token, "Face pick");
      await page.goto(`/parts/${part.id}`);
      await buildBox(page);

      await page.getByTestId("new-sketch").click();
      await page.getByTestId("plane-pick-face").click();
      await expect(page.getByTestId("face-pick-prompt")).toBeVisible();
      const nodes = page.locator('[data-testid^="plane-pick-face-"]');
      await expect(nodes.first()).toBeVisible({ timeout: 20_000 });

      // The prompt says "Click a highlighted planar face to sketch on it", but
      // the only live targets are the six 24 px `PickNode` markers at the face
      // CENTROIDS — the face itself carries no raycast handler (ModelMesh has
      // no onClick at all). Measured: 2.2% of the body's on-screen area is a
      // pick target. This clicks the top face well away from every marker.
      const marker = await nodes.first().boundingBox();
      expect(marker).not.toBeNull();
      await page.mouse.click(1000, 430);

      await expect(page.getByTestId("sketch-step")).toHaveText("On Face", {
        timeout: 5_000,
      });
    },
  );
});
