import { expect, test, type Page } from "./fixtures";

import { handClick } from "./hand";
import {
  chromeRects,
  expectCameraStable,
  expectModelUnoccluded,
  installSceneProbe,
  measureOcclusion,
  waitForCameraRest,
} from "./invariants";
import { litPoints, measureReachabilityWith } from "./reachability";
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
 *   - FB-7  — FIXED 2026-08-06 (ChromeRail + the plane-frame fix): the editors
 *     dock into the tree's own column and the extrude ghost stopped painting on
 *     the far side of the sketch plane. The case is a plain `test` with NO
 *     `extraSelectors`, and it carries a containment assertion so it cannot
 *     pass by simply failing to find the editor.
 *   - FB-3/FB-5 — FIXED (SEL-1 A2): the drawn face IS the click target now.
 *     Both cases flipped to plain `test`s, and BOTH needed more than the
 *     annotation changed. The affordance case had to stop hit-testing the DOM
 *     (`elementFromPoint` answers "the canvas" for a raycast handler, so it
 *     could not have scored the fix); the seat case had to stop clicking a
 *     hardcoded coordinate that turned out to be 40 px off the body, i.e. it
 *     had never failed for its stated reason. Affordance: **9.9 % -> 84.6 %**
 *     of the visible body, against a 50 % floor.
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

/**
 * Frame the body deliberately and wait for the fit to land, returning the free
 * rect it solved. The auto-fit that follows an extrude is not a settled state:
 * the inspector mounts a beat later and gives the column back, which announces
 * a chrome change and re-frames. Both halves of the FB-7 gate start from the
 * same explicit fit so "before" and "after" are the same measurement.
 */
