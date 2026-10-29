import { expectSolved, openCutList } from "./buildFlow";
import { expect, type Page, test } from "./fixtures";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * DECK-FOOTINGS: B1 (docs/reference-parts/buildings.md) on pier footings, as
 * Chief Architect's deck room places a post footing under every post. Build
 * > Deck at 16 x 12 ft with every default: a Ø16 x 12 in round pier under
 * each of the 3 posts, its top at grade, bought as 80 lb bags.
 *
 * The cut list leads with Foundation: the 3 footings, 7 238.23 in³ as
 * 0.16 yd³, 4.19 ft³ x 1.05 / 0.60 = 7.33, so 8 bags at $6.48 = $51.84; and
 * 3 post bases (ABU66) at $28.97 = $86.91. The Deck framing follows,
 * unchanged. The 20 ft edit gives 4 footings, 9.77 so 10 bags, and 4 bases;
 * Ready-mix instead orders 0.25 yd³. Goldens
 * `plugin-deck-v1.2-b1-footings-16ft` and `-20ft` pin the geometry.
 */

const PLUGIN = "loft.deck";

type Row = [string, string, string, string, string];

/** The Foundation rows: member, qty, length, stock, extended price. */
const FOOTINGS_16: Row[] = [
  ["Footing", "3", "0.16 yd³", "8 bags", "$51.84"],
  ["Post base", "3", "—", "Each", "$86.91"],
];
const FOOTINGS_20: Row[] = [
  ["Footing", "4", "0.21 yd³", "10 bags", "$64.80"],
  ["Post base", "4", "—", "Each", "$115.88"],
];

async function expectFoundation(page: Page, rows: Row[]): Promise<void> {
  const panel = page.getByTestId("cut-list-panel");
  const foundation = panel.locator(
    '[data-testid="cut-list-row"][data-system="foundation"]',
  );
  await expect(foundation).toHaveCount(rows.length, { timeout: 90_000 });
  for (const [index, [member, qty, length, stock, ext]] of rows.entries()) {
    const row = foundation.nth(index);
    await expect(row.getByTestId("cut-list-member")).toHaveText(member);
    await expect(row.getByTestId("cut-list-qty")).toHaveText(qty);
    await expect(row.getByTestId("cut-list-length")).toHaveText(length);
    await expect(row.getByTestId("cut-list-stock")).toHaveText(stock);
    await expect(row.getByTestId("cut-list-ext-price")).toHaveText(ext);
  }
}

async function submit(page: Page): Promise<void> {
  const editor = page.getByTestId("plugin-editor");
  await page.getByTestId("plugin-submit").click();
  await expect(editor).toBeHidden({ timeout: 60_000 });
  await expectSolved(page);
}

test.describe("Deck footings — B1 on piers", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a new deck stands on a pier under each post, bought in 80 lb bags with post bases", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const account = await seedSession(page);
    const auth = { Authorization: `Bearer ${account.token}` };
    // $6.48 a bag and $28.97 a post base, saved as a yard's book would be.
    const book = await page.request.put("/api/v1/price-book", {
      data: {
        currency: "USD",
        entries: [
          {
            material: "concrete",
            profile: "concrete_bag_80",
            unit: "each",
            price_cents: 648,
          },
          {
            material: "steel_1018",
            profile: "post_base_6x6",
            unit: "each",
            price_cents: 2897,
          },
        ],
      },
      headers: { ...auth, "If-Match": '"0"' },
    });
    expect(book.ok(), await book.text()).toBe(true);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B1 deck on piers", length_unit: "in" },
      headers: auth,
    });
    expect(created.ok(), await created.text()).toBe(true);
    const partId = ((await created.json()) as { id: string }).id;

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(0);

    // Build > Deck: the footings are on by default, Ø16 x 12, in bags.
    const tool = page.getByTestId(`plugin-tool-${PLUGIN}`);
    await expect(tool).toBeEnabled({ timeout: 30_000 });
    await tool.click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("New Deck");
    await page.getByTestId("plugin-input-width_mm").fill("16 ft");
    await page.getByTestId("plugin-input-depth_mm").fill("12 ft");
    await expect(page.getByTestId("plugin-input-footings")).toHaveValue(
      "piers",
    );
    await expect(
      page.getByTestId("plugin-input-footing_diameter_mm"),
    ).toHaveValue("16");
    await expect(page.getByTestId("plugin-input-footing_depth_mm")).toHaveValue(
      "12",
    );
    await expect(
      page.getByTestId("plugin-input-footing_concrete-bags_80"),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(
      page.getByTestId("plugin-input-post_bases-yes"),
    ).toHaveAttribute("aria-pressed", "true");
    await submit(page);
    await expect(rows).toHaveCount(1);

    // One footing member under each post.
    await page.getByTestId("feature-unfold-0").click();
    const members = page.getByTestId("feature-member-row");
    await expect(members.filter({ hasText: "Footing" })).toHaveCount(3);
    await page.getByTestId("feature-unfold-0").click();

    // From the front: the piers below grade under the posts.
    await page.getByTestId("view-front").click();
    await page.getByTestId("view-fit").click();
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/deck-footings-front.png`,
    });
    await page.getByTestId("view-iso").click();

    await openCutList(page);
    await expectFoundation(page, FOOTINGS_16);
    const panel = page.getByTestId("cut-list-panel");
    await expect(
      panel.locator('[data-testid="cut-list-row"][data-system="deck"]'),
    ).toHaveCount(6);
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/deck-footings-cut-list.png`,
    });

    // The spec's edit, 16 -> 20 ft: a fourth post, so a fourth pier.
    await page.getByTestId("feature-select-0").click();
    await expect(editor).toContainText("Edit Deck");
    await page.getByTestId("plugin-input-width_mm").fill("20 ft");
    await submit(page);
    await openCutList(page);
    await expectFoundation(page, FOOTINGS_20);
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/deck-footings-20ft.png`,
    });

    // Ready-mix instead: SLAB's takeoff, 0.21 x 1.05 up to 0.25 yd³ (the
    // book prices no ready-mix, so the line stays blank).
    await page.getByTestId("feature-select-0").click();
    await page.getByTestId("plugin-input-footing_concrete-ready_mix").click();
    await submit(page);
    await openCutList(page);
    const footing = panel.locator(
      '[data-testid="cut-list-row"][data-member="Footing"]',
    );
    await expect(footing.getByTestId("cut-list-stock")).toHaveText("0.25 yd³", {
      timeout: 90_000,
    });
    await expect(footing.getByTestId("cut-list-ext-price")).toHaveText("");

    // A reload keeps the stored inputs.
    await page.reload();
    await expect(rows).toHaveCount(1);
    await expectSolved(page);
    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: auth,
    });
    const params = (
      (await tree.json()) as {
        features: {
          feature: {
            params: {
              plugin_version: string;
              inputs: Record<string, unknown>;
            };
          };
        }[];
      }
    ).features[0]?.feature.params;
    expect(params?.plugin_version).toBe("1.2.0");
    expect(params?.inputs.footing_concrete).toBe("ready_mix");
    expect(params?.inputs.footings).toBe("piers");
  });
});
