import { expectSolved, openBuildTool, openCutList } from "./buildFlow";
import { expect, type Page, test } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * STAIRS: B1's stair (docs/reference-parts/buildings.md B1 "Stair") in the
 * real app, as Chief Architect's Stair tool and Revit's Stair by Component
 * lay one out. B1's deck is seeded; Build ▾ > Stair picks it, every default
 * kept: on the rim centred at X 96, 36 in wide, 4 risers of 7.5 and 3
 * treads of 11, three cut 2x12 stringers and a 2x2 handrail on 4x4 posts.
 *
 * The cut list lists the stair under Stairs: 3 stringers 602.5 / √177.25 =
 * 45.2547 in, one 8 ft stock each (one piece), 6 treads 5/4x6 x 36, the
 * handrail 40.9633 and its posts 45.8864 and 66. Raising the deck to 36 in
 * re-lays the stair (5 risers of 7.2: 8 tread boards); no handrail on 4
 * risers is refused by IRC R311.7.8. A free 107.09375 in stair with closed
 * risers builds 14 risers and warns of its 4.9697 in throat (DCA6) and its
 * unguarded sides (R312.1.1). Goldens `b1-stair-*` and `free-stair-107` pin
 * the geometry.
 */

const DECK = {
  type: "custom",
  version: 1,
  params: { plugin_id: "loft.deck", plugin_version: "1.2.0", inputs: {} },
};

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

type Row = [string, string, RegExp, string];

/** The Stairs rows: member, qty, length, stock. */
const STAIRS_30: Row[] = [
  ["Stringer", "3", /^45\.254/, "8 ft"],
  ["Tread", "6", /^36$/, "8 ft"],
  ["Handrail", "1", /^40\.963/, "8 ft"],
  ["Handrail post", "1", /^45\.886/, "8 ft"],
  ["Handrail post", "1", /^66$/, "8 ft"],
];

async function expectStairs(page: Page, rows: Row[]): Promise<void> {
  const stairs = page
    .getByTestId("cut-list-panel")
    .locator('[data-testid="cut-list-row"][data-system="stairs"]');
  await expect(stairs).toHaveCount(rows.length, { timeout: 90_000 });
  for (const [index, [member, qty, length, stock]] of rows.entries()) {
    const row = stairs.nth(index);
    await expect(row.getByTestId("cut-list-member")).toHaveText(member);
    await expect(row.getByTestId("cut-list-qty")).toHaveText(qty);
    await expect(row.getByTestId("cut-list-length")).toHaveText(length);
    await expect(row.getByTestId("cut-list-stock")).toHaveText(stock);
  }
}

