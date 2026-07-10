import { expect, test } from "@playwright/test";

const TESSELLATE = "**/api/v1/geometry/tessellate";

/**
 * The worst CAD failure mode is a wrong model on screen: a corrupt GLB with
 * a valid X-Loft-Properties header would previously leave the previous mesh
 * rendered while the inspector showed fresh numbers. The viewport must clear
 * the stale mesh and surface a visible error instead.
 */
test("corrupt GLB clears the stale mesh and shows the rejection stamp", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByTestId("tessellation-status")).toHaveText(
    "Up to date",
    { timeout: 30_000 },
  );
  await expect(page.getByTestId("viewport-error")).toHaveCount(0);

  // Corrupt the mesh bytes but keep the real headers — the inspector metadata
  // stays "fresh" while the GLB is garbage (the exact hazard under test).
  await page.route(TESSELLATE, async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      body: Buffer.from([0x67, 0x6c, 0x54, 0x46, 2, 0, 0, 0]), // truncated GLB
    });
  });

  const field = page.getByTestId("dim-x");
  await field.click();
  await field.fill("");
  await field.pressSequentially("15", { delay: 40 });
  await field.press("Enter");

  const stamp = page.getByTestId("viewport-error");
  await expect(stamp).toBeVisible({ timeout: 30_000 });
  await expect(stamp).toContainText("Mesh rejected");
  await expect(stamp).toContainText(
    "The model could not be displayed and was cleared.",
  );

  // Recovery: un-corrupt the wire, re-apply, and the stamp clears.
  await page.unroute(TESSELLATE);
  await field.click();
  await field.fill("");
  await field.pressSequentially("25", { delay: 40 });
  await field.press("Enter");
  await expect(page.getByTestId("prop-extents")).toContainText("25 × 20 × 30", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("viewport-error")).toHaveCount(0, {
    timeout: 15_000,
  });
});
