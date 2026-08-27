import { expect, test } from "./fixtures";

import { createPlateWithHoleViaApi } from "./assemblyFlow";
import { seedSession, SCREENSHOT_DIR } from "./support";

/**
 * The sheet's numbered PARTS LIST — the first caller `GET /drawings/{id}/bom`
 * has ever had.
 *
 * `assembly-drawing.spec.ts` proves an assembly can be drafted at all; this one
 * starts there and reads the item list off the sheet. What it insists on:
 *
 *  - item 1 qty 2 and item 2 qty 1, under the CURRENT part names — the flat
 *    direct-instance roll-up, numbered by the assembly's stable instance order;
 *  - the numbers survive a RELOAD. They are derived server-side and never
 *    stored on the drawing, so a fresh read reproducing them is the cheap proof
 *    they cannot drift from the assembly they name;
 *  - a PART-sourced sheet renders the block DISABLED with its reason, and that
 *    reason is reachable by TAB alone. It is the on-screen form of the server's
 *    typed `drawing_bom_source_not_assembly` — legible before it can be hit,
 *    and to a keyboard, not only to a hovering mouse.
 */

/** Build an assembly of `Bracket plate` x2 + `Cover plate` x1 through the UI. */
async function draftedAssembly(page: import("@playwright/test").Page) {
  const account = await seedSession(page);
  const partA = await createPlateWithHoleViaApi(
    page,
    account.token,
    "Bracket plate",
  );
  const partB = await createPlateWithHoleViaApi(
    page,
    account.token,
    "Cover plate",
  );

  await page.goto("/assemblies");
  await page.getByTestId("create-assembly-name").fill("Numbered rig");
  await page.getByTestId("create-assembly-name").press("Enter");
  const row = page
    .getByTestId("assembly-row")
    .filter({ hasText: "Numbered rig" });
  await expect(row).toBeVisible();
  await row.getByTestId("assembly-open").click();
  await expect(page).toHaveURL(/\/assemblies\/[0-9a-f-]+$/);

  await page.getByTestId("add-instance").click();
  await expect(page.getByTestId("add-instance-panel")).toBeVisible();
  const cellA = page.getByTestId(`add-instance-part-${partA.id}`);
  const cellB = page.getByTestId(`add-instance-part-${partB.id}`);
  for (let n = 1; n <= 2; n++) {
    await cellA.click();
    await expect(page.getByTestId("instance-row")).toHaveCount(n, {
      timeout: 20_000,
    });
  }
  await cellB.click();
  await expect(page.getByTestId("instance-row")).toHaveCount(3, {
    timeout: 20_000,
  });
  await page.getByTestId("add-instance-done").click();

  // Onto paper, with the assembly pre-selected, then lay out the four views.
  await page.getByTestId("assembly-drawing").click();
  await expect(page).toHaveURL(/\/drawings\/[0-9a-f-]+\?source=/, {
    timeout: 20_000,
  });
  await page.getByTestId("drawing-autolayout").click();
  await expect(
    page.locator('[data-testid="drawing-view"]').first(),
  ).toBeVisible({ timeout: 60_000 });
  return { partA, partB };
}

