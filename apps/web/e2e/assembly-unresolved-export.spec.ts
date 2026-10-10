import { expect, test } from "./fixtures";

import { setupTwoInstances, waitForSolved } from "./assemblyFlow";
import { pickHoleCentres } from "./jointFlow";

/**
 * QA 2026-10-10 (blocking): an assembly whose joints stopped resolving after
 * an upstream part edit still reads "Ready" and exports every component at
 * its seed pose, with no warning.
 *
 * In the real app: a hinge of two brackets and a pin at 90°, then the
 * bracket's width parameter 100 -> 80. Both joints showed "unresolved" in the
 * tree, the export band still said "Ready", and the STEP held the brackets
 * side by side at their seeds with the pin overlapping one by 43.6 mm³.
 * A part export in the same state says "Partial" and names the failed
 * feature; an assembly export says nothing.
 *
 * Here: two hole plates, a revolute joint through the hole centres, then the
 * hole is moved 2 mm in the part's sketch. Joint origins resolve on the strict
 * signature tier only (`geometry/assembly/joint_origins.py::_resolve_edge`),
 * so the joint goes unresolved. The export must then say so.
 */
test.describe("assembly export after an upstream edit", () => {
  test("an unresolved joint is not exported as Ready", async ({ page }) => {
    test.setTimeout(240_000);
    const { idA, idB, token, assemblyId } = await setupTwoInstances(page);
    const auth = { Authorization: `Bearer ${token}` };

    await pickHoleCentres(page, idA, idB);
    await page.getByTestId("joint-motion-revolute").click();
    await page.getByTestId("joint-ok").click();
    await expect(page.getByTestId("mate-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await waitForSolved(page);
    await expect(page.getByTestId("mate-row").first()).not.toContainText(
      "unresolved",
    );
    await expect(page.getByTestId("assembly-export-status")).toHaveText(
      "Ready",
    );

    // Move the hole 2 mm in the part (the plate's Sketch1 circle).
    const instances = (await (
      await page.request.get(`/api/v1/assemblies/${assemblyId}`, {
        headers: auth,
      })
    ).json()) as { instances: Array<{ ref_document_id: string }> };
    const partId = instances.instances[0]?.ref_document_id ?? "";
    const tree = (await (
      await page.request.get(`/api/v1/parts/${partId}/features`, {
        headers: auth,
      })
    ).json()) as {
      tree_version: number;
      features: Array<{
        id: string;
        feature: {
          type: string;
          version: number;
          params: {
            entities: Array<{
              kind: string;
              center?: { x: number; y: number };
            }>;
          };
        };
      }>;
    };
    const sketch = tree.features[0];
    if (sketch === undefined) throw new Error("the plate has no sketch");
    const circle = sketch.feature.params.entities.find(
      (e) => e.kind === "circle",
    );
    if (circle?.center === undefined) throw new Error("no hole circle");
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

    // Reopen the assembly: the joint no longer resolves (today's behaviour).
    await page.reload();
    await waitForSolved(page);
    await expect(page.getByTestId("mate-row").first()).toContainText(
      "unresolved",
      { timeout: 30_000 },
    );

    // The defect: the export still claims the assembly is ready, and its
    // STEP would hold the parts at their seeds, not where the joint put them.
    await expect(
      page.getByTestId("assembly-export-status"),
      "an assembly with an unresolved joint must not export as Ready",
    ).not.toHaveText("Ready");
  });
});
