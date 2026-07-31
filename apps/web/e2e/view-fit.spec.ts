import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";
import { createFeature } from "./partSeed";

/**
 * "Fit model" frames the VISIBLE viewport, not the canvas (founder capture
 * 2026-07-31, `docs/BACKLOG.md` P2 + P3).
 *
 * The defect, measured on a 120×80×40 shelled enclosure: the canvas is
 * full-bleed and the feature tree, the Bodies list and the inspector FLOAT over
 * it, so an arithmetically perfect fit put a third of the part under the tree,
 * a third under the inspector, and the top edge off the frame. A control that
 * hides the thing it just claimed to fit is chrome that does not do what it
 * says — mandate 3c.
 *
 * The invariant asserted here is the one the backlog asked for: the body's
 * PROJECTED bounding box lies inside the unobstructed rect, with margin on all
 * four sides, for parts of very different aspect ratios. The projected box is
 * measured from the canvas PIXELS (the lit machined-aluminum body against the
 * dark bench), so it cannot pass by agreeing with the same arithmetic that
 * produced the camera pose; the rect is read from the `data-fit-rect` hook the
 * rig stamps after the move settles.
 */

/** A rectangular profile on XY, fixed at the origin. */
function rectangle(widthMm: number, depthMm: number) {
  return {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [
      {
        id: "e1",
        kind: "line",
        start: { x: 0, y: 0 },
        end: { x: widthMm, y: 0 },
      },
      {
        id: "e2",
        kind: "line",
        start: { x: widthMm, y: 0 },
        end: { x: widthMm, y: depthMm },
      },
      {
        id: "e3",
        kind: "line",
        start: { x: widthMm, y: depthMm },
        end: { x: 0, y: depthMm },
      },
      {
        id: "e4",
        kind: "line",
        start: { x: 0, y: depthMm },
        end: { x: 0, y: 0 },
      },
    ],
    constraints: [
      {
        kind: "coincident",
        a: { entity: "e1", point: "end" },
        b: { entity: "e2", point: "start" },
      },
      {
        kind: "coincident",
        a: { entity: "e2", point: "end" },
        b: { entity: "e3", point: "start" },
      },
      {
        kind: "coincident",
        a: { entity: "e3", point: "end" },
        b: { entity: "e4", point: "start" },
      },
      {
        kind: "coincident",
        a: { entity: "e4", point: "end" },
        b: { entity: "e1", point: "start" },
      },
      { kind: "horizontal", entity: "e1" },
      { kind: "vertical", entity: "e2" },
      { kind: "horizontal", entity: "e3" },
      { kind: "vertical", entity: "e4" },
      { kind: "distance", entity: "e1", value_mm: widthMm },
      { kind: "distance", entity: "e2", value_mm: depthMm },
      { kind: "fixed", point: { entity: "e1", point: "start" } },
    ],
  };
}

/** Seed a w × d × h box through the real gateway. */
export async function seedBox(
  page: Page,
  token: string,
  partId: string,
  widthMm: number,
  depthMm: number,
  heightMm: number,
): Promise<void> {
  const sketch = await createFeature(page, token, partId, {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangle(widthMm, depthMm),
    },
    expected_tree_version: 0,
  });
  await createFeature(page, token, partId, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: heightMm,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
}

interface Box {
  left: number;
  top: number;
  right: number;
  bottom: number;
  pixels: number;
}

/**
 * The reference cube's corner, excluded from the body census. The cube is drawn
 * INTO the same canvas (a drei `GizmoHelper` scissor viewport) and its engraved
 * labels are bright, so without this mask every measurement of "where the body
 * is" reports the cube's right edge. Sized from the cube's own constants in
 * `Viewport.tsx` — a 96px inset plus half of a 120px footprint, plus slack —
 * and the fit already treats the same square as an obstruction, so the masked
 * region lies outside the rect being asserted against.
 */
const CUBE_MASK_PX = 170;

/**
 * A column/row must carry at least this many bright pixels to count as part of
 * the body. Measured need, not a fudge: the drawing buffer carries a handful of
 * ISOLATED bright pixels (a stray AA fragment at the frame edge under software
 * GL), and a raw min/max over pixels reported the body's right edge at 1436px
 * when its silhouette genuinely ended at 1080px. A silhouette is a run, not a
 * speck, so the extent is taken over columns and rows with real coverage.
 */
const COVERAGE_MIN = 4;

/**
 * The body's projected bounding box in CSS pixels, read off the drawing buffer.
 * "Body" is anything brighter than the bench: the studio matcap's body tone is
 * ~163, the major grid tops out at ~76 and the atmosphere is painted in the DOM
 * behind a transparent canvas.
 *
 * Note this reads the CANVAS, so a body that runs under an opaque floating
 * panel is still measured — which is exactly the defect being asserted against.
 */
