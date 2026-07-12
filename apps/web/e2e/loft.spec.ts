import { expect, test, type Page } from "@playwright/test";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * BACKLOG #8: the loft authoring UI, driven through the real browser against
 * the real stack (gateway + documents + geometry, no mocks). Loft is the first
 * feature that references an ORDERED LIST of ≥2 earlier sketches, blended in
 * order. The payoff — unblocked by offset datum planes (commit 125672f) — is
 * two PARALLEL circular sections (one on XY, one on an XY +30 offset plane
 * authored through the "+ Offset plane" flow) skinned into a real blended body
 * (a frustum). Everything is authored in-UI: draw both sections, pick them in
 * the ordered section stack, create → the lofted solid renders and the feature
 * lands in the tree.
 */

/** The lit aluminium solid + B-rep edges paint far more shades than ground. */
async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/** Draw a circle (centre click + radius click) with the circle tool. */
async function drawCircle(
  page: Page,
  cx: number,
  cy: number,
  radiusX: number,
): Promise<void> {
  await page.keyboard.press("c");
  await expect(page.getByTestId("tool-circle")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(cx, cy);
  await page.mouse.click(radiusX, cy);
}

/** Persist the current sketch and wait for the solve to land. */
async function saveSketch(page: Page): Promise<void> {
  const save = page.getByTestId("sketch-save");
  await expect(save).toBeEnabled();
  await save.click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/**
 * Author two PARALLEL circular sections in-UI: a wide circle on XY and a
 * narrower circle on an XY +30 offset plane (the "+ Offset plane" flow). Leaves
 * a tree of Sketch1 / Plane1 / Sketch2, both sketches solved.
 */
async function authorTwoParallelSections(page: Page): Promise<void> {
  // Section 1: a wide circle on the XY origin plane.
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await drawCircle(page, 770, 430, 910);
  await saveSketch(page);

  // Section 2: a narrower circle on an XY +30 offset plane, authored inline.
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("datum-offset-plane").click();
  await expect(page.getByTestId("offset-plane-panel")).toBeVisible();
  await page.getByTestId("offset-plane-offset").fill("30");
  await page.getByTestId("offset-plane-confirm").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY +30", {
    timeout: 15_000,
  });
  await drawCircle(page, 770, 430, 840);
  await saveSketch(page);
}

