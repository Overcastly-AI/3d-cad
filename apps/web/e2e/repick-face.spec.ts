import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Re-pick repair affordance (FINDINGS #3 follow-up). The kernel now re-matches a
 * same-face reference resiliently, so a hole whose placement face is GENUINELY
 * unresolvable surfaces as a typed `subshape_unresolved` FeatureError. This spec
 * proves the frontend repair: the tree error row offers a one-click "Re-pick
 * face" that opens the hole editor AND re-arms its face pick, so the user can
 * re-attach the lost reference — verified against the real stack (no mocks).
 *
 * The unresolvable state is seeded directly: a hole feature carrying a bogus
 * planar-face signature (an area/centroid/normal that matches no face of the
 * cube), which the resolver cannot re-match → `subshape_unresolved`.
 */

/** A closed, fully-constrained 20×20 square on XY → a face that extrudes. */
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

/** Seed a 20 mm cube plus a hole whose placement face cannot be resolved. */
async function seedUnresolvableHole(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Re-pick plate");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  const extrude = await createFeature(page, account.token, part.id, {
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
  await createFeature(page, account.token, part.id, {
    name: "Hole1",
    feature: {
      type: "hole",
      version: 1,
      params: {
        face: {
          kind: "subshape",
          feature_id: extrude.feature.id,
          subshape_type: "face",
          selector: {
            selector_version: 1,
            signature: {
              subshape_type: "face",
              surface: "plane",
              // Deliberately off the body: no face of the cube has this
              // area/centroid/normal, so the resilient resolver still can't
              // match it → subshape_unresolved.
              area_mm2: 987654,
              centroid: { x: 500, y: 500, z: 500 },
              normal: { x: 0, y: 0, z: 1 },
            },
          },
        },
        position: { x: 500, y: 500, z: 500 },
        diameter_mm: 5,
        depth: { kind: "through_all" },
      },
    },
    expected_tree_version: extrude.tree_version,
  });
  return part.id;
}

test.describe("re-pick repair — a lost face reference is re-attachable", () => {
  test("subshape_unresolved offers Re-pick face → arms the hole face pick", async ({
    page,
  }) => {
    const partId = await seedUnresolvableHole(page);
    await page.goto(`/parts/${partId}`);

    // The tree evaluates and the Hole row (index 2) reports the typed error.
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    const errorRow = page.getByTestId("feature-error-2");
    await expect(errorRow).toBeVisible();
    await expect(errorRow).toContainText("subshape_unresolved");

    // The last-good body (the extrude) still renders — wait for it so the frame
    // captures the lit solid, not a pre-paint flash.
    await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
      timeout: 30_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);

    // Before: the honest error with its one-click repair affordance.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/repick-face-error-desktop.png`,
    });

    // The repair is offered and re-arms the face pick for the hole feature.
    const repick = page.getByTestId("feature-repick-face-2");
    await expect(repick).toBeVisible();
    await repick.click();

    // The hole editor opens with its FACE pick armed — the user can now re-pick.
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // After: the hole editor open, face selection re-armed.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/repick-face-armed-desktop.png`,
    });
  });
});
