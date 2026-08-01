import { expect, test } from "./fixtures";

import { seedCube } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * THE KEY CARD (UI-REVIEW F4) — that `?` reaches the reference from the surfaces
 * a user is actually on, and that what it teaches is TRUE of those surfaces.
 *
 * The last part is the point. A reference nobody checks is the "gate that cannot
 * fail" defect in documentation form, so the spec does not stop at "the overlay
 * opens": it reads a binding off the card and then FIRES that binding, in the
 * real app, and asserts the app reacted. `/` is the one used here because its
 * effect is unambiguous from the outside (the filter field takes focus).
 */

test.describe("keyboard reference", () => {
  test("? opens the card in a register, and what it teaches is true", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    await createPartViaApi(page, token, "Bracket plate");

    await page.goto("/");
    await expect(page.getByTestId("parts-table")).toBeVisible();
    await expect(page.getByTestId("shortcut-sheet")).toHaveCount(0);

    await page.keyboard.press("?");
    const sheet = page.getByTestId("shortcut-sheet");
    await expect(sheet).toBeVisible();
    // The groups a register user needs are all on it, derived from the tables
    // the handlers index — not a hand-typed subset.
    await expect(sheet).toContainText("Registers");
    await expect(sheet).toContainText("Sketch tools");
    await expect(sheet).toContainText("Sketch constraints");
    await expect(sheet).toContainText("View");

    for (const width of [1440, 1366]) {
      await page.setViewportSize({ width, height: 900 });
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/shortcut-sheet-${width}.png`,
      });
    }
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.keyboard.press("Escape");
    await expect(sheet).toHaveCount(0);

    // ...and the binding the card just taught really works here.
    await page.keyboard.press("/");
    await expect(page.getByTestId("parts-filter")).toBeFocused();
  });

  test("? opens it in the part workspace too, over the viewport", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Bracket plate");
    await seedCube(page, token, part.id);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("feature-tree")).toBeVisible();

    await page.keyboard.press("?");
    await expect(page.getByTestId("shortcut-sheet")).toBeVisible();
    // The modelling accelerators are what a user in here is looking for.
    await expect(page.getByTestId("shortcut-sheet")).toContainText("Modelling");

    // Clicking the ground behind it dismisses, and the workspace is intact.
    await page.getByTestId("shortcut-sheet-backdrop").click({
      position: { x: 5, y: 5 },
    });
    await expect(page.getByTestId("shortcut-sheet")).toHaveCount(0);
    await expect(page.getByTestId("feature-tree")).toBeVisible();
  });
});
