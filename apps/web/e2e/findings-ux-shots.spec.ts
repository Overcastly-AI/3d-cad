import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Founder evidence for the UX P1 trio (FINDINGS #11–#13). Screenshot-only —
 * behaviour is locked by mirror.spec / extrude-ui.spec / dimension-expressions.
 * Two surfaces at both reference widths:
 *
 *   1. The contextual dimension hint in the sketch status bar (#12) — selecting
 *      one line surfaces "D · dimension", teaching the previously-invisible
 *      select-then-D path.
 *   2. The corrected open-profile EXTRUDE error copy (#13) — extrude-specific
 *      advice, no longer the shared revolve centerline text.
 *
 * Shots write only under UPDATE_SCREENSHOTS=1 (the fixtures gate docs/ writes).
 */

const WIDTHS: ReadonlyArray<{ tag: string; width: number; height: number }> = [
  { tag: "desktop", width: 1440, height: 900 },
  { tag: "laptop", width: 1280, height: 800 },
];

async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
}

for (const { tag, width, height } of WIDTHS) {
  test.describe(`FINDINGS UX shots (${tag})`, () => {
    test.use({ viewport: { width, height } });

    test("dimension hint appears on a selected line", async ({ page }) => {
      const account = await seedSession(page);
      const part = await createPartViaApi(page, account.token, "Dim hint");
      await page.goto(`/parts/${part.id}`);

      await enterSketch(page, "XY");
      // Draw one line with raw screen clicks, then drop back to the select tool.
      const a = { x: Math.round(width * 0.42), y: Math.round(height * 0.5) };
      const b = { x: Math.round(width * 0.68), y: Math.round(height * 0.5) };
      await page.keyboard.press("l");
      await page.mouse.click(a.x, a.y);
      await page.mouse.click(b.x, b.y);
      await page.keyboard.press("Escape"); // back to select
      // Select the line at its screen midpoint.
      await page.mouse.click(Math.round((a.x + b.x) / 2), a.y);
      await expect(page.getByTestId("selection-readout")).toContainText(
        "1 ent",
      );
      const hint = page.getByTestId("dimension-hint");
      await expect(hint).toBeVisible();
      await expect(hint).toContainText("D");
      await expect(hint).toContainText("dimension");

      await page.screenshot({
        path: `${SCREENSHOT_DIR}/findings-dimension-hint-${tag}.png`,
      });
    });

    test("open-profile extrude shows extrude-specific advice", async ({
      page,
    }) => {
      const account = await seedSession(page);
      const part = await createPartViaApi(
        page,
        account.token,
        "Extrude advice",
      );
      await page.goto(`/parts/${part.id}`);

      // An open two-line path — a valid sketch with no closed face.
      await enterSketch(page, "XY");
      await page.keyboard.press("l");
      await page.mouse.click(640, 620);
      await page.mouse.click(940, 620);
      await page.mouse.click(940, 620);
      await page.mouse.click(940, 420);
      await expect(page.getByTestId("sketch-save")).toContainText("2 entities");
      await page.getByTestId("sketch-save").click();
      await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
      await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
        timeout: 30_000,
      });

      await page.getByTestId("new-extrude").click();
      await page.getByTestId("extrude-distance").press("Enter");
      await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
        timeout: 30_000,
      });
      const error = page.getByTestId("feature-error-1");
      await expect(error).toContainText("profile_not_closed");
      await expect(error).toContainText(/extrude/i);
      await expect(error).not.toContainText(/centerline|axis/i);

      await page.screenshot({
        path: `${SCREENSHOT_DIR}/findings-extrude-error-${tag}.png`,
      });
    });
  });
}