async function settleFit(page: Page): Promise<string | null> {
  const viewport = page.getByTestId("viewport");
  await viewport.evaluate((node) => {
    node.dataset["fitRect"] = "";
  });
  await page.getByTestId("view-fit").click();
  await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
    timeout: 20_000,
  });
  await waitForFrames(page, 6);
  return viewport.getAttribute("data-fit-rect");
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

  test("FB-3/FB-5: clicking a highlighted face seats the sketch on it", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Face pick");
    await page.goto(`/parts/${part.id}`);
    await buildBox(page);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-pick-face").click();
    await expect(page.getByTestId("face-pick-prompt")).toBeVisible();
    const nodes = page.locator('[data-testid^="plane-pick-face-"]');
    await expect(nodes.first()).toBeVisible({ timeout: 20_000 });

    // The prompt says "Click a highlighted planar face to sketch on it", and
    // until SEL-1 A2 that was a lie: the only live targets were the six 24 px
    // `PickNode` markers at the face CENTROIDS, so 2.2 % of the body's
    // on-screen area was a pick target and the sentence described an
    // affordance that did not exist. The click below lands ON the body and
    // well AWAY from every marker — the exact aim that used to do nothing.
    //
    // THE POINT IS DERIVED, and it has to be. This case used to click a
    // hardcoded (1000, 430) under `test.fail()`, and when the fix landed and it
    // was flipped, it still failed — because at this framing (1000, 430) is
    // bench, roughly 40 px off the body's upper-right corner. So the old case
    // had never been testing what it said: it "failed as expected" for years
    // because the click MISSED, not because the face was dead, and it would
    // have kept failing after any fix whatsoever. That is the same trap the
    // FB-13 case fell into, and the general rule this file already states —
    // read WHY it failed, never just that it did. A point taken from the lit
    // silhouette cannot drift out from under the assertion when the fit changes.
    const markers = await nodes.all();
    const boxes = (
      await Promise.all(markers.map((n) => n.boundingBox()))
    ).flatMap((b) => (b === null ? [] : [b]));
    expect(boxes.length, "the PickNode markers are present").toBeGreaterThan(0);
    const clear = (await litPoints(page, { step: 8 })).find((point) =>
      boxes.every(
        (b) =>
          point.x < b.x - 12 ||
          point.x > b.x + b.width + 12 ||
          point.y < b.y - 12 ||
          point.y > b.y + b.height + 12,
      ),
    );
    expect(clear, "a lit point clear of every marker").toBeDefined();
    if (clear === undefined) return;
    await page.mouse.click(clear.x, clear.y);

    await expect(page.getByTestId("sketch-step")).toHaveText("On Face", {
      timeout: 5_000,
    });
  });

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
   * Measured on this spec 2026-08-01, BEFORE the fix: **45/454 sampled points
   * = 9.9 %**, and 46/796 = 5.8 % on a run where the body framed larger. That
   * spread was not noise to be tuned away, it was the defect stated
   * numerically — six 24 px `PickNode` markers do not grow when the face does,
   * so the affordance got WORSE the closer you looked at the part. (The
   * earlier QA pass's 2.2 % is the same effect at a larger framing.) The fit is
   * pinned before measuring so the number is comparable run to run.
   *
   * The floor is 50 %: when the face itself becomes the target, every lit point
   * over the body picks it and this lands near 100 %, so 50 % cannot be reached
   * by adding dots — only by changing the model of what a target is.
   *
   * NOW A REAL ASSERTION (SEL-1 A2, 2026-08-05) — and note WHAT HAD TO CHANGE
   * ABOUT THE MEASUREMENT, because the old form could not have scored the fix.
   * `measureReachability` hit-tests the DOM with `elementFromPoint`, which was
   * the right model while every target WAS DOM (a drei `Html` `PickNode`). The
   * fix makes the drawn surface itself the target via a raycast handler, and
   * `elementFromPoint` can only ever answer "the canvas" for one of those — so
   * the DOM census would have stayed pinned near 9.9 % with the defect fully
   * fixed. That is the `gen-check`-measuring-the-wrong-input trap in another
   * costume: a gate is only as honest as its INPUT. The probe therefore aims
   * the pointer and asks the app what it is ADDRESSING (`data-face-pick-hover`),
   * which is exactly the question the founder was asking.
   */
  test("FB-3/FB-5: the visible body IS the pick target", async ({ page }) => {
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

    // One round trip per point, so the grid is coarse (the helper's own
    // guidance). The lit silhouette supplies the points either way, so this
    // is still a fraction of what the user can SEE, not of the canvas.
    const points = await litPoints(page, { step: 24 });
    const measured = await measureReachabilityWith(points, async (point) => {
      await page.mouse.move(point.x, point.y);
      return (await viewport.getAttribute("data-face-pick-hover")) !== null;
    });

    // Guards BEFORE the real assertion, so this case cannot start passing
    // for a new reason — e.g. an attribute that gets stuck set, which would
    // score 100 % on a body that is not there at all.
    expect(measured.sampled, "body sampled").toBeGreaterThan(40);
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-face-pick-hover", /.*/, {
      timeout: 5_000,
    });

    expect(
      measured.fraction,
      `clickable ${measured.reachable}/${measured.sampled} = ${(measured.fraction * 100).toFixed(1)}%`,
    ).toBeGreaterThanOrEqual(0.5);
  });

  /**
   * FB-17 — INVARIANTS ACROSS AN ACTION (the FB-1 gate).
   *
   * "After the extrude it flipped to xy." The extrude was always correct; the
   * auto-fit re-imposed iso on every rebuild, and no spec noticed because every
   * spec asserted the RESULT. One line — record the direction, act, compare —
   * would have caught it, and now does.
   *
   * NOT redundant with `axis-flip-probe.spec.ts` (FB-20), and the reason
   * generalises: `buildBox` above performs the FIRST sketch→extrude before the
   * measurement window opens, so `framedOnce` is already true here and this
   * gate has only ever watched the SECOND extrude — a fixture that consumes the
   * first-run state cannot see first-run bugs.
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
   * Two halves. At rest the fit does its job: the body lands between the tree
   * and the inspector with no overlap. Opening a feature editor used to land it
   * ON the model — and the app's own free-rect fit could not see it, because
   * the editor card declared no `data-viewport-chrome`, so this spec had to
   * name the selector by hand, which was itself the bug report.
   *
   * FIXED 2026-08-06. The editors DOCK into a `ChromeRail` — the same column
   * and the same width as the tree panel — so the overlap is structurally
   * impossible rather than merely smaller, and the rail declares itself as
   * chrome. `extraSelectors` is gone from both halves: the editor is gated
   * because the app admits it exists.
   *
   * Two things had to be true for that to work, and both are asserted below.
   * The charged inset must NOT change when an editor opens, or the fit would
   * lurch. And the ghost had to stop drawing on the wrong side of the sketch
   * plane: re-opening an unmodified 10 mm extrude painted a translucent prism
   * 152 px BELOW the body — through the ground grid and into the view rail —
   * because the origin-datum plane bases were stated in the kernel's Z-up frame
   * while the scene renders Y-up (FB-7c / FB-9, `sketch/plane.ts`). No framing
   * change could have fixed that one: the fit's subject is the body's bounds,
   * and a preview is not in them.
   */
  test("FB-7 gate: at rest, no chrome covers the model", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Occlusion rest");
    await page.goto(`/parts/${part.id}`);
    await buildBox(page);
    await settleFit(page);

    const report = await expectModelUnoccluded(page);
    // Measured: model box 375–1239 × 340–799 between panel-tree (ends 332) and
    // panel-inspector (starts 1268), with view-bar below at y 906.
    expect(report.chromeCount).toBeGreaterThanOrEqual(3);
  });

  test("FB-7 FIXED: an open feature editor does not cover the model", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Occlusion edit");
    await page.goto(`/parts/${part.id}`);
    await buildBox(page);
    const restFit = await settleFit(page);
    const restBox = (await measureOcclusion(page)).model;

    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await waitForFrames(page, 6);

    // NON-VACUITY, and it is the whole reason this reads as a pass rather than
    // as a gate that stopped looking: the editor must be CONTAINED by a rect
    // `chromeRects` returns on its own — no `extraSelectors`. Take the rail
    // away and the card floats free of every declared rect, so this fails
    // before the overlap assertion is even reached.
    const editorBox = await page.getByTestId("extrude-editor").boundingBox();
    expect(editorBox, "editor rendered").not.toBeNull();
    const declared = await chromeRects(page);
    const housing = declared.find(
      (rect) =>
        editorBox !== null &&
        rect.left <= editorBox.x + 1 &&
        rect.top <= editorBox.y + 1 &&
        rect.right >= editorBox.x + editorBox.width - 1 &&
        rect.bottom >= editorBox.y + editorBox.height - 1,
    );
    expect(
      housing,
      "the editor declares itself as chrome " +
        `(rects: ${JSON.stringify(declared)}, editor: ${JSON.stringify(editorBox)})`,
    ).toBeDefined();

    // Measured on this spec 2026-08-01, BEFORE the fix, so the size of what was
    // wrong stays on record: the editor card (x 344-664, y 112-480) covered
    // **50 069 px2 = 9.0 %** of the body's box (375-1239 x 307-951), and
    // `view-bar` another 6 630 px2 (1.2 %) — the panel editing the part sitting
    // on the part, plus the bottom rail catching the mis-framed ghost.
    const report = await measureOcclusion(page);
    expect(report.modelPixels, "body rendered").toBeGreaterThan(500);
    expect(report.chromeCount, "chrome measured").toBeGreaterThan(0);
    await expectModelUnoccluded(page);

    // The FRAMING invariant that made docking the safe first move: the column
    // the editor takes is the column the tree already had, so the fit's free
    // rect is untouched and the camera never moves (2026-08-06: 356,24,888,758
    // either way).
    expect(
      await page.getByTestId("viewport").getAttribute("data-fit-rect"),
    ).toBe(restFit);

    // The GHOST invariant: re-opening an extrude WITHOUT changing anything
    // previews exactly the body that is already there, so the lit silhouette
    // must not grow. It grew 152 px downward before the frame fix — a
    // translucent prism on the far side of the sketch plane (FB-7c / FB-9).
    expect(report.model.bottom).toBeLessThanOrEqual(restBox.bottom + 2);
    expect(report.model.top).toBeGreaterThanOrEqual(restBox.top - 2);
  });
});
