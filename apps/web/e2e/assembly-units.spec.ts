import { expect, test, type Page } from "./fixtures";

import { setupTwoInstances, waitForSolved } from "./assemblyFlow";
import { SCREENSHOT_DIR } from "./support";

/**
 * The assembly title block honors the document unit (FINDINGS burn-down
 * 2026-07-25 #7). FINDINGS #17 made the PART readouts unit-aware and left the
 * assembly panel hardcoded to mm³/mm²/mm, so one product spoke two
 * conventions: the same solid read `31,391.38 mm³` in an inch assembly and
 * `1.9156 in³` in the part it instanced. Driven against the real stack.
 */

/** Which capture pass this run is (`before` runs against the pre-fix panel). */
const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";

/** Stand up the two-plate assembly and switch the document to inches. */
async function inchAssembly(page: Page): Promise<void> {
  await setupTwoInstances(page);
  await waitForSolved(page);
  const unitSelect = page.getByTestId("document-unit-select");
  await unitSelect.selectOption("in");
  await expect(unitSelect).toHaveValue("in", { timeout: 30_000 });
}

test.describe("assembly readouts follow the document unit", () => {
  test("switching to inches converts volume, centroid and extents", async ({
    page,
  }) => {
    await setupTwoInstances(page);
    await waitForSolved(page);

    const volume = page.getByTestId("assembly-volume");
    await expect(volume).toContainText("mm³");
    const mmVolume = (await volume.innerText()).trim();

    const unitSelect = page.getByTestId("document-unit-select");
    await expect(unitSelect).toHaveValue("mm");
    await unitSelect.selectOption("in");
    await expect(unitSelect).toHaveValue("in", { timeout: 30_000 });

    await expect(volume).toContainText("in³", { timeout: 30_000 });
    await expect(volume).not.toContainText("mm");
    expect((await volume.innerText()).trim()).not.toBe(mmVolume);

    // Two 40×25×10 plates less two Ø10 holes ≈ 18,429 mm³ ≈ 1.12 in³.
    await expect(volume).toContainText("1.12");
    await expect(page.getByTestId("assembly-centroid")).toContainText("in");
    await expect(page.getByTestId("assembly-centroid")).not.toContainText("mm");
    await expect(page.getByTestId("assembly-extents")).toContainText("in");
  });
});

test.describe("founder shots — inch assembly", () => {
  test("inch assembly readouts (1440)", async ({ page }) => {
    await inchAssembly(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-units-in-${SHOT_TAG}-desktop.png`,
    });
  });
});

test.describe("founder shots — inch assembly, small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("inch assembly readouts at laptop width", async ({ page }) => {
    await inchAssembly(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-units-in-${SHOT_TAG}-laptop.png`,
    });
  });
});
