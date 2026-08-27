import { expect, test, type Page } from "./fixtures";

import { createPlateWithHoleViaApi } from "./assemblyFlow";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * REACH-3 — place a drawing dimension AS YOU CREATE IT.
 *
 * `DimensionPlacement.offset_mm` / `text_pos` have been in the gateway contract
 * and fully honoured by the composer since drawings v1, and the app had never
 * sent either: every dimension a user could author landed wherever the auto
 * engine put it, with no way to move it — not afterwards, and not while
 * drawing. This spec is the reachability proof, driven entirely through the
 * sheet: pick an edge, choose the type, drag the ghost out, click (or press
 * Enter), and the dimension lands where you put it and STAYS there.
 *
 * Everything is measured in the sheet's own millimetres — the SVG's viewBox is
 * mm, so a coordinate read off the DOM IS a sheet coordinate, the same space
 * `offset_mm` is expressed in.
 */

/** Lay out the standard views for a fresh plate-with-hole drawing. */
async function layOutPlateDrawing(page: Page, token: string): Promise<string> {
  const part = await createPlateWithHoleViaApi(page, token, "Plate 40x25");
  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill("Plate — placement");
  await page.getByTestId("create-drawing-submit").click();
  const row = page.getByTestId("drawing-row").first();
  await expect(row).toBeVisible();
  await row.getByTestId("drawing-open").click();
  await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
  await page.getByTestId("drawing-part-select").selectOption(part.id);
  await page.getByTestId("drawing-autolayout").click();
  await expect(page.getByTestId("drawing-sheet")).toBeVisible({
    timeout: 30_000,
  });
  const url = page.url();
  const id = url.split("/").pop();
  if (!id) throw new Error(`no drawing id in ${url}`);
  return id;
}

/** The longest horizontal (≈ 40 mm) line pick-target in a view, by bbox width. */
async function longestHorizontalEdge(page: Page, view: string) {
  const edges = page.locator(
    `[data-testid="drawing-pick-edge"][data-view="${view}"][data-primitive="line"]`,
  );
  const count = await edges.count();
  let best = 0;
  let bestWidth = 0;
  for (let i = 0; i < count; i += 1) {
    const box = await edges.nth(i).boundingBox();
    if (!box) continue;
    if (box.width > box.height && box.width > bestWidth) {
      bestWidth = box.width;
      best = i;
    }
  }
  return edges.nth(best);
}

interface Pt {
  x: number;
  y: number;
}

/** Map a point in SHEET millimetres to viewport pixels, via the SVG's own CTM. */
async function sheetToClient(page: Page, at: Pt): Promise<Pt> {
  return page.evaluate(({ x, y }) => {
    const svg = document.querySelector(
      '[data-testid="drawing-sheet"]',
    ) as SVGSVGElement | null;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) throw new Error("sheet has no screen CTM");
    const p = svg.createSVGPoint();
    p.x = x;
    p.y = y;
    const mapped = p.matrixTransform(ctm);
    return { x: mapped.x, y: mapped.y };
  }, at);
}

/** Read an SVG line's four coordinates (sheet mm) off the DOM. */
async function lineMm(
  page: Page,
  selector: string,
): Promise<{ x1: number; y1: number; x2: number; y2: number }> {
  const el = page.locator(selector).first();
  await expect(el).toBeAttached();
  const [x1, y1, x2, y2] = await Promise.all(
    ["x1", "y1", "x2", "y2"].map(async (a) => Number(await el.getAttribute(a))),
  );
  return { x1: x1!, y1: y1!, x2: x2!, y2: y2! };
}

/**
 * The GHOST's placing rule: from the measured midpoint out to the live
 * dimension line. Its vector IS the current offset in sheet mm along the
 * composer's outward normal — which is how this spec aims the pointer at a
 * chosen offset without having to know which side of the paper "away" is on.
 */
const ghostRule =
  '[data-testid="dimension-ghost"] line[data-ghost-role="rule"]';

/** The committed dimension line (not its witness lines). */
const placedLine =
  '[data-testid="drawing-dimension"] line[data-dim-line-role="dimension"]';

/** Perpendicular distance from `p` to the infinite line `line`. */
function distanceToLine(
  p: Pt,
  line: { x1: number; y1: number; x2: number; y2: number },
): number {
  const dx = line.x2 - line.x1;
  const dy = line.y2 - line.y1;
  return (
    Math.abs(dy * (p.x - line.x1) - dx * (p.y - line.y1)) / Math.hypot(dx, dy)
  );
}

