import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Hole feature (slice 1) — face-placed cylindrical drill, through-all. Real
 * stack (gateway + documents + geometry, no mocks). The whole authoring loop is
 * exercised in the UI: build a base box, open the Hole command, PICK the top
 * face (the SAME FacePickOverlay the on_face datum uses), PICK the drill point
 * on it (the DOM-in-canvas point affordance the measure overlay uses), set the
 * diameter, and drill.
 *
 * The load-bearing proof is server-side: the Hole feature EVALUATES to "Solved"
 * (the kernel resolved the picked face's stage-1 signature, projected the point,
 * and the cut boolean removed material — an off-body / too-deep / unresolved
 * pick would be an ERR row + "Failed"), the body RE-RENDERS with the bore, and
 * it survives a reload.
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
 * Click the body's TOP face node (greatest z in the pick-node accessible name)
 * — deterministic, no reliance on screen projection or a transient face index.
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

test.describe("hole — drill a through-all hole in the UI", () => {
  test("pick a face, pick a point, drill → the body shows the hole", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Drilled plate");
    await page.goto(`/parts/${part.id}`);

    await buildBaseBox(page);

    // Open the Hole command — enabled once a body exists (canModify).
    await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    // No face yet → Create is blocked.
    await expect(page.getByTestId("hole-face-empty")).toHaveText(
      "No face chosen",
    );
    await expect(page.getByTestId("hole-submit")).toBeDisabled();

    // Arm the face pick: the body's six planar faces light up.
    await page.getByTestId("hole-face-pick").click();
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.locator('[data-testid^="plane-pick-face-"]')).toHaveCount(
      6,
    );

    // Click the top face (z = 10) → it folds in, the pick disarms, and the drill
    // point seeds to the face centre — the form is now submittable.
    await clickTopFace(page);
    await expect(page.getByTestId("hole-face")).toContainText("10");
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await expect(page.getByTestId("hole-position")).toContainText(
      "Centre of face",
    );

    // Refine the drill point IN the viewport: arm the point pick and click the
    // face centre node (the DOM-in-canvas point affordance).
    await page.getByTestId("hole-point-pick").click();
    await expect(page.getByTestId("hole-point-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("hole-point-center")).toBeVisible({
      timeout: 20_000,
    });
    await page.getByTestId("hole-point-center").click();
    await expect(page.getByTestId("hole-position")).toContainText("mm");

    // Diameter default Ø6, through-all default. Drill.
    await expect(page.getByTestId("hole-diameter")).toHaveValue("6");
    const write = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/features`) &&
        r.request().method() === "POST",
    );
    await expect(page.getByTestId("hole-submit")).toBeEnabled();
    await page.getByTestId("hole-submit").click();
    expect((await write).status()).toBe(201);

    // The Hole lands as its own tree row.
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Hole1" }),
    ).toBeVisible();

    // THE PROOF: the kernel drilled cleanly — the tree evaluates to Solved (an
    // off-body / too-deep / unresolved pick would be an ERR row), and the body
    // re-renders with the bore.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
    await expectRenderedBody(page);

    // Reload: the hole re-resolves through the real API and holds.
    await page.reload();
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Hole1" }),
    ).toBeVisible();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
  });

  test("a face-based feature AFTER the hole anchors to the hole body", async ({
    page,
  }) => {
    // The mis-anchor guard: `lastBodyFeatureId` must return the HOLE (not the
    // pre-hole extrude) as the anchor for the next face pick. A through-all hole
    // reshapes the top face into an annulus, so a datum on that face carries the
    // HOLE body's signature — anchored to the hole it resolves; anchored to the
    // extrude (the bug this fixes) it would be `subshape_unresolved` → "Failed".
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Anchor check");
    await page.goto(`/parts/${part.id}`);

    await buildBaseBox(page);

    // Drill a through-all hole (Ø6, centre of the top face).
    await page.getByTestId("new-hole").click();
    await page.getByTestId("hole-face-pick").click();
    await clickTopFace(page);
    await expect(page.getByTestId("hole-face")).toContainText("10");
    await page.getByTestId("hole-submit").click();
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Hole1" }),
    ).toBeVisible();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // Now author a datum ON the (reshaped) top face — its pick anchors to the
    // last body-affecting feature, which MUST be the hole.
    await page.getByTestId("tool-datum").click();
    await page.getByTestId("datum-kind").selectOption("on_face");
    await page.getByTestId("datum-on-face-pick").click();
    await clickTopFace(page);
    await expect(page.getByTestId("datum-on-face")).toContainText("10");
    await page.getByTestId("datum-submit").click();
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Plane1" }),
    ).toBeVisible();

    // THE PROOF: the datum resolved against the HOLE body (correct anchor) — the
    // tree stays Solved and the datum row (index 3: sketch, extrude, hole, datum)
    // carries no error. A mis-anchor to the extrude would fail this row.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-3")).toHaveCount(0);
  });

  test("blind depth field appears and drills", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Blind hole");
    await page.goto(`/parts/${part.id}`);

    await buildBaseBox(page);

    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    await page.getByTestId("hole-face-pick").click();
    await clickTopFace(page);
    await expect(page.getByTestId("hole-face")).toContainText("10");

    // Switch to Blind → the depth field appears; a 4 mm pocket into a 10 mm box.
    await page.getByTestId("hole-depth-blind").click();
    await expect(page.getByTestId("hole-blind-depth")).toBeVisible();
    await page.getByTestId("hole-blind-depth").fill("4");

    const write = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/features`) &&
        r.request().method() === "POST",
    );
    await expect(page.getByTestId("hole-submit")).toBeEnabled();
    await page.getByTestId("hole-submit").click();
    expect((await write).status()).toBe(201);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
  });
});

test.describe("hole — founder screenshots", () => {
  async function armedHoleEditor(page: Page, part: { id: string }) {
    await page.goto(`/parts/${part.id}`);
    await buildBaseBox(page);
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    await page.getByTestId("hole-face-pick").click();
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

  test("hole authoring (desktop 1440×900)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Hole shot");
    await armedHoleEditor(page, part);
    // The armed face pick: faces highlighted + the Hole editor.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/hole-face-pick-desktop.png`,
    });
    await clickUnoccludedFace(page);
    await expect(page.getByTestId("hole-face")).toBeVisible();
    await page.getByTestId("hole-point-pick").click();
    await expect(page.getByTestId("hole-point-center")).toBeVisible({
      timeout: 20_000,
    });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/hole-authoring-desktop.png`,
    });
  });

  test("hole authoring (small laptop 1280×800)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Hole shot");
    await armedHoleEditor(page, part);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/hole-face-pick-laptop.png`,
    });
    await clickUnoccludedFace(page);
    await expect(page.getByTestId("hole-face")).toBeVisible();
    await page.getByTestId("hole-point-pick").click();
    await expect(page.getByTestId("hole-point-center")).toBeVisible({
      timeout: 20_000,
    });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/hole-authoring-laptop.png`,
    });
  });
});