/** POST one feature at the tree tip via the real gateway (error-case seeding). */
async function createFeature(
  page: Page,
  token: string,
  partId: string,
  body: unknown,
): Promise<void> {
  const response = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: body,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e create feature failed: ${response.status()} ${await response.text()}`,
    );
  }
}

/** A closed circle section sketch on `plane`, referenced by the loft. */
function circleSectionParams(plane: unknown, radius: number): unknown {
  return {
    plane,
    entities: [{ id: "c1", kind: "circle", center: { x: 0, y: 0 }, radius }],
    constraints: [],
  };
}

test.describe("loft authoring", () => {
  test("two parallel sections (XY + XY +30) → lofted body renders and lands in the tree", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Adapter");
    await page.goto(`/parts/${part.id}`);

    await authorTwoParallelSections(page);

    // Loft lights up once two sketch sections have solved.
    const loftAction = page.getByTestId("new-loft");
    await expect(loftAction).toBeEnabled({ timeout: 30_000 });
    await loftAction.click();

    // The ordered section stack defaults to the two sketches (Section 01 =
    // Sketch1, Section 02 = Sketch2), add selected. Create skins the frustum.
    const editor = page.getByTestId("loft-editor");
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("loft-section-row")).toHaveCount(2);
    await expect(page.getByTestId("loft-op-add")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("loft-section-0")).toHaveValue(/./);
    await expect(page.getByTestId("loft-section-1")).toHaveValue(/./);
    await page.getByTestId("loft-submit").click();

    // The lofted solid renders and lands as its own row (Sketch1 / Plane1 /
    // Sketch2 / Loft1) — a real body from the evaluate→mesh path.
    await expect(page.getByTestId("feature-row")).toHaveCount(4);
    await expect(page.getByTestId("feature-row").last()).toContainText("loft");
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expectRenderedBody(page);

    // The loft is editable: its row re-opens the editor with its sections
    // seeded in order.
    await page.getByTestId("feature-select-3").click();
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("loft-section-row")).toHaveCount(2);
    await expect(page.getByTestId("loft-section-0")).toHaveValue(/./);
  });

  test("an unfilled section keeps the loft from submitting", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Guarded loft");
    // Seed two closed circle sketches straight through the gateway — the guard
    // under test is pure UI (no geometry needs to succeed).
    await createFeature(page, account.token, part.id, {
      name: "Sketch1",
      feature: {
        type: "sketch",
        version: 1,
        params: circleSectionParams({ kind: "datum_plane", plane: "XY" }, 8),
      },
      expected_tree_version: 0,
    });
    await createFeature(page, account.token, part.id, {
      name: "Sketch2",
      feature: {
        type: "sketch",
        version: 1,
        params: circleSectionParams({ kind: "datum_plane", plane: "XZ" }, 5),
      },
      expected_tree_version: 1,
    });
    await page.goto(`/parts/${part.id}`);

    await expect(page.getByTestId("new-loft")).toBeEnabled({ timeout: 30_000 });
    await page.getByTestId("new-loft").click();
    await expect(page.getByTestId("loft-editor")).toBeVisible();

    // Two seeded sections → submit is live. The note is honest about scope.
    await expect(page.getByTestId("loft-submit")).toBeEnabled();
    await expect(page.getByTestId("loft-note")).toContainText("order");
    // With only two rows, neither can be removed below the minimum.
    await expect(page.getByTestId("loft-section-remove-0")).toBeDisabled();

    // Add a third, UNFILLED section → the loft can't submit an incomplete
    // stack. Removing it restores the valid two-section loft.
    await page.getByTestId("loft-add-section").click();
    await expect(page.getByTestId("loft-section-row")).toHaveCount(3);
    await expect(page.getByTestId("loft-section-2")).toHaveValue("");
    await expect(page.getByTestId("loft-submit")).toBeDisabled();

    await page.getByTestId("loft-section-remove-2").click();
    await expect(page.getByTestId("loft-section-row")).toHaveCount(2);
    await expect(page.getByTestId("loft-submit")).toBeEnabled();
  });

  test("founder screenshot: lofted body + loft editor (desktop)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1512, height: 945 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Adapter");
    await page.goto(`/parts/${part.id}`);

    await authorTwoParallelSections(page);

    // BEFORE: the two parallel section sketches in space, the ordered section
    // stack open pre-submit — the authoring moment.
    await page.getByTestId("new-loft").click();
    await expect(page.getByTestId("loft-editor")).toBeVisible();
    await expect(page.getByTestId("loft-section-row")).toHaveCount(2);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/loft-before-desktop.png`,
    });

    // AFTER: create the loft; the frustum skins through the two sections.
    await page.getByTestId("loft-submit").click();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expectRenderedBody(page);

    // Re-open the editor on the loft so the ordered section stack, the body,
    // and the tree are all in one frame.
    await page.getByTestId("feature-select-3").click();
    await expect(page.getByTestId("loft-editor")).toBeVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/loft-desktop.png` });
  });
});

test.describe("loft authoring small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("stack + tree stay usable at laptop width; founder screenshot", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Adapter");
    await page.goto(`/parts/${part.id}`);

    await authorTwoParallelSections(page);
    await page.getByTestId("new-loft").click();
    await page.getByTestId("loft-submit").click();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expectRenderedBody(page);

    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(560);

    await page.getByTestId("feature-select-3").click();
    await expect(page.getByTestId("loft-editor")).toBeVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/loft-laptop.png` });
  });
});
