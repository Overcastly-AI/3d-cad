import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

/**
 * CAN THE USER GET A FILE OUT? — the reachability of export, driven against the
 * real stack (EXPORT-1; founder, 2026-08-17: *"the button to export should not
 * be with all the mass properties."*).
 *
 * The defect this spec fences off was not a missing capability. Export worked;
 * it was parented to the Inspector's readout stack, so collapsing that panel —
 * a gesture design mandate 3 actively invites, since the viewport is the hero —
 * removed the only way to issue a file. Measured before the fix, at 1600x1000:
 * with the Inspector collapsed via its own `panel-collapse-inspector` control,
 * `[data-testid="part-export-controls"]` was count 0 / visible false, and the
 * export cell was **53 Tab presses** from the start of the document.
 *
 * So the assertions here are about PLACE, not about STEP: export must be
 * reachable with the panel shut, in both workspaces, without first choosing a
 * tab — and the file that comes out of the band must be the real one.
 */

/** Sketch + extrude a 20 mm cube through the real gateway. */
async function seedCubePart(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Motor mount plate");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part.id;
}

/**
 * How many Tab presses from the start of the document until `testId` holds
 * focus, or null within `limit`.
 *
 * Reload before calling this twice on one page: Chromium remembers the
 * sequential focus navigation starting point, so a second walk resumes from
 * where the first stopped and reports a distance that is too small.
 */
async function tabDistance(
  page: Page,
  testId: string,
  limit = 80,
): Promise<number | null> {
  await page.evaluate(() => (document.activeElement as HTMLElement)?.blur?.());
  for (let i = 1; i <= limit; i += 1) {
    await page.keyboard.press("Tab");
    const hit = await page.evaluate(
      (id) => document.activeElement?.getAttribute("data-testid") === id,
      testId,
    );
    if (hit) return i;
  }
  return null;
}

test.describe("Export is reachable", () => {
  test("survives collapsing the Inspector, and writes a real STEP", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });

    // Both surfaces agree about the same body, from the same derivation.
    await expect(page.getByTestId("part-export-band-controls")).toHaveAttribute(
      "data-export-state",
      "ready",
    );
    await expect(page.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "ready",
    );

    // THE AUDIT'S EXACT PROBE: shut the panel with its own control.
    await page.getByTestId("panel-collapse-inspector").click();
    await expect(page.getByTestId("part-export-controls")).toHaveCount(0);
    // ...and the verb is still on screen, still operable.
    const bandStep = page.getByTestId("part-export-band-step");
    await expect(bandStep).toBeVisible();
    await expect(bandStep).toBeEnabled();

    const downloadPromise = page.waitForEvent("download");
    await bandStep.click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.step$/);
    const path = await download.path();
    const content = await readFile(path, "utf-8");
    // A real B-rep from OCCT — the band's button is wired to the same route the
    // panel strip uses, not to a decorative stub (design mandate 3c).
    expect(content.startsWith("ISO-10303-21")).toBe(true);
    expect(content).toContain("END-ISO-10303-21");
  });

  test("is a short Tab walk from the start of the document", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });

    const band = await tabDistance(page, "part-export-band-step");
    expect(band).not.toBeNull();
    // Measured 30 on this exact part at 1600x1000 (the band's last group, after
    // History / Create / Modify / Sheet metal / Inspect), against 53 for the
    // panel cell before this ticket. The bound is deliberately just above the
    // measurement: adding a whole tool GROUP ahead of export should have to be
    // a decision, not an accident.
    expect(band ?? 999).toBeLessThanOrEqual(34);
  });

  test("keeps the panel strip's honest reason in the band when there is no body", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Sketch only");
    await createFeature(page, account.token, part.id, {
      name: "Sketch1",
      feature: { type: "sketch", version: 1, params: SQUARE_20 },
      expected_tree_version: 0,
    });

    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("part-export-band-controls")).toHaveAttribute(
      "data-export-state",
      "no-body",
      { timeout: 30_000 },
    );
    const step = page.getByTestId("part-export-band-step");
    await expect(step).toBeDisabled();
    // The reason is on the CELL, reachable by keyboard and pointer alike — a
    // grey button that will not say why is the same defect one layer down. It
    // rides the DESCRIPTION, not the name (A11Y-TOOLBTN-1): the cell is called
    // the same thing gated or not, so a returning user recognises it.
    await expect(step).toHaveAccessibleName("Export STEP (exact B-rep)");
    await expect(step).toHaveAccessibleDescription(/No body/);
  });

  test("assembly: export without first choosing an inspector tab", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);

    await page.goto("/assemblies");
    await page.getByTestId("create-assembly-name").fill("Bolted plates");
    await page.getByTestId("create-assembly-name").press("Enter");
    const row = page
      .getByTestId("assembly-row")
      .filter({ hasText: "Bolted plates" });
    await expect(row).toBeVisible();
    await row.getByTestId("assembly-open").click();
    await expect(page).toHaveURL(/\/assemblies\/[0-9a-f-]+$/);

    // Before any instance exists the band still shows the verb — inert, and
    // saying why (the affordance is discoverable before it is usable).
    const bandStep = page.getByTestId("assembly-export-band-step");
    await expect(bandStep).toBeVisible();
    await expect(bandStep).toBeDisabled();

    await page.getByTestId("add-instance").click();
    await page.getByTestId(`add-instance-part-${partId}`).click();
    await expect(page.getByTestId("instance-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await page.getByTestId("add-instance-done").click();

    // No Solve / Parts / Clash tab was ever touched.
    await expect(bandStep).toBeEnabled({ timeout: 30_000 });
    const downloadPromise = page.waitForEvent("download");
    await bandStep.click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("bolted-plates.step");
    const content = await readFile(await download.path(), "utf-8");
    expect(content.startsWith("ISO-10303-21")).toBe(true);
  });
});
