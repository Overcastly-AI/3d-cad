import { expect, test, type Page } from "./fixtures";

import { setupTwoInstances, waitForSolved } from "./assemblyFlow";
import { SCREENSHOT_DIR, waitForFrames } from "./support";

/**
 * UI-W2 — per-instance visibility / opacity / isolate in the ASSEMBLY
 * workspace (founder: "what about different components enablement, opacity,
 * etc."; design `docs/design/ui-wave-tool-grade.md` Surface 2).
 *
 * The mandate's rule for this wave is 3c: a control that does not move a pixel
 * in the WebGL scene is a defect, not a stub. So the load-bearing assertions
 * here are PIXEL assertions, taken off the real canvas of the real stack — not
 * "the button has aria-pressed=false".
 *
 * The probe splits the canvas into two luminance bands, which is enough to tell
 * the three stops apart without a golden image:
 *
 *   · BRIGHT (> 110) — lit machined-aluminum body. The studio matcap's body
 *     tone is ~163; the bench grid tops out ~76 and the background is
 *     transparent (the atmosphere is painted in the DOM, behind the canvas).
 *   · MID (45…110) — where a GHOSTED body lands: 0.42 x 163 ≈ 68 composited
 *     over the dark bench.
 *
 * Hiding a part therefore drops BRIGHT and does NOT raise MID; ghosting it
 * drops BRIGHT and DOES raise MID. One probe, three distinguishable states.
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

/**
 * Settle the on-demand render loop before sampling the drawing buffer: wait
 * for real PAINTS (`waitForFrames`), not for 400 ms of wall clock, which under
 * load can pass with nothing drawn — the sample would then be the pre-change
 * frame and the numeric assertion below has no auto-retry to save it
 * (docs/BACKLOG.md GATE-1a). Every call here follows a locator assertion that
 * the state change has already committed, so what remains to wait for is the
 * frame, which is exactly what this waits for.
 */
async function settledBands(page: Page): Promise<Bands> {
  await waitForFrames(page);
  return canvasBands(page);
}

