import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * (P2) Datum editor — midplane FACE-sides + `on_face` authoring. Real stack
 * (gateway + documents + geometry, no mocks). The editor-side pick integration:
 * the standalone DatumEditor arms the SAME FacePickOverlay the sketch-on-face
 * flow uses, and a clicked planar face becomes an `on_face` datum base or a
 * midplane FACE-side. The load-bearing proof is server-side: each authored
 * datum EVALUATES to "Solved" (the kernel resolved the picked face's stage-1
 * signature — a wrong anchor or malformed signature would be an ERR row), and
 * survives a reload. The deterministic on_face basis itself is proven
 * geometrically by sketch-on-face.spec, which seats a sketch on the same
 * `on_face` datum params this editor authors.
 */

/** The lit aluminium solid + B-rep edges paint far more shades than ground. */
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

/**
 * Click the body's TOP face node in the datum face-pick overlay. Faces are
 * identified by their OCCT centroid in the pick node's accessible name; the top
 * face has the greatest z (10 for a 10 mm box) — deterministic, no reliance on
 * screen projection or a transient face index.
 */
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

test.describe("datum editor — pick a model face", () => {
  test("on_face datum from a picked face resolves + persists", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Face datum");
    await page.goto(`/parts/${part.id}`);

    await buildBaseBox(page);

    // Open the standalone Datum tool and choose the On-a-face kind.
    await page.getByTestId("tool-datum").click();
    await expect(page.getByTestId("datum-editor")).toBeVisible();
    await page.getByTestId("datum-kind").selectOption("on_face");
    await expect(page.getByTestId("datum-on-face-empty")).toHaveText(
      "No face chosen",
    );
    // No face yet → Create is blocked.
    await expect(page.getByTestId("datum-submit")).toBeDisabled();

    // Arm the pick: the body's six planar faces light up in the viewport.
    await page.getByTestId("datum-on-face-pick").click();
    await expect(page.getByTestId("datum-on-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.locator('[data-testid^="plane-pick-face-"]')).toHaveCount(
      6,
    );

    // Click the top face → it folds into the base slot, the pick disarms, and
    // the chip names where it sits (z = 10, the top of a 10 mm box).
    await clickTopFace(page);
    await expect(page.getByTestId("datum-on-face")).toContainText("10");
    await expect(page.getByTestId("datum-on-face-pick")).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    // Commit → an on_face datum POSTs and lands as its own tree row.
    const write = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/features`) &&
        r.request().method() === "POST",
    );
    await expect(page.getByTestId("datum-submit")).toBeEnabled();
    await page.getByTestId("datum-submit").click();
    expect((await write).status()).toBe(201);
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Plane1" }),
    ).toBeVisible();

    // THE PROOF: the kernel resolved the picked face's signature — the datum
    // evaluates cleanly (a bad reference would be an ERR row + "Failed").
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toHaveCount(0);

    // Reload: the on_face datum re-resolves through the real API and holds.
    await page.reload();
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Plane1" }),
    ).toBeVisible();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
  });

  test("midplane with a picked FACE side resolves", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Face midplane");
    await page.goto(`/parts/${part.id}`);

    await buildBaseBox(page);

    // Midplane between the XY origin datum (z = 0) and the picked TOP face
    // (z = 10) — a parallel pair whose midplane sits at z = 5.
    await page.getByTestId("tool-datum").click();
    await expect(page.getByTestId("datum-editor")).toBeVisible();
    await page.getByTestId("datum-kind").selectOption("midplane");
    await page.getByTestId("datum-side-a").selectOption({ label: "XY datum" });

    // Side B is a picked model face — arm its pick, click the top face.
    await page.getByTestId("datum-side-b-pick").click();
    await expect(page.getByTestId("datum-side-b-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.locator('[data-testid^="plane-pick-face-"]')).toHaveCount(
      6,
    );
    await clickTopFace(page);
    // The dropdown is swapped for the picked-face chip.
    await expect(page.getByTestId("datum-side-b-face")).toContainText("10");

    const write = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/features`) &&
        r.request().method() === "POST",
    );
    await expect(page.getByTestId("datum-submit")).toBeEnabled();
    await page.getByTestId("datum-submit").click();
    expect((await write).status()).toBe(201);
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Plane1" }),
    ).toBeVisible();

    // THE PROOF: the kernel resolved the FACE side of the midplane — clean eval.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
  });

  test("Escape disarms an armed datum face pick, editor stays open", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Cancel pick");
    await page.goto(`/parts/${part.id}`);

    await buildBaseBox(page);

    await page.getByTestId("tool-datum").click();
    await page.getByTestId("datum-kind").selectOption("on_face");
    await page.getByTestId("datum-on-face-pick").click();
    await expect(page.locator('[data-testid^="plane-pick-face-"]')).toHaveCount(
      6,
    );

    // Escape disarms the pick — the highlights clear, the editor stays open.
    await page.keyboard.press("Escape");
    await expect(page.locator('[data-testid^="plane-pick-face-"]')).toHaveCount(
      0,
    );
    await expect(page.getByTestId("datum-editor")).toBeVisible();
    await expect(page.getByTestId("datum-on-face-pick")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });
});

test.describe("datum editor — face pick founder screenshots", () => {
  async function pickedFaceEditor(page: Page, part: { id: string }) {
    await page.goto(`/parts/${part.id}`);
    await buildBaseBox(page);
    await page.getByTestId("tool-datum").click();
    await page.getByTestId("datum-kind").selectOption("on_face");
    await page.getByTestId("datum-on-face-pick").click();
    await expect(
      page.locator('[data-testid^="plane-pick-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
  }

  /**
   * Click the face node furthest from the top-left corner — the editor panel is
   * anchored there, so the bottom-right-most node is reliably UNOCCLUDED at any
   * viewport (the top face can project behind the panel on a short laptop). The
   * founder shot only needs a populated face chip, not a specific face.
   */
  async function clickUnoccludedFace(page: Page): Promise<void> {
    const nodes = page.locator('[data-testid^="plane-pick-face-"]');
    await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
    const count = await nodes.count();
    let bestScore = -Infinity;
    let bestIndex = 0;
    for (let i = 0; i < count; i += 1) {
      const box = await nodes.nth(i).boundingBox();
      if (box === null) continue;
      const score = box.x + box.y; // furthest from the top-left panel
      if (score > bestScore) {
        bestScore = score;
        bestIndex = i;
      }
    }
    await nodes.nth(bestIndex).click();
  }

  test("on_face pick + editor (desktop 1440×900)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Face datum shot");
    await pickedFaceEditor(page, part);
    // The armed pick: faces highlighted + the editor's face slot.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/datum-on-face-pick-desktop.png`,
    });
    await clickUnoccludedFace(page);
    await expect(page.getByTestId("datum-on-face")).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/datum-on-face-picked-desktop.png`,
    });
  });

  test("on_face pick + editor (small laptop 1280×800)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Face datum shot");
    await pickedFaceEditor(page, part);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/datum-on-face-pick-laptop.png`,
    });
    await clickUnoccludedFace(page);
    await expect(page.getByTestId("datum-on-face")).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/datum-on-face-picked-laptop.png`,
    });
  });
});
