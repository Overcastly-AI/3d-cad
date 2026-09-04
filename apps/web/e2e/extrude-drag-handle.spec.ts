/**
 * T-23 — THE EXTRUDE DRAG HANDLE, driven the way a modeller drives it.
 *
 * The audit that filed this swept the whole DOM in every state it could reach
 * for `[data-testid*="handle|gizmo|drag|arrow|manip"]` and got `[]`: the
 * product had no drag affordance anywhere. The design mandate calls that the
 * single biggest "does not feel like a modeling tool" gap we have.
 *
 * A handle QA cannot drive is a handle that rots silently, so this spec does
 * the actual gesture — press on the arrow, move the pointer, release — and
 * follows the value all the way to the SOLID: the distance field, the live
 * ghost's stamp, the readout at the tip, and finally the committed body's own
 * height in the scene. Any one of those alone can pass on a handle that moves
 * a number and nothing else.
 *
 * It also drives it by KEYBOARD, because the grip is a real `role="slider"` and
 * the quality floor says nothing is reachable by pointer alone.
 */
import { expect, test, type Page } from "./fixtures";
import {
  installSceneProbe,
  namedWorldBox,
  waitForCameraRest,
} from "./invariants";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

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

/** Sketch a profile and open the extrude editor on it. */
async function openExtrude(page: Page): Promise<void> {
  await enterSketch(page, "XY");
  await sketchRectangle(page);
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-editor")).toBeVisible();
  await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
}

