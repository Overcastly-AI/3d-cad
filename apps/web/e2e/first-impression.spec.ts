import { expect, test } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
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
      /**
       * The flow assertion, and the one this page had no answer to before: the
       * landing surface must PROPOSE the next step, not merely list what is
       * filed. These parts are all freshly created stubs, so the band is in its
       * "start here" branch and must say so rather than claim work to resume —
       * asserting the caption, not just the band's presence, is what stops a
       * regression from silently telling a first-run user to resume nothing.
       */
      await expect(page.getByTestId("parts-resume")).toBeVisible();
      await expect(page.getByTestId("parts-resume-caption")).toHaveText(
        "Named, not drawn yet — open it and pick a plane.",
      );
      await expect(page.getByTestId("parts-resume-open")).toHaveAttribute(
        "aria-label",
        /^Open /,
      );
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/first-impression/parts-${label}.png`,
      });
    });

    /**
     * The OTHER branch, exercised against the real gateway rather than only in
     * `ResumeBand.test.ts`: a part that has actually been worked on must be
     * offered by name with the age of its last edit. This is the case the
     * landing surface exists for, and it depends on a server fact the client
     * cannot fake — that a tree write bumps `updated_at` — so a unit test with
     * hand-written stamps cannot stand in for it.
     */
    test(`a worked part is offered by name to resume (${label})`, async ({
      page,
    }) => {
      const account = await seedSession(page);
      await createPartViaApi(page, account.token, "Cover panel");
      const worked = await createPartViaApi(
        page,
        account.token,
        "Spindle housing",
      );
      /*
       * The wait is load-bearing, not flake padding, and it is the SUBJECT of
       * the test as much as the setup. `lib/activity.ts` treats a document whose
       * two stamps are within `CREATION_SKEW_MS` (250 ms) as never edited,
       * because a fresh INSERT writes `created_at` and `updated_at` from
       * separate `datetime.now()` calls and they differ by microseconds. A spec
       * that creates a part and writes to its tree in the same breath lands
       * INSIDE that window — measured here at first attempt: the band correctly
       * refused to say "resume", which is the window doing its job on input no
       * human can produce. 700 ms is ~3x the threshold and still far below any
       * real edit, so the two writes are two distinct actions the way a person's
       * would be.
       */
      await page.waitForTimeout(700);
      // A real tree write, which is what bumps `updated_at` — the server fact
      // the whole "last worked" readout rests on.
      await createFeature(page, account.token, worked.id, {
        name: "Sketch1",
        feature: { type: "sketch", version: 1, params: SQUARE_20 },
        expected_tree_version: 0,
      });

      await page.goto("/");
      await expect(page.getByTestId("parts-resume-name")).toHaveText(
        "Spindle housing",
      );
      await expect(page.getByTestId("parts-resume-caption")).toContainText(
        "Last edited",
      );
      // And it opens what it names — a proposal that goes somewhere else is
      // worse than no proposal.
      await page.getByTestId("parts-resume-open").click();
      await expect(page).toHaveURL(new RegExp(`/parts/${worked.id}$`));
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
