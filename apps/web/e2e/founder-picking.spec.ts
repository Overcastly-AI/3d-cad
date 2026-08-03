import { expect, test, type Page } from "./fixtures";

import { handClick } from "./hand";
import {
  expectCameraStable,
  expectModelUnoccluded,
  installSceneProbe,
  measureOcclusion,
  waitForCameraRest,
} from "./invariants";
import { measureReachability, testIdPrefix } from "./reachability";
import {
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
  waitForFrames,
} from "./support";

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
 *
 * FB-17 (2026-08-01) added the second half: the gates that make this class of
 * defect VISIBLE rather than relying on a founder to find it. `hand.ts` drives
 * clicks with real drift and dwell, `reachability.ts` measures the affordance
 * as a FRACTION of what the user can see, and `invariants.ts` asserts the
 * camera and the panels behave across an action. Their own calibration and
 * negative controls live in `qa-harness.spec.ts`; what lives here is those
 * gates pointed at the real product.
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

  /**
   * FB-17(a) — INPUT FIDELITY, swept rather than sampled.
   *
   * `founder-picking`'s FB-12 case pins ONE drift value (6 px). One value is a
   * spot check on a threshold, and thresholds are exactly what regress: the
   * original bug was a single constant, and any replacement constant fails at
   * some distance. Sweeping the range a trackpad actually produces turns the
   * assertion from "6 px works" into "the whole band a hand covers works",
   * which is the property the product needs and the one a spot check cannot
   * express. 0 is included deliberately as the degenerate machine input, so a
   * regression that broke only the STILL click would show up here too.
   */
  for (const drift of [0, 2, 4, 6, 10]) {
    test(`FB-12 sweep: a click that drifts ${drift} px selects the line`, async ({
      page,
    }) => {
      const account = await seedSession(page);
      const part = await createPartViaApi(
        page,
        account.token,
        `Drift ${drift}`,
      );
      await page.goto(`/parts/${part.id}`);
      await sketchOnXY(page);
      await drawProbeRectangle(page);
      await expect(page.getByTestId("selection-readout")).toContainText(
        "nothing selected",
      );

      await handClick(page, BOTTOM_EDGE.x, BOTTOM_EDGE.y, { drift });

      // The readout, not the dimension editor: this asserts the PICK resolved,
      // with no second interaction to muddy which step failed.
      await expect(page.getByTestId("selection-readout")).not.toContainText(
        "nothing selected",
      );
      await page.keyboard.press("d");
      await expect(page.getByTestId("dimension-input")).toBeVisible();
    });
  }

  /**
   * FB-17(c) — MEASURE THE AFFORDANCE.
   *
   * The `test.fail()` above proves ONE coordinate is dead, which a single
   * 24 px dot in the right place would satisfy. This measures the fraction of
   * the body's visible area that is a live pick target, which no arrangement of
   * dots can fake.
   *
   * STILL FAILING, and expected to. Measured on this spec 2026-08-01:
   * **45/454 sampled points = 9.9 %**, and 46/796 = 5.8 % on a run where the
   * body framed larger. That spread is not noise to be tuned away, it is the
   * defect stated numerically — six 24 px `PickNode` markers do not grow when
   * the face does, so the affordance gets WORSE the closer you look at the
   * part. (The earlier QA pass's 2.2 % is the same effect at a larger framing.)
   * The fit is pinned before measuring so the number is comparable run to run.
   *
   * The floor is 50 %: when the face itself becomes the target (FB-3/FB-5,
   * FB-8's hovered-face highlight), every lit point over the body picks it and
   * this lands near 100 %, so 50 % cannot be reached by adding dots — only by
   * changing the model of what a target is. Flip this to a plain `test` then.
   */
  test.fail(
    "FB-3/FB-5: only a few percent of the visible body is a pick target",
    async ({ page }) => {
      const account = await seedSession(page);
      const part = await createPartViaApi(page, account.token, "Affordance");
      await page.goto(`/parts/${part.id}`);
      await buildBox(page);

      // Pin the framing: the fraction is a ratio of screen areas, so it is only
      // comparable between runs if the body is the same size in frame.
      const viewport = page.getByTestId("viewport");
      await viewport.evaluate((node) => {
        node.dataset["fitRect"] = "";
      });
      await page.getByTestId("view-fit").click();
      await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
        timeout: 20_000,
      });

      await page.getByTestId("new-sketch").click();
      await page.getByTestId("plane-pick-face").click();
      await expect(page.getByTestId("face-pick-prompt")).toBeVisible();
      await expect(
        page.locator('[data-testid^="plane-pick-face-"]').first(),
      ).toBeVisible({ timeout: 20_000 });
      await waitForFrames(page, 6);

      const measured = await measureReachability(page, {
        step: 8,
        accept: testIdPrefix("plane-pick-face-"),
      });
      // Guards BEFORE the real assertion, so this case cannot start "failing
      // as expected" for a new reason — the trap the FB-13 case fell into.
      expect(measured.sampled, "body sampled").toBeGreaterThan(300);
      expect(measured.reachable, "the markers ARE reachable").toBeGreaterThan(
        10,
      );
      expect(
        measured.fraction,
        `clickable ${measured.reachable}/${measured.sampled} = ${(measured.fraction * 100).toFixed(1)}%`,
      ).toBeGreaterThanOrEqual(0.5);
    },
  );

  /**
   * FB-17 — INVARIANTS ACROSS AN ACTION (the FB-1 gate).
   *
   * "After the extrude it flipped to xy." The extrude was always correct; the
   * auto-fit re-imposed iso on every rebuild, and no spec noticed because every
   * spec asserted the RESULT. One line — record the direction, act, compare —
   * would have caught it, and now does.
   */
  test("FB-1 gate: a rebuild re-frames the body without stealing the viewpoint", async ({
    page,
  }) => {
    await installSceneProbe(page); // before goto: it hooks three.js construction
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Viewpoint");
    await page.goto(`/parts/${part.id}`);
    await buildBox(page);

    // Put the user somewhere deliberate and NOT iso, via the view rail: a snap
    // ends in the rig's own settle stamp, so the precondition is established by
    // a condition rather than by waiting out orbit damping.
    const viewport = page.getByTestId("viewport");
    await viewport.evaluate((node) => {
      node.dataset["fitRect"] = "";
    });
    await page.getByTestId("view-front").click();
    await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
      timeout: 20_000,
    });
    const chosen = await waitForCameraRest(page);
    expect(chosen.agreesWithStamp, "probe locked onto the model camera").toBe(
      true,
    );

    // Now change the model. This rebuilds the geometry, which changes `fitKey`
    // and re-runs the auto-fit — the exact trigger of FB-1.
    const drift = await expectCameraStable(page, async () => {
      await page.getByTestId("feature-select-1").click();
      await expect(page.getByTestId("extrude-editor")).toBeVisible();
      await page.getByTestId("extrude-distance").fill("25");
      await page.getByTestId("extrude-distance").press("Enter");
      await expect
        .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
        .toBeGreaterThan(24);
    });
    // Measured 0.071° on 2026-08-01 — the fit re-frames distance and target and
    // leaves the direction alone. The 1° ceiling is `expectCameraStable`'s
    // default; this records what "correct" actually costs.
    expect(drift).toBeLessThan(0.5);
  });

  /**
   * FB-17 — OCCLUSION (the FB-7 gate, which the founder photographed).
   *
   * Two halves, and the second is the finding. At rest the fit does its job:
   * the body lands between the tree and the inspector with no overlap. Open a
   * feature editor and it lands ON the model — and the app's own free-rect fit
   * cannot see it, because the editor card never declares
   * `data-viewport-chrome` the way `FloatingPanel` and `ViewBar` do. So the
   * editor has to be named explicitly here, which is itself the bug report.
   */
  test("FB-7 gate: at rest, no chrome covers the model", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Occlusion rest");
    await page.goto(`/parts/${part.id}`);
    await buildBox(page);
    const viewport = page.getByTestId("viewport");
    await viewport.evaluate((node) => {
      node.dataset["fitRect"] = "";
    });
    await page.getByTestId("view-fit").click();
    await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
      timeout: 20_000,
    });
    await waitForFrames(page, 6);

    const report = await expectModelUnoccluded(page);
    // Measured: model box 375–1239 × 340–799 between panel-tree (ends 332) and
    // panel-inspector (starts 1268), with view-bar below at y 906.
    expect(report.chromeCount).toBeGreaterThanOrEqual(3);
  });

  test.fail(
    "FB-7: an open feature editor covers the model it is editing",
    async ({ page }) => {
      const account = await seedSession(page);
      const part = await createPartViaApi(
        page,
        account.token,
        "Occlusion edit",
      );
      await page.goto(`/parts/${part.id}`);
      await buildBox(page);

      await page.getByTestId("feature-select-1").click();
      await expect(page.getByTestId("extrude-editor")).toBeVisible();
      await waitForFrames(page, 6);

      // Measured on this spec 2026-08-01, with the annotation lifted so the
      // reason is on record: the editor card (x 344–664, y 112–480) covers
      // **50 069 px² = 9.0 %** of the body's box (375–1239 × 307–951) — the
      // panel editing the part is sitting on the part. The same report also
      // named `view-bar` at 6 630 px² (1.2 %), i.e. the bottom rail overlaps
      // too once the editor pushes the framing; both are FB-7, and only the
      // second is visible to the app's own free-rect fit.
      const report = await measureOcclusion(page, {
        extraSelectors: ['[data-testid="extrude-editor"]'],
      });
      expect(report.modelPixels, "body rendered").toBeGreaterThan(500);
      expect(report.chromeCount, "chrome measured").toBeGreaterThan(0);
      await expectModelUnoccluded(page, {
        extraSelectors: ['[data-testid="extrude-editor"]'],
      });
    },
  );
});