test.describe("Drawings — the sheet's parts list", () => {
  test("number the items, read their quantities and names, and reload", async ({
    page,
  }) => {
    const { partA, partB } = await draftedAssembly(page);

    const list = page.getByTestId("parts-list-panel");
    await expect(list).toBeVisible();
    await expect(list).toHaveAttribute("data-disabled", "false");
    await expect(page.getByTestId("parts-list-row")).toHaveCount(2, {
      timeout: 30_000,
    });

    const rowA = page.locator(
      `[data-testid="parts-list-row"][data-ref-document-id="${partA.id}"]`,
    );
    const rowB = page.locator(
      `[data-testid="parts-list-row"][data-ref-document-id="${partB.id}"]`,
    );
    await expect(rowA).toHaveAttribute("data-item-number", "1");
    await expect(rowB).toHaveAttribute("data-item-number", "2");
    await expect(rowA.getByTestId("parts-list-qty")).toHaveText("2");
    await expect(rowB.getByTestId("parts-list-qty")).toHaveText("1");
    await expect(rowA.getByTestId("parts-list-name")).toHaveText(
      "Bracket plate",
    );
    await expect(rowB.getByTestId("parts-list-name")).toHaveText("Cover plate");
    await expect(page.getByTestId("parts-list-total")).toHaveText("3");

    // Founder shot: an assembly drafted, with its numbered item list.
    await page.mouse.move(1400, 950);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-assembly-parts-list.png`,
    });

    // The numbers are DERIVED, never stored — a reload has to reproduce them.
    await page.reload();
    await expect(page.getByTestId("parts-list-row")).toHaveCount(2, {
      timeout: 60_000,
    });
    await expect(rowA).toHaveAttribute("data-item-number", "1");
    await expect(rowB).toHaveAttribute("data-item-number", "2");
    await expect(rowA.getByTestId("parts-list-qty")).toHaveText("2");
    await expect(rowB.getByTestId("parts-list-qty")).toHaveText("1");
  });

  test("an item row opens the document it names", async ({ page }) => {
    const { partB } = await draftedAssembly(page);
    const rowB = page.locator(
      `[data-testid="parts-list-row"][data-ref-document-id="${partB.id}"]`,
    );
    await expect(rowB).toBeVisible({ timeout: 30_000 });
    // A real click at the control's centre — the list is the only place on this
    // sheet where another document is named, so it is the only place "what IS
    // item 2?" can be answered from.
    await rowB.getByTestId("parts-list-name").click();
    await expect(page).toHaveURL(new RegExp(`/parts/${partB.id}`), {
      timeout: 20_000,
    });
  });

  test("a part-sourced sheet disables the block and says why, by keyboard", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPlateWithHoleViaApi(
      page,
      account.token,
      "Lone plate",
    );

    await page.goto("/drawings");
    await page.getByTestId("create-drawing-name").fill("Part sheet");
    await page.getByTestId("create-drawing-name").press("Enter");
    const row = page
      .getByTestId("drawing-row")
      .filter({ hasText: "Part sheet" });
    await expect(row).toBeVisible();
    await row.getByTestId("drawing-open").click();
    await expect(page).toHaveURL(/\/drawings\/[0-9a-f-]+/);

    await page.getByTestId("drawing-part-select").selectOption(part.id);
    await page.getByTestId("drawing-autolayout").click();
    await expect(
      page.locator('[data-testid="drawing-view"]').first(),
    ).toBeVisible({ timeout: 60_000 });

    // The block is PRESENT and disabled — not absent. An absent block teaches
    // nothing; a disabled one carrying its reason teaches what a parts list
    // needs, which is the whole point of surfacing the server's typed refusal
    // before anyone can trip it.
    const list = page.getByTestId("parts-list-panel");
    await expect(list).toBeVisible();
    await expect(list).toHaveAttribute("data-disabled", "true");
    await expect(page.getByTestId("parts-list-row")).toHaveCount(0);

    const reason = page.getByTestId("parts-list-unavailable");
    await expect(reason).toContainText("needs an assembly source");

    // READABLE AFTER TAB ALONE. Not hover: focus the panel's preceding control
    // and walk forward with the keyboard until the reason takes focus. A
    // caption only a pointer can reach is half-shipped, and `toBeVisible()`
    // cannot notice that — so assert with the user's own mechanism.
    await page.getByTestId("note-input").focus();
    let focused = false;
    for (let step = 0; step < 12 && !focused; step += 1) {
      await page.keyboard.press("Tab");
      focused = await reason.evaluate((el) => document.activeElement === el);
    }
    expect(focused).toBe(true);
    // And what focus landed on actually carries the sentence — the text a
    // screen reader announces, not just painted pixels.
    const announced = await page.evaluate(
      () => document.activeElement?.textContent?.trim() ?? "",
    );
    expect(announced).toContain("A parts list needs an assembly source");
  });
});
