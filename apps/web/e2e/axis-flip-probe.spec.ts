/**
 * FOUNDER REPORT (2026-08-14): "I draw in a plane and then all of a sudden it
 * switches after an extrude."
 *
 * OBSERVATION FIRST — this file does not assert a fix, it MEASURES the axis at
 * every step of the founder's own flow so the switch can be seen rather than
 * theorised about. It prints one JSON line per observation; run with
 *
 *   scripts/e2e.sh --web-only -- e2e/axis-flip-probe.spec.ts --reporter=list
 *
 * What is sampled at each step:
 *   view        `data-view`     — the named view the camera settled into
 *   cameraPos   `data-camera-pos` — where the camera actually is
 *   up          the camera's UP vector, read from the live three camera
 *   forward     the direction it looks, ditto
 *   sketchStep  the sketcher's own statement of which plane it is on
 *
 * The camera's own up/forward are read from the r3f scene rather than inferred
 * from `cameraPos`, because a position alone cannot distinguish a camera that
 * ORBITED from one whose UP AXIS CHANGED — and the founder's report is about
 * the latter. That distinction is the whole point of this probe.
 */
import { expect, test } from "./fixtures";
import { enterSketch } from "./planeMap";
import { createPartViaApi, seedSession } from "./support";

interface AxisSample {
  step: string;
  view: string | null;
  cameraPos: string | null;
  up: [number, number, number] | null;
  forward: [number, number, number] | null;
  sketchStep: string | null;
}

/**
 * Read the camera's basis out of the live scene.
 *
 * r3f keeps the camera on the root state; drei's controls mutate it in place,
 * so reading it after a settle gives the orientation the user is actually
 * looking through. Rounded to 3 dp: we are looking for axis SWAPS (a 1 becoming
 * a 0 in a different slot), not for sub-degree drift.
 */
async function readCameraBasis(page: import("@playwright/test").Page): Promise<{
  up: [number, number, number] | null;
  forward: [number, number, number] | null;
}> {
  return page.evaluate(() => {
    // r3f keeps its store on the canvas element as `__r3f`. Reaching for it is
    // deliberate: adding a production global for a diagnostic is what put a
    // `RenderProbe` in shipped code, and this probe is meant to be deleted.
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    const root = (
      canvas as unknown as {
        __r3f?: { root?: { getState?: () => { camera?: unknown } } };
      } | null
    )?.__r3f?.root;
    const state = root?.getState?.();
    const cam = state?.camera as
      | {
          up: { x: number; y: number; z: number };
          getWorldDirection: (v: unknown) => {
            x: number;
            y: number;
            z: number;
          };
        }
      | undefined;
    if (!cam) return { up: null, forward: null };
    const r = (n: number) => Math.round(n * 1000) / 1000;
    const dir = cam.getWorldDirection({ x: 0, y: 0, z: 0 });
    return {
      up: [r(cam.up.x), r(cam.up.y), r(cam.up.z)] as [number, number, number],
      forward: [r(dir.x), r(dir.y), r(dir.z)] as [number, number, number],
    };
  });
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
  const basis = await readCameraBasis(page);
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
    up: basis.up,
    forward: basis.forward,
    sketchStep,
  };
  console.log(`[AXIS] ${JSON.stringify(s)}`);
  return s;
}

test.describe("FOUNDER — the axis switches after an extrude", () => {
  test("observe the axis through draw -> save -> extrude", async ({ page }) => {
    test.setTimeout(180_000);

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
    samples.push(await sample(page, "06-extrude-editor-open"));

    await page.getByTestId("extrude-distance").press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    samples.push(await sample(page, "07-after-extrude"));

    await page.screenshot({
      path: "docs/screenshots/axis-probe-after-extrude.png",
    });

    // THE OBSERVATION. Not a pass/fail on the founder's behalf — a printed
    // table, plus the one comparison that says whether an AXIS changed rather
    // than the camera merely having moved.
    console.log(`[AXIS-TABLE] ${JSON.stringify(samples, null, 2)}`);

    const pinned = samples.find((s) => s.step === "02-iso-pinned");
    const after = samples.find((s) => s.step === "07-after-extrude");
    console.log(
      `[AXIS-VERDICT] up before=${JSON.stringify(pinned?.up)} after=${JSON.stringify(after?.up)} | ` +
        `view before=${pinned?.view} after=${after?.view} | ` +
        `forward before=${JSON.stringify(pinned?.forward)} after=${JSON.stringify(after?.forward)}`,
    );
  });
});
