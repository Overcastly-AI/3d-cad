import {
  B7_SAVED_IN3,
  B7_SAVED_PINS,
  OPENING_NAMES,
  partVolume,
  seedSavedB7,
  storedPins,
  storedRows,
} from "./b7Saved";
import { expectSolved } from "./buildFlow";
import { expect, test } from "./fixtures";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * PLUGIN-UPDATE-ALL: B7 saved at batch48's releases (golden `b7-outline`).
 * Onshape updates a custom feature to its newest Feature Studio, every new
 * parameter at its default, so each Build release maps to its newest: the
 * floor 1.2.0 -> 1.3.0 (Joists bear on Long walls frames the same joists,
 * byte for byte), the walls 1.3.0 -> 1.4.0, the openings 1.1.0 -> 1.5.0 and
 * the roof 1.4.0 -> 1.6.0, which ties the gable with its 11 ceiling joists.
 * The badge names what an update adds ("adds 11 ceiling joists"); the floor
 * and the walls change no member, so they wear none but ride in Update all.
 *
 * Update from an editor holding unsaved edits asks first: dismissed, the
 * edits stay and nothing is updated; confirmed, that one feature updates as
 * stored. Then one Update all leaves nothing out of date and builds B7 as
 * drawn today: 264 852.3789 + 1 769.625 + 1 179.75 + 22 887.596423 =
 * 290 689.3503 in³ (golden `b7-update-all`). Each update is one Ctrl+Z.
 */

const IN = 25.4;
const AFTER = 290689.350289;
const WINDOW_1_OFFSET_MM = 228 * IN;

test.describe("Update all on a saved B7", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("names what each update adds, asks before dropping edits, and leaves nothing out of date", async ({
    page,
  }) => {
    test.setTimeout(480_000);
    const account = await seedSession(page);
    const partId = await seedSavedB7(page, account.token);
    const before = await storedRows(page, partId, account.token);

    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(10);
    await expectSolved(page);
    await expect
      .poll(() => partVolume(page), { timeout: 120_000 })
      .toBeCloseTo(B7_SAVED_IN3, 2);

    // Every Build feature is offered its newest release; the floor's and the
    // walls' change nothing, so only the seven that add members are badged.
    for (const name of Object.keys(B7_SAVED_PINS)) {
      expect(before[name]?.plugin_update, name).toBeTruthy();
    }
    const strip = page.getByTestId("feature-update-strip");
    await expect(strip).toContainText("7 Build features out of date");
    await expect(page.getByTestId("feature-update-badge-1")).toHaveCount(0);
    await expect(page.getByTestId("feature-update-badge-2")).toHaveCount(0);
    const roofBadge = page.getByTestId("feature-update-badge-9");
    await expect(roofBadge).toHaveAttribute(
      "title",
      "Update to 1.6.0: adds 11 ceiling joists",
    );
    await expect(page.getByTestId("feature-update-badge-3")).toHaveAttribute(
      "title",
      "Update to 1.5.0: adds 2 header spacers and 1 header ply",
    );
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/update-all-tree.png` });

    // The roof's editor names the joists its update adds.
    await page.getByTestId("feature-select-9").click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("Edit Roof");
    await expect(page.getByTestId("plugin-update-notice")).toContainText(
      "1.6.0: Adds 11 ceiling joists.",
    );
    await page.getByTestId("plugin-cancel").click();
    await expect(editor).toBeHidden();

    // Window 1's editor with an unsaved edit: Update asks first.
    await page.getByTestId("feature-select-4").click();
    await expect(editor).toContainText("Edit Window");
    const offset = page.getByTestId("plugin-input-offset_mm");
    await offset.fill("200");
    await page.getByTestId("plugin-update").click();
    const ask = page.getByTestId("plugin-update-confirm-notice");
    await expect(ask).toContainText("Unsaved edits");
    await expect(ask).toContainText("your unsaved edits are dropped");
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/update-all-editor-prompt.png`,
    });
    // Dismissed: the edit stays, nothing is updated.
    await page.getByTestId("plugin-update-cancel").click();
    await expect(ask).toBeHidden();
    await expect(offset).toHaveValue("200");
    expect(await storedPins(page, partId, account.token)).toEqual(
      B7_SAVED_PINS,
    );
    // Confirmed: Window 1 updates as stored, its edit dropped.
    await page.getByTestId("plugin-update").click();
    await page.getByTestId("plugin-update-confirm").click();
    await expect(editor).toBeHidden({ timeout: 60_000 });
    await expect(strip).toContainText("6 Build features out of date", {
      timeout: 60_000,
    });
    const oneUpdated = { ...B7_SAVED_PINS, "Window 1": "1.5.0" };
    expect(await storedPins(page, partId, account.token)).toEqual(oneUpdated);
    const window1 = (await storedRows(page, partId, account.token))["Window 1"];
    expect(window1?.feature.params.inputs?.offset_mm).toBeCloseTo(
      WINDOW_1_OFFSET_MM,
      6,
    );

    // One Update all: nothing is left out of date, quiet updates included.
    await page.getByTestId("feature-update-all").click();
    await expect(strip).toBeHidden({ timeout: 90_000 });
    await expectSolved(page);
    await expect
      .poll(() => partVolume(page), { timeout: 120_000 })
      .toBeCloseTo(AFTER, 2);
    const after = await storedRows(page, partId, account.token);
    expect(await storedPins(page, partId, account.token)).toEqual({
      Floor: "1.3.0",
      Walls: "1.4.0",
      ...Object.fromEntries(OPENING_NAMES.map((n) => [n, "1.5.0"])),
      Roof: "1.6.0",
    });
    for (const row of Object.values(after)) {
      expect(row.plugin_update ?? null, row.name).toBeNull();
    }
    await expect(
      page.locator('[data-testid^="feature-update-badge-"]'),
    ).toHaveCount(0);
    // The floor frames the same joists, byte for byte, on Long walls.
    expect(after.Floor?.feature.params.expansion).toEqual(
      before.Floor?.feature.params.expansion,
    );
    expect(after.Floor?.feature.params.inputs?.joists_bear_on).toBe(
      "long_walls",
    );
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/update-all-done.png` });

    // One Ctrl+Z undoes the whole Update all, and only it.
    await page.keyboard.press("Control+z");
    await expect(strip).toContainText("6 Build features out of date", {
      timeout: 90_000,
    });
    expect(await storedPins(page, partId, account.token)).toEqual(oneUpdated);
  });
});
