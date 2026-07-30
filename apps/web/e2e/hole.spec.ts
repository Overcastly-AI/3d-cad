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
    // No face yet → Create is blocked, and the anchor block asks for a CLICK
    // rather than reporting an empty field (UI-W3).
    await expect(page.getByTestId("hole-face-empty")).toHaveText(
      "Click a face",
    );
    await expect(page.getByTestId("hole-submit")).toBeDisabled();

    // UI-W3: the face pick is ARMED on open — invoking Hole with nothing
    // selected puts the cursor straight into the pick, so the body's six planar
    // faces are already live. No arming step.
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
    // UI-W3: the face pick is ARMED on open — invoking Hole with nothing
    // selected puts the cursor straight into the pick.
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
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
    // UI-W3: the face pick is ARMED on open — invoking Hole with nothing
    // selected puts the cursor straight into the pick.
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
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

test.describe("hole — a TAPPED hole in the UI", () => {
  /**
   * A tapped hole is the one feature whose result is invisible: the kernel cuts
   * the tap-drill bore and NOTHING else (the thread is a cosmetic callout), and
   * the evaluate response is byte-identical to the same hole untapped. So the
   * proof here is not pixels — it is that the designation the editor derives
   * SURVIVES the write and comes back on reload, on a row the modeler can read.
   */
  test("tick Tapped, pick M10x1.5 → the bore derives, drills, and the callout persists", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Tapped plate");
    await page.goto(`/parts/${part.id}`);

    await buildBaseBox(page);
    await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    // UI-W3: the face pick is ARMED on open — invoking Hole with nothing
    // selected puts the cursor straight into the pick.
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await clickTopFace(page);
    await expect(page.getByTestId("hole-face")).toContainText("10");

    // Untapped: no thread controls at all, and Ø6.
    await expect(page.getByTestId("hole-thread-designation")).toHaveCount(0);
    await expect(page.getByTestId("hole-diameter")).toHaveValue("6");

    // Tick Tapped → the callout stamps and the bore DERIVES to the M6x1 tap
    // drill (D - P = 5). The bore is authored, not locked: it just gets filled.
    // Thread is progressively disclosed (UI-W4) — open the block, then tap.
    await page.getByTestId("hole-thread-toggle").click();
    await page.getByTestId("hole-tapped").click();
    await expect(page.getByTestId("hole-thread-designation")).toHaveText(
      "M6x1",
    );
    await expect(page.getByTestId("hole-diameter")).toHaveValue("5");

    // Choose M10 → the pitch resets to COARSE (1.5) and the bore re-derives to
    // the published M10x1.5 tap drill, 8.5.
    await page.getByTestId("hole-thread-size").selectOption("10");
    await expect(page.getByTestId("hole-thread-pitch")).toHaveValue("1.5");
    await expect(page.getByTestId("hole-thread-designation")).toHaveText(
      "M10x1.5",
    );
    await expect(page.getByTestId("hole-diameter")).toHaveValue("8.5");

    // The `hole_thread_mismatch` guard bites BEFORE the round-trip: a Ø12 bore
    // is wider than the M10 nominal, so there's no material for the tap to cut.
    await page.getByTestId("hole-diameter").fill("12");
    await expect(page.getByTestId("hole-submit")).toBeDisabled();
    await expect(page.getByTestId("hole-editor")).toContainText(
      "Too wide to tap M10x1.5",
    );

    // One click on the tap-drill chip restores the derived bore.
    await page.getByTestId("hole-thread-tap-drill").click();
    await expect(page.getByTestId("hole-diameter")).toHaveValue("8.5");
    await expect(page.getByTestId("hole-thread-tap-drill")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    const write = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/features`) &&
        r.request().method() === "POST",
    );
    await expect(page.getByTestId("hole-submit")).toBeEnabled();
    await page.getByTestId("hole-submit").click();
    expect((await write).status()).toBe(201);

    // THE PROOF: the kernel honoured the callout (an unknown designation or an
    // untappable bore would be an ERR row, never a plain hole), the body
    // re-renders with the Ø8.5 bore, and the TREE ROW carries the designation —
    // the only place a tapped hole is distinguishable from its clearance twin.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
    await expectRenderedBody(page);
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Hole1" }),
    ).toContainText("M10x1.5");

    // Reload: the designation round-tripped through the real API — it is stored
    // in the feature params, not inferred from a geometry that cannot carry it.
    await page.reload();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Hole1" }),
    ).toContainText("M10x1.5");

    // Re-opening the hole seeds the editor from the stored thread.
    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("hole-thread-designation")).toHaveText(
      "M10x1.5",
    );
    await expect(page.getByTestId("hole-diameter")).toHaveValue("8.5");
  });

  test("tapped composes with a counterbore — one feature, not two", async ({
    page,
  }) => {
    // The whole reason Tapped is a toggle and not a fourth Type segment: a
    // counterbored tapped hole is an everyday feature the kernel builds as ONE.
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Tapped cbore");
    await page.goto(`/parts/${part.id}`);

    await buildBaseBox(page);
    await page.getByTestId("new-hole").click();
    // UI-W3: the face pick is ARMED on open — invoking Hole with nothing
    // selected puts the cursor straight into the pick.
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await clickTopFace(page);
    await expect(page.getByTestId("hole-face")).toContainText("10");

    await page.getByTestId("hole-type-counterbore").click();
    // Thread is progressively disclosed (UI-W4) — open the block, then tap.
    await page.getByTestId("hole-thread-toggle").click();
    await page.getByTestId("hole-tapped").click();
    await page.getByTestId("hole-thread-size").selectOption("6");
    await expect(page.getByTestId("hole-diameter")).toHaveValue("5");
    // A Ø11 x 3 mm cbore over the M6 tap drill, into the 10 mm plate.
    await page.getByTestId("hole-cbore-depth").fill("3");

    await expect(page.getByTestId("hole-submit")).toBeEnabled();
    await page.getByTestId("hole-submit").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Hole1" }),
    ).toContainText("M6x1");
  });
});

test.describe("hole — counterbore + countersink recesses in the UI", () => {
  /** Build a box, open the Hole command, and pick the top face — the shared
   * lead-in for both recess tests (the recess is set AFTER a face is chosen). */
  async function armFaceAndTopPick(page: Page): Promise<void> {
    await buildBaseBox(page);
    await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    // UI-W3: the face pick is ARMED on open — invoking Hole with nothing
    // selected puts the cursor straight into the pick.
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await clickTopFace(page);
    await expect(page.getByTestId("hole-face")).toContainText("10");
  }

  test("counterbore: recess fields reveal, the Ø-exceeds-bore guard bites, then drills", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Counterbore");
    await page.goto(`/parts/${part.id}`);
    await armFaceAndTopPick(page);

    // Switch to Counterbore → the two recess fields reveal with defaults.
    await page.getByTestId("hole-type-counterbore").click();
    await expect(page.getByTestId("hole-type-counterbore")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("hole-cbore-diameter")).toHaveValue("11");
    await expect(page.getByTestId("hole-cbore-depth")).toHaveValue("6");

    // The guard: a recess no wider than the Ø6 bore blocks Create with a reason.
    await page.getByTestId("hole-cbore-diameter").fill("5");
    await expect(page.getByTestId("hole-submit")).toBeDisabled();
    await expect(page.getByTestId("hole-editor")).toContainText(
      "wider than the Ø6 mm bore",
    );

    // A valid Ø11 × 6 mm counterbore into the 10 mm box drills clean.
    await page.getByTestId("hole-cbore-diameter").fill("11");
    const write = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/features`) &&
        r.request().method() === "POST",
    );
    await expect(page.getByTestId("hole-submit")).toBeEnabled();
    await page.getByTestId("hole-submit").click();
    expect((await write).status()).toBe(201);

    // THE PROOF: the kernel cut the bore + the coaxial cylindrical recess — the
    // tree evaluates to Solved (an invalid recess would be a hole_cbore_invalid
    // ERR row) and the body re-renders with the counterbored hole.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
    await expectRenderedBody(page);
  });

  test("countersink: mouth Ø + angle presets reveal, then drills", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Countersink");
    await page.goto(`/parts/${part.id}`);
    await armFaceAndTopPick(page);

    // Switch to Countersink → the mouth Ø + angle field (default 90°) reveal.
    await page.getByTestId("hole-type-countersink").click();
    await expect(page.getByTestId("hole-csink-diameter")).toHaveValue("12");
    await expect(page.getByTestId("hole-csink-angle")).toHaveValue("90");

    // The fastener-standard presets fill the angle field; 82° reads back on the
    // chip and the field.
    await page.getByTestId("hole-csink-angle-82").click();
    await expect(page.getByTestId("hole-csink-angle")).toHaveValue("82");
    await expect(page.getByTestId("hole-csink-angle-82")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // Back to 90° for a shallow cone that fits the 10 mm box.
    await page.getByTestId("hole-csink-angle-90").click();
    await expect(page.getByTestId("hole-csink-angle")).toHaveValue("90");

    const write = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/features`) &&
        r.request().method() === "POST",
    );
    await expect(page.getByTestId("hole-submit")).toBeEnabled();
    await page.getByTestId("hole-submit").click();
    expect((await write).status()).toBe(201);

    // THE PROOF: the conical recess cut clean — Solved, no ERR row, body redraws.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
    await expectRenderedBody(page);
  });
});

test.describe("hole — founder screenshots", () => {
  async function armedHoleEditor(page: Page, part: { id: string }) {
    await page.goto(`/parts/${part.id}`);
    await buildBaseBox(page);
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    // UI-W3: the face pick is ARMED on open — invoking Hole with nothing
    // selected puts the cursor straight into the pick.
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(
      page.locator('[data-testid^="plane-pick-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
  }

  /**
   * Click the face node furthest from the EDITOR CARD — measured, not guessed,
   * because the card's seat is a design decision that moves (UI-W4 docked it to
   * the right rail; it used to sit at the left editor inset). The founder shot
   * only needs a populated face chip, not a specific face, so the reliable rule
   * is "whichever pick node the panel is not sitting on".
   */
  async function clickUnoccludedFace(page: Page): Promise<void> {
    const nodes = page.locator('[data-testid^="plane-pick-face-"]');
    await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
    const card = await page.getByTestId("hole-editor-shell").boundingBox();
    const cardCentre =
      card === null
        ? { x: 0, y: 0 }
        : { x: card.x + card.width / 2, y: card.y + card.height / 2 };
    const count = await nodes.count();
    let bestScore = -Infinity;
    let bestIndex = 0;
    for (let i = 0; i < count; i += 1) {
      const box = await nodes.nth(i).boundingBox();
      if (box === null) continue;
      const score = Math.hypot(box.x - cardCentre.x, box.y - cardCentre.y);
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

  /**
   * The AUTHORING founder shot: build a box, pick a face, choose the recess
   * type, and capture the EDITOR (recess params revealed) over the body — no
   * submit, so any pickable face is fine (`clickUnoccludedFace` is reliable at
   * every width). This is the primary deliverable — the type selector + recess
   * fields the founder asked to see, over the viewport hero.
   */
  async function recessAuthoringShot(
    page: Page,
    part: { id: string },
    type: "counterbore" | "countersink",
    tag: string,
  ): Promise<void> {
    await page.goto(`/parts/${part.id}`);
    await buildBaseBox(page);
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    // UI-W3: the face pick is ARMED on open — invoking Hole with nothing
    // selected puts the cursor straight into the pick.
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await clickUnoccludedFace(page);
    await expect(page.getByTestId("hole-face")).toBeVisible();
    await page.getByTestId(`hole-type-${type}`).click();
    const revealed =
      type === "counterbore" ? "hole-cbore-diameter" : "hole-csink-diameter";
    await expect(page.getByTestId(revealed)).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/hole-${type}-${tag}.png`,
    });
  }

  /**
   * The RESULT founder shot (desktop): drill the recess into the TOP face — the
   * 10 mm-thick face that has room below for a Ø11 × 6 mm counterbore / a Ø12
   * 90° countersink — and capture the RECESSED hole in the viewport. The top
   * face is clickable at 1440 (unlike the short-laptop width, where the taller
   * editor occludes its node), so the result shot runs desktop-only.
   */
  async function recessResultShot(
    page: Page,
    part: { id: string },
    type: "counterbore" | "countersink",
  ): Promise<void> {
    await page.goto(`/parts/${part.id}`);
    await buildBaseBox(page);
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    // UI-W3: the face pick is ARMED on open — invoking Hole with nothing
    // selected puts the cursor straight into the pick.
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await clickTopFace(page);
    await expect(page.getByTestId("hole-face")).toContainText("10");
    await page.getByTestId(`hole-type-${type}`).click();
    await expect(page.getByTestId("hole-submit")).toBeEnabled();
    await page.getByTestId("hole-submit").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
    await expectRenderedBody(page);
    // Wait for the recessed mesh to finish shading — a shot taken mid-regen
    // shows only the wireframe silhouette, not the studio-shaded recess.
    await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
      timeout: 30_000,
    });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/hole-${type}-result-desktop.png`,
    });
  }

  for (const width of [1440, 1280] as const) {
    const tag = width === 1440 ? "desktop" : "laptop";
    const height = width === 1440 ? 900 : 800;
    test(`counterbore authoring (${width}×${height})`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      const account = await seedSession(page);
      const part = await createPartViaApi(page, account.token, "Cbore shot");
      await recessAuthoringShot(page, part, "counterbore", tag);
    });
    test(`countersink authoring (${width}×${height})`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      const account = await seedSession(page);
      const part = await createPartViaApi(page, account.token, "Csink shot");
      await recessAuthoringShot(page, part, "countersink", tag);
    });
  }

  /**
   * The TAPPED founder shot: the thread callout stamped over the viewport with
   * an M10x1.5 chosen and the bore derived to its 8.5 mm tap drill. This is the
   * only surface on which a tapped hole is visible at all, so the shot IS the
   * feature (the body it drills is a plain Ø8.5 bore, by design).
   */
  async function tappedAuthoringShot(
    page: Page,
    part: { id: string },
    tag: string,
  ): Promise<void> {
    await page.goto(`/parts/${part.id}`);
    await buildBaseBox(page);
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    // UI-W3: the face pick is ARMED on open — invoking Hole with nothing
    // selected puts the cursor straight into the pick.
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await clickUnoccludedFace(page);
    await expect(page.getByTestId("hole-face")).toBeVisible();
    // Thread is progressively disclosed (UI-W4) — open the block, then tap.
    await page.getByTestId("hole-thread-toggle").click();
    await page.getByTestId("hole-tapped").click();
    await page.getByTestId("hole-thread-size").selectOption("10");
    await expect(page.getByTestId("hole-thread-designation")).toHaveText(
      "M10x1.5",
    );
    await expect(page.getByTestId("hole-diameter")).toHaveValue("8.5");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/hole-tapped-${tag}.png`,
    });
  }

  for (const width of [1440, 1280] as const) {
    const tag = width === 1440 ? "desktop" : "laptop";
    const height = width === 1440 ? 900 : 800;
    test(`tapped authoring (${width}×${height})`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      const account = await seedSession(page);
      const part = await createPartViaApi(page, account.token, "Tapped shot");
      await tappedAuthoringShot(page, part, tag);
    });
  }

  /**
   * The TREE shot: a drilled tapped hole whose row carries `hole · M10x1.5`.
   * The founder asked where tapped-ness lives outside the editor — this is it.
   */
  test("tapped hole in the feature tree (desktop 1440×900)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Tapped tree");
    await page.goto(`/parts/${part.id}`);
    await buildBaseBox(page);
    await page.getByTestId("new-hole").click();
    // UI-W3: the face pick is ARMED on open — invoking Hole with nothing
    // selected puts the cursor straight into the pick.
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await clickTopFace(page);
    await expect(page.getByTestId("hole-face")).toContainText("10");
    // Thread is progressively disclosed (UI-W4) — open the block, then tap.
    await page.getByTestId("hole-thread-toggle").click();
    await page.getByTestId("hole-tapped").click();
    await page.getByTestId("hole-thread-size").selectOption("10");
    await expect(page.getByTestId("hole-submit")).toBeEnabled();
    await page.getByTestId("hole-submit").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);
    await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
      timeout: 30_000,
    });
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Hole1" }),
    ).toContainText("M10x1.5");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/hole-tapped-tree-desktop.png`,
    });
  });

  test("counterbore result (desktop 1440×900)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Cbore result");
    await recessResultShot(page, part, "counterbore");
  });

  test("countersink result (desktop 1440×900)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Csink result");
    await recessResultShot(page, part, "countersink");
  });
});
