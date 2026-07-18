import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * BACKLOG Interop UI leg (part 2 of 2): the "Import STEP" affordance — the leg
 * that flips the Interop scorecard row ❌→➖. Real stack (gateway + documents +
 * geometry, no mocks). The load-bearing proof: pick a local STEP file → the
 * imported base body renders in BOTH the feature tree and the viewport, and the
 * Import button then disables (import is a base feature, first body only). The
 * error path proves the server envelope surfaces legibly on a bad file.
 *
 * Fixture: the byte-deterministic 10×20×30 box from the geometry golden
 * `import-step-box-10x20x30`, extracted verbatim to `fixtures/box-10x20x30.step`.
 */

const STEP_FIXTURE = fileURLToPath(
  new URL("./fixtures/box-10x20x30.step", import.meta.url),
);

/** The lit aluminium solid + B-rep edges paint far more shades than ground. */
async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/** Open a fresh empty part in the workspace, ready to import onto. */
async function openEmptyPart(page: Page, name: string): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, name);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("import-step-button")).toBeEnabled();
}

test.describe("STEP import", () => {
  test("import a STEP file → body appears in the tree and viewport", async ({
    page,
  }) => {
    await openEmptyPart(page, "Imported box");

    // Pick the local STEP file through the hidden native input.
    await page.getByTestId("import-step-input").setInputFiles(STEP_FIXTURE);

    // The imported base body evaluates and lands in the tree as one row.
    await expect(page.getByTestId("feature-row")).toHaveCount(1);
    await expect(page.getByTestId("feature-row")).toContainText("box-10x20x30");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // The body's mass properties reach the inspector: a 10×20×30 = 6,000 mm³ box.
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("6,000");
    await expect(page.getByTestId("prop-extents")).toContainText(
      "10 × 20 × 30",
    );

    // The solid actually renders in the viewport.
    await expectRenderedBody(page);

    // Import is a BASE feature: with a body present, the affordance disables.
    await expect(page.getByTestId("import-step-button")).toBeDisabled();

    // Reload: the imported body re-evaluates through the real API and holds.
    await page.reload();
    await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);
  });

  test("a non-STEP file surfaces a legible error, no body", async ({
    page,
  }) => {
    await openEmptyPart(page, "Bad import");

    // A file whose bytes lack the ISO-10303-21 header but carries a .step name:
    // the client precheck passes it (right extension), the SERVER rejects it,
    // and its envelope message is surfaced verbatim — nothing swallowed.
    await page.getByTestId("import-step-input").setInputFiles({
      name: "garbage.step",
      mimeType: "application/octet-stream",
      buffer: Buffer.from("this is not a STEP file at all\n"),
    });

    const error = page.getByTestId("import-step-error");
    await expect(error).toBeVisible({ timeout: 30_000 });
    await expect(error).toContainText("Import failed");

    // No body was created — the part is still empty and import stays available.
    await expect(page.getByTestId("body-inspector")).toHaveCount(0);
    await expect(page.getByTestId("import-step-button")).toBeEnabled();

    // Dismiss clears the error surface.
    await page.getByTestId("import-step-dismiss").click();
    await expect(error).toHaveCount(0);
  });

  test("an oversize file is rejected instantly, client-side", async ({
    page,
  }) => {
    await openEmptyPart(page, "Oversize import");

    // 17 MiB of a valid-looking header — over the 16 MiB cap. The client
    // precheck rejects it before any upload (instant feedback).
    const header = "ISO-10303-21;\n";
    const big = header + "x".repeat(17 * 1024 * 1024);
    await page.getByTestId("import-step-input").setInputFiles({
      name: "huge.step",
      mimeType: "application/octet-stream",
      buffer: Buffer.from(big),
    });

    const error = page.getByTestId("import-step-error");
    await expect(error).toBeVisible();
    await expect(error).toContainText("16 MB");
    await expect(page.getByTestId("body-inspector")).toHaveCount(0);
  });
});

test.describe("STEP import — founder screenshots", () => {
  test("empty-part affordance + imported body (desktop)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openEmptyPart(page, "Imported box");

    // The empty part with the Import affordance live in the create strip.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/import-step-affordance-desktop.png`,
    });

    await page.getByTestId("import-step-input").setInputFiles(STEP_FIXTURE);
    await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/import-step-body-desktop.png`,
    });
  });

  test("affordance + imported body at small laptop (1280×800)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await openEmptyPart(page, "Imported box");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/import-step-affordance-laptop.png`,
    });

    await page.getByTestId("import-step-input").setInputFiles(STEP_FIXTURE);
    await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);
    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(560);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/import-step-body-laptop.png`,
    });
  });
});
