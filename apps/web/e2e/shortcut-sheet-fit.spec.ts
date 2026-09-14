import { expect, test } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * THE KEY CARD FITS ON ONE SCREEN — at the 1440x900 laptop and at the 1280x800
 * quality floor.
 *
 * Why this is a gate and not a preference. The card is the ONLY place the five
 * new modelling accelerators are taught in words: the band's tooltip prints a
 * letter to whoever already hovered the tool, and the card is what answers "what
 * else is there?". A reference whose MODELLING block is below the fold teaches
 * the keys to nobody who does not already know to scroll for them, which makes
 * it the same defect as not shipping the letters.
 *
 * It regressed the moment FLOW-B2 bound five verbs (11 rows -> 16): 1127 px of
 * content in a 900 px frame. Nothing was broken — the backdrop scrolls and the
 * last row is reachable — which is exactly why it needed a measurement rather
 * than a look.
 *
 * The assertion is deliberately on the SCROLL, not on a pixel height: a height
 * budget would have to be re-guessed every time a row lands, and the question a
 * user has is "can I see it without scrolling", which `scrollHeight` answers
 * directly. It therefore keeps working as rows accumulate, and fails on the
 * commit that adds the row that does not fit — which is when somebody can still
 * decide what to do about it.
 */

/** The card's own geometry, read from the live overlay. */
async function cardMetrics(page: import("./fixtures").Page): Promise<{
  scrollHeight: number;
  clientHeight: number;
  cardHeight: number;
  lastRowBottom: number;
  viewportHeight: number;
}> {
  return page.evaluate(() => {
    const backdrop = document.querySelector<HTMLElement>(
      "[data-testid='shortcut-sheet-backdrop']",
    );
    const card = document.querySelector<HTMLElement>(
      "[data-testid='shortcut-sheet']",
    );
    if (backdrop === null || card === null) throw new Error("no key card");
    const rows = Array.from(
      document.querySelectorAll<HTMLElement>("[data-testid='shortcut-row']"),
    );
    const lastRowBottom = rows.reduce(
      (low, row) => Math.max(low, row.getBoundingClientRect().bottom),
      0,
    );
    return {
      scrollHeight: backdrop.scrollHeight,
      clientHeight: backdrop.clientHeight,
      cardHeight: Math.round(card.getBoundingClientRect().height),
      lastRowBottom: Math.round(lastRowBottom),
      viewportHeight: window.innerHeight,
    };
  });
}

for (const size of [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
]) {
  test(`the key card fits one screen at ${size.width}x${size.height}`, async ({
    page,
  }) => {
    await page.setViewportSize(size);
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Key card fit");

    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("feature-tree")).toBeVisible();
    await page.keyboard.press("?");
    await expect(page.getByTestId("shortcut-sheet")).toBeVisible();

    const metrics = await cardMetrics(page);
    // Reported unconditionally: the number is the evidence, and a spec that
    // only prints it on failure cannot show a density pass working.
    console.log(`key card ${size.width}x${size.height}:`, metrics);

    // Nothing is below the fold — the backdrop has nothing to scroll.
    expect(metrics.scrollHeight).toBeLessThanOrEqual(metrics.clientHeight);
    // …and the LAST row is fully inside the frame, not merely "not scrolled":
    // a card that overflowed with `overflow:hidden` would pass the line above.
    expect(metrics.lastRowBottom).toBeGreaterThan(0);
    expect(metrics.lastRowBottom).toBeLessThanOrEqual(metrics.viewportHeight);

    // NOT ASSERTED HERE: "the density pass did not buy its fit by dropping
    // rows". The obvious line — a floor on the rendered row count — was written
    // first and then MUTATION-TESTED by deleting a row from the registry: it
    // passed, because no hand-picked floor can notice 62 becoming 61, and a
    // floor that cannot fail for its own reason is this repo's most-repeated
    // defect. This spec is about FIT, and it says so by not pretending to cover
    // completeness too.
    //
    // THE GATE THAT ACTUALLY BITES IS `src/shortcuts/registry.test.ts` (W2
    // review, finding 4 — this comment used to name `ShortcutSheet.test.tsx`
    // and call it "strictly stronger", which is false and would have talked the
    // next reader out of a floor that was load-bearing). Measured: delete a row
    // from `PART_CREATE_SHORTCUTS` and `ShortcutSheet.test.tsx` reports 7/7
    // PASSED, because the sheet and `shortcutGroups()` are both derived from
    // the registry and move together — it is a gate agreeing with itself. The
    // same deletion reddens SEVEN cases in `registry.test.ts`, whose KEYED and
    // FLOW-B2 lists are hand-enumerated and therefore an independent reading.

    // The MODELLING block specifically: the reason the card exists this wave.
    const modelling = page.locator("[data-group='Modelling']");
    await expect(modelling).toBeVisible();
    const box = await modelling.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y + box!.height).toBeLessThanOrEqual(size.height);

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/shortcut-sheet-${size.width}.png`,
    });
  });
}
