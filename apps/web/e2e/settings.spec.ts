import { expect, test } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * THE SETTINGS SURFACE (#58) — and the only claim worth testing about a
 * preferences page: does the switch reach the thing it names?
 *
 * A settings row is trivially easy to render and trivially easy to leave
 * unwired, which is the failure this suite is built to catch. So nothing here
 * asserts that a control exists: each case sets a preference on `/settings`,
 * navigates AWAY to the surface that is supposed to honour it, and asserts the
 * effect there — the created part's unit on the register, and the number the
 * orbit rig was handed in the workspace viewport.
 *
 * The scroll-direction case is the one the founder called out: a fixed zoom
 * binding with no invert is a real adoption blocker, and the binding IS the
 * sign of the rig's zoom speed (see `settings/preferences.ts`).
 */
const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";

test.describe("settings — 1440x900", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("is reachable from every register and says whose settings these are", async ({
    page,
  }) => {
    await seedSession(page);
    await page.goto("/");
    await page.getByTestId("nav-settings").click();

    await expect(page.getByTestId("settings-sheet")).toBeVisible();
    await expect(page.getByTestId("settings-scope")).toContainText(
      "saved in this browser",
    );
    // ...and the way back is on screen, because this is a place you leave.
    await page.getByTestId("nav-parts").click();
    await expect(page.getByTestId("parts-register")).toBeVisible();
  });

  test("the units preference reaches the parts it creates", async ({
    page,
  }) => {
    await seedSession(page);
    await page.goto("/settings");
    await page.getByTestId("settings-new-document-unit").selectOption("in");

    // A new part, filed from the register's own scribe line (filing a part
    // OPENS it, so the assertion lands in the workspace).
    await page.getByTestId("nav-parts").click();
    await page.getByTestId("create-part-name").fill("Inch bracket");
    await page.getByTestId("create-part-submit").click();
    await expect(page).toHaveURL(/\/parts\/[0-9a-f-]+$/, { timeout: 30_000 });

    // The workspace opens in inches — the document was STAMPED, not converted.
    await expect(page.getByTestId("document-unit-select")).toHaveValue("in", {
      timeout: 30_000,
    });

    // ...and the register agrees: the drawer's UNITS column reads it back.
    await page.goto("/");
    await expect(page.getByTestId("part-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("part-row").first()).toContainText("in");

    // ...and the preference survives a reload, which is what makes it a
    // preference rather than a session accident.
    await page.goto("/settings");
    await page.reload();
    await expect(page.getByTestId("settings-new-document-unit")).toHaveValue(
      "in",
    );
  });

  test("inverting the scroll direction reaches the orbit rig", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Nav bracket");

    await page.goto(`/parts/${part.id}`);
    const viewport = page.getByTestId("viewport");
    await expect(viewport).toBeVisible({ timeout: 30_000 });
    // The shipped binding: one notch of the wheel pulls the camera IN.
    await expect(viewport).toHaveAttribute("data-nav-zoom-speed", "1");

    await page.goto("/settings");
    await page.getByTestId("settings-zoom-inverted").click();
    await page.getByTestId("settings-zoom-sensitivity-fast").click();
    await page.getByTestId("settings-orbit-slow").click();

    await page.goto(`/parts/${part.id}`);
    await expect(viewport).toBeVisible({ timeout: 30_000 });
    // Inverted AND faster: the sign is the direction, the magnitude is the
    // sensitivity, and both reached the camera without a reload.
    await expect(viewport).toHaveAttribute("data-nav-zoom-speed", "-2");
    await expect(viewport).toHaveAttribute("data-nav-rotate-speed", "0.5");
    await expect(viewport).toHaveAttribute("data-nav-pan-speed", "1");
  });

  test("restore defaults puts every preference back", async ({ page }) => {
    await seedSession(page);
    await page.goto("/settings");
    const reset = page.getByTestId("settings-reset");
    await expect(reset).toBeDisabled();

    await page.getByTestId("settings-zoom-inverted").click();
    await page.getByTestId("settings-new-document-unit").selectOption("ft");
    await expect(reset).toBeEnabled();
    await reset.click();

    await expect(page.getByTestId("settings-new-document-unit")).toHaveValue(
      "mm",
    );
    await expect(page.getByTestId("settings-zoom-standard")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(reset).toBeDisabled();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/settings-${SHOT_TAG}-1440.png`,
    });
  });
});

test.describe("settings — 1366x768", () => {
  test.use({ viewport: { width: 1366, height: 768 } });

  test("the sheet fits a small laptop without a root scroll", async ({
    page,
  }) => {
    await seedSession(page);
    await page.goto("/settings");
    await expect(page.getByTestId("settings-sheet")).toBeVisible();

    const overflow = await page.evaluate(() => ({
      scrollHeight: document.documentElement.scrollHeight,
      clientHeight: document.documentElement.clientHeight,
    }));
    expect
      .soft(overflow.scrollHeight)
      .toBeLessThanOrEqual(overflow.clientHeight);

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/settings-${SHOT_TAG}-1366.png`,
    });
  });
});
