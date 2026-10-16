import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * "Lay out standard views" picks the standard scale that fits the sheet
 * (BIKE2-DRAWING-SCALE).
 *
 * Bike round 2 laid a 1.6 m assembly out on A4 at 1:10, the smallest scale the
 * picker had: all four views ran off the paper and a red error was printed on
 * the sheet. Fusion and SolidWorks default a new drawing to the largest
 * standard scale whose views fit, so:
 *
 *  - a 1,622 x 100 x 650 mm two-wheel assembly (two instances of one Wheel
 *    sub-assembly plus a frame) lays out on A4 at 1:20, every view frame inside
 *    the drawn border and off the title block, no issue reported, no error text
 *    on the paper, and the title block names it an ASSEMBLY DRAWING;
 *  - a 20 mm cube is drawn bigger than life, at 2:1.
 *
 * The scales are the unit-tested rule's (`layout.test.ts`) for these extents;
 * the frames are measured in the browser, as the founder sees them.
 */

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A `w` x `d` x `h` box, its sketch rectangle centred on the origin in x/y
 * when `centred`, extruded +Z. */
async function boxPartViaApi(
  page: Page,
  token: string,
  name: string,
  [w, d, h]: [number, number, number],
  centred = true,
): Promise<string> {
  const headers = { Authorization: `Bearer ${token}` };
  const part = await page.request.post("/api/v1/parts", {
    data: { name },
    headers,
  });
  expect(part.ok(), await part.text()).toBe(true);
  const partId = ((await part.json()) as { id: string }).id;
  const [x0, y0] = centred ? [-w / 2, -d / 2] : [0, 0];
  const corners = [
    [x0, y0],
    [x0 + w, y0],
    [x0 + w, y0 + d],
    [x0, y0 + d],
  ] as const;
  const sketch = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Sketch1",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          entities: corners.map(([x, y], i) => {
            const [nx, ny] = corners[(i + 1) % 4]!;
            return {
              id: `e${i + 1}`,
              kind: "line",
              start: { x, y },
              end: { x: nx, y: ny },
            };
          }),
          constraints: [],
        },
      },
      expected_tree_version: 0,
    },
    headers,
  });
  expect(sketch.ok(), await sketch.text()).toBe(true);
  const body = (await sketch.json()) as {
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
          profile: { kind: "feature", feature_id: body.feature.id },
          distance_mm: h,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: body.tree_version,
    },
    headers,
  });
  expect(extrude.ok(), await extrude.text()).toBe(true);
  return partId;
}

/** An assembly of grounded instances, through the real gateway. */
async function assemblyViaApi(
  page: Page,
  token: string,
  name: string,
  instances: {
    ref: string;
    kind: "part" | "assembly";
    name: string;
    at: [number, number, number];
  }[],
): Promise<string> {
  const headers = { Authorization: `Bearer ${token}` };
  const created = await page.request.post("/api/v1/assemblies", {
    data: { name },
    headers,
  });
  expect(created.ok(), await created.text()).toBe(true);
  const id = ((await created.json()) as { id: string }).id;
  let version = 0;
  for (const instance of instances) {
    const [x, y, z] = instance.at;
    const response = await page.request.post(
      `/api/v1/assemblies/${id}/instances`,
      {
        data: {
          expected_version: version,
          ref_document_id: instance.ref,
          ref_document_kind: instance.kind,
          name: instance.name,
          grounded: true,
          placement: {
            position: { x, y, z },
            orientation: { x: 0, y: 0, z: 0, w: 1 },
          },
        },
        headers,
      },
    );
    expect(response.ok(), await response.text()).toBe(true);
    version = ((await response.json()) as { doc_version: number }).doc_version;
  }
  return id;
}

/** Open a new drawing of `sourceId` and lay out the four standard views. */
async function layOutDrawing(
  page: Page,
  token: string,
  name: string,
  sourceId: string,
): Promise<void> {
  const created = await page.request.post("/api/v1/drawings", {
    data: { name },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(created.ok(), await created.text()).toBe(true);
  const drawingId = ((await created.json()) as { id: string }).id;
  await page.goto(`/drawings/${drawingId}?source=${sourceId}`);
  await expect(page.getByTestId("drawing-part-select")).toHaveValue(sourceId);
  // The caption quotes the scale Auto will pick, once the source is measured.
  await expect(page.getByTestId("drawing-autolayout")).toHaveAttribute(
    "data-paper",
    /landscape \d+:\d+/,
    { timeout: 60_000 },
  );
  await page.getByTestId("drawing-autolayout").click();
  await expect(page.getByTestId("drawing-view")).toHaveCount(4, {
    timeout: 90_000,
  });
}

/** The drawn border, the title block and every view frame, in viewport px. */
async function sheetRects(page: Page): Promise<{
  border: Rect;
  title: Rect;
  frames: { view: string; rect: Rect }[];
}> {
  return page.evaluate(() => {
    const box = (el: Element) => {
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height };
    };
    const one = (testId: string) => {
      const el = document.querySelector(`[data-testid="${testId}"]`);
      if (el === null) throw new Error(`no ${testId} on the sheet`);
      return box(el);
    };
    return {
      border: one("drawing-border"),
      title: one("drawing-title-block"),
      frames: Array.from(
        document.querySelectorAll('[data-testid="drawing-view-drag"]'),
      ).map((el) => ({
        view: el.closest("[data-view]")?.getAttribute("data-view") ?? "?",
        rect: box(el),
      })),
    };
  });
}

/** How far (px) `inner` pokes outside `outer` on its worst side; <= 0 inside. */
function overrun(inner: Rect, outer: Rect): number {
  return Math.max(
    outer.x - inner.x,
    outer.y - inner.y,
    inner.x + inner.w - (outer.x + outer.w),
    inner.y + inner.h - (outer.y + outer.h),
  );
}

function overlapArea(a: Rect, b: Rect): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  return w > 0 && h > 0 ? w * h : 0;
}

