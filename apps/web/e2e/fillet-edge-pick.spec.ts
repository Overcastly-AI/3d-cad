import { expect, test, type Page } from "@playwright/test";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * The last-named Part-modeling blocker: CLICK-specific edge selection for
 * fillet/chamfer. Real stack (gateway + documents + geometry, no mocks). The
 * daily-driver payoff — round ONE edge and leave its neighbour sharp — is the
 * thing the `all_edges`/`axis_parallel` predicates structurally cannot express.
 *
 * Extrude a 20 mm cube → Fillet → "Pick edges" → click ONE top edge → apply
 * r5. The proof it rounded EXACTLY that edge (not all 12): a single-edge fillet
 * adds exactly one face to the cube's six (→ 7 faces); an all-edges fillet
 * rounds every edge + corner (26 faces). Then reload and re-assert — the picked
 * edge is named by a rebuild-surviving signature ref, so the body holds.
 */

/** A 20×20 rectangle fixed at the origin on XY — a clean 20 mm cube when extruded. */
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
  const part = await createPartViaApi(page, account.token, "Edge-pick cube");
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

async function waitForCube(page: Page): Promise<void> {
  await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
    timeout: 30_000,
  });
  await expect.poll(() => faceCount(page), { timeout: 30_000 }).toBe(6);
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/** The face count parsed from the topology readout. */
async function faceCount(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-faces").innerText();
  return Number.parseInt(text.replace(/[^\d]/g, ""), 10);
}

/**
 * Click the edge-pick node at the extreme z of the cube — a TOP edge
 * (midpoint z = 20) or a BOTTOM edge (z = 0), chosen from the accessible name
 * so the pick is deterministic (no reliance on screen projection or index). A
 * bottom edge projects low in the viewport, clear of the top-left editor and
 * the top HUD strips — the reliable target on the tight laptop width.
 */
async function clickExtremeEdge(
  page: Page,
  which: "top" | "bottom",
): Promise<void> {
  const nodes = page.locator('[data-testid^="edge-pick-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const count = await nodes.count();
  let bestZ = which === "top" ? -Infinity : Infinity;
  let bestIndex = 0;
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const z = Number.parseFloat(nums[nums.length - 1] as string);
    if (!Number.isFinite(z)) continue;
    if (which === "top" ? z > bestZ : z < bestZ) {
      bestZ = z;
      bestIndex = i;
    }
  }
  await nodes.nth(bestIndex).click();
}

test.describe("fillet — pick edges", () => {
  test("round ONE picked top edge; neighbours stay sharp; reload holds", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);
    await expect(page.getByTestId("feature-row")).toHaveCount(2);

    // Open the fillet editor, set r5, switch to "Pick edges".
    await page.getByTestId("new-fillet").click();
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await page.getByTestId("fillet-radius").fill("5");
    await page.getByTestId("fillet-mode-pick").click();

    // A 20 mm cube exposes all 12 B-rep edges as pick targets.
    await expect(page.locator('[data-testid^="edge-pick-"]')).toHaveCount(12);
    await expect(page.getByTestId("selected-count")).toHaveText(
      "No edges picked",
    );

    // Pick exactly ONE top edge → the count + highlight update.
    await clickExtremeEdge(page, "top");
    await expect(page.getByTestId("selected-count")).toHaveText(
      "1 edge picked",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/fillet-edge-pick-selected-desktop.png`,
    });

    // Apply — the fillet lands as the third feature and the body rebuilds.
    await page.getByTestId("fillet-submit").click();
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("feature-row").nth(2)).toContainText(
      "fillet",
    );
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);

    // THE PROOF: exactly ONE edge rounded. A single-edge fillet adds one
    // cylindrical face to the cube's six (→ 7); an all-edges fillet would round
    // all 12 edges + 8 corners (26 faces). 7 ≠ 26 — one edge, neighbours sharp.
    await expect.poll(() => faceCount(page), { timeout: 30_000 }).toBe(7);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/fillet-edge-pick-rounded-desktop.png`,
    });

    // Reload: the picked edge is a rebuild-surviving signature ref, so the
    // single-edge fillet re-resolves through the real API and the body holds.
    await page.reload();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect.poll(() => faceCount(page), { timeout: 30_000 }).toBe(7);
  });

  test.describe("small laptop (1280×800)", () => {
    test.use({ viewport: { width: 1280, height: 800 } });

    test("the edge-pick flow keeps the viewport dominant; founder screenshot", async ({
      page,
    }) => {
      const partId = await seedCubePart(page);
      await page.goto(`/parts/${partId}`);
      await waitForCube(page);

      await page.getByTestId("new-fillet").click();
      await page.getByTestId("fillet-radius").fill("5");
      await page.getByTestId("fillet-mode-pick").click();
      await clickExtremeEdge(page, "bottom");
      await expect(page.getByTestId("selected-count")).toHaveText(
        "1 edge picked",
      );
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/fillet-edge-pick-selected-laptop.png`,
      });

      // The viewport still owns the width — chrome recedes (design mandate #3).
      const box = await page.getByTestId("viewport").boundingBox();
      expect(box?.width ?? 0).toBeGreaterThan(560);
    });
  });
});
