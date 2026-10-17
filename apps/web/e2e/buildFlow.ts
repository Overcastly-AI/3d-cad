import { expect, type Page } from "./fixtures";

/**
 * Shared steps of the B-series building specs (docs/reference-parts/
 * buildings.md): the Build tools, the solve, and the cut list read row by row.
 */

/** One cut-list row: member, qty, length (document unit), stock. */
export type CutRow = [string, string, string, string];

/** The cut list reads *table* in order, with *total* pieces. */
export async function expectTable(
  page: Page,
  table: CutRow[],
  total: string,
): Promise<void> {
  const panel = page.getByTestId("cut-list-panel");
  await expect(panel.getByTestId("cut-list-total")).toHaveText(total, {
    timeout: 90_000,
  });
  const rows = panel.getByTestId("cut-list-row");
  await expect(rows).toHaveCount(table.length, { timeout: 30_000 });
  for (const [index, [member, qty, length, stock]] of table.entries()) {
    const row = rows.nth(index);
    await expect(row.getByTestId("cut-list-member")).toHaveText(member);
    await expect(row.getByTestId("cut-list-qty")).toHaveText(qty);
    await expect(row.getByTestId("cut-list-length")).toHaveText(length);
    await expect(row.getByTestId("cut-list-stock")).toHaveText(stock);
  }
}

export async function expectSolved(page: Page): Promise<void> {
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 90_000,
  });
}

export async function openCutList(page: Page): Promise<void> {
  const tool = page.getByTestId("cut-list-tool");
  await expect(tool).toBeEnabled({ timeout: 30_000 });
  if ((await page.getByTestId("cut-list-panel").count()) === 0) {
    await tool.click();
  }
  await expect(page.getByTestId("cut-list-panel")).toBeVisible();
}

/** Build ▾ > *title*: the tools behind the group's eyebrow (Door, Roof, ...). */
export async function openBuildTool(
  page: Page,
  pluginId: string,
  title: string,
): Promise<void> {
  await page.getByTestId("build-more").click();
  const tool = page.getByTestId(`plugin-tool-${pluginId}`);
  await expect(tool).toBeEnabled({ timeout: 30_000 });
  await expect(tool).toHaveAccessibleName(new RegExp(`^${title}`));
  await tool.click();
  await expect(page.getByTestId("plugin-editor")).toContainText(`New ${title}`);
}
