import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Daily-driver proof for the multi-loop-profile win (commit a36e436): a single
 * sketch of an OUTER boundary + INNER circles now extrudes into a plate WITH
 * HOLES — the product audit's #1 gap (bolt circles), closed backend-side with
 * NO frontend change. The sketcher already authors multiple closed loops in one
 * sketch; this spec proves the whole flow end-to-end through the real browser
 * and the real stack (gateway + documents + geometry, no mocks): sketch an
 * outer rectangle + two inner circles → extrude (add) → assert the resulting
 * body is a holed plate.
 *
 * Holes are proven two independent ways, both read from the OCCT mass
 * properties the geometry service computed:
 *   1. Topology — a solid rectangular prism has 6 faces; each through-hole adds
 *      one cylindrical wall, so a two-hole plate has exactly 8 faces.
 *   2. Volume — a solid plate's volume equals its bounding box (X·Y·Z); a holed
 *      plate is strictly LESS (the two bores removed material), so
 *      volume < X·Y·Z is the material-was-removed proof, independent of the
 *      exact mouse-drawn dimensions.
 */

/** The lit aluminium solid + B-rep edges paint far more shades than ground. */
async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/** Enter sketch mode on a datum plane. */
async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
}

/**
 * Draw a bolt-plate: an outer rectangle (two corner clicks → four CCW lines)
 * plus two disjoint inner circles (each: center click, then radius click). Both
 * circle centers and their full radii sit strictly inside the rectangle with a
 * wide margin, and the circles are far apart — the v1 rule the builder enforces
 * (one outer boundary + strictly-interior, mutually-disjoint holes). Since the
 * normal-on sketch camera maps screen pixels to plane mm affinely, screen-
 * interior is plane-interior regardless of the pixel→mm scale.
 */
async function sketchBoltPlate(
  page: Page,
  rect: { a: { x: number; y: number }; b: { x: number; y: number } },
  holes: ReadonlyArray<{ cx: number; cy: number; rx: number; ry: number }>,
): Promise<void> {
  // Outer rectangle.
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(rect.a.x, rect.a.y);
  await page.mouse.move(rect.b.x, rect.b.y);
  await page.mouse.click(rect.b.x, rect.b.y);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

  // Two inner circles — the bolt holes.
  for (const hole of holes) {
    await page.keyboard.press("c");
    await expect(page.getByTestId("tool-circle")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.mouse.click(hole.cx, hole.cy); // center
    await page.mouse.move(hole.rx, hole.ry);
    await page.mouse.click(hole.rx, hole.ry); // radius point
  }

  // Outer rect (4 lines) + 2 circles = 6 committed entities, all in one sketch.
  await expect(page.getByTestId("sketch-save")).toContainText("6 entities");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** Extrude the just-solved sketch 10 mm as an ADD, keyboard-first (Enter). */
async function extrudeAdd(page: Page): Promise<void> {
  const extrudeAction = page.getByTestId("new-extrude");
  await expect(extrudeAction).toBeEnabled();
  await extrudeAction.click();
  await expect(page.getByTestId("extrude-editor")).toBeVisible();
  await expect(page.getByTestId("extrude-op-add")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByTestId("extrude-distance").press("Enter");
}

/** The body volume (mm³) — the cell carries its label + unit, so parse. */
async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

/** The bounding-box extents (mm) as [X, Y, Z] — "40 × 25 × 10" → [40,25,10]. */
async function bodyExtents(page: Page): Promise<number[]> {
  const text = await page.getByTestId("prop-extents").innerText();
  // The cell reads "Extents 40 × 25 × 10 mm"; keep only the ×-joined figures.
  return text
    .split("×")
    .map((part) => {
      const m = part.match(/[\d.]+/);
      return m ? Number.parseFloat(m[0]) : Number.NaN;
    })
    .filter((n) => Number.isFinite(n));
}

/** The topology face count from the inspector (label "Faces" carries no digit). */
async function bodyFaceCount(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-faces").innerText();
  const match = text.match(/\d+/);
  return match ? Number.parseInt(match[0], 10) : Number.NaN;
}

/**
 * Assert the rendered body is a HOLED plate: exactly 8 faces (6-box + 2
 * cylindrical bores) and a volume strictly less than its bounding-box product
 * (material removed by the two holes). A solid plate would be 6 faces and
 * volume == X·Y·Z, so this fails loudly if the holes were ever dropped.
 */
async function expectHoledPlate(page: Page): Promise<void> {
  await expect(page.getByTestId("body-inspector")).toBeVisible();
  await expectRenderedBody(page);

  // Topology: two through-holes → two extra cylindrical faces → 8 total.
  expect(await bodyFaceCount(page)).toBe(8);

  // Volume: strictly less than the enclosing box — the bores removed material.
  const [x, y, z] = await bodyExtents(page);
  expect(Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)).toBe(
    true,
  );
  const boxVolume = (x as number) * (y as number) * (z as number);
  const volume = await bodyVolume(page);
  expect(volume).toBeLessThan(boxVolume);
  // Sanity floor: the plate is still mostly material, not a sliver — the holes
  // did not swallow the whole face (guards against a degenerate over-cut).
  expect(volume).toBeGreaterThan(boxVolume * 0.5);
}

test.describe("extrude multi-loop profile → holes", () => {
  test("bolt-plate: outer rectangle + two inner circles → plate with holes", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Bolt plate");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    await sketchBoltPlate(
      page,
      { a: { x: 650, y: 420 }, b: { x: 1050, y: 700 } },
      [
        { cx: 780, cy: 560, rx: 780, ry: 520 },
        { cx: 950, cy: 560, rx: 950, ry: 520 },
      ],
    );

    await extrudeAdd(page);

    // Both features present, tree solved, and the body is a HOLED plate.
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    await expectHoledPlate(page);

    // Reload: the tree re-evaluates through the real API and the holes persist.
    await page.reload();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expectHoledPlate(page);
  });
});