test.describe("UI-W2 — per-instance visibility moves the render", () => {
  test("hide, ghost and isolate each change what the viewport draws", async ({
    page,
  }) => {
    const { idA, idB } = await setupTwoInstances(page);
    await waitForSolved(page);

    // Both plates solid: the baseline census.
    const both = await settledBands(page);
    expect(both.bright).toBeGreaterThan(0);

    // --- HIDE (the eye) --------------------------------------------------
    const eyeB = page.getByTestId(`instance-visibility-${idB}`);
    await expect(eyeB).toHaveAttribute("aria-pressed", "true");
    await eyeB.click();
    await expect(eyeB).toHaveAttribute("aria-pressed", "false");
    await expect(
      page.locator(`[data-testid="instance-row"][data-instance-id="${idB}"]`),
    ).toHaveAttribute("data-visibility", "hidden");

    // A hidden instance draws NOTHING — not the body, and not the balloon
    // that would otherwise float over an absent part.
    await expect(page.getByTestId(`assembly-balloon-${idB}`)).toHaveCount(0);
    await expect(page.getByTestId(`assembly-balloon-${idA}`)).toHaveCount(1);

    const hidden = await settledBands(page);
    expect(hidden.bright).toBeLessThan(both.bright * 0.8);

    // --- SHOW again: the render comes back --------------------------------
    await eyeB.click();
    await expect(page.getByTestId(`assembly-balloon-${idB}`)).toHaveCount(1);
    const restored = await settledBands(page);
    expect(restored.bright).toBeGreaterThan(hidden.bright * 1.1);

    // --- GHOST (the opacity stop) -----------------------------------------
    // The three-stop control is disclosed under the ADDRESSED row. Selecting
    // also warms the body toward brass, which moves pixels on its own — so the
    // ghost baseline is taken AFTER the selection, never before it, or the
    // assertion would pass on the selection tint alone.
    await page.getByTestId(`instance-select-${idB}`).click();
    const opacity = page.getByTestId(`instance-opacity-${idB}`);
    await expect(opacity).toBeVisible();
    const selectedSolid = await settledBands(page);

    await opacity.getByTestId("instance-opacity-ghost").click();
    await expect(
      page.locator(`[data-testid="instance-row"][data-instance-id="${idB}"]`),
    ).toHaveAttribute("data-visibility", "ghost");

    const ghosted = await settledBands(page);
    // Translucent: the ghosted plate's lit pixels drop out of the BRIGHT band
    // (0.42 x the studio matcap over a dark bench) and reappear in MID — the
    // part is still THERE, you are seeing through it. Hiding it, by contrast,
    // left MID alone. One probe separates the three stops.
    expect(ghosted.bright).toBeLessThan(selectedSolid.bright * 0.8);
    expect(ghosted.mid).toBeGreaterThan(selectedSolid.mid * 1.1);
    expect(ghosted.mid).toBeGreaterThan(hidden.mid);

    // A ghost is still drawn, so it keeps its balloon.
    await expect(page.getByTestId(`assembly-balloon-${idB}`)).toHaveCount(1);

    // --- The eye preserves the opacity stop --------------------------------
    await eyeB.click();
    await expect(
      page.locator(`[data-testid="instance-row"][data-instance-id="${idB}"]`),
    ).toHaveAttribute("data-visibility", "hidden");
    await eyeB.click();
    await expect(
      page.locator(`[data-testid="instance-row"][data-instance-id="${idB}"]`),
    ).toHaveAttribute("data-visibility", "ghost");

    // Back to solid for the isolate leg.
    await opacity.getByTestId("instance-opacity-solid").click();
    await expect(
      page.locator(`[data-testid="instance-row"][data-instance-id="${idB}"]`),
    ).toHaveAttribute("data-visibility", "solid");
  });

  test("isolate from the row menu, and the stamp is the way back", async ({
    page,
  }) => {
    const { idA, idB } = await setupTwoInstances(page);
    await waitForSolved(page);
    const solid = await settledBands(page);

    // Nothing is hidden → no stamp. Chrome that only decorates is a defect.
    await expect(page.getByTestId("visibility-stamp")).toHaveCount(0);

    // Right-click the component row → the view verbs at the pointer.
    const rowA = page.locator(
      `[data-testid="instance-row"][data-instance-id="${idA}"]`,
    );
    await rowA.click({ button: "right" });
    await expect(page.getByTestId("instance-context-menu")).toBeVisible();
    // The way back is offered but honestly gated: nothing is hidden yet.
    await expect(page.getByTestId("instance-ctx-show-all")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await page.getByTestId("instance-ctx-isolate").click();

    // Only the isolated instance is drawn.
    await expect(page.getByTestId(`assembly-balloon-${idA}`)).toHaveCount(1);
    await expect(page.getByTestId(`assembly-balloon-${idB}`)).toHaveCount(0);
    const isolated = await settledBands(page);
    expect(isolated.bright).toBeLessThan(solid.bright * 0.8);

    // The ISOLATED stamp names what survived and offers the way back.
    const stamp = page.getByTestId("visibility-stamp");
    await expect(stamp).toBeVisible();
    await expect(stamp).toHaveAttribute("data-hidden-count", "1");
    await expect(page.getByTestId("visibility-stamp-label")).toContainText(
      "Isolated",
    );

    // The stamp CARD must not shield the model: pointer events are off on it
    // and on only re-enabled on its one control (a panel that swallows clicks
    // over the viewport was a defect found in review the same day).
    const inert = await stamp.evaluate(
      (el) => getComputedStyle(el).pointerEvents,
    );
    expect(inert).toBe("none");
    const live = await page
      .getByTestId("visibility-show-all")
      .evaluate((el) => getComputedStyle(el).pointerEvents);
    expect(live).toBe("auto");

    await page.getByTestId("visibility-show-all").click();
    await expect(page.getByTestId("visibility-stamp")).toHaveCount(0);
    await expect(page.getByTestId(`assembly-balloon-${idB}`)).toHaveCount(1);
    const shownAgain = await settledBands(page);
    expect(shownAgain.bright).toBeGreaterThan(isolated.bright * 1.1);
  });

  test("keyboard-first: V hides the addressed component, Shift+V isolates and returns", async ({
    page,
  }) => {
    const { idA, idB } = await setupTwoInstances(page);
    await waitForSolved(page);

    const rowB = page.locator(
      `[data-testid="instance-row"][data-instance-id="${idB}"]`,
    );
    await page.getByTestId(`instance-select-${idB}`).click();

    await page.keyboard.press("v");
    await expect(rowB).toHaveAttribute("data-visibility", "hidden");
    await expect(page.getByTestId("visibility-stamp")).toBeVisible();

    await page.keyboard.press("v");
    await expect(rowB).toHaveAttribute("data-visibility", "solid");

    // Shift+V isolates the addressed component…
    await page.keyboard.press("Shift+V");
    await expect(
      page.locator(`[data-testid="instance-row"][data-instance-id="${idA}"]`),
    ).toHaveAttribute("data-visibility", "hidden");
    await expect(page.getByTestId("visibility-stamp")).toBeVisible();

    // …and, with something hidden, the SAME chord is the way back, so the one
    // accelerator can never strand a modeler in an empty scene.
    await page.keyboard.press("Shift+V");
    await expect(page.getByTestId("visibility-stamp")).toHaveCount(0);
    await expect(
      page.locator(`[data-testid="instance-row"][data-instance-id="${idA}"]`),
    ).toHaveAttribute("data-visibility", "solid");
  });

  test("the new controls meet the target floor and take visible focus", async ({
    page,
  }) => {
    const { idB } = await setupTwoInstances(page);
    await waitForSolved(page);

    // `target.dense` (24px) is the product's written floor for a data row's
    // inline verbs. Measured, because a 16px button and a correct one
    // photograph identically (tokens.ts `target`).
    const eye = page.getByTestId(`instance-visibility-${idB}`);
    const eyeBox = await eye.boundingBox();
    expect(eyeBox?.width ?? 0).toBeGreaterThanOrEqual(24);
    expect(eyeBox?.height ?? 0).toBeGreaterThanOrEqual(24);

    // …and it is actually REACHABLE at its own centre (nothing overlays it).
    const reachable = await page.evaluate(
      (box) => {
        const el = document.elementFromPoint(
          box.x + box.width / 2,
          box.y + box.height / 2,
        );
        return el?.closest("[data-testid^='instance-visibility-']") !== null;
      },
      eyeBox ?? { x: 0, y: 0, width: 0, height: 0 },
    );
    expect(reachable).toBe(true);

    await page.getByTestId(`instance-select-${idB}`).click();
    for (const stop of ["solid", "ghost", "hidden"]) {
      const box = await page
        .getByTestId(`instance-opacity-${idB}`)
        .getByTestId(`instance-opacity-${stop}`)
        .boundingBox();
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(24);
    }

    // Keyboard focus is visible — the eye takes a real ring, not a UA default
    // that the token reset removed.
    await eye.focus();
    const outline = await eye.evaluate((el) => {
      const s = getComputedStyle(el);
      return { width: s.outlineWidth, style: s.outlineStyle };
    });
    expect(outline.style).not.toBe("none");
    expect(parseFloat(outline.width)).toBeGreaterThan(0);
  });
});

test.describe("UI-W2 — founder shots", () => {
  for (const [label, width] of [
    ["1440", 1440],
    ["1366", 1366],
  ] as const) {
    test(`ghost + isolate at ${label}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const { idA, idB } = await setupTwoInstances(page);
      await waitForSolved(page);

      // BEFORE: both components solid, no view controls engaged.
      await page.mouse.move(width - 40, 860);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/uiw2-visibility-before-${label}.png`,
      });

      // GHOST: the near plate goes see-through — the "look inside" state.
      // Addressing moves to the OTHER component afterwards so the ghost reads
      // in its own colour (a selected body warms toward brass, which would sell
      // the shot as a preview rather than as a ghost).
      await page.getByTestId(`instance-select-${idB}`).click();
      await page
        .getByTestId(`instance-opacity-${idB}`)
        .getByTestId("instance-opacity-ghost")
        .click();
      await page.getByTestId(`instance-select-${idA}`).click();
      await page.waitForTimeout(500);
      await page.mouse.move(width - 40, 860);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/uiw2-ghost-${label}.png`,
      });

      // ISOLATE: one component kept, the ISOLATED stamp offering the way back.
      await page
        .locator(`[data-testid="instance-row"][data-instance-id="${idA}"]`)
        .click({ button: "right" });
      await page.getByTestId("instance-ctx-isolate").click();
      await expect(page.getByTestId("visibility-stamp")).toBeVisible();
      await page.waitForTimeout(500);
      await page.mouse.move(width - 40, 860);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/uiw2-isolate-${label}.png`,
      });
    });
  }
});
