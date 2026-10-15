import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "./fixtures";

import { createPlateWithHoleViaApi, waitForSolved } from "./assemblyFlow";
import { pickHoleCentres } from "./jointFlow";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * BIKE2-FAILED-PART-KILLS-PICKS (blocking), end to end: one part of the
 * assembly fails to build and two good ones do not.
 *
 *  - The failed part's component row says so and links to the part.
 *  - Joint picking still offers the good parts' hole centres, and the armed
 *    picker names the part it cannot offer instead of hanging.
 *  - Edit in Place still offers the good parts' edges to project.
 *  - The BOM flags the part's line.
 *  - Export reads "Partial" naming the part, asks once, and the STEP it then
 *    writes holds the two good occurrences.
 *  - Fixed, the same assembly exports "Ready" with all three.
 *
 * The broken part is the hole plate with one side of its outline removed, so
 * its extrude has no closed profile — the crank arm's `profile_unsupported`
 * at a smaller scale. `LOFT_SHOT_TAG=before|after` writes the screenshots
 * `docs/screenshots/asm-failed-part-<tag>-{row,export}.png`.
 */

const NAUO = /NEXT_ASSEMBLY_USAGE_OCCURRENCE\(/g;

type Auth = Record<string, string>;

interface SketchFeature {
  id: string;
  feature: { params: { entities: Array<{ id: string }> } };
}

/** The part's sketch (first feature) and the tree version to patch it at. */
async function readSketch(
  page: Page,
  auth: Auth,
  partId: string,
): Promise<{ sketch: SketchFeature; version: number }> {
  const tree = (await (
    await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: auth,
    })
  ).json()) as { tree_version: number; features: SketchFeature[] };
  const sketch = tree.features[0];
  if (sketch === undefined) throw new Error("the part has no sketch");
  return { sketch, version: tree.tree_version };
}

async function patchSketch(
  page: Page,
  auth: Auth,
  partId: string,
  sketch: SketchFeature,
  version: number,
): Promise<void> {
  const patch = await page.request.patch(
    `/api/v1/parts/${partId}/features/${sketch.id}`,
    {
      data: { expected_tree_version: version, feature: sketch.feature },
      headers: auth,
    },
  );
  expect(patch.ok(), await patch.text()).toBe(true);
}

/** Add one instance of `partId` through the add-part panel. */
async function addInstance(page: Page, partId: string, count: number) {
  await page.getByTestId(`add-instance-part-${partId}`).click();
  await expect(page.getByTestId("instance-row")).toHaveCount(count, {
    timeout: 15_000,
  });
}

async function shoot(page: Page, name: string): Promise<void> {
  const tag = process.env.LOFT_SHOT_TAG;
  if (!tag) return;
  const target =
    name === "row"
      ? page.getByTestId("assembly-tree")
      : page.getByTestId("assembly-export-controls").locator("..");
  await target.screenshot({
    path: `${SCREENSHOT_DIR}/asm-failed-part-${tag}-${name}.png`,
  });
}

/** Export STEP through the strip; returns the file name and its NAUO count. */
async function exportStep(page: Page, confirmLabel: string | null) {
  await page.getByTestId("assembly-export-step").click();
  const pending = page.waitForEvent("download", { timeout: 90_000 });
  if (confirmLabel !== null) {
    await page.getByRole("button", { name: confirmLabel }).click();
  }
  const file = await pending;
  const path = await file.path();
  const text = await readFile(path, "latin1");
  return {
    name: file.suggestedFilename(),
    occurrences: text.match(NAUO)?.length ?? 0,
  };
}

