import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Pre-selection (UI-W3) — the founder's report, driven end-to-end in the real
 * stack: "placement face looks like a text box? Shouldn't it know based on the
 * face I select with the cursor?"
 *
 * Before this, every pick session died with the editor that opened it: pick a
 * face for a hole, change your mind, and the next command opened with an empty
 * reference and demanded you ARM a pick mode and click the same face again.
 * The proofs here are the three halves of the fix:
 *
 *  1. the face pick is ARMED on open, so a click just takes it (no arming step);
 *  2. a pick SURVIVES the command that made it — reopening Hole finds the face
 *     already placed and Create immediately reachable;
 *  3. the selection crosses commands — the face picked for a hole seeds a DATUM
 *     as an on_face datum, which is what the modeller meant by selecting it.
 *
 * And the guard rail that keeps it honest: once the body has been rebuilt by a
 * feature, the old pick is NOT offered (its signature may no longer resolve).
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

/** Build a 10 mm base box on XY, leaving a body with a top face at z = 10. */
async function buildBaseBox(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await sketchRectangleAndSave(page);
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

/** Click the body's TOP face node (greatest z in the pick-node label). */
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

/** Open Hole (armed on open), click the top face, then cancel the editor. */
async function pickTopFaceThenCancel(page: Page): Promise<void> {
  await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-hole").click();
  await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await clickTopFace(page);
  await expect(page.getByTestId("hole-face")).toContainText("10");
  await page.getByTestId("hole-cancel").click();
  await expect(page.getByTestId("hole-editor")).toHaveCount(0);
}

test.describe("pre-selection — the cursor's pick outlives the command", () => {
  test("a cancelled pick re-opens the hole already placed", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Preselect hole");
    await page.goto(`/parts/${part.id}`);
    await buildBaseBox(page);

    await pickTopFaceThenCancel(page);

    // The selection is VISIBLE with no editor open — the picked face stays lit
    // (a selection you cannot see would make the next prefill feel like magic).
    await expect(page.getByTestId("viewport")).toHaveAttribute(
      "data-body-highlight",
      "feature",
      { timeout: 15_000 },
    );

    // Re-open Hole: the anchor block is FILLED from the pre-selection, the pick
    // is NOT armed (arming is for CHANGING a reference now), and Create is
    // reachable without touching the viewport again.
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-face")).toContainText("10");
    await expect(page.getByTestId("hole-position")).toContainText(
      "Centre of face",
    );
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await expect(page.getByTestId("hole-submit")).toBeEnabled();

    // THE PROOF: the seeded reference is a real one — the kernel resolves it
    // and drills. A prefilled-but-broken reference would be worse than none.
    const write = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/features`) &&
        r.request().method() === "POST",
    );
    await page.getByTestId("hole-submit").click();
    expect((await write).status()).toBe(201);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
  });

  test("the selection crosses commands — a picked face seeds a datum ON it", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Preselect datum");
    await page.goto(`/parts/${part.id}`);
    await buildBaseBox(page);

    await pickTopFaceThenCancel(page);

    // Datum opens as an ON FACE datum seated on the selected face — no kind
    // switch, no second pick of the same face.
    await page.getByTestId("tool-datum").click();
    await expect(page.getByTestId("datum-kind")).toHaveValue("on_face");
    await expect(page.getByTestId("datum-on-face")).toContainText("10");
    await page.getByTestId("datum-submit").click();
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Plane1" }),
    ).toBeVisible();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
  });

  test("a pick taken on a SUPERSEDED body is not offered", async ({ page }) => {
    // The guard rail. Drill the hole, which rebuilds the body: the top face the
    // hole was placed on is now an annulus of a different feature's body, so
    // prefilling the next hole with the old signature would author a reference
    // that cannot resolve. The next Hole must open EMPTY and armed instead.
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Preselect stale");
    await page.goto(`/parts/${part.id}`);
    await buildBaseBox(page);

    await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
    await page.getByTestId("new-hole").click();
    await clickTopFace(page);
    await expect(page.getByTestId("hole-face")).toContainText("10");
    await page.getByTestId("hole-submit").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // The drilled hole opened its own editor on save; leave it.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("hole-editor")).toHaveCount(0);

    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-face-empty")).toHaveText(
      "Click a face",
    );
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});

test.describe("pre-selection — founder screenshots", () => {
  for (const width of [1440, 1366] as const) {
    const height = width === 1440 ? 900 : 768;
    test(`hole editor: references pinned, parameters scrolling (${width}x${height})`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height });
      const account = await seedSession(page);
      const part = await createPartViaApi(page, account.token, "UI-W4 shot");
      await page.goto(`/parts/${part.id}`);
      await buildBaseBox(page);

      // 1) Invoked with nothing selected: armed on open, the anchor block asks
      //    for a click.
      await expect(page.getByTestId("new-hole")).toBeEnabled({
        timeout: 30_000,
      });
      await page.getByTestId("new-hole").click();
      await expect(
        page.locator('[data-testid^="plane-pick-face-"]').first(),
      ).toBeVisible({ timeout: 20_000 });
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/uiw3-hole-armed-${width}.png`,
      });

      // 2) Placed: the anchor block reads as confirmation, the Ø is THE handle.
      await clickTopFace(page);
      await expect(page.getByTestId("hole-face")).toContainText("10");
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/uiw4-hole-placed-${width}.png`,
      });

      // 3) The tallest form (C'sink + Tapped + Blind): the references are still
      //    pinned in sight while the parameters scroll under them.
      await page.getByTestId("hole-type-countersink").click();
      await page.getByTestId("hole-depth-blind").click();
      await page.getByTestId("hole-thread-toggle").click();
      await page.getByTestId("hole-tapped").click();
      await expect(page.getByTestId("hole-thread-designation")).toBeVisible();
      await expect(page.getByTestId("hole-face")).toBeVisible();
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/uiw4-hole-tallest-${width}.png`,
      });
    });
  }
});
