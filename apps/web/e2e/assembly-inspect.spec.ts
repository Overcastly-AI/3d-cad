import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "./fixtures";

import { setupTwoInstances, waitForSolved } from "./assemblyFlow";
import { SCREENSHOT_DIR } from "./support";

/**
 * Assembly inspection exit gate — export + interference, driven end to end
 * through a real browser against the real stack (gateway + documents +
 * geometry, no mocks). Both were shipped-but-headless backend capabilities
 * (engineering audit E2); this proves the buttons are wired to the real
 * endpoints and render real results.
 *
 * The two instances seed APART (x ≈ 80) → a clean assembly. Moving the free
 * instance onto the grounded one (via the instance PATCH, then a reload so the
 * graph refetches) forces a deterministic overlap the clash scan must flag.
 */

/** Read the assembly's current concurrency token from the graph GET. */
async function docVersion(
  page: Page,
  token: string,
  assemblyId: string,
): Promise<number> {
  const res = await page.request.get(`/api/v1/assemblies/${assemblyId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok()) {
    throw new Error(`graph GET failed: ${res.status()} ${await res.text()}`);
  }
  return ((await res.json()) as { doc_version: number }).doc_version;
}

test.describe("Assembly inspect — export + interference", () => {
  test("exports the solved assembly as a STEP file", async ({ page }) => {
    await setupTwoInstances(page);

    const step = page.getByTestId("assembly-export-step");
    await expect(step).toBeVisible();
    await expect(page.getByTestId("assembly-export-status")).toHaveText(
      "Ready",
    );

    const downloadPromise = page.waitForEvent("download");
    await step.click();
    const download = await downloadPromise;
    // Named after the ASSEMBLY, inside and out (audit N4): the download is
    // `bolted-plates.step` and its ROOT PRODUCT carries the document name, so
    // a shop that receives the file can tell what it is — and two assemblies
    // exported in a row do not overwrite each other in Downloads.
    expect(download.suggestedFilename()).toBe("bolted-plates.step");
    const path = await download.path();
    expect(path).toBeTruthy();
    const content = await readFile(path, "utf-8");
    expect(content.startsWith("ISO-10303-21")).toBe(true);
    expect(content).toContain("PRODUCT('Bolted plates'");

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-export-desktop.png`,
    });
  });

  test("reports no interference when parts are apart", async ({ page }) => {
    await setupTwoInstances(page);

    await page.getByTestId("check-interference").click();
    // Running the check reveals the CLASH view.
    await expect(page.getByTestId("assembly-clash")).toBeVisible();
    await expect(page.getByTestId("clash-empty")).toBeVisible({
      timeout: 30_000,
    });

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-clash-empty-desktop.png`,
    });
  });

  test("flags a clash with an overlap volume for overlapping parts", async ({
    page,
  }) => {
    const { idB, token, assemblyId } = await setupTwoInstances(page);

    // Drive the free instance onto the grounded one so their bodies overlap.
    const version = await docVersion(page, token, assemblyId);
    const patch = await page.request.patch(
      `/api/v1/assemblies/${assemblyId}/instances/${idB}`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          expected_version: version,
          placement: {
            position: { x: 0, y: 0, z: 0 },
            orientation: { w: 1, x: 0, y: 0, z: 0 },
          },
        },
      },
    );
    expect(patch.ok()).toBeTruthy();

    // Reload so the graph query refetches the overlapping placement.
    await page.reload();
    await waitForSolved(page);

    await page.getByTestId("check-interference").click();
    await expect(page.getByTestId("clash-row")).toHaveCount(1, {
      timeout: 30_000,
    });

    // The overlap volume reads as a positive number.
    const volume = page.getByTestId("clash-volume").first();
    await expect(volume).toBeVisible();
    const text = (await volume.innerText()).trim().replace(/,/g, "");
    expect(Number.parseFloat(text)).toBeGreaterThan(0);

    // The clashing instance is badged in the tree and flagged in the viewport.
    await expect(page.getByTestId(`instance-clash-${idB}`)).toBeVisible();
    await expect(
      page.locator(`[data-testid="assembly-balloon-${idB}"]`),
    ).toHaveAttribute("data-clashing", "true");

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-clash-found-desktop.png`,
    });
  });
});

test.describe("Assembly inspect — small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("clash panel + export read at 1280×800 (founder shot)", async ({
    page,
  }) => {
    const { idB, token, assemblyId } = await setupTwoInstances(page);

    const version = await docVersion(page, token, assemblyId);
    await page.request.patch(
      `/api/v1/assemblies/${assemblyId}/instances/${idB}`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          expected_version: version,
          placement: {
            position: { x: 0, y: 0, z: 0 },
            orientation: { w: 1, x: 0, y: 0, z: 0 },
          },
        },
      },
    );
    await page.reload();
    await waitForSolved(page);

    await page.getByTestId("check-interference").click();
    await expect(page.getByTestId("clash-row")).toHaveCount(1, {
      timeout: 30_000,
    });

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-clash-found-laptop.png`,
    });
  });
});
