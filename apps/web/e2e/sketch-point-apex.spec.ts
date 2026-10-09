import { expect, test, type Page } from "./fixtures";

import { calibratePlane, clickPlane, enterSketch } from "./planeMap";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * SKETCH POINT TOOL, end to end: the golden `loft-pyramid-sq20-h30` built
 * entirely through the UI.
 *
 * The golden lofts a 20 mm square on XY to a single sketch POINT 30 mm up the
 * XZ plane's vertical axis (world (0, 0, 30)): a right square pyramid of
 * exactly a^2 * h / 3 = 4000 mm^3. The loft editor has always advertised "a
 * single point as an apex", but the sketcher had no Point tool, so nobody could
 * author that apex. Here every step is the user's: the square typed point by
 * point with the Line tool, the apex placed by W and a typed X / Y, picked and
 * Fixed (X) as the golden's apex is, then Loft through the two sketches.
 */

/** The golden's analytic volume (services/geometry/goldens/.../expected.json). */
const GOLDEN_VOLUME_MM3 = 4000;

/** One key at a time, as a hand types a coordinate it already knows. */
async function typePoint(page: Page, x: string, y: string): Promise<void> {
  for (const key of x) await page.keyboard.press(key);
  await page.keyboard.press("Tab");
  for (const key of y) await page.keyboard.press(key);
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("point-entry")).toHaveCount(0);
}

/** Persist the open sketch and wait for the tree to solve. */
async function saveSketch(page: Page): Promise<void> {
  const save = page.getByTestId("sketch-save");
  await expect(save).toBeEnabled();
  await save.click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** The volume from the body inspector's mass readout (commas stripped). */
async function volume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  return Number.parseFloat(text.replace(/,/g, "").replace(/[^\d.-]/g, ""));
}

test.use({ viewport: { width: 1280, height: 800 } });

test("a square lofted to a Point-tool apex is the pyramid golden", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Pyramid");
  await page.goto(`/parts/${part.id}`);

  // Section 1: the 20 mm square on XY, every corner typed, the chain closed
  // back onto its first point.
  await enterSketch(page, "XY");
  await page.keyboard.press("l");
  await page.mouse.move(1000, 300);
  await typePoint(page, "-10", "-10");
  await typePoint(page, "10", "-10");
  await typePoint(page, "10", "10");
  await typePoint(page, "-10", "10");
  await typePoint(page, "-10", "-10");
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  await saveSketch(page);

  // Section 2: the apex. W arms the Point tool (the strip says so), a typed
  // X / Y places it, and the tool stays armed with nothing pending.
  await enterSketch(page, "XZ");
  const at = await calibratePlane(page, { x: 560, y: 420 }, { x: 760, y: 300 });
  await page.keyboard.press("w");
  await expect(page.getByTestId("tool-point")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.move(1000, 300);
  await typePoint(page, "0", "30");
  await expect(page.getByTestId("sketch-save")).toContainText("1 entit");
  await expect(page.getByTestId("tool-point")).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  // Pick it and Fix it, as the golden's apex is fixed.
  await page.keyboard.press("Escape"); // back to Select
  await clickPlane(page, at, { x: 0, y: 30 });
  await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
  await page.screenshot({ path: `${SCREENSHOT_DIR}/sketch-point-apex.png` });
  await page.keyboard.press("x");
  await expect(page.getByTestId("selection-readout")).toContainText(
    "nothing selected",
  );
  await saveSketch(page);

  // The persisted apex sketch is exactly the golden's: one point at (0, 30)
  // on XZ, fixed.
  const response = await page.request.get(`/api/v1/parts/${part.id}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = (await response.json()) as {
    features: Array<{
      feature: {
        params: {
          plane: unknown;
          entities: Array<{ kind: string; position?: unknown }>;
          constraints: Array<{ kind: string }>;
        };
      };
    }>;
  };
  const apex = body.features[1]?.feature.params;
  expect(apex?.plane).toMatchObject({ plane: "XZ" });
  expect(apex?.entities, JSON.stringify(apex)).toEqual([
    expect.objectContaining({ kind: "point", position: { x: 0, y: 30 } }),
  ]);
  expect(apex?.constraints.map((c) => c.kind)).toContain("fixed");

  // Loft: the section stack offers the one-point sketch as the apex.
  const loft = page.getByTestId("new-loft");
  await expect(loft).toBeEnabled({ timeout: 30_000 });
  await loft.click();
  await expect(page.getByTestId("loft-editor")).toBeVisible();
  await expect(
    page.getByTestId("loft-section-1").locator("option:checked"),
  ).toHaveText(/\(apex\)$/);
  await page.getByTestId("loft-submit").click();

  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
  await expect
    .poll(() => volume(page), { timeout: 30_000 })
    .toBeCloseTo(GOLDEN_VOLUME_MM3, 1);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/sketch-point-pyramid.png` });
});
