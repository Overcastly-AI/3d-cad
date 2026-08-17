import { expect, test } from "./fixtures";

import {
  createPartViaApi,
  openRowActions,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * FOLDERS (#WS2) — filing driven through a real browser against the real stack
 * (gateway + documents, no mocks).
 *
 * Every assertion here is aimed at the defect class the brief named rather than
 * at the happy path:
 *
 *  - a folder's count is checked against what was actually filed into it, and
 *    it is read AFTER a reload, so a number the browser computed for itself
 *    would fail;
 *  - the move is re-read from a RELOADED page, so a move that reported success
 *    while the document was still in the old place would fail;
 *  - the rename is checked to reach the register, so a tree that disagreed with
 *    the drawer after a rename would fail;
 *  - a document filed in a folder is checked to still be FINDABLE by filter
 *    from the root, which is the reachability guarantee the whole design rests
 *    on;
 *  - the non-empty delete is checked to NAME what is inside AND to have left it
 *    there — the refusal must not be a cascade wearing a message.
 */

/** Every visible register row name, in draw order. */
async function rowNames(page: import("@playwright/test").Page) {
  return page.getByTestId("part-open").allTextContents();
}

test.describe("folders", () => {
  test("files, finds, moves and refuses to swallow work", async ({ page }) => {
    const { token } = await seedSession(page);
    await createPartViaApi(page, token, "Bracket plate");
    await createPartViaApi(page, token, "Rib 2");

    await page.goto("/");
    await expect(page.getByTestId("parts-table")).toBeVisible();
    await expect(page.getByTestId("parts-count")).toHaveText("2 parts");
    // Nothing pretends a tree exists before one does.
    await expect(page.getByTestId("parts-folder-row")).toHaveCount(0);

    // --- FILE A DIVIDER --------------------------------------------------
    await page.getByTestId("parts-new-folder").click();
    await page.getByTestId("create-part-folder-name").fill("Gearbox");
    await page.getByTestId("create-part-folder-submit").click();

    const divider = page.getByTestId("parts-folder-row");
    await expect(divider).toHaveCount(1);
    await expect(page.getByTestId("parts-folder-open")).toHaveText("Gearbox");
    // A folder nothing has been filed into says so, rather than "0 parts".
    await expect(page.getByTestId("parts-folder-count")).toHaveText("Empty");

    // --- MOVE A DOCUMENT INTO IT -----------------------------------------
    const bracketRow = page
      .getByTestId("part-row")
      .filter({ hasText: "Bracket plate" });
    await openRowActions(bracketRow);
    await bracketRow.getByTestId("part-move").click();
    await page
      .getByTestId("part-move-folder")
      .selectOption({ label: "Gearbox" });
    await page.getByTestId("part-move-save").click();

    // The root now holds ONE document and the readout is a fraction of the
    // whole drawer — the same grammar the filter uses, for the same reason.
    await expect(page.getByTestId("part-row")).toHaveCount(1);
    await expect(page.getByTestId("parts-count")).toHaveText("1 of 2 parts");
    // ...and the divider's count came from the server, so it moved too.
    await expect(page.getByTestId("parts-folder-count")).toHaveText("1 part");

    // RELOAD: the move was real, not a repaint.
    await page.reload();
    await expect(page.getByTestId("parts-folder-count")).toHaveText("1 part");
    expect(await rowNames(page)).toEqual(["Rib 2"]);

    // --- REACHABILITY: the filter searches the WHOLE drawer ---------------
    await page.getByTestId("parts-filter").fill("bracket");
    await expect(page.getByTestId("part-row")).toHaveCount(1);
    await expect(page.getByTestId("part-location")).toHaveText("Gearbox");
    // The drawer goes flat while filtering — a filter is a way of looking.
    await expect(page.getByTestId("parts-folder-row")).toHaveCount(0);
    await page.getByTestId("parts-filter").fill("");

    // --- ENTER THE FOLDER -------------------------------------------------
    await page.getByTestId("parts-folder-open").click();
    await expect(page.getByTestId("parts-breadcrumb")).toContainText("Gearbox");
    expect(await rowNames(page)).toEqual(["Bracket plate"]);
    await expect(page.getByTestId("parts-count")).toHaveText("1 of 2 parts");

    // A part named INSIDE a folder is filed there, in ONE call. Creating a
    // part OPENS it (FINDINGS #22), so the register is left behind — come back
    // and check the server really filed it where the click said.
    await page.getByTestId("create-part-name").fill("Housing");
    await page.getByTestId("create-part-submit").click();
    await expect(page).toHaveURL(/\/parts\/[0-9a-f-]+$/);

    await page.goto("/");
    // At the ROOT it is not on screen — it is filed, not unfiled.
    await expect(page.getByTestId("part-row")).toHaveCount(1);
    expect(await rowNames(page)).toEqual(["Rib 2"]);
    await page.getByTestId("parts-folder-open").click();
    await expect(page.getByTestId("part-row")).toHaveCount(2);
    expect((await rowNames(page)).sort()).toEqual(["Bracket plate", "Housing"]);

    // --- RENAME THE FOLDER, and the drawer agrees -------------------------
    await page.getByTestId("parts-breadcrumb-root").click();
    await openRowActions(page, "parts-folder");
    await page.getByTestId("parts-folder-rename").click();
    await page.getByTestId("parts-folder-rename-name").fill("Gearbox v2");
    await page.getByTestId("parts-folder-rename-save").click();
    await expect(page.getByTestId("parts-folder-open")).toHaveText(
      "Gearbox v2",
    );
    await page.reload();
    await expect(page.getByTestId("parts-folder-open")).toHaveText(
      "Gearbox v2",
    );

    // --- DELETE IS REFUSED, AND NAMES WHAT IS INSIDE ----------------------
    await openRowActions(page, "parts-folder");
    await page.getByTestId("parts-folder-delete").click();
    await page.getByTestId("parts-folder-delete-confirm").click();
    const blocked = page.getByTestId("parts-folder-blocked");
    await expect(blocked).toBeVisible();
    const named = await page
      .getByTestId("parts-folder-content")
      .allTextContents();
    expect(named.sort()).toEqual(["Bracket plate", "Housing"]);
    // Not a cascade wearing a message: both parts are still there.
    await page.getByTestId("parts-folder-delete-cancel").click();
    await page.getByTestId("parts-folder-open").click();
    await expect(page.getByTestId("part-row")).toHaveCount(2);

    await page.getByTestId("parts-breadcrumb-root").click();
    for (const width of [1440, 1366]) {
      await page.setViewportSize({ width, height: 900 });
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/workspace-folders-${width}.png`,
      });
    }
    // ...and the view from INSIDE a folder, where the breadcrumb and the
    // fraction readout are the two things doing the work.
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.getByTestId("parts-folder-open").click();
    await expect(page.getByTestId("parts-breadcrumb")).toContainText(
      "Gearbox v2",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/workspace-folders-inside-1440.png`,
    });
  });

  test("two folders may each hold a part of the same name", async ({
    page,
  }) => {
    // The point of per-FOLDER uniqueness. Before #WS2 the second create was a
    // 409, which is what made folders worth building.
    const { token } = await seedSession(page);
    await createPartViaApi(page, token, "Bracket");

    await page.goto("/");
    for (const name of ["Left", "Right"]) {
      await page.getByTestId("parts-new-folder").click();
      await page.getByTestId("create-part-folder-name").fill(name);
      await page.getByTestId("create-part-folder-submit").click();
      await expect(
        page.getByTestId("parts-folder-row").filter({ hasText: name }),
      ).toHaveCount(1);
    }

    await openRowActions(page);
    await page.getByTestId("part-move").click();
    await page.getByTestId("part-move-folder").selectOption({ label: "Left" });
    await page.getByTestId("part-move-save").click();
    await expect(page.getByTestId("part-row")).toHaveCount(0);

    // Same name, other folder: accepted.
    await page
      .getByTestId("parts-folder-row")
      .filter({ hasText: "Right" })
      .getByTestId("parts-folder-open")
      .click();
    await page.getByTestId("create-part-name").fill("Bracket");
    await page.getByTestId("create-part-submit").click();
    // Creating a part opens it (FINDINGS #22); come back and read the drawer.
    await expect(page).toHaveURL(/\/parts\/[0-9a-f-]+$/);
    await page.goto("/");
    await page
      .getByTestId("parts-folder-row")
      .filter({ hasText: "Right" })
      .getByTestId("parts-folder-open")
      .click();
    await expect(page.getByTestId("part-open")).toHaveText("Bracket");

    // ...and the SAME folder still refuses a second one.
    await page.getByTestId("create-part-name").fill("Bracket");
    await page.getByTestId("create-part-submit").click();
    await expect(page.getByTestId("create-part-name")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });
});
