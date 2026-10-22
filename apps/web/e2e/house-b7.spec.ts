import { readFile } from "node:fs/promises";

import type { Locator, Page } from "@playwright/test";

import {
  type CutRow,
  expectSolved,
  expectTable,
  openBuildTool,
  openCutList,
} from "./buildFlow";
import { expect, test } from "./fixtures";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * QA-B7-HOUSE: B7 of docs/reference-parts/buildings.md, the 24 x 16 ft house,
 * built in the real app from Build features only and priced to the cut list's
 * last priceable line.
 *
 *  - Floor 288 x 192, 2x10 joists along Y at 16 in o.c., PT 2x6 sills and the
 *    23/32 plywood subfloor (framing top 10.75, subfloor top 11.46875).
 *  - Four 2x6 walls with 7/16 OSB, drawn clockwise and standing on the
 *    subfloor (base elevation typed by hand: SHEATHING-WALL-BASE).
 *  - A 36 x 80 door at X 144 and two 36 x 48 windows at X 60 and 228 in the
 *    front wall (it runs from X 288 to 0, so their offsets are 144, 228, 60);
 *    a 36 x 48 window at X 144 in the back; a 24 x 36 window centred in each
 *    side.
 *  - A 6/12 gable of 2x8 rafters at 24 in o.c. on a 2x10 ridge, 12 in
 *    overhang, on the typed bearing: plate 108.59375 high (11.46875 +
 *    97.125) and 5.5 wide (ROOF-GABLE-WALLS: a gable cannot pick walls).
 *
 * The numbers are an independent calculation from buildings.md's rules:
 * studs, cripples, headers and plates by the B2 layout rules, rafters (95.25 +
 * 12) x sqrt(1.25) + 7.25 x 6/12 = 123.5341 overall, and the volume as the
 * members' prisms less each rafter's birdsmouth: 264 895.4795 in³ (the STEP
 * export measured the same, 217 solids).
 *
 * Priced through the blank prices: the eight single-stock keys, then the
 * rim's blank, whose seeded row is turned to an 8 ft SPF 2x10 at $11.47. The
 * five lines over 20 ft are spliced (CUT-LIST-LONG-STOCK): rims and ridge
 * 16 ft + 8 ft, top plates 16 ft + 8 ft, PT sills and bottom plate 2 x 12 ft,
 * so B7 prices to the last line at $2,868.87, as loft-wire's
 * test_b7_is_priced_to_the_last_line_2868_87 sums it by hand ($2,608.83 for
 * the 18 short lines + $260.04 of splices).
 *
 * Then the three named edits, each from the base house: the front left
 * window moved 24 in (undone with Ctrl+Z), pitch 6/12 -> 8/12 (set back), and
 * length 24 -> 28 ft, which takes eight feature edits because the openings
 * are placed from the front wall's start (X 288 -> 336).
 */

/** The walls, clockwise: start x, start y, direction, length (in). */
const WALLS: [string, string, string, string][] = [
  ["288", "0", "180", "288"], // front, Y 0..5.5
  ["0", "5.5", "90", "181"], // left, X 0..5.5
  ["0", "192", "0", "288"], // back, Y 186.5..192
  ["288", "186.5", "270", "181"], // right, X 282.5..288
];

/** Plugin, title, host wall, offset (in), a 36 x 48 window. */
const OPENINGS: [string, string, string, string, boolean][] = [
  ["loft.door", "Door", "Wall 1", "144", false],
  ["loft.window", "Window", "Wall 1", "228", true], // X 60, front left
  ["loft.window", "Window", "Wall 1", "60", true], // X 228
  ["loft.window", "Window", "Wall 3", "144", true],
  ["loft.window", "Window", "Wall 2", "90.5", false],
  ["loft.window", "Window", "Wall 4", "90.5", false],
];

/** Tree indices. */
const FLOOR = 0;
const FRONT = 1;
const BACK = 3;
const RIGHT = 4;
const DOOR = 5;
const FRONT_LEFT = 6;
const FRONT_RIGHT = 7;
const ROOF = 11;

