import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * BACKLOG #2b: the offset / datum-plane picker UI. Real stack (gateway +
 * documents + geometry, no mocks). The load-bearing proof: a sketch authored on
 * an XY offset +30 plane, extruded 10 mm, produces a body that sits at
 * z ≈ 30..40 — the offset actually applied end-to-end, DOM math and kernel
 * agreeing. The plain one-click XY path is checked unchanged in the same file.
 */

/** The lit aluminium solid + B-rep edges paint far more shades than ground. */
async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/** The z component (last number) of a bounding-box / centroid readout cell. */
async function cellZ(page: Page, testid: string): Promise<number> {
  const text = await page.getByTestId(testid).innerText();
  const nums = text.match(/-?\d+(?:\.\d+)?/g) ?? [];
  return nums.length > 0
    ? Number.parseFloat(nums[nums.length - 1] as string)
    : NaN;
}

/** The z-extent (last number) of the extents cell — an XY extrude's distance. */
async function bodyDepth(page: Page): Promise<number> {
  const extents = await page.getByTestId("prop-extents").innerText();
  const parts = extents.split("×").map((p) => Number.parseFloat(p.trim()));
  return parts[parts.length - 1] ?? NaN;
}

/** Author an offset datum `offsetMm` above XY via the standalone Datum tool. */
async function authorOffsetDatum(
  page: Page,
  offsetMm: number,
  expectName: string,
): Promise<void> {
  await page.getByTestId("tool-datum").click();
  await expect(page.getByTestId("datum-editor")).toBeVisible();
  // Offset is the default kind; just set the distance and commit.
  await page.getByTestId("datum-offset").fill(String(offsetMm));
  const write = page.waitForResponse(
    (r) => r.url().includes("/features") && r.request().method() === "POST",
  );
  await page.getByTestId("datum-submit").click();
  expect((await write).status()).toBe(201);
  await expect(
    page.getByTestId("feature-row").filter({ hasText: expectName }),
  ).toBeVisible();
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
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** Extrude the solved profile 10 mm through the UI and wait for the body. */
async function extrudeTenMm(page: Page): Promise<void> {
  await expect(page.getByTestId("new-extrude")).toBeEnabled();
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
  await page.getByTestId("extrude-distance").press("Enter");
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
  await expectRenderedBody(page);
}

test.describe("offset datum plane", () => {
  test("sketch on XY +30 → extrude → body sits at z ≈ 30..40", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Raised boss");
    await page.goto(`/parts/${part.id}`);

    // Enter sketch mode; the three origin planes are still the one-click choice.
    await page.getByTestId("new-sketch").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("Pick a plane");
    await expect(page.getByTestId("plane-XY")).toBeVisible();

    // Author an offset plane inline: base XY (default), +30 mm. Creating it
    // POSTs a datum feature, then starts the sketch on it via a FeatureRef.
    await page.getByTestId("datum-offset-plane").click();
    await expect(page.getByTestId("offset-plane-panel")).toBeVisible();
    await page.getByTestId("offset-plane-offset").fill("30");
    const datumWrite = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/features`) &&
        r.request().method() === "POST",
    );
    await page.getByTestId("offset-plane-confirm").click();
    expect((await datumWrite).status()).toBe(201);

    // The sketcher is now on the offset plane — the DRO/strip say so.
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY +30", {
      timeout: 15_000,
    });
    await expect(page.getByTestId("dro-plane")).toHaveText("XY +30");

    // The datum feature landed in the tree as its own row.
    await expect(page.getByTestId("feature-row")).toContainText("Plane1");

    // Draw + extrude through the UI.
    await sketchRectangleAndSave(page);
    await extrudeTenMm(page);

    // THE PROOF: the body sits at the offset. Bounding box z spans 30..40 and
    // the centroid z is the midpoint (35); the extrude depth is still 10.
    expect(await bodyDepth(page)).toBeCloseTo(10, 3);
    expect(await cellZ(page, "prop-bbox-min")).toBeCloseTo(30, 2);
    expect(await cellZ(page, "prop-bbox-max")).toBeCloseTo(40, 2);
    expect(await cellZ(page, "prop-centroid")).toBeCloseTo(35, 2);

    // Reload: the sketch-on-datum re-resolves through the real API, body holds.
    await page.reload();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    expect(await cellZ(page, "prop-bbox-min")).toBeCloseTo(30, 2);
    expect(await cellZ(page, "prop-bbox-max")).toBeCloseTo(40, 2);
  });

  test("plain one-click XY path is unchanged (body at z ≈ 0..10)", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Base plate");
    await page.goto(`/parts/${part.id}`);

    // One click: the XY origin datum — no offset ceremony.
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");

    await sketchRectangleAndSave(page);
    await extrudeTenMm(page);

    // The body sits on the base plane, exactly as before this feature.
    expect(await bodyDepth(page)).toBeCloseTo(10, 3);
    expect(await cellZ(page, "prop-bbox-min")).toBeCloseTo(0, 2);
    expect(await cellZ(page, "prop-bbox-max")).toBeCloseTo(10, 2);
    // The tree has just the sketch + extrude — no stray datum feature.
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
  });

  test("standalone Datum tool authors a reusable plane in the tree", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Datum library");
    await page.goto(`/parts/${part.id}`);

    // The feature-toolbar Datum tool creates a standalone datum feature.
    await page.getByTestId("tool-datum").click();
    await expect(page.getByTestId("datum-editor")).toBeVisible();
    await page.getByTestId("datum-offset").fill("20");
    await page.getByTestId("datum-submit").click();
    await expect(page.getByTestId("feature-row")).toContainText("Plane1");

    // It is then offered in the plane picker for reuse by a new sketch.
    await page.getByTestId("new-sketch").click();
    await expect(page.locator('[data-testid^="plane-datum-"]')).toBeVisible();
  });
});

test.describe("datum kinds — midplane + offset chaining", () => {
  test("midplane between XY and an offset datum → sketch → body z ≈ 20..30", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Web bracket");
    await page.goto(`/parts/${part.id}`);

    // Plane1: an offset datum 40 mm above XY (the second midplane reference).
    await authorOffsetDatum(page, 40, "Plane1");

    // Plane2: the midplane between the XY origin datum and Plane1 — the founder's
    // "mid point plane". Parallel references → the plane midway between them
    // (z = 20). Authored entirely from dropdown sides (no picking).
    await page.getByTestId("tool-datum").click();
    await expect(page.getByTestId("datum-editor")).toBeVisible();
    await page.getByTestId("datum-kind").selectOption("midplane");
    await page.getByTestId("datum-side-a").selectOption({ label: "XY datum" });
    await page.getByTestId("datum-side-b").selectOption({ label: "Plane1" });
    await expect(page.getByTestId("datum-submit")).toBeEnabled();
    const midWrite = page.waitForResponse(
      (r) => r.url().includes("/features") && r.request().method() === "POST",
    );
    await page.getByTestId("datum-submit").click();
    expect((await midWrite).status()).toBe(201);
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Plane2" }),
    ).toBeVisible();

    // A sketch CAN sit on the midplane: it's offered in the plane picker's
    // in-tree reuse, and the DRO names it.
    await page.getByTestId("new-sketch").click();
    await page
      .getByTestId("sketch-strip")
      .getByRole("button", { name: "Sketch on Plane2" })
      .click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On Plane2", {
      timeout: 15_000,
    });

    await sketchRectangleAndSave(page);
    await extrudeTenMm(page);

    // THE PROOF: the midplane resolves to z = 20 server-side, so the extruded
    // body spans z ≈ 20..30 — the client authoring and the kernel agreeing.
    expect(await bodyDepth(page)).toBeCloseTo(10, 3);
    expect(await cellZ(page, "prop-bbox-min")).toBeCloseTo(20, 2);
    expect(await cellZ(page, "prop-bbox-max")).toBeCloseTo(30, 2);
  });

  test("offset_from another datum (chaining) → sketch → body z ≈ 30..40", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Chained datum");
    await page.goto(`/parts/${part.id}`);

    // Plane1: XY + 40. Plane2: offset FROM Plane1 by −10 → z = 30 (the chain).
    await authorOffsetDatum(page, 40, "Plane1");

    await page.getByTestId("tool-datum").click();
    await expect(page.getByTestId("datum-editor")).toBeVisible();
    await page.getByTestId("datum-kind").selectOption("offset_from");
    await page
      .getByTestId("datum-base-plane")
      .selectOption({ label: "Plane1" });
    await page.getByTestId("datum-offset").fill("-10");
    await expect(page.getByTestId("datum-submit")).toBeEnabled();
    const chainWrite = page.waitForResponse(
      (r) => r.url().includes("/features") && r.request().method() === "POST",
    );
    await page.getByTestId("datum-submit").click();
    expect((await chainWrite).status()).toBe(201);
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Plane2" }),
    ).toBeVisible();

    await page.getByTestId("new-sketch").click();
    await page
      .getByTestId("sketch-strip")
      .getByRole("button", { name: "Sketch on Plane2" })
      .click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On Plane2", {
      timeout: 15_000,
    });

    await sketchRectangleAndSave(page);
    await extrudeTenMm(page);

    // The chain resolves to z = 30, so the body spans z ≈ 30..40.
    expect(await cellZ(page, "prop-bbox-min")).toBeCloseTo(30, 2);
    expect(await cellZ(page, "prop-bbox-max")).toBeCloseTo(40, 2);
  });
});

test.describe("offset datum plane — founder screenshots", () => {
  test("picker with the offset affordance + a raised body (desktop)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1512, height: 945 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Raised boss");
    await page.goto(`/parts/${part.id}`);

    // The plane picker showing the three origin planes + the offset panel open.
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("datum-offset-plane").click();
    await expect(page.getByTestId("offset-plane-panel")).toBeVisible();
    await page.getByTestId("offset-plane-offset").fill("30");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/datum-plane-picker-desktop.png`,
    });

    // Author the plane, sketch on it (grid visibly at height), extrude.
    await page.getByTestId("offset-plane-confirm").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY +30", {
      timeout: 15_000,
    });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/datum-plane-sketch-desktop.png`,
    });

    await sketchRectangleAndSave(page);
    await extrudeTenMm(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/datum-plane-body-desktop.png`,
    });
  });

  test("offset picker + raised body at small laptop (1280×800)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Raised boss");
    await page.goto(`/parts/${part.id}`);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("datum-offset-plane").click();
    await page.getByTestId("offset-plane-offset").fill("30");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/datum-plane-picker-laptop.png`,
    });
    await page.getByTestId("offset-plane-confirm").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY +30", {
      timeout: 15_000,
    });
    await sketchRectangleAndSave(page);
    await extrudeTenMm(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/datum-plane-body-laptop.png`,
    });
  });
});

test.describe("datum kinds — founder screenshots", () => {
  /** Open the datum editor on a midplane over XY + Plane1 (dropdown sides). */
  async function openMidplaneEditor(page: Page): Promise<void> {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Web bracket");
    await page.goto(`/parts/${part.id}`);
    await authorOffsetDatum(page, 40, "Plane1");
    await page.getByTestId("tool-datum").click();
    await expect(page.getByTestId("datum-editor")).toBeVisible();
    await page.getByTestId("datum-kind").selectOption("midplane");
    await page.getByTestId("datum-side-a").selectOption({ label: "XY datum" });
    await page.getByTestId("datum-side-b").selectOption({ label: "Plane1" });
    await expect(page.getByTestId("datum-submit")).toBeEnabled();
  }

  test("midplane editor (desktop 1440×900)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openMidplaneEditor(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/datum-midplane-desktop.png`,
    });
  });

  test("midplane editor (small laptop 1280×800)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await openMidplaneEditor(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/datum-midplane-laptop.png`,
    });
  });
});
