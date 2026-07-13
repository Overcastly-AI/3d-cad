import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Shell — the housing / enclosure primitive: hollow a solid to a uniform wall,
 * opening picked faces. Real stack (gateway + documents + geometry, no mocks).
 * The daily-driver payoff is a real cavity, so the proof is VOLUME, not pixels:
 *
 *  - OPEN-TOP (the money shot — a housing): extrude a 20 mm cube (8,000 mm³) →
 *    Shell → pick the TOP face → 2 mm wall → apply. The cavity is a 16×16×18
 *    box open at the top (4,608 mm³ removed), so the body drops to 3,392 mm³
 *    and gains interior faces — well below the solid box.
 *  - SEALED (no face picked): a fully-enclosed hollow — the cavity is inset on
 *    all six sides (16³ = 4,096 mm³ removed), so the body is 8,000 − 4,096 =
 *    3,904 mm³ (outer − inner), with no opening.
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
  const part = await createPartViaApi(page, account.token, "Shell cube");
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

/** The count parsed from a topology / mass readout cell. */
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
 * Click the shell face-pick node at the extreme z of the cube — the TOP face
 * (centroid z = 20) or the BOTTOM face (z = 0), chosen from the accessible name
 * so the pick is deterministic (no reliance on screen projection or index).
 */
async function clickExtremeFace(
  page: Page,
  which: "top" | "bottom",
): Promise<void> {
  const nodes = page.locator('[data-testid^="shell-face-"]');
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

test.describe("shell — hollow a body", () => {
  test("pick the TOP face → an open-top hollow (the money shot)", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/shell-before-solid-desktop.png`,
    });

    // Open the shell editor: a 20 mm cube exposes all 6 planar faces as targets.
    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await page.getByTestId("shell-thickness").fill("2");
    await expect(page.locator('[data-testid^="shell-face-"]')).toHaveCount(6);
    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "No faces open — a sealed hollow",
    );

    // Pick exactly the TOP face → the open-count updates.
    await clickExtremeFace(page, "top");
    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "1 face open",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/shell-pick-open-top-desktop.png`,
    });

    // Apply — the shell lands as the third feature and the body rebuilds.
    await page.getByTestId("shell-submit").click();
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("feature-row").nth(2)).toContainText("shell");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // THE PROOF: an open-top cavity. Solid 8,000 → shell 3,392 mm³ (a 16×16×18
    // hole scooped out), and interior faces appear (a real cavity, not a facet).
    await expect(page.getByTestId("prop-volume")).toContainText("3,392", {
      timeout: 30_000,
    });
    await expect
      .poll(() => faceCount(page), { timeout: 30_000 })
      .toBeGreaterThan(6);
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/shell-open-top-hollow-desktop.png`,
    });

    // Reload: the picked face is a rebuild-surviving signature ref, so the
    // open-top shell re-resolves through the real API and the body holds.
    await page.reload();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("3,392", {
      timeout: 30_000,
    });
  });

  test("no face picked → a fully sealed hollow (outer − inner)", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);

    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await page.getByTestId("shell-thickness").fill("2");
    // Leave every face closed — the honest default is a sealed hollow.
    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "No faces open — a sealed hollow",
    );

    await page.getByTestId("shell-submit").click();
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // A sealed hollow removes a fully-enclosed 16³ cavity: 8,000 − 4,096 =
    // 3,904 mm³ (outer − inner), with no opening.
    await expect(page.getByTestId("prop-volume")).toContainText("3,904", {
      timeout: 30_000,
    });
  });

  test.describe("small laptop (1280×800)", () => {
    test.use({ viewport: { width: 1280, height: 800 } });

    test("the shell face-pick keeps the viewport dominant; founder screenshot", async ({
      page,
    }) => {
      const partId = await seedCubePart(page);
      await page.goto(`/parts/${partId}`);
      await waitForCube(page);

      await page.getByTestId("new-shell").click();
      await page.getByTestId("shell-thickness").fill("2");
      // A bottom face projects low in the viewport, clear of the top-left editor
      // and the top HUD strips — the reliable target on the tight laptop width.
      await clickExtremeFace(page, "bottom");
      await expect(page.getByTestId("shell-open-count")).toHaveText(
        "1 face open",
      );
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/shell-pick-open-laptop.png`,
      });

      // The viewport still owns the width — chrome recedes (design mandate #3).
      const box = await page.getByTestId("viewport").boundingBox();
      expect(box?.width ?? 0).toBeGreaterThan(560);
    });
  });
});