/** The base house's cut list, in tree order. */
const HOUSE: CutRow[] = [
  ["Joist", "19", "189", "16 ft"],
  ["Rim", "2", "288", "2 × 12 ft"],
  ["Sill", "2", "288", "2 × 12 ft"],
  ["Sill", "2", "181", "16 ft"],
  ["Subfloor", "14", "55,296 in²", "12 × 4x8"],
  ["Stud", "60", "92.625", "8 ft"],
  ["Jack", "12", "81", "8 ft"],
  ["Header", "6", "39.5", "8 ft"],
  ["Header", "2", "41", "8 ft"],
  ["Cripple", "14", "6.125", "8 ft"],
  ["Sill", "3", "36.5", "8 ft"],
  ["Cripple", "7", "31", "8 ft"],
  ["Top plate", "4", "288", "2 × 12 ft"],
  ["Bottom plate", "2", "125", "12 ft"],
  // 80 869 in² of walls less openings + four 5.9375 x 97.125 corner rips.
  ["Sheathing", "24", "83,175.7188 in²", "17 × 4x9"],
  ["Header", "4", "27.5", "8 ft"],
  ["Sill", "2", "24.5", "8 ft"],
  ["Cripple", "4", "43", "8 ft"],
  ["Top plate", "4", "181", "16 ft"],
  ["Bottom plate", "2", "181", "16 ft"],
  ["Bottom plate", "1", "288", "2 × 12 ft"],
  ["Rafter", "26", "123.5341", "12 ft"],
  ["Ridge", "1", "288", "2 × 12 ft"],
];

/** Priced, each long line is cut from the cheapest splice the book prices. */
const SPLICED: Record<string, string> = {
  "Rim 288": "16 ft + 8 ft",
  "Sill 288": "2 × 12 ft",
  "Top plate 288": "16 ft + 8 ft",
  "Bottom plate 288": "2 × 12 ft",
  "Ridge 288": "16 ft + 8 ft",
};
const HOUSE_PRICED: CutRow[] = HOUSE.map(([member, qty, length, stock]) => [
  member,
  qty,
  length,
  SPLICED[`${member} ${length}`] ?? stock,
]);

/** 8/12: (95.25 + 12) x sqrt(1 + (8/12)²) + 7.25 x 8/12, still 12 ft. */
const PITCH_8_12: CutRow[] = HOUSE_PRICED.map((row) =>
  row[0] === "Rafter" ? ["Rafter", "26", "133.7318", "12 ft"] : row,
);

/** 28 ft long, every opening kept at its X. */
const HOUSE_28: CutRow[] = [
  ["Joist", "22", "189", "16 ft"],
  ["Rim", "2", "336", "2 × 14 ft"],
  ["Sill", "2", "336", "16 ft + 12 ft"],
  ["Sill", "2", "181", "16 ft"],
  ["Subfloor", "16", "64,512 in²", "14 × 4x8"],
  ["Stud", "66", "92.625", "8 ft"],
  ["Jack", "12", "81", "8 ft"],
  ["Header", "6", "39.5", "8 ft"],
  ["Header", "2", "41", "8 ft"],
  ["Cripple", "14", "6.125", "8 ft"],
  ["Sill", "3", "36.5", "8 ft"],
  ["Cripple", "7", "31", "8 ft"],
  ["Top plate", "4", "336", "2 × 14 ft"],
  ["Bottom plate", "1", "173", "16 ft"],
  ["Bottom plate", "1", "125", "12 ft"],
  ["Sheathing", "26", "92,499.7188 in²", "18 × 4x9"],
  ["Header", "4", "27.5", "8 ft"],
  ["Sill", "2", "24.5", "8 ft"],
  ["Cripple", "4", "43", "8 ft"],
  ["Top plate", "4", "181", "16 ft"],
  ["Bottom plate", "2", "181", "16 ft"],
  ["Bottom plate", "1", "336", "16 ft + 12 ft"],
  ["Rafter", "30", "123.5341", "12 ft"],
  ["Ridge", "1", "336", "2 × 14 ft"],
];

