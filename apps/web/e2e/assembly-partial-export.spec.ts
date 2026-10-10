import { expect, test } from "./fixtures";

import { setupTwoInstances, waitForSolved } from "./assemblyFlow";
import { pickHoleCentres } from "./jointFlow";

/**
 * The fix for QA's `assembly-unresolved-export.spec.ts`: once a joint stops
 * resolving, the assembly's export says "Partial" and names it, a format click
 * asks once ("Export anyway — parts at their last solved or initial
 * positions"), the file it then writes is named partial, and a drawing of the
 * assembly carries the same warning onto the sheet.
 *
 * Same fixture as QA's spec: two hole plates, a revolute joint through the
 * hole centres, then the hole moved 2 mm in the part's sketch.
 */
test.describe("a partial assembly export", () => {
  test("says Partial, asks once, and marks the file and the drawing", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const { idA, idB, token, assemblyId } = await setupTwoInstances(page);
    const auth = { Authorization: `Bearer ${token}` };

    await pickHoleCentres(page, idA, idB);
    await page.getByTestId("joint-motion-revolute").click();
    await page.getByTestId("joint-ok").click();
    await expect(page.getByTestId("mate-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await waitForSolved(page);
    await expect(page.getByTestId("assembly-export-status")).toHaveText(
      "Ready",
    );

    // Move the hole 2 mm: the joint's origin no longer resolves.
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
    await page.getByTestId("assembly-drawing").click();
    await expect(page).toHaveURL(/\/drawings\/[0-9a-f-]+\?source=/, {
      timeout: 30_000,
    });
    await page.getByTestId("drawing-autolayout").click();
    await expect(page.locator('[data-testid="drawing-view"]')).toHaveCount(4, {
      timeout: 60_000,
    });
    const notice = page.getByTestId("drawing-assembly-partial");
    await expect(notice).toBeVisible({ timeout: 30_000 });
    await expect(notice).toContainText("1 joint unresolved");
    await expect(notice).toContainText("last solved or initial positions");
  });
});
