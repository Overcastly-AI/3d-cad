import { expect, test } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * THE FIRST IMPRESSION — the two surfaces an evaluating engineer meets before
 * they have modelled anything: the sign-in sheet and the parts register.
 *
 * They already have shots in `auth.spec.ts` and `parts-home.spec.ts`, but those
 * are captured incidentally in the middle of behavioural specs, at whatever
 * width that spec happened to run at. SIGNIN-1 survived four audit passes partly
 * because nobody was looking at these two frames side by side, at both of the
 * widths the design mandate names, on purpose. This spec exists to make that
 * comparison cheap and repeatable: same seed, same two widths, one directory.
 *
 * The seed is deliberately a REAL drawer (five parts, one of them never opened),
 * not one row — a register's job is only visible when it has something in it.
 */

/** Both widths the design mandate holds every surface to. */
const WIDTHS = [
  { label: "1600", width: 1600, height: 1000 },
  { label: "1280", width: 1280, height: 800 },
] as const;

const SEED_PARTS = [
  "Bracket plate",
  "Motor mount",
  "Spindle housing",
  "Cover panel",
  "Shim 0.8",
];

for (const { label, width, height } of WIDTHS) {
  test.describe(`first impression @ ${label}`, () => {
    test.use({ viewport: { width, height } });

    test(`sign-in sheet is composed, not corner-pinned (${label})`, async ({
      page,
    }) => {
      await page.goto("/sign-in");
      await expect(page.getByTestId("auth-panel")).toBeVisible();
      await expect(page.getByTestId("auth-email")).toBeFocused();

      /**
       * SIGNIN-1's acceptance, measured rather than eyeballed. A screenshot
       * cannot fail; this can, and it is worth being precise about WHAT it
       * asserts, because the naive version ("the card is centred") would forbid
       * the design rather than the defect.
       *
       * The filed defect was two separate things wearing one complaint: the card
       * was pinned to a frame CORNER, and 94.8 % of the frame was empty. So both
       * are asserted, and neither is asserted as "centre the card":
       *
       *  (a) the SHEET — the composition the card belongs to — is horizontally
       *      centred and covers a real share of the frame. This is the "94.8 %
       *      empty" half, and it is the one that actually mattered.
       *  (b) the card's VERTICAL centre is central. Combined with (a) this
       *      forbids the bottom-right pin while permitting the title block to
       *      stay right-of-centre, which is where a title block belongs and is
       *      the idea the original design got right.
       *
       * Baseline for comparison, measured on this exact frame before the change:
       * a 320x260 card at (1232, 692), i.e. cy = 0.82, with no sheet at all.
       */
      const sheet = await page.getByTestId("sign-in-sheet").boundingBox();
      const card = await page.getByTestId("auth-panel").boundingBox();
      expect(sheet).not.toBeNull();
      expect(card).not.toBeNull();
      if (sheet === null || card === null) return;

      const sheetCentre = (sheet.x + sheet.width / 2) / width;
      expect(Math.abs(sheetCentre - 0.5)).toBeLessThan(0.02);
      expect(sheet.width / width).toBeGreaterThan(0.55);
      expect((sheet.width * sheet.height) / (width * height)).toBeGreaterThan(
        0.4,
      );

      const cardCentreY = (card.y + card.height / 2) / height;
      expect(cardCentreY).toBeGreaterThan(0.3);
      expect(cardCentreY).toBeLessThan(0.7);

      await page.screenshot({
        path: `${SCREENSHOT_DIR}/first-impression/sign-in-${label}.png`,
      });
    });

    test(`parts register with real work in it (${label})`, async ({ page }) => {
      const account = await seedSession(page);
      for (const name of SEED_PARTS) {
        await createPartViaApi(page, account.token, name);
      }
      await page.goto("/");
      await expect(page.getByTestId("part-row")).toHaveCount(SEED_PARTS.length);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/first-impression/parts-${label}.png`,
      });
    });

    test(`parts register on a first run (${label})`, async ({ page }) => {
      await seedSession(page);
      await page.goto("/");
      await expect(page.getByTestId("parts-empty")).toBeVisible();
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/first-impression/parts-empty-${label}.png`,
      });
    });
  });
}
