import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

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

  test("a tall part is offered portrait, at a strictly better scale", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createTallPartViaApi(page, account.token, "Tall column");
    await seedLaidOutDrawing(page, part.id, "Portrait column");

    // The first sheet is landscape, and the orientation cell says what that
    // costs: the fitted scale for each paper, read off the SAME `fitScale` the
    // layout action uses.
    const orientation = page.getByTestId("sheet-orientation");
    await expect(orientation).toHaveAttribute("data-orientation", "landscape");
    await expect(orientation).toHaveAttribute("data-fit-portrait", /\d+:\d+/, {
      timeout: 30_000,
    });
    const landscapeFit = await orientation.getAttribute("data-fit-landscape");
    const portraitFit = await orientation.getAttribute("data-fit-portrait");
    expect(landscapeFit).toBe("1:5");
    expect(portraitFit).toBe("1:2");
    // The claim that matters, stated as a comparison rather than a golden:
    // portrait draws this part BIGGER.
    expect(scaleRatio(portraitFit as string)).toBeGreaterThan(
      scaleRatio(landscapeFit as string),
    );
    // ...and the current landscape sheet is honestly NOT the proposed one.
    await expect(orientation).toHaveAttribute("data-proposed", "false");

    // The add affordance proposes portrait, naming the scale it earns.
    const add = page.getByTestId("sheet-tab-add");
    await expect(add).toHaveAttribute("data-proposed-orientation", "portrait");
    await expect(add).toHaveAccessibleName(/portrait at 1:2/i);

    await page.setViewportSize({ width: 1280, height: 800 });

    // Accept it: the new sheet is created portrait.
    await add.click();
    await expect(page.getByTestId("sheet-tab-1")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByTestId("sheet-orientation")).toHaveAttribute(
      "data-orientation",
      "portrait",
    );
    await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();

    // Lay the part out on it — the composed paper is A4 PORTRAIT (210 x 297 mm,
    // the viewBox the sheet renders at) and the views are drawn at the better
    // scale the cell promised, not the landscape one.
    await page.getByTestId("drawing-part-select").selectOption(part.id);
    await page.getByTestId("drawing-autolayout").click();
    const sheet = page.getByTestId("drawing-sheet");
    await expect(sheet).toBeVisible({ timeout: 30_000 });
    await expect(sheet).toHaveAttribute("viewBox", "0 0 210 297");
    await expect(sheet).toHaveAccessibleName(/at 1:2/);

    await page.mouse.move(640, 400);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-sheet-portrait-1280.png`,
    });
  });
});
