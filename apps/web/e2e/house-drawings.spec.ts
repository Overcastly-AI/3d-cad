import { readFile } from "node:fs/promises";

import type { Locator, Page } from "@playwright/test";

import { seedSavedB7 } from "./b7Saved";
import { expectSolved } from "./buildFlow";
import { expect, test } from "./fixtures";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * HOUSE-DRAWINGS on B7 (docs/reference-parts/buildings.md): a builder takes the
 * house to a permit desk or a crew. The part editor's Export ▾ > Drawing opens
 * a sheet drafting the part (QA-PART-DRAWING-CMD); House set lays out, as
 * Revit and Chief Architect do,
 *
 *  - Plan: a horizontal section 48 in above the subfloor (Revit's 4'-0"), with
 *    Chief's automatic exterior strings to the opening centres: B7's front
 *    openings on X 60, 144 and 228 read 5'-0", 7'-0", 7'-0", 5'-0"; the back
 *    window on X 144, 12'-0" + 12'-0"; each side window centred, 8'-0" +
 *    8'-0"; the framing 24'-0" x 16'-0" overall;
 *  - Elevations: the plate 97.125 above the subfloor (1.5 + 92.625 + 3), 8'-1
 *    1/8", and the heads at 82.5, 6'-10 1/2" — feet-inch to 1/16 in
 *    (QA-DRAWING-DECIMALS);
 *  - Materials: the cut list as a yard order (Item, Qty, Size, Length,
 *    Material, Price) on its own sheet (CUT-LIST-PDF), equal to the cut-list
 *    panel line for line and to the cent, in the PDF and in the CSV
 *    (DRAWING-PARTS-LIST-EXPORT).
 *
 * Every number is buildings.md's (the kernel test test_house_drawings.py
 * checks the same against an independent section).
 */

/** A small book: the house's lumber per foot and its two sheet goods. */
const BOOK = [
  ["spf_lumber", "us_2x10", 144],
  ["spf_lumber", "us_2x8", 112],
  ["spf_lumber", "us_2x6", 81],
  ["southern_pine_pt", "us_2x6", 106],
].map(([material, profile, cents]) => ({
  material,
  profile,
  unit: "linear_foot",
  stock_length_ft: null,
  sheet: null,
  price_cents: cents,
}));
const SHEETS = [
  { material: "plywood", profile: "plywood_23_32", sheet: "4x8", cents: 4250 },
  { material: "osb", profile: "osb_7_16", sheet: "4x9", cents: 2498 },
].map(({ material, profile, sheet, cents }) => ({
  material,
  profile,
  unit: "each",
  stock_length_ft: null,
  sheet,
  price_cents: cents,
}));

async function seedPriceBook(page: Page, token: string): Promise<void> {
  const auth = { Authorization: `Bearer ${token}` };
  const read = await page.request.get("/api/v1/price-book", { headers: auth });
  const { version } = (await read.json()) as { version: number };
  const saved = await page.request.put("/api/v1/price-book", {
    headers: { ...auth, "If-Match": `"${version}"` },
    data: { currency: "USD", entries: [...BOOK, ...SHEETS] },
  });
  expect(saved.ok(), await saved.text()).toBe(true);
}

/** The values a view's dimensions stamp, in the composer's order. */
async function dimensionValues(view: Locator): Promise<string[]> {
  return view
    .getByTestId("drawing-dimension")
    .evaluateAll((els) =>
      els.map((el) => el.getAttribute("data-dimension-value") ?? ""),
    );
}

/** "$1,234.56" or "" as integer cents (null for a blank). */
function cents(text: string): number | null {
  const t = text.trim().replace(/[$,]/g, "");
  return t === "" ? null : Math.round(Number(t) * 100);
}

/** RFC 4180 rows (quoted cells may hold commas). */
function csvRows(text: string): string[][] {
  return text
    .trim()
    .split("\r\n")
    .map((line) => {
      const cells: string[] = [];
      let cell = "";
      let quoted = false;
      for (let i = 0; i < line.length; i += 1) {
        const ch = line[i];
        if (quoted) {
          if (ch === '"' && line[i + 1] === '"') {
            cell += '"';
            i += 1;
          } else if (ch === '"') quoted = false;
          else cell += ch;
        } else if (ch === '"') quoted = true;
        else if (ch === ",") {
          cells.push(cell);
          cell = "";
        } else cell += ch;
      }
      cells.push(cell);
      return cells;
    });
}

