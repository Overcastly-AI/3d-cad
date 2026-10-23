import { readFile } from "node:fs/promises";

import type { Locator, Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { B7_CUT_LIST } from "./fixtures/b7CutList";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * CUT-LIST-PANEL: B7's priced cut list fits the screen. Priced, the old panel
 * clipped its Ext. price column and the Total at 1600 px and showed 5 of 23
 * lines at 1280, with one member's rows split across walls. Now it is a
 * full-height view grouped Floor, Walls, Roof, Sheathing (Chief Architect's
 * Materials List), one row per system, member, profile and length, and every
 * column and the Total are on screen with no sideways scroll at 1280x800 and
 * 1600x1000.
 *
 * The part is the B1 deck (fixtures/b1-deck.loft, real stack); its cut-list
 * read is answered with B7's priced list as the gateway serves it
 * (fixtures/b7CutList.ts, loft-wire's own grouping and prices), so the layout
 * is checked on the widest real list in seconds. house-b7.spec.ts reads the
 * same list built from the UI.
 */

async function importDeck(page: Page, token: string): Promise<string> {
  const file = await readFile(
    new URL("./fixtures/b1-deck.loft", import.meta.url),
  );
  const response = await page.request.post("/api/v1/parts/import", {
    data: file,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/octet-stream",
    },
  });
  expect(response.ok(), await response.text()).toBe(true);
  return ((await response.json()) as { part: { id: string } }).part.id;
}

/** Every horizontal scroller in the cut list's panel, and its overflow. */
async function sidewaysOverflow(view: Locator): Promise<string[]> {
  return view.evaluate((root) => {
    const out: string[] = [];
    for (const node of [root, ...root.querySelectorAll("*")]) {
      if (!(node instanceof HTMLElement)) continue;
      const overflow = getComputedStyle(node).overflowX;
      if (overflow !== "auto" && overflow !== "scroll") continue;
      if (node.scrollWidth > node.clientWidth) {
        out.push(
          `${node.dataset.testid ?? node.tagName}: ${node.scrollWidth} > ${node.clientWidth}`,
        );
      }
    }
    return out;
  });
}

for (const [width, height] of [
  [1280, 800],
  [1600, 1000],
] as const) {
  test(`B7's priced cut list fits ${width}x${height} with no sideways scroll`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height });
    const account = await seedSession(page);
    const partId = await importDeck(page, account.token);
    await page.route(`**/api/v1/parts/${partId}/cut-list`, (route) =>
      route.fulfill({ json: B7_CUT_LIST }),
    );

    await page.goto(`/parts/${partId}`);
    const tool = page.getByTestId("cut-list-tool");
    await expect(tool).toBeEnabled({ timeout: 60_000 });
    await tool.click();
    const panel = page.getByTestId("cut-list-panel");
    const rows = panel.getByTestId("cut-list-row");
    await expect(rows).toHaveCount(23, { timeout: 30_000 });

    // Grouped by system, in a takeoff's order, each key once.
    await expect(panel.getByTestId("cut-list-group-label")).toHaveText([
      /^Floor/,
      /^Walls/,
      /^Roof/,
      /^Sheathing/,
    ]);
    const keys = await rows.evaluateAll((all) =>
      all.map((row) =>
        [
          row.getAttribute("data-system"),
          row.getAttribute("data-member"),
          row.getAttribute("data-profile"),
          row.querySelector('[data-testid="cut-list-length"]')?.textContent,
        ].join("|"),
      ),
    );
    expect(new Set(keys).size).toBe(keys.length);
    // One member's lines sit together: the three Headers are adjacent.
    const headers = keys
      .map((key, index) => (key.startsWith("walls|Header|") ? index : -1))
      .filter((index) => index >= 0);
    expect(headers).toEqual([headers[0], headers[0]! + 1, headers[0]! + 2]);

    // The view: full height of the rail, and nothing scrolls sideways.
    const view = page.locator('[data-viewport-chrome="panel-cut-list"]');
    const box = (await view.boundingBox())!;
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    // It takes the rail's height; the inspector below keeps only its floor
    // (120 px) past the 8 px gap.
    const rail = page.locator('[data-viewport-chrome="rail-right"]');
    const column = (await rail.boundingBox())!;
    expect(box.height).toBeGreaterThanOrEqual(column.height - 128 - 1);
    expect(await sidewaysOverflow(view)).toEqual([]);

    // Every column and the Total inside the view's edges.
    const right = box.x + box.width;
    for (const name of ["Member", "Qty", "Length", "Run", "Stock"]) {
      const head = panel.getByRole("columnheader", { name, exact: true });
      const cell = (await head.boundingBox())!;
      expect(cell.x).toBeGreaterThanOrEqual(box.x);
      expect(cell.x + cell.width).toBeLessThanOrEqual(right);
    }
    for (const id of ["cut-list-price-total", "cut-list-ext-price"]) {
      const cell = (await panel.getByTestId(id).last().boundingBox())!;
      expect(cell.x + cell.width).toBeLessThanOrEqual(right);
    }
    // The Total and the last line read in full once scrolled to.
    const total = panel.getByTestId("cut-list-price-total");
    await total.scrollIntoViewIfNeeded();
    await expect(total).toHaveText("$2,968.79");
    await expect(total).toBeInViewport({ ratio: 1 });
    const last = rows.last();
    await expect(last.getByTestId("cut-list-member")).toHaveText("Sheathing");
    await expect(last.getByTestId("cut-list-ext-price")).toHaveText("$524.58");
    await expect(last.getByTestId("cut-list-ext-price")).toBeInViewport({
      ratio: 1,
    });
    // A member's name is never cut off: no cell clips its text.
    const clipped = await panel
      .getByTestId("cut-list-member")
      .evaluateAll((all) =>
        all
          .filter((m) => m.scrollWidth > m.clientWidth)
          .map((m) => m.textContent),
      );
    expect(clipped).toEqual([]);

    // Founder shots: the view scrolled to its Total, then from the top.
    await page.mouse.move(width / 2, height - 10);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/cut-list-panel-${width}-total.png`,
    });
    await panel.evaluate((aside) => aside.scrollIntoView({ block: "start" }));
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/cut-list-panel-${width}.png`,
    });

    // The view's left edge drags wider; the keyboard moves it too.
    const sash = page.getByTestId("panel-resize-cut-list");
    const start = (await sash.boundingBox())!;
    await page.mouse.move(start.x + 2, start.y + start.height / 2);
    await page.mouse.down();
    await page.mouse.move(start.x - 118, start.y + start.height / 2, {
      steps: 4,
    });
    await page.mouse.up();
    await expect
      .poll(async () => (await view.boundingBox())!.width)
      .toBeCloseTo(box.width + 120, 0);
    expect(await sidewaysOverflow(view)).toEqual([]);
    await sash.focus();
    await page.keyboard.press("Home");
    await expect
      .poll(async () => (await view.boundingBox())!.width)
      .toBeCloseTo(box.width, 0);
    await page.keyboard.press("ArrowLeft");
    await expect(sash).toHaveAttribute(
      "aria-valuenow",
      String(Math.round(box.width) + 32),
    );
    // The sash names its range: the frame less the tree is its ceiling.
    await expect(sash).toHaveAttribute("aria-valuemax", /^\d+$/);
    const max = Number(await sash.getAttribute("aria-valuemax"));
    expect(max).toBeGreaterThan(box.width);
    expect(max).toBeLessThanOrEqual(width - 24 - 320);
  });
}

