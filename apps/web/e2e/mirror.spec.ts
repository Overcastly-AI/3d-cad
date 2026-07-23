import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * BACKLOG P2: the mirror feature authoring UI, driven through the real browser
 * against the real stack (gateway + documents + geometry, no mocks). A mirror
 * reflects the current body about a plane and unions the reflection back in, so
 * the flow is: sketch a rectangle → extrude it → add a Mirror about the XY
 * origin plane → the mirror lands in the tree AND the body re-renders reflected.
 *
 * The seed body sits at z ∈ [0, H] (an XY-sketch extruded +Z). Mirroring about
 * the XY plane (z = 0) reflects it to z ∈ [−H, 0], so the union's Z-extent
 * DOUBLES — a deterministic, position-independent end-to-end geometric assertion
 * (unlike an XY-plane mirror, an in-plane XY rectangle's model position is
 * screen-dependent, but its Z placement is always [0, H]).
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
 *  reads "Extents  X × Y × Z  mm", so pull the three numbers by regex. */
async function bodyExtent(page: Page, axis: 0 | 1 | 2): Promise<number> {
  const text = await page.getByTestId("prop-extents").innerText();
  const nums = text.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/g) ?? [];
  return Number.parseFloat(nums[axis] ?? "NaN");
}

/** Sketch + extrude a rectangle — the seed body every mirror test starts from. */
async function extrudedSeed(page: Page): Promise<void> {
  await enterSketch(page, "XY");
  await sketchRectangle(page);
  await page.getByTestId("new-extrude").click();
  await page.getByTestId("extrude-distance").press("Enter");
  await expect(page.getByTestId("body-inspector")).toBeVisible();
  await expectRenderedBody(page);
}

test.describe("mirror authoring", () => {
  test("mirror about XY lands in the tree and doubles the body's height", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Mirror bracket");
    await page.goto(`/parts/${part.id}`);

    await extrudedSeed(page);
    // Two features so far (sketch + extrude); record the seed's Z-extent.
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    const seedHeight = await bodyExtent(page, 2);
    expect(seedHeight).toBeGreaterThan(0);

    // Mirror gates on a body existing — it lights up in the Modify group.
    const mirrorAction = page.getByTestId("new-mirror");
    await expect(mirrorAction).toBeEnabled();
    await mirrorAction.click();

    // The keyboard-first form: XY is the default plane, the readout echoes it.
    const editor = page.getByTestId("mirror-editor");
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("mirror-plane-XY")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("mirror-readout")).toHaveText("XY");

    // Enter creates the mirror about XY.
    await page.getByTestId("mirror-submit").click();

    // The mirror is the third feature and the body rebuilds — no rebuild error.
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("feature-row").nth(2)).toContainText(
      "mirror",
    );
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);

    // The reflection lands at z ∈ [−H, 0], so the Z-extent roughly doubles.
    await expect
      .poll(() => bodyExtent(page, 2), { timeout: 30_000 })
      .toBeGreaterThan(seedHeight * 1.6);
  });

  test("the plane picker offers the origin datums", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Mirror planes");
    await page.goto(`/parts/${part.id}`);

    await extrudedSeed(page);
    await page.getByTestId("new-mirror").click();
    await expect(page.getByTestId("mirror-editor")).toBeVisible();

    // Choosing YZ updates the live readout — the same plane vocabulary a sketch
    // uses, in the editor seat.
    await page.getByTestId("mirror-plane-YZ").click();
    await expect(page.getByTestId("mirror-plane-YZ")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("mirror-readout")).toHaveText("YZ");

    // Escape cancels without authoring — the tree is untouched (sketch + extrude).
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("mirror-editor")).toHaveCount(0);
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
  });
});

test.describe("mirror founder screenshots", () => {
  for (const [name, width, height] of [
    ["desktop", 1440, 900],
    ["laptop", 1280, 800],
  ] as const) {
    test(`before/after at ${name} width`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      const account = await seedSession(page);
      const part = await createPartViaApi(
        page,
        account.token,
        `Mirror ${name}`,
      );
      await page.goto(`/parts/${part.id}`);
      await extrudedSeed(page);

      // BEFORE: the single seed body with the mirror form open on XY.
      await page.getByTestId("new-mirror").click();
      await expect(page.getByTestId("mirror-editor")).toBeVisible();
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/mirror-ui-before-${name}.png`,
      });

      // AFTER: commit the mirror; the reflected body lands in the tree.
      await page.getByTestId("mirror-submit").click();
      await expect(page.getByTestId("feature-row")).toHaveCount(3);
      await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
        timeout: 30_000,
      });
      await expectRenderedBody(page);
      // Re-open the mirror to show the form, body, and tree in one frame.
      await page.getByTestId("feature-select-2").click();
      await expect(page.getByTestId("mirror-editor")).toBeVisible();
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/mirror-ui-after-${name}.png`,
      });
    });
  }
});
