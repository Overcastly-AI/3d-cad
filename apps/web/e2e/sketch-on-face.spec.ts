import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * BACKLOG #1 (UI leg): sketch on a picked model face. Real stack (gateway +
 * documents + geometry, no mocks). The daily-driver payoff: extrude a base box,
 * "Pick a face" → click its TOP face → draw a rectangle → extrude (add) → a boss
 * sits on top at z ≈ 10..20. That the boss lands at the RIGHT height proves the
 * whole chain: the `on_face` datum resolved the picked face, and the sketch
 * basis the UI reconstructed from the face signature agreed with the kernel's
 * `resolve_sketch_plane` (drew where the server built).
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

/** The z-extent (last number) of the extents cell — the body's total height. */
async function bodyDepth(page: Page): Promise<number> {
  const extents = await page.getByTestId("prop-extents").innerText();
  const parts = extents.split("×").map((p) => Number.parseFloat(p.trim()));
  return parts[parts.length - 1] ?? NaN;
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
  // The strip closes only after the sketch solve round-trips back — 30s (matches
  // the sibling eval-status wait) so a slow solve under CPU load holds.
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** Draw a SMALLER rectangle near the face centre — a boss that steps up. */
async function sketchBossAndSave(page: Page): Promise<void> {
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(740, 470);
  await page.mouse.move(900, 590);
  await page.mouse.click(900, 590);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.getByTestId("sketch-save").click();
  // The strip closes only after the sketch solve round-trips back — 30s (matches
  // the sibling eval-status wait) so a slow solve under CPU load holds.
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** Extrude the solved profile 10 mm through the UI and wait for the body. */
async function extrudeTenMm(page: Page): Promise<void> {
  // Extrude enables only once the sketch solve round-trips back (canExtrude =
  // hasSolvedSketch) — 30s so a slow solve under load isn't misread as broken.
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

/**
 * Wait until the BOSS body has re-meshed and rendered — `extrudeTenMm` only
 * proves *a* body is up (the base box still shows during the re-solve), so poll
 * the inspector until its max z clears the base (10) into the boss range (20).
 */
async function waitForBossBody(page: Page): Promise<void> {
  await expect
    .poll(() => cellZ(page, "prop-bbox-max"), { timeout: 20_000 })
    .toBeGreaterThan(19);
}

/** Build a 10 mm base box on XY, leaving a body with a top face at z = 10. */
async function buildBaseBox(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await sketchRectangleAndSave(page);
  await extrudeTenMm(page);
}

/** Everything the app is SAYING about the face pick, for a failure message. */
async function facePickReport(page: Page): Promise<string> {
  const read = async (testid: string): Promise<string> =>
    (await page.getByTestId(testid).allTextContents()).join(" | ").trim() ||
    "(absent)";
  return (
    `sketch-step="${await read("sketch-step")}" ` +
    `face-pick-prompt="${await read("face-pick-prompt")}" ` +
    `face-pick-error="${await read("face-pick-error")}" ` +
    `pick-nodes=${await page.locator('[data-testid^="plane-pick-face-"]').count()}`
  );
}

/**
 * Click the body's TOP face node. Faces are identified by their OCCT centroid
 * in the pick node's accessible name; the top face has the greatest z (10 for a
 * 10 mm box, vs. 5 for the sides and 0 for the base) — deterministic, no
 * reliance on screen projection or a transient face index.
 *
 * IT WAITS FOR THE DATUM WRITE, and that is not politeness (CI-4). A click here
 * starts a chain — `authorFacePlane` reads a tree version, POSTs an `on_face`
 * datum, awaits the refetch, then seats the sketch — and every caller used to
 * assert only the LAST link (`sketch-step` reads "On Face"). When that assertion
 * timed out in CI the message was `Expected "On Face", Received "Pick a plane"`,
 * which is true of all four ways the chain can break and evidence for none:
 * the click was never acted on; the POST was rejected; the app refused the pick
 * before writing (no body anchor); or the seating is merely slow. The three
 * that are FAULTS all leave a reading on screen — the prompt flips to "Placing
 * the sketch on the face…" the instant the click is received, and
 * `face-pick-error` carries the app's own refusal text — so a failure here now
 * reports which link broke instead of only that one did.
 *
 * The functional test already waited for this response; hoisting it into the
 * shared helper is why the two screenshot tests, which did not, were the ones
 * that failed unattributably.
 */
async function clickTopFace(page: Page, partId: string): Promise<void> {
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
  const datumWrite = page
    .waitForResponse(
      (r) =>
        r.url().includes(`/parts/${partId}/features`) &&
        r.request().method() === "POST",
      { timeout: 30_000 },
    )
    .catch(() => null);
  await nodes.nth(bestIndex).click();
  const response = await datumWrite;
  if (response === null) {
    throw new Error(
      `clickTopFace: the top face (z=${bestZ}, ${count} pickable) was clicked ` +
        "and no on_face datum POST followed within 30s — the app never acted " +
        `on the click. What it is showing: ${await facePickReport(page)}`,
    );
  }
  expect(
    response.status(),
    `the on_face datum write was rejected: ${await response
      .text()
      .catch(() => "(no body)")}`,
  ).toBe(201);
}

/**
 * The sketch seated on the picked face. Same assertion as before — this only
 * attaches the app's own account of itself when it fails.
 */
async function expectSeatedOnFace(page: Page): Promise<void> {
  try {
    await expect(page.getByTestId("sketch-step")).toHaveText("On Face", {
      timeout: 15_000,
    });
  } catch (failure) {
    throw new Error(
      "the on_face datum was written (201) and the sketcher never seated on " +
        `it. What the app is showing: ${await facePickReport(page)}. ` +
        `Original: ${failure instanceof Error ? failure.message : String(failure)}`,
    );
  }
}

test.describe("sketch on a model face", () => {
  test("pick the top face → boss adds on top at z ≈ 10..20", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Boss on a face");
    await page.goto(`/parts/${part.id}`);

    await buildBaseBox(page);

    // Re-enter sketch mode: "Pick a face" is now offered (a body exists).
    await page.getByTestId("new-sketch").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("Pick a plane");
    await expect(page.getByTestId("plane-pick-face")).toBeVisible();

    // Arm the face pick: the guide appears and the body's PLANAR faces light up.
    // A 10 mm box has exactly six planar faces (all pickable).
    await page.getByTestId("plane-pick-face").click();
    await expect(page.getByTestId("face-pick-prompt")).toBeVisible();
    await expect(page.locator('[data-testid^="plane-pick-face-"]')).toHaveCount(
      6,
    );

    // Click the top face → an on_face datum POSTs (asserted 201 in the helper),
    // the sketch seats on it.
    await clickTopFace(page, part.id);

    // The sketcher is now ON the face — the DRO/strip say so, a datum row lands.
    await expectSeatedOnFace(page);
    await expect(page.getByTestId("dro-plane")).toHaveText("Face");
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Plane1" }),
    ).toBeVisible();

    // Draw a smaller rectangle on the face and extrude (add) a boss.
    await sketchBossAndSave(page);
    await extrudeTenMm(page);
    await waitForBossBody(page);

    // THE PROOF: the boss sits ON the top face — the body now spans z 0..20
    // (base 0..10 + boss 10..20), so its total height is 20 and its max is 20.
    // A wrong plane basis (a side/bottom face, or a flipped normal) would land
    // the boss elsewhere and fail these.
    expect(await cellZ(page, "prop-bbox-min")).toBeCloseTo(0, 2);
    expect(await cellZ(page, "prop-bbox-max")).toBeCloseTo(20, 2);
    expect(await bodyDepth(page)).toBeCloseTo(20, 2);

    // Reload: the sketch-on-face re-resolves through the real API, body holds.
    await page.reload();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    expect(await cellZ(page, "prop-bbox-max")).toBeCloseTo(20, 2);
  });

  test("no body → the Pick a face affordance is not offered", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "No body yet");
    await page.goto(`/parts/${part.id}`);

    // A fresh part has no body, so a face pick has nothing to target.
    await page.getByTestId("new-sketch").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("Pick a plane");
    await expect(page.getByTestId("plane-XY")).toBeVisible();
    await expect(page.getByTestId("plane-pick-face")).toHaveCount(0);
  });

  test("Escape disarms the face pick, then exits the sketch", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(
      page,
      account.token,
      "Cancel face pick",
    );
    await page.goto(`/parts/${part.id}`);

    await buildBaseBox(page);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-pick-face").click();
    await expect(page.getByTestId("face-pick-prompt")).toBeVisible();

    // First Escape disarms the pick (stays in the plane-pick step)…
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("face-pick-prompt")).toHaveCount(0);
    await expect(page.getByTestId("sketch-step")).toHaveText("Pick a plane");
    // …a second Escape exits the sketch entirely.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  });
});

