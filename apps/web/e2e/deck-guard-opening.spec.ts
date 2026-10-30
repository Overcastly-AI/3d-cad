import { expectSolved, openBuildTool, openCutList } from "./buildFlow";
import { expect, type Page, test } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * DECK-GUARD-OPENING: B1's guard opens where its stair lands, as Chief
 * Architect's deck railing breaks at a stair. B1 is seeded at loft.deck
 * 1.3.0 with its guard on the open sides; Build ▾ > Stair picks it, every
 * default kept (centred on the rim at X 96, 36 in wide), and the deck
 * re-lays in the same write: the front guard opens between the outer
 * stringer faces, X 78 to X 114, a 4x4 post each side.
 *
 * By hand: each run either side, 78 in, takes posts at both ends and one
 * between (two 33.75 in bays), so the guard lists 10 posts at 36, rails 8 x
 * 66.75 (the sides) and 8 x 33.75 (the front's 6 x 59.3333 before), and 72
 * balusters (81 before). The stair no longer warns "Deck guard". A deck
 * saved at 1.2.0 keeps its guard and its stair warns; its update to 1.3.0
 * re-lays the front guard, so the editor offers it on its own, and after
 * it the warning is gone. Golden `b1-stair-30-guard-opening` pins the
 * geometry.
 */

function deck(version: string): Record<string, unknown> {
  return {
    type: "custom",
    version: 1,
    params: {
      plugin_id: "loft.deck",
      plugin_version: version,
      inputs: { guard: "open_sides" },
    },
  };
}

async function submit(page: Page): Promise<void> {
  const editor = page.getByTestId("plugin-editor");
  const button = page.getByTestId("plugin-submit");
  await expect(button).not.toHaveAttribute("aria-disabled", "true", {
    timeout: 90_000,
  });
  await button.click();
  await expect(editor).toBeHidden({ timeout: 60_000 });
  await expectSolved(page);
}

async function seed(
  page: Page,
  token: string,
  name: string,
  version: string,
): Promise<{ partId: string; deckId: string }> {
  const created = await page.request.post("/api/v1/parts", {
    data: { name, length_unit: "in" },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(created.ok(), await created.text()).toBe(true);
  const partId = ((await created.json()) as { id: string }).id;
  const made = await createFeature(page, token, partId, {
    name: "Deck",
    feature: deck(version),
    expected_tree_version: 0,
  });
  return { partId, deckId: made.feature.id };
}

async function addStair(page: Page, deckId: string): Promise<void> {
  await openBuildTool(page, "loft.stair", "Stair");
  await page.getByTestId("plugin-input-deck").selectOption(deckId);
  await expect(page.getByTestId("plugin-input-position_mm")).toHaveValue("96");
  await submit(page);
  await expect(page.getByTestId("feature-row")).toHaveCount(2);
}

type Row = [string, string, string];

async function expectGuard(page: Page, rows: Row[]): Promise<void> {
  await openCutList(page);
  const guard = page
    .getByTestId("cut-list-panel")
    .locator(
      '[data-testid="cut-list-row"]:is([data-member="Guard post"], [data-member="Rail"], [data-member="Baluster"])',
    );
  await expect(guard).toHaveCount(rows.length, { timeout: 90_000 });
  const got: Row[] = [];
  for (let k = 0; k < rows.length; k += 1) {
    const row = guard.nth(k);
    got.push([
      (await row.getByTestId("cut-list-member").innerText()).trim(),
      (await row.getByTestId("cut-list-qty").innerText()).trim(),
      (await row.getByTestId("cut-list-length").innerText()).trim(),
    ]);
  }
  expect([...got].sort()).toEqual([...rows].sort());
}

const OPEN: Row[] = [
  ["Guard post", "10", "36"],
  ["Rail", "8", "66.75"],
  ["Rail", "8", "33.75"],
  ["Baluster", "72", "25.5"],
];

test.describe("Deck guard opening — B1's guard opens at its stair", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a stair on B1's guarded rim opens the guard between its stringers, with a post each side, and an older deck updates to it", async ({
    page,
  }) => {
    test.setTimeout(420_000);
    const account = await seedSession(page);
    const fresh = await seed(page, account.token, "B1 guard opening", "1.3.0");

    await page.goto(`/parts/${fresh.partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(1);
    await expectSolved(page);
    await addStair(page, fresh.deckId);

    // The guard's lines: 10 posts, the front's rails at 33.75, 72 balusters.
    await expectGuard(page, OPEN);
    await page
      .getByTestId("cut-list-panel")
      .locator('[data-testid="cut-list-row"][data-member="Rail"]')
      .last()
      .scrollIntoViewIfNeeded();
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/deck-guard-opening-cut-list.png`,
    });

    // From above and in iso: the guard stops at the stair's stringers.
    await page.getByTestId("view-top").click();
    await page.getByTestId("view-fit").click();
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/deck-guard-opening-top.png`,
    });
    await page.getByTestId("view-iso").click();
    await page.getByTestId("view-fit").click();
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/deck-guard-opening-iso.png`,
    });

    // The stair no longer warns of the deck's guard.
    await page.getByTestId("feature-select-1").click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("Edit Stair");
    await expect(page.getByTestId("plugin-warning")).toHaveCount(0);
    await page.getByTestId("plugin-cancel").click();
    await expect(editor).toBeHidden();

    // A deck saved at 1.2.0: its guard stays across the stair, which warns.
    const saved = await seed(page, account.token, "B1 at 1.2.0", "1.2.0");
    await page.goto(`/parts/${saved.partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(1);
    await expectSolved(page);
    await addStair(page, saved.deckId);
    await page.getByTestId("feature-select-1").click();
    await expect(editor).toContainText("Edit Stair");
    const warning = page.getByTestId("plugin-warning");
    await expect(warning).toHaveCount(1);
    await expect(warning).toContainText("Deck guard");
    await expect(warning).toContainText("1.3.0 opens its guard at the stair");
    await page.getByTestId("plugin-cancel").click();
    await expect(editor).toBeHidden();

    // Its update re-lays the front guard: badged, offered on its own.
    await expect(page.getByTestId("feature-update-badge-0")).toBeVisible({
      timeout: 60_000,
    });
    await page.getByTestId("feature-select-0").click();
    await expect(editor).toContainText("Edit Deck");
    const notice = page.getByTestId("plugin-update-notice");
    await expect(notice).toContainText(
      "Re-lays 2 guard posts, 6 rails and 33 balusters to open the guard at the stair.",
    );
    await expect(notice).toContainText("Adds 2 guard posts and 2 rails.");
    await expect(page.getByTestId("plugin-update")).toHaveText(
      "Update to 1.3.0",
    );
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/deck-guard-opening-update.png`,
    });
    await page.getByTestId("plugin-update").click();
    await expect(editor).toBeHidden({ timeout: 60_000 });
    await expectSolved(page);
    await expect(page.getByTestId("feature-update-badge-0")).toHaveCount(0);
    await expectGuard(page, OPEN);
    await page.getByTestId("feature-select-1").click();
    await expect(editor).toContainText("Edit Stair");
    await expect(page.getByTestId("plugin-warning")).toHaveCount(0);
    await page.getByTestId("plugin-cancel").click();
  });
});
