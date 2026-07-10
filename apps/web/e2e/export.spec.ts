import { readFile, stat } from "node:fs/promises";

import { expect, test, type Page } from "@playwright/test";

import { expectRenderedModel, SCREENSHOT_DIR, seedSession } from "./support";

// The modeler now lives behind sign-in; every spec gets a fresh session.
test.beforeEach(async ({ page }) => {
  await seedSession(page);
});

/** The first-light box must be meshed before its export can mean anything. */
async function waitForModel(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByTestId("tessellation-status")).toHaveText(
    "Up to date",
    { timeout: 30_000 },
  );
  await expect(page.getByTestId("export-status")).toHaveText("Ready");
}

test.describe("STEP/STL export", () => {
  test("STEP cell downloads box.step with real ISO-10303-21 content", async ({
    page,
  }) => {
    await waitForModel(page);

    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId("export-step").click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toBe("box.step");
    const path = await download.path();
    const content = await readFile(path, "utf-8");
    // A real STEP part 21 file, straight from OCCT via the gateway proxy.
    expect(content.startsWith("ISO-10303-21")).toBe(true);
    expect(content).toContain("END-ISO-10303-21");

    await expect(page.getByTestId("export-status")).toHaveText("Ready");
    await expect(page.getByTestId("export-error")).toHaveCount(0);
  });

  test("STL export works keyboard-only and delivers the binary mesh", async ({
    page,
  }) => {
    await waitForModel(page);

    // Keyboard-first: focus the cell and press Enter — no pointer involved.
    await page.getByTestId("export-stl").focus();
    const downloadPromise = page.waitForEvent("download");
    await page.keyboard.press("Enter");
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toBe("box.stl");
    const path = await download.path();
    const { size } = await stat(path);
    expect(size).toBeGreaterThan(0);
    // Binary STL of the 12-triangle box: 84-byte header + 12 × 50 bytes.
    expect(size).toBe(684);

    await expect(page.getByTestId("export-status")).toHaveText("Ready");
  });

  test("a failed export shows the flag state and recovers", async ({
    page,
  }) => {
    await waitForModel(page);

    const EXPORT = "**/api/v1/geometry/export";
    await page.route(EXPORT, (route) => route.abort("connectionrefused"));
    await page.getByTestId("export-step").click();

    await expect(page.getByTestId("export-status")).toHaveText("Failed");
    await expect(page.getByTestId("export-error")).toContainText(
      "Export failed — the STEP file could not be written.",
    );

    // Recovery: un-break the wire and export again.
    await page.unroute(EXPORT);
    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId("export-step").click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("box.step");
    await expect(page.getByTestId("export-status")).toHaveText("Ready");
    await expect(page.getByTestId("export-error")).toHaveCount(0);
  });
});

test.describe("small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("export row is visible and downloads at 1280×800 (founder shot)", async ({
    page,
  }) => {
    await waitForModel(page);
    await expectRenderedModel(page);
    await expect(page.getByTestId("export-controls")).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/export-control.png`,
    });

    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId("export-step").click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("box.step");
  });
});
