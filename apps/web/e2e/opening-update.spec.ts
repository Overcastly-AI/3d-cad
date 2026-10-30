import {
  B7_SAVED_IN3,
  B7_SAVED_PINS,
  OPENING_NAMES,
  partVolume,
  seedSavedB7,
  storedPins,
} from "./b7Saved";
import { expectSolved, openCutList } from "./buildFlow";
import { expect, test } from "./fixtures";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * OPENING-UPDATE: B7 as saved before HEADER-PLIES (golden `b7-outline`: walls
 * `loft.wall` 1.3.0, the door and five windows `loft.door`/`loft.window`
 * 1.1.0, the gable `loft.roof` 1.4.0, the floor 1.2.0), so its 2x6 headers
 * are two plies with a 2-1/2 in void. As Onshape marks a custom feature whose
 * Feature Studio is newer and Fusion badges stale content, each out-of-date
 * Build feature that an update changes wears an Update badge (the floor and
 * the walls, whose updates change no member, none: PLUGIN-UPDATE-ALL), its
 * editor says what "Update to 1.5.0" adds, and the tree offers one "Update
 * all Build features". That one step takes the headers to 18 plies (was 12)
 * and draws 12 spacers of 1/2 plywood, cut from one 4x8, and ties the gable
 * with its 11 ceiling joists and frames its gable ends (22 studs, 12 OSB
 * panels: GABLE-END-STUDS): 264 852.3789 + 1 769.625 + 1 179.75 +
 * 22 887.596423 + 4 268 + 4 992.0374 = 299 949.3876 in³ (golden
 * `b7-update-all`). Ctrl+Z restores
 * 264 852.3789 and every pin.
 */

const AFTER = 299949.387649;

const UPDATED = {
  Floor: "1.4.0",
  Walls: "1.5.0",
  ...Object.fromEntries(OPENING_NAMES.map((n) => [n, "1.5.0"])),
  Roof: "1.8.0",
};

test.describe("Updating B7's out-of-date Build features", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("badges them, updates all in one step to 18 plies and 12 spacers, and Ctrl+Z restores", async ({
    page,
  }) => {
    test.setTimeout(420_000);
    const account = await seedSession(page);
    const partId = await seedSavedB7(
      page,
      account.token,
      "B7 saved before header plies",
    );

    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(10);
    await expectSolved(page);
    await expect
      .poll(() => partVolume(page), { timeout: 120_000 })
      .toBeCloseTo(B7_SAVED_IN3, 2);

    // Every Build feature an update changes is badged; the floor and the
    // walls (no member changes) are not.
    const strip = page.getByTestId("feature-update-strip");
    await expect(strip).toContainText("7 Build features out of date");
    for (const index of [1, 2]) {
      await expect(
        page.getByTestId(`feature-update-badge-${index}`),
      ).toHaveCount(0);
    }
    for (const index of [3, 4, 5, 6, 7, 8, 9]) {
      await expect(
        page.getByTestId(`feature-update-badge-${index}`),
      ).toBeVisible();
    }
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/opening-update-tree.png`,
    });

    // A window's editor says what its update adds; opening it changes
    // nothing.
    await page.getByTestId("feature-select-4").click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("Edit Window");
    const notice = page.getByTestId("plugin-update-notice");
    await expect(notice).toContainText("Update available");
    await expect(notice).toContainText(
      "Adds 2 header spacers and 1 header ply.",
    );
    await expect(notice).toContainText("1/2 in");
    await expect(page.getByTestId("plugin-update")).toHaveText(
      "Update to 1.5.0",
    );
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/opening-update-editor.png`,
    });
    await page.getByTestId("plugin-cancel").click();
    await expect(editor).toBeHidden();
    expect(await storedPins(page, partId, account.token)).toEqual(
      B7_SAVED_PINS,
    );

    // Update all: one step.
    await page.getByTestId("feature-update-all").click();
    await expect(strip).toBeHidden({ timeout: 90_000 });
    await expectSolved(page);
    await expect
      .poll(() => partVolume(page), { timeout: 120_000 })
      .toBeCloseTo(AFTER, 2);
    expect(await storedPins(page, partId, account.token)).toEqual(UPDATED);

    // The cut list: 18 header plies and the spacers cut from one sheet.
    await openCutList(page);
    const panel = page.getByTestId("cut-list-panel");
    const headers = panel.locator(
      '[data-testid="cut-list-row"][data-member="Header"]',
    );
    await expect(headers).toHaveCount(3, { timeout: 90_000 });
    const quantities = await headers
      .getByTestId("cut-list-qty")
      .allInnerTexts();
    expect(quantities.map(Number).sort((a, b) => a - b)).toEqual([3, 6, 9]);
    const spacers = panel.locator(
      '[data-testid="cut-list-row"][data-member="Spacer"]',
    );
    await expect(spacers).toHaveCount(1);
    await expect(spacers).toHaveAttribute("data-system", "walls");
    await expect(spacers).toHaveAttribute("data-profile", "1/2 plywood");
    await expect(spacers.getByTestId("cut-list-qty")).toHaveText("12");
    await expect(spacers.getByTestId("cut-list-stock")).toHaveText("1 × 4x8");
    await spacers.scrollIntoViewIfNeeded();
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/opening-update-cut-list.png`,
    });

    // One Ctrl+Z restores every pin and the volume.
    await page.getByTestId("feature-select-1").click();
    await page.getByTestId("plugin-cancel").click();
    await page.keyboard.press("Control+z");
    await expect
      .poll(() => partVolume(page), { timeout: 120_000 })
      .toBeCloseTo(B7_SAVED_IN3, 2);
    expect(await storedPins(page, partId, account.token)).toEqual(
      B7_SAVED_PINS,
    );
    await expect(strip).toContainText("7 Build features out of date");
  });
});
