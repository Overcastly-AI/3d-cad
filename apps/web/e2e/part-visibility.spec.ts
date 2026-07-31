import { expect, test, type Page } from "./fixtures";

import { seedCube } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * UI-W2 — the PART half: Origin / Sketches / Bodies view control (founder:
 * *"what about the ability to enable planes, sketches and bodies? Similar to
 * fusion?"*; design `docs/design/ui-wave-tool-grade.md` Surface 2).
 *
 * The mandate's rule for this wave is 3c: a control that does not move a pixel
 * in the WebGL scene is a defect, not a stub. So the load-bearing assertions
 * here are PIXEL assertions taken off the real canvas of the real stack — the
 * same discipline the assembly half shipped with — and the DOM/aria state is
 * only ever the companion.
 *
 * Two probes, because the three categories draw in three different inks:
 *
 *  · a luminance-banded census for BODIES. BRIGHT (>110) is lit machined
 *    aluminum under the studio matcap; MID (45…110) is where a GHOSTED body
 *    lands (0.42 × body tone composited over the dark bench). Hiding drops
 *    BRIGHT without raising MID; ghosting drops BRIGHT and DOES raise MID.
 *  · an exact-ink census for ORIGIN. Datum sheets and axes draw their borders
 *    in the `sketch.planeEdge` token (`#5A6A7E`) through un-tonemapped line
 *    materials, so the token lands on the canvas at its exact hex — the same
 *    trick `countSketchInkPixels` uses for scribe ink.
 */

interface Bands {
  bright: number;
  mid: number;
}

/** Luminance-banded pixel census of the live WebGL canvas. */
async function canvasBands(page: Page): Promise<Bands> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (!canvas) return { bright: 0, mid: 0 };
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const ctx = probe.getContext("2d");
    if (!ctx) return { bright: 0, mid: 0 };
    ctx.drawImage(canvas, 0, 0);
    const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
    let bright = 0;
    let mid = 0;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i] ?? 0;
      const g = data[i + 1] ?? 0;
      const b = data[i + 2] ?? 0;
      const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      if (lum > 110) bright += 1;
      else if (lum > 45) mid += 1;
    }
    return { bright, mid };
  });
}

/** Pixels drawn in the datum-edge token `sketch.planeEdge` (#5A6A7E). */
async function datumEdgePixels(page: Page): Promise<number> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (!canvas) return 0;
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const ctx = probe.getContext("2d");
    if (!ctx) return 0;
    ctx.drawImage(canvas, 0, 0);
    const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
    let count = 0;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i] ?? 0;
      const g = data[i + 1] ?? 0;
      const b = data[i + 2] ?? 0;
      if (
        Math.abs(r - 0x5a) <= 6 &&
        Math.abs(g - 0x6a) <= 6 &&
        Math.abs(b - 0x7e) <= 6
      ) {
        count += 1;
      }
    }
    return count;
  });
}

/**
 * Pixels drawn in the solved-sketch ink token `sketch.scribeSolved` (#C4D2DE).
 *
 * The shared `countSketchInkPixels` helper is deliberately NOT used here: its
 * filter ("bright and blue-leaning") also matches machined aluminum under the
 * studio matcap, which is fine on a body-less sketching frame and useless here,
 * where the whole question is whether ink appeared ON TOP of a solid. Solved
 * ink renders un-tonemapped through a line material, so it lands on its exact
 * token hex and a tight match separates it from the shaded body.
 */
async function scribeInkPixels(page: Page): Promise<number> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (!canvas) return 0;
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const ctx = probe.getContext("2d");
    if (!ctx) return 0;
    ctx.drawImage(canvas, 0, 0);
    const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
    let count = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (
        Math.abs((data[i] ?? 0) - 0xc4) <= 4 &&
        Math.abs((data[i + 1] ?? 0) - 0xd2) <= 4 &&
        Math.abs((data[i + 2] ?? 0) - 0xde) <= 4
      ) {
        count += 1;
      }
    }
    return count;
  });
}