/** The PDF's text runs, as reportlab writes them uncompressed: (x, y, text). */
function pdfRows(pdf: string): string[][] {
  const runs: { x: number; y: number; text: string }[] = [];
  const re = /BT 1 0 0 -1 ([\d.]+) ([\d.]+) Tm \(((?:\\.|[^\\)])*)\) Tj/g;
  for (const m of pdf.matchAll(re)) {
    runs.push({
      x: Number(m[1]),
      y: Number(m[2]),
      text: (m[3] ?? "").replace(/\\(.)/g, "$1"),
    });
  }
  const byY = new Map<number, { x: number; text: string }[]>();
  for (const run of runs) {
    const key = Math.round(run.y * 10);
    byY.set(key, [...(byY.get(key) ?? []), run]);
  }
  return [...byY.entries()]
    .sort(([a], [b]) => a - b)
    .map(([, row]) => row.sort((a, b) => a.x - b.x).map((r) => r.text));
}

test.describe("house drawings (HOUSE-DRAWINGS)", () => {
  test.setTimeout(420_000);

  test("B7's plan, elevations and materials list", async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    const account = await seedSession(page);
    await seedPriceBook(page, account.token);
    const partId = await seedSavedB7(page, account.token, "B7 house");

    // The part editor's Export ▾ > Drawing (QA-PART-DRAWING-CMD).
    await page.goto(`/parts/${partId}`);
    await expectSolved(page);
    const exportMore = page.getByTestId("part-export-band-more");
    await expect(exportMore).toBeEnabled({ timeout: 60_000 });
    await exportMore.click();
    const drawingCommand = page.getByTestId("part-drawing");
    await expect(drawingCommand).toBeEnabled({ timeout: 60_000 });
    await expect(drawingCommand).toHaveAccessibleName(/Drawing/);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/house-drawings-part-command.png`,
      clip: { x: 800, y: 0, width: 800, height: 240 },
    });
    await drawingCommand.click();
    await expect(page).toHaveURL(/\/drawings\/[^?]+\?source=/, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("drawing-part-select")).toHaveValue(partId, {
      timeout: 30_000,
    });

    // House set: three sheets, laid out in one action.
    const houseSet = page.getByTestId("drawing-house-set");
    await expect(houseSet).toBeEnabled();
    await houseSet.click();
    await expect(page.getByTestId("sheet-tab-2")).toBeVisible({
      timeout: 60_000,
    });

    // Plan: the strings, in feet-inch.
    const plan = page.locator('[data-testid="drawing-view"][data-view="plan"]');
    await expect(plan).toBeVisible({ timeout: 180_000 });
    await expect(plan.getByTestId("drawing-dimension")).toHaveCount(14, {
      timeout: 60_000,
    });
    expect(await dimensionValues(plan)).toEqual([
      // Front (below the plan): to the opening centres, then overall.
      `5'-0"`,
      `7'-0"`,
      `7'-0"`,
      `5'-0"`,
      `24'-0"`,
      // Back.
      `12'-0"`,
      `12'-0"`,
      `24'-0"`,
      // Left, then right side.
      `8'-0"`,
      `8'-0"`,
      `16'-0"`,
      `8'-0"`,
      `8'-0"`,
      `16'-0"`,
    ]);
    // The front string really is below the plan, and reads left to right.
    const front = await plan
      .getByTestId("drawing-dimension-value")
      .evaluateAll((els) =>
        els.slice(0, 4).map((el) => {
          const r = el.getBoundingClientRect();
          return { x: r.x, y: r.y };
        }),
      );
    const planBox = await plan.locator("line").first().boundingBox();
    expect(planBox).not.toBeNull();
    for (const [i, at] of front.entries()) {
      expect(at.y).toBeGreaterThan(planBox?.y ?? 0);
      if (i > 0) expect(at.x).toBeGreaterThan(front[i - 1]?.x ?? 0);
    }
    await expect(plan.getByTestId("drawing-hatch")).toHaveCount(1);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/house-drawings-plan.png`,
    });

    // Elevations: heads and plate above the subfloor.
    await page.getByTestId("sheet-tab-1").click();
    const elevation = (side: string) =>
      page.locator(
        `[data-testid="drawing-view"][data-view="elevation_${side}"]`,
      );
    for (const side of ["front", "back", "left", "right"]) {
      await expect(elevation(side)).toBeVisible({ timeout: 180_000 });
      expect(await dimensionValues(elevation(side))).toEqual([
        `6'-10 1/2"`,
        `8'-1 1/8"`,
      ]);
    }
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/house-drawings-elevations.png`,
    });

    // Materials: the sheet's yard order equals the cut-list panel.
    await page.getByTestId("sheet-tab-2").click();
    const table = page.getByTestId("drawing-materials-table");
    await expect(table).toBeVisible({ timeout: 180_000 });
    const panel = page.getByTestId("cut-list-panel");
    await expect(panel.getByTestId("cut-list-row").first()).toBeVisible({
      timeout: 120_000,
    });
    const panelRows = await panel
      .getByTestId("cut-list-row")
      .evaluateAll((rows) =>
        rows.map((row) => ({
          member:
            row.querySelector('[data-testid="cut-list-member"]')?.textContent ??
            "",
          price:
            row.querySelector('[data-testid="cut-list-ext-price"]')
              ?.textContent ?? "",
        })),
      );
    const panelTotal =
      (await panel.getByTestId("cut-list-price-total").textContent()) ?? "";
    expect(panelRows.length).toBeGreaterThan(10);
    expect(cents(panelTotal)).not.toBeNull();

    const sheetLines = await table
      .getByTestId("drawing-materials-row")
      .evaluateAll((rows) =>
        rows.map((row) => ({
          kind: row.getAttribute("data-row-kind"),
          cells: [
            ...row.querySelectorAll('[data-testid="drawing-materials-cell"]'),
          ].map((c) => c.textContent ?? ""),
        })),
      );
    const lines = sheetLines.filter((row) => row.kind === "line");
    expect(lines.map((row) => row.cells[0])).toEqual(
      panelRows.map((row) => row.member),
    );
    // The last cell of a priced line is its price; an unpriced line has none.
    expect(
      lines.map((row) => {
        const last = row.cells[row.cells.length - 1] ?? "";
        return last.startsWith("$") ? cents(last) : null;
      }),
    ).toEqual(panelRows.map((row) => cents(row.price)));
    const sheetTotal = sheetLines.find((row) => row.kind === "total");
    expect(cents(sheetTotal?.cells[sheetTotal.cells.length - 1] ?? "")).toBe(
      cents(panelTotal),
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/house-drawings-materials.png`,
    });

    // The PDF a yard receives: the same lines, to the cent.
    const pdfDownload = page.waitForEvent("download");
    await page.getByTestId("drawing-export-pdf").click();
    const pdf = await readFile(
      (await (await pdfDownload).path()) ?? "",
      "latin1",
    );
    const rows = pdfRows(pdf);
    const header = rows.findIndex((r) => r[0] === "ITEM");
    const totalAt = rows.findIndex((r) => r[0]?.startsWith("Total") ?? false);
    expect(header).toBeGreaterThanOrEqual(0);
    const pdfLines = rows
      .slice(header + 1, totalAt)
      .filter((r) => r.length > 1);
    expect(pdfLines.map((r) => r[0])).toEqual(panelRows.map((r) => r.member));
    expect(
      pdfLines.map((r) => {
        const last = r[r.length - 1] ?? "";
        return last.startsWith("$") ? cents(last) : null;
      }),
    ).toEqual(panelRows.map((row) => cents(row.price)));
    const pdfTotal = rows[totalAt] ?? [];
    expect(cents(pdfTotal[pdfTotal.length - 1] ?? "")).toBe(cents(panelTotal));

    // The CSV: the same lines, to the cent.
    const csvDownload = page.waitForEvent("download");
    await page.getByTestId("drawing-export-csv").click();
    const download = await csvDownload;
    expect(download.suggestedFilename()).toBe("B7 house materials.csv");
    const csv = csvRows(await readFile((await download.path()) ?? "", "utf-8"));
    const csvLines = csv.slice(1, -1);
    expect(csvLines.map((r) => r[1])).toEqual(panelRows.map((r) => r.member));
    expect(csvLines.map((r) => cents(r[r.length - 1] ?? ""))).toEqual(
      panelRows.map((row) => cents(row.price)),
    );
    const csvTotal = csv[csv.length - 1] ?? [];
    expect(cents(csvTotal[csvTotal.length - 1] ?? "")).toBe(cents(panelTotal));
  });
});
