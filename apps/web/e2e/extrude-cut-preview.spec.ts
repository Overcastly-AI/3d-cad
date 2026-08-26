import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * The live extrude ghost obeys the OPERATION (FINDINGS burn-down 2026-07-25
 * #5). Choosing Cut used to paint the very same warm brass SOLID an Add
 * paints — a preview that stated the opposite of what Save produces (a
 * pocket). The ghost now reads a cut as a void: cold back walls under a
 * dashed hidden-line silhouette, and no brass metal anywhere.
 *
 * Proven raster-independently (the marker carries the operation) AND on the
 * canvas itself: the warm brass pixels the add ghost paints all but vanish
 * when the operation flips to Cut, on the same camera, same profile, same
 * depth. Screenshots feed the founder update.
 */

/** Which capture pass this run is (`before` runs against the pre-fix ghost). */
const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";

/**
 * Count the canvas pixels that read as warm metal (brass-tinted): red clearly
 * ahead of blue, and bright enough not to be the blued-steel bench. The add
 * ghost is exactly this; a void must not be.
 *
 * THE DEPTH GAUGE IS EXCLUDED, and it has to be (T-23). The extrude handle is a
 * brass arrow standing on the profile whenever the editor is open, in BOTH
 * operations — it is the manipulator, not the material, and Fusion's is the
 * same colour whatever the operation. Left in the count it puts a constant
 * brass floor under both readings, which is not a wrong picture but is a wrong
 * MEASUREMENT: this test's question is what the swept volume reads as. The
 * gauge occupies a narrow column on the profile's centre, so the column is
 * skipped, in both states equally — the comparison keeps its power because the
 * ghost is far wider than the shaft.
 */
const GAUGE_COLUMN_HALF_PX = 40;

async function warmPixels(page: Page): Promise<number> {
  return page.evaluate((halfPx: number) => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (!canvas) return -1;
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const ctx = probe.getContext("2d");
    if (!ctx) return -1;
    ctx.drawImage(canvas, 0, 0);
    const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
    // The gauge's column, in CANVAS pixels (the canvas may be scaled).
    const canvasRect = canvas.getBoundingClientRect();
    const scale = canvasRect.width > 0 ? probe.width / canvasRect.width : 1;
    const gripRect = document
      .querySelector('[data-testid="extrude-depth-handle"]')
      ?.getBoundingClientRect();
    const columnX =
      gripRect === undefined
        ? null
        : (gripRect.x + gripRect.width / 2 - canvasRect.x) * scale;
    const columnHalf = halfPx * scale;
    let warm = 0;
    for (let i = 0; i < data.length; i += 16) {
      if (columnX !== null) {
        const x = (i >> 2) % probe.width;
        if (Math.abs(x - columnX) < columnHalf) continue;
      }
      const r = data[i] ?? 0;
      const b = data[i + 2] ?? 0;
      if (r > 110 && r - b > 30) warm++;
    }
    return warm;
  }, GAUGE_COLUMN_HALF_PX);
}

/**
 * Seed a plate with a SECOND sketch (a circle inside its footprint) through the
 * real gateway: exactly the founder's scenario — a circle on a plate, about to
 * become a pocket.
 */
async function seedPlateWithPocketProfile(page: Page): Promise<string> {
  const account = await seedSession(page);
  const auth = { Authorization: `Bearer ${account.token}` };

  const part = await page.request.post("/api/v1/parts", {
    data: { name: "Pocket plate" },
    headers: auth,
  });
  if (!part.ok()) {
    throw new Error(`create part failed: ${part.status()}`);
  }
  const partId = ((await part.json()) as { id: string }).id;

  const seededIds: string[] = [];
  const post = async (body: unknown): Promise<number> => {
    const res = await page.request.post(`/api/v1/parts/${partId}/features`, {
      data: body,
      headers: auth,
    });
    if (!res.ok()) {
      throw new Error(`feature failed: ${res.status()} ${await res.text()}`);
    }
    const json = (await res.json()) as {
      feature: { id: string };
      tree_version: number;
    };
    seededIds.push(json.feature.id);
    return json.tree_version;
  };

  const v1 = await post({
    name: "Plate profile",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [
          {
            id: "l1",
            kind: "line",
            start: { x: 0, y: 0 },
            end: { x: 60, y: 0 },
          },
          {
            id: "l2",
            kind: "line",
            start: { x: 60, y: 0 },
            end: { x: 60, y: 40 },
          },
          {
            id: "l3",
            kind: "line",
            start: { x: 60, y: 40 },
            end: { x: 0, y: 40 },
          },
          {
            id: "l4",
            kind: "line",
            start: { x: 0, y: 40 },
            end: { x: 0, y: 0 },
          },
        ],
        constraints: [],
      },
    },
    expected_tree_version: 0,
  });

  const v2 = await post({
    name: "Plate",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: seededIds[0] },
        distance_mm: 10,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: v1,
  });

  await post({
    name: "Pocket profile",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [
          {
            id: "c1",
            kind: "circle",
            center: { x: 30, y: 20 },
            radius: 9,
            construction: false,
          },
        ],
        constraints: [],
      },
    },
    expected_tree_version: v2,
  });

  return partId;
}

/** Open the part, wait for the solid, and open the extrude editor on the circle. */
async function openExtrudeOnPocketProfile(page: Page): Promise<void> {
  const partId = await seedPlateWithPocketProfile(page);
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-editor")).toBeVisible();
  // The newest sketch (the circle) is the default profile.
  await expect(page.getByTestId("extrude-preview-active")).toBeAttached();
}

test.describe("extrude ghost honors the operation (FINDINGS #5)", () => {
  test("a cut preview reads as a void, not an added solid", async ({
    page,
  }) => {
    await openExtrudeOnPocketProfile(page);
    const marker = page.getByTestId("extrude-preview-active");
    await expect(marker).toHaveAttribute("data-operation", "add");

    // The ADD ghost paints warm brass metal about to exist.
    let addWarm = 0;
    await expect
      .poll(
        async () => {
          addWarm = await warmPixels(page);
          return addWarm;
        },
        { timeout: 15_000 },
      )
      .toBeGreaterThan(200);

    // Flip to Cut — same profile, same depth, same camera.
    await page.getByTestId("extrude-op-cut").click();
    await expect(marker).toHaveAttribute("data-operation", "cut");

    // The brass solid is gone: the ghost now reads as removed material.
    await expect
      .poll(() => warmPixels(page), { timeout: 15_000 })
      .toBeLessThan(addWarm / 4);

    // Flipping back restores the solid read (the ghost tracks the form).
    await page.getByTestId("extrude-op-add").click();
    await expect(marker).toHaveAttribute("data-operation", "add");
    await expect
      .poll(() => warmPixels(page), { timeout: 15_000 })
      .toBeGreaterThan(addWarm / 2);
  });

  test("founder shot: cut ghost on a plate (1440)", async ({ page }) => {
    await openExtrudeOnPocketProfile(page);
    await page.getByTestId("extrude-op-cut").click();
    await expect(page.getByTestId("extrude-preview-active")).toBeAttached();
    await page.waitForTimeout(400); // let the debounced rebuild settle
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-cut-ghost-${SHOT_TAG}-desktop.png`,
    });
  });
});

test.describe("cut ghost small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("founder shot: cut ghost at laptop width", async ({ page }) => {
    await openExtrudeOnPocketProfile(page);
    await page.getByTestId("extrude-op-cut").click();
    await expect(page.getByTestId("extrude-preview-active")).toBeAttached();
    await page.waitForTimeout(400);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-cut-ghost-${SHOT_TAG}-laptop.png`,
    });
  });
});
