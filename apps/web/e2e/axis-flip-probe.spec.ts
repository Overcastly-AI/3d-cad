/**
 * FB-20 — THE GATE ON THE FIRST EXTRUDE.
 *
 * Founder report (2026-08-14): "I draw in a plane and then all of a sudden it
 * switches after an extrude." This file began life as a pure probe — it printed
 * the camera at every step of that flow and asserted nothing, which is how the
 * cause was found: `framedOnce` meant "has the auto-fit run", not "does this
 * scene have a viewpoint", so the FIRST body to appear in a session was framed
 * as if nobody had ever posed the camera, whatever the user had pinned.
 *
 * It now ASSERTS that. The printing stayed, because the per-step table is what
 * made the bug legible in the first place; run it with
 *
 *   scripts/e2e.sh --web-only -- e2e/axis-flip-probe.spec.ts --reporter=list
 *
 * Three assertions, in the order they matter:
 *
 *   1. DIRECTION HOLDS across the first extrude (`expectCameraStable`) — the
 *      defect.
 *   2. POSITION MOVES across it — the WANTED half. Pre-extrude there are no
 *      bounds, so the fit sits at the empty-scene radius (200 × 1.75 = 350);
 *      post-extrude it is solved against the body's projected extents. A gate
 *      that only forbade movement would pass just as happily on a camera that
 *      had stopped re-framing altogether.
 *   3. A FRESH SCENE STILL OPENS ISO (after `reload`) — because the cheap
 *      "fix" is to delete the first-run branch, and an empty part with no prior
 *      pose does need a default.
 *
 * What each step samples:
 *   view        `data-view`        — the named view the camera settled into
 *   cameraPos   `data-camera-pos`  — where the camera actually is
 *   up/forward  the live three camera, via the shared scene probe
 *   sketchStep  the sketcher's own statement of which plane it is on
 *
 * The live camera is read through `./invariants` (`cameraPose`), not through a
 * bespoke `__r3f` reader: one maintained camera-reading path, and every sample
 * carries `agreesWithStamp` so a probe that latched onto the reference cube's
 * HUD camera cannot quietly report health.
 */
import { expect, test } from "./fixtures";
import {
  angleBetween,
  cameraPose,
  expectCameraStable,
  installSceneProbe,
  waitForCameraRest,
} from "./invariants";
import { enterSketch } from "./planeMap";
import { createPartViaApi, distinctCanvasColors, seedSession } from "./support";

/** The direction the shell opens with (`VIEW_DIRECTIONS.iso`, normalised). */
const ISO_FORWARD: [number, number, number] = [-0.5518, -0.3752, -0.7449];

interface AxisSample {
  step: string;
  view: string | null;
  cameraPos: string | null;
  up: [number, number, number] | null;
  forward: [number, number, number] | null;
  agreesWithStamp: boolean;
  sketchStep: string | null;
}

function round3(v: readonly number[]): [number, number, number] {
  const r = (n: number): number => Math.round(n * 1000) / 1000;
  return [r(v[0] ?? 0), r(v[1] ?? 0), r(v[2] ?? 0)];
}

async function sample(
  page: import("@playwright/test").Page,
  step: string,
): Promise<AxisSample> {
  // A BOUNDED settle, deliberately not `waitForFrames`: the viewport is
  // `frameloop="demand"`, so an idle scene produces no renders and the first
  // version of this probe hung on its very first sample until the test timed
  // out at 180 s without printing a single reading. That is corroboration for
  // REV-5, not a detour — but a diagnostic must not depend on the thing it is
  // trying to observe.
  await page.waitForTimeout(400);
  const viewport = page.getByTestId("viewport");
  const pose = await cameraPose(page);
  // AN EXPLICIT TIMEOUT, because `.catch()` cannot save you from a promise
  // that never settles. `sketch-step` does not exist outside the sketcher, and
  // this project leaves Playwright's `actionTimeout` unset — which means NO
  // timeout, not the 5 s of `expect`. The first version of this probe therefore
  // hung forever on the empty part page and reported the failure against the
  // NEXT line, which is how it looked like a `getAttribute` problem.
  const sketchStep = await page
    .getByTestId("sketch-step")
    .innerText({ timeout: 750 })
    .catch(() => null);
  const s: AxisSample = {
    step,
    view: await viewport.getAttribute("data-view"),
    cameraPos: await viewport.getAttribute("data-camera-pos"),
    up: round3(pose.up),
    forward: round3(pose.direction),
    agreesWithStamp: pose.agreesWithStamp,
    sketchStep,
  };
  console.log(`[AXIS] ${JSON.stringify(s)}`);
  return s;
}