/** Settle the on-demand render loop before sampling the drawing buffer. */
async function settled<T>(page: Page, probe: () => Promise<T>): Promise<T> {
  await page.waitForTimeout(450);
  return probe();
}

/** Seed a 20 mm cube part, open it and wait for the solid to render. */
async function openCubePart(page: Page): Promise<string> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Bracket");
  await seedCube(page, token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByTestId("viewport")).toHaveAttribute(
    "data-total-faces",
    /[1-9]/,
    { timeout: 30_000 },
  );
  return part.id;
}

test.describe("UI-W2 part half — the browser controls what is drawn", () => {
  test("origin planes and axes render on demand and nothing else moves", async ({
    page,
  }) => {
    await openCubePart(page);

    // Fusion's default, and ours: origin geometry starts OFF, so a part that
    // needs no datum work is not permanently cluttered.
    const xy = page.getByTestId("origin-plane-XY");
    await expect(xy).toHaveAttribute("aria-pressed", "false");
    const before = await settled(page, () => datumEdgePixels(page));
    const bodyBefore = await canvasBands(page);

    await xy.click();
    await expect(xy).toHaveAttribute("aria-pressed", "true");
    const withPlane = await settled(page, () => datumEdgePixels(page));
    // The sheet's scribed border is hundreds of pixels of exact token ink.
    expect(withPlane).toBeGreaterThan(before + 150);

    // The axes are independent rows, and each adds its own ink.
    await page.getByTestId("origin-axis-X").click();
    await page.getByTestId("origin-axis-Y").click();
    const withAxes = await settled(page, () => datumEdgePixels(page));
    expect(withAxes).toBeGreaterThan(withPlane);
    await expect(page.getByTestId("origin-axis-label-X")).toBeVisible();

    // Datum geometry is not a solid: the body census is untouched by it.
    const bodyAfter = await canvasBands(page);
    expect(Math.abs(bodyAfter.bright - bodyBefore.bright)).toBeLessThan(
      bodyBefore.bright * 0.1,
    );

    // And switching it back off leaves no residue.
    await xy.click();
    await page.getByTestId("origin-axis-X").click();
    await page.getByTestId("origin-axis-Y").click();
    const off = await settled(page, () => datumEdgePixels(page));
    expect(off).toBeLessThan(before + 60);
  });

  test("a sketch can be brought back with the body on screen", async ({
    page,
  }) => {
    await openCubePart(page);

    // The default, unchanged: the body is the hero and the profile that made it
    // recedes. What is NEW is that this is now a stop the modeler can answer.
    const row = page.getByTestId(/^sketch-visibility-/).first();
    await expect(row).toHaveAttribute("aria-pressed", "false");
    const inkBefore = await settled(page, () => scribeInkPixels(page));

    await row.click();
    await expect(row).toHaveAttribute("aria-pressed", "true");
    const inkAfter = await settled(page, () => scribeInkPixels(page));
    // The profile sits ON the body's base face, so most of it is occluded by
    // the solid it made and only the silhouette peeks — a modest but decisive
    // count against a baseline of zero.
    expect(inkAfter).toBeGreaterThan(inkBefore + 50);

    await row.click();
    const inkOff = await settled(page, () => scribeInkPixels(page));
    expect(inkOff).toBeLessThan(inkAfter / 2);
  });

  test("hide and ghost a body change what the viewport draws", async ({
    page,
  }) => {
    await openCubePart(page);
    const viewport = page.getByTestId("viewport");
    const solid = await settled(page, () => canvasBands(page));
    expect(solid.bright).toBeGreaterThan(0);

    // --- HIDE (the eye) ------------------------------------------------
    // Driving the EYE (not the row's name) is the point: touching the eye
    // addresses the row and discloses its stops WITHOUT opening the base
    // feature's editor.
    const eye = page.getByTestId("body-visibility-0");
    await eye.click();
    await expect(eye).toHaveAttribute("aria-pressed", "false");
    const hidden = await settled(page, () => canvasBands(page));
    // Nothing drawn: no lit surface AND no translucent one either — the mesh,
    // its B-rep edge overlay and its pick target all go.
    expect(hidden.bright).toBeLessThan(solid.bright * 0.02);
    await expect(viewport).toHaveAttribute("data-drawn-faces", "0");
    await expect(viewport).toHaveAttribute("data-ghost-faces", "0");

    // The way back is on screen, derived, and works.
    const stamp = page.getByTestId("visibility-stamp");
    await expect(stamp).toBeVisible();
    await expect(stamp).toHaveAttribute("data-hidden-count", "1");

    // --- GHOST ---------------------------------------------------------
    await page.getByTestId("body-opacity-ghost").click();
    const ghosted = await settled(page, () => canvasBands(page));
    // Translucent, not dim: lit pixels drop OUT of the BRIGHT band and land in
    // MID, which is what tells ghost apart from hide (hide drops both). The
    // same bands and bounds the assembly half asserts on.
    expect(ghosted.bright).toBeLessThan(solid.bright * 0.8);
    expect(ghosted.mid).toBeGreaterThan(solid.mid * 1.1);
    expect(ghosted.mid).toBeGreaterThan(hidden.mid);
    await expect(viewport).toHaveAttribute("data-ghost-faces", /[1-9]/);

    await page.getByTestId("body-opacity-solid").click();
    const restored = await settled(page, () => canvasBands(page));
    expect(restored.bright).toBeGreaterThan(solid.bright * 0.8);
    await expect(stamp).toHaveCount(0);
  });

  test("V and shift+V drive the addressed row from the keyboard", async ({
    page,
  }) => {
    await openCubePart(page);
    const solid = await settled(page, () => canvasBands(page));

    // Address the body by its eye (which also hides it), then drive the rest
    // from the keyboard — no pointer, no editor opened.
    await page.getByTestId("body-visibility-0").click();
    const hidden = await settled(page, () => canvasBands(page));
    expect(hidden.bright).toBeLessThan(solid.bright * 0.02);

    // Shift+V is the way BACK whenever anything is hidden, so the one
    // accelerator can never strand a modeler in an empty scene.
    await page.keyboard.press("Shift+V");
    const restored = await settled(page, () => canvasBands(page));
    expect(restored.bright).toBeGreaterThan(solid.bright * 0.8);

    // …and plain V hides the same addressed row again.
    await page.keyboard.press("v");
    const again = await settled(page, () => canvasBands(page));
    expect(again.bright).toBeLessThan(solid.bright * 0.02);
  });

  test("view state changes nothing the document knows", async ({ page }) => {
    await openCubePart(page);
    const volume = await page.getByTestId("prop-volume").textContent();

    await page.getByTestId("body-visibility-0").click();
    await page.getByTestId("origin-plane-XZ").click();

    // The solve, the tree and the export gate are untouched: this is VIEW
    // state, client-only, unversioned.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved");
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    await expect(page.getByTestId("part-export-step")).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(await page.getByTestId("prop-volume").textContent()).toBe(volume);
  });

  // Founder evidence at both widths the quality floor names. The 1440 frames
  // are captured inside the functional tests above (a screenshot of a state no
  // assertion reached is a screenshot of nothing); these are the small-laptop
  // twins, where a browser that grew two sections has the least room to spare.
  for (const width of [1440, 1366]) {
    test(`founder shots — the part browser at ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await openCubePart(page);

      // XZ + YZ read against a solid far better than XY, which lies in the
      // base face of anything sitting on the bench.
      await page.getByTestId("origin-plane-XZ").click();
      await page.getByTestId("origin-plane-YZ").click();
      await page.getByTestId("origin-axis-Z").click();
      await page
        .getByTestId(/^sketch-visibility-/)
        .first()
        .click();
      await page.waitForTimeout(600);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/uiw2-part-origin-after-${width}.png`,
      });

      await page.getByTestId("body-visibility-0").click();
      await page.waitForTimeout(600);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/uiw2-part-hidden-after-${width}.png`,
      });

      await page.getByTestId("body-opacity-ghost").click();
      await page.waitForTimeout(600);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/uiw2-part-ghost-after-${width}.png`,
      });
    });
  }
});
