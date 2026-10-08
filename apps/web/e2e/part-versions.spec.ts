import { expect, test, type Page } from "./fixtures";

import { seedCube } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * NAMED VERSIONS in the part workspace (LOFT-VERSIONS, docs/FILE-FORMAT.md):
 * save "v1" from the export strip, change the extrude depth, save "v2", then
 * restore v1 from the Versions panel and see the depth and the body come
 * back; Ctrl+Z undoes the restore, because a restore is one undoable edit.
 *
 * The depth is read twice over: from the stored tree (the API) and from the
 * inspector's volume (the rebuilt body on screen).
 */

async function storedDepthMm(
  page: Page,
  partId: string,
  token: string,
): Promise<number | undefined> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const tree = (await response.json()) as {
    features: { feature: { type: string; params: { distance_mm?: number } } }[];
  };
  return tree.features.find((f) => f.feature.type === "extrude")?.feature.params
    .distance_mm;
}

/** Name the version in the open Save version dialog; Enter submits. */
async function nameVersion(page: Page, name: string): Promise<void> {
  const dialog = page.getByRole("dialog", { name: "Save version" });
  await expect(dialog).toBeVisible();
  const field = dialog.getByLabel("Name");
  await expect(field).toBeFocused();
  await field.fill(name);
  await field.press("Enter");
  await expect(dialog).toBeHidden({ timeout: 30_000 });
}

test.describe("part versions", () => {
  test("save, restore and undo a named version", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Versioned block");
    await seedCube(page, account.token, part.id);
    await page.goto(`/parts/${part.id}`);
    const volume = page.getByTestId("prop-volume");
    await expect(volume).toContainText("8,000", { timeout: 30_000 });

    // Save "v1" at 20 mm from the Versions panel, reached from the export
    // strip's status line.
    await page.getByTestId("part-versions").click();
    const panel = page.getByRole("dialog", { name: /Versions/ });
    await expect(panel.getByTestId("versions-empty")).toBeVisible();
    await panel.getByRole("button", { name: "Save version…" }).click();
    await nameVersion(page, "v1");
    await expect(panel.getByTestId("version-row")).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();

    // Ctrl+S opens the same dialog; Escape cancels it without saving.
    await page.keyboard.press("Control+s");
    await expect(page.getByTestId("save-version-dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("save-version-dialog")).toBeHidden();

    // Change the depth to 35 mm through the extrude editor.
    await page.getByTestId("feature-select-1").click();
    const distance = page.getByTestId("extrude-distance");
    await expect(distance).toHaveValue("20");
    await distance.fill("35");
    await distance.press("Enter");
    await expect
      .poll(() => storedDepthMm(page, part.id, account.token), {
        timeout: 30_000,
      })
      .toBe(35);
    await expect(volume).toContainText("14,000", { timeout: 30_000 });
    await expect(page.getByTestId("extrude-editor")).toBeHidden();

    // Save "v2" at 35 mm with Ctrl+S, Fusion's chord.
    await page.keyboard.press("Control+s");
    await nameVersion(page, "v2");

    // The panel lists both, newest first.
    await page.getByTestId("part-versions").click();
    await expect(panel).toBeVisible();
    const rows = panel.getByTestId("version-row");
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0).getByTestId("version-name")).toHaveText("v2");
    await expect(rows.nth(1).getByTestId("version-name")).toHaveText("v1");
    await expect(rows.nth(0).getByTestId("version-age")).toHaveText("just now");
    await page.mouse.move(0, 0);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/part-versions-panel-desktop.png`,
    });

    // Restore v1: it asks first, and says Undo brings the current tree back.
    await panel.getByRole("button", { name: "Restore V1, v1" }).click();
    await expect(panel.getByTestId("version-confirm")).toContainText(
      "brings the current tree back",
    );
    // Enter on the focused confirm restores.
    await expect(panel.getByTestId("version-restore-confirm")).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(panel).toBeHidden({ timeout: 30_000 });
    await expect
      .poll(() => storedDepthMm(page, part.id, account.token), {
        timeout: 30_000,
      })
      .toBe(20);
    await expect(volume).toContainText("8,000", { timeout: 30_000 });
    await expect(page.getByTestId("feature-row")).toHaveCount(2);

    // Ctrl+Z undoes the restore: v2's depth and body are back.
    await page.keyboard.press("Control+z");
    await expect
      .poll(() => storedDepthMm(page, part.id, account.token), {
        timeout: 30_000,
      })
      .toBe(35);
    await expect(volume).toContainText("14,000", { timeout: 30_000 });

    // The editor agrees with the stored tree.
    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("extrude-distance")).toHaveValue("35");
  });
});