/** The line whose blank is clicked (member, stock cell) and its price. */
const PRICES: [string, string, string][] = [
  ["Joist", "16 ft", "22.97"], // SPF 2x10 16 ft
  ["Sill", "16 ft", "16.98"], // PT 2x6 16 ft
  ["Subfloor", "12 × 4x8", "42.50"], // 23/32 plywood 4x8
  ["Stud", "8 ft", "6.48"], // SPF 2x6 8 ft
  ["Bottom plate", "12 ft", "12.48"], // PT 2x6 12 ft
  ["Sheathing", "17 × 4x9", "24.98"], // 7/16 OSB 4x9
  ["Top plate", "16 ft", "13.98"], // SPF 2x6 16 ft
  ["Rafter", "12 ft", "13.47"], // SPF 2x8 12 ft
];

/**
 * The 18 short lines, 19 x 22.97 + 4 x 16.98 + 12 x 42.50 + 114 x 6.48 +
 * 2 x 12.48 + 17 x 24.98 + 4 x 13.98 + 26 x 13.47 = 2 608.83, plus the
 * splices: rims 2 x 34.44, sills 2 x 24.96, top plates 4 x 20.46, bottom
 * plate 24.96, ridge 34.44 = 260.04.
 */
const PRICE = "$2,868.87";
/**
 * 28 ft: the short lines (22 joists, 14 plywood and 18 OSB sheets, 120
 * 2x6 x 8, 30 rafters, ...) come to 2 884.98, and the PT sills and bottom
 * plate splice 16 + 12 (3 x 29.46 = 88.38). The 28 ft SPF rims, top plates and ridge stay
 * unpriced: the splice is chosen among the least-waste ties (2 x 14, 16 + 12,
 * 20 + 8), and the book has no 14, 12 or 20 ft SPF 2x10 or 2x6, though 16 +
 * 16 would do (CUT-LIST-SPLICE-TIES).
 */
const PRICE_28 = "$2,973.36";
const UNPRICED_28 = "3 lines unpriced";

const VOLUME = "264,895.4795";
const VOLUME_8_12 = "267,494.1504";

const IN = 25.4;

async function submit(page: Page): Promise<void> {
  await page.getByTestId("plugin-submit").click();
  await expect(page.getByTestId("plugin-editor")).toBeHidden({
    timeout: 30_000,
  });
}

async function edit(
  page: Page,
  index: number,
  fields: Record<string, string>,
): Promise<void> {
  await page.getByTestId(`feature-select-${index}`).click();
  await expect(page.getByTestId("plugin-editor")).toContainText("Edit");
  for (const [name, value] of Object.entries(fields)) {
    const input = page.getByTestId(`plugin-input-${name}`);
    if (name === "pitch") await input.selectOption({ label: value });
    else await input.fill(value);
  }
  await submit(page);
}

async function expectPrice(
  page: Page,
  total: string,
  unpriced: string | null = null,
): Promise<void> {
  const panel = page.getByTestId("cut-list-panel");
  await expect(panel.getByTestId("cut-list-price-total")).toHaveText(total, {
    timeout: 60_000,
  });
  if (unpriced === null) {
    await expect(panel.getByTestId("cut-list-unpriced")).toHaveCount(0);
    await expect(panel.getByTestId("cut-list-price-blank")).toHaveCount(0);
  } else {
    await expect(panel.getByTestId("cut-list-unpriced")).toHaveText(unpriced);
  }
}

function line(panel: Locator, member: string, stock: string): Locator {
  return panel
    .locator(`[data-testid="cut-list-row"][data-member="${member}"]`)
    .filter({
      has: panel.page().getByTestId("cut-list-stock").getByText(stock, {
        exact: true,
      }),
    });
}

async function storedOffset(
  page: Page,
  token: string,
  partId: string,
  index: number,
): Promise<number> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const tree = (await response.json()) as {
    features: { feature: { params: { inputs: Record<string, number> } } }[];
  };
  return (tree.features[index]?.feature.params.inputs.offset_mm ?? 0) / IN;
}

