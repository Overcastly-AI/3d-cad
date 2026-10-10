import { expect, test, type Locator, type Page } from "./fixtures";

import { seedCube } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * PART-PARAMETERS step 7: the Parameters panel (docs/RESEARCH.md §20),
 * Fusion's Change Parameters as a modeless side panel, against the real stack.
 *
 *  - W = 40 and H = W - 15 read 25 mm in the Value column (the server's
 *    evaluation, not the client's);
 *  - Escape puts a cell back; a cycle is refused on the row as its chain, with
 *    the typed text kept in the cell;
 *  - Ctrl+Z restores the previous table and Ctrl+Y brings it back, through the
 *    workspace's own history (one PUT = one undo step);
 *  - the table survives a reload;
 *  - in an inch document a bare `2` is sent as `2 in` and every value reads
 *    in inches.
 */

interface StoredParameter {
  name: string;
  expression: string;
  unit: string;
  value: number;
}

async function storedParameters(
  page: Page,
  partId: string,
  token: string,
): Promise<StoredParameter[]> {
  const response = await page.request.get(
    `/api/v1/parts/${partId}/parameters`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { parameters: StoredParameter[] })
    .parameters;
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

/** Add a row: Add focuses its Name; Tab to Expression; Enter commits. */
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
  // Tab passes the Unit cell on its way to Expression.
  await page.keyboard.press("Tab");
  const expressionCell = row(panel, name).getByTestId("parameter-expression");
  await expect(expressionCell).toBeFocused();
  await expressionCell.fill(expression);
  await expressionCell.press("Enter");
  await expect(panel.getByTestId("parameters-saving")).toBeHidden({
    timeout: 30_000,
  });
}

test.describe("parameters panel", () => {
  test("define, refuse a cycle, undo, redo and reload", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Param plate");
    await seedCube(page, account.token, part.id);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("new-sketch")).toBeEnabled();

    const panel = await openPanel(page);
    await expect(panel.getByTestId("parameters-empty")).toContainText(
      "every feature that uses it follows",
    );

    await addParameter(page, panel, "W", "40");
    await expect(row(panel, "W").getByTestId("parameter-value")).toHaveText(
      "40 mm",
    );
    await addParameter(page, panel, "H", "W - 15");
    await expect(row(panel, "H").getByTestId("parameter-value")).toHaveText(
      "25 mm",
    );

    // Escape puts the cell back and sends nothing.
    const wExpression = row(panel, "W").getByTestId("parameter-expression");
    await wExpression.fill("99");
    await wExpression.press("Escape");
    await expect(wExpression).toHaveValue("40");

    // A loop is refused on the row, as its chain, and the text stays.
    await wExpression.fill("H + 1");
    await wExpression.press("Enter");
    const refusal = panel.getByTestId("parameter-row-error");
    await expect(refusal).toHaveText(
      /Circular reference: (W → H → W|H → W → H)/,
      {
        timeout: 30_000,
      },
    );
    await expect(wExpression).toHaveValue("H + 1");
    await expect(wExpression).toHaveAttribute("aria-invalid", "true");
    // Nothing was stored.
    expect(
      (await storedParameters(page, part.id, account.token)).map(
        (p) => p.expression,
      ),
    ).toEqual(["40", "W - 15"]);

    // Putting the text back clears the refusal without a write.
    await wExpression.fill("40");
    await wExpression.press("Enter");
    await expect(refusal).toBeHidden();

    // Ctrl+Z restores the previous table: H goes; Ctrl+Y brings it back.
    await expect(wExpression).not.toBeFocused();
    await page.keyboard.press("Control+z");
    await expect(panel.getByTestId("parameter-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(row(panel, "W").getByTestId("parameter-value")).toHaveText(
      "40 mm",
    );
    await page.keyboard.press("Control+y");
    await expect(row(panel, "H").getByTestId("parameter-value")).toHaveText(
      "25 mm",
      { timeout: 30_000 },
    );

    // It survives a reload.
    await page.reload();
    await expect(page.getByTestId("new-sketch")).toBeEnabled();
    const reloaded = await openPanel(page);
    await expect(reloaded.getByTestId("parameter-row")).toHaveCount(2);
    await expect(
      row(reloaded, "H").getByTestId("parameter-expression"),
    ).toHaveValue("W - 15");
    await expect(row(reloaded, "H").getByTestId("parameter-value")).toHaveText(
      "25 mm",
    );

    // A few more for the picture: an angle, a count, comments.
    await addParameter(page, reloaded, "Draft", "3 deg");
    await expect(
      row(reloaded, "Draft").getByTestId("parameter-value"),
    ).toHaveText("3°");
    await addParameter(page, reloaded, "Holes", "6");
    await row(reloaded, "Holes")
      .getByTestId("parameter-unit")
      .selectOption("unitless");
    await expect(
      row(reloaded, "Holes").getByTestId("parameter-value"),
    ).toHaveText("6", { timeout: 30_000 });
    const comment = row(reloaded, "W").getByTestId("parameter-comment");
    await comment.fill("Overall width");
    await comment.press("Enter");
    await expect
      .poll(async () =>
        (await storedParameters(page, part.id, account.token)).map((p) => [
          p.name,
          p.unit,
          p.value,
        ]),
      )
      .toEqual([
        ["W", "length", 40],
        ["H", "length", 25],
        ["Draft", "angle", 3],
        ["Holes", "unitless", 6],
      ]);
    await page.mouse.move(0, 0);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/parameters-panel-desktop.png`,
    });
  });

  test("an inch document sends bare numbers in inches and reads in inches", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "Inch params", length_unit: "in" },
      headers: { Authorization: `Bearer ${account.token}` },
    });
    expect(created.ok()).toBe(true);
    const part = (await created.json()) as { id: string };
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("new-sketch")).toBeEnabled();

    const panel = await openPanel(page);
    await addParameter(page, panel, "L", "2");
    await expect(row(panel, "L").getByTestId("parameter-value")).toHaveText(
      "2 in",
    );
    // The stored expression says what it means.
    await expect(
      row(panel, "L").getByTestId("parameter-expression"),
    ).toHaveValue("2 in");
    await addParameter(page, panel, "M", "L + 25.4 mm");
    await expect(row(panel, "M").getByTestId("parameter-value")).toHaveText(
      "3 in",
    );
    const stored = await storedParameters(page, part.id, account.token);
    expect(stored.map((p) => [p.name, p.expression])).toEqual([
      ["L", "2 in"],
      ["M", "L + 25.4 mm"],
    ]);
    expect(stored[0]?.value).toBeCloseTo(50.8, 9);
    expect(stored[1]?.value).toBeCloseTo(76.2, 9);
  });
});
