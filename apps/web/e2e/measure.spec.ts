import { expect, test, type Page } from "@playwright/test";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * BACKLOG #6b: the measurement pick-and-read UI. This spec drives the REAL
 * stack (gateway + documents + geometry): it seeds a 10×20×30 box body through
 * the API, arms the Measure tool in the browser, picks two opposite corners in
 * the viewport overlay, and asserts the readout reads the golden distance
 * √1400 ≈ 37.42 mm — the same acceptance number the 6a backend gate pins. The
 * distance is server-authoritative (the UI echoes each picked vertex's exact
 * coordinates), so this ties the UI to the geometry golden, not a weakened check.
 */

interface Vec3 {
  x: number;
  y: number;
  z: number;
}

/** A 10×20 rectangle fixed at the origin on XY — solves to clean corners. */
const RECTANGLE_10x20 = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 9.7, y: 0.4 } },
    {
      id: "e2",
      kind: "line",
      start: { x: 10, y: 0.2 },
      end: { x: 10.3, y: 19 },
    },
    {
      id: "e3",
      kind: "line",
      start: { x: 10.2, y: 20.4 },
      end: { x: -0.3, y: 19.7 },
    },
    {
      id: "e4",
      kind: "line",
      start: { x: 0.3, y: 19.5 },
      end: { x: -0.2, y: 0.5 },
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
    { kind: "distance", entity: "e1", value_mm: 10 },
    { kind: "distance", entity: "e2", value_mm: 20 },
    { kind: "fixed", point: { entity: "e1", point: "start" } },
  ],
};

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

/** Seed a part whose body is a 10×20×30 box with a corner at the origin. */
async function seedBoxPart(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Measured box");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: RECTANGLE_10x20 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 30,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part;
}

/** Index of the overlay vertex nearest `target` (world mm), or -1. */
function vertexIndex(vertices: Vec3[], target: Vec3): number {
  return vertices.findIndex(
    (v) => Math.hypot(v.x - target.x, v.y - target.y, v.z - target.z) < 1e-4,
  );
}

test.describe("measurement", () => {
  test("pick two box corners → readout reads the golden √1400 distance", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);

    // The body renders (10×20×30 = 6,000 mm³).
    await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
      timeout: 30_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);

    // Arm the Measure tool; the overlay for the current body loads.
    const overlayResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v1/geometry/overlay") &&
        r.request().method() === "POST",
    );
    await page.getByTestId("measure-tool").click();
    await expect(page.getByTestId("measure-tool")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const overlay = (await (await overlayResponse).json()) as {
      vertices: Vec3[];
    };

    // The prompt invites the first pick.
    await expect(page.getByTestId("measure-prompt")).toContainText(
      "Pick a point or edge",
    );

    // Two OPPOSITE corners: (0,0,0) and (10,20,30) → distance √1400.
    const a = vertexIndex(overlay.vertices, { x: 0, y: 0, z: 0 });
    const b = vertexIndex(overlay.vertices, { x: 10, y: 20, z: 30 });
    expect(a).toBeGreaterThanOrEqual(0);
    expect(b).toBeGreaterThanOrEqual(0);

    const measureResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v1/geometry/measure") &&
        r.request().method() === "POST",
    );
    await page.getByTestId(`measure-vertex-${a}`).dispatchEvent("click");
    await expect(page.getByTestId("measure-prompt")).toContainText(
      "Pick the second point or edge",
    );
    await page.getByTestId(`measure-vertex-${b}`).dispatchEvent("click");
    expect((await measureResponse).status()).toBe(200);

    // THE assertion: the readout reads the golden distance.
    await expect(page.getByTestId("measure-readout-distance")).toHaveText(
      "37.42",
    );
    // Component deltas match the corner offset.
    await expect(page.getByTestId("measure-readout-dx")).toHaveText("+10.00");
    await expect(page.getByTestId("measure-readout-dy")).toHaveText("+20.00");
    await expect(page.getByTestId("measure-readout-dz")).toHaveText("+30.00");
    // Point-point has no angle.
    await expect(page.getByTestId("measure-readout-angle")).toHaveCount(0);

    // Clear resets to the prompt; exit disarms the tool.
    await page.getByTestId("measure-clear").click();
    await expect(page.getByTestId("measure-prompt")).toBeVisible();
    await page.getByTestId("measure-exit").click();
    await expect(page.getByTestId("measure-readout")).toHaveCount(0);
    await expect(page.getByTestId("measure-tool")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  test("founder screenshot: dimension line + readout (desktop)", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
      timeout: 30_000,
    });

    const overlayResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v1/geometry/overlay") &&
        r.request().method() === "POST",
    );
    await page.getByTestId("measure-tool").click();
    const overlay = (await (await overlayResponse).json()) as {
      vertices: Vec3[];
    };
    const a = vertexIndex(overlay.vertices, { x: 0, y: 0, z: 0 });
    const b = vertexIndex(overlay.vertices, { x: 10, y: 20, z: 30 });
    await page.getByTestId(`measure-vertex-${a}`).dispatchEvent("click");
    await page.getByTestId(`measure-vertex-${b}`).dispatchEvent("click");
    await expect(page.getByTestId("measure-readout-distance")).toHaveText(
      "37.42",
    );
    await page.screenshot({ path: `${SCREENSHOT_DIR}/measure-desktop.png` });
  });
});

test.describe("measurement small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("measurement stays viewport-dominant; founder screenshot", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
      timeout: 30_000,
    });

    const overlayResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v1/geometry/overlay") &&
        r.request().method() === "POST",
    );
    await page.getByTestId("measure-tool").click();
    const overlay = (await (await overlayResponse).json()) as {
      vertices: Vec3[];
    };
    const a = vertexIndex(overlay.vertices, { x: 0, y: 0, z: 0 });
    const b = vertexIndex(overlay.vertices, { x: 10, y: 20, z: 30 });
    await page.getByTestId(`measure-vertex-${a}`).dispatchEvent("click");
    await page.getByTestId(`measure-vertex-${b}`).dispatchEvent("click");
    await expect(page.getByTestId("measure-readout-distance")).toHaveText(
      "37.42",
    );

    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(560);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/measure-laptop.png` });
  });
});