/** `data-camera-pos` as numbers — the settled position, to 0.1. */
function posOf(sample: AxisSample): [number, number, number] {
  const parts = (sample.cameraPos ?? "").split(",").map(Number);
  expect(parts, `no data-camera-pos at ${sample.step}`).toHaveLength(3);
  return round3(parts);
}

function distance(
  a: readonly [number, number, number],
  b: readonly [number, number, number],
): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

test.describe("FB-20 — the FIRST extrude re-frames the body without stealing the viewpoint", () => {
  test("pin a view, sketch, extrude: direction holds, distance re-fits", async ({
    page,
  }) => {
    test.setTimeout(180_000);

    await installSceneProbe(page); // before goto: it hooks three.js construction
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Axis probe");
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("viewport")).toBeVisible();

    const samples: AxisSample[] = [];
    samples.push(await sample(page, "01-empty-part"));

    // Pin a known starting orientation so any later change is the app's doing
    // and not a leftover from however the part page happened to open.
    await page.getByTestId("view-iso").click();
    samples.push(await sample(page, "02-iso-pinned"));

    await enterSketch(page, "XY");
    samples.push(await sample(page, "03-in-sketch-on-XY"));

    await page.keyboard.press("r");
    await expect(page.getByTestId("tool-rect")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.mouse.click(650, 420);
    await page.mouse.move(980, 640);
    await page.mouse.click(980, 640);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    samples.push(await sample(page, "04-rectangle-drawn"));

    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    samples.push(await sample(page, "05-sketch-saved"));

    await page.getByTestId("new-extrude").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    const before = await sample(page, "06-extrude-editor-open");
    samples.push(before);
    expect(
      before.agreesWithStamp,
      "probe locked onto the model camera, not the reference cube's HUD",
    ).toBe(true);

    // THE GATE. `expectCameraStable` samples at REST either side (orbit damping
    // and the settle ease both coast), so the comparison is between two static
    // poses rather than between a moving camera and a still one.
    const drift = await expectCameraStable(
      page,
      async () => {
        await page.getByTestId("extrude-distance").press("Enter");
        await expect(page.getByTestId("body-inspector")).toBeVisible({
          timeout: 30_000,
        });
        // Not just the panel: the MESH. Without this the gate would pass on a
        // body that never rendered, since a camera nothing re-framed is the
        // most stable camera there is.
        await expect
          .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
          .toBeGreaterThan(24);
      },
      { maxDegrees: 1 },
    );

    const after = await sample(page, "07-after-extrude");
    samples.push(after);

    // THE WANTED HALF. Pre-extrude the fit had no bounds and parked at the
    // empty-scene radius (200 × 1.75 = 350); post-extrude it is solved against
    // the body. Re-framing is the whole reason the auto-fit exists, so a gate
    // that only forbids motion is half a gate.
    const moved = distance(posOf(before), posOf(after));
    expect(
      moved,
      `the fit did not re-frame: ${before.cameraPos} -> ${after.cameraPos}`,
    ).toBeGreaterThan(20);

    await page.screenshot({
      path: "docs/screenshots/axis-probe-after-extrude.png",
    });

    console.log(`[AXIS-TABLE] ${JSON.stringify(samples, null, 2)}`);
    console.log(
      `[AXIS-VERDICT] drift=${drift.toFixed(3)}° moved=${moved.toFixed(1)} | ` +
        `view before=${before.view} after=${after.view} | ` +
        `forward before=${JSON.stringify(before.forward)} after=${JSON.stringify(after.forward)}`,
    );

    // FIRST-RUN DEFAULT, kept honest. The framing above is preserved because
    // the scene HAS a pose; a scene that has none must still open iso, so
    // "delete the first-run branch" is not a fix. A reload is a genuinely
    // unposed scene with geometry already in it.
    await page.reload();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(24);
    const reopened = await waitForCameraRest(page);
    const fromIso = angleBetween(reopened.direction, ISO_FORWARD);
    console.log(
      `[AXIS-RELOAD] forward=${JSON.stringify(round3(reopened.direction))} ` +
        `iso-delta=${fromIso.toFixed(2)}°`,
    );
    expect(
      fromIso,
      `a freshly opened part must still frame iso (was ${JSON.stringify(round3(reopened.direction))})`,
    ).toBeLessThan(3);
  });
});
