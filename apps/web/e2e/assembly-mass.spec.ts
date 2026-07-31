import { expect, test, type Page } from "./fixtures";

import { setupTwoInstances, waitForSolved } from "./assemblyFlow";
import { SCREENSHOT_DIR } from "./support";

/**
 * THE ASSEMBLY'S COMBINED-MASS CLAIM (materials.md §6.1, at its second
 * address).
 *
 * The panel carried a section headed COMBINED MASS that reported Volume /
 * Area / Centroid and no mass — the identical overstated title #57b removed
 * from the part inspector. Both halves are driven here through the real stack:
 * with no material anywhere the section must not promise mass and must say why
 * there is none, and once the referenced part HAS a material the same section
 * earns the words and shows a real number.
 *
 * The roll-up's rule is what makes the first state normal rather than exotic:
 * `mass_g` is null unless EVERY placed instance has a material, because a
 * partial sum would under-report while looking complete.
 */
const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";

/** The part's current tree version — the assignment PATCH's concurrency guard. */
async function treeVersion(
  page: Page,
  token: string,
  partId: string,
): Promise<number> {
  const res = await page.request.get(`/api/v1/parts/${partId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok()) throw new Error(`part GET failed: ${res.status()}`);
  return ((await res.json()) as { tree_version: number }).tree_version;
}

test.describe("assembly combined mass — 1440x900", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("promises mass only once every component has a material", async ({
    page,
  }) => {
    const { token, assemblyId } = await setupTwoInstances(page);
    const inspector = page.getByTestId("assembly-inspector");
    await expect(inspector).toBeVisible();

    // Shot FIRST, assertions after: run against HEAD~ the same spec captures the
    // BEFORE state (a section headed COMBINED MASS with no mass in it).
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-mass-${SHOT_TAG}-1440.png`,
    });

    // NO material anywhere — the shipped default state of every assembly.
    await expect(inspector).not.toContainText("Combined mass");
    await expect(inspector).toContainText("Combined properties");
    await expect(page.getByTestId("assembly-mass")).toHaveCount(0);
    // Absence is stated, and it is never a zero.
    await expect(page.getByTestId("assembly-mass-notice")).toContainText(
      "no total mass",
    );
    await expect(inspector).not.toContainText("0 g");
    // ...while the numbers it CAN report are still reported.
    await expect(page.getByTestId("assembly-volume")).not.toHaveText("—");

    // Give the referenced part a material, through the real assignment route.
    const graph = await page.request.get(`/api/v1/assemblies/${assemblyId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const target =
      ((await graph.json()) as { instances: { ref_document_id: string }[] })
        .instances[0]?.ref_document_id ?? "";
    expect(target).not.toBe("");
    const patch = await page.request.patch(`/api/v1/parts/${target}`, {
      data: {
        materials: { default_material: "aluminium_6061", bodies: [] },
        expected_tree_version: await treeVersion(page, token, target),
      },
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(patch.ok()).toBe(true);

    await page.goto(`/assemblies/${assemblyId}`);
    await waitForSolved(page);

    // The words are earned, and the number is real (two 40x25x10 plates with a
    // Ø10 bore, 6061 at 2.70 g/cm³ — tens of grams, not zero, not a dash).
    await expect(page.getByTestId("assembly-inspector")).toContainText(
      "Combined mass",
      { timeout: 30_000 },
    );
    const mass = page.getByTestId("assembly-mass");
    await expect(mass).toBeVisible();
    const reading = Number(
      (await mass.textContent())?.replace(/[^0-9.]/g, "") ?? "0",
    );
    expect(reading).toBeGreaterThan(0);
    await expect(page.getByTestId("assembly-mass-notice")).toHaveCount(0);
    // A mass-weighted centre appears beside the volume centroid, named apart.
    await expect(page.getByTestId("assembly-center-of-mass")).toBeVisible();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-mass-after-material-1440.png`,
    });
  });
});