async function shoot(page: Page, name: string, view: "iso" | "front") {
  await page.keyboard.press("Escape");
  await page.getByTestId(`view-${view}`).click();
  await page.waitForTimeout(1_000);
  await page.getByTestId("view-fit").click();
  await page.mouse.move(800, 990);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/${name}.png` });
}

test.describe("B7 house — built, priced and edited from Build features", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("floor, walls, a door, four windows and a gable; price it; three edits", async ({
    page,
  }) => {
    test.setTimeout(1_200_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B7 house", length_unit: "in" },
      headers: { Authorization: `Bearer ${account.token}` },
    });
    expect(created.ok(), await created.text()).toBe(true);
    const partId = ((await created.json()) as { id: string }).id;

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(0);

    // Build ▾ > Floor: 288 x 192, 2x10 joists; the subfloor is the default.
    await openBuildTool(page, "loft.floor", "Floor");
    await page.getByTestId("plugin-input-width_mm").fill("288");
    await page.getByTestId("plugin-input-depth_mm").fill("192");
    await page
      .getByTestId("plugin-input-joist_profile")
      .selectOption("us_2x10");
    await expect(page.getByTestId("plugin-input-subfloor")).toHaveValue(
      "plywood_23_32",
    );
    await submit(page);

    // Build > Wall, four times: 2x6, OSB, on the subfloor's top.
    for (const [index, [x, y, direction, length]] of WALLS.entries()) {
      const tool = page.getByTestId("plugin-tool-loft.wall");
      await expect(tool).toBeEnabled({ timeout: 30_000 });
      await tool.click();
      await expect(page.getByTestId("plugin-editor")).toContainText("New Wall");
      await page.getByTestId("plugin-input-start_x_mm").fill(x);
      await page.getByTestId("plugin-input-start_y_mm").fill(y);
      await page.getByTestId("plugin-input-direction_deg").fill(direction);
      await page.getByTestId("plugin-input-length_mm").fill(length);
      await page.getByTestId("plugin-input-elevation_mm").fill("11.46875");
      await page.getByTestId("plugin-input-stud_profile-us_2x6").click();
      await page.getByTestId("plugin-input-sheathing").selectOption("osb_7_16");
      await submit(page);
      await expect(rows).toHaveCount(index + 2);
    }

    // Build ▾ > Door and Window, hosted.
    for (const [plugin, title, host, offset, large] of OPENINGS) {
      await openBuildTool(page, plugin, title);
      await page
        .getByTestId("plugin-input-host_wall")
        .selectOption({ label: host });
      await page.getByTestId("plugin-input-offset_mm").fill(offset);
      if (large) {
        await page.getByTestId("plugin-input-width_mm").fill("36");
        await page.getByTestId("plugin-input-height_mm").fill("48");
      }
      await submit(page);
    }
    await expect(rows).toHaveCount(11);

    // Build ▾ > Roof: the 6/12 gable on the typed bearing.
    await openBuildTool(page, "loft.roof", "Roof");
    await page.getByTestId("plugin-input-span_mm").fill("192");
    await page.getByTestId("plugin-input-length_mm").fill("288");
    await page.getByTestId("plugin-input-plate_height_mm").fill("108.59375");
    await page.getByTestId("plugin-input-plate_width_mm").fill("5.5");
    await page
      .getByTestId("plugin-input-rafter_profile")
      .selectOption("us_2x8");
    await page
      .getByTestId("plugin-input-ridge_profile")
      .selectOption("us_2x10");
    await expect(
      page.getByTestId("plugin-input-pitch").locator("option:checked"),
    ).toHaveText("6/12");
    await submit(page);
    await expect(rows).toHaveCount(12);
    await expectSolved(page);

    await openCutList(page);
    await expectTable(page, HOUSE, "217");
    await expect(page.getByTestId("prop-volume")).toContainText(VOLUME, {
      timeout: 60_000,
    });
    await shoot(page, "b7-house", "iso");

    // Price every blank: each opens the book on its line's key.
    await openCutList(page);
    const panel = page.getByTestId("cut-list-panel");
    await expect(panel.getByTestId("cut-list-unpriced")).toHaveText(
      "23 lines unpriced",
    );
    const dialog = page.getByRole("dialog", { name: "Price book" });
    for (const [member, stock, price] of PRICES) {
      const row = line(panel, member, stock);
      await expect(row).toHaveCount(1);
      await row.getByTestId("cut-list-price-blank").click();
      await expect(dialog).toBeVisible();
      const field = dialog
        .getByTestId("price-book-row")
        .last()
        .getByTestId("price-book-price");
      await expect(field).toBeFocused();
      await field.fill(price);
      await field.press("Enter");
      await expect(dialog).toBeHidden({ timeout: 15_000 });
    }
    // The PT sills and plates splice from priced 12s, the SPF top plates
    // from 16 + 8; the 2x10 rims and ridge still lack a piece.
    await expectPrice(page, "$2,765.55", "2 lines unpriced");
    // The rim's blank seeds its missing piece; a framer buys 16s and 8s.
    const rim = panel.locator(
      '[data-testid="cut-list-row"][data-member="Rim"]',
    );
    await rim.getByTestId("cut-list-price-blank").click();
    await expect(dialog).toBeVisible();
    const seeded = dialog.getByTestId("price-book-row").last();
    await expect(seeded).toHaveAttribute("data-profile", "us_2x10");
    await expect(seeded).toHaveAttribute("data-material", "spf_lumber");
    await seeded.getByTestId("price-book-stock").selectOption("8");
    await seeded.getByTestId("price-book-price").fill("11.47");
    await dialog.getByTestId("price-book-save").click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });
    await expectPrice(page, PRICE);
    await expectTable(page, HOUSE_PRICED, "217");
    await expect(rim.getByTestId("cut-list-unit-price")).toHaveText("$34.44");
    await expect(rim.getByTestId("cut-list-ext-price")).toHaveText("$68.88");
    await panel
      .locator("thead")
      .evaluate((head) => head.scrollIntoView({ block: "start" }));
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/b7-cut-list-priced.png` });

    // The CSV's Total row is the same sum.
    const downloading = page.waitForEvent("download");
    await panel.getByTestId("cut-list-csv").click();
    const csv = (
      await readFile(await (await downloading).path(), "utf-8")
    ).split("\r\n");
    expect(csv).toContain(",Total,,,,,,,,,,,,,2868.87");

    // Edit 1: the front left window (X 60) moved 24 in, to X 84. The wall
    // re-frames it with the same counts; Ctrl+Z returns to the base house.
    await edit(page, FRONT_LEFT, { offset_mm: "204" });
    await expectSolved(page);
    expect(
      await storedOffset(page, account.token, partId, FRONT_LEFT),
    ).toBeCloseTo(204, 9);
    await openCutList(page);
    await expectTable(page, HOUSE_PRICED, "217");
    await expectPrice(page, PRICE);
    await shoot(page, "b7-edit-window", "front");
    await page.keyboard.press("Control+z");
    await expect
      .poll(() => storedOffset(page, account.token, partId, FRONT_LEFT), {
        timeout: 30_000,
      })
      .toBeCloseTo(228, 9);
    await expectSolved(page);

    // Edit 2: pitch 6/12 -> 8/12. The rafters lengthen and stay on 12 ft.
    await edit(page, ROOF, { pitch: "8/12" });
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, PITCH_8_12, "217");
    await expectPrice(page, PRICE);
    await expect(page.getByTestId("prop-volume")).toContainText(VOLUME_8_12, {
      timeout: 60_000,
    });
    await shoot(page, "b7-edit-pitch", "iso");
    await edit(page, ROOF, { pitch: "6/12" });

    // Edit 3: length 24 -> 28 ft. The floor, the front, back and right walls
    // and the roof, then the front wall's openings back to their X (their
    // offsets run from its start, which moved 48): the front left window
    // first, or the door's new place overlaps it and is refused.
    await edit(page, FLOOR, { width_mm: "336" });
    await edit(page, FRONT, { start_x_mm: "336", length_mm: "336" });
    await edit(page, BACK, { length_mm: "336" });
    await edit(page, RIGHT, { start_x_mm: "336" });
    await edit(page, ROOF, { length_mm: "336" });
    await edit(page, FRONT_LEFT, { offset_mm: "276" });
    await edit(page, DOOR, { offset_mm: "192" });
    await edit(page, FRONT_RIGHT, { offset_mm: "108" });
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, HOUSE_28, "234");
    await expectPrice(page, PRICE_28, UNPRICED_28);
    await shoot(page, "b7-edit-length", "iso");

    // A reload keeps it.
    await page.reload();
    await expect(rows).toHaveCount(12);
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, HOUSE_28, "234");
    await expectPrice(page, PRICE_28, UNPRICED_28);
  });
});
