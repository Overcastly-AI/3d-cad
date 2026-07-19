import { expect, test } from "./fixtures";

import { createPlateWithHoleViaApi } from "./assemblyFlow";
import { seedSession, SCREENSHOT_DIR } from "./support";

/**
 * Assemblies — the bill-of-materials panel exit gate. Driven end to end through
 * a real browser against the real stack (gateway + documents + geometry): two
 * DISTINCT plate parts are built via the API, then instanced into a fresh
 * assembly through the UI — part A three times, part B once. Switching the
 * right instrument to PARTS surfaces the flat BOM read model: one line per
 * referenced document, quantity = the shared-reference count, deterministically
 * ordered, with a summed total. This asserts the two lines, their quantities
 * (3 and 1), and the total (4) — the aggregation the founder sees.
 */

test.describe("Assemblies — bill of materials", () => {
  test("instance A×3 + B×1, open PARTS, see two lines and the total", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const partA = await createPlateWithHoleViaApi(
      page,
      account.token,
      "Bracket plate",
    );
    const partB = await createPlateWithHoleViaApi(
      page,
      account.token,
      "Cover plate",
    );

    // Open a fresh assembly from the register.
    await page.goto("/assemblies");
    await page.getByTestId("create-assembly-name").fill("BOM demo");
    await page.getByTestId("create-assembly-name").press("Enter");
    const row = page
      .getByTestId("assembly-row")
      .filter({ hasText: "BOM demo" });
    await expect(row).toBeVisible();
    await row.getByTestId("assembly-open").click();
    await expect(page).toHaveURL(/\/assemblies\/[0-9a-f-]+$/);

    // Add three instances of part A, then one of part B, via the add panel.
    await page.getByTestId("add-instance").click();
    await expect(page.getByTestId("add-instance-panel")).toBeVisible();
    const cellA = page.getByTestId(`add-instance-part-${partA.id}`);
    const cellB = page.getByTestId(`add-instance-part-${partB.id}`);
    for (let n = 1; n <= 3; n++) {
      await cellA.click();
      await expect(page.getByTestId("instance-row")).toHaveCount(n, {
        timeout: 15_000,
      });
    }
    await cellB.click();
    await expect(page.getByTestId("instance-row")).toHaveCount(4, {
      timeout: 15_000,
    });
    await page.getByTestId("add-instance-done").click();

    // Switch the right instrument from SOLVE to PARTS.
    await page.getByTestId("inspector-view-bom").click();
    const bom = page.getByTestId("bom-panel");
    await expect(bom).toBeVisible();

    // Two lines — one per referenced document — and the summed total.
    await expect(page.getByTestId("bom-row")).toHaveCount(2);
    const rowA = page.locator(
      `[data-testid="bom-row"][data-ref-document-id="${partA.id}"]`,
    );
    const rowB = page.locator(
      `[data-testid="bom-row"][data-ref-document-id="${partB.id}"]`,
    );
    await expect(rowA.getByTestId("bom-quantity")).toHaveText("3");
    await expect(rowB.getByTestId("bom-quantity")).toHaveText("1");
    await expect(rowA.getByTestId("bom-name")).toHaveText("Bracket plate");
    await expect(rowB.getByTestId("bom-name")).toHaveText("Cover plate");
    await expect(page.getByTestId("bom-total")).toHaveText("4");

    // Founder shot: the bill of materials in the assembly workspace.
    await page.mouse.move(1400, 900);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-bom-desktop.png`,
    });
  });
});