test.describe("an assembly with a part that failed to build", () => {
  test("keeps the good parts pickable, names the failure, and exports Partial", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    await page.setViewportSize({ width: 1600, height: 1000 });
    const account = await seedSession(page);
    const auth = { Authorization: `Bearer ${account.token}` };
    const good = await createPlateWithHoleViaApi(
      page,
      account.token,
      "Hole plate",
    );
    const crank = await createPlateWithHoleViaApi(
      page,
      account.token,
      "Crank arm",
    );
    // Break the crank arm: drop one side of its outline (an open profile).
    const intact = await readSketch(page, auth, crank.id);
    const original = structuredClone(intact.sketch);
    intact.sketch.feature.params.entities =
      intact.sketch.feature.params.entities.filter((e) => e.id !== "e4");
    await patchSketch(page, auth, crank.id, intact.sketch, intact.version);

    // ---- The assembly: two good plates and the broken arm ------------------
    await page.goto("/assemblies");
    await page.getByTestId("create-assembly-name").fill("Crankset");
    await page.getByTestId("create-assembly-name").press("Enter");
    await page
      .getByTestId("assembly-row")
      .filter({ hasText: "Crankset" })
      .getByTestId("assembly-open")
      .click();
    await expect(page).toHaveURL(/\/assemblies\/[0-9a-f-]+$/);
    const assemblyId = page.url().split("/").pop() ?? "";
    await page.getByTestId("add-instance").click();
    await addInstance(page, good.id, 1);
    await addInstance(page, good.id, 2);
    await addInstance(page, crank.id, 3);
    await page.getByTestId("add-instance-done").click();
    const [idA, idB, idC] = await page
      .getByTestId("instance-row")
      .evaluateAll((rows) =>
        rows.map((r) => (r as HTMLElement).dataset.instanceId ?? ""),
      );
    if (!idA || !idB || !idC) throw new Error("expected three instance ids");
    await waitForSolved(page);
    await shoot(page, "row");
    await shoot(page, "export");

    // ---- The component row names the failure and links to the part --------
    const note = page.getByTestId(`instance-failed-${idC}`);
    await expect(note).toContainText("Crank arm failed to build:", {
      timeout: 30_000,
    });
    await expect(page.getByTestId(`instance-failed-${idA}`)).toHaveCount(0);
    await expect(note.getByTestId("instance-failed-open")).toHaveAttribute(
      "href",
      `/parts/${crank.id}`,
    );

    // ---- Joint picking still works on the good parts ------------------------
    const t0 = Date.now();
    await pickHoleCentres(page, idA, idB);
    const pickMs = Date.now() - t0;
    test.info().annotations.push({
      type: "joint-pick-ms",
      description: String(pickMs),
    });
    // The armed picker says which part it cannot offer, and why.
    const status = page.getByTestId("pick-geometry-failed");
    await expect(status).toHaveCount(1, { timeout: 30_000 });
    await expect(status).toContainText("Crank arm has nothing to pick");
    await expect(status).toContainText("The other parts can be picked.");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("joint-dialog")).toHaveCount(0);

    // ---- The BOM flags the failed part's line -------------------------------
    await page.getByTestId("inspector-view-bom").click();
    const crankLine = page.locator(
      `[data-testid="bom-row"][data-ref-document-id="${crank.id}"]`,
    );
    await expect(crankLine.getByTestId("bom-failed")).toBeVisible();
    await expect(
      page.locator(
        `[data-testid="bom-row"][data-ref-document-id="${good.id}"] [data-testid="bom-failed"]`,
      ),
    ).toHaveCount(0);

    // ---- Export: Partial, named, asks once, writes the two good parts -------
    await expect(page.getByTestId("assembly-export-status")).toHaveText(
      "Partial · Crank arm failed to build",
    );
    await expect(page.getByTestId("assembly-export-controls")).toHaveAttribute(
      "data-export-state",
      "partial",
    );
    await expect(page.getByTestId("assembly-export-notice")).toContainText(
      "the file would leave out 1 body",
    );
    await expect(page.getByTestId("assembly-export-band-stl")).toContainText(
      "Crank arm failed to build",
    );
    await page.getByTestId("assembly-export-step").click();
    const confirm = page.getByTestId("assembly-export-confirm");
    await expect(confirm).toContainText("Crank arm failed to build.");
    await page.getByTestId("assembly-export-confirm-cancel").click();
    await expect(confirm).toBeHidden();
    const partial = await exportStep(page, "Export anyway — without Crank arm");
    expect(partial.name).toMatch(/-partial\.step$/);
    expect(partial.occurrences).toBe(2);

    // ---- Edit in Place on a good plate still offers the others' edges -------
    await page
      .locator(`[data-testid="instance-row"][data-instance-id="${idA}"]`)
      .click({ button: "right" });
    await page.getByTestId("instance-ctx-edit-in-place").click();
    await expect(page).toHaveURL(new RegExp(`/parts/${good.id}\\?context=`));
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    await expect(page.getByTestId("in-context-banner")).toHaveAttribute(
      "data-loading",
      "false",
      { timeout: 60_000 },
    );
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await page.keyboard.press("p");
    const t1 = Date.now();
    await expect(
      page.locator(`[data-testid^="mate-axis-${idB}-"]`).first(),
    ).toBeAttached({ timeout: 30_000 });
    test.info().annotations.push({
      type: "project-edges-ms",
      description: String(Date.now() - t1),
    });

    // ---- Fixed: the same assembly is Ready and exports all three ------------
    const broken = await readSketch(page, auth, crank.id);
    broken.sketch.feature = original.feature;
    await patchSketch(page, auth, crank.id, broken.sketch, broken.version);
    await page.goto(`/assemblies/${assemblyId}`);
    await waitForSolved(page);
    await expect(page.getByTestId("assembly-export-status")).toHaveText(
      "Ready",
      { timeout: 30_000 },
    );
    await expect(page.getByTestId("instance-failed-part")).toHaveCount(0);
    const full = await exportStep(page, null);
    expect(full.name).not.toMatch(/-partial/);
    expect(full.occurrences).toBe(3);
  });
});