test.describe("sketch on a model face — founder screenshots", () => {
  async function bossOnFace(page: Page, part: { id: string }): Promise<void> {
    await page.goto(`/parts/${part.id}`);
    await buildBaseBox(page);
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-pick-face").click();
    await expect(page.getByTestId("face-pick-prompt")).toBeVisible();
    await expect(
      page.locator('[data-testid^="plane-pick-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
  }

  test("face picker + boss-on-a-face (desktop)", async ({ page }) => {
    await page.setViewportSize({ width: 1512, height: 945 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Boss desktop");
    await bossOnFace(page, part);

    // The face-pick step: the body's planar faces highlighted + the guide.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-on-face-pick-desktop.png`,
    });

    await clickTopFace(page, part.id);
    await expectSeatedOnFace(page);
    await sketchBossAndSave(page);
    await extrudeTenMm(page);
    await waitForBossBody(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-on-face-boss-desktop.png`,
    });
  });

  test("face picker + boss-on-a-face (small laptop 1280×800)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Boss laptop");
    await bossOnFace(page, part);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-on-face-pick-laptop.png`,
    });

    await clickTopFace(page, part.id);
    await expectSeatedOnFace(page);
    await sketchBossAndSave(page);
    await extrudeTenMm(page);
    await waitForBossBody(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-on-face-boss-laptop.png`,
    });
  });
});
