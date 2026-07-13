import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * BACKLOG #2: the workspace viewport renders an evaluated-tree body. The
 * extrude-authoring UI is the NEXT item (#3), so this spec creates the
 * sketch + extrude features through the real gateway API — the same seam the
 * gateway e2e (`test_evaluate_e2e.py`) uses — then drives the browser to
 * prove the solid actually renders and its mass properties reach the
 * inspector. Real stack: gateway + documents + geometry, no mocks.
 */

/** §6 worked example: a 40×25 mm rectangle on XY, benchmark-constrained. */
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

/** Seed a part with Sketch1 (40×25) + Extrude1 (10 mm add) via the API. */
async function seedExtrudedPart(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Extruded plate");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: RECTANGLE_SKETCH },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 10,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part;
}

/** The lit aluminium solid + B-rep edges paint far more shades than ground. */
async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

test.describe("extrude body render", () => {
  test("evaluated body renders with mass properties; reload persists", async ({
    page,
  }) => {
    const part = await seedExtrudedPart(page);
    await page.goto(`/parts/${part.id}`);

    // Both features present and evaluated.
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // The body's mass properties reach the title-block inspector.
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expect(page.getByTestId("prop-volume")).toContainText("10,000");
    await expect(page.getByTestId("prop-extents")).toContainText(
      "40 × 25 × 10",
    );

    // The solid actually renders (non-empty canvas pixel check).
    await expectRenderedBody(page);

    // Reload: the tree re-evaluates and the body renders again through the API.
    await page.reload();
    await expect(page.getByTestId("prop-volume")).toContainText("10,000", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);
  });

  test("founder screenshot: extruded solid + mass properties (desktop)", async ({
    page,
  }) => {
    const part = await seedExtrudedPart(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("prop-volume")).toContainText("10,000", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-body-desktop.png`,
    });
  });
});

test.describe("extrude body small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("body stays the hero at laptop width; founder screenshot", async ({
    page,
  }) => {
    const part = await seedExtrudedPart(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("prop-volume")).toContainText("10,000", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);

    // Tree + inspector flank the viewport; the model still holds the centre.
    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(560);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-body-laptop.png`,
    });
  });
});
