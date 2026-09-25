import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

/**
 * A 3MF OF A DENSE TWIST SAYS WHAT TO DO INSTEAD (MESH-TOO-DENSE-COPY-1).
 *
 * The geometry service refuses a 3MF of a many-turn twisted body as
 * `export_mesh_too_dense` (`4c49218`): lib3mf re-meshes a copy of the body at
 * full cost. STL and STEP of the same body are fine. Before this, the band said
 * "Failed — check the gateway, then retry", which sends the user to the wrong
 * place. Driven against the real stack for both surfaces that export: the part
 * workspace and the assembly workspace.
 */

const TOO_DENSE =
  "This twisted body is too dense to write as 3MF in reasonable time. " +
  "Export STL or STEP instead, or reduce the twist.";

/** Two full turns over 30 mm: the geometry suite's refused 3MF case. */
async function seedDenseTwist(page: Page, token: string): Promise<string> {
  const part = await createPartViaApi(page, token, "Twisted column");
  const sketch = await createFeature(page, token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  await createFeature(page, token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 30,
        operation: "add",
        direction: "normal",
        twist_angle_deg: 720,
        twist_center: { x: 10, y: 10 },
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part.id;
}

test.describe("a refused 3MF names the cure", () => {
  test("in the part workspace", async ({ page }) => {
    const account = await seedSession(page);
    const partId = await seedDenseTwist(page, account.token);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("part-export-band-controls")).toHaveAttribute(
      "data-export-state",
      "ready",
      { timeout: 60_000 },
    );

    const cell = page.getByTestId("part-export-band-3mf");
    await cell.click();
    await expect(page.getByTestId("part-export-band-error")).toHaveText(
      TOO_DENSE,
      { timeout: 60_000 },
    );
    await expect(cell).toContainText("Too dense — use STL or STEP");

    // The cure is real: STL of the same body downloads.
    const pending = page.waitForEvent("download");
    await page.getByTestId("part-export-band-stl").click();
    expect((await pending).suggestedFilename()).toMatch(/\.stl$/);
  });

  test("in the assembly workspace", async ({ page }) => {
    const account = await seedSession(page);
    const partId = await seedDenseTwist(page, account.token);
    await page.goto("/assemblies");
    await page.getByTestId("create-assembly-name").fill("Twisted rack");
    await page.getByTestId("create-assembly-name").press("Enter");
    const row = page
      .getByTestId("assembly-row")
      .filter({ hasText: "Twisted rack" });
    await expect(row).toBeVisible();
    await row.getByTestId("assembly-open").click();
    await expect(page).toHaveURL(/\/assemblies\/[0-9a-f-]+$/);
    await page.getByTestId("add-instance").click();
    await page.getByTestId(`add-instance-part-${partId}`).click();
    await expect(page.getByTestId("instance-row")).toHaveCount(1, {
      timeout: 60_000,
    });
    await page.getByTestId("add-instance-done").click();

    const cell = page.getByTestId("assembly-export-band-3mf");
    await expect(cell).toBeEnabled({ timeout: 60_000 });
    await cell.click();
    await expect(page.getByTestId("assembly-export-band-error")).toHaveText(
      TOO_DENSE,
      { timeout: 60_000 },
    );
    await expect(cell).toContainText("Too dense — use STL or STEP");
  });
});