test.describe("Drawings — the layout picks a standard scale that fits", () => {
  test("a 1.6 m two-level assembly lays out on A4 at 1:20, every view inside the border", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width: 1600, height: 1000 });
    const { token } = await seedSession(page);

    // Wheel = an upright 622 mm disc (a box, x/z) and a hub through it (along
    // y); Bike = two of that Wheel 1000 mm apart and a frame over them.
    const rim = await boxPartViaApi(page, token, "Rim", [622, 20, 622]);
    const hub = await boxPartViaApi(page, token, "Hub", [40, 100, 40]);
    const frame = await boxPartViaApi(
      page,
      token,
      "Frame",
      [1000, 50, 50],
      false,
    );
    const wheel = await assemblyViaApi(page, token, "Wheel", [
      { ref: rim, kind: "part", name: "Rim <1>", at: [0, 0, 0] },
      { ref: hub, kind: "part", name: "Hub <1>", at: [0, 0, 291] },
    ]);
    const bike = await assemblyViaApi(page, token, "Bike", [
      { ref: frame, kind: "part", name: "Frame <1>", at: [0, -25, 600] },
      { ref: wheel, kind: "assembly", name: "Wheel <1>", at: [0, 0, 0] },
      { ref: wheel, kind: "assembly", name: "Wheel <2>", at: [1000, 0, 0] },
    ]);

    // The premise, from the server: 1,622 x 100 x 650 mm once solved.
    const extents = await page.request.get(
      `/api/v1/assemblies/${bike}/extents`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    expect(extents.ok(), await extents.text()).toBe(true);
    const box = (
      (await extents.json()) as {
        bounding_box: {
          min: { x: number; y: number; z: number };
          max: { x: number; y: number; z: number };
        };
      }
    ).bounding_box;
    expect(box.max.x - box.min.x).toBeCloseTo(1622, 3);
    expect(box.max.y - box.min.y).toBeCloseTo(100, 3);
    expect(box.max.z - box.min.z).toBeCloseTo(650, 3);

    // Auto is the default, on the default A4 the user has not fixed.
    await layOutDrawing(page, token, "Bike drawing", bike);
    await expect(page.getByTestId("drawing-size-readout")).toHaveText("A4");
    await expect(page.getByTestId("drawing-scale-readout")).toHaveText("1:20");
    await expect(page.getByTestId("title-block-scale")).toHaveText("1:20");
    await expect(page.getByTestId("title-block-kind")).toHaveText(
      "LOFT · ASSEMBLY DRAWING",
    );

    // Every view frame (geometry + caption + pad) lies inside the drawn border
    // and off the title block. Filtered, so a failure names the view and px.
    const { border, title, frames } = await sheetRects(page);
    expect(frames).toHaveLength(4);
    expect(
      frames
        .map((f) => ({ view: f.view, over: overrun(f.rect, border) }))
        .filter((f) => f.over > 0.5),
    ).toEqual([]);
    expect(
      frames
        .map((f) => ({ view: f.view, area: overlapArea(f.rect, title) }))
        .filter((f) => f.area > 0),
    ).toEqual([]);
    // The views carry ink (fitted, not empty), and nothing reports a problem:
    // no issue strip, and never error text on the paper.
    const ink = await page
      .locator('[data-testid="drawing-view"][data-view="front"]')
      .evaluate((g) => g.querySelectorAll("line, polyline, path").length);
    expect(ink).toBeGreaterThan(8);
    await expect(page.getByTestId("sheet-issue-strip")).toHaveCount(0);
    await expect(page.getByTestId("drawing-layout-issue")).toHaveCount(0);
    await expect(page.getByTestId("drawing-sheet")).not.toContainText("LAYOUT");

    await page.mouse.move(20, 980);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/drawing-autoscale.png` });
  });

  test("a 20 mm part is drawn at 2:1", async ({ page }) => {
    test.setTimeout(120_000);
    const { token } = await seedSession(page);
    const cube = await boxPartViaApi(page, token, "Cube 20", [20, 20, 20]);
    await layOutDrawing(page, token, "Cube drawing", cube);
    await expect(page.getByTestId("drawing-scale-readout")).toHaveText("2:1");
    await expect(page.getByTestId("title-block-kind")).toHaveText(
      "LOFT · PART DRAWING",
    );
    const { border, title, frames } = await sheetRects(page);
    for (const f of frames) {
      expect(overrun(f.rect, border), `${f.view} past the border`).toBeLessThan(
        0.5,
      );
      expect(overlapArea(f.rect, title), `${f.view} on the title block`).toBe(
        0,
      );
    }
  });
});
