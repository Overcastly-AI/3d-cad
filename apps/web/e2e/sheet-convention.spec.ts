import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, clickForReal, seedSession } from "./support";

/**
 * REACH-3 — a sheet DECLARES its projection convention, and can be first-angle
 * or portrait.
 *
 * `SheetCreate`/`SheetUpdate` have carried `projection` and `orientation` since
 * drawings v1 and the composer has honoured both (`bounds_aware_layout`'s
 * `top_sy`/`right_sx`), but nothing in the UI ever sent anything except
 * `third_angle` + `landscape` — so a European shop could not draft to its own
 * standard, and a tall part could not have the paper that suits it. This spec
 * drives BOTH through the real UI only (no seeded fixture, no direct PATCH):
 * the sheet header's convention cell and orientation cell, and the content-led
 * orientation proposal on sheet-tab-add.
 *
 * The layout assertions are the point. A convention is not a label — flipping it
 * has to MOVE the views, so the spec measures where the top and right views land
 * relative to front in both standards, which is the one thing a stamped-string
 * assertion could not tell you.
 */

/** Extents (mm) of the tall part below — deliberately taller than wide, so
 * portrait earns a strictly better fitted scale than landscape (1:2 vs 1:5 on
 * A4). See `fitScale` in `src/drawing/layout.ts` for the cell model. */
const TALL_PART = { width: 40, depth: 40, height: 150 };

/** A 40 x 40 x 150 mm column via the real gateway — tall enough that A4
 * portrait fits it a full scale step better than A4 landscape. */
async function createTallPartViaApi(
  page: Page,
  token: string,
  name: string,
): Promise<{ id: string }> {
  const auth = { Authorization: `Bearer ${token}` };
  const part = await page.request.post("/api/v1/parts", {
    data: { name },
    headers: auth,
  });
  if (!part.ok()) {
    throw new Error(
      `create part failed: ${part.status()} ${await part.text()}`,
    );
  }
  const partId = ((await part.json()) as { id: string }).id;

  const { width, depth, height } = TALL_PART;
  const sketch = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Sketch1",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          entities: [
            {
              id: "e1",
              kind: "line",
              start: { x: 0, y: 0 },
              end: { x: width, y: 0 },
            },
            {
              id: "e2",
              kind: "line",
              start: { x: width, y: 0 },
              end: { x: width, y: depth },
            },
            {
              id: "e3",
              kind: "line",
              start: { x: width, y: depth },
              end: { x: 0, y: depth },
            },
            {
              id: "e4",
              kind: "line",
              start: { x: 0, y: depth },
              end: { x: 0, y: 0 },
            },
          ],
          constraints: [],
        },
      },
      expected_tree_version: 0,
    },
    headers: auth,
  });
  if (!sketch.ok()) {
    throw new Error(`sketch failed: ${sketch.status()} ${await sketch.text()}`);
  }
  const sketchBody = (await sketch.json()) as {
    feature: { id: string };
    tree_version: number;
  };

  const extrude = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketchBody.feature.id },
          distance_mm: height,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketchBody.tree_version,
    },
    headers: auth,
  });
  if (!extrude.ok()) {
    throw new Error(
      `extrude failed: ${extrude.status()} ${await extrude.text()}`,
    );
  }
  return { id: partId };
}

/** Open a fresh drawing on the empty bench and lay out the standard views. */
async function seedLaidOutDrawing(
  page: Page,
  partId: string,
  name: string,
): Promise<void> {
  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill(name);
  await page.getByTestId("create-drawing-submit").click();
  const row = page.getByTestId("drawing-row").first();
  await expect(row).toBeVisible();
  await row.getByTestId("drawing-open").click();

  await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
  await page.getByTestId("drawing-part-select").selectOption(partId);
  await page.getByTestId("drawing-autolayout").click();
  await expect(page.getByTestId("drawing-sheet")).toBeVisible({
    timeout: 30_000,
  });
}

/** The on-sheet CENTRE of a placed view, in page pixels. The composer places
 * every auto-placed view, so this is the placement the server actually chose —
 * not something the browser derived. */