/** The drawing's stored dimensions, straight from the gateway. */
async function storedDimensions(
  page: Page,
  token: string,
  drawingId: string,
): Promise<
  {
    dimension: {
      type: string;
      placement?: {
        offset_mm: number;
        text_pos?: { x_mm: number; y_mm: number } | null;
      };
    };
  }[]
> {
  const res = await page.request.get(`/api/v1/drawings/${drawingId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok()) {
    throw new Error(`fetch drawing failed: ${res.status()}`);
  }
  const tree = (await res.json()) as {
    sheets: { dimensions: { dimension: { type: string } }[] }[];
  };
  return tree.sheets.flatMap((s) => s.dimensions) as never;
}

test("drag a linear dimension onto the side of the paper you want", async ({
  page,
}) => {
  const account = await seedSession(page);
  const drawingId = await layOutPlateDrawing(page, account.token);

  // --- Pick the 40 mm edge and choose Length. ------------------------------
  const longEdge = await longestHorizontalEdge(page, "top");
  await longEdge.click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-linear").click();

  // The pick has become a PLACEMENT: same chip, next sentence.
  const hint = page.getByTestId("dimension-pick-hint");
  await expect(hint).toContainText("Click to place the dimension");
  const readout = page.getByTestId("dimension-offset-readout");
  // The ghost opens at the composer's own auto offset — the BASELINE this
  // spec measures the hand placement against. The user adjusts a real
  // proposal rather than starting from nothing.
  await expect(readout).toHaveAttribute("data-offset-mm", "11.00");
  const baselineMm = 11;

  // --- Drag it 33 mm onto the OTHER side of the geometry. ------------------
  // Deliberately the side the auto engine does not prefer: `offset_mm` is
  // SIGNED, and only a placement the composer honours end to end — sign and
  // magnitude — can land a dimension over there.
  const rule = await lineMm(page, ghostRule);
  const edgeMid = { x: rule.x1, y: rule.y1 };
  const outward = { x: rule.x2 - rule.x1, y: rule.y2 - rule.y1 };
  const targetMm = -33;
  const aim = {
    x: edgeMid.x + (outward.x / baselineMm) * targetMm,
    y: edgeMid.y + (outward.y / baselineMm) * targetMm,
  };
  const aimPx = await sheetToClient(page, aim);
  await page.mouse.move(aimPx.x, aimPx.y);
  // The readout TRACKS the pointer — the number is live, not a label.
  await expect(readout).toHaveText("-33.0 mm");

  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-dimension-placing-1280.png`,
  });

  // --- Enter commits it. ---------------------------------------------------
  await page.keyboard.press("Enter");
  await expect(
    page.locator(
      '[data-testid="drawing-dimension"][data-dimension-value="40.000"]',
    ),
  ).toHaveCount(1, { timeout: 30_000 });
  await expect(page.getByTestId("dimension-ghost")).toHaveCount(0);

  // The COMPOSED dimension line sits where the pointer left it — 33 mm off the
  // measured edge, not the 11 mm the auto engine would have chosen. The server
  // measured the value; the user placed the annotation.
  const placed = await lineMm(page, placedLine);
  const placedDistance = distanceToLine(edgeMid, placed);
  expect(placedDistance).toBeGreaterThan(baselineMm + 5);
  expect(placedDistance).toBeCloseTo(Math.abs(targetMm), 1);
  // …and on the side the pointer was on, not mirrored across the geometry.
  expect(Math.sign(placed.y1 - edgeMid.y)).toBe(Math.sign(aim.y - edgeMid.y));

  // --- It STAYS there across a reload. -------------------------------------
  await page.reload();
  await expect(page.getByTestId("drawing-sheet")).toBeVisible({
    timeout: 30_000,
  });
  const reloaded = await lineMm(page, placedLine);
  expect(reloaded.y1).toBeCloseTo(placed.y1, 1);

  // …because it was PERSISTED as the authored placement, not re-derived.
  const stored = await storedDimensions(page, account.token, drawingId);
  expect(stored).toHaveLength(1);
  expect(stored[0]!.dimension.placement?.offset_mm).not.toBe(0);
  expect(stored[0]!.dimension.placement!.offset_mm).toBeCloseTo(targetMm, 1);

  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-dimension-placed-1280.png`,
  });
});

test("place a linear dimension from the keyboard alone", async ({ page }) => {
  const account = await seedSession(page);
  const drawingId = await layOutPlateDrawing(page, account.token);

  const longEdge = await longestHorizontalEdge(page, "top");
  await longEdge.click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-linear").click();

  const readout = page.getByTestId("dimension-offset-readout");
  await expect(readout).toHaveAttribute("data-offset-mm", "11.00");
  const rule = await lineMm(page, ghostRule);
  const edgeMid = { x: rule.x1, y: rule.y1 };

  // Five presses of the 1 mm nudge — no pointer involved at any point.
  for (let i = 0; i < 5; i += 1) await page.keyboard.press("ArrowUp");
  await expect(readout).toHaveText("16.0 mm");
  // And it goes back down again, so the keyboard is a two-way control.
  await page.keyboard.press("ArrowDown");
  await expect(readout).toHaveText("15.0 mm");

  await page.keyboard.press("Enter");
  await expect(
    page.locator(
      '[data-testid="drawing-dimension"][data-dimension-value="40.000"]',
    ),
  ).toHaveCount(1, { timeout: 30_000 });

  const placed = await lineMm(page, placedLine);
  expect(distanceToLine(edgeMid, placed)).toBeCloseTo(15, 1);

  const stored = await storedDimensions(page, account.token, drawingId);
  expect(Math.abs(stored[0]!.dimension.placement!.offset_mm)).toBeCloseTo(
    15,
    1,
  );
});

test("escape backs out of the placement without losing the pick", async ({
  page,
}) => {
  const account = await seedSession(page);
  await layOutPlateDrawing(page, account.token);

  const longEdge = await longestHorizontalEdge(page, "top");
  await longEdge.click({ force: true });
  await page.getByTestId("dimension-type-linear").click();
  await expect(page.getByTestId("dimension-ghost")).toHaveCount(1);

  // One Escape drops the PLACEMENT and returns the type menu — the edge you
  // picked is still picked, so a mis-drag costs a keypress, not the selection.
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("dimension-ghost")).toHaveCount(0);
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await expect(
    page.locator('[data-testid="drawing-pick-edge"][data-selected="true"]'),
  ).toHaveCount(1);

  // A second Escape abandons the pick entirely.
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("dimension-author-menu")).toHaveCount(0);
});

test("drag a diameter's value off the hole and it stays there", async ({
  page,
}) => {
  const account = await seedSession(page);
  const drawingId = await layOutPlateDrawing(page, account.token);

  const topCircle = page
    .locator(
      '[data-testid="drawing-pick-edge"][data-view="top"][data-primitive="circle"]',
    )
    .first();
  await topCircle.click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-diameter").click();

  // A diameter has no offset LINE to slide (the composer applies `offset_mm` to
  // linear dimensions only), so the placement it authors is `text_pos`: the
  // ghost is a leader to a crosshair, and the chip says so.
  await expect(page.getByTestId("dimension-pick-hint")).toContainText(
    "Click to place the value",
  );
  await expect(page.getByTestId("dimension-offset-readout")).toHaveCount(0);
  const leader = await lineMm(
    page,
    '[data-testid="dimension-ghost"] line[data-ghost-role="leader"]',
  );
  const holeCentre = { x: leader.x1, y: leader.y1 };

  // Drag the value up and to the right of the hole and click it down.
  const seat = { x: holeCentre.x + 26, y: holeCentre.y - 20 };
  const seatPx = await sheetToClient(page, seat);
  await page.mouse.move(seatPx.x, seatPx.y);
  await page.mouse.click(seatPx.x, seatPx.y);

  const value = page.locator(
    '[data-testid="drawing-dimension"][data-dimension-type="diameter"] [data-testid="drawing-dimension-value"]',
  );
  await expect(value).toHaveCount(1, { timeout: 30_000 });
  expect(Number(await value.getAttribute("x"))).toBeCloseTo(seat.x, 1);
  expect(Number(await value.getAttribute("y"))).toBeCloseTo(seat.y, 1);

  const stored = await storedDimensions(page, account.token, drawingId);
  expect(stored[0]!.dimension.type).toBe("diameter");
  expect(stored[0]!.dimension.placement?.text_pos?.x_mm).toBeCloseTo(seat.x, 1);
  expect(stored[0]!.dimension.placement?.text_pos?.y_mm).toBeCloseTo(seat.y, 1);
});
