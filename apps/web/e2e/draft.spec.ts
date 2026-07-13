import { expect, test, type Page } from "@playwright/test";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Draft — the mold-release taper: tilt picked faces of a body by a constant
 * angle about a neutral (parting) plane so the part pulls cleanly from a die.
 * Real stack (gateway + documents + geometry, no mocks). The daily-driver
 * payoff is a real tapered/frustum body, so the proof is VOLUME:
 *
 *  - TAPER (the payoff): extrude a 20 mm cube (8,000 mm³) → Draft → pick the 4
 *    SIDE faces → 5° about the XY neutral plane (z=0, the base) → apply. Each
 *    side tilts INWARD going up (positive = toward pull), so the top narrows to
 *    a ~16.5 mm square and the body becomes a frustum well under 8,000 mm³.
 *  - TOO-LARGE (the honest failure): the same pick at 80° collapses the tapered
 *    faces — OCCT raises, so the feature lands but the rebuild is a legible
 *    `draft_failed` in the tree, never a silently wrong solid.
 */

/** A 20×20 rectangle fixed at the origin on XY — a clean 20 mm cube extruded. */
const SQUARE_20 = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 20, y: 0 } },
    { id: "e2", kind: "line", start: { x: 20, y: 0 }, end: { x: 20, y: 20 } },
    { id: "e3", kind: "line", start: { x: 20, y: 20 }, end: { x: 0, y: 20 } },
    { id: "e4", kind: "line", start: { x: 0, y: 20 }, end: { x: 0, y: 0 } },
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
    { kind: "distance", entity: "e1", value_mm: 20 },
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

/** Seed a part whose body is a 20 mm cube (8,000 mm³) at the origin. */
async function seedCubePart(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Draft cube");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part.id;
}

/** The volume value parsed from the mass readout cell (commas stripped). */
async function volume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  return Number.parseFloat(text.replace(/,/g, "").replace(/[^\d.-]/g, ""));
}

/** The face count parsed from the topology readout cell. */
async function faceCount(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-faces").innerText();
  return Number.parseInt(text.replace(/[^\d]/g, ""), 10);
}

async function waitForCube(page: Page): Promise<void> {
  await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
    timeout: 30_000,
  });
  await expect.poll(() => faceCount(page), { timeout: 30_000 }).toBe(6);
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/**
 * Click every SIDE face-pick node of the cube — the four whose centroid sits at
 * mid-height (z ≈ 10), read from the accessible name so the pick is
 * deterministic (no reliance on screen projection or index). The top (z = 20)
 * and bottom (z = 0) faces are left untouched.
 */
async function pickSideFaces(page: Page): Promise<number> {
  const nodes = page.locator('[data-testid^="draft-face-"]');
  // All 6 cube faces render a pick node; wait for the full overlay to settle.
  await expect(nodes).toHaveCount(6, { timeout: 20_000 });
  const count = await nodes.count();
  let picked = 0;
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const z = Number.parseFloat(nums[nums.length - 1] as string);
    if (Number.isFinite(z) && Math.abs(z - 10) < 0.5) {
      // Dispatch the click straight to the node: several side faces project
      // UNDER the top-left editor panel, so a hit-tested mouse click would land
      // on the panel. These are DOM-in-canvas buttons, so a direct click event
      // drives the same React onClick QA would (no reliance on projection).
      await nodes.nth(i).dispatchEvent("click");
      picked += 1;
    }
  }
  return picked;
}

test.describe("draft — taper faces for mold release", () => {
  test("pick the 4 side faces → a tapered frustum (the payoff)", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/draft-before-solid-desktop.png`,
    });

    // Open the draft editor: a 20 mm cube exposes all 6 planar faces as targets.
    await page.getByTestId("new-draft").click();
    await expect(page.getByTestId("draft-editor")).toBeVisible();
    await page.getByTestId("draft-angle").fill("5");
    // The default neutral plane is the XY datum (z=0, the cube base).
    await expect(page.getByTestId("draft-neutral-base-XY")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.locator('[data-testid^="draft-face-"]')).toHaveCount(6, {
      timeout: 20_000,
    });
    await expect(page.getByTestId("draft-taper-count")).toHaveText(
      "No faces picked yet",
    );
    // Apply is guarded until at least one face is picked (`no_draft_faces`).
    await expect(page.getByTestId("draft-submit")).toBeDisabled();

    // Pick the four side faces → the live count updates.
    const picked = await pickSideFaces(page);
    expect(picked).toBe(4);
    await expect(page.getByTestId("draft-taper-count")).toHaveText(
      "4 faces tapered",
    );
    await expect(page.getByTestId("draft-submit")).toBeEnabled();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/draft-pick-faces-desktop.png`,
    });

    // Apply — the draft lands as the third feature and the body rebuilds.
    await page.getByTestId("draft-submit").click();
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("feature-row").nth(2)).toContainText("draft");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // THE PROOF: an inward taper removes material — the cube (8,000 mm³) becomes
    // a frustum (top narrowed to ~16.5 mm), so the volume drops well below the
    // solid box while the body stays valid and renders.
    await expect
      .poll(() => volume(page), { timeout: 30_000 })
      .toBeGreaterThan(5_500);
    await expect
      .poll(() => volume(page), { timeout: 30_000 })
      .toBeLessThan(7_900);
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/draft-tapered-desktop.png`,
    });

    // Reload: the picked faces are rebuild-surviving signature refs, so the
    // tapered body re-resolves through the real API and holds.
    await page.reload();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect
      .poll(() => volume(page), { timeout: 30_000 })
      .toBeLessThan(7_900);
  });

  test("too large an angle surfaces a legible draft_failed", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);

    await page.getByTestId("new-draft").click();
    await expect(page.getByTestId("draft-editor")).toBeVisible();
    // 80° is in the accepted (-90, 90) range, so it writes — but it collapses
    // the tapered faces of a 20 mm cube, so the rebuild fails honestly.
    await page.getByTestId("draft-angle").fill("80");
    const picked = await pickSideFaces(page);
    expect(picked).toBe(4);

    await page.getByTestId("draft-submit").click();
    // The feature lands (write succeeds) but the tree shows the rebuild failure.
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toContainText(
      "draft_failed",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/draft-failed-desktop.png`,
    });
  });

  test.describe("small laptop (1280×800)", () => {
    test.use({ viewport: { width: 1280, height: 800 } });

    test("the draft face-pick keeps the viewport dominant; founder screenshot", async ({
      page,
    }) => {
      const partId = await seedCubePart(page);
      await page.goto(`/parts/${partId}`);
      await waitForCube(page);

      await page.getByTestId("new-draft").click();
      await page.getByTestId("draft-angle").fill("5");
      const picked = await pickSideFaces(page);
      expect(picked).toBe(4);
      await expect(page.getByTestId("draft-taper-count")).toHaveText(
        "4 faces tapered",
      );
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/draft-pick-faces-laptop.png`,
      });

      // The viewport still owns the width — chrome recedes (design mandate #3).
      const box = await page.getByTestId("viewport").boundingBox();
      expect(box?.width ?? 0).toBeGreaterThan(560);
    });
  });
});
