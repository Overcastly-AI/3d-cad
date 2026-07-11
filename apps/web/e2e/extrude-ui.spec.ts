import { expect, test, type Page } from "@playwright/test";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * BACKLOG #3: the extrude authoring UI + feature-tree edit/rollback. Everything
 * here is driven through the real browser against the real stack (gateway +
 * documents + geometry, no mocks): sketch a rectangle, extrude it via the UI,
 * see the body, edit the distance and watch it update, roll the bar back before
 * the extrude and see the pre-extrude state, and surface a profile_not_closed
 * rebuild error legibly in the tree.
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

/** The z-extent of the rendered body (mm) — equals an XY extrude's distance. */
async function bodyDepth(page: Page): Promise<number> {
  const extents = await page.getByTestId("prop-extents").innerText();
  const parts = extents.split("×").map((p) => Number.parseFloat(p.trim()));
  return parts[parts.length - 1] ?? Number.NaN;
}

/** The body volume (mm³) — the cell text carries its label + unit, so parse. */
async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

test.describe("extrude authoring", () => {
  test("create → body; edit distance → updates; roll back → pre-extrude", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Extrude plate");
    await page.goto(`/parts/${part.id}`);

    // Sketch a rectangle in the UI, then extrude it — the whole point of #3.
    await enterSketch(page, "XY");
    await sketchRectangle(page);

    // The Extrude action lights up once a sketch has solved.
    const extrudeAction = page.getByTestId("new-extrude");
    await expect(extrudeAction).toBeEnabled();
    await extrudeAction.click();

    // The keyboard-first form: distance is focused at 10 mm; Enter creates.
    const editor = page.getByTestId("extrude-editor");
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
    await expect(page.getByTestId("extrude-op-add")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.getByTestId("extrude-distance").press("Enter");

    // The body renders and its mass properties reach the inspector; the
    // z-extent equals the 10 mm distance.
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expectRenderedBody(page);
    expect(await bodyDepth(page)).toBeCloseTo(10, 3);
    const volume10 = await bodyVolume(page);

    // Edit the extrude: select its tree row, retarget the editor, 10 → 25.
    await page.getByTestId("feature-select-1").click();
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
    await page.getByTestId("extrude-distance").fill("25");
    await page.getByTestId("extrude-distance").press("Enter");

    // The body updates live — deeper solid, larger volume.
    await expect
      .poll(() => bodyDepth(page), { timeout: 30_000 })
      .toBeCloseTo(25, 3);
    await expectRenderedBody(page);
    expect(await bodyVolume(page)).toBeGreaterThan(volume10);

    // Roll the bar back before the extrude: the body disappears, the sketch
    // returns — the pre-extrude state, extrude marked rolled back (not deleted).
    await page.getByTestId("rollback-slot-0").click();
    await expect(page.getByTestId("body-inspector")).toBeHidden({
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-row").nth(1)).toHaveAttribute(
      "data-rolled-back",
      "true",
    );
    await expect(page.getByTestId("rollback-slot-0")).toHaveAttribute(
      "data-active",
      "true",
    );
    // Both features persist through the roll-back (nothing was destroyed).
    await expect(page.getByTestId("feature-row")).toHaveCount(2);

    // Roll forward to the tip: the body comes back.
    await page.getByTestId("rollback-slot-1").click();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expectRenderedBody(page);
  });

  test("unclosed profile surfaces profile_not_closed in the tree", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Open profile");
    await page.goto(`/parts/${part.id}`);

    // An open two-line path (not a closed loop) — a valid sketch, but no face.
    await enterSketch(page, "XY");
    await page.keyboard.press("l");
    await page.mouse.click(640, 620);
    await page.mouse.click(940, 620);
    await page.mouse.click(940, 620);
    await page.mouse.click(940, 420);
    await expect(page.getByTestId("sketch-save")).toContainText("2 entities");
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // Extrude the open profile — the create succeeds, the rebuild fails.
    await page.getByTestId("new-extrude").click();
    await page.getByTestId("extrude-distance").press("Enter");

    // The failure is loud and located: the extrude row flags ERR, the tree
    // solve summary fails, and the reason prints under the row — never silent.
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    const error = page.getByTestId("feature-error-1");
    await expect(error).toBeVisible();
    await expect(error).toContainText("profile_not_closed");
    // No blank-viewport crash: the sketch still renders behind the failure.
    await expect(page.getByTestId("body-inspector")).toBeHidden({
      timeout: 30_000,
    });
  });

  test("founder screenshot: extrude form + body + rollback bar (desktop)", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Extrude plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    await sketchRectangle(page);
    await page.getByTestId("new-extrude").click();
    await page.getByTestId("extrude-distance").press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expectRenderedBody(page);
    // Re-open the editor on the extrude so the form, the body, and the tree's
    // rollback bar are all in one frame.
    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/extrude-ui-desktop.png` });
  });
});

test.describe("extrude authoring small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("form + tree stay usable at laptop width; founder screenshot", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Extrude plate");
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
    await page.getByTestId("extrude-distance").press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expectRenderedBody(page);

    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(560);

    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/extrude-ui-laptop.png` });
  });
});
