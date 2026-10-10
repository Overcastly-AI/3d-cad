import { expect, test, type Locator, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * PART-PARAMETERS step 8: formulas in every numeric field
 * (docs/RESEARCH.md §20), against the real stack.
 *
 *  - H = 20 in the Parameters panel, then an Extrude whose distance is typed
 *    as `H/2`: the field shows the formula with its `fx` mark and `= 10 mm`,
 *    the formula is stored as the feature's `expressions`, and the body is
 *    10 mm tall;
 *  - H = 40 in the panel re-drives the body to 20 mm; Ctrl+Z puts it back and
 *    Ctrl+Y forwards again;
 *  - a sketch dimension typed as a parameter (`W`, offered by the dimension
 *    box's autocomplete) re-drives with it;
 *  - an unknown name is refused on the field, and Save stays shut.
 */

/** A 20 × 20 square (a width and a height dimension), unextruded. */
const WIDTH_GLYPH = "glyph-8";

async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

async function expectVolume(page: Page, mm3: number): Promise<void> {
  await expect
    .poll(() => bodyVolume(page), { timeout: 45_000 })
    .toBeCloseTo(mm3, 0);
}

async function openPanel(page: Page): Promise<Locator> {
  await page.getByTestId("parameters-tool").click();
  const panel = page.getByTestId("parameters-panel");
  await expect(panel).toBeVisible();
  return panel;
}

function row(panel: Locator, name: string): Locator {
  return panel.locator(`[data-testid="parameter-row"][data-name="${name}"]`);
}

async function addParameter(
  page: Page,
  panel: Locator,
  name: string,
  expression: string,
): Promise<void> {
  await panel.getByTestId("parameters-add").click();
  const nameCell = panel.getByTestId("parameter-name").last();
  await expect(nameCell).toBeFocused();
  await nameCell.fill(name);
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  const expressionCell = row(panel, name).getByTestId("parameter-expression");
  await expect(expressionCell).toBeFocused();
  await expressionCell.fill(expression);
  await expressionCell.press("Enter");
  await expect(row(panel, name).getByTestId("parameter-value")).not.toHaveText(
    "—",
    { timeout: 30_000 },
  );
}

async function setParameter(
  panel: Locator,
  name: string,
  expression: string,
): Promise<void> {
  const cell = row(panel, name).getByTestId("parameter-expression");
  await cell.fill(expression);
  await cell.press("Enter");
  await expect(panel.getByTestId("parameters-saving")).toBeHidden({
    timeout: 30_000,
  });
}

interface StoredFeature {
  feature: {
    type: string;
    expressions?: Record<string, string> | null;
    params: Record<string, unknown>;
  };
}

async function storedFeatures(
  page: Page,
  partId: string,
  token: string,
): Promise<StoredFeature[]> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { features: StoredFeature[] }).features;
}

test.describe("parameters drive the model", () => {
  test("an extrude typed as H/2 and a sketch dimension typed as W follow the table", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Driven plate");
    await createFeature(page, account.token, part.id, {
      name: "Sketch1",
      feature: { type: "sketch", version: 1, params: SQUARE_20 },
      expected_tree_version: 0,
    });
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // H = 20.
    let panel = await openPanel(page);
    await addParameter(page, panel, "H", "20");
    await page.getByTestId("parameters-close").click();

    // Extrude, distance H/2: offered as it is typed, marked fx, read as 10.
    await page.getByTestId("new-extrude").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    const distance = page.getByTestId("extrude-distance");
    // Ctrl+Space lists what is in scope, the part's parameters first.
    await distance.fill("");
    await distance.press("Control+Space");
    const suggestions = page.getByTestId("extrude-distance-suggestions");
    await expect(suggestions.getByRole("option").first()).toHaveText("H20 mm");
    await distance.press("Enter");
    await expect(suggestions).toHaveCount(0);
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await distance.pressSequentially("/2");
    await expect(distance).toHaveValue("H/2");
    await expect(distance).toHaveAttribute("data-formula", "");
    await expect(page.getByTestId("extrude-distance-hint")).toHaveText(
      "= 10 mm",
    );
    await expect(
      page.getByTestId("extrude-editor").locator("[data-formula-mark]"),
    ).toHaveText("fx");
    await page.mouse.move(1400, 900);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/value-field-extrude-desktop.png`,
    });
    await distance.press("Enter");
    await expect(page.getByTestId("extrude-editor")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expectVolume(page, 20 * 20 * 10);
    const extrude = (await storedFeatures(page, part.id, account.token))[1];
    expect(extrude?.feature.expressions).toEqual({ "/distance_mm": "H/2" });
    expect(extrude?.feature.params.distance_mm).toBe(10);

    // Re-opened, the field shows the formula, not the number.
    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("extrude-distance")).toHaveValue("H/2");
    await page.getByTestId("extrude-cancel").click();
    await expect(page.getByTestId("extrude-editor")).toHaveCount(0);

    // H = 40: the body re-drives to 20 mm.
    panel = await openPanel(page);
    await setParameter(panel, "H", "40");
    await expectVolume(page, 20 * 20 * 20);

    // Undo puts H (and the body) back; redo forwards again.
    await expect(
      row(panel, "H").getByTestId("parameter-expression"),
    ).not.toBeFocused();
    await page.keyboard.press("Control+z");
    await expect(row(panel, "H").getByTestId("parameter-value")).toHaveText(
      "20 mm",
      { timeout: 30_000 },
    );
    await expectVolume(page, 20 * 20 * 10);
    await page.keyboard.press("Control+y");
    await expect(row(panel, "H").getByTestId("parameter-value")).toHaveText(
      "40 mm",
      { timeout: 30_000 },
    );
    await expectVolume(page, 20 * 20 * 20);

    // W = 30, then the sketch's width dimension typed as W.
    await addParameter(page, panel, "W", "30");
    await page.getByTestId("parameters-close").click();
    await page.getByTestId("feature-row").first().click({ button: "right" });
    await page.getByTestId("tree-ctx-edit").click();
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await page.getByTestId(WIDTH_GLYPH).click();
    const dimension = page.getByTestId("dimension-input");
    await expect(dimension).toBeVisible();
    await dimension.fill("");
    await dimension.pressSequentially("W");
    await expect(
      page.getByTestId("dimension-input-hint"),
      "the dimension box resolves the parameter as it is typed",
    ).toHaveText("= 30 mm");
    await dimension.press("Enter");
    await expect(page.getByTestId(WIDTH_GLYPH)).toHaveText("30", {
      timeout: 30_000,
    });
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expectVolume(page, 30 * 20 * 20);

    // W = 35 in the table: the sketch re-drives, and the extrude with it.
    panel = await openPanel(page);
    await setParameter(panel, "W", "35");
    await expectVolume(page, 35 * 20 * 20);
    await page.getByTestId("parameters-close").click();

    // An unknown name is refused on the field, and Save stays shut.
    await page.getByTestId("feature-select-1").click();
    const field = page.getByTestId("extrude-distance");
    await expect(field).toHaveValue("H/2");
    await field.fill("Q/2");
    await expect(
      page.getByTestId("extrude-editor").getByRole("alert"),
    ).toHaveText("Parameter 'Q' not found.");
    await expect(field).toHaveAttribute("aria-invalid", "true");
    await expect(page.getByTestId("extrude-submit")).toBeDisabled();
    await page.getByTestId("extrude-cancel").click();
    expect(
      (await storedFeatures(page, part.id, account.token))[1]?.feature
        .expressions,
    ).toEqual({ "/distance_mm": "H/2" });
  });
});
