import { expect, test, type Page } from "./fixtures";

import {
  angleBetween,
  installSceneProbe,
  waitForCameraRest,
  type CameraPose,
} from "./invariants";
import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * CAMRESTORE-1 — leaving a sketch gives the VIEW back, not just the camera.
 *
 * The sketcher parks the camera normal-on to the plane, and exiting used to
 * leave it there: a modeller who entered a sketch to add one dimension came
 * back to a flat plan view of their part and had to re-orient by hand. Measured
 * while closing GHOST-1: whole-canvas brightness 310289 -> 24675 across the
 * round trip with `data-drawn-faces` 6 and `data-ghost-faces` 0 at BOTH ends,
 * i.e. nothing about what is DRAWN changed and only the framing moved. Fusion
 * returns you to the view you were in.
 *
 * WHAT THIS SPEC ASSERTS ON, and why it is not that brightness census. A census
 * across sketch entry/exit is exactly the measurement CAMRESTORE-1 broke — the
 * framing moves, so the number moves for reasons unrelated to the subject. The
 * camera itself is the subject here, so it is read directly, from the live
 * three.js camera through `installSceneProbe`: DIRECTION is the invariant (the
 * FB-1 distinction — re-framing distance and target when a body changes is
 * behaviour users want; taking the VIEWPOINT away is the defect), with position
 * asserted only on the path where nothing rebuilt.
 *
 * `waitForCameraRest`'s 0.05 deg default is unreachable on this scene: damping
 * decays per RENDERED frame on a demand loop, so the coast times out at 15 s
 * still moving. 0.3 deg settles, and every assertion below has at least 10x
 * that much room.
 */

/** Direction agreement good enough to call it the same viewpoint. */
const SAME_VIEW_DEG = 1;

/** The camera has plainly been taken somewhere else. */
const DIFFERENT_VIEW_DEG = 10;

/** Rest tolerance the demand loop can actually reach — see the file docstring. */
const REST = { epsilonDeg: 0.3, timeoutMs: 60_000 };

async function rest(page: Page): Promise<CameraPose> {
  return waitForCameraRest(page, REST);
}

function distance(
  a: readonly [number, number, number],
  b: readonly [number, number, number],
): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

/** Standoff from the orbit centre — the scale a position miss is judged against. */
function standoff(pose: CameraPose): number {
  return Math.hypot(...pose.position);
}

/**
 * How much of the frame the body fills, in painted pixels.
 *
 * The apparent-size witness for the PARALLEL case: an orthographic camera frames
 * by zoom, not by distance, so a restore that put the attitude back and dropped
 * the zoom would satisfy every direction assertion here and still hand the
 * modeller a part at the wrong size. The canvas is transparent (the atmosphere
 * is DOM beneath it) and the grid is drawn into it, so "body" is read as the
 * bright, low-saturation aluminium the matcap paints — the grid inks are dark
 * and blue, and the ground shadow is dark.
 */
async function bodyPixels(page: Page): Promise<number> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (!canvas) return -1;
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const ctx = probe.getContext("2d");
    if (!ctx) return -1;
    ctx.drawImage(canvas, 0, 0);
    const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
    let count = 0;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i] ?? 0;
      const g = data[i + 1] ?? 0;
      const b = data[i + 2] ?? 0;
      const alpha = data[i + 3] ?? 0;
      const spread = Math.max(r, g, b) - Math.min(r, g, b);
      if (alpha > 200 && Math.min(r, g, b) > 110 && spread < 60) count += 1;
    }
    return count;
  });
}

/** Sketch a rectangle on XY and extrude it 10 mm — the part every case starts from. */
async function buildPlate(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(620, 400);
  await page.mouse.move(1000, 640);
  await page.mouse.click(1000, 640);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
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

/** A fresh part with a plate on it, the scene probe already installed. */
async function partWithPlate(page: Page, name: string): Promise<void> {
  await installSceneProbe(page); // before goto: hooks three.js at Scene construction
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, name);
  await page.goto(`/parts/${part.id}`);
  await buildPlate(page);
  await page.keyboard.press("Escape"); // close the extrude editor
}