/** The rows whose whole box shows: inside the window and every clipping
 * ancestor (the panel's or the view's scroller). */
async function visibleRows(rows: Locator): Promise<number> {
  return rows.evaluateAll((all) => {
    let count = 0;
    for (const row of all) {
      const box = row.getBoundingClientRect();
      let top = 0;
      let bottom = window.innerHeight;
      for (let node = row.parentElement; node; node = node.parentElement) {
        if (getComputedStyle(node).overflowY === "visible") continue;
        const clip = node.getBoundingClientRect();
        top = Math.max(top, clip.top);
        bottom = Math.min(bottom, clip.bottom);
      }
      if (
        box.height > 0 &&
        box.top >= top - 0.5 &&
        box.bottom <= bottom + 0.5
      ) {
        count += 1;
      }
    }
    return count;
  });
}

test("B7's cut list expands full width at 1280x800 and closes with Esc", async ({
  page,
}) => {
  const [width, height] = [1280, 800];
  await page.setViewportSize({ width, height });
  const account = await seedSession(page);
  const partId = await importDeck(page, account.token);
  await page.route(`**/api/v1/parts/${partId}/cut-list`, (route) =>
    route.fulfill({ json: B7_CUT_LIST }),
  );
  await page.goto(`/parts/${partId}`);
  const tool = page.getByTestId("cut-list-tool");
  await expect(tool).toBeEnabled({ timeout: 60_000 });
  await tool.click();
  const panel = page.getByTestId("cut-list-panel");
  await expect(panel.getByTestId("cut-list-row")).toHaveCount(23, {
    timeout: 30_000,
  });
  const inPanel = await visibleRows(panel.getByTestId("cut-list-row"));

  // Scrolled, the panel's rows slide under its caption bar, never under the
  // collapse tab: the tab sits on the bar, and the table (its Ext. price
  // head, then rows) passes beneath the bar, not between it and the tab.
  const side = page.locator('[data-viewport-chrome="panel-cut-list"]');
  await side.evaluate((root) => {
    const scroller = [...root.querySelectorAll<HTMLElement>("*")].find(
      (node) => getComputedStyle(node).overflowY === "auto",
    );
    scroller!.scrollTop = 40;
  });
  const covered = await page
    .getByTestId("panel-collapse-cut-list")
    .evaluate((tab) => {
      const box = tab.getBoundingClientRect();
      const under = document
        .elementsFromPoint(box.x + box.width / 2, box.y + box.height / 2)
        .filter((node) => node !== tab && !tab.contains(node));
      // Topmost first: the bar, then (painted under it) the scrolled table.
      return {
        bar: under.findIndex((n) => n.closest("[data-caption-bar]") !== null),
        table: under.findIndex((n) => n.closest("table") !== null),
      };
    });
  expect(covered.bar).toBe(0);
  expect(covered.table).toBeGreaterThan(0);

  // Expand: the same grouped, priced list, full width.
  await panel.getByRole("button", { name: "Expand the cut list" }).click();
  const view = page.getByRole("dialog", { name: "Cut list" });
  await expect(view).toBeVisible();
  const rows = view.getByTestId("cut-list-row");
  await expect(rows).toHaveCount(23);
  await expect(view.getByTestId("cut-list-group-label")).toHaveText([
    /^Floor/,
    /^Walls/,
    /^Roof/,
    /^Sheathing/,
  ]);
  const box = (await view.boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(width);
  expect(box.width).toBeGreaterThanOrEqual(width - 40);
  expect(await sidewaysOverflow(view)).toEqual([]);
  const inView = await visibleRows(rows);
  expect(inView).toBeGreaterThanOrEqual(Math.max(12, 2 * inPanel));
  // Prices, the price-book link and CSV come along.
  await expect(view.getByTestId("cut-list-price-book")).toBeVisible();
  await expect(view.getByTestId("cut-list-csv")).toBeEnabled();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/cut-list-expanded-1280.png`,
  });

  // The Total reads in full once scrolled to; the head stays put.
  const total = view.getByTestId("cut-list-price-total");
  await total.scrollIntoViewIfNeeded();
  await expect(total).toHaveText("$2,968.79");
  await expect(total).toBeInViewport({ ratio: 1 });
  await expect(
    view.getByRole("columnheader", { name: "Ext. price" }),
  ).toBeInViewport({ ratio: 1 });
  await expect(rows.last().getByTestId("cut-list-ext-price")).toHaveText(
    "$524.58",
  );
  expect(await sidewaysOverflow(view)).toEqual([]);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/cut-list-expanded-1280-total.png`,
  });

  // Esc closes it; the panel and the inspector beside it are as they were.
  await page.keyboard.press("Escape");
  await expect(view).toBeHidden();
  await expect(
    panel.getByRole("button", { name: "Expand the cut list" }),
  ).toBeFocused();
  await expect(panel.getByTestId("cut-list-row")).toHaveCount(23);
  // And its Close button does too.
  await panel.getByRole("button", { name: "Expand the cut list" }).click();
  await page.getByRole("button", { name: "Close the full cut list" }).click();
  await expect(view).toBeHidden();
});
