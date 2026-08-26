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

    await grip.press("ArrowUp");
    await grip.press("ArrowUp");
    expect(await distance(page)).toBeCloseTo(11, 6);

    await grip.press("Shift+ArrowUp");
    expect(await distance(page)).toBeCloseTo(16, 6);

    await grip.press("ArrowDown");
    expect(await distance(page)).toBeCloseTo(15.5, 6);

    // No dead end: the editor's own commit key still works from the handle.
    await grip.press("Enter");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-extents")).toContainText("15.5");
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
