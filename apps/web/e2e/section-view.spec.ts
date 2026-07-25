import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * E1b — section-view web authoring, driven end to end through a real browser
 * against the real stack (gateway + documents + geometry, no mocks). E1a made a
 * STORED section view compose to a hatched section; this closes the loop by
 * AUTHORING one in the UI: a plate-with-a-hole part + an XY offset datum are
 * built once via the API, a drawing is created through the register UI, then the
 * Section-view author is opened, the in-tree datum plane is picked as the cutting
 * plane, the removed half is toggled, and "Cut section" persists a `section`
 * view carrying its `section_params`. The compose wire then resolves the datum,
 * cuts the solid, and hatches the cross-section — and the sheet renders the
 * `drawing-hatch` fill on-screen (the same test hook + palette the SVG/PDF/DXF
 * export uses). This is section views FULLY end to end: kernel + wire + web
 * authoring, "a working engineer cuts a section in the app," the founder payoff.
 */

/** Build a 40×25×10 plate with a Ø10 through hole + an XY datum offset to z=5
 * (the cutting plane a section slices through the solid's mid-height). Returns
 * the part id and the datum feature id the section view will reference. */
async function createPlateWithSectionDatum(
  page: Page,
  token: string,
  name: string,
): Promise<{ id: string; datumId: string }> {
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
              end: { x: 40, y: 0 },
            },
            {
              id: "e2",
              kind: "line",
              start: { x: 40, y: 0 },
              end: { x: 40, y: 25 },
            },
            {
              id: "e3",
              kind: "line",
              start: { x: 40, y: 25 },
              end: { x: 0, y: 25 },
            },
            {
              id: "e4",
              kind: "line",
              start: { x: 0, y: 25 },
              end: { x: 0, y: 0 },
            },
            {
              id: "e5",
              kind: "circle",
              center: { x: 20, y: 12.5 },
              radius: 5,
              construction: false,
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
          distance_mm: 10,
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
  const extrudeBody = (await extrude.json()) as { tree_version: number };

  // The cutting plane: an XY datum offset to z=5 — a principal (axis-aligned)
  // plane through the plate's mid-height, so the section slices a real face.
  const datum = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Datum XY+5",
      feature: {
        type: "datum",
        version: 1,
        params: { kind: "offset", base: "XY", offset_mm: 5, flip: false },
      },
      expected_tree_version: extrudeBody.tree_version,
    },
    headers: auth,
  });
  if (!datum.ok()) {
    throw new Error(`datum failed: ${datum.status()} ${await datum.text()}`);
  }
  const datumId = ((await datum.json()) as { feature: { id: string } }).feature
    .id;
  return { id: partId, datumId };
}

test("author a section view in the app and see it hatched on the sheet", async ({
  page,
}) => {
  const account = await seedSession(page);
  const part = await createPlateWithSectionDatum(
    page,
    account.token,
    "Plate — section",
  );

  // Create the drawing through the register UI.
  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill("Plate — section A-A");
  await page.getByTestId("create-drawing-submit").click();
  const row = page.getByTestId("drawing-row").first();
  await expect(row).toBeVisible();
  await row.getByTestId("drawing-open").click();

  // Choose the part; the Section-view action is available on the empty bench.
  await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
  await page.getByTestId("drawing-part-select").selectOption(part.id);
  const sectionButton = page.getByTestId("drawing-section");
  await expect(sectionButton).toBeEnabled();

  // Founder frame (before) — the pre-layout bench with the new Section action.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.mouse.move(720, 500);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-section-before-1440.png`,
  });

  // Open the Section-view author. It reuses the sketch plane picker's vocabulary
  // — the three origin datums, then the part's in-tree datums (FeatureRefs).
  await sectionButton.click();
  const panel = page.getByTestId("section-author-panel");
  await expect(panel).toBeVisible();

  // Pick the in-tree XY+5 datum as the cutting plane (its normal is axis-aligned,
  // so the v1 precondition passes and Cut is enabled). The readout reflects it.
  const datumChoice = page.getByTestId(`section-plane-datum-${part.datumId}`);
  await expect(datumChoice).toBeVisible();
  await datumChoice.click();
  await expect(page.getByTestId("section-readout")).toHaveText("XY +5");

  // Toggle which half is removed, then cut — exercising the flip control.
  await page.getByTestId("section-flip-far").click();

  // Founder frame — the section author open with the plane + flip chosen.
  await expect(page.getByTestId("section-confirm")).toBeEnabled();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-section-author-1440.png`,
  });

  await page.getByTestId("section-confirm").click();

  // The sheet composes with the persisted section view — resolved, cut, hatched.
  const sheet = page.getByTestId("drawing-sheet");
  await expect(sheet).toBeVisible({ timeout: 30_000 });

  // The section view landed and produced real geometry (not a typed failure).
  const sectionView = page.locator(
    '[data-testid="drawing-view"][data-view="section"]',
  );
  await expect(sectionView).toHaveAttribute("data-view-error", "false", {
    timeout: 30_000,
  });
  expect(
    await sectionView.locator("line, circle, polyline").count(),
  ).toBeGreaterThan(0);

  // THE payoff: the cross-section is hatched on-screen — the ANSI 45° fill, the
  // same `drawing-hatch` hook + palette the SVG/PDF/DXF export draws.
  const hatch = page.getByTestId("drawing-hatch");
  await expect(hatch.first()).toBeAttached({ timeout: 30_000 });
  expect(await hatch.locator("line").count()).toBeGreaterThan(0);

  // Founder frames (after) — a hatched section on the sheet, desktop + laptop.
  await page.mouse.move(720, 500);
  await expect(sheet).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-section-after-1440.png`,
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(sheet).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-section-after-1280.png`,
  });
});