/** Press, travel in steps, release — the gesture a hand actually makes. */
async function drag(
  page: Page,
  button: "left" | "middle",
  from: { x: number; y: number },
  dx: number,
  dy: number,
): Promise<void> {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down({ button });
  await page.mouse.move(from.x + dx / 2, from.y + dy / 2, { steps: 6 });
  await page.mouse.move(from.x + dx, from.y + dy, { steps: 6 });
  await page.mouse.up({ button });
}

/** Open the sketcher on XY and wait for the plane-normal park to land. */
async function enterSketchOnXy(page: Page): Promise<CameraPose> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
  return rest(page);
}

/** Leave the sketcher without saving anything, and wait for the camera. */
async function escapeSketch(page: Page): Promise<CameraPose> {
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  return rest(page);
}

test.describe("CAMRESTORE-1 — leaving a sketch gives the view back", () => {
  // Every case waits out a real damping coast, which decays per RENDERED frame
  // on a demand loop — so its wall-clock length is set by the box's CPU, not by
  // anything the spec does. Same reasoning as `sketch-orbit.spec.ts`.
  test.beforeEach(() => {
    test.slow();
  });

  test("the exact pose comes back when nothing was built", async ({ page }) => {
    await partWithPlate(page, "Camera restore");

    // A view the modeller chose by hand, so the restore cannot be passing by
    // landing on some default the app would have picked anyway.
    await drag(page, "left", { x: 800, y: 500 }, 170, -120);
    const before = await rest(page);

    // THE PREMISE, asserted so this case cannot pass vacuously: the sketcher
    // really does move the camera. Without it a rig that did nothing at all on
    // entry would satisfy every assertion below.
    const parked = await enterSketchOnXy(page);
    expect(
      angleBetween(before.direction, parked.direction),
      "the sketcher must park the camera somewhere else, or there is nothing to restore",
    ).toBeGreaterThan(DIFFERENT_VIEW_DEG);

    const after = await escapeSketch(page);
    const drift = angleBetween(before.direction, after.direction);
    expect(
      drift,
      `view direction after the round trip: ${before.direction.join(",")} -> ${after.direction.join(",")}`,
    ).toBeLessThanOrEqual(SAME_VIEW_DEG);
    // Nothing rebuilt, so no refit is entitled to re-frame: the POSITION comes
    // back too, not merely the attitude. Judged against the standoff so the
    // tolerance means the same thing whatever the plate's size turned out to be.
    expect(
      distance(before.position, after.position) / standoff(before),
    ).toBeLessThan(0.02);
  });

  test("a parallel view comes back at the same apparent size", async ({
    page,
  }) => {
    await partWithPlate(page, "Camera restore ortho");

    // FRONT is a named view, so it arms ORTHOGRAPHIC — and a parallel camera is
    // framed by its zoom, which the sketcher's park does not preserve
    // (`ProjectionRig` holds perspective for the duration). So this is the case
    // where restoring the attitude alone is not enough.
    await page.getByTestId("view-front").click();
    const viewport = page.getByTestId("viewport");
    await expect(viewport).toHaveAttribute("data-projection", "orthographic");
    const before = await rest(page);
    await waitForFrames(page, 4);
    const sizeBefore = await bodyPixels(page);
    expect(
      sizeBefore,
      "the plate must be on screen to measure",
    ).toBeGreaterThan(2_000);

    await enterSketchOnXy(page);
    const after = await escapeSketch(page);

    expect(angleBetween(before.direction, after.direction)).toBeLessThanOrEqual(
      SAME_VIEW_DEG,
    );
    // The modeller's projection is theirs again…
    await expect(viewport).toHaveAttribute("data-projection", "orthographic");
    // …and the part is the size they left it. Within 5%: the same pixels are
    // re-rasterised at a sub-pixel-different camera, so the silhouette's edge
    // row can gain or lose a pixel, but a dropped zoom is a whole-frame miss.
    await waitForFrames(page, 4);
    const sizeAfter = await bodyPixels(page);
    expect(
      Math.abs(sizeAfter - sizeBefore) / sizeBefore,
      `apparent size ${sizeBefore} -> ${sizeAfter} px`,
    ).toBeLessThan(0.05);
  });

  test("a deliberate orbit inside the sketch is not overruled", async ({
    page,
  }) => {
    await partWithPlate(page, "Camera restore orbit");

    // A NAMED view, not a hand orbit, for the pre-entry pose: this case has to
    // tell "the exit left the camera alone" from "the exit put it back", and
    // those two are only distinguishable while the remembered pose and the
    // mid-sketch one are far apart. A hand orbit lands wherever it lands — one
    // run of an earlier draft put them 6.8 deg apart and the case would have
    // been vacuous — so the fixture pins one end.
    await page.getByTestId("view-front").click();
    const before = await rest(page);

    // Wait for the park to LAND before the gesture. Dragging into the entry
    // ease loses the turn — the rig is writing the camera every frame in that
    // window — and a zero turn reads exactly like an unbound control, so this
    // wait is what makes the measurement below mean anything.
    const parked = await enterSketchOnXy(page);
    await drag(page, "middle", { x: 800, y: 500 }, 60, -150);
    const orbited = await rest(page);
    expect(
      angleBetween(parked.direction, orbited.direction),
      "the mid-sketch orbit must actually turn the view (VP-1)",
    ).toBeGreaterThan(DIFFERENT_VIEW_DEG);
    // THE PREMISE, stated so a fixture that stops separating the two poses
    // fails loudly here instead of quietly passing for the wrong reason.
    expect(
      angleBetween(before.direction, orbited.direction),
      "fixture: the mid-sketch view must be plainly different from the remembered one",
    ).toBeGreaterThan(DIFFERENT_VIEW_DEG);

    const after = await escapeSketch(page);
    // The rule (same shape as the auto-ghost's, `905fcc4`): the remembered pose
    // is a DEFAULT, and an explicit user action beats it. Restoring over a view
    // the modeller turned to by hand would be the same class of defect as the
    // one being fixed, pointed the other way.
    expect(
      angleBetween(orbited.direction, after.direction),
      "the view the modeller chose inside the sketch must survive the exit",
    ).toBeLessThanOrEqual(2 * SAME_VIEW_DEG);
  });

  test("the ticket's own flow: draw, save, and still be where you were", async ({
    page,
  }) => {
    await partWithPlate(page, "Camera restore save");

    await drag(page, "left", { x: 800, y: 500 }, 170, -120);
    const before = await rest(page);

    // A sketch that BUILDS something, which is the case with a second mover in
    // it: the new geometry triggers the auto-fit, and that fit must re-frame
    // the restored view rather than adopt whatever attitude the ease was
    // passing through when it landed.
    await enterSketchOnXy(page);
    await page.keyboard.press("c");
    await expect(page.getByTestId("tool-circle")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.mouse.click(800, 500);
    await page.mouse.click(860, 500);
    await expect(page.getByTestId("sketch-save")).toContainText("1 entity");
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    const after = await rest(page);
    // DIRECTION only: the fit is entitled to re-frame distance and target for
    // the new subject, and taking that away would break FB-1's fix. The
    // viewpoint is the thing the user chose.
    expect(
      angleBetween(before.direction, after.direction),
      `view direction across a saved sketch: ${before.direction.join(",")} -> ${after.direction.join(",")}`,
    ).toBeLessThanOrEqual(SAME_VIEW_DEG);
    // And the body is still drawn — a restore that flew the camera off the part
    // would satisfy the angle and lose the model.
    expect(await bodyPixels(page)).toBeGreaterThan(2_000);
  });
});

/**
 * Founder before/after (gated behind UPDATE_SCREENSHOTS — see e2e/fixtures.ts).
 * This test regenerates the AFTER frame; the BEFORE was captured once by
 * removing the restore request and renaming the file, because it is the
 * behaviour this change deleted rather than a mode the app still has.
 *
 * The frame is the moment that matters: the instant after the sketch closes,
 * which is where the modeller used to find themselves looking at a plan view of
 * a part they were examining in three-quarters a second earlier.
 */
test.describe("CAMRESTORE-1 founder screenshots", () => {
  test("the frame you land on after leaving a sketch", async ({ page }) => {
    test.slow();
    await page.setViewportSize({ width: 1280, height: 800 });
    await partWithPlate(page, "Camera restore shot");

    await page.getByTestId("view-iso").click();
    await rest(page);
    await enterSketchOnXy(page);
    await escapeSketch(page);
    // Park the pointer off every control and off the body: a tooltip or a hover
    // glow in the frame is a hand's accident, not part of the state on show.
    await page.mouse.move(420, 640);
    await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("viewport")).toHaveAttribute(
      "data-body-highlight",
      "none",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/camrestore-sketch-exit-after-laptop.png`,
    });
  });
});