/** The handle's centre in page coordinates. */
async function gripCentre(page: Page): Promise<{ x: number; y: number }> {
  const box = await page.getByTestId("extrude-depth-handle").boundingBox();
  if (box === null) throw new Error("the depth handle has no box");
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** The distance field's current value as a number. */
async function distance(page: Page): Promise<number> {
  return Number.parseFloat(
    await page.getByTestId("extrude-distance").inputValue(),
  );
}

/**
 * The distance once the field and the live ghost AGREE.
 *
 * The drag runs handle -> editor form -> ghost, so during a fast pointer sweep
 * the field is a render or two behind the pointer and converges when it stops.
 * Reading the field the instant the button comes up therefore catches an
 * intermediate value — which is how the first run of this spec managed to
 * report a 27.5 mm drag and a 31 mm body and blame the model. Waiting for the
 * two readouts to agree is the honest settle, and it asserts the invariant the
 * feature is actually claiming: one value, read twice.
 */
async function settledDistance(page: Page): Promise<number> {
  await expect
    .poll(async () => {
      const field = await distance(page);
      const stamp = await page
        .getByTestId("extrude-preview-active")
        .getAttribute("data-distance-mm");
      return stamp === String(field);
    })
    .toBe(true);
  return distance(page);
}

test.describe("extrude drag handle", () => {
  test("drag the arrow and the depth follows it — field, ghost and body", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Dragged boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    // The affordance the audit could not find, now nameable and typed.
    const grip = page.getByRole("slider", { name: "Extrude depth" });
    await expect(grip).toBeVisible();
    await expect(grip).toHaveAttribute("data-testid", "extrude-depth-handle");
    await expect(grip).toHaveAttribute("aria-valuenow", "10");
    await expect(grip).toHaveAttribute("aria-valuetext", "10 mm");
    // The number rides with the arrow, not 800 px away in the rail (T-4).
    await expect(page.getByTestId("extrude-depth-readout")).toContainText("10");

    // THE GESTURE. An XY sketch sweeps up the scene, and the default iso view
    // puts scene +Y up the screen, so dragging the pointer UP grows the boss.
    const from = await gripCentre(page);
    await page.mouse.move(from.x, from.y);
    await page.mouse.down();
    for (let step = 1; step <= 6; step += 1) {
      await page.mouse.move(from.x, from.y - step * 12);
    }
    await page.mouse.up();

    const dragged = await settledDistance(page);
    expect(
      dragged,
      "dragging up must GROW the extrude, not shrink or ignore it",
    ).toBeGreaterThan(10);
    // Snapped to the half-millimetre, so a pointer never writes 12.4713 into a
    // field a machinist has to read.
    expect(Math.round(dragged * 2) / 2).toBeCloseTo(dragged, 6);

    // One value, read three ways: the field, the live ghost, and the tip tag.
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-distance-mm",
      String(dragged),
    );
    await expect(page.getByTestId("extrude-depth-readout")).toContainText(
      String(dragged),
    );
    await expect(grip).toHaveAttribute("aria-valuenow", String(dragged));

    // …and it reaches the SOLID. A handle that moves a number and not the model
    // would pass everything above.
    await page.getByTestId("extrude-distance").press("Enter");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect
      .poll(
        async () => (await namedWorldBox(page, "model-body"))?.vertices ?? 0,
        { timeout: 30_000 },
      )
      .toBeGreaterThan(0);
    const body = await namedWorldBox(page, "model-body");
    if (body === null) throw new Error("no body after save");
    const height = body.max[1] - body.min[1];
    console.log(
      `T-23 dragged ${dragged} mm -> body height ${height.toFixed(4)} mm`,
    );
    expect(height).toBeCloseTo(dragged, 2);
  });

  test("in an iso view: typing moves the arrow, and the arrow moves the value", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Typed boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    // Saving a sketch leaves the camera NORMAL to the plane — the reference
    // cube reads TOP — where the pull axis points straight at the eye and has
    // no screen direction to read. That pose is covered by the drag test above
    // (it is the common one, and it is why the handle carries a screen-space
    // fallback). THIS test needs the other mode, so it takes an iso view first.
    await page.getByTestId("view-iso").click();
    await waitForCameraRest(page);

    const before = await gripCentre(page);
    await page.getByTestId("extrude-distance").fill("40");
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-distance-mm",
      "40",
    );
    await expect(
      page.getByRole("slider", { name: "Extrude depth" }),
    ).toHaveAttribute("aria-valuenow", "40");
    const after = await gripCentre(page);
    // Deeper extrude, arrow further up the screen: the two controls are one
    // value, in both directions.
    expect(after.y).toBeLessThan(before.y - 20);

    // …and now the REAL gesture, with the axis readable on screen: pull the
    // arrow back down and the value comes with it.
    await page.mouse.move(after.x, after.y);
    await page.mouse.down();
    for (let step = 1; step <= 5; step += 1) {
      await page.mouse.move(after.x, after.y + step * 10);
    }
    await page.mouse.up();
    const dragged = await settledDistance(page);
    expect(dragged).toBeLessThan(40);
    expect(dragged).toBeGreaterThan(0);
  });

  test("keyboard: the grip is a slider, and Enter still saves", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Keyed boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    const grip = page.getByRole("slider", { name: "Extrude depth" });
    await grip.focus();
    await expect(grip).toBeFocused();

    // POLLED, not sampled. A key press returns as soon as the event is
    // dispatched, while the value travels handle -> editor form -> field, so a
    // bare read races the round trip: this test failed twice in a full run and
    // passed alone, reporting 11 where 16 was expected — the value BEFORE the
    // third press had landed, which reads exactly like a swallowed key. `poll`
    // retries the read; `expect(await …)` cannot.
    await grip.press("ArrowUp");
    await grip.press("ArrowUp");
    await expect.poll(() => distance(page)).toBeCloseTo(11, 6);

    // 15, not 16. A coarse press lands on the COARSE grid (5 mm here — ten fine
    // steps), which is the same rule the drawing sheet's nudge follows and the
    // reason two independently-dragged depths can be made to meet. Adding 5 to
    // 11 would give a number that is on no grid at all; see `steppedDepth`.
    await grip.press("Shift+ArrowUp");
    await expect.poll(() => distance(page)).toBeCloseTo(15, 6);

    await grip.press("ArrowDown");
    await expect.poll(() => distance(page)).toBeCloseTo(14.5, 6);

    // No dead end: the editor's own commit key still works from the handle.
    await grip.press("Enter");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-extents")).toContainText("14.5");
  });

  test("keyboard: every press counts, however fast they come", async ({
    page,
  }) => {
    // THE LOST UPDATE, which is a SECOND defect and not the quantiser's. The
    // value round-trips handle -> editor -> ghost -> back, several commits long,
    // and the handle's optimistic value used to be dropped by the
    // acknowledgement of the PREVIOUS press — so a key arriving inside that
    // window computed from a stale prop and overwrote the one before it. The
    // browser said so itself, in an instrumented run of 20 fast sequences on the
    // real stack, 13 of them wrong:
    //
    //     key=ArrowUp pending=null depthMm=10   from=10   next=10.5
    //     key=ArrowUp pending=10.5 depthMm=10   from=10.5 next=11
    //     effect depthMm=10.5 pending=11    <- ack for press 1 clears press 2
    //     key=ArrowUp pending=null depthMm=10.5 from=10.5 next=15.5
    //
    // NOTE WHY THIS COUNTS FINE PRESSES rather than repeating that sequence.
    // Quantising the coarse step MASKS the race for a coarse key — 10.5 and 11
    // both land on 15 — so `Up, Up, Shift+Up` would go green with the race still
    // live. Only a run of FINE presses, where a lost press is a lost half
    // millimetre, can see it. Six presses, repeated, with no settle between
    // them, because a settle is precisely what hides this.
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Hammered boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    const grip = page.getByRole("slider", { name: "Extrude depth" });
    const field = page.getByTestId("extrude-distance");
    const PRESSES = 6;

    for (let run = 0; run < 4; run += 1) {
      await field.fill("10");
      await expect.poll(() => distance(page)).toBeCloseTo(10, 6);
      await grip.focus();
      for (let i = 0; i < PRESSES; i += 1) await grip.press("ArrowUp");
      // Six presses, six steps: 10 -> 13, no matter how little time the round
      // trip was given.
      await expect
        .poll(() => distance(page), { message: `fast run ${run}` })
        .toBeCloseTo(10 + PRESSES * 0.5, 6);
      // …and the grip says the same thing it asked for, so assistive tech and
      // the field cannot disagree about where the arrow is.
      await expect(grip).toHaveAttribute("aria-valuenow", "13");
      // A coarse press on top still lands on the coarse grid, from a value the
      // keyboard (not the pointer) produced.
      await grip.press("Shift+ArrowUp");
      await expect.poll(() => distance(page)).toBeCloseTo(15, 6);
    }
  });

  test("keyboard: from a value a drag left behind, a press lands on the grid", async ({
    page,
  }) => {
    // A free (Ctrl) drag ends wherever the pointer said — 12.4713 and the like.
    // The nudge used to ADD its step to that, so the whole sequence after it sat
    // on an offset lattice (12.9713, 13.4713, 17.4713 …) and no round number was
    // reachable by any number of presses. This drives that exact start, and
    // follows the value to the SOLID rather than stopping at the field: a
    // quantiser that fixes the readout and not the geometry would pass a
    // text assertion.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Odd boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    const grip = page.getByRole("slider", { name: "Extrude depth" });
    await page.getByTestId("extrude-distance").fill("12.4713");
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-distance-mm",
      "12.4713",
    );

    // The NEXT half-millimetre, not "the nearest one plus a step": 12.5 is the
    // value the user is standing next to, and skipping it would be the same
    // unreachability in a smaller costume.
    await grip.focus();
    await grip.press("ArrowUp");
    await expect.poll(() => distance(page)).toBeCloseTo(12.5, 6);
    // …and a coarse press from there reaches a decade mark, which is what a
    // part is actually dimensioned in.
    await grip.press("Shift+ArrowUp");
    await expect.poll(() => distance(page)).toBeCloseTo(15, 6);

    await grip.press("Enter");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect
      .poll(
        async () => (await namedWorldBox(page, "model-body"))?.vertices ?? 0,
        {
          timeout: 30_000,
        },
      )
      .toBeGreaterThan(0);
    const body = await namedWorldBox(page, "model-body");
    if (body === null) throw new Error("no body after save");
    const height = body.max[1] - body.min[1];
    console.log(`T-23 fractional start 12.4713 -> body height ${height}`);
    expect(height).toBeCloseTo(15, 2);
  });

  test("the slider tells the truth about itself, steps included", async ({
    page,
  }) => {
    // ARIA has no way to say what a press is WORTH, so a slider whose step lives
    // only in the source is one a screen-reader user discovers by trial. The
    // description names both steps; this asserts the named step is the APPLIED
    // step, so the sentence cannot drift away from the behaviour.
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Spoken boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    const grip = page.getByRole("slider", { name: "Extrude depth" });
    await expect(grip).toHaveAttribute("aria-valuenow", "10");
    await expect(grip).toHaveAttribute("aria-valuemin", "0.1");
    await expect(grip).toHaveAttribute("aria-valuemax", "10000");
    await expect(grip).toHaveAttribute("aria-valuetext", "10 mm");

    const hint = page.getByTestId("extrude-depth-steps");
    await expect(hint).toHaveText(
      "Arrow keys step 0.5 mm; Shift or Page keys step 5 mm. Enter saves.",
    );
    // The description is wired to the control, not merely present on the page.
    const describedBy = await grip.getAttribute("aria-describedby");
    expect(describedBy).toBe(await hint.getAttribute("id"));
    // …and it is SPOKEN, not PAINTED. `sr-only` is a build-time utility, so a
    // theme that failed to generate it would leave a sentence of body text
    // sitting over the viewport beside the arrow — a real visual regression
    // that every assertion above would sail past, since they all read the
    // accessibility tree. Measured on the box, which is the only thing that can
    // see it: `sr-only` clips to 1x1.
    const hintBox = await hint.boundingBox();
    if (hintBox === null) throw new Error("the step hint has no box");
    expect(hintBox.width).toBeLessThanOrEqual(1);
    expect(hintBox.height).toBeLessThanOrEqual(1);

    // The spoken step IS the applied step.
    const fine = Number(await grip.getAttribute("data-step-mm"));
    const coarse = Number(await grip.getAttribute("data-coarse-step-mm"));
    expect(fine).toBe(0.5);
    expect(coarse).toBe(fine * 10);
    await grip.focus();
    await grip.press("ArrowUp");
    await expect.poll(() => distance(page)).toBeCloseTo(10 + fine, 6);
    await grip.press("Shift+ArrowUp");
    await expect.poll(() => distance(page)).toBeCloseTo(15, 6);
    await expect(grip).toHaveAttribute("aria-valuenow", "15");
    await expect(grip).toHaveAttribute("aria-valuetext", "15 mm");
  });

  test("founder screenshot: the gauge on a live extrude (desktop)", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);
    // Iso, because a gauge photographed end-on is a dot: the post-sketch camera
    // looks straight down the pull axis (see the shallow-axis note in
    // `extrudeHandle.ts`), which is the right state to SUPPORT and the wrong
    // one to show.
    await page.getByTestId("view-iso").click();
    await waitForCameraRest(page);
    // Held, so the ladder is extended — the state the founder should see.
    const at = await gripCentre(page);
    await page.mouse.move(at.x, at.y);
    await page.mouse.down();
    await page.mouse.move(at.x, at.y - 60);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-drag-handle-desktop.png`,
    });
    await page.mouse.up();
  });
});

test.describe("extrude drag handle small laptop (1280x800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the gauge is reachable and legible at the responsive floor", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);
    await page.getByTestId("view-iso").click();
    await waitForCameraRest(page);

    const grip = page.getByRole("slider", { name: "Extrude depth" });
    const box = await grip.boundingBox();
    if (box === null) throw new Error("the depth handle has no box");
    // WCAG 2.2 SC 2.5.8: the target is 24 px and does not shrink with the frame.
    expect(box.width).toBeGreaterThanOrEqual(24);
    expect(box.height).toBeGreaterThanOrEqual(24);
    // …and it is inside the frame, not pushed off the edge by the narrower view.
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(1280);
    expect(box.y + box.height).toBeLessThanOrEqual(800);

    const at = await gripCentre(page);
    await page.mouse.move(at.x, at.y);
    await page.mouse.down();
    await page.mouse.move(at.x, at.y - 40);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-drag-handle-laptop.png`,
    });
    await page.mouse.up();
    expect(await settledDistance(page)).toBeGreaterThan(10);
  });
});
