import { expect, test } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * BACKLOG #4: the parts home — the landing surface after sign-in. Everything
 * runs through the real browser against the real stack (gateway + documents):
 * land on the register, create a part from the UI, open its workspace, come
 * back, delete it with a confirm, and prove the deletion persisted on reload.
 */

test.describe("parts home", () => {
  test("create → list → open → back → delete → persists", async ({ page }) => {
    await seedSession(page);
    await page.goto("/");

    // First-run: the register is empty and invites the first sheet.
    await expect(page.getByTestId("parts-register")).toBeVisible();
    await expect(page.getByTestId("parts-empty")).toBeVisible();

    // Create a part from the UI (keyboard-first: Enter files it).
    await page.getByTestId("create-part-name").fill("Bracket plate");
    await page.getByTestId("create-part-name").press("Enter");

    // It appears in the register; the empty invitation is gone.
    const row = page
      .getByTestId("part-row")
      .filter({ hasText: "Bracket plate" });
    await expect(row).toBeVisible();
    await expect(page.getByTestId("parts-empty")).toHaveCount(0);
    await expect(page.getByTestId("parts-count")).toHaveText("1 part");

    // Open the workspace — the register row is the door to the part.
    await row.getByTestId("part-open").click();
    await expect(page).toHaveURL(/\/parts\/[0-9a-f-]+$/);
    await expect(page.getByTestId("part-name")).toHaveText("Bracket plate");

    // Back to the register — the part is still filed.
    await page.goBack();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId("part-row")).toHaveCount(1);

    // Delete with a confirm — nothing destructive on a single click.
    await page.getByTestId("part-delete").click();
    await expect(page.getByTestId("part-delete-confirm")).toBeVisible();
    await page.getByTestId("part-delete-confirm").click();

    // Gone from the list; the invitation returns.
    await expect(page.getByTestId("part-row")).toHaveCount(0);
    await expect(page.getByTestId("parts-empty")).toBeVisible();

    // Reload proves it persisted server-side, not just in the client cache.
    await page.reload();
    await expect(page.getByTestId("parts-empty")).toBeVisible();
  });

  test("cancelling the delete confirm keeps the part", async ({ page }) => {
    const account = await seedSession(page);
    await createPartViaApi(page, account.token, "Keep me");
    await page.goto("/");

    await page.getByTestId("part-delete").click();
    await page.getByTestId("part-delete-cancel").click();
    await expect(page.getByTestId("part-row")).toHaveCount(1);
    await expect(
      page.getByTestId("part-row").filter({ hasText: "Keep me" }),
    ).toBeVisible();
  });

  test("a duplicate name is surfaced legibly on the field (409)", async ({
    page,
  }) => {
    const account = await seedSession(page);
    await createPartViaApi(page, account.token, "Housing");
    await page.goto("/");

    await page.getByTestId("create-part-name").fill("Housing");
    await page.getByTestId("create-part-submit").click();

    await expect(page.getByRole("alert")).toContainText("already exists");
    // No phantom duplicate was created.
    await expect(page.getByTestId("part-row")).toHaveCount(1);
  });

  test("founder screenshots: empty + populated register (desktop)", async ({
    page,
  }) => {
    const account = await seedSession(page);
    await page.goto("/");

    await expect(page.getByTestId("parts-empty")).toBeVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/parts-home-empty.png` });

    for (const name of ["Bracket plate", "Motor mount", "Spindle housing"]) {
      await createPartViaApi(page, account.token, name);
    }
    await page.reload();
    await expect(page.getByTestId("part-row")).toHaveCount(3);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/parts-home-desktop.png` });
  });
});

test.describe("parts home small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("register + create line stay usable at laptop width", async ({
    page,
  }) => {
    const account = await seedSession(page);
    for (const name of ["Bracket plate", "Motor mount"]) {
      await createPartViaApi(page, account.token, name);
    }
    await page.goto("/");

    await expect(page.getByTestId("part-row")).toHaveCount(2);
    // The create control and the created/updated columns are visible at width.
    await expect(page.getByTestId("create-part-name")).toBeVisible();
    await expect(page.getByTestId("create-part-submit")).toBeVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/parts-home-laptop.png` });
  });
});