async function bodyPixelBox(page: Page): Promise<Box> {
  return page.evaluate(
    ([maskPx, minCoverage]: [number, number]) => {
      const canvas = document.querySelector<HTMLCanvasElement>(
        '[data-testid="viewport"] canvas',
      );
      const empty = { left: 0, top: 0, right: 0, bottom: 0, pixels: 0 };
      if (!canvas) return empty;
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      if (!ctx) return empty;
      ctx.drawImage(canvas, 0, 0);
      const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
      const columns = new Uint32Array(probe.width);
      const rows = new Uint32Array(probe.height);
      let pixels = 0;
      const maskX = probe.width - maskPx * (probe.width / canvas.clientWidth);
      const maskY =
        probe.height - maskPx * (probe.height / canvas.clientHeight);
      for (let i = 0; i < data.length; i += 4) {
        const r = data[i] ?? 0;
        const g = data[i + 1] ?? 0;
        const b = data[i + 2] ?? 0;
        if (0.2126 * r + 0.7152 * g + 0.0722 * b <= 110) continue;
        const pixel = i / 4;
        const x = pixel % probe.width;
        const y = Math.floor(pixel / probe.width);
        if (x > maskX && y > maskY) continue; // the reference cube's corner
        columns[x] = (columns[x] ?? 0) + 1;
        rows[y] = (rows[y] ?? 0) + 1;
        pixels += 1;
      }
      const span = (counts: Uint32Array): [number, number] | null => {
        let lo = -1;
        let hi = -1;
        for (let i = 0; i < counts.length; i += 1) {
          if ((counts[i] ?? 0) < minCoverage) continue;
          if (lo < 0) lo = i;
          hi = i;
        }
        return lo < 0 ? null : [lo, hi];
      };
      const x = span(columns);
      const y = span(rows);
      if (x === null || y === null) return empty;
      // Buffer pixels → CSS pixels (dpr-independent).
      const sx = canvas.clientWidth / probe.width;
      const sy = canvas.clientHeight / probe.height;
      return {
        left: x[0] * sx,
        top: y[0] * sy,
        right: x[1] * sx,
        bottom: y[1] * sy,
        pixels,
      };
    },
    [CUBE_MASK_PX, COVERAGE_MIN] as [number, number],
  );
}

/** The rect the rig actually framed into, from its QA hook. */
async function fitRect(page: Page): Promise<Box> {
  const raw = await page.getByTestId("viewport").getAttribute("data-fit-rect");
  const parts = (raw ?? "").split(",").map(Number);
  const [x, y, width, height] = parts;
  if (
    parts.length !== 4 ||
    x === undefined ||
    y === undefined ||
    width === undefined ||
    height === undefined ||
    Number.isNaN(x)
  ) {
    throw new Error(`viewport did not report a fit rect (got "${raw}")`);
  }
  return {
    left: x,
    top: y,
    right: x + width,
    bottom: y + height,
    pixels: 0,
  };
}

/** Seed a part of the given extents, open it, fit it. */
async function fitPart(
  page: Page,
  name: string,
  extents: [number, number, number],
): Promise<void> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, name);
  await seedBox(page, token, part.id, extents[0], extents[1], extents[2]);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByTestId("viewport")).toHaveAttribute(
    "data-total-faces",
    /[1-9]/,
    { timeout: 30_000 },
  );
  await page.getByTestId("view-fit").click();
  await page.waitForTimeout(900);
}

test.describe("view fit frames the UNOBSTRUCTED viewport", () => {
  // Three very different aspect ratios: a wide enclosure (the founder's case),
  // a tall column, and a long bar. Each stresses a different edge.
  const CASES: { name: string; extents: [number, number, number] }[] = [
    { name: "Enclosure", extents: [120, 80, 40] },
    { name: "Column", extents: [40, 40, 200] },
    { name: "Rail", extents: [260, 24, 24] },
  ];

  for (const shape of CASES) {
    test(`${shape.name} lands inside the free rect on all four sides`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await fitPart(page, shape.name, shape.extents);

      const body = await bodyPixelBox(page);
      expect(body.pixels).toBeGreaterThan(500);
      const free = await fitRect(page);

      // Margin on all four sides. 2px of slack absorbs sub-pixel raster drift
      // (the documented tolerance class from the undo-redo band-fit fix); the
      // fit's own margin is 24px, so this is not papering over a real miss.
      expect(body.left).toBeGreaterThanOrEqual(free.left - 2);
      expect(body.right).toBeLessThanOrEqual(free.right + 2);
      expect(body.top).toBeGreaterThanOrEqual(free.top - 2);
      expect(body.bottom).toBeLessThanOrEqual(free.bottom + 2);

      // …and it still FILLS the frame it was given: a fit that satisfies the
      // containment test by zooming to a speck would be the opposite defect.
      const width = body.right - body.left;
      const height = body.bottom - body.top;
      expect(
        Math.max(
          width / (free.right - free.left),
          height / (free.bottom - free.top),
        ),
      ).toBeGreaterThan(0.3);
    });
  }

  test("collapsing a panel gives the space back", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await fitPart(page, "Enclosure", [120, 80, 40]);
    const before = await fitRect(page);

    await page.getByTestId("panel-collapse-tree").click();
    await page.waitForTimeout(900);
    const after = await fitRect(page);
    expect(after.right - after.left).toBeGreaterThan(
      before.right - before.left,
    );

    // The part re-framed itself into the wider rect rather than staying parked
    // where the old chrome put it.
    const body = await bodyPixelBox(page);
    expect(body.left).toBeGreaterThanOrEqual(after.left - 2);
    expect(body.right).toBeLessThanOrEqual(after.right + 2);
  });

  test("founder shots — enclosure framing at two widths", async ({ page }) => {
    for (const width of [1440, 1366]) {
      await page.setViewportSize({ width, height: 900 });
      await fitPart(page, "Enclosure", [120, 80, 40]);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/viewfit-after-${width}.png`,
      });
    }
  });
});