test.describe("extrude holes — founder screenshots (desktop 1600)", () => {
  test("multi-loop sketch + resulting holed plate", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Bolt plate");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");

    // Draw the multi-loop sketch, then capture it BEFORE saving — the marquee
    // "one sketch, three closed loops" frame (outer rectangle + two bores).
    await page.keyboard.press("r");
    await page.mouse.click(650, 420);
    await page.mouse.move(1050, 700);
    await page.mouse.click(1050, 700);
    for (const hole of [
      { cx: 780, cy: 560, rx: 780, ry: 520 },
      { cx: 950, cy: 560, rx: 950, ry: 520 },
    ]) {
      await page.keyboard.press("c");
      await page.mouse.click(hole.cx, hole.cy);
      await page.mouse.move(hole.rx, hole.ry);
      await page.mouse.click(hole.rx, hole.ry);
    }
    await expect(page.getByTestId("sketch-save")).toContainText("6 entities");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-holes-sketch-desktop.png`,
    });

    // Save + extrude → the holed plate body, mass properties in the inspector.
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await extrudeAdd(page);
    await expectHoledPlate(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-holes-body-desktop.png`,
    });
  });
});

test.describe("extrude holes — founder screenshots (laptop 1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("holes flow stays viewport-dominant at laptop width", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Bolt plate");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");

    await page.keyboard.press("r");
    await page.mouse.click(500, 300);
    await page.mouse.move(820, 540);
    await page.mouse.click(820, 540);
    for (const hole of [
      { cx: 600, cy: 430, rx: 600, ry: 400 },
      { cx: 720, cy: 430, rx: 720, ry: 400 },
    ]) {
      await page.keyboard.press("c");
      await page.mouse.click(hole.cx, hole.cy);
      await page.mouse.move(hole.rx, hole.ry);
      await page.mouse.click(hole.rx, hole.ry);
    }
    await expect(page.getByTestId("sketch-save")).toContainText("6 entities");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-holes-sketch-laptop.png`,
    });

    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await extrudeAdd(page);
    await expectHoledPlate(page);

    // The model still holds the centre; tree + inspector flank it.
    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(560);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-holes-body-laptop.png`,
    });
  });
});