test.describe("Stairs — B1's stair and a free stair", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a stair on B1's rim lists its stringers, treads and handrail, follows the deck, and R311.7 refuses or warns by name", async ({
    page,
  }) => {
    test.setTimeout(420_000);
    const account = await seedSession(page);
    const auth = { Authorization: `Bearer ${account.token}` };
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B1 deck and stair", length_unit: "in" },
      headers: auth,
    });
    expect(created.ok(), await created.text()).toBe(true);
    const partId = ((await created.json()) as { id: string }).id;
    const deck = await createFeature(page, account.token, partId, {
      name: "Deck",
      feature: DECK,
      expected_tree_version: 0,
    });
    const deckId = deck.feature.id;

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(1);
    await expectSolved(page);

    // Build ▾ > Stair on the deck: the typed rise gives way to the pick.
    await openBuildTool(page, "loft.stair", "Stair");
    await expect(page.getByTestId("plugin-input-rise_mm")).toBeVisible();
    await page.getByTestId("plugin-input-deck").selectOption(deckId);
    await expect(page.getByTestId("plugin-input-rise_mm")).toHaveCount(0);
    await expect(page.getByTestId("plugin-input-position_mm")).toHaveValue(
      "96",
    );
    await expect(page.getByTestId("plugin-input-width_mm")).toHaveValue("36");
    await expect(page.getByTestId("plugin-input-max_riser_mm")).toHaveValue(
      "7.75",
    );
    await expect(page.getByTestId("plugin-input-tread_depth_mm")).toHaveValue(
      "11",
    );
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/stairs-form.png` });
    await submit(page);
    await expect(rows).toHaveCount(2);

    // Three stringers, six tread boards, the handrail and two posts.
    await page.getByTestId("feature-unfold-1").click();
    const members = page.getByTestId("feature-member-row");
    await expect(members.filter({ hasText: "Stringer" })).toHaveCount(3);
    await expect(members.filter({ hasText: "Tread" })).toHaveCount(6);
    await page.getByTestId("feature-unfold-1").click();

    await page.getByTestId("view-right").click();
    await page.getByTestId("view-fit").click();
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/stairs-b1-side.png` });
    // From above: the stair centred on the rim, its handrail on the left.
    await page.getByTestId("view-top").click();
    await page.getByTestId("view-fit").click();
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/stairs-b1.png` });
    await page.getByTestId("view-iso").click();

    await openCutList(page);
    await expectStairs(page, STAIRS_30);
    const stringer = page
      .getByTestId("cut-list-panel")
      .locator('[data-testid="cut-list-row"][data-member="Stringer"]');
    await expect(stringer.getByTestId("cut-list-caption")).toContainText(
      "2x12",
    );
    // The Stairs group, scrolled into the panel.
    await page
      .getByTestId("cut-list-panel")
      .locator('[data-testid="cut-list-row"][data-system="stairs"]')
      .last()
      .scrollIntoViewIfNeeded();
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/stairs-cut-list.png` });

    // The deck raised to 36 in: the stair re-lays in the same write, 5
    // risers of 7.2, so 4 treads of two boards.
    await page.getByTestId("feature-select-0").click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("Edit Deck");
    await page.getByTestId("plugin-input-height_mm").fill("36");
    await submit(page);
    await openCutList(page);
    const tread = page
      .getByTestId("cut-list-panel")
      .locator('[data-testid="cut-list-row"][data-member="Tread"]');
    await expect(tread.getByTestId("cut-list-qty")).toHaveText("8", {
      timeout: 90_000,
    });
    await page.getByTestId("view-right").click();
    await page.getByTestId("view-fit").click();
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/stairs-b1-36.png` });

    // No handrail on 5 risers: refused, naming R311.7.8.
    await page.getByTestId("feature-select-1").click();
    await expect(editor).toContainText("Edit Stair");
    await page.getByTestId("plugin-input-handrail-none").click();
    await page.getByTestId("plugin-submit").click();
    await expect(page.getByTestId("plugin-error")).toContainText("R311.7.8", {
      timeout: 60_000,
    });
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/stairs-refused.png` });
    await page.getByTestId("plugin-cancel").click();
    await expect(editor).toBeHidden();

    // A free interior stair, 107.09375 in, closed risers: 14 risers, and
    // it warns of its throat and its open sides.
    const free = await page.request.post("/api/v1/parts", {
      data: { name: "Free stair", length_unit: "in" },
      headers: auth,
    });
    expect(free.ok(), await free.text()).toBe(true);
    const freeId = ((await free.json()) as { id: string }).id;
    await page.goto(`/parts/${freeId}`);
    await expect(rows).toHaveCount(0);
    await openBuildTool(page, "loft.stair", "Stair");
    await page.getByTestId("plugin-input-rise_mm").fill("107.09375");
    await page.getByTestId("plugin-input-risers").selectOption("closed");
    await submit(page);
    await page.getByTestId("view-right").click();
    await page.getByTestId("view-fit").click();
    await openCutList(page);
    const riser = page
      .getByTestId("cut-list-panel")
      .locator('[data-testid="cut-list-row"][data-member="Riser"]');
    await expect(riser.getByTestId("cut-list-qty")).toHaveText("13", {
      timeout: 90_000,
    });
    await page.getByTestId("feature-select-0").click();
    const warnings = page.getByTestId("plugin-warning");
    await expect(warnings).toHaveCount(3);
    await expect(warnings.nth(0)).toContainText("Stringer throat");
    await expect(warnings.nth(0)).toContainText("4.9697 in");
    await expect(warnings.nth(1)).toContainText("Stringer span");
    await expect(warnings.nth(1)).toContainText(`11'-11"`);
    await expect(warnings.nth(2)).toContainText("R312.1.1");
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/stairs-free-warning.png`,
    });
    await page.getByTestId("plugin-cancel").click();

    // Stored at 1.0.0 with the deck's pick as made.
    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: auth,
    });
    const features = (
      (await tree.json()) as {
        features: {
          feature: {
            params: {
              plugin_version?: string;
              inputs?: Record<string, unknown>;
            };
          };
        }[];
      }
    ).features;
    expect(features[1]?.feature.params.plugin_version).toBe("1.0.0");
    expect(features[1]?.feature.params.inputs?.deck).toEqual({
      kind: "feature",
      feature_id: deckId,
    });
  });
});
