import { expectSolved, openBuildTool, openCutList } from "./buildFlow";
import { expect, type Page, test } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * CASEWORK (docs/reference-parts/casework.md): Build ▾ > Cabinets, a cabinet
 * run as ONE feature whose boxes are a list input, rendered by the generated
 * form as an add and remove list.
 *
 * C1: the new run is one frameless B24 in 3/4 plywood; its cut list lists,
 * under Casework, the 3/4 panels on two 4x8 sheets, the drawer box's 1/2
 * and 1/4 on one each, 24 ft of edge banding (282.4375 in), 2 hinges and a
 * pair of 22 in slides (golden c1-b24-frameless-casework). Adding a box
 * copies the last; an 18 in second box adds its hinges and slides.
 *
 * C3: a V3021 in 3/4 melamine, priced from its blanks to the last line, its
 * total the lines summed by hand (golden c3-v3021-melamine-frameless).
 *
 * On a wall: a run picked onto a typed wall's inside face, from its end.
 * The Pieces total counts bodies and Each items, never banding
 * (CASEWORK-B10); a new run is `loft.cabinets` 1.1.0.
 */

const IN = 25.4;

async function newPart(
  page: Page,
  token: string,
  name: string,
): Promise<string> {
  const created = await page.request.post("/api/v1/parts", {
    data: { name, length_unit: "in" },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(created.ok(), await created.text()).toBe(true);
  return ((await created.json()) as { id: string }).id;
}

function line(page: Page, profile: string) {
  return page
    .getByTestId("cut-list-panel")
    .locator(`[data-testid="cut-list-row"][data-profile="${profile}"]`);
}

async function expectLine(
  page: Page,
  profile: string,
  qty: string,
  stock: string,
): Promise<void> {
  const row = line(page, profile);
  await expect(row).toHaveCount(1, { timeout: 90_000 });
  await expect(row).toHaveAttribute("data-system", "casework");
  await expect(row.getByTestId("cut-list-qty")).toHaveText(qty);
  await expect(row.getByTestId("cut-list-stock")).toHaveText(stock);
}

async function inputs(
  page: Page,
  token: string,
  partId: string,
): Promise<Record<string, unknown> | undefined> {
  const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const rows = (
    (await tree.json()) as {
      features: {
        feature: { type: string; params: { inputs?: Record<string, unknown> } };
      }[];
    }
  ).features.filter((f) => f.feature.type === "custom");
  return rows[rows.length - 1]?.feature.params.inputs;
}

test.describe("Cabinets", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("C1: a B24 lists its panels by sheet, banding and hardware; Add box copies it", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const account = await seedSession(page);
    const partId = await newPart(page, account.token, "C1 B24");
    await page.goto(`/parts/${partId}`);

    await openBuildTool(page, "loft.cabinets", "Cabinets");
    const editor = page.getByTestId("plugin-editor");
    const boxes = page.getByTestId("plugin-input-boxes");
    await expect(boxes).toContainText("Boxes (1)");
    await expect(page.getByTestId("plugin-input-boxes-0-type")).toHaveValue(
      "base",
    );
    await expect(page.getByTestId("plugin-input-boxes-0-width_mm")).toHaveValue(
      "24",
    );
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 60_000 });
    await expectSolved(page);

    await openCutList(page);
    await expect(
      page.locator('[data-testid="cut-list-group"][data-system="casework"]'),
    ).toBeVisible({ timeout: 90_000 });
    await expectLine(page, "3/4 plywood", "10", "2 × 4x8");
    await expectLine(page, "1/2 plywood", "4", "1 × 4x8");
    await expectLine(page, "1/4 plywood", "1", "1 × 4x8");
    await expectLine(page, "Edge banding 7/8 in", "7", "24 ft");
    await expect(
      line(page, "Edge banding 7/8 in").getByTestId("cut-list-length"),
    ).toContainText("282");
    await expectLine(page, "Concealed hinge", "2", "Each");
    await expectLine(page, "Drawer slides 22 in, pair", "1", "Each");
    // Pieces (CASEWORK-B10): the 15 panels, 2 hinges and 1 slide pair; the
    // banding line's 7 banded panels are not counted again.
    await expect(page.getByTestId("cut-list-total")).toHaveText("18");
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/casework-c1-b24.png` });

    // Edit: Add box copies the B24; an 18 in second box.
    await page.getByTestId("feature-select-0").click();
    await expect(editor).toContainText("Edit Cabinets");
    await page.getByTestId("plugin-input-boxes-add").click();
    await expect(boxes).toContainText("Boxes (2)");
    const width = page.getByTestId("plugin-input-boxes-1-width_mm");
    await expect(width).toHaveValue("24");
    // A width off the 3 in steps names its box.
    await width.fill("19");
    await page.getByTestId("plugin-submit").click();
    await expect(page.getByTestId("plugin-error")).toContainText("Box 2", {
      timeout: 60_000,
    });
    await width.fill("18");
    await page.screenshot({ path: `${SCREENSHOT_DIR}/casework-box-list.png` });
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 60_000 });
    await expectSolved(page);
    await openCutList(page);
    await expectLine(page, "Concealed hinge", "4", "Each");
    const slides = line(page, "Drawer slides 22 in, pair");
    await expect(slides.getByTestId("cut-list-qty")).toHaveText("2", {
      timeout: 90_000,
    });
    const stored = await inputs(page, account.token, partId);
    expect(stored?.boxes).toEqual([
      expect.objectContaining({ type: "base", width_mm: 24 * IN }),
      expect.objectContaining({ type: "base", width_mm: 18 * IN }),
    ]);

    // Remove takes the second box away again.
    await page.getByTestId("feature-select-0").click();
    await page.getByTestId("plugin-input-boxes-remove").nth(1).click();
    await expect(boxes).toContainText("Boxes (1)");
    await expect(page.getByTestId("plugin-input-boxes-remove")).toBeDisabled();
  });

  test("C3: a melamine V3021 prices to the last line", async ({ page }) => {
    test.setTimeout(240_000);
    const account = await seedSession(page);
    const partId = await newPart(page, account.token, "C3 V3021");
    await page.goto(`/parts/${partId}`);

    await openBuildTool(page, "loft.cabinets", "Cabinets");
    const editor = page.getByTestId("plugin-editor");
    await page.getByTestId("plugin-input-carcass").selectOption("melamine");
    await page.getByTestId("plugin-input-boxes-0-type").selectOption("vanity");
    await page.getByTestId("plugin-input-boxes-0-width_mm").fill("30");
    await page.getByTestId("plugin-input-boxes-0-shelves").fill("0");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 60_000 });
    await expectSolved(page);

    await openCutList(page);
    await expectLine(page, "3/4 melamine", "10", "2 × 4x8");
    await expectLine(page, "Edge banding 7/8 in", "7", "29 ft");
    await expectLine(page, "Concealed hinge", "4", "Each");
    // Pieces: 10 panels and 4 hinges, never the banding.
    await expect(page.getByTestId("cut-list-total")).toHaveText("14");
    const panel = page.getByTestId("cut-list-panel");
    const total = panel.getByTestId("cut-list-price-total");
    await expect(total).toHaveText("");

    // Each blank opens the book on its line; type the price, Enter.
    const dialog = page.getByTestId("price-book-dialog");
    for (const [profile, key, price] of [
      ["3/4 melamine", "melamine_3_4", "42.98"],
      ["Edge banding 7/8 in", "edge_banding", "0.35"],
      ["Concealed hinge", "hinge", "4.50"],
    ] as const) {
      await line(page, profile).getByTestId("cut-list-price-blank").click();
      await expect(dialog).toBeVisible();
      const row = dialog.locator(
        `[data-testid="price-book-row"][data-profile="${key}"]`,
      );
      await expect(row).toHaveCount(1);
      const field = row.getByTestId("price-book-price");
      await expect(field).toBeFocused();
      await field.fill(price);
      if (key === "edge_banding") {
        await expect(row.getByTestId("price-book-material")).toHaveValue("pvc");
        await expect(row.getByTestId("price-book-unit-item")).toHaveText(
          "Per ft",
        );
        await page.screenshot({
          path: `${SCREENSHOT_DIR}/casework-c3-price-book.png`,
        });
      }
      await field.press("Enter");
      await expect(dialog).toBeHidden({ timeout: 30_000 });
    }

    // 2 sheets x $42.98 + 29 ft x $0.35 + 4 x $4.50 = $114.11.
    await expect(total).toHaveText("$114.11", { timeout: 30_000 });
    await expect(panel.getByTestId("cut-list-unpriced")).toHaveCount(0);
    await total.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/casework-c3-priced.png` });
  });

  test("a run sits on a picked wall's inside face, from its end", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const account = await seedSession(page);
    const partId = await newPart(page, account.token, "Wall run");
    // A 12 ft 2x4 wall along X from the origin, framed to the right of its
    // line: its inside face 3.5 in from it, where the run's backs sit.
    await createFeature(page, account.token, partId, {
      name: "Wall",
      feature: {
        type: "custom",
        version: 1,
        params: {
          plugin_id: "loft.wall",
          plugin_version: "1.1.0",
          inputs: { length_mm: 144 * IN },
        },
      },
      expected_tree_version: 0,
    });
    await page.goto(`/parts/${partId}`);
    await expectSolved(page);

    await openBuildTool(page, "loft.cabinets", "Cabinets");
    const editor = page.getByTestId("plugin-editor");
    await page.getByTestId("plugin-input-wall").selectOption({ label: "Wall" });
    // A picked wall hides the typed position.
    await expect(page.getByTestId("plugin-input-x_mm")).toHaveCount(0);
    await page.getByTestId("plugin-input-measure_from-end").click();
    await page.getByTestId("plugin-input-offset_mm").fill("12");
    await page.getByTestId("plugin-input-boxes-add").click();
    await page.getByTestId("plugin-input-boxes-1-width_mm").fill("36");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/casework-wall-run-form.png`,
    });
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 60_000 });
    await expectSolved(page);
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/casework-wall-run.png` });
    const stored = await inputs(page, account.token, partId);
    expect(stored?.measure_from).toBe("end");
    // A new run is loft.cabinets 1.1.0 (CASEWORK-B10); a line wall's
    // inside face is its framing, so it sits where 1.0.0 put it.
    const rows = (
      (await (
        await page.request.get(`/api/v1/parts/${partId}/features`, {
          headers: { Authorization: `Bearer ${account.token}` },
        })
      ).json()) as {
        features: { feature: { params: { plugin_version?: string } } }[];
      }
    ).features;
    expect(rows[rows.length - 1]?.feature.params.plugin_version).toBe("1.1.0");
    expect(stored?.boxes).toHaveLength(2);
  });
});