async function viewCentre(
  page: Page,
  projection: string,
): Promise<{ x: number; y: number }> {
  const group = page.locator(
    `[data-testid="drawing-view"][data-view="${projection}"]`,
  );
  await expect(group).toBeVisible({ timeout: 30_000 });
  const box = await group.boundingBox();
  if (!box) throw new Error(`no bounding box for the ${projection} view`);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/**
 * Every placed view lies inside the sheet's own paper, measured in SHEET
 * millimetres off the `<svg>` viewBox rather than in page pixels — so the claim
 * is "on the paper", not "somewhere in the frame". A flip that changed only the
 * viewBox would leave a view hanging off the narrower edge.
 */
async function expectViewsOnPaper(
  page: Page,
  paper: { width: number; height: number },
): Promise<void> {
  const svg = page.getByTestId("drawing-sheet");
  await expect(svg).toHaveAttribute(
    "viewBox",
    `0 0 ${paper.width} ${paper.height}`,
  );
  const boxes = await page.evaluate(() => {
    const root = document.querySelector('[data-testid="drawing-sheet"]');
    if (root === null) return [];
    return [...root.querySelectorAll('[data-testid="drawing-view"]')].map(
      (node) => {
        const b = (node as SVGGraphicsElement).getBBox();
        return {
          view: node.getAttribute("data-view") ?? "?",
          x: b.x,
          y: b.y,
          right: b.x + b.width,
          bottom: b.y + b.height,
        };
      },
    );
  });
  expect(boxes.length, "no placed views to measure").toBeGreaterThan(0);
  for (const box of boxes) {
    expect(box.x, `${box.view} runs off the left edge`).toBeGreaterThanOrEqual(
      0,
    );
    expect(box.y, `${box.view} runs off the top edge`).toBeGreaterThanOrEqual(
      0,
    );
    expect(
      box.right,
      `${box.view} runs off the right edge`,
    ).toBeLessThanOrEqual(paper.width);
    expect(
      box.bottom,
      `${box.view} runs off the bottom edge`,
    ).toBeLessThanOrEqual(paper.height);
  }
}

/** The front view's centre X in SHEET millimetres (the coordinate the pin is
 * actually stored in), read off the composed SVG's own user space. */
async function frontCentreMm(page: Page): Promise<number> {
  const x = await page.evaluate(() => {
    const node = document.querySelector(
      '[data-testid="drawing-view"][data-view="front"]',
    );
    if (node === null) return null;
    const b = (node as SVGGraphicsElement).getBBox();
    return b.x + b.width / 2;
  });
  if (x === null) throw new Error("no front view to measure");
  return x;
}

/** `"1:5"` -> 0.2 — bigger is a bigger drawing. */
function scaleRatio(label: string): number {
  const [numerator, denominator] = label.split(":").map(Number);
  if (!numerator || !denominator) throw new Error(`bad scale label: ${label}`);
  return numerator / denominator;
}

test.describe("drawings — the sheet declares its projection convention", () => {
  test("third angle by default; the header cell flips it, and the flip persists", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createTallPartViaApi(page, account.token, "Column");
    await seedLaidOutDrawing(page, part.id, "Convention column");

    // --- Third angle: top ABOVE front, right view to its RIGHT (ISO 128). ---
    // Page pixels grow DOWNWARD, so "above" is a smaller y.
    let front = await viewCentre(page, "front");
    let top = await viewCentre(page, "top");
    let right = await viewCentre(page, "right");
    expect(top.y).toBeLessThan(front.y);
    expect(right.x).toBeGreaterThan(front.x);

    // The sheet STAMPS the convention where it is read, and says which one.
    const cell = page.getByTestId("sheet-projection");
    await expect(cell).toBeVisible();
    await expect(cell).toHaveAttribute("data-projection", "third_angle");
    await expect(cell).toHaveAccessibleName(/third angle/i);
    // The ISO symbol itself, not just the caption: the third-angle glyph is the
    // unmirrored one (its end view sits to the RIGHT of the elevation, exactly
    // where this sheet's right view landed).
    const glyph = page.locator('[data-testid="sheet-projection"] svg g');
    await expect(glyph).not.toHaveAttribute("transform", /scale/);

    // Founder frame — third-angle sheet with the convention cell in place.
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.mouse.move(640, 400);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-sheet-convention-third-1280.png`,
    });

    // --- Activate the cell BY KEYBOARD: the sheet re-lays out in first angle. ---
    await cell.focus();
    await expect(cell).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(cell).toHaveAttribute("data-projection", "first_angle", {
      timeout: 30_000,
    });
    await expect(cell).toHaveAccessibleName(/first angle/i);
    await expect(glyph).toHaveAttribute("transform", /scale\(-1 1\)/);

    // The views MOVED — first angle mirrors both axes about front.
    front = await viewCentre(page, "front");
    top = await viewCentre(page, "top");
    right = await viewCentre(page, "right");
    expect(top.y).toBeGreaterThan(front.y);
    expect(right.x).toBeLessThan(front.x);

    await page.mouse.move(640, 400);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-sheet-convention-first-1280.png`,
    });

    // --- It is the SHEET that changed, not the screen: reload and re-read. ---
    await page.reload();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("sheet-projection")).toHaveAttribute(
      "data-projection",
      "first_angle",
    );
    const reloaded = {
      front: await viewCentre(page, "front"),
      top: await viewCentre(page, "top"),
      right: await viewCentre(page, "right"),
    };
    expect(reloaded.top.y).toBeGreaterThan(reloaded.front.y);
    expect(reloaded.right.x).toBeLessThan(reloaded.front.x);
  });

  test("SHEET ONE is offered portrait, at a strictly better scale", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createTallPartViaApi(page, account.token, "Tall column");

    // REACH-3-FLOW P1-1. The proposal used to fire only on the SECOND sheet,
    // because all four Sheet-1 create paths wrote `orientation: "landscape"` as
    // a literal and the extents query that feeds the proposal was keyed on the
    // DRAFTED source — null until a sheet already had views. So on the only
    // sheet most drawings have, the feature could not have fired.
    await page.goto("/drawings");
    await expect(page.getByTestId("nav-drawings")).toBeVisible();
    await page.getByTestId("create-drawing-name").fill("Portrait column");
    await page.getByTestId("create-drawing-submit").click();
    const row = page.getByTestId("drawing-row").first();
    await expect(row).toBeVisible();
    await row.getByTestId("drawing-open").click();

    // --- The SET-UP screen states the proposal BEFORE the click that spends it.
    await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
    await page.getByTestId("drawing-part-select").selectOption(part.id);
    const setupPaper = page.getByTestId("setup-paper");
    await expect(setupPaper).toHaveAttribute("data-orientation", "portrait", {
      timeout: 30_000,
    });
    await expect(setupPaper).toHaveAttribute("data-proposed", "true");
    await expect(setupPaper).toHaveAccessibleName(/portrait, fits 1:2/i);
    // Painted, not merely "visible": a cell clipped to 1x1 passes toBeVisible.
    const paperBox = await setupPaper.boundingBox();
    expect(paperBox, "the set-up paper cell has no box").not.toBeNull();
    expect(paperBox!.width).toBeGreaterThan(80);
    expect(paperBox!.height).toBeGreaterThan(12);
    // And the size picker names the paper that proposal will actually make.
    await expect(page.getByTestId("drawing-size-select")).toContainText(
      "A4 · 210 × 297 mm",
    );

    await page.setViewportSize({ width: 1280, height: 800 });
    await page.mouse.move(640, 700);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-setup-paper-proposal-1280.png`,
    });

    // --- Lay out: SHEET ONE is the portrait sheet, at the promised scale.
    await page.getByTestId("drawing-autolayout").click();
    const sheet = page.getByTestId("drawing-sheet");
    await expect(sheet).toBeVisible({ timeout: 30_000 });
    await expect(sheet).toHaveAttribute("viewBox", "0 0 210 297");
    await expect(sheet).toHaveAccessibleName(/at 1:2/);
    await expect(page.getByTestId("sheet-tabs").getByRole("tab")).toHaveCount(
      1,
    );
    await expect(page.getByTestId("drawing-scale-readout")).toHaveText("1:2");

    // The header cell agrees, and says what the other paper would cost.
    const orientation = page.getByTestId("sheet-orientation");
    await expect(orientation).toHaveAttribute("data-orientation", "portrait");
    await expect(orientation).toHaveAttribute("data-proposed", "true");
    const landscapeFit = await orientation.getAttribute("data-fit-landscape");
    const portraitFit = await orientation.getAttribute("data-fit-portrait");
    expect(landscapeFit).toBe("1:5");
    expect(portraitFit).toBe("1:2");
    // The claim that matters, stated as a comparison rather than a golden:
    // portrait draws this part BIGGER.
    expect(scaleRatio(portraitFit as string)).toBeGreaterThan(
      scaleRatio(landscapeFit as string),
    );

    await page.mouse.move(640, 400);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-sheet-portrait-1280.png`,
    });
  });

  test("the paper cell promises exactly what the flip delivers", async ({
    page,
  }) => {
    // REACH-3-FLOW P1-2. The cell used to read "switch to landscape (1:5)" and
    // then hand back a sheet still drawn at 1:2 — a control quoting a scale it
    // cannot produce. MEASURED against the real stack: documents refuses a
    // per-view re-scale on a laid-out multi-view sheet
    // (`sheet_view_scale_mismatch`, its H2 one-sheet-one-scale invariant) and
    // the refusal cannot be sequenced around, so the promise is what had to
    // change. The trade now lives on the SET-UP screen, where the scale is
    // still free; here the cell states the flip, and the flip does it.
    const account = await seedSession(page);
    const part = await createTallPartViaApi(page, account.token, "Flip column");
    await seedLaidOutDrawing(page, part.id, "Flip column drawing");
    await page.setViewportSize({ width: 1280, height: 800 });

    const sheet = page.getByTestId("drawing-sheet");
    const scale = page.getByTestId("drawing-scale-readout");
    const cell = page.getByTestId("sheet-orientation");
    await expect(sheet).toHaveAttribute("viewBox", "0 0 210 297");
    await expect(scale).toHaveText("1:2");

    // THE CASE, stated as the cell states it: it names the paper it will make
    // and the scale it will keep. Nothing here is a claim about a re-fit.
    await expect(cell).toHaveAccessibleName(
      /switch to landscape paper, keeping 1:2/i,
    );
    // ...and it still tells you what landscape WOULD buy, naming the sheet that
    // could deliver it — the exit, not a promise this control can keep.
    await expect(cell).toHaveAccessibleName(
      /fresh landscape sheet would fit this at 1:5/i,
    );

    // Activate it the way a user does — a real mouse click at the control's
    // centre, after proving that point actually resolves TO the control
    // (`force: true` would skip exactly the check that matters here).
    await clickForReal(page, "sheet-orientation");

    await expect(cell).toHaveAttribute("data-orientation", "landscape", {
      timeout: 30_000,
    });
    // Delivered: the paper changed, and the scale the cell said it would keep
    // is the scale the title block states.
    await expect(sheet).toHaveAttribute("viewBox", "0 0 297 210");
    await expect(scale).toHaveText("1:2");
    await expect(sheet).toHaveAccessibleName(/at 1:2/);
    // Every view is still ON the new paper — a flip that only changed the
    // viewBox would leave a hand-placed view off the narrower edge.
    await expectViewsOnPaper(page, { width: 297, height: 210 });

    await page.mouse.move(640, 400);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-sheet-flipped-landscape-1280.png`,
    });

    // ...and back again. No dead end either way.
    await clickForReal(page, "sheet-orientation");
    await expect(cell).toHaveAttribute("data-orientation", "portrait", {
      timeout: 30_000,
    });
    await expect(sheet).toHaveAttribute("viewBox", "0 0 210 297");
    await expectViewsOnPaper(page, { width: 210, height: 297 });

    // It is the SHEET that changed, not the screen.
    await page.reload();
    await expect(page.getByTestId("drawing-sheet")).toHaveAttribute(
      "viewBox",
      "0 0 210 297",
      { timeout: 30_000 },
    );
    await expect(page.getByTestId("drawing-scale-readout")).toHaveText("1:2");
  });

  test("a HAND-PLACED view survives the flip onto narrower paper", async ({
    page,
  }) => {
    // The half of the flip that was never cosmetic. `auto_place:false` is
    // honoured by the composer VERBATIM, so a view dragged to x = 270 mm on a
    // 297 mm-wide landscape sheet is off the edge of a 210 mm-wide portrait
    // one. An auto-placed view hides this — the composer re-derives it either
    // way — so this case drags first, deliberately: an assertion that only ever
    // sees auto-placed views cannot observe the failure it is standing in for.
    await page.setViewportSize({ width: 1440, height: 900 });
    const account = await seedSession(page);
    const part = await createTallPartViaApi(page, account.token, "Pin column");
    await seedLaidOutDrawing(page, part.id, "Pinned view flip");

    // Start landscape so the flip NARROWS the paper (297 -> 210 mm).
    await clickForReal(page, "sheet-orientation");
    await expect(page.getByTestId("sheet-orientation")).toHaveAttribute(
      "data-orientation",
      "landscape",
      { timeout: 30_000 },
    );

    // Drag the front view as far right as the sheet allows.
    const front = page.locator(
      '[data-testid="drawing-view"][data-view="front"]',
    );
    await expect(front).toBeVisible({ timeout: 30_000 });
    await front.hover();
    const grip = front.getByTestId("drawing-view-grip");
    const gripBox = await grip.boundingBox();
    if (!gripBox) throw new Error("grip has no box");
    const gx = gripBox.x + gripBox.width / 2;
    const gy = gripBox.y + gripBox.height / 2;
    await page.mouse.move(gx, gy);
    await page.mouse.down();
    await page.mouse.move(gx + 150, gy, { steps: 6 });
    await page.mouse.move(gx + 300, gy, { steps: 6 });
    await page.mouse.up();
    await expect(front).toHaveAttribute("data-placed", "true", {
      timeout: 30_000,
    });
    const pinnedX = await frontCentreMm(page);
    expect(
      pinnedX,
      "the drag must land the pin in the right-hand half of the landscape sheet",
    ).toBeGreaterThan(297 / 2);

    // Flip onto the narrower paper. The pin keeps its composition — right-hand
    // side stays right-hand side — and lands somewhere that exists.
    await clickForReal(page, "sheet-orientation");
    await expect(page.getByTestId("sheet-orientation")).toHaveAttribute(
      "data-orientation",
      "portrait",
      { timeout: 30_000 },
    );
    await expect(front).toHaveAttribute("data-placed", "true");
    const reframedX = await frontCentreMm(page);
    expect(reframedX, "the pin is off the narrower paper").toBeLessThan(210);
    expect(reframedX / 210, "the pin lost its place on the sheet").toBeCloseTo(
      pinnedX / 297,
      1,
    );
    await expectViewsOnPaper(page, { width: 210, height: 297 });
  });

  test("the header cells survive an eleven-sheet drawing at 1024", async ({
    page,
  }) => {
    // REACH-3-FLOW P2: with no cap and no scroll region the tab rail pushed the
    // convention and orientation cells off the right of the viewport — the two
    // controls that DECLARE the sheet's standard were the first thing a
    // many-sheet drawing lost, with nothing to say where they had gone.
    const account = await seedSession(page);
    const part = await createTallPartViaApi(page, account.token, "Many column");
    await seedLaidOutDrawing(page, part.id, "Eleven sheets");
    await page.setViewportSize({ width: 1024, height: 768 });

    const add = page.getByTestId("sheet-tab-add");
    for (let n = 1; n < 11; n += 1) {
      await add.click();
      await expect(page.getByTestId(`sheet-tab-${n}`)).toHaveAttribute(
        "aria-selected",
        "true",
        { timeout: 30_000 },
      );
    }
    await expect(page.getByTestId("sheet-tabs").getByRole("tab")).toHaveCount(
      11,
    );
    // A scrolling rail must still show you where you are: the tab that add just
    // selected is fully inside the rail, not off its end.
    const railFit = await page.evaluate(() => {
      const rail = document.querySelector('[data-testid="sheet-tabs"]');
      const tab = rail?.querySelector('[role="tab"][data-active]');
      if (!rail || !tab) return null;
      const r = rail.getBoundingClientRect();
      const t = tab.getBoundingClientRect();
      return { inside: t.left >= r.left - 0.5 && t.right <= r.right + 0.5 };
    });
    expect(railFit, "no active tab in the rail").not.toBeNull();
    expect(railFit!.inside, "the active tab is scrolled off the rail").toBe(
      true,
    );

    // Every control that is NOT a tab is still ON the paper — the two header
    // cells and the add affordance. `+` is the one that makes a TWELFTH sheet,
    // so scrolling it off the end of an eleven-sheet rail would be its own dead
    // end: the rail scrolls, the actions do not.
    for (const testid of [
      "sheet-projection",
      "sheet-orientation",
      "sheet-tab-add",
    ]) {
      const box = await page.getByTestId(testid).boundingBox();
      expect(box, `${testid} has no box`).not.toBeNull();
      expect(
        box!.x + box!.width,
        `${testid} is off the right edge`,
      ).toBeLessThan(1024);
      expect(box!.x, `${testid} is off the left edge`).toBeGreaterThanOrEqual(
        0,
      );
      // ...and a pointer aimed at it lands on it, without Playwright scrolling
      // the rail on the user's behalf first.
      const resolves = await page.evaluate((id) => {
        const el = document.querySelector(`[data-testid="${id}"]`);
        if (el === null) return "missing";
        const r = el.getBoundingClientRect();
        const hit = document.elementFromPoint(
          r.x + r.width / 2,
          r.y + r.height / 2,
        );
        return hit !== null && el.contains(hit) ? id : "occluded";
      }, testid);
      expect(resolves, `${testid} is not where a pointer would land`).toBe(
        testid,
      );
    }
    await clickForReal(page, "sheet-projection");
    await expect(page.getByTestId("sheet-projection")).toHaveAttribute(
      "data-projection",
      "first_angle",
      { timeout: 30_000 },
    );

    await page.mouse.move(512, 500);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-sheet-header-eleven-1024.png`,
    });
  });
});
