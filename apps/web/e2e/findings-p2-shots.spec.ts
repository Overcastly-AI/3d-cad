import { expect, test, type Page } from "./fixtures";

import { createPlateWithHoleViaApi, setupTwoInstances } from "./assemblyFlow";
import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Founder evidence + behaviour lock for the P2 interaction / jargon clusters
 * (FINDINGS #19, #20). Two reference widths.
 *
 *   1. The discoverable navigation cue (#19c) — a quiet legend teaching
 *      orbit/zoom/pan, dismissible for good.
 *   2. The reworded create gate (#20a) — "Draw a sketch…" replaces the
 *      "Solve a sketch first" solver jargon on the most-hit gate.
 *   3. Assembly-scene depth (#19d) — each part seated on its own contact pool
 *      instead of one flat blob.
 *
 * Shots write only under UPDATE_SCREENSHOTS=1 (the fixtures gate docs/ writes).
 */

const WIDTHS: ReadonlyArray<{ tag: string; width: number; height: number }> = [
  { tag: "desktop", width: 1440, height: 900 },
  { tag: "laptop", width: 1280, height: 800 },
];

async function openFreshPart(page: Page, name: string): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, name);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("viewport")).toBeVisible();
}

for (const { tag, width, height } of WIDTHS) {
  test.describe(`FINDINGS P2 shots (${tag})`, () => {
    test.use({ viewport: { width, height } });

    test("navigation cue is discoverable and dismissible", async ({ page }) => {
      await openFreshPart(page, "Nav cue");

      const cue = page.getByTestId("nav-cue");
      await expect(cue).toBeVisible();
      await expect(cue).toContainText(/orbit/i);
      await expect(cue).toContainText(/zoom/i);
      await expect(cue).toContainText(/pan/i);

      await page.screenshot({
        path: `${SCREENSHOT_DIR}/findings-nav-cue-${tag}.png`,
      });

      // "Got it" retires it for good — gone now and after a reload.
      await page.getByTestId("nav-cue-dismiss").click();
      await expect(cue).toHaveCount(0);
      await page.reload();
      await expect(page.getByTestId("viewport")).toBeVisible();
      await expect(page.getByTestId("nav-cue")).toHaveCount(0);
    });

    test("the extrude gate teaches in plain language", async ({ page }) => {
      await openFreshPart(page, "Gate copy");

      // No sketch yet — the gate holds, but with teaching copy, not "solve".
      const extrude = page.getByTestId("new-extrude");
      await expect(extrude).toHaveAttribute(
        "aria-label",
        "Extrude — draw a sketch first",
      );
      await expect(page.getByTestId("new-revolve")).toHaveAttribute(
        "aria-label",
        "Revolve — draw a sketch first",
      );

      // Surface the reason tooltip for the founder shot.
      await extrude.hover();
      await expect(page.getByText("Draw a sketch to extrude")).toBeVisible();
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/findings-extrude-gate-copy-${tag}.png`,
      });
    });

    test("hovering the body gives a perceptible, quiet warm-up", async ({
      page,
    }) => {
      const account = await seedSession(page);
      const part = await createPlateWithHoleViaApi(
        page,
        account.token,
        "Hover",
      );
      await page.goto(`/parts/${part.id}`);
      await expect(page.getByTestId("viewport")).toBeVisible();
      // The plate mesh has landed once the scene paints many shades.
      await expect
        .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
        .toBeGreaterThan(24);

      const viewport = page.getByTestId("viewport");
      await expect(viewport).toHaveAttribute("data-body-highlight", "none");
      const box = await viewport.boundingBox();
      if (box === null) throw new Error("no viewport box");
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await expect(viewport).toHaveAttribute("data-body-highlight", "hover", {
        timeout: 10_000,
      });

      await page.screenshot({
        path: `${SCREENSHOT_DIR}/findings-body-hover-${tag}.png`,
      });
    });

    test("the assembly scene seats each part on its own pool", async ({
      page,
    }) => {
      await setupTwoInstances(page);
      // The two plates + their contact pools have rendered (setup asserts the
      // solved paint). Capture the grounded scene.
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/findings-assembly-depth-${tag}.png`,
      });
    });
  });
}
