import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";

import { setupTwoInstances, waitForSolved } from "./assemblyFlow";
import { pickHoleCentres } from "./jointFlow";

/**
 * The fix for QA's `assembly-unresolved-export.spec.ts`: once a joint stops
 * resolving, the assembly's export says "Partial" and names it, a format click
 * asks once ("Export anyway — parts at their last solved or initial
 * positions"), the file it then writes is named partial, and a drawing of the
 * assembly carries the same warning onto the sheet. While a re-solve is in
 * flight the export waits ("Solving…") rather than reading "Ready" over a pose
 * it has not seen.
 *
 * Same fixture as QA's spec: two hole plates, a revolute joint through the
 * hole centres, then the hole moved 2 mm in the part's sketch.
 */

/** Two plates joined by a solved revolute joint; returns the ids to edit. */
async function solvedHinge(
  page: Page,
): Promise<{ auth: Record<string, string>; assemblyId: string; idB: string }> {
  const { idA, idB, token, assemblyId } = await setupTwoInstances(page);
  await pickHoleCentres(page, idA, idB);
  await page.getByTestId("joint-motion-revolute").click();
  await page.getByTestId("joint-ok").click();
  await expect(page.getByTestId("mate-row")).toHaveCount(1, {
    timeout: 30_000,
  });
  await waitForSolved(page);
  await expect(page.getByTestId("assembly-export-status")).toHaveText("Ready");
  return { auth: { Authorization: `Bearer ${token}` }, assemblyId, idB };
}

/** Move the plate's hole 2 mm: the joint's origin no longer resolves. */
async function moveHole(
  page: Page,
  auth: Record<string, string>,
  assemblyId: string,
): Promise<void> {
  const graph = (await (
    await page.request.get(`/api/v1/assemblies/${assemblyId}`, {
      headers: auth,
    })
  ).json()) as { instances: Array<{ ref_document_id: string }> };
  const partId = graph.instances[0]?.ref_document_id ?? "";
  const tree = (await (
    await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: auth,
    })
  ).json()) as {
    tree_version: number;
    features: Array<{
      id: string;
      feature: {
        params: {
          entities: Array<{ kind: string; center?: { x: number } }>;
        };
      };
    }>;
  };
  const sketch = tree.features[0];
  const circle = sketch?.feature.params.entities.find(
    (e) => e.kind === "circle",
  );
  if (sketch === undefined || circle?.center === undefined) {
    throw new Error("the plate has no hole circle");
  }
  circle.center.x += 2;
  const patch = await page.request.patch(
    `/api/v1/parts/${partId}/features/${sketch.id}`,
    {
      data: {
        expected_tree_version: tree.tree_version,
        feature: sketch.feature,
      },
      headers: auth,
    },
  );
  expect(patch.ok(), await patch.text()).toBe(true);
}

/** Assembly → Drawing → the four standard views laid out. */
async function layOutDrawing(page: Page): Promise<void> {
  await page.getByTestId("assembly-drawing").click();
  await expect(page).toHaveURL(/\/drawings\/[0-9a-f-]+\?source=/, {
    timeout: 30_000,
  });
  await page.getByTestId("drawing-autolayout").click();
  await expect(page.locator('[data-testid="drawing-view"]')).toHaveCount(4, {
    timeout: 60_000,
  });
}

test.describe("a partial assembly export", () => {
  test("says Partial, asks once, and marks the file and the drawing", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const { auth, assemblyId, idB } = await solvedHinge(page);

    // A re-solve in flight is not "Ready": hold the solve, edit the part,
    // and make a graph write so the page re-solves (review 2026-10-10).
    let release = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/v1/geometry/assembly/evaluate", async (route) => {
      await held;
      await route.continue();
    });
    await moveHole(page, auth, assemblyId);
    await page.getByTestId(`instance-ground-${idB}`).click();
    await expect(page.getByTestId("assembly-export-status")).toHaveText(
      "Solving…",
    );
    await expect(page.getByTestId("assembly-export-step")).toBeDisabled();
    await expect(page.getByTestId("assembly-export-band-step")).toBeDisabled();
    release();
    await page.unroute("**/api/v1/geometry/assembly/evaluate");

    await page.reload();
    await waitForSolved(page);
    await expect(page.getByTestId("mate-row").first()).toContainText(
      "unresolved",
      { timeout: 30_000 },
    );

    // The strip: the word, the count and the kind, and the sentence.
    await expect(page.getByTestId("assembly-export-status")).toHaveText(
      "Partial · 1 joint unresolved",
    );
    await expect(page.getByTestId("assembly-export-controls")).toHaveAttribute(
      "data-export-state",
      "partial",
    );
    await expect(page.getByTestId("assembly-export-notice")).toContainText(
      "last solved or initial positions",
    );
    // The band says it too, on every cell.
    await expect(page.getByTestId("assembly-export-band-step")).toContainText(
      "1 joint unresolved",
    );

    // One click asks; nothing is written until the user says so.
    let downloads = 0;
    page.on("download", () => {
      downloads += 1;
    });
    await page.getByTestId("assembly-export-step").click();
    const confirm = page.getByTestId("assembly-export-confirm");
    await expect(confirm).toBeVisible();
    await expect(confirm).toContainText("1 joint unresolved");
    await page.getByTestId("assembly-export-confirm-cancel").click();
    await expect(confirm).toBeHidden();
    expect(downloads).toBe(0);

    await page.getByTestId("assembly-export-step").click();
    const pending = page.waitForEvent("download");
    await page
      .getByRole("button", {
        name: "Export anyway — parts at their last solved or initial positions",
      })
      .click();
    const file = await pending;
    expect(file.suggestedFilename()).toMatch(/-partial\.step$/);
    await expect(confirm).toBeHidden();

    // A drawing of this assembly carries the same warning onto the sheet.
    await layOutDrawing(page);
    const notice = page.getByTestId("drawing-assembly-partial");
    await expect(notice).toBeVisible({ timeout: 30_000 });
    await expect(notice).toContainText("1 joint unresolved");
    await expect(notice).toContainText("last solved or initial positions");
  });

  test("a sheet laid out before the edit warns after Reproject", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const { auth, assemblyId } = await solvedHinge(page);

    await layOutDrawing(page);
    const notice = page.getByTestId("drawing-assembly-partial");
    await expect(page.getByTestId("drawing-sheet")).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expect(notice).toHaveCount(0);

    // Edit the part, then re-project: the paper is recomposed from the new
    // solve, and the warning must be read from that solve, not a cached one
    // (review 2026-10-10).
    await moveHole(page, auth, assemblyId);
    await page.getByTestId("drawing-reproject").click();
    await expect(notice).toBeVisible({ timeout: 60_000 });
    await expect(notice).toContainText("1 joint unresolved");
  });
});
