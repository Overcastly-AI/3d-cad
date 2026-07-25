import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, seedSession, SCREENSHOT_DIR } from "./support";

/**
 * Units U2 acceptance (docs/design/units.md §U2). The document-unit selector +
 * the one conversion seam, proven against the real stack (gateway + documents +
 * geometry, no mocks):
 *
 *  - Set a part to inches, type `2` in an extrude length → the field round-trips
 *    to `2` in and the PERSISTED/canonical value is 50.8 mm.
 *  - Type `25.4 mm` into that inch document (explicit suffix override) → it
 *    stores 25.4 mm and re-displays as `1` in.
 *
 * The load-bearing rule under test: only canonical mm ever crosses the wire, so
 * every assertion on storage reads the API's `distance_mm` directly.
 */

/** A closed, fully-constrained 40×25 rectangle on XY — solves to a face. */
const RECTANGLE_SKETCH = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 38, y: 1 } },
    { id: "e2", kind: "line", start: { x: 39, y: 0.5 }, end: { x: 41, y: 24 } },
    {
      id: "e3",
      kind: "line",
      start: { x: 40.5, y: 26 },
      end: { x: -1, y: 25.5 },
    },
    {
      id: "e4",
      kind: "line",
      start: { x: 0.5, y: 24.5 },
      end: { x: -0.5, y: 1 },
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
    { kind: "distance", entity: "e1", value_mm: 40 },
    { kind: "distance", entity: "e2", value_mm: 25 },
    { kind: "fixed", point: { entity: "e1", point: "start" } },
  ],
};

/** Seed a part carrying just Sketch1 (a solved 40×25 rectangle) via the API. */
async function seedSketchedPart(
  page: Page,
): Promise<{ id: string; token: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Unit plate");
  const response = await page.request.post(
    `/api/v1/parts/${part.id}/features`,
    {
      data: {
        name: "Sketch1",
        feature: { type: "sketch", version: 1, params: RECTANGLE_SKETCH },
        expected_tree_version: 0,
      },
      headers: { Authorization: `Bearer ${account.token}` },
    },
  );
  if (!response.ok()) {
    throw new Error(
      `e2e seed sketch failed: ${response.status()} ${await response.text()}`,
    );
  }
  return { id: part.id, token: account.token };
}

/** The persisted extrude's canonical `distance_mm`, read straight from the API. */
async function persistedDistanceMm(
  page: Page,
  partId: string,
  token: string,
): Promise<number> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const tree = (await response.json()) as {
    features: Array<{
      feature: { type: string; params: { distance_mm?: number } };
    }>;
  };
  const extrude = tree.features.find((f) => f.feature.type === "extrude");
  if (!extrude || extrude.feature.params.distance_mm === undefined) {
    throw new Error("no extrude with a distance_mm in the tree");
  }
  return extrude.feature.params.distance_mm;
}

test.describe("document units — inch entry stores canonical mm", () => {
  test("set inches, type 2 → stores 50.8 mm; 25.4 mm → displays 1 in", async ({
    page,
  }) => {
    const { id: partId, token } = await seedSketchedPart(page);
    await page.goto(`/parts/${partId}`);

    // The sketch solves, so the extrude action lights up.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // Set the document unit to inches through the chrome selector — a pure
    // re-label persisted via the document PATCH.
    const unitSelect = page.getByTestId("document-unit-select");
    await expect(unitSelect).toHaveValue("mm");
    await unitSelect.selectOption("in");
    await expect(unitSelect).toHaveValue("in");

    // Author an extrude and type 2 (interpreted as inches).
    await page.getByTestId("new-extrude").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    const distance = page.getByTestId("extrude-distance");
    await distance.fill("2");
    await distance.press("Enter");

    // The body evaluates; the CANONICAL stored value is 50.8 mm (2 in), proving
    // conversion happens only at the input boundary — the wire stays mm.
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    expect(await persistedDistanceMm(page, partId, token)).toBeCloseTo(50.8, 3);

    // Re-open the extrude: its length re-seeds in the document unit → reads "2".
    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("extrude-distance")).toHaveValue("2");

    // Founder shot: the document unit selector reads "in" and the extrude length
    // is unit-aware (2 in), the mm→in re-label seam under test made visible.
    await page.mouse.move(1400, 900);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/document-units-inch-desktop.png`,
    });

    // Type an explicit mm-suffixed value into the inch document: the suffix
    // overrides, so 25.4 mm stores 25.4 mm and re-displays as 1 in.
    await distance.fill("25.4 mm");
    await distance.press("Enter");
    await expect
      .poll(() => persistedDistanceMm(page, partId, token), { timeout: 30_000 })
      .toBeCloseTo(25.4, 3);

    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("extrude-distance")).toHaveValue("1");

    // The unit choice persists across a reload (it lives on the document).
    await page.reload();
    await expect(page.getByTestId("document-unit-select")).toHaveValue("in", {
      timeout: 30_000,
    });
  });

  test("mass-props + bbox readouts honor the document unit (FINDINGS #17)", async ({
    page,
  }) => {
    const { id: partId } = await seedSketchedPart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // Author a 10 mm extrude → a 40×25×10 body = 10,000 mm³. In the default mm
    // document the readout is the raw grouped mm³ with the mm³ label.
    await page.getByTestId("new-extrude").click();
    await page.getByTestId("extrude-distance").press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    const volume = page.getByTestId("prop-volume");
    await expect(volume).toContainText("10,000", { timeout: 30_000 });
    await expect(volume).toContainText("mm³");
    await expect(page.getByTestId("prop-area")).toContainText("mm²");

    // Before: the mm readout (audit's baseline).
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.mouse.move(720, 500);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/units-readout-mm-1440.png`,
    });

    // Flip to inches — a PURE re-label: the stored mm never moves, but the
    // readouts now convert. 10,000 mm³ / 25.4³ = 0.6102 in³; the label is in³
    // (the audit bug was the readout still printing raw mm under `in`).
    await page.getByTestId("document-unit-select").selectOption("in");
    await expect(volume).toContainText("in³", { timeout: 30_000 });
    await expect(volume).toContainText("0.61");
    await expect(volume).not.toContainText("mm");
    // 40×25 mm face = 1000 mm² / 25.4² = 1.55 in²; the area label follows too.
    await expect(page.getByTestId("prop-area")).toContainText("in²");
    await expect(page.getByTestId("prop-centroid")).toContainText("in");

    // After: the same body, readouts in inches (1440 + small-laptop).
    await page.mouse.move(720, 500);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/units-readout-in-1440.png`,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.mouse.move(640, 400);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/units-readout-in-1280.png`,
    });
  });

  test("changing units is a pure re-label — the stored mm never moves", async ({
    page,
  }) => {
    const { id: partId, token } = await seedSketchedPart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // Author a 10 mm extrude in the default mm document.
    await page.getByTestId("new-extrude").click();
    await page.getByTestId("extrude-distance").press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    expect(await persistedDistanceMm(page, partId, token)).toBeCloseTo(10, 3);

    // Flip mm → cm → in. The stored mm is untouched by any of it; only the
    // displayed length re-formats (10 mm → 1 cm → ~0.3937 in).
    const unitSelect = page.getByTestId("document-unit-select");
    await unitSelect.selectOption("cm");
    await expect(unitSelect).toHaveValue("cm");
    expect(await persistedDistanceMm(page, partId, token)).toBeCloseTo(10, 3);
    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("extrude-distance")).toHaveValue("1");

    await unitSelect.selectOption("in");
    expect(await persistedDistanceMm(page, partId, token)).toBeCloseTo(10, 3);
  });
});
