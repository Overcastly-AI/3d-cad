import { expect, test } from "./fixtures";

import { seedCube } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * DELETING A FEATURE SAYS WHO BREAKS (UI-REVIEW 2026-07-30 F3) — through a real
 * browser against the real stack.
 *
 * The finding was that delete fired with no confirmation and no dependency
 * check, so a user learned what it broke when the extrude turned red on the
 * next evaluate. What is under test is not "a dialog appears": it is that the
 * dialog says the RIGHT thing, from the server, in both directions —
 *
 *  - a feature something consumes is NAMED as blocked, the dependent is listed
 *    by its own name, and no delete button is offered (the server would refuse
 *    it, and a button that cannot work is a defect);
 *  - the feature nothing consumes gets a plain confirmation and really does
 *    delete, so the warning is discriminating rather than universal.
 */

test.describe("feature delete", () => {
  test("names the dependent before deleting, and deletes when nothing does", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Bracket plate");
    // Sketch1 → Extrude1: the smallest real dependency in the product, and the
    // exact pair the finding names.
    await seedCube(page, token, part.id);
    await page.goto(`/parts/${part.id}`);

    const tree = page.getByTestId("feature-tree");
    await expect(tree).toBeVisible();
    const sketchRow = tree
      .getByTestId("feature-row")
      .filter({ hasText: "Sketch1" });
    const extrudeRow = tree
      .getByTestId("feature-row")
      .filter({ hasText: "Extrude1" });
    await expect(sketchRow).toHaveCount(1);
    await expect(extrudeRow).toHaveCount(1);

    // --- THE CONSUMED FEATURE --------------------------------------------
    await sketchRow.click({ button: "right" });
    await page.getByTestId("tree-ctx-delete").click();

    const confirm = page.getByTestId("feature-delete-confirm");
    await expect(confirm).toBeVisible();
    await expect(confirm).toHaveAttribute("data-blocked", "true");
    // The dependent is named — not counted.
    await expect(page.getByTestId("feature-dependent")).toHaveText("Extrude1");
    await expect(page.getByTestId("feature-dependent")).toHaveAttribute(
      "data-dependent-kind",
      "feature",
    );
    // No delete is offered, because the server would refuse it.
    await expect(page.getByTestId("feature-delete-confirm-action")).toHaveCount(
      0,
    );

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/feature-delete-dependents-1440.png`,
      fullPage: false,
    });

    await page.getByTestId("feature-delete-cancel").click();
    await expect(confirm).toHaveCount(0);
    // Nothing was destroyed by asking.
    await expect(tree.getByTestId("feature-row")).toHaveCount(2);

    // --- THE FEATURE NOTHING CONSUMES ------------------------------------
    await extrudeRow.click({ button: "right" });
    await page.getByTestId("tree-ctx-delete").click();
    await expect(confirm).toHaveAttribute("data-blocked", "false");
    await expect(confirm).toContainText("Nothing else depends on it");

    await page.getByTestId("feature-delete-confirm-action").click();
    await expect(confirm).toHaveCount(0);
    await expect(tree.getByTestId("feature-row")).toHaveCount(1);
    await expect(tree.getByTestId("feature-row")).toContainText("Sketch1");

    // ...and now that the extrude is gone, the sketch is free — the warning
    // tracks the real graph rather than flagging sketches on principle.
    await page.reload();
    await expect(page.getByTestId("feature-tree")).toBeVisible();
    await page
      .getByTestId("feature-row")
      .filter({ hasText: "Sketch1" })
      .click({ button: "right" });
    await page.getByTestId("tree-ctx-delete").click();
    await expect(page.getByTestId("feature-delete-confirm")).toHaveAttribute(
      "data-blocked",
      "false",
    );
  });
});
