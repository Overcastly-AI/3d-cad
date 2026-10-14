import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * QA-DRAWING-CENTRE-MARKS, end to end through a real browser against the real
 * stack: a hole's POSITION is dimensioned on a drawing by picking its centre
 * mark, the way Fusion's drawing dimension tool does.
 *
 * The part is a W x 60 x 10 plate with two Ø10 holes, A at (W - 20, 30) — it
 * moves with the plate's width — and B at (20, 15). In the top view:
 *
 *  - left edge -> centre A reads 80 at W = 100;
 *  - centre A <-> centre B, placed ABOVE the holes, is a HORIZONTAL dimension:
 *    |80 - 20| = 60; and
 *  - after the one-number edit W 100 -> 80 (A to x = 60), the same two
 *    dimensions follow the hole: 60 and 40.
 */

/** The plate profile: a `width` x 60 rectangle around holes A and B. */
function plate(width: number) {
  const pts: [number, number][] = [
    [0, 0],
    [width, 0],
    [width, 60],
    [0, 60],
  ];
  const hole = (id: string, x: number, y: number) => ({
    id,
    kind: "circle",
    construction: false,
    center: { x, y },
    radius: 5,
  });
  return {
    entities: [
      ...pts.map((p, i) => {
        const next = pts[(i + 1) % pts.length] as [number, number];
        return {
          id: `e${i + 1}`,
          kind: "line",
          construction: false,
          start: { x: p[0], y: p[1] },
          end: { x: next[0], y: next[1] },
        };
      }),
      hole("hA", width - 20, 30),
      hole("hB", 20, 15),
    ],
    constraints: [],
  };
}

async function createPlateViaApi(
  page: Page,
  token: string,
  width: number,
): Promise<{ id: string; sketchId: string; treeVersion: number }> {
  const auth = { Authorization: `Bearer ${token}` };
  const part = await page.request.post("/api/v1/parts", {
    data: { name: "Hole plate" },
    headers: auth,
  });
  expect(part.ok()).toBe(true);
  const partId = ((await part.json()) as { id: string }).id;
  const sketch = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Sketch1",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          ...plate(width),
        },
      },
      expected_tree_version: 0,
    },
    headers: auth,
  });
  expect(sketch.ok()).toBe(true);
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
          distance_mm: 10,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketchBody.tree_version,
    },
    headers: auth,
  });
  expect(extrude.ok()).toBe(true);
  const extrudeBody = (await extrude.json()) as { tree_version: number };
  return {
    id: partId,
    sketchId: sketchBody.feature.id,
    treeVersion: extrudeBody.tree_version,
  };
}

async function resizePlate(
  page: Page,
  token: string,
  part: { id: string; sketchId: string; treeVersion: number },
  width: number,
): Promise<void> {
  const response = await page.request.patch(
    `/api/v1/parts/${part.id}/features/${part.sketchId}`,
    {
      data: {
        feature: {
          type: "sketch",
          version: 1,
          params: {
            plane: { kind: "datum_plane", plane: "XY" },
            ...plate(width),
          },
        },
        expected_tree_version: part.treeVersion,
      },
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  expect(response.ok()).toBe(true);
}

async function layOutDrawing(page: Page, partId: string): Promise<void> {
  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill("Hole plate - positions");
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

/** The top view's centre-mark picks, left to right (B first, then A). */
async function centres(page: Page) {
  const picks = page.locator(
    '[data-testid="drawing-pick-centre"][data-view="top"]',
  );
  await expect(picks).toHaveCount(2, { timeout: 30_000 });
  const boxes = await Promise.all(
    [0, 1].map(async (i) => ({ i, box: await picks.nth(i).boundingBox() })),
  );
  boxes.sort((a, b) => (a.box?.x ?? 0) - (b.box?.x ?? 0));
  return boxes.map(({ i, box }) => ({ pick: picks.nth(i), box: box! }));
}

/** The left-most vertical line pick in the top view (the plate's x = 0 edge). */
async function leftEdge(page: Page) {
  const edges = page.locator(
    '[data-testid="drawing-pick-edge"][data-view="top"][data-primitive="line"]',
  );
  const count = await edges.count();
  let best = 0;
  let bestX = Infinity;
  for (let i = 0; i < count; i += 1) {
    const box = await edges.nth(i).boundingBox();
    if (box && box.height > box.width && box.x < bestX) {
      bestX = box.x;
      best = i;
    }
  }
  return edges.nth(best);
}

const value = (page: Page, text: string) =>
  page.locator(
    `[data-testid="drawing-dimension"][data-dimension-type="linear"][data-dimension-value="${text}"]`,
  );

test("pick hole centre marks and dimension the holes' positions", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  const account = await seedSession(page);
  const part = await createPlateViaApi(page, account.token, 100);
  await layOutDrawing(page, part.id);

  // Every hole seen end-on carries a centre mark, and it is pickable.
  const [markB, markA] = await centres(page);
  expect(markA!.box.x).toBeGreaterThan(markB!.box.x);

  // 1) Left edge -> centre A: pick the edge, reach for "Distance to centre"
  //    (it ARMS a centre pick), then pick the mark.
  await (await leftEdge(page)).click();
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-start_edge_to_centre").click();
  await expect(page.getByTestId("dimension-pick-hint")).toContainText(
    /hole centre/i,
  );
  await markA!.pick.click();
  await expect(page.getByTestId("dimension-type-edge_to_centre")).toBeVisible();
  await page.getByTestId("dimension-type-edge_to_centre").click();
  await page.keyboard.press("Enter");
  await expect(value(page, "80.000")).toHaveCount(1, { timeout: 30_000 });
  await expect(
    page.locator(
      '[data-testid="dimension-row"][data-dimension-mode="edge_to_centre"]',
    ),
  ).toHaveCount(1);

  // 2) Centre A <-> centre B, PLACED ABOVE both holes: horizontal (Fusion).
  const [b2, a2] = await centres(page);
  await a2!.pick.click();
  await expect(page.getByTestId("dimension-pick-hint")).toContainText(
    /second centre/i,
  );
  await b2!.pick.click();
  await page.getByTestId("dimension-type-centre_to_centre").click();
  const midX = (a2!.box.x + b2!.box.x) / 2 + a2!.box.width / 2;
  const top = Math.min(a2!.box.y, b2!.box.y);
  await page.mouse.move(midX, top - 60, { steps: 4 });
  await page.mouse.click(midX, top - 60);
  await expect(value(page, "60.000")).toHaveCount(1, { timeout: 30_000 });
  await expect(
    page.locator(
      '[data-testid="dimension-row"][data-dimension-mode="centre_to_centre"]',
    ),
  ).toHaveCount(1);

  await page.mouse.move(20, 980);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawing-centre-marks-1600.png`,
  });

  // 3) The one-number edit: W 100 -> 80, hole A moves to x = 60. Both hole
  //    dimensions follow it.
  await resizePlate(page, account.token, part, 80);
  await page.getByTestId("drawing-reproject").click();
  await expect(value(page, "60.000")).toHaveCount(1, { timeout: 30_000 });
  await expect(value(page, "40.000")).toHaveCount(1, { timeout: 30_000 });
  await expect(value(page, "80.000")).toHaveCount(0);
  await expect(
    page.locator('[data-testid="drawing-dimension"][data-dimension-error]'),
  ).toHaveCount(0);

  await page.mouse.move(20, 980);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawing-centre-marks-resized-1600.png`,
  });
});
