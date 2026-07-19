import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * MB-1 (docs/design/multi-body.md): a part can hold more than one body, and a
 * `boolean` union fuses two of them. This spec seeds TWO overlapping 20 mm
 * cubes through the real gateway — Extrude1 (default merge) is body A; Extrude2
 * carries `merge: false`, so it starts a SECOND body — then drives the browser
 * Combine tool to union them and proves ONE fused solid remains. Real stack:
 * gateway + documents + geometry, no mocks.
 *
 * Overlap matches the design golden (`boolean-union-two-cubes-overlap`): two
 * 20 mm cubes offset 10 mm on X overlap by 4000 mm³ → union = 12000 mm³.
 */

/** A fully-constrained axis-aligned rectangle at (x0,y0), w×h, on XY. */
function rectangleSketch(x0: number, y0: number, w: number, h: number) {
  return {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [
      {
        id: "e1",
        kind: "line",
        start: { x: x0, y: y0 },
        end: { x: x0 + w, y: y0 },
      },
      {
        id: "e2",
        kind: "line",
        start: { x: x0 + w, y: y0 },
        end: { x: x0 + w, y: y0 + h },
      },
      {
        id: "e3",
        kind: "line",
        start: { x: x0 + w, y: y0 + h },
        end: { x: x0, y: y0 + h },
      },
      {
        id: "e4",
        kind: "line",
        start: { x: x0, y: y0 + h },
        end: { x: x0, y: y0 },
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
      { kind: "distance", entity: "e1", value_mm: w },
      { kind: "distance", entity: "e2", value_mm: h },
      { kind: "fixed", point: { entity: "e1", point: "start" } },
    ],
  };
}

/** POST one feature at the tree tip via the real gateway. */
async function createFeature(
  page: Page,
  token: string,
  partId: string,
  body: unknown,
): Promise<{ feature: { id: string }; tree_version: number }> {
  const response = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: body,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e create feature failed: ${response.status()} ${await response.text()}`,
    );
  }
  return (await response.json()) as {
    feature: { id: string };
    tree_version: number;
  };
}

/** Seed a part with two overlapping 20 mm cubes — the second a new body. */
async function seedTwoBodies(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Two cubes");

  // Body A — a 20×20 square at the origin, extruded 20 mm (default merge).
  const sketchA = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(0, 0, 20, 20),
    },
    expected_tree_version: 0,
  });
  const extrudeA = await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketchA.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
        merge: true,
      },
    },
    expected_tree_version: sketchA.tree_version,
  });

  // Body B — a 20×20 square offset 10 mm on X (overlapping A), extruded 20 mm
  // with merge: false so it starts a SECOND body.
  const sketchB = await createFeature(page, account.token, part.id, {
    name: "Sketch2",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(10, 0, 20, 20),
    },
    expected_tree_version: extrudeA.tree_version,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude2",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketchB.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
        merge: false,
      },
    },
    expected_tree_version: sketchB.tree_version,
  });
  return part;
}

/** The lit solid + B-rep edges paint far more shades than the empty ground. */
async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

test.describe("multi-body union", () => {
  test("two bodies combine into one fused solid", async ({ page }) => {
    const part = await seedTwoBodies(page);
    await page.goto(`/parts/${part.id}`);

    // The tree solved and the Bodies panel shows the two independent bodies.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("bodies-panel")).toBeVisible();
    await expect(page.getByTestId("body-row")).toHaveCount(2);
    await expectRenderedBody(page);

    // Combine is enabled with two bodies — author a union through the UI.
    const combine = page.getByTestId("new-combine");
    await expect(combine).toBeEnabled();
    await combine.click();
    await expect(page.getByTestId("combine-editor")).toBeVisible();
    // Defaults target = Body 1, tool = Body 2 — commit the union.
    await page.getByTestId("combine-submit").click();

    // The union fused them: exactly ONE body remains and the fused solid shows
    // the golden 12,000 mm³ (8000 + 8000 − 4000 overlap).
    await expect(page.getByTestId("combine-editor")).toBeHidden();
    await expect(page.getByTestId("body-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("12,000", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);
  });

  test("subtract removes the tool from the target (Target − Tool)", async ({
    page,
  }) => {
    const part = await seedTwoBodies(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("body-row")).toHaveCount(2, {
      timeout: 30_000,
    });

    await page.getByTestId("new-combine").click();
    await expect(page.getByTestId("combine-editor")).toBeVisible();
    // Pick Subtract — the role labels flip to the asymmetric Target − Tool.
    await page.getByTestId("combine-op-subtract").click();
    await expect(page.getByTestId("combine-op-subtract")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.getByTestId("combine-submit").click();

    // Target (8000) − overlap (4000) = 4000 mm³, one connected solid remains.
    await expect(page.getByTestId("combine-editor")).toBeHidden();
    await expect(page.getByTestId("body-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("4,000", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);
  });

  test("intersect keeps only the shared volume", async ({ page }) => {
    const part = await seedTwoBodies(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("body-row")).toHaveCount(2, {
      timeout: 30_000,
    });

    await page.getByTestId("new-combine").click();
    await expect(page.getByTestId("combine-editor")).toBeVisible();
    await page.getByTestId("combine-op-intersect").click();
    await expect(page.getByTestId("combine-op-intersect")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.getByTestId("combine-submit").click();

    // The common volume of the two cubes is the 10×20×20 overlap = 4000 mm³.
    await expect(page.getByTestId("combine-editor")).toBeHidden();
    await expect(page.getByTestId("body-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("4,000", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);
  });

  test("founder screenshot: fused multi-body union (desktop)", async ({
    page,
  }) => {
    const part = await seedTwoBodies(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("body-row")).toHaveCount(2, {
      timeout: 30_000,
    });

    await page.getByTestId("new-combine").click();
    await page.getByTestId("combine-submit").click();
    await expect(page.getByTestId("body-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("12,000", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/multibody-union-desktop.png`,
    });
  });

  test("founder screenshot: boolean operation selector + subtract result (desktop)", async ({
    page,
  }) => {
    const part = await seedTwoBodies(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("body-row")).toHaveCount(2, {
      timeout: 30_000,
    });
    await expectRenderedBody(page);

    // Open the editor and choose Subtract — the shot captures the union /
    // subtract / intersect selector with subtract's Target − Tool labelling
    // over the two-body scene.
    await page.getByTestId("new-combine").click();
    await expect(page.getByTestId("combine-editor")).toBeVisible();
    await page.getByTestId("combine-op-subtract").click();
    await expect(page.getByTestId("combine-op-subtract")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/multibody-boolean-ops-desktop.png`,
    });
  });
});
